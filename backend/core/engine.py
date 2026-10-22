"""Deterministic, long-only, shared-cash daily-bar research engine.

Signals observed at close cannot execute before the next instrument bar.
Prices are research prices supplied by a data snapshot. Corporate actions and
historical exchange rules are not inferred from ticker strings.
"""
from __future__ import annotations

from copy import deepcopy
import math

import numpy as np
import pandas as pd

from backend.core.strategy import StrategyFactory
from backend.core.account import ACCOUNT_DEFAULTS, normalize_account as _account, AccountLedger
from backend.core.metrics import calculate_metrics
from backend.core.execution import execute_order

ENGINE_VERSION = "2.0.0"
INDICATORS = ("fast_ma", "slow_ma", "middle_band", "upper_band", "lower_band", "rsi", "momentum")


def _number(value, default=None):
    if value is None or pd.isna(value):
        return default
    result = float(value)
    return result if math.isfinite(result) else default


def _date(value):
    return pd.Timestamp(value).strftime("%Y-%m-%d")


def _prepare(frame):
    required = {"date", "open", "high", "low", "close", "volume"}
    if not required.issubset(frame.columns):
        raise ValueError(f"行情缺少字段：{sorted(required - set(frame.columns))}")
    out = frame.copy()
    out["date"] = pd.to_datetime(out.date, errors="raise").dt.normalize()
    if out.date.isna().any() or out.date.duplicated().any():
        raise ValueError("行情日期不能为空或重复")
    out = out.sort_values("date").reset_index(drop=True)
    for col in required - {"date"}:
        out[col] = pd.to_numeric(out[col], errors="raise")
        if not np.isfinite(out[col]).all():
            raise ValueError(f"行情 {col} 存在无效值")
    if (out[["open", "high", "low", "close"]] <= 0).any().any() or (out.volume < 0).any():
        raise ValueError("行情价格必须为正数，成交量不能为负数")
    if ((out.high < out[["open", "close", "low"]].max(axis=1)) | (out.low > out[["open", "close", "high"]].min(axis=1))).any():
        raise ValueError("OHLC 高低价关系不合法")
    return out


