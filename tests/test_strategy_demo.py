"""The browser walkthrough must use only the fixed offline strategy fixture."""
import hashlib
import json

from fastapi.testclient import TestClient
import pytest

from backend.core.data_format import canonical_json
from backend.main import create_app
from scripts.reproduce import EXPECTED


RUN = "/api/demo/strategy/run"
REPLAY = "/api/demo/strategy/replay"


def digest(package):
    package.pop("sha256", None)
    package["sha256"] = hashlib.sha256(canonical_json(package).encode("utf-8")).hexdigest()
    return canonical_json(package)


def file_hashes(root):
    return {path.relative_to(root): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in root.rglob("*") if path.is_file()}


@pytest.fixture
def client(tmp_path, monkeypatch):
    def unexpected_download(*args, **kwargs):
        pytest.fail("An offline demo must not request market data")

    monkeypatch.setattr("backend.core.data_center.DataCenter.fetch_stock_data", unexpected_download)
    with TestClient(create_app(tmp_path / "workspace", run_jobs=False)) as test_client:
        yield test_client


def test_demo_uses_cli_reference_and_never_touches_workspace(client, tmp_path):
    workspace = tmp_path / "workspace"
    # Keep an existing run in the normal registry while the demo runs twice.
    existing = client.post("/api/runs", json={})
    assert existing.status_code == 202
    saved_runs = client.get("/api/runs").json()
    before = file_hashes(workspace)
    baseline_response = client.post(RUN, json={})
    assert baseline_response.status_code == 200, baseline_response.text
    baseline = baseline_response.json()
    assert baseline["synthetic"] is True
    assert baseline["snapshot"]["sha256"] == EXPECTED["snapshot_sha256"]
    assert baseline["snapshot"]["suspension_dates"] == ["2024-03-04"]
    assert baseline["period"]["observations"] == EXPECTED["observations"] == len(baseline["series"])
    assert baseline["period"]["warmup_rows"] == 65
    assert baseline["metrics"]["trade_count"] == EXPECTED["trades"] == len(baseline["trades"])
    assert all(trade["signal_date"] < trade["date"] for trade in baseline["trades"])
    assert baseline["result_sha256"] == EXPECTED["result_sha256"]
    assert str(tmp_path) not in baseline["evidence"]

    alternative_response = client.post(RUN, json={"fast_period": 8, "slow_period": 30})
    assert alternative_response.status_code == 200, alternative_response.text
    alternative = alternative_response.json()
    assert alternative["snapshot"] == baseline["snapshot"]
    assert alternative["period"] == baseline["period"]
    assert alternative["account"] == baseline["account"]
    assert alternative["metrics"]["benchmark_return"] == baseline["metrics"]["benchmark_return"]
    assert alternative["result_sha256"] != baseline["result_sha256"]

    replay_response = client.post(REPLAY, json={"evidence": alternative["evidence"]})
    assert replay_response.status_code == 200, replay_response.text
    assert replay_response.json() == {
        "synthetic": True, "snapshot_sha256": EXPECTED["snapshot_sha256"],
        "result_sha256": alternative["result_sha256"], "matched": True,
        "compared_fields": ["metrics", "series", "trades", "decisions"], "different_fields": [],
    }
    assert client.get("/api/runs").json() == saved_runs
    assert file_hashes(workspace) == before


@pytest.mark.parametrize("payload", [
    {"fast_period": 20, "slow_period": 20},
    {"fast_period": 2, "slow_period": 61},
    {"fast_period": 1},
    {"fast_period": True},
    {"fast_period": "5"},
    {"source": "akshare"},
])
def test_demo_rejects_inputs_outside_its_fixed_scope(client, payload):
    assert client.post(RUN, json=payload).status_code == 422


def test_demo_discards_non_demo_and_corrupted_evidence_and_reports_real_mismatch(client):
    baseline = client.post(RUN, json={}).json()
    raw = baseline["evidence"]
    assert client.post(REPLAY, json={"evidence": "{"}).status_code == 422
    assert client.post(REPLAY, json={"evidence": "x" * 300_001}).status_code == 422

    package = json.loads(raw)
    package["datasets"][0]["rows"][0]["is_suspended"] = True
    assert client.post(REPLAY, json={"evidence": digest(package)}).status_code == 422

    package = json.loads(raw)
    package["run"]["config"]["source"] = "akshare"
    assert client.post(REPLAY, json={"evidence": digest(package)}).status_code == 422

    package = json.loads(raw)
    package["run"]["result"]["decisions"][0]["action"] = "changed"
    assert client.post(REPLAY, json={"evidence": canonical_json(package)}).status_code == 422
    # A valid content hash still does not guarantee the saved decisions reproduce.
    response = client.post(REPLAY, json={"evidence": digest(package)})
    assert response.status_code == 200, response.text
    replay = response.json()
    assert replay["matched"] is False
    assert replay["different_fields"] == ["decisions"]
    assert replay["result_sha256"] == baseline["result_sha256"]
