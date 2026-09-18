"""Cross-layer invariants: API -> stored snapshots -> engine -> evidence replay."""
import hashlib
import json
from pathlib import Path

from fastapi.testclient import TestClient
import pandas as pd
import pytest

from backend.core.data_center import canonical_json, frame_hash, frame_records, validate_frame
from backend.main import create_app
from backend.research import calculate_metrics
from backend.services.provenance import engine_fingerprint
from backend.services.runner import execute_job


def finish(client, app, identifier):
    app.state.store.patch_run(identifier, status="running")
    execute_job(str(app.state.store.root), identifier)
    result = client.get(f"/api/runs/{identifier}").json()
    assert result["status"] == "completed", result.get("error")
    return result


@pytest.fixture
def study(tmp_path):
    app = create_app(tmp_path, run_jobs=False)
    with TestClient(app) as client:
        response = client.post("/api/runs", json={"name": "Invariant baseline", "tickers": ["000858"],
                                                 "start_date": "2024-01-01", "end_date": "2024-06-28",
                                                 "account": {"position_size": .8}})
        assert response.status_code == 202, response.text
        run = finish(client, app, response.json()["id"])
        yield client, app, run


def test_nested_api_branches_keep_frozen_parent_data_and_state(study):
    client, app, baseline = study
    dates = [s["date"] for s in baseline["result"]["series"]]
    first_date, second_date = dates[40], dates[80]
    response = client.post(f"/api/runs/{baseline['id']}/branch", json={"fork_date": first_date, "account": {"position_size": .4}})
    assert response.status_code == 202, response.text
    parent = finish(client, app, response.json()["id"])
    response = client.post(f"/api/runs/{parent['id']}/branch", json={"fork_date": second_date, "account": {"position_size": .15}})
    assert response.status_code == 202, response.text
    child = finish(client, app, response.json()["id"])
    assert child["branch"]["history"] == [parent["branch"]]
    assert child["manifest"] == baseline["manifest"]
    for key in ("series", "trades"):
        assert [r for r in child["result"][key] if r["date"] <= second_date] == [r for r in parent["result"][key] if r["date"] <= second_date]
    assert client.get(f"/api/runs/{baseline['id']}").json()["result"] == baseline["result"]
    rejected = client.post(f"/api/runs/{parent['id']}/branch", json={"fork_date": dates[0], "account": {"position_size": .2}})
    assert rejected.status_code == 422


def test_blind_session_contains_only_visible_evidence_and_metrics(study):
    client, _, run = study
    session = client.post(f"/api/runs/{run['id']}/sessions", json={"cursor": 10}).json()
    result, cutoff = session["result"], session["date"]
    assert len(result["series"]) == 11
    for key in ("series", "trades", "decisions", "checkpoints"):
        assert all(row["date"] <= cutoff for row in result[key])
    assert all(row["date"] <= cutoff for bars in result["bars"].values() for row in bars)
    for checkpoint in result["checkpoints"]:
        assert all(order["signal_date"] <= checkpoint["date"] for order in checkpoint["pending_orders"])
    assert result["metrics"] == calculate_metrics(result["series"], result["trades"], run["config"]["account"]["initial_cash"])
    assert result["metrics"]["trading_days"] == 11
    next_session = client.post(f"/api/sessions/{session['id']}/advance", json={"steps": 3}).json()
    assert next_session["result"]["series"][:11] == result["series"]
    assert not next_session["revealed"]
    revealed = client.post(f"/api/sessions/{session['id']}/reveal").json()
    assert revealed["revealed"] and revealed["revealed_at"]
    assert revealed["result"]["metrics"] == run["result"]["metrics"]


def test_nested_branch_export_import_replays_identically(study):
    client, app, baseline = study
    dates = [s["date"] for s in baseline["result"]["series"]]
    parent = baseline
    for index, size in [(35, .5), (80, .2)]:
        response = client.post(f"/api/runs/{parent['id']}/branch", json={"fork_date": dates[index], "account": {"position_size": size}})
        assert response.status_code == 202
        parent = finish(client, app, response.json()["id"])
    package = client.get(f"/api/runs/{parent['id']}/export").json()
    response = client.post("/api/import", json=package)
    assert response.status_code == 202, response.text
    replay = finish(client, app, response.json()["id"])
    assert replay["result"]["replay_verification"]["matched"] is True
    assert replay["result"]["series"] == parent["result"]["series"]
    assert replay["result"]["trades"] == parent["result"]["trades"]
    assert replay["branch"] == parent["branch"]


def test_branch_experiments_fail_explicitly_instead_of_dropping_parent_policy(study):
    client, app, base = study
    response = client.post(f"/api/runs/{base['id']}/branch", json={"fork_date": base["result"]["series"][30]["date"], "account": {"position_size": .2}})
    branch = finish(client, app, response.json()["id"])
    response = client.post(f"/api/runs/{branch['id']}/experiments", json={"kind": "pressure"})
    assert response.status_code == 422


def test_corrupt_evidence_payload_is_rejected(study):
    client, _, base = study
    package = client.get(f"/api/runs/{base['id']}/export").json()
    package["datasets"][0]["rows"][0]["volume"] += 100
    # Re-signing the outer JSON must not bypass the dataset fingerprint.
    package["sha256"] = hashlib.sha256(canonical_json({k: v for k, v in package.items() if k != "sha256"}).encode()).hexdigest()
    response = client.post("/api/import", json=package)
    assert response.status_code == 422
    assert "SHA256" in response.json()["detail"]


