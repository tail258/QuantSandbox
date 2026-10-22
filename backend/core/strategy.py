"""Causal daily-bar strategies. Indicators only use data known at that close."""
from __future__ import annotations

import math
import pandas as pd
from backend.core.strategy_catalog import DEFAULTS, NAME_ALIASES, canonical_name, normalize_parameters, strategy_defaults


class StrategyFactory:
    NAMES = (*DEFAULTS, *NAME_ALIASES)

    @staticmethod
    def generate_signals(df: pd.DataFrame, strategy_name: str, params: dict | None = None) -> pd.DataFrame:
        params = params or {}
        if strategy_name not in StrategyFactory.NAMES:
            raise ValueError(f"未知策略：{strategy_name}")
        strategy_name = canonical_name(strategy_name)
        params = {**strategy_defaults(strategy_name), **normalize_parameters(params, canonical_wins=True)}
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
        fast = StrategyFactory._period(params, "fast_period", DEFAULTS["dual_ma"]["fast_period"])
        slow = StrategyFactory._period(params, "slow_period", DEFAULTS["dual_ma"]["slow_period"])
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
        window = StrategyFactory._period(params, "window", DEFAULTS["bollinger_bands"]["window"])
        deviation = float(params.get("std_dev", DEFAULTS["bollinger_bands"]["std_dev"]))
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
        window = StrategyFactory._period(params, "window", DEFAULTS["rsi_reversal"]["window"])
        low = float(params.get("buy_threshold", DEFAULTS["rsi_reversal"]["buy_threshold"]))
        high = float(params.get("sell_threshold", DEFAULTS["rsi_reversal"]["sell_threshold"]))
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
        window = StrategyFactory._period(params, "window", DEFAULTS["momentum"]["window"])
        threshold = float(params.get("threshold", DEFAULTS["momentum"]["threshold"]))
        if not math.isfinite(threshold) or not 0 <= threshold < 1:
            raise ValueError("momentum threshold 必须在 [0, 1) 内（小数收益率）")
        df["momentum"] = df.close.pct_change(window, fill_method=None)
        df.loc[df.momentum > threshold, "trade_signal"] = 1
        df.loc[df.momentum < -threshold, "trade_signal"] = -1
        return df
