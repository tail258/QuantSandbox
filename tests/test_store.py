import json

import pytest

from backend.services.store import Store


@pytest.mark.parametrize("result", [None, {}, {"baseline": {"return": 1.2345678901234567}},
    {"metrics": None, "baseline": {"return": 9}},
    {"metrics": {}, "baseline": {"return": 9}},
    {"metrics": {"precise": 0.12345678901234566, "integer": 9007199254740993},
     "bars": {"000858": [{"date": "2024-01-01", "close": 1}] * 10000}}])
def test_list_summary_matches_previous_contract_without_decoding_large_result(tmp_path, monkeypatch, result):
    store = Store(tmp_path)
    run = store.create_run({"name": "example", "source": "demo"}, experiment={"hidden": True}, expected_result={"hidden": True})
    store.patch_run(run["id"], result=result)
    expected = store.get_run(run["id"])
    expected.pop("result")
    expected.pop("experiment")
    expected.pop("expected_result")
    expected["metrics"] = (result or {}).get("metrics", (result or {}).get("baseline"))
    original = json.loads
    def small_only(value, *args, **kwargs):
        assert len(value) < 1000, "list_runs decoded a full research result"
        return original(value, *args, **kwargs)
    monkeypatch.setattr("backend.services.store.json.loads", small_only)
    assert store.list_runs() == [expected]
    assert store.list_runs(limit=0) == []
