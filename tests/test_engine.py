"""Small hand-auditable invariants for accounting, causality, and experiments."""
from copy import deepcopy
import json

import numpy as np
import pandas as pd
import pytest

from backend.core.engine import BacktestEngine, calculate_metrics, run_backtest
from backend.core.strategy import StrategyFactory
from backend.research import run_stress_suite, run_walk_forward


def prices(closes, opens=None, first="2024-01-01"):
    closes = np.array(closes, dtype=float)
    opens = np.array(opens if opens is not None else closes, dtype=float)
    return pd.DataFrame({"date": pd.bdate_range(first, periods=len(closes)), "open": opens,
                         "high": np.maximum(opens, closes), "low": np.minimum(opens, closes),
                         "close": closes, "volume": np.full(len(closes), 100000)})


def config(frame, **account):
    return {"tickers": ["AAA"], "start_date": str(frame.date.iloc[0].date()), "end_date": str(frame.date.iloc[-1].date()),
            "strategy": {"name": "dual_ma", "parameters": {"fast_period": 1, "slow_period": 2}},
            "account": {"initial_cash": 100000, "position_size": 1, "commission_rate": 0,
                        "min_commission": 0, "tax_rate": 0, "slippage_bps": 0, **account}}


def test_signal_only_executes_after_its_close():
    frame = prices([9, 10, 11, 10, 9], [9, 10, 10, 10, 10])
    out = run_backtest({"AAA": frame}, config(frame))
    assert out["trades"][0]["date"] == "2024-01-03"
    assert out["trades"][0]["signal_date"] == "2024-01-02"
    assert all(t["date"] > t["signal_date"] for t in out["trades"])


def test_future_changes_cannot_change_prefix():
    frame = prices([9, 10, 11, 10, 9, 8, 9, 10, 11, 12])
    changed = frame.copy()
    changed.loc[7:, ["open", "high", "low", "close"]] *= 3
    base = run_backtest({"AAA": frame}, config(frame))
    alternate = run_backtest({"AAA": changed}, config(frame))
    cutoff = str(frame.date.iloc[6].date())
    for key in ("trades", "decisions", "series", "checkpoints"):
        assert [r for r in base[key] if r["date"] <= cutoff] == [r for r in alternate[key] if r["date"] <= cutoff]


def test_first_day_drawdown_includes_initial_cash_and_warmup_signal():
    frame = prices([9, 10, 9], [9, 10, 10])
    cfg = config(frame)
    cfg["start_date"] = "2024-01-03"
    out = run_backtest({"AAA": frame}, cfg)
    assert len(out["series"]) == 1
    assert out["metrics"]["final_equity"] == 90000
    assert out["metrics"]["max_drawdown"] == -10
    assert out["series"][0]["daily_return"] == -10


def test_buy_commission_included_in_closed_trade_win_rate():
    frame = prices([9, 10, 11, 10, 9], [9, 10, 10, 10, 10])
    out = run_backtest({"AAA": frame}, config(frame, commission_rate=0.00025, tax_rate=0.0005, min_commission=5))
    assert out["metrics"]["closed_trade_count"] == 1
    assert out["metrics"]["win_rate"] == 0
    assert out["trades"][-1]["round_trip_pnl"] < 0
    assert out["metrics"]["final_equity"] == pytest.approx(100000 - out["metrics"]["total_fees"])


def test_cash_conservation_with_minimum_fees_and_slippage():
    frame = prices([9, 10, 11, 10, 9], [9, 10, 10, 10, 10])
    out = run_backtest({"AAA": frame}, config(frame, initial_cash=2000, min_commission=5, slippage_bps=10))
    running = 2000
    for t in out["trades"]:
        running += (-t["value"] if t["action"] == "buy" else t["value"]) - t["fee"]
        assert t["evidence"]["cash_after"] == pytest.approx(running, abs=1e-5)
    assert out["series"][-1]["cash"] == pytest.approx(running, abs=1e-5)
    for row in out["series"]:
        assert row["equity"] == pytest.approx(row["cash"] + sum(p["market_value"] for p in row["positions"].values()), abs=1e-5)


