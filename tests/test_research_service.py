from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient

from backend.api.schemas import BranchRequest, ExperimentRequest, RunConfig, StrategyConfig
from backend.main import create_app
from backend.services.errors import ResearchError
from backend.services.research import ResearchService
from backend.services.runner import execute_job
from backend.services.store import Store


@pytest.fixture
def service(tmp_path):
    return ResearchService(Store(tmp_path))


def baseline(service, strategy=None):
    config = RunConfig(strategy=strategy or {}, tickers=["000858"], start_date="2024-01-01", end_date="2024-06-30")
    run = service.create_run(config)
    service.store.patch_run(run["id"], status="completed", result={"series": [{"date": "2024-01-02"}, {"date": "2024-01-03"}]})
    return run


def test_service_submission_errors_cancellation_and_notification(service):
    service.runner = Mock()
    queued = service.create_run(RunConfig())
    service.runner.notify.assert_called_once()
    assert queued["status"] == "queued" and "experiment" not in queued
    with pytest.raises(ResearchError) as missing:
        service.get_run("missing")
    assert missing.value.status_code == 404
    with pytest.raises(ResearchError) as unfinished:
        service.create_experiment(queued["id"], ExperimentRequest(kind="pressure"))
    assert unfinished.value.status_code == 409
    service.runner = None
    assert service.cancel_run(queued["id"])["status"] == "cancelled"
    assert service.cancel_run(queued["id"])["status"] == "cancelled"
    for _ in range(20):
        service.create_run(RunConfig())
    with pytest.raises(ResearchError) as full:
        service.create_run(RunConfig())
    assert full.value.status_code == 429


def test_service_branch_history_and_errors(service):
    run = baseline(service)
    child = service.create_branch(run["id"], BranchRequest(fork_date="2024-01-03", account={"position_size": .2}))
    assert child["parent_id"] == run["id"] and child["kind"] == "branch"
    service.store.patch_run(child["id"], status="completed", result=service.store.get_run(run["id"])["result"])
    grandchild = service.create_branch(child["id"], BranchRequest(fork_date="2024-01-03"))
    assert grandchild["branch"]["history"] == [child["branch"]]
    for parent, day in [(run, "2024-01-04"), (child, "2024-01-02")]:
        with pytest.raises(ResearchError) as error:
            service.create_branch(parent["id"], BranchRequest(fork_date=day))
        assert error.value.status_code == 422


@pytest.mark.parametrize("strategy,key", [
    ({"name": "bollinger_bands", "parameters": {"std_dev": .1}}, "std_dev"),
    ({"name": "momentum", "parameters": {"threshold": 0}}, "threshold"),
    ({"name": "dual_ma", "parameters": {"fast_period": 498, "slow_period": 500}}, "slow_period"),
    ({"name": "rsi_reversal", "parameters": {"buy_threshold": 69, "sell_threshold": 70}}, "sell_threshold"),
])
def test_auto_candidates_are_distinct_and_valid_under_cross_constraints(service, strategy, key):
    parent = baseline(service, strategy)
    experiment = service.create_experiment(parent["id"], ExperimentRequest(kind="parameter", parameter=key))
    values = service.store.get_run(experiment["id"])["experiment"]["values"]
    assert len(set(values)) >= 2
    config = service.store.get_run(parent["id"])["config"]["strategy"]
    for value in values:
        StrategyConfig.model_validate({**config, "parameters": {**config["parameters"], key: value}})


def test_unknown_explicit_invalid_and_single_feasible_candidate_do_not_schedule(service):
    parent = baseline(service, {"name": "dual_ma", "parameters": {"fast_period": 2, "slow_period": 3}})
    for request in [ExperimentRequest(kind="parameter", parameter="unknown"),
                    ExperimentRequest(kind="parameter", parameter="fast_period"),
                    ExperimentRequest(kind="parameter", parameter="fast_period", values=[1, 2])]:
        with pytest.raises(ResearchError) as error:
            service.create_experiment(parent["id"], request)
        assert error.value.status_code == 422
    assert len(service.list_runs()["runs"]) == 1
    explicit = service.create_experiment(parent["id"], ExperimentRequest(kind="parameter", parameter="slow_period", values=[3, 4, 3]))
    assert service.store.get_run(explicit["id"])["experiment"]["values"] == [3, 4, 3]


@pytest.mark.parametrize("name,key,current", [("bollinger_bands", "std_dev", .1), ("momentum", "threshold", 0)])
def test_api_default_fractional_trials_complete(tmp_path, name, key, current):
    with TestClient(create_app(tmp_path, run_jobs=False)) as client:
        parent = client.post("/api/runs", json={"tickers": ["000858"], "start_date": "2024-01-01", "end_date": "2024-06-30",
                                                  "strategy": {"name": name, "parameters": {key: current}}}).json()
        store = client.app.state.store
        store.patch_run(parent["id"], status="running")
        execute_job(str(tmp_path), parent["id"])
        response = client.post(f"/api/runs/{parent['id']}/experiments", json={"kind": "parameter", "parameter": key})
        assert response.status_code == 202, response.text
        experiment = response.json()
        store.patch_run(experiment["id"], status="running")
        execute_job(str(tmp_path), experiment["id"])
        result = client.get(f"/api/runs/{experiment['id']}").json()
        assert result["status"] == "completed", result["error"]
        values = [variant["value"] for variant in result["result"]["variants"]]
        assert len(set(values)) >= 2 and all(0 <= value < 1 for value in values)
