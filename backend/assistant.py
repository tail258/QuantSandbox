"""Deterministic, offline research commands; never execute generated code."""

from __future__ import annotations

from copy import deepcopy
import re


DEFAULT_CONFIG = {
    "name": "研究指令实验",
    "tickers": ["000858", "601318", "600036"],
    "start_date": "2024-01-01",
    "end_date": "2025-12-31",
    "source": "demo",
    "strategy": {"name": "dual_ma", "parameters": {"fast_period": 5, "slow_period": 20}},
    "account": {
        "initial_cash": 100000,
        "commission_rate": 0.00025,
        "tax_rate": 0.0005,
        "min_commission": 5,
        "slippage_bps": 5,
        "position_size": 0.3,
    },
}


def plan_research(prompt: str, base_config: dict | None = None) -> dict:
    """Return an explicit, reviewable proposal, with no execution side effect."""
    if not isinstance(prompt, str) or not prompt.strip():
        raise ValueError("请输入研究指令")
    if len(prompt) > 1000:
        raise ValueError("研究指令最多 1000 个字符")
    text = prompt.strip().lower()
    config = deepcopy(DEFAULT_CONFIG)
    if base_config:
        for key in ("name", "tickers", "start_date", "end_date", "source", "strategy", "account"):
            if key not in base_config:
                continue
            if key in ("account", "strategy"):
                config[key].update(deepcopy(base_config[key]))
            else:
                config[key] = deepcopy(base_config[key])
    changes: list[dict] = []
    warnings: list[str] = []

    def change(field: str, value):
        parts = field.split(".")
        target = config
        for part in parts[:-1]:
            target = target.setdefault(part, {})
        target[parts[-1]] = value
        changes.append({"field": field, "value": value})

    if re.search(r"布林|bollinger", text):
        change("strategy", {"name": "bollinger_bands", "parameters": {"window": 20, "std_dev": 2}})
    elif re.search(r"rsi|相对强弱", text):
        change("strategy", {"name": "rsi_reversal", "parameters": {"window": 14, "buy_threshold": 30, "sell_threshold": 70}})
    elif re.search(r"双均线|均线交叉|dual_ma", text):
        change("strategy", {"name": "dual_ma", "parameters": {"fast_period": 5, "slow_period": 20}})

    field_patterns = [
        (r"(?:快线|短期均线|fast)[^\d]{0,6}(\d+)", "fast_period"),
        (r"(?:慢线|长期均线|slow)[^\d]{0,6}(\d+)", "slow_period"),
        (r"(?:窗口|周期|window)[^\d]{0,6}(\d+)", "window"),
        (r"(?:买入阈值|超卖)[^\d]{0,6}(\d+)", "buy_threshold"),
        (r"(?:卖出阈值|超买)[^\d]{0,6}(\d+)", "sell_threshold"),
    ]
    allowed = {
        "dual_ma": {"fast_period", "slow_period"},
        "bollinger_bands": {"window", "std_dev"},
        "rsi_reversal": {"window", "buy_threshold", "sell_threshold"},
    }
    strategy_name = config["strategy"]["name"]
    for pattern, field in field_patterns:
        match = re.search(pattern, text)
        if match:
            if field in allowed.get(strategy_name, set()):
                change(f"strategy.parameters.{field}", int(match.group(1)))
            else:
                warnings.append(f"当前策略不支持参数 {field}，该参数未应用。")

    names = {"五粮液": "000858", "中国平安": "601318", "招商银行": "600036", "贵州茅台": "600519", "平安银行": "000001"}
    tickers = re.findall(r"(?<!\d)((?:sh|sz)?\d{6})(?!\d)", text)
    selected = []
    for ticker in tickers:
        normalized = ticker[2:] if ticker.startswith(("sh", "sz")) else ticker
        if normalized not in selected:
            selected.append(normalized)
    for name, ticker in names.items():
        if name in text and ticker not in selected:
            selected.append(ticker)
    if selected:
        change("tickers", selected)

    dates = re.findall(r"(20\d{2})[-/.年](\d{1,2})[-/.月](\d{1,2})日?", text)
    if len(dates) >= 2:
        change("start_date", "-".join([dates[0][0], dates[0][1].zfill(2), dates[0][2].zfill(2)]))
        change("end_date", "-".join([dates[1][0], dates[1][1].zfill(2), dates[1][2].zfill(2)]))
    elif not dates:
        years = re.search(r"(20\d{2})\s*年?\s*(?:到|至|—|~|-)\s*(20\d{2})\s*年?", text)
        if years:
            change("start_date", years.group(1) + "-01-01")
            change("end_date", years.group(2) + "-12-31")

    money = re.search(r"(?:本金|资金|初始资金)[^\d]{0,6}([\d.]+)\s*(万|千|元)?", text)
    if money:
        multiplier = {"万": 10000, "千": 1000}.get(money.group(2), 1)
        change("account.initial_cash", float(money.group(1)) * multiplier)
    size = re.search(r"(?:单票仓位|仓位|持仓上限)[^\d]{0,8}([\d.]+)\s*(%|％|成)", text)
    if size:
        change("account.position_size", float(size.group(1)) / (10 if size.group(2) == "成" else 100))
    slippage = re.search(r"滑点[^\d]{0,8}([\d.]+)\s*(?:bps?|基点)", text)
    if slippage:
        change("account.slippage_bps", float(slippage.group(1)))
    commission = re.search(r"佣金[^\d]{0,6}万分之\s*([\d.]+)", text)
    if commission:
        change("account.commission_rate", float(commission.group(1)) / 10000)
    if re.search(r"真实行情|在线行情|akshare", text):
        change("source", "akshare")
    elif re.search(r"演示|离线|合成", text):
        change("source", "demo")

    experiment = None
    if re.search(r"压力|失效|敏感性|stress", text):
        experiment = {"kind": "pressure"}
    elif re.search(r"样本外|滚动验证|walk.?forward", text):
        experiment = {"kind": "walk_forward"}
    elif re.search(r"参数扫描|参数比较|参数对比", text):
        experiment = {"kind": "parameter"}
    if experiment:
        warnings.append("实验需基于已完成的回测，在实验室执行。")
    if not changes and not experiment:
        warnings.append("没有识别到支持的设置。可输入：双均线，快线 5，慢线 20，仓位 30%，本金 10 万。")
    return {
        "mode": "local_rules",
        "label": "本地规则解析",
        "recognized": bool(changes or experiment),
        "config": config,
        "changes": changes,
        "experiment": experiment,
        "warnings": warnings,
        "explanation": "仅识别策略、参数、标的、日期、资金和实验类型；最终配置仍需通过回测参数校验。",
    }
