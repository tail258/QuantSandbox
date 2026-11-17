import copy
import hashlib

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from backend.api.schemas import RunConfig
from backend.core.data_format import DataUnavailable, canonical_json, validate_frame
from backend.core.engine import run_backtest
from backend.main import create_app
from backend.services.runner import execute_job

TICKER = "000338"
JAN_2, JAN_3, JAN_4, JAN_5, JAN_8 = (
    "2024-01-02", "2024-01-03", "2024-01-04", "2024-01-05", "2024-01-08",
)


def bars():
    return pd.DataFrame({
        "date": [JAN_2, JAN_3, JAN_4, JAN_5, JAN_8],
        "open": [10, 10, 9, 9, 9],
        "high": [10, 10, 9, 9, 9],
        "low": [10, 10, 9, 9, 9],
        "close": [10, 10, 9, 9, 9],
        "volume": 10_000,
        "cash_dividend_per_share": [None, 1.0, None, None, None],
        "dividend_ex_date": [None, JAN_4, None, None, None],
        "dividend_payment_date": [None, JAN_5, None, None, None],
    })


def config():
    return RunConfig.model_validate({
        "source": "snapshot", "tickers": [TICKER], "start_date": JAN_3, "end_date": JAN_8,
        "strategy": {"name": "buy_and_hold"},
        "account": {"initial_cash": 10_000, "commission_rate": 0, "tax_rate": 0,
                    "min_commission": 0, "slippage_bps": 0, "position_size": 1},
    }).model_dump(mode="json")


@pytest.mark.parametrize("sell_after_record", [True, False])
def test_entitlement_uses_record_close_and_cash_arrives_after_open(sell_after_record):
    frame = bars()
    # An order decided at the record-date close can sell at ex-date open.
    frame["trade_signal"] = [1, -1 if sell_after_record else 0, 0, 0, 0]
    result = run_backtest({TICKER: frame}, {**config(), "_precomputed_signals": True})
    record, ex, payment, final = result["series"]
    assert record["positions"][TICKER]["shares"] == 1_000
    assert record["dividend_receivables"] == record["dividend_cash_paid"] == 0
    assert ex["positions"][TICKER]["shares"] == (0 if sell_after_record else 1_000)
    assert ex["dividend_receivables"] == 1_000
    assert ex["dividend_cash_paid"] == 0
    assert ex["cash"] == (9_000 if sell_after_record else 0)
    assert payment["dividend_cash_paid"] == 1_000
    assert payment["dividend_receivables"] == 0
    assert payment["cash"] == (10_000 if sell_after_record else 1_000)
    assert final["dividend_cash_paid"] == 0
    assert all(row["equity"] == 10_000 for row in result["series"])
    assert result["dividends"] == [{
        "ticker": TICKER, "record_date": JAN_3, "ex_date": JAN_4, "payment_date": JAN_5,
        "shares": 1_000, "cash_per_share": 1.0, "gross_amount": 1_000.0,
        "recognized_date": JAN_4, "credited_date": JAN_5,
    }]
    assert result["metrics"]["dividend_cash_paid"] == 1_000


def test_ex_date_purchase_cannot_claim_dividend():
    frame = bars()
    frame["trade_signal"] = [0, 1, 0, 0, 0]
    result = run_backtest({TICKER: frame}, {**config(), "_precomputed_signals": True})
    assert result["series"][1]["positions"][TICKER]["shares"] > 0
    assert result["dividends"] == []
    assert result["metrics"]["dividend_cash_paid"] == 0


def test_unobserved_payment_waits_for_next_observed_close_and_no_early_equity_lookup():
    frame = bars()
    frame.loc[1, "dividend_payment_date"] = "2024-01-06"
    cfg = config()
    prefix = run_backtest({TICKER: frame}, {**cfg, "end_date": JAN_5})
    assert prefix["metrics"]["dividend_receivables"] == 1_000
    assert prefix["metrics"]["dividend_cash_paid"] == 0
    assert prefix["dividends"][0]["credited_date"] is None
    full = run_backtest({TICKER: frame}, cfg)
    assert full["dividends"][0]["credited_date"] == JAN_8
    assert prefix["series"] == full["series"][:-1]
    assert full["checkpoints"][-1]["dividend_cash_paid"] == 1_000


def test_due_dividend_is_not_spendable_at_payment_open():
    frame = bars()
    frame["trade_signal"] = [1, -1, 0, 0, 0]
    second = frame[["date", "open", "high", "low", "close", "volume"]].copy()
    second[["open", "high", "low", "close"]] = 10.0
    second["trade_signal"] = [0, 0, 1, 1, 0]
    result = run_backtest({TICKER: frame, "000962": second}, {
        **config(), "tickers": [TICKER, "000962"], "_precomputed_signals": True,
    })
    second_buy, = (trade for trade in result["trades"] if trade["ticker"] == "000962")
    assert (second_buy["date"], second_buy["shares"]) == (JAN_5, 900)
    assert result["series"][2]["cash"] == 1_000


@pytest.mark.parametrize(("column", "value"), [
    ("cash_dividend_per_share", False),
    ("cash_dividend_per_share", 0),
    ("cash_dividend_per_share", float("inf")),
    ("dividend_ex_date", None),
    ("dividend_ex_date", "20240104"),
    ("dividend_ex_date", JAN_3),
    ("dividend_payment_date", JAN_3),
])
def test_invalid_dividend_fields_fail_validation(column, value):
    frame = bars()
    frame[column] = frame[column].astype(object)
    frame.loc[1, column] = value
    with pytest.raises(DataUnavailable):
        validate_frame(frame)


def test_dividend_snapshot_is_hashed_replayed_and_masked_at_a_blind_cutoff(tmp_path):
    def complete(client, run):
        store = client.app.state.store
        store.patch_run(run["id"], status="running")
        execute_job(str(store.root), run["id"])
        completed = client.get(f'/api/runs/{run["id"]}').json()
        assert completed["status"] == "completed", completed["error"]
        return completed

    with TestClient(create_app(tmp_path, run_jobs=False)) as client:
        center = client.app.state.center
        manifest = center.snapshot(TICKER, bars(), "snapshot")
        assert manifest["data_schema"] == "market-daily-v3"
        assert manifest["dividend_event_count"] == 1
        run = complete(client, client.app.state.research.schedule(config(), manifest=[manifest]))
        evidence = client.get(f'/api/runs/{run["id"]}/export').text
        response = client.post("/api/import", content=evidence, headers={"Content-Type": "application/json"})
        assert response.status_code == 202, response.text
        replay = complete(client, response.json())
        assert replay["result"]["replay_verification"]["matched"]
        assert "dividends" in replay["result"]["replay_verification"]["compared_fields"]
        assert replay["result"]["dividends"] == run["result"]["dividends"]
        assert replay["manifest"][0]["sha256"] == manifest["sha256"]
        session = client.post(f'/api/runs/{run["id"]}/sessions', json={"cursor": 1}).json()
        assert session["result"]["dividends"][0]["recognized_date"] == JAN_4
        assert session["result"]["dividends"][0]["credited_date"] is None
        assert session["result"]["metrics"]["dividend_cash_paid"] == 0
        assert session["result"]["metrics"]["dividend_receivables"] == 1_000
        package = client.get(f'/api/runs/{run["id"]}/export').json()
        changed = copy.deepcopy(package)
        changed["datasets"][0]["rows"][1]["dividend_payment_date"] = JAN_8
        changed["sha256"] = hashlib.sha256(canonical_json({k: v for k, v in changed.items() if k != "sha256"}).encode()).hexdigest()
        assert client.post("/api/import", json=changed).status_code == 422
