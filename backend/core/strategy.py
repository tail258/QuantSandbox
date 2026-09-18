"""Causal daily-bar strategies. Indicators only use data known at that close."""
from __future__ import annotations

import math
import pandas as pd


class StrategyFactory:
    NAMES = ("dual_ma", "bollinger_bands", "rsi_reversal", "momentum", "sma_cross", "rsi_reversion")

    @staticmethod
    def generate_signals(df: pd.DataFrame, strategy_name: str, params: dict | None = None) -> pd.DataFrame:
        params = params or {}
        if strategy_name not in StrategyFactory.NAMES:
            raise ValueError(f"未知策略：{strategy_name}")
        strategy_name = {"sma_cross": "dual_ma", "rsi_reversion": "rsi_reversal"}.get(strategy_name, strategy_name)
        params = dict(params)
        aliases = {"fast": "fast_period", "slow": "slow_period", "period": "window", "lookback": "window",
                   "oversold": "buy_threshold", "overbought": "sell_threshold"}
        for alias, canonical in aliases.items():
            if alias in params and canonical not in params:
                params[canonical] = params[alias]
        out = df.copy()
        out["trade_signal"] = 0
        return getattr(StrategyFactory, f"_{strategy_name}")(out, params)

    @staticmethod
    def _period(params, key, default):
        value = params.get(key, default)
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or int(value) != value or not 1 <= value <= 504:
            raise ValueError(f"{key} 必须为 1–504 之间的整数")
        return int(value)

    @staticmethod
    def _dual_ma(df, params):
        fast = StrategyFactory._period(params, "fast_period", 5)
        slow = StrategyFactory._period(params, "slow_period", 20)
        if fast >= slow:
            raise ValueError("fast_period 必须小于 slow_period")
        df["fast_ma"] = df["close"].rolling(fast).mean()
        df["slow_ma"] = df["close"].rolling(slow).mean()
        ready = df["slow_ma"].notna()
        df.loc[ready & (df.fast_ma > df.slow_ma), "trade_signal"] = 1
        df.loc[ready & (df.fast_ma <= df.slow_ma), "trade_signal"] = -1
        return df

    @staticmethod
    def _bollinger_bands(df, params):
        window = StrategyFactory._period(params, "window", 20)
        deviation = float(params.get("std_dev", 2.0))
        if not math.isfinite(deviation) or not 0 < deviation <= 10:
            raise ValueError("std_dev 必须在 (0, 10] 内")
        df["middle_band"] = df.close.rolling(window).mean()
        std = df.close.rolling(window).std(ddof=0)
        df["upper_band"] = df.middle_band + deviation * std
        df["lower_band"] = df.middle_band - deviation * std
        df.loc[df.close < df.lower_band, "trade_signal"] = 1
        df.loc[df.close > df.upper_band, "trade_signal"] = -1
        return df

    @staticmethod
    def _rsi_reversal(df, params):
        window = StrategyFactory._period(params, "window", 14)
        low = float(params.get("buy_threshold", 30))
        high = float(params.get("sell_threshold", 70))
        if not 0 <= low < high <= 100:
            raise ValueError("RSI 阈值需满足 0 ≤ buy_threshold < sell_threshold ≤ 100")
        delta = df.close.diff()
        gain = delta.clip(lower=0).rolling(window).mean()
        loss = (-delta.clip(upper=0)).rolling(window).mean()
        df["rsi"] = 100 - 100 / (1 + gain / loss.where(loss != 0))
        df.loc[(loss == 0) & (gain > 0), "rsi"] = 100.0
        df.loc[(loss == 0) & (gain == 0), "rsi"] = 50.0
        df.loc[df.rsi < low, "trade_signal"] = 1
        df.loc[df.rsi > high, "trade_signal"] = -1
        return df

    @staticmethod
    def _momentum(df, params):
        window = StrategyFactory._period(params, "window", 20)
        threshold = float(params.get("threshold", 0.02))
        if not math.isfinite(threshold) or not 0 <= threshold < 1:
            raise ValueError("momentum threshold 必须在 [0, 1) 内（小数收益率）")
        df["momentum"] = df.close.pct_change(window, fill_method=None)
        df.loc[df.momentum > threshold, "trade_signal"] = 1
        df.loc[df.momentum < -threshold, "trade_signal"] = -1
        return df
