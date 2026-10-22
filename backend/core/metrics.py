"""Performance metrics computed only from the supplied visible prefix."""
import math
import numpy as np


def calculate_metrics(series: list[dict], trades: list[dict], initial_cash: float) -> dict:
    """Metrics for a visible prefix, including initial cash to the first close."""
    equity = [float(initial_cash)] + [float(row["equity"]) for row in series]
    final = equity[-1]
    values = np.asarray(equity, dtype=float)
    daily = values[1:] / values[:-1] - 1
    peak = np.maximum.accumulate(values)
    max_drawdown = float(np.min(values / peak - 1))
    closes = [t for t in trades if t.get("round_trip_closed")]
    pnl = [float(t.get("round_trip_pnl", t.get("realized_pnl", 0))) for t in closes]
    wins = [p for p in pnl if p > 1e-8]
    losses = [p for p in pnl if p < -1e-8]
    stdev = float(np.std(daily, ddof=1)) if len(daily) > 1 else 0
    years = len(daily) / 252
    annual = 0.0
    if years and final > 0:
        exponent = math.log(final / initial_cash) / years
        annual = math.expm1(exponent) if exponent < 700 else float("nan")
    elif years:
        annual = -1.0 if final == 0 else float("nan")
    positions = series[-1].get("positions", {}) if series else {}
    open_count = sum(int(p.get("shares", 0)) > 0 for p in positions.values())
    benchmark_return = (series[-1].get("benchmark", initial_cash) / initial_cash - 1) * 100 if series else 0
    return {"initial_cash": round(initial_cash, 2), "final_equity": round(final, 2),
            "total_return": round((final / initial_cash - 1) * 100, 4),
            "annualized_return": round(annual * 100, 4) if math.isfinite(annual) else None,
            "max_drawdown": round(max_drawdown * 100, 4),
            "sharpe_ratio": round(float(np.mean(daily)) / stdev * math.sqrt(252), 4) if stdev > 0 else 0,
            "win_rate": round(len(wins) / len(pnl) * 100, 4) if pnl else 0,
            "pnl_ratio": round(float(np.mean(wins)) / abs(float(np.mean(losses))), 4) if wins and losses else None,
            "profit_factor": round(sum(wins) / abs(sum(losses)), 4) if losses else None,
            "trade_count": len(trades), "closed_trade_count": len(closes), "round_trip_count": len(closes),
            "open_position_count": open_count, "total_fees": round(sum(t["fee"] for t in trades), 2),
            "realized_pnl": round(sum(t.get("realized_pnl", 0) for t in trades), 2),
            "benchmark_return": round(benchmark_return, 4),
            "excess_return": round((final / initial_cash - 1) * 100 - benchmark_return, 4),
            "trading_days": len(series), "ending_cash": round(series[-1]["cash"], 2) if series else round(initial_cash, 2)}


