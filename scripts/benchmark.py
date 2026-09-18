"""Repeatable offline benchmark. Invoke from project root with the project Python."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import platform
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.core.data_center import synthetic_frame
from backend.research import run_backtest


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--symbols", type=int, default=3)
    parser.add_argument("--start", default="2021-01-01")
    parser.add_argument("--end", default="2025-12-31")
    options = parser.parse_args()
    if not 1 <= options.symbols <= 100:
        parser.error("--symbols must be between 1 and 100")
    seed = synthetic_frame("000858")
    frames = {f"sample-{i:03d}": seed.copy() for i in range(options.symbols)}
    config = {
        "tickers": list(frames), "start_date": options.start, "end_date": options.end,
        "strategy": {"name": "dual_ma", "parameters": {"fast_period": 5, "slow_period": 20}},
        "account": {"initial_cash": 1000000, "position_size": 1 / options.symbols},
    }
    before = time.perf_counter()
    result = run_backtest(frames, config)
    elapsed = time.perf_counter() - before
    print(json.dumps({"python": platform.python_version(), "platform": platform.platform(),
                      "symbols": options.symbols, "bars": sum(len(b) for b in result["bars"].values()),
                      "seconds": round(elapsed, 3), "trades": len(result["trades"]),
                      "synthetic": True, "io_included": False}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
