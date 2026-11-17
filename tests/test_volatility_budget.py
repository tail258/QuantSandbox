import pandas as pd
import pytest

from backend.api.schemas import StrategyConfig
from backend.core.engine import run_backtest
from backend.core.strategy import StrategyFactory


def volatile_bars():
    closes = [10, 10, 13, 13, 13, 13, 13, 9, 9]
    return pd.DataFrame({
        "date": pd.date_range("2024-01-01", periods=len(closes)),
        "open": closes, "high": closes, "low": closes, "close": closes,
        "volume": [1_000] * len(closes),
        "is_suspended": [False, False, False, True, True, False, False, False, False],
    })


def test_volatility_is_causal_and_leaves_exit_unchanged():
    frame = volatile_bars()
    parameters = {"fast_period": 2, "slow_period": 3, "volatility_window": 3}
    signals = StrategyFactory.generate_signals(frame, "dual_ma_volatility", parameters)
    prefix = StrategyFactory.generate_signals(frame.iloc[:4], "dual_ma_volatility", parameters)
    pd.testing.assert_frame_equal(signals.iloc[:4], prefix)
    assert pd.isna(signals.loc[2, "realized_volatility"])
    assert signals.loc[2, "trade_signal"] == 0
    assert signals.loc[3, "trade_signal"] == 1
    assert signals.loc[3, "realized_volatility"] == pytest.approx(.3 / (3 ** .5))
    assert signals.loc[3, "entry_size_multiplier"] == .5
    assert signals.loc[6, "entry_size_multiplier"] == 1
    plain = StrategyFactory.generate_signals(frame, "dual_ma", parameters)
    assert signals.trade_signal.eq(-1).tolist() == plain.trade_signal.eq(-1).tolist()


def test_volatility_budget_is_frozen_through_suspension_and_next_open():
    frame = volatile_bars()
    # Signal on January 3. Two blocked bars let the rolling volatility and position
    # signal change, but cannot move the queued order's target fraction.
    strategy = StrategyConfig.model_validate({"name": "dual_ma_volatility", "parameters": {
        "fast_period": 2, "slow_period": 3, "volatility_window": 2,
    }}).model_dump()
    result = run_backtest({"000962": frame}, {
        "tickers": ["000962"], "start_date": "2024-01-03", "end_date": "2024-01-09",
        "account": {"initial_cash": 100_000, "position_size": .3}, "strategy": strategy,
    })
    buy, sell = result["trades"]
    assert (buy["signal_date"], buy["date"], buy["action"]) == ("2024-01-03", "2024-01-06", "buy")
    assert buy["evidence"]["indicators"]["entry_size_multiplier"] == .5
    assert buy["evidence"]["target_fraction"] == .15
    assert 0 < buy["value"] + buy["fee"] <= 15_000
    assert result["bars"]["000962"][3]["entry_size_multiplier"] == 1
    assert [d["date"] for d in result["decisions"] if d["status"] == "deferred"] == ["2024-01-04", "2024-01-05"]
    assert sell["action"] == "sell" and sell["shares"] == buy["shares"]
