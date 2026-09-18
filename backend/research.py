"""Inspectable experiments built on the same deterministic execution engine."""
from __future__ import annotations

from copy import deepcopy
import pandas as pd

from backend.core.engine import ACCOUNT_DEFAULTS, calculate_metrics, run_backtest

__all__ = ["run_backtest", "calculate_metrics", "run_stress_suite", "run_walk_forward"]


def run_stress_suite(frames: dict[str, pd.DataFrame], config: dict) -> dict:
    """One-factor execution assumptions; measured outcomes, not projected claims."""
    baseline = run_backtest(frames, config)
    account = {**ACCOUNT_DEFAULTS, **config.get("account", {})}
    scenarios = [
        ("fees_2x", "双倍交易费用", {"commission_rate": min(account["commission_rate"] * 2, 0.1), "min_commission": account["min_commission"] * 2, "tax_rate": min(account["tax_rate"] * 2, 0.1)}, "佣金、最低佣金与卖出税费同时翻倍"),
        ("slippage_20", "滑点增加 20 bps", {"slippage_bps": min(account["slippage_bps"] + 20, 1000)}, "每次买卖额外承受 0.20% 不利价格偏移"),
        ("delay_1", "延迟一个交易日", {"execution_delay": account["execution_delay"] + 1}, "信号在额外一根标的日线之后撮合"),
        ("half_position", "仓位预算减半", {"position_size": account["position_size"] * 0.5}, "单标的每次入场资金预算减半"),
        ("combined", "复合执行压力", {"commission_rate": min(account["commission_rate"] * 2, 0.1), "min_commission": account["min_commission"] * 2,
                                       "slippage_bps": min(account["slippage_bps"] + 30, 1000), "execution_delay": account["execution_delay"] + 1}, "双倍佣金、额外 30 bps 滑点及一日延迟"),
    ]
    results = []
    for identifier, name, changes, description in scenarios:
        variant = deepcopy(config)
        variant["account"] = {**account, **changes}
        result = run_backtest(frames, variant)
        results.append({"id": identifier, "name": name, "description": description, "changes": changes,
                        "metrics": result["metrics"], "delta_return": round(result["metrics"]["total_return"] - baseline["metrics"]["total_return"], 4),
                        "series": [{k: s[k] for k in ("date", "equity", "drawdown")} for s in result["series"]]})
    return {"kind": "stress", "baseline": baseline["metrics"], "scenarios": results,
            "assumptions": baseline["assumptions"], "interpretation": "情景是固定行情下的执行假设变化；情景收益可能改善，不能视为概率预测。"}


def _candidates(config):
    strategy = config.get("strategy", {"name": "sma_cross", "parameters": {}})
    name = strategy["name"]
    original = strategy.get("parameters", {})
    if name in ("dual_ma", "sma_cross"):
        params = [{"fast_period": 3, "slow_period": 10}, {"fast_period": 5, "slow_period": 20}, {"fast_period": 10, "slow_period": 30}]
    elif name in ("rsi_reversal", "rsi_reversion"):
        params = [{"window": 7, "buy_threshold": 30, "sell_threshold": 70}, {"window": 14, "buy_threshold": 30, "sell_threshold": 70}, {"window": 21, "buy_threshold": 35, "sell_threshold": 65}]
    elif name == "bollinger_bands":
        params = [{"window": 10, "std_dev": 1.5}, {"window": 20, "std_dev": 2}, {"window": 30, "std_dev": 2}]
    else:
        params = [{"window": 10, "threshold": 0.01}, {"window": 20, "threshold": 0.02}, {"window": 40, "threshold": 0.03}]
    return [{"name": name, "parameters": p} for p in [original, *params]]