def test_unchanged_branch_has_identical_results():
    frame = prices([9, 10, 11, 12, 13, 12, 11])
    cfg = config(frame)
    base = run_backtest({"AAA": frame}, cfg)
    assert run_backtest({"AAA": frame}, cfg, {"at_date": "2024-01-04"}) == base


def test_branch_preserves_prefix_and_rebalances_after_close():
    frame = prices([9, 10, 11, 12, 13, 14, 15])
    cfg = config(frame)
    base = run_backtest({"AAA": frame}, cfg)
    branch = run_backtest({"AAA": frame}, cfg, {"at_date": "2024-01-04", "position_size": 0.2})
    assert branch["series"][:4] == base["series"][:4]
    assert [t for t in base["trades"] if t["date"] <= "2024-01-04"] == [t for t in branch["trades"] if t["date"] <= "2024-01-04"]
    assert branch["trades"][-1]["date"] == "2024-01-05"
    assert branch["trades"][-1]["action"] == "sell"
    assert branch["series"][-1]["positions"]["AAA"]["shares"] < base["series"][-1]["positions"]["AAA"]["shares"]


def test_multiple_stocks_share_cash_and_cannot_overdraw():
    frame = prices([9, 10, 11, 12, 13, 14])
    cfg = config(frame, min_commission=5)
    cfg["tickers"] = ["CCC", "BBB", "AAA"]
    out = run_backtest({t: frame for t in cfg["tickers"]}, cfg)
    assert all(s["cash"] >= -1e-7 for s in out["series"])
    assert out["trades"][0]["ticker"] == "AAA"
    assert sum(t["value"] + t["fee"] for t in out["trades"] if t["action"] == "buy") <= 100000


def test_suspended_execution_is_deferred():
    frame = prices([9, 10, 11, 12, 13])
    frame.loc[2, "volume"] = 0
    out = run_backtest({"AAA": frame}, config(frame))
    assert out["trades"][0]["date"] == "2024-01-04"
    assert any(d["status"] == "deferred" for d in out["decisions"])


def test_final_position_not_forcibly_liquidated_and_result_serializes():
    frame = prices([9, 10, 11, 12, 13])
    out = run_backtest({"AAA": frame}, config(frame))
    assert out["metrics"]["open_position_count"] == 1
    assert out["metrics"]["closed_trade_count"] == 0
    assert out["metrics"]["pnl_ratio"] is None
    json.dumps(out, allow_nan=False)


def test_legacy_engine_preserves_supplied_signals_with_next_bar_execution():
    frame = prices([10, 10, 10, 10])
    frame["trade_signal"] = [1, 0, -1, 0]
    out = BacktestEngine(slippage_bps=0).run(frame, "AAA")
    assert len(out["logs"]) == 2
    assert out["logs"][0]["timestamp"] == "2024-01-02"
    assert out["metadata"]["win_rate"] == 0


def test_aliases_and_flat_rsi_are_well_defined():
    frame = prices([10] * 20)
    alias = StrategyFactory.generate_signals(frame, "rsi_reversion", {"period": 7, "oversold": 30, "overbought": 70})
    assert alias.rsi.iloc[-1] == 50
    assert (alias.trade_signal == 0).all()


def test_stress_scenarios_are_computed_from_engine():
    frame = prices([9, 10, 11, 10, 9, 10, 11, 10, 9])
    result = run_stress_suite({"AAA": frame}, config(frame, min_commission=5))
    assert len(result["scenarios"]) == 5
    assert result["scenarios"][0]["metrics"]["total_fees"] >= result["baseline"]["total_fees"]
    json.dumps(result, allow_nan=False)


