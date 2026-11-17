"""Shared strategy names, defaults and public editor metadata."""
from copy import deepcopy

NAME_ALIASES = {"sma_cross": "dual_ma", "rsi_reversion": "rsi_reversal"}
PARAMETER_ALIASES = {"fast": "fast_period", "slow": "slow_period", "period": "window", "lookback": "window",
                     "oversold": "buy_threshold", "overbought": "sell_threshold"}
VOLUME_THRESHOLD_MIN = 0.01
VOLUME_THRESHOLD_MAX = 500
VOLATILITY_THRESHOLD_MIN = .001
VOLATILITY_MULTIPLIER_MIN = .05
MA_STRATEGIES = frozenset({"dual_ma", "dual_ma_volume", "dual_ma_volatility"})
DEFAULTS = {
    "dual_ma": {"fast_period": 5, "slow_period": 20},
    "dual_ma_volume": {"fast_period": 5, "slow_period": 20, "volume_window": 20, "volume_threshold": 1.2},
    "dual_ma_volatility": {"fast_period": 5, "slow_period": 20, "volatility_window": 20,
                           "volatility_threshold": .03, "high_volatility_multiplier": .5},
    "buy_and_hold": {},
    "bollinger_bands": {"window": 20, "std_dev": 2},
    "rsi_reversal": {"window": 14, "buy_threshold": 30, "sell_threshold": 70},
    "momentum": {"window": 20, "threshold": .02},
}


def canonical_name(name: str) -> str:
    return NAME_ALIASES.get(name, name)


def normalize_parameters(params: dict, *, canonical_wins=False) -> dict:
    """Preserve each existing caller's alias collision policy.

    Requests historically use the last supplied key; the engine prefers an
    explicitly supplied canonical key, regardless of input key order.
    """
    if canonical_wins:
        output = dict(params)
        for alias, key in PARAMETER_ALIASES.items():
            if alias in params and key not in output:
                output[key] = params[alias]
        return output
    return {PARAMETER_ALIASES.get(key, key): value for key, value in params.items()}


def strategy_defaults(name: str) -> dict:
    return deepcopy(DEFAULTS.get(canonical_name(name), {}))


def warmup_requirements(name: str, parameters: dict) -> tuple[int, int | None]:
    """Count rows needed for indicators at the final close before the run."""
    if name == "dual_ma_volume":
        # The signal close needs its own volume and a mean of prior eligible bars.
        volume_rows = int(parameters["volume_window"]) + 1
        return max(int(parameters["slow_period"]), volume_rows), volume_rows
    if name == "dual_ma_volatility":
        return max(int(parameters["slow_period"]), int(parameters["volatility_window"]) + 1), None
    if name in {"momentum", "rsi_reversal"}:
        return int(parameters["window"]) + 1, None
    if name == "bollinger_bands":
        return int(parameters["window"]), None
    return int(parameters.get("slow_period", 0)), None


def _parameter(name, key, label, minimum, maximum, step=1):
    return {"key": key, "label": label, "default": DEFAULTS[name][key], "min": minimum, "max": maximum, "step": step}


def strategy_catalog() -> list[dict]:
    """Return fresh UI metadata; API validation remains authoritative."""
    def p(name, key, label, minimum, maximum, step=1):
        return _parameter(name, key, label, minimum, maximum, step)
    return [
        {"name": "dual_ma", "label": "双均线趋势", "description": "短期均线高于长期均线时持有，反向退出。",
         "parameters": [p("dual_ma", "fast_period", "快线周期", 2, 500), p("dual_ma", "slow_period", "慢线周期", 3, 500)]},
        {"name": "dual_ma_volume", "label": "双均线放量", "description": "短期均线高于长期均线且成交量达到阈值时入场，反向退出。",
         "parameters": [p("dual_ma_volume", "fast_period", "快线周期", 2, 500), p("dual_ma_volume", "slow_period", "慢线周期", 3, 500),
                        p("dual_ma_volume", "volume_window", "成交量窗口", 2, 500),
                        p("dual_ma_volume", "volume_threshold", "成交量倍数阈值", VOLUME_THRESHOLD_MIN, VOLUME_THRESHOLD_MAX, .01)]},
        {"name": "dual_ma_volatility", "label": "双均线波动控制", "description": "双均线入场时用已观察的滚动波动率调整预算，保留原出场规则。",
         "parameters": [p("dual_ma_volatility", "fast_period", "快线周期", 2, 500), p("dual_ma_volatility", "slow_period", "慢线周期", 3, 500),
                        p("dual_ma_volatility", "volatility_window", "波动率窗口", 2, 500),
                        p("dual_ma_volatility", "volatility_threshold", "日波动率阈值（小数）", VOLATILITY_THRESHOLD_MIN, 1, .001),
                        p("dual_ma_volatility", "high_volatility_multiplier", "高波动入场预算倍率", VOLATILITY_MULTIPLIER_MIN, 1, .05)]},
        {"name": "buy_and_hold", "label": "预算内买入持有", "description": "首次观测收盘后，按配置仓位在后续可交易日开盘入场，持有至回测结束。",
         "parameters": []},
        {"name": "bollinger_bands", "label": "布林带回归", "description": "跌破下轨时买入，突破上轨时退出。",
         "parameters": [p("bollinger_bands", "window", "窗口周期", 2, 500), p("bollinger_bands", "std_dev", "标准差倍数", .1, 10, .1)]},
        {"name": "rsi_reversal", "label": "RSI 反转", "description": "超卖时买入，超买时退出。",
         "parameters": [p("rsi_reversal", "window", "RSI 周期", 2, 500), p("rsi_reversal", "buy_threshold", "超卖阈值", 1, 99),
                        p("rsi_reversal", "sell_threshold", "超买阈值", 1, 99)]},
        {"name": "momentum", "label": "动量跟随", "description": "区间收益突破阈值时持有，负向突破时退出。",
         "parameters": [p("momentum", "window", "观察周期", 2, 500), p("momentum", "threshold", "收益阈值（小数）", 0, .9, .01)]},
    ]