def run_backtest(frames: dict[str, pd.DataFrame], config: dict, branch: dict | None = None) -> dict:
    """Branch changes take effect at fork-day close. Input before start is warm-up.

    Branches use deterministic replay from origin, preserving prior state and fills.
    The final warm-up close may generate the first official session's order.
    """
    config = deepcopy(config)
    account = _account(config)
    tickers = list(dict.fromkeys(str(t) for t in config.get("tickers", frames.keys())))
    if not tickers or any(t not in frames for t in tickers):
        raise ValueError("股票池为空或缺少对应行情")
    tickers = sorted(tickers)
    strategy = config.get("strategy", {"name": "dual_ma", "parameters": {}})
    strategy = {"name": strategy.get("name", "dual_ma"), "parameters": strategy.get("parameters", strategy.get("params", {}))}
    sources = {t: _prepare(frames[t]) for t in tickers}
    if any(f.empty for f in sources.values()):
        raise ValueError("股票池中存在空行情")
    start = pd.Timestamp(config.get("start_date", min(f.date.min() for f in sources.values()))).normalize()
    end = pd.Timestamp(config.get("end_date", max(f.date.max() for f in sources.values()))).normalize()
    if start > end:
        raise ValueError("开始日期不得晚于结束日期")
    dates = sorted({d for frame in sources.values() for d in frame.date if start <= d <= end})
    if not dates:
        raise ValueError("所选区间没有交易数据")
    if config.get("_precomputed_signals"):
        if any("trade_signal" not in f or not f.trade_signal.isin([-1, 0, 1]).all() for f in sources.values()):
            raise ValueError("预计算信号必须为 -1、0 或 1")
        generated = {t: f.copy() for t, f in sources.items()}
    else:
        generated = {t: StrategyFactory.generate_signals(f, strategy["name"], strategy["parameters"]) for t, f in sources.items()}
    lookup = {t: f.set_index("date") for t, f in generated.items()}
    transitions = []
    # Publicly persisted schedule used by walk-forward: policies are selected on
    # prior training data, then installed at the previous test window's close.
    for item in config.get("strategy_schedule", []):
        at = pd.Timestamp(item["at_date"]).normalize()
        if at not in dates:
            raise ValueError("策略切换日期必须为区间内交易日")
        selected = item["strategy"]
        selected = {"name": selected["name"], "parameters": selected.get("parameters", {})}
        table = {t: StrategyFactory.generate_signals(f, selected["name"], selected["parameters"]).set_index("date") for t, f in sources.items()}
        transitions.append({"date": at, "strategy": selected, "account": account, "lookup": table, "rebalance": False})
    branch = branch or {}
    history = branch.get("history", [])
    if not isinstance(history, list) or len(history) > 100:
        raise ValueError("分叉历史必须为最多 100 项的列表")
    lineage = [*history, {k: v for k, v in branch.items() if k != "history"}]
    current_policy, current_account = strategy, account
    previous_fork = None
    for item in lineage:
        fork_value = item.get("at_date", item.get("fork_date"))
        if fork_value is None:
            if item:
                raise ValueError("分叉修改必须指定日期")
            continue
        fork = pd.Timestamp(fork_value).normalize()
        if fork not in dates:
            raise ValueError("分叉日期必须为本次研究的交易日")
        if previous_fork is not None and fork < previous_fork:
            raise ValueError("子分叉日期不得早于父分叉日期")
        previous_fork = fork
        prior_schedule = [t for t in transitions if t["date"] <= fork]
        if prior_schedule:
            prior = max(enumerate(prior_schedule), key=lambda pair: (pair[1]["date"], pair[0]))[1]
            current_policy, current_account = prior["strategy"], prior["account"]
        changed_policy = item.get("strategy", current_policy)
        changed_name = changed_policy.get("name", current_policy["name"])
        changed_policy = {"name": changed_name, "parameters": changed_policy.get("parameters", changed_policy.get("params", current_policy["parameters"] if changed_name == current_policy["name"] else {}))}
        changed_account = {**current_account, **item.get("account", {})}
        if "position_size" in item:
            changed_account["position_size"] = item["position_size"]
        if changed_account["initial_cash"] != account["initial_cash"]:
            raise ValueError("分叉不能改变历史初始资金")
        changed_account = _account({"account": changed_account})
        if changed_policy != current_policy or changed_account != current_account:
            # Several child edits at the same close are one final policy change.
            # Compare its rebalance with the actual policy before that close.
            earlier = [t for t in transitions if t["date"] < fork]
            reference = max(earlier, key=lambda t: t["date"]) if earlier else None
            before_policy = reference["strategy"] if reference else strategy
            before_account = reference["account"] if reference else account
            transitions = [t for t in transitions if t["date"] != fork]
            if changed_policy != before_policy or changed_account != before_account:
                table = {t: StrategyFactory.generate_signals(f, changed_policy["name"], changed_policy["parameters"]).set_index("date") for t, f in sources.items()}
                transitions.append({"date": fork, "strategy": changed_policy, "account": changed_account,
                                    "lookup": table, "rebalance": changed_account["position_size"] != before_account["position_size"]})
        current_policy, current_account = changed_policy, changed_account
    transitions.sort(key=lambda x: x["date"])
    ledger = AccountLedger(account["initial_cash"], tickers)
    initial = ledger.cash
    previous_equity = ledger.cash
    peak = ledger.cash
    positions = ledger.positions
    last_close = {t: float(f.loc[f.date <= start, "close"].iloc[-1]) if (f.date <= start).any() else float(f.close.iloc[0]) for t, f in sources.items()}
    benchmark_entry = {}
    pending: dict[str, dict] = {}
    series, trades, decisions, checkpoints = [], [], [], []

    def evidence(row, policy):
        return {"strategy": policy["name"], "parameters": deepcopy(policy["parameters"]),
                "close": float(row["close"]), "indicators": {k: _number(row[k]) for k in INDICATORS if k in row},
                "signal": int(row["trade_signal"]), "observed_at": "close",
                "execution_rule": "next_available_open", "uses_future_data": False}

    def decide(ticker, day, row, policy, settings, rebalance=False, record=True):
        signal = int(row.trade_signal)
        position = positions[ticker]
        ev = evidence(row, policy)
        ev["signal_date"] = _date(day)
        action = "buy" if signal > 0 else "sell" if signal < 0 else "hold"
        reason = "策略条件满足，下一交易日开盘执行" if signal else "等待策略条件"
        order = None
        if signal < 0 and position["shares"] > 0:
            order = {"action": "sell", "target_fraction": 0.0}
        elif signal > 0 and position["shares"] == 0 and settings["position_size"] > 0:
            order = {"action": "buy", "target_fraction": settings["position_size"]}
        elif rebalance and position["shares"] > 0 and signal >= 0:
            order = {"action": "rebalance", "target_fraction": settings["position_size"]}
            reason = "分叉后的仓位上限在下一开盘重新配置"
            action = "rebalance"
        elif signal > 0 and position["shares"]:
            reason, action = "已持仓，维持当前头寸", "hold"
        elif signal < 0:
            reason, action = "当前空仓，无需卖出", "hold"
        queued = order is not None and ticker not in pending
        if queued:
            pending[ticker] = {**order, "ticker": ticker, "signal_date": _date(day), "remaining_bars": settings["execution_delay"],
                               "settings": deepcopy(settings), "evidence": ev, "reason": reason}
        if record:
            decisions.append({"id": f"decision-{len(decisions)+1:05d}", "date": _date(day), "ticker": ticker,
                              "action": action, "status": "queued" if queued else "pending" if ticker in pending else "observed", "reason": reason, "evidence": ev})

    for ticker in tickers:
        history = generated[ticker].loc[generated[ticker].date < start]
        if not history.empty:
            row = history.iloc[-1]
            decide(ticker, row.date, row, strategy, account, record=False)

    for day in dates:
        available = {t: lookup[t].loc[day] for t in tickers if day in lookup[t].index}
        due = []
        for ticker in tickers:
            order = pending.get(ticker)
            if order and ticker in available and day > pd.Timestamp(order["signal_date"]):
                order["remaining_bars"] -= 1
                if order["remaining_bars"] <= 0:
                    due.append(ticker)
        due.sort(key=lambda t: (pending[t]["action"] != "sell", t))
        for ticker in due:
            order = pending[ticker]
            row = available[ticker]
            settings = order["settings"]
            fill = execute_order(ledger, ticker, day, row, order, previous_equity)
            action = fill["action"]
            if fill["status"] == "deferred":
                decisions.append({"id": f"decision-{len(decisions)+1:05d}", "date": _date(day), "ticker": ticker,
                                  "action": action, "status": "deferred", "reason": "停牌、零成交量或显式涨跌停限制，订单顺延",
                                  "evidence": deepcopy(order["evidence"])})
                continue
            if fill["status"] == "t_plus_one":
                continue
            raw_price, price, qty = fill["raw_price"], fill["price"], fill["qty"]
            value, fee, realized = fill["value"], fill["fee"], fill["realized"]
            closed, cycle_pnl = fill["closed"], fill["cycle_pnl"]
            del pending[ticker]
            if qty:
                trade_ev = deepcopy(order["evidence"])
                trade_ev.update({"execution_open": raw_price, "slippage_bps": settings["slippage_bps"],
                                 "execution_delay_bars": settings["execution_delay"],
                                 "commission_rate": settings["commission_rate"], "min_commission": settings["min_commission"],
                                 "tax_rate": settings["tax_rate"] if action == "sell" else 0,
                                 "cash_after": round(ledger.cash, 6), "target_fraction": order["target_fraction"]})
                trades.append({"id": f"trade-{len(trades)+1:05d}", "date": _date(day), "ticker": ticker,
                               "action": action, "price": round(price, 6), "shares": int(qty), "fee": round(fee, 6),
                               "value": round(value, 6), "reason": order["reason"], "signal_date": order["signal_date"],
                               "evidence": trade_ev, "realized_pnl": round(realized, 6),
                               "round_trip_closed": closed, "round_trip_pnl": round(cycle_pnl, 6) if closed else None})
            else:
                decisions.append({"id": f"decision-{len(decisions)+1:05d}", "date": _date(day), "ticker": ticker,
                                  "action": action, "status": "rejected", "reason": "现金或仓位预算不足一手，或目标仓位无变化",
                                  "evidence": deepcopy(order["evidence"])})
        for ticker, row in available.items():
            last_close[ticker] = float(row.close)
            benchmark_entry.setdefault(ticker, float(row.open))
        equity = ledger.cash + sum(p["shares"] * last_close[t] for t, p in positions.items())
        peak = max(peak, equity)
        snapshot_positions = {t: {"shares": p["shares"], "cost_basis": round(p["cost_basis"], 6),
                                  "market_value": round(p["shares"] * last_close[t], 6),
                                  "unrealized_pnl": round(p["shares"] * last_close[t] - p["cost_basis"], 6),
                                  "entry_date": p["entry_date"]} for t, p in positions.items()}
        benchmark = initial / len(tickers) * sum(last_close[t] / benchmark_entry[t] if t in benchmark_entry else 1 for t in tickers)
        series.append({"date": _date(day), "equity": round(equity, 6), "cash": round(ledger.cash, 6),
                       "drawdown": round((equity / peak - 1) * 100, 6), "benchmark": round(benchmark, 6),
                       "daily_return": round((equity / previous_equity - 1) * 100, 6), "positions": snapshot_positions})
        eligible = [item for item in transitions if item["date"] <= day]
        transition = eligible[-1] if eligible else None
        policy = transition["strategy"] if transition else strategy
        settings = transition["account"] if transition else account
        changing = transition is not None and transition["date"] == day
        if changing:
            pending.clear()
        for ticker in available:
            row = transition["lookup"][ticker].loc[day] if transition else available[ticker]
            decide(ticker, day, row, policy, settings, rebalance=bool(changing and transition["rebalance"]))
        checkpoints.append({"date": _date(day), "cash": round(ledger.cash, 6), "equity": round(equity, 6),
                            "positions": deepcopy(snapshot_positions), "pending_orders": deepcopy(list(pending.values()))})
        previous_equity = equity
    bars = {}
    for ticker in tickers:
        rows = []
        for _, row in generated[ticker].iterrows():
            if not start <= row.date <= end:
                continue
            bar_date = row.date
            eligible = [item for item in transitions if item["date"] <= bar_date]
            if eligible:
                row = eligible[-1]["lookup"][ticker].loc[bar_date]
            rows.append({"date": _date(bar_date), **{k: _number(row[k]) for k in ("open", "high", "low", "close", "volume", *INDICATORS) if k in row}})
        bars[ticker] = rows
    return {"engine_version": ENGINE_VERSION, "config": config, "metrics": calculate_metrics(series, trades, initial),
            "series": series, "bars": bars, "trades": trades, "decisions": decisions, "checkpoints": checkpoints,
            "assumptions": ["收盘观察信号，最早在下一根可交易日线开盘成交；无日内路径假设。",
                            "共享现金、只做多、默认整手 100 股及 T+1；不同板块规则需另行配置。",
                            "按固定滑点及佣金模型撮合；成交量为零和显式涨跌停价会阻止成交。未提供涨跌停价时不推断限制。",
                            "已排队委托持续等待成交，不因后续信号自动撤单；分叉时以新策略重新生成尚未执行的委托。",
                            "仓位参数是每次入场的单标的资金预算；除分叉调整外不每日再平衡。",
                            "股票依代码排序分配可用资金，先处理卖出。期末不强制平仓。",
                            "基准为等权买入并持有、允许碎股、不计费用；缺失行情以最近已知收盘价估值。",
                            "结果使用输入快照价格；复权行情不等同真实现金账本，未模拟公司行动和价格冲击。",
                            "历史分叉从起点确定性重放，检查点用于审计和展示；尚未直接从检查点恢复状态。",
                            "历史分叉沿用固定行情，不会模拟交易改变市场价格；分叉当日收盘的新指标用于随后订单。"]}


class BacktestEngine:
    """Compatibility adapter for the original single-ticker API."""
    def __init__(self, initial_cash=100000.0, commission_rate=0.00025, tax_rate=0.0005, **kwargs):
        self.account = {"initial_cash": initial_cash, "commission_rate": commission_rate,
                        "tax_rate": tax_rate, "position_size": 1.0, **kwargs}
        self.logs = []

    def run(self, df: pd.DataFrame, symbol: str):
        result = run_backtest({symbol: df}, {"tickers": [symbol], "account": self.account, "_precomputed_signals": "trade_signal" in df,
                                            "strategy": {"name": "dual_ma", "parameters": {}}})
        data = df.copy()
        equity = {s["date"]: s["equity"] for s in result["series"]}
        data["total_equity"] = data.date.map(lambda d: equity.get(_date(d)))
        self.logs = [{**trade, "timestamp": trade["date"], "action": "买入" if trade["action"] == "buy" else "卖出"} for trade in result["trades"]]
        return {"metadata": {**result["metrics"], "symbol": symbol}, "data": data, "logs": self.logs}
