"""Causal daily-bar strategies. Indicators only use data known at that close."""
from __future__ import annotations

import math
import pandas as pd
from backend.core.strategy_catalog import (DEFAULTS, NAME_ALIASES, VOLATILITY_MULTIPLIER_MIN, VOLATILITY_THRESHOLD_MIN,
                                           VOLUME_THRESHOLD_MAX, VOLUME_THRESHOLD_MIN,
                                           canonical_name, normalize_parameters, strategy_defaults)


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
    def _dual_ma_volume(df, params):
        defaults = DEFAULTS["dual_ma_volume"]
        window = StrategyFactory._period(params, "volume_window", defaults["volume_window"])
        threshold = float(params.get("volume_threshold", defaults["volume_threshold"]))
        if not VOLUME_THRESHOLD_MIN <= threshold <= VOLUME_THRESHOLD_MAX:
            raise ValueError(f"成交量倍数阈值必须在 [{VOLUME_THRESHOLD_MIN}, {VOLUME_THRESHOLD_MAX}] 内")

        df = StrategyFactory._dual_ma(df, params)
        volume = pd.to_numeric(df.get("volume", pd.Series(index=df.index, dtype=float)), errors="coerce").astype(float)
        eligible = volume.gt(0) & volume.lt(math.inf)
        if "is_suspended" in df:
            eligible &= ~df["is_suspended"].eq(True).fillna(False)
        observed = volume[eligible]
        # Roll over observed volume bars only. Shift before rolling to exclude the signal bar.
        mean = observed.shift().rolling(window).mean()
        mean = mean.where(mean.gt(0) & mean.lt(math.inf))
        ratio = observed / mean
        df["volume_ma"] = mean
        df["volume_ratio"] = ratio.where(ratio.lt(math.inf))
        df.loc[df.trade_signal.gt(0) & ~df.volume_ratio.ge(threshold), "trade_signal"] = 0
        return df

    @staticmethod
    def _dual_ma_volatility(df, params):
        defaults = DEFAULTS["dual_ma_volatility"]
        window = StrategyFactory._period(params, "volatility_window", defaults["volatility_window"])
        threshold = float(params["volatility_threshold"])
        multiplier = float(params["high_volatility_multiplier"])
        if not VOLATILITY_THRESHOLD_MIN <= threshold <= 1:
            raise ValueError(f"日波动率阈值必须在 [{VOLATILITY_THRESHOLD_MIN}, 1] 内")
        if not VOLATILITY_MULTIPLIER_MIN <= multiplier <= 1:
            raise ValueError(f"高波动入场预算倍率必须在 [{VOLATILITY_MULTIPLIER_MIN}, 1] 内")

        df = StrategyFactory._dual_ma(df, params)
        volatility = df.close.pct_change(fill_method=None).rolling(window).std(ddof=1)
        ready = volatility.notna()
        df["realized_volatility"] = volatility
        df["entry_size_multiplier"] = pd.Series(1.0, index=df.index).mask(volatility.gt(threshold), multiplier).where(ready)
        df.loc[df.trade_signal.gt(0) & ~ready, "trade_signal"] = 0
        return df

    @staticmethod
    def _buy_and_hold(df, params):
        df["trade_signal"] = 1
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