def test_replay_detects_inconsistent_expected_accounting(study):
    client, app, base = study
    package = client.get(f"/api/runs/{base['id']}/export").json()
    package["run"]["result"]["metrics"]["final_equity"] += 1
    package["sha256"] = hashlib.sha256(canonical_json({k: v for k, v in package.items() if k != "sha256"}).encode()).hexdigest()
    response = client.post("/api/import", json=package)
    assert response.status_code == 202, response.text
    replay = finish(client, app, response.json()["id"])
    assert replay["result"]["replay_verification"]["matched"] is False
    assert "metrics" in replay["result"]["replay_verification"]["different_fields"]


def test_import_rejects_evidence_without_verifiable_results(study):
    client, _, base = study
    package = client.get(f"/api/runs/{base['id']}/export").json()
    package["run"]["result"] = {"unrelated": "must not pass an empty comparison"}
    package["sha256"] = hashlib.sha256(canonical_json({k: v for k, v in package.items() if k != "sha256"}).encode()).hexdigest()
    response = client.post("/api/import", json=package)
    assert response.status_code == 422


def test_engine_fingerprint_includes_actual_matching_implementation(monkeypatch):
    baseline = engine_fingerprint()
    original_read = Path.read_bytes

    def changed_matching_file(path):
        return original_read(path) + (b"\n# hypothetical engine modification\n" if path.name == "engine.py" else b"")

    monkeypatch.setattr(Path, "read_bytes", changed_matching_file)
    assert engine_fingerprint()["source_sha256"] != baseline["source_sha256"]


def test_export_keeps_fingerprint_captured_when_the_run_executed(study, monkeypatch):
    client, _, base = study
    captured = base["result"]["engine"]
    monkeypatch.setattr("backend.services.provenance.engine_fingerprint", lambda: {"version": "changed", "source_sha256": "changed"})
    monkeypatch.setattr("backend.services.runner.engine_fingerprint", lambda: {"version": "changed", "source_sha256": "changed"})
    package = client.get(f"/api/runs/{base['id']}/export").json()
    assert package["engine"] == captured


def test_market_price_precision_survives_evidence_json_roundtrip():
    price = 10.000000000041
    source = validate_frame(pd.DataFrame([{"date": "2024-01-01", "open": price, "close": price,
                                          "high": price, "low": price, "volume": 10000}]))
    serialized = canonical_json(frame_records(source))
    restored = validate_frame(pd.DataFrame(json.loads(serialized)))
    assert restored.open.iloc[0] == price
    assert frame_hash(restored) == frame_hash(source)


@pytest.mark.parametrize("value", [float("nan"), float("inf"), -float("inf")])
def test_nonfinite_request_numbers_return_validation_error_instead_of_500(tmp_path, value):
    app = create_app(tmp_path, run_jobs=False)
    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.post("/api/runs", content=json.dumps({"account": {"commission_rate": value}}),
                               headers={"Content-Type": "application/json"})
        assert response.status_code == 422
        assert response.json()["detail"]


@pytest.mark.parametrize("case", ["unknown_account", "bad_strategy", "bad_date", "reverse_dates", "nontrading_date", "recursive_history"])
def test_import_checks_every_branch_history_entry_before_scheduling(study, case):
    client, _, base = study
    package = client.get(f"/api/runs/{base['id']}/export").json()
    dates = [s["date"] for s in base["result"]["series"]]
    history = [{"fork_date": dates[20], "account": {"position_size": .5}}]
    if case == "unknown_account":
        history[0]["account"] = {"initial_cash": 5}
    elif case == "bad_strategy":
        history[0]["strategy"] = {"name": "missing-strategy"}
    elif case == "bad_date":
        history[0]["fork_date"] = "not-a-date"
    elif case == "reverse_dates":
        history = [{"fork_date": dates[60]}, {"fork_date": dates[20]}]
    elif case == "nontrading_date":
        history[0]["fork_date"] = "2024-01-06"
    else:
        history[0]["history"] = [{"fork_date": dates[10]}]
    package["run"]["kind"] = "branch"
    package["run"]["branch"] = {"fork_date": dates[90], "history": history}
    package["sha256"] = hashlib.sha256(canonical_json({k: v for k, v in package.items() if k != "sha256"}).encode()).hexdigest()
    response = client.post("/api/import", json=package)
    assert response.status_code == 422, response.text


def test_import_normalizes_optional_null_branch_fields_before_engine(study):
    client, app, base = study
    package = client.get(f"/api/runs/{base['id']}/export").json()
    package["run"]["kind"] = "branch"
    package["run"]["branch"] = {"fork_date": base["result"]["series"][20]["date"],
                                "strategy": None, "account": None, "history": None, "name": None}
    package["sha256"] = hashlib.sha256(canonical_json({k: v for k, v in package.items() if k != "sha256"}).encode()).hexdigest()
    response = client.post("/api/import", json=package)
    assert response.status_code == 202, response.text
    replay = finish(client, app, response.json()["id"])
    assert replay["result"]["replay_verification"]["matched"] is True
