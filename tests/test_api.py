import copy
import hashlib
import time
import shutil
import subprocess

import pytest
from fastapi.testclient import TestClient

from backend.core.data_center import canonical_json
from backend.main import create_app
from backend.services.runner import execute_job


@pytest.fixture
def client(tmp_path):
    with TestClient(create_app(tmp_path, run_jobs=False)) as test_client:
        yield test_client


def complete(client, run):
    identifier = run["id"]
    client.app.state.store.patch_run(identifier, status="running")
    execute_job(str(client.app.state.store.root), identifier)
    response = client.get(f"/api/runs/{identifier}")
    result = response.json()
    assert result["status"] == "completed", result["error"]
    return result


@pytest.fixture
def run(client):
    response = client.post("/api/runs", json={"tickers": ["000858"], "start_date": "2024-01-01", "end_date": "2024-08-30"})
    assert response.status_code == 202
    return complete(client, response.json())


def test_catalog_validation_and_explicit_data_source_errors(client, monkeypatch):
    catalog = client.get("/api/catalog").json()
    assert catalog["defaults"]["strategy"]["parameters"] == {"fast_period": 5, "slow_period": 20}
    assert catalog["sources"][0]["synthetic"] is True
    assert client.post("/api/runs", json={"tickers": ["../../secret"]}).status_code == 422
    assert client.post("/api/runs", json={"start_date": "2025-01-01", "end_date": "2024-01-01"}).status_code == 422
    assert client.post("/api/runs", json={"strategy": {"name": "dual_ma", "parameters": {"fast_period": 30, "slow_period": 20}}}).status_code == 422
    assert client.post("/api/runs", json={"strategy": {"name": "dual_ma", "parameters": None}}).status_code == 422
    assert client.post("/api/runs", json={"strategy": {"name": [], "parameters": {}}}).status_code == 422
    assert client.post("/api/runs", json={"tickers": ["999999"]}).status_code == 422
    monkeypatch.setattr("backend.main.importlib.util.find_spec", lambda _: None)
    response = client.post("/api/runs", json={"source": "akshare"})
    assert response.status_code == 503
    assert "演示" in response.json()["detail"]


def test_summary_notes_and_source_are_persisted(client, run):
    summary = client.get("/api/runs").json()["runs"][0]
    assert summary["synthetic"] is True and "result" not in summary
    assert summary["metrics"] == run["result"]["metrics"]
    created = client.post("/api/notes", json={"run_id": run["id"], "title": "核对成交", "body": "买入费用已纳入账本"}).json()
    assert client.get(f"/api/notes?run_id={run['id']}").json()["notes"][0] == created
    updated = client.put(f"/api/notes/{created['id']}", json={"run_id": run["id"], "title": "核对完成", "body": "已查看"}).json()
    assert updated["id"] == created["id"]
    assert client.delete(f"/api/notes/{created['id']}").json() == {"deleted": True}
    assert client.get("/api/data/status").json()["snapshot_count"] == 1


def test_blind_session_contains_only_visible_history_and_reveal_is_permanent(client, run):
    session = client.post(f"/api/runs/{run['id']}/sessions", json={}).json()
    assert session["cursor"] == 0 and not session["revealed"]
    assert len(session["result"]["series"]) == 1
    assert "config" not in session and "config" not in session["result"]
    assert session["result"]["metrics"]["final_equity"] == pytest.approx(session["result"]["series"][-1]["equity"], abs=.005)
    for key in ["series", "trades", "decisions", "checkpoints"]:
        assert all(row["date"] <= session["date"] for row in session["result"][key])
    assert all(row["date"] <= session["date"] for rows in session["result"]["bars"].values() for row in rows)
    advanced = client.post(f"/api/sessions/{session['id']}/advance", json={"steps": 20}).json()
    assert advanced["cursor"] == 20 and len(advanced["result"]["series"]) == 21
    assert client.post(f"/api/sessions/{session['id']}/advance", json={"steps": -1}).status_code == 422
    revealed = client.post(f"/api/sessions/{session['id']}/reveal").json()
    assert revealed["revealed"] and revealed["revealed_at"]
    assert revealed["result"]["metrics"] == run["result"]["metrics"]
    assert client.post(f"/api/sessions/{session['id']}/reveal").json()["revealed_at"] == revealed["revealed_at"]


def test_branch_and_nested_branch_reuse_data_and_preserve_parent_prefix(client, run):
    fork_date = run["result"]["series"][30]["date"]
    response = client.post(f"/api/runs/{run['id']}/branch", json={"fork_date": fork_date, "account": {"position_size": .15}})
    assert response.status_code == 202
    child = complete(client, response.json())
    assert child["manifest"] == run["manifest"]
    assert child["result"]["series"][:31] == run["result"]["series"][:31]
    second_date = child["result"]["series"][60]["date"]
    nested = complete(client, client.post(f"/api/runs/{child['id']}/branch", json={"fork_date": second_date}).json())
    assert nested["result"]["series"] == child["result"]["series"]
    assert len(nested["branch"]["history"]) == 1
    assert client.post(f"/api/runs/{child['id']}/branch", json={"fork_date": run["result"]["series"][10]["date"]}).status_code == 422
    assert client.post(f"/api/runs/{child['id']}/experiments", json={"kind": "pressure"}).status_code == 422


