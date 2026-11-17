from datetime import date, datetime, timedelta, timezone

from fastapi.testclient import TestClient
import pytest

from backend.main import create_app
from backend.services.daily_paper import advance_paper, start_paper


def observed_date(day):
    return datetime.fromisoformat(day + "T15:20:00+08:00")


def bundle(end="2024-02-19", *, next_session="2024-02-20"):
    days = [(date(2024, 1, 8) + timedelta(days=offset)).isoformat() for offset in range(37)
            if (date(2024, 1, 8) + timedelta(days=offset)).weekday() < 5]
    # Use a fixture calendar with a substantial closure and two sessions after it.
    days = [day for day in days if day <= "2024-02-07"] + ["2024-02-19", "2024-02-20"]
    days = [day for day in days if day <= end]
    source = {"name": "Fixed input", "url": "https://example.com/source", "acquired_at": end+"T15:05:00+08:00",
              "method": "Test price source and exchange calendar"}
    return {
        "symbol": "000338", "start": days[0], "end": end, "price_basis": "raw_unadjusted", "volume_unit": "shares",
        "price_source": source, "trading_evidence": {"suspension": source, "limits": source, "limits_kind": "published"},
        "calendar": {"source": source, "sessions": days, "next_session": next_session},
        "dividend_review": source, "dividend_review_through": end,
        "dividend_events": [{"record_date": "2024-02-19", "ex_date": "2024-02-20", "payment_date": "2024-02-20",
                              "cash_per_share": .2, "announced_date": "2024-02-01", "source_url": "https://example.com/notice"}],
        "rows": [{"date": day, "open": 10+index/10, "high": 10+index/10, "low": 10+index/10,
                  "close": 10+index/10, "volume": 50000, "is_suspended": False, "limit_down": 9, "limit_up": 15}
                 for index, day in enumerate(days)],
    }


def test_import_preserves_evidence_in_bridge_and_rejects_unsourced_controls(tmp_path):
    with TestClient(create_app(tmp_path, run_jobs=False)) as client:
        data = bundle()
        no_source = {**data, "trading_evidence": {}}
        response = client.post("/api/research/execution-history", json=no_source)
        assert response.status_code == 400
        response = client.post("/api/research/execution-history", json=data)
        assert response.status_code == 201, response.text
        saved = response.json()
        assert saved["execution_history"]["coverage"]["dividend_events"] == 1
        assert saved["execution_history"]["coverage"]["missing_sessions"] == []
        response = client.post("/api/bridge/backtests", json={"snapshot_ids": [saved["id"]], "config": {
            "source": "snapshot", "tickers": ["000338"], "start_date": "2024-02-01", "end_date": data["end"],
        }})
        assert response.status_code == 202, response.text
        manifest = response.json()["manifest"][0]
        assert manifest["origin"]["execution_history"]["dividend_events"][0]["source_url"] == "https://example.com/notice"
        assert "limit_up" in manifest["execution_fields"]


@pytest.mark.parametrize(("start", "end", "gap", "bounds", "missing", "warning"), [
    ("2024-01-08", "2024-02-19", False, {}, [], None),
    ("2024-01-08", "2024-02-20", False, {}, None, "calendar_unknown"),
    ("2024-01-05", "2024-02-19", False, {}, None, "calendar_unknown"),
    ("2024-01-08", "2024-02-19", True, {}, ["2024-02-19"], "missing_sessions"),
    ("2024-01-07", "2024-02-19", False, {"start_date": "2024-01-07", "end_date": "2024-02-19"}, [], None),
])
def test_backtest_preview_only_counts_gaps_for_a_covered_calendar(tmp_path, start, end, gap, bounds, missing, warning):
    data = bundle()
    data.update(start=start, end=end, dividend_events=[])
    data["calendar"].update(next_session=None, **bounds)
    if gap:
        data["rows"].pop()
    with TestClient(create_app(tmp_path, run_jobs=False)) as client:
        project = client.post("/api/projects", json={"name": "calendar", "symbols": ["000338"]}).json()
        uploaded = client.post("/api/research/execution-history", json=data)
        assert uploaded.status_code == 201, uploaded.text
        snapshot = uploaded.json()
        assert snapshot["execution_history"]["coverage"]["missing_sessions"] == missing
        response = client.post("/api/bridge/backtests/preview", json={
            "project_id": project["id"], "snapshot_ids": [snapshot["id"]],
            "config": {"source": "snapshot", "tickers": ["000338"], "start_date": start, "end_date": end,
                       "strategy": {"name": "buy_and_hold"}},
        })
        assert response.status_code == 200, response.text
        preview = response.json()
        inputs = preview["inputs"][0]
        assert inputs["calendar_has_sessions"] is (missing is not None)
        assert inputs["missing_session_count"] == (len(missing) if missing is not None else None)
        assert inputs["sample_missing_sessions"] == missing
        calendar_warnings = [w["code"] for w in preview["warnings"]
                             if w["code"] in {"missing_sessions", "calendar_unknown"}]
        assert calendar_warnings == ([warning] if warning else [])


