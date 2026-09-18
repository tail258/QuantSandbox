"""A durable queue supervised by a thread; each research job runs in a child process.

The web server never computes backtests in the ASGI event loop. One child at a time
also avoids cache-update races. Cancellation terminates that isolated child.
"""
from __future__ import annotations

import copy
import multiprocessing
import threading
from pathlib import Path

import pandas as pd

from backend.api.schemas import StrategyConfig
from backend.core.data_center import DEMO_START, DataCenter, DataUnavailable
from backend.services.store import Store
from backend.services.provenance import engine_fingerprint


def execute_job(root: str, identifier: str) -> None:
    store = Store(Path(root))
    run = store.get_run(identifier)
    if not run or run["status"] != "running":
        return
    try:
        from backend.research import run_backtest, run_stress_suite, run_walk_forward

        implementation = engine_fingerprint()

        config = run["config"]
        center = DataCenter(root=root)
        frames = {}
        manifests = run["manifest"]
        if manifests:
            frames = {item["ticker"]: center.load_snapshot(item) for item in manifests}
        else:
            # Reserve enough history for the maximum 500-bar indicator even
            # after exchange holidays; the engine still trades only in scope.
            earliest = pd.Timestamp(config["start_date"]) - pd.Timedelta(days=1100)
            if config["source"] == "demo":
                earliest = max(earliest, pd.Timestamp(DEMO_START))
            for index, ticker in enumerate(config["tickers"]):
                frame = center.fetch_stock_data(ticker, str(earliest.date()), config["end_date"], source=config["source"])
                frames[ticker] = frame
                manifests.append(center.snapshot(ticker, frame, config["source"]))
                store.patch_run(identifier, unless_terminal=True, progress=10 + int(40 * (index + 1) / len(config["tickers"])))
        store.patch_run(identifier, unless_terminal=True, progress=55, manifest=manifests)
        if store.get_run(identifier)["status"] == "cancelled":
            return

        kind = run["kind"]
        if kind in {"backtest", "branch"}:
            result = run_backtest(frames, config, run["branch"])
        elif kind == "pressure":
            result = run_stress_suite(frames, config)
        elif kind == "walk_forward":
            options = run["experiment"]
            result = run_walk_forward(frames, config, training_days=options["training_days"], test_days=options["test_days"])
        elif kind == "parameter":
            options = run["experiment"]
            variants = []
            baseline = run_backtest(frames, config)
            for index, value in enumerate(options["values"]):
                changed = copy.deepcopy(config)
                changed["strategy"]["parameters"][options["parameter"]] = value
                StrategyConfig.model_validate(changed["strategy"])
                variant = run_backtest(frames, changed)
                variants.append({"value": value, "metrics": variant["metrics"]})
                store.patch_run(identifier, unless_terminal=True, progress=55 + int(35 * (index + 1) / len(options["values"])))
            best = max(variants, key=lambda item: item["metrics"]["total_return"])
            result = {"parameter": options["parameter"], "baseline": baseline["metrics"], "variants": variants,
                      "best_value": best["value"], "notice": "同区间参数敏感性研究；最佳值未经样本外验证，不构成选参结论。"}
        else:
            raise ValueError("未知实验类型")
        if run.get("expected_result"):
            # Compare meaningful deterministic values; presentation metadata may differ.
            expected = run["expected_result"]
            compared = [key for key in ["metrics", "series", "trades", "scenarios", "variants", "folds"] if key in expected]
            differences = [key for key in compared if result.get(key) != expected[key]]
            result["replay_verification"] = {"matched": bool(compared) and not differences, "compared_fields": compared,
                                               "different_fields": differences, "notice": "使用当前引擎与导入数据重新计算"}
        result["engine"] = implementation
        result["data_provenance"] = {"source": config["source"], "synthetic": config["source"] == "demo",
                                     "snapshot_hashes": [item["sha256"] for item in manifests]}
        store.patch_run(identifier, unless_terminal=True, status="completed", progress=100, result=result)
    except Exception as exc:
        code = "data_unavailable" if isinstance(exc, DataUnavailable) else "research_failed"
        store.patch_run(identifier, unless_terminal=True, status="failed", error={"code": code, "message": str(exc)})


class JobRunner:
    def __init__(self, store: Store):
        self.store = store
        self.stop_event = threading.Event()
        self.wake_event = threading.Event()
        self.lock = threading.Lock()
        self.current: tuple[str, multiprocessing.Process] | None = None
        self.thread = threading.Thread(target=self._supervise, name="research-supervisor", daemon=True)

    def start(self):
        self.store.recover_interrupted()
        self.thread.start()

    def notify(self):
        self.wake_event.set()

    def _supervise(self):
        context = multiprocessing.get_context("spawn")
        while not self.stop_event.is_set():
            identifier = self.store.next_queued()
            if identifier is None:
                self.wake_event.wait(.25)
                self.wake_event.clear()
                continue
            with self.lock:
                if self.stop_event.is_set():
                    break
                self.store.patch_run(identifier, unless_terminal=True, status="running", progress=5)
                process = context.Process(target=execute_job, args=(str(self.store.root), identifier), daemon=True,
                                          name=f"research-{identifier[:8]}")
                self.current = identifier, process
                try:
                    process.start()
                except Exception as exc:
                    self.current = None
                    self.store.patch_run(identifier, unless_terminal=True, status="failed",
                                         error={"code": "worker_start_failed", "message": str(exc)})
                    continue
            while process.is_alive() and not self.stop_event.is_set():
                process.join(.15)
            if process.is_alive():
                process.terminate()
                process.join(3)
            run = self.store.get_run(identifier)
            if run["status"] == "running":
                self.store.patch_run(identifier, unless_terminal=True, status="failed",
                                     error={"code": "worker_stopped", "message": "研究进程中断，请重新运行。"})
            with self.lock:
                self.current = None

    def cancel(self, identifier: str):
        with self.lock:
            self.store.patch_run(identifier, unless_terminal=True, status="cancelled")
            if self.current and self.current[0] == identifier and self.current[1].is_alive():
                self.current[1].terminate()
        self.notify()

    def close(self):
        self.stop_event.set()
        self.notify()
        self.thread.join(5)
        with self.lock:
            if self.current and self.current[1].is_alive():
                self.current[1].terminate()