def run_walk_forward(frames: dict[str, pd.DataFrame], config: dict, training_days: int = 60,
                     test_days: int = 20, candidates: list[dict] | None = None) -> dict:
    """Rolling parameter selection with a continuous out-of-sample portfolio.

    Candidate trials each start with initial cash, entirely within the training
    interval. The selected strategy is applied to the following unseen window.
    Test holdings/cash persist at window boundaries; new policies only affect
    subsequent orders. Warm-up observations are earlier than each tested window.
    """
    if not isinstance(training_days, int) or training_days < 10 or not isinstance(test_days, int) or test_days < 5:
        raise ValueError("训练窗口至少 10 个交易日，测试窗口至少 5 个交易日")
    start = pd.Timestamp(config["start_date"])
    end = pd.Timestamp(config["end_date"])
    tickers = config.get("tickers", list(frames))
    dates = sorted({pd.Timestamp(d).normalize() for t in tickers for d in frames[t].date if start <= pd.Timestamp(d) <= end})
    if len(dates) < training_days + 5:
        raise ValueError(f"样本不足：需要至少 {training_days + 5} 个交易日，实际 {len(dates)} 个")
    choices = candidates or _candidates(config)
    if not 1 <= len(choices) <= 20:
        raise ValueError("候选策略数量须在 1–20 之间")
    folds = []
    selected = []
    for offset in range(training_days, len(dates), test_days):
        window = dates[offset:offset + test_days]
        if len(window) < 5:
            break
        train_start, train_end = dates[offset - training_days], dates[offset - 1]
        trials = []
        # Truncate physical input too, so future test rows cannot affect selection.
        training_frames = {t: frames[t].loc[pd.to_datetime(frames[t].date) <= train_end].copy() for t in tickers}
        for index, candidate in enumerate(choices):
            trial_config = deepcopy(config)
            trial_config.pop("strategy_schedule", None)
            trial_config.update(start_date=train_start.strftime("%Y-%m-%d"), end_date=train_end.strftime("%Y-%m-%d"), strategy=candidate)
            result = run_backtest(training_frames, trial_config)
            metric = result["metrics"]
            # Explicit simple objective, recorded for all candidates.
            score = metric["total_return"] + metric["max_drawdown"] * 0.5
            trials.append({"candidate_index": index, "strategy": deepcopy(candidate), "score": round(score, 6), "metrics": metric})
        winner = max(trials, key=lambda t: (t["score"], -t["candidate_index"]))
        selected.append(deepcopy(winner["strategy"]))
        folds.append({"fold": len(folds) + 1, "train_start": train_start.strftime("%Y-%m-%d"), "train_end": train_end.strftime("%Y-%m-%d"),
                      "test_start": window[0].strftime("%Y-%m-%d"), "test_end": window[-1].strftime("%Y-%m-%d"),
                      "selected_strategy": deepcopy(winner["strategy"]), "training_metrics": winner["metrics"], "trials": trials})
    if not folds:
        raise ValueError("没有完整的样本外测试窗口")
    out_config = deepcopy(config)
    out_config.update(start_date=folds[0]["test_start"], end_date=folds[-1]["test_end"], strategy=selected[0])
    out_config["strategy_schedule"] = [{"at_date": folds[i-1]["test_end"], "strategy": selected[i]} for i in range(1, len(folds))]
    out = run_backtest(frames, out_config)
    prior_equity = float({**ACCOUNT_DEFAULTS, **config.get("account", {})}["initial_cash"])
    prior_benchmark = prior_equity
    for fold in folds:
        visible = [s for s in out["series"] if fold["test_start"] <= s["date"] <= fold["test_end"]]
        fills = [t for t in out["trades"] if fold["test_start"] <= t["date"] <= fold["test_end"]]
        normalized = [{**s, "benchmark": s["benchmark"] / prior_benchmark * prior_equity} for s in visible]
        fold["test_metrics"] = calculate_metrics(normalized, fills, prior_equity)
        prior_equity = visible[-1]["equity"]
        prior_benchmark = visible[-1]["benchmark"]
    return {"kind": "walk_forward", "folds": folds, "metrics": out["metrics"], "series": out["series"],
            "trades": out["trades"], "config": out_config, "training_days": training_days, "test_days": test_days,
            "selection_objective": "训练区间收益率 + 0.5 × 最大回撤（负数），并列时选列表靠前候选。",
            "assumptions": [*out["assumptions"], "样本外账户连续；每个训练实验独立初始化资金。最后不足 5 日的尾部不纳入。",
                            "滚动训练允许使用此前已结束的测试时段；本实现未提供独立的最终保留测试集。"]}