@pytest.mark.parametrize("bounds", [
    {"start_date": "2024-01-08"},
    {"start_date": "2024-01-09", "end_date": "2024-02-19"},
    {"start_date": "2024-01-07", "end_date": "2024-02-19"},
])
def test_execution_history_rejects_inconsistent_calendar_bounds(tmp_path, bounds):
    data = bundle()
    data["calendar"].update(bounds)
    with TestClient(create_app(tmp_path, run_jobs=False)) as client:
        assert client.post("/api/research/execution-history", json=data).status_code == 400


@pytest.mark.parametrize("near_limit", [False, True])
def test_paper_keeps_seed_and_advances_exactly_once_with_same_history(tmp_path, near_limit):
    with TestClient(create_app(tmp_path, run_jobs=False)) as client:
        project = client.post("/api/projects", json={"name": "纸面账户", "symbols": ["000338"]}).json()
        def save(data):
            response = client.post("/api/research/execution-history", json=data)
            assert response.status_code == 201, response.text
            return client.get("/api/research/snapshot/"+response.json()["id"]).json()
        first = save(bundle())
        with pytest.raises(ValueError, match="已经开盘"):
            start_paper(tmp_path, project, first, date(2024, 2, 19), observed_at=observed_date("2024-02-20"))
        seed = start_paper(tmp_path, project, first, date(2024, 2, 19), observed_at=observed_date("2024-02-19"))
        assert seed["plan"]["action"] == "buy"
        assert seed["plan"]["next_session"] == "2024-02-20"
        assert seed["receipt"] is None
        data = bundle("2024-02-20", next_session="2024-02-21")
        if near_limit:
            data["rows"][-1].update(open=29.99, high=30, low=29.9, close=29.95, limit_up=30, limit_down=25)
        current = save(data)
        cutoff = observed_date("2024-02-20")
        prior = lambda _sid: first
        revised = {**current, "rows": [{**current["rows"][0], "close": 10.01}, *current["rows"][1:]]}
        with pytest.raises(ValueError, match="历史输入不能改变"):
            advance_paper(tmp_path, project, seed["id"], revised, cutoff.date(), prior, observed_at=cutoff)
        record = advance_paper(tmp_path, project, seed["id"], current, cutoff.date(), prior, observed_at=cutoff)
        if near_limit:
            assert record["receipt"]["state"]["cash"] == seed["account"]["initial_cash"]
            assert record["receipt"]["trades"] == []
            blocked, = record["receipt"]["blocked"]
            assert blocked["status"] == "deferred"
            assert record["plan"]["pending_signal_date"] == seed["as_of"]
        else:
            assert record["receipt"]["state"]["cash"] < seed["account"]["initial_cash"]
            buy, = record["receipt"]["trades"]
            assert buy["signal_date"] == seed["as_of"] and buy["date"] == "2024-02-20"
        assert record["receipt"]["state"].get("dividend_cash_paid", 0) == 0
        assert advance_paper(tmp_path, project, seed["id"], current, cutoff.date(), prior, observed_at=cutoff) == record
        saved = client.get(f"/api/projects/{project['id']}/daily-paper").json()["records"]
        assert {row["kind"] for row in saved} == {"seed", "session"}