@pytest.mark.parametrize("kind", ["pressure", "parameter", "walk_forward"])
def test_experiments_execute_real_engine(client, run, kind):
    response = client.post(f"/api/runs/{run['id']}/experiments", json={"kind": kind, "training_days": 60, "test_days": 20})
    assert response.status_code == 202, response.text
    result = complete(client, response.json())["result"]
    if kind == "pressure":
        assert len(result["scenarios"]) == 5
        assert result["baseline"] == run["result"]["metrics"]
    elif kind == "parameter":
        assert len(result["variants"]) >= 2
        assert result["best_value"] in [row["value"] for row in result["variants"]]
    else:
        assert all(row["train_end"] < row["test_start"] for row in result["folds"])
        assert result["series"][0]["date"] > run["result"]["series"][0]["date"]


def test_export_import_recomputes_and_rejects_tampering(client, run):
    evidence = client.get(f"/api/runs/{run['id']}/export").json()
    assert evidence["engine"] == run["result"]["engine"]
    response = client.post("/api/import", json=evidence)
    assert response.status_code == 202, response.text
    replay = complete(client, response.json())
    assert replay["result"]["replay_verification"]["matched"] is True
    assert replay["result"]["metrics"] == run["result"]["metrics"]
    tampered = copy.deepcopy(evidence)
    tampered["datasets"][0]["rows"][0]["close"] *= 2
    assert client.post("/api/import", json=tampered).status_code == 422
    # Recomputing the envelope hash does not bypass a mismatching dataset hash.
    tampered["sha256"] = hashlib.sha256(canonical_json({k: v for k, v in tampered.items() if k != "sha256"}).encode()).hexdigest()
    assert client.post("/api/import", json=tampered).status_code == 422
    invalid = copy.deepcopy(evidence)
    invalid["run"]["result"] = {"fake": True}
    invalid["sha256"] = hashlib.sha256(canonical_json({k: v for k, v in invalid.items() if k != "sha256"}).encode()).hexdigest()
    assert client.post("/api/import", json=invalid).status_code == 422


def test_browser_file_upload_preserves_numeric_representation(client, run):
    executable = shutil.which("node")
    if executable is None:
        pytest.skip("Node is needed to reproduce browser JSON serialization")
    original = client.get(f"/api/runs/{run['id']}/export").text
    reserialized = subprocess.check_output(
        [executable, "-e", 'let s=""; process.stdin.setEncoding("utf8"); process.stdin.on("data",c=>s+=c); process.stdin.on("end",()=>process.stdout.write(JSON.stringify(JSON.parse(s))));'],
        input=original, text=True, encoding="utf-8")
    assert '"initial_cash":1000000.0' in original
    assert '"initial_cash":1000000,' in reserialized
    # The upload must send the untouched file text: JS Number discards the
    # int/float spelling and would invalidate the Python v2 evidence checksum.
    assert client.post("/api/import", content=reserialized, headers={"Content-Type": "application/json"}).status_code == 422
    response = client.post("/api/import", content=original, headers={"Content-Type": "application/json"})
    assert response.status_code == 202
    replay = complete(client, response.json())
    assert replay["result"]["replay_verification"]["matched"] is True


def test_queue_cancel_and_restart_preserve_completed_data(client, run):
    queued = client.post("/api/runs", json={}).json()
    assert client.post(f"/api/runs/{queued['id']}/cancel").json()["status"] == "cancelled"
    active = client.post("/api/runs", json={}).json()
    client.app.state.store.recover_interrupted()
    assert client.get(f"/api/runs/{active['id']}").json()["error"]["code"] == "interrupted"
    assert client.get(f"/api/runs/{run['id']}").json()["status"] == "completed"


def test_independent_process_worker_completes_and_running_task_can_be_cancelled(tmp_path):
    with TestClient(create_app(tmp_path)) as client:
        queued = client.post("/api/runs", json={"tickers": ["000858"], "start_date": "2024-01-01", "end_date": "2024-02-29"}).json()
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            run = client.get(f"/api/runs/{queued['id']}").json()
            if run["status"] in {"completed", "failed"}:
                break
            time.sleep(.1)
        assert run["status"] == "completed", run
        cancelled = client.post("/api/runs", json={"start_date": "2019-01-01", "end_date": "2026-09-18"}).json()
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            active = client.get(f"/api/runs/{cancelled['id']}").json()
            if active["status"] == "running":
                break
            time.sleep(.02)
        assert client.post(f"/api/runs/{cancelled['id']}/cancel").json()["status"] == "cancelled"
        time.sleep(.2)
        assert client.get(f"/api/runs/{cancelled['id']}").json()["status"] == "cancelled"