def test_walk_forward_selection_is_causal_and_oos_account_is_continuous():
    frame = prices(10 + np.sin(np.arange(65) / 3) + np.arange(65) * 0.02)
    cfg = config(frame, min_commission=5, position_size=0.5)
    candidates = [{"name": "dual_ma", "parameters": {"fast_period": 2, "slow_period": 5}},
                  {"name": "dual_ma", "parameters": {"fast_period": 3, "slow_period": 8}}]
    base = run_walk_forward({"AAA": frame}, cfg, training_days=20, test_days=10, candidates=candidates)
    assert len(base["folds"]) == 5
    assert base["series"][0]["date"] == str(frame.date.iloc[20].date())
    assert len(base["series"]) == 45
    # First test changes cannot influence first training selection.
    changed = frame.copy()
    changed.loc[20:, ["open", "high", "low", "close"]] *= 2
    alt = run_walk_forward({"AAA": changed}, cfg, training_days=20, test_days=10, candidates=candidates)
    assert base["folds"][0]["trials"] == alt["folds"][0]["trials"]
    direct = run_backtest({"AAA": frame}, base["config"])
    assert base["series"] == direct["series"]
    assert base["trades"] == direct["trades"]
    json.dumps(base, allow_nan=False)


def test_visible_prefix_metrics_do_not_use_future_trades():
    series = [{"date": "2024-01-01", "equity": 90000, "cash": 90000, "positions": {}}]
    assert calculate_metrics(series, [], 100000)["max_drawdown"] == -10


def test_extreme_one_day_return_cannot_overflow_annualization():
    metric = calculate_metrics([{"date": "2024-01-01", "equity": 1e12, "cash": 1e12}], [], 100000)
    assert metric["annualized_return"] is None
    json.dumps(metric, allow_nan=False)


def test_nested_branch_inherits_earlier_policy_and_preserves_parent_prefix():
    frame = prices([9, 10, 11, 12, 13, 14, 15, 16, 17, 18])
    cfg = config(frame)
    first = {"at_date": "2024-01-04", "account": {"position_size": 0.5, "min_commission": 8}}
    parent = run_backtest({"AAA": frame}, cfg, first)
    child = run_backtest({"AAA": frame}, cfg, {"at_date": "2024-01-09", "position_size": 0.1, "history": [first]})
    assert [s for s in parent["series"] if s["date"] <= "2024-01-09"] == [s for s in child["series"] if s["date"] <= "2024-01-09"]
    assert [t for t in parent["trades"] if t["date"] <= "2024-01-09"] == [t for t in child["trades"] if t["date"] <= "2024-01-09"]
    assert child["trades"][-1]["evidence"]["min_commission"] == 8
    unchanged = run_backtest({"AAA": frame}, cfg, {"at_date": "2024-01-09", "history": [first]})
    assert unchanged == parent


def test_walk_forward_fold_benchmark_uses_local_window_return():
    frame = prices(10 + np.arange(45) * 0.5)
    result = run_walk_forward({"AAA": frame}, config(frame, position_size=0.5), training_days=20, test_days=10)
    fold = result["folds"][1]
    previous = next(s for s in result["series"] if s["date"] == result["folds"][0]["test_end"])
    end = next(s for s in result["series"] if s["date"] == fold["test_end"])
    expected = (end["benchmark"] / previous["benchmark"] - 1) * 100
    assert fold["test_metrics"]["benchmark_return"] == pytest.approx(expected, abs=1e-4)


def test_same_close_nested_edits_combine_into_one_effective_policy():
    frame = prices([9, 10, 11, 12, 13, 14, 15, 16, 17, 18])
    cfg = config(frame)
    first = {"at_date": "2024-01-04", "position_size": .5}
    second = {"at_date": "2024-01-04", "account": {"min_commission": 9}}
    nested = run_backtest({"AAA": frame}, cfg, {**second, "history": [first]})
    combined = run_backtest({"AAA": frame}, cfg, {"at_date": "2024-01-04", "account": {"position_size": .5, "min_commission": 9}})
    assert nested == combined
    # Reverting a same-close policy before it could trade must restore baseline.
    reverted = run_backtest({"AAA": frame}, cfg, {"at_date": "2024-01-04", "position_size": 1, "history": [first]})
    assert reverted == run_backtest({"AAA": frame}, cfg)


@pytest.mark.parametrize("bad", [float("nan"), -0.1, 1.1])
def test_invalid_account_values_are_rejected(bad):
    frame = prices([9, 10, 11])
    with pytest.raises(ValueError):
        run_backtest({"AAA": frame}, config(frame, position_size=bad))
