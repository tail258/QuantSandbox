"""Contracts must validate real engine output without rewriting audit data."""
import copy

import pytest
from pydantic import TypeAdapter, ValidationError

from backend.api.responses import Run, RunList, ReplaySession
from backend.api.schemas import RunConfig
from backend.services.runner import execute_job
from backend.services.store import Store


@pytest.mark.parametrize("kind", ["backtest", "branch", "pressure", "parameter", "walk_forward"])
def test_real_run_contracts_preserve_results(tmp_path, kind):
    store = Store(tmp_path)
    config = RunConfig(start_date="2024-01-01", end_date="2024-06-30", tickers=["000858"]).model_dump(mode="json")
    options = {"parameter": "fast_period", "values": [3, 5], "training_days": 30, "test_days": 20}
    run = store.create_run(config, kind=kind, experiment=options)
    adapter = TypeAdapter(Run)
    public = {k: v for k, v in run.items() if k not in {"expected_result", "experiment"}}
    assert adapter.validate_python(public).model_dump() == public
    store.patch_run(run["id"], status="running")
    execute_job(str(tmp_path), run["id"])
    completed = store.get_run(run["id"])
    assert completed["status"] == "completed", completed["error"]
    public = {k: v for k, v in completed.items() if k not in {"expected_result", "experiment"}}
    public["result"]["future_audit_field"] = {"exact": 0.12345678901234566, "integer": 9007199254740993}
    assert adapter.validate_python(public).model_dump() == public
    summary = {"runs": store.list_runs()}
    assert RunList.model_validate(summary).model_dump() == summary
    broken = copy.deepcopy(public)
    broken["result"].pop("engine")
    with pytest.raises(ValidationError):
        adapter.validate_python(broken)
    if kind == "backtest":
        result = {k: public["result"][k] for k in ("series", "bars", "trades", "decisions", "checkpoints", "metrics")}
        session = dict(id="session", run_id=run["id"], cursor=0, date=result["series"][0]["date"],
                       total_steps=len(result["series"]), revealed=False, revealed_at=None,
                       source="demo", synthetic=True, result=result)
        assert ReplaySession.model_validate(session).model_dump() == session
