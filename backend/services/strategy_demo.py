"""The fixed, offline daily strategy walkthrough and release fixture."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory

from backend.api.schemas import RunConfig
from backend.core.data_center import DataCenter, canonical_json, synthetic_frame
from backend.services.errors import ResearchError
from backend.services.evidence import EvidenceService
from backend.services.research import ResearchService
from backend.services.runner import execute_job
from backend.services.store import Store

DEMO_TICKER = "600036"
SNAPSHOT_START = "2023-10-02"
START_DATE = "2024-01-01"
END_DATE = "2024-06-28"
SUSPENSION_DATE = "2024-03-04"
SNAPSHOT_SHA256 = "0afe8b3aff2f16a919b4c367ed5743942856e93b2abe17df6578dd2a853b4281"
DEFAULT_FAST_PERIOD = 5
DEFAULT_SLOW_PERIOD = 20
MAX_PERIOD = 60
MAX_EVIDENCE_LENGTH = 300_000
RESULT_FIELDS = ("metrics", "series", "trades", "decisions")


def study_config(fast_period: int = DEFAULT_FAST_PERIOD, slow_period: int = DEFAULT_SLOW_PERIOD) -> dict:
    return RunConfig.model_validate({
        "name": "Offline reproducibility example", "source": "demo", "tickers": [DEMO_TICKER],
        "start_date": START_DATE, "end_date": END_DATE,
        "strategy": {"name": "dual_ma", "parameters": {"fast_period": fast_period, "slow_period": slow_period}},
        "account": {"initial_cash": 1000000, "commission_rate": .0003, "tax_rate": .0005,
                    "min_commission": 5, "slippage_bps": 5, "position_size": .3},
    }).model_dump(mode="json")


def _json_hash(value) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def result_hash(result: dict) -> str:
    return _json_hash({key: result[key] for key in RESULT_FIELDS})


def _complete(store: Store, run: dict) -> dict:
    store.patch_run(run["id"], status="running")
    execute_job(str(store.root), run["id"])
    finished = store.get_run(run["id"])
    if finished["status"] != "completed":
        raise RuntimeError(f"Offline calculation failed: {finished.get('error')}")
    return finished


def write_baseline(root: Path, config: dict) -> tuple[dict, str]:
    """Caller supplies an isolated store root. Never invoke a market provider."""
    store = Store(root)
    center = DataCenter(root=store.root)
    research = ResearchService(store)
    frame = synthetic_frame(DEMO_TICKER)
    frame = frame.loc[frame.date.between(SNAPSHOT_START, END_DATE)].reset_index(drop=True)
    # Artificial controls: a known suspension and no inferred price limits.
    frame["is_suspended"] = frame.date.eq(SUSPENSION_DATE)
    frame["limit_up"] = None
    frame["limit_down"] = None
    manifest = center.snapshot(DEMO_TICKER, frame, "demo")
    if manifest["sha256"] != SNAPSHOT_SHA256:
        raise RuntimeError("Offline strategy fixture differs from the fixed snapshot")
    run = _complete(store, research.schedule(config, manifest=[manifest]))
    return run, canonical_json(EvidenceService(research, center).export_run(run["id"]))


def _demo_evidence(raw: str) -> dict:
    """Allow only this fixed dataset and this walkthrough's editable MA periods."""
    try:
        package = json.loads(raw)
    except (ValueError, RecursionError) as exc:
        raise ResearchError(422, "Invalid strategy demo evidence") from exc

    not_demo = "Evidence does not belong to the offline strategy demo"
    try:
        run = package["run"]
        config = run["config"]
        parameters = config["strategy"]["parameters"]
        fast, slow = parameters["fast_period"], parameters["slow_period"]
        [dataset] = package["datasets"]
        manifest = dataset["manifest"]
        if not (
            type(fast) is int and type(slow) is int and 2 <= fast < slow <= MAX_PERIOD
            and canonical_json(config) == canonical_json(study_config(fast, slow))
            and manifest["sha256"] == SNAPSHOT_SHA256
            and manifest["ticker"] == DEMO_TICKER and manifest["source"] == "demo"
            and manifest["synthetic"] is True and "origin" not in manifest
            and _json_hash(dataset["rows"]) == SNAPSHOT_SHA256
            and run["kind"] == "backtest" and run["branch"] is None and run["experiment"] is None
            and isinstance(run["result"], dict) and set(RESULT_FIELDS) <= run["result"].keys()
        ):
            raise ResearchError(422, not_demo)
    except (KeyError, TypeError, ValueError, RecursionError) as exc:
        raise ResearchError(422, not_demo) from exc
    return package


def recalculate_evidence(root: Path, raw: str) -> tuple[dict, dict]:
    """Read the exported rows into another store and compare deterministic outputs."""
    package = _demo_evidence(raw)
    store = Store(root)
    center = DataCenter(root=store.root)
    research = ResearchService(store)
    try:
        imported = EvidenceService(research, center).import_run(package)
    except RecursionError as exc:
        raise ResearchError(422, "Invalid strategy demo evidence") from exc
    replay = _complete(store, imported)
    actual, expected = replay["result"], package["run"]["result"]
    differences = [key for key in RESULT_FIELDS if canonical_json(actual[key]) != canonical_json(expected[key])]
    return replay, {"matched": not differences, "compared_fields": list(RESULT_FIELDS), "different_fields": differences}


def run_demo(fast_period: int, slow_period: int) -> dict:
    config = study_config(fast_period, slow_period)
    with TemporaryDirectory(prefix="quantsandbox-strategy-demo-") as temporary:
        run, raw = write_baseline(Path(temporary), config)
    snapshot, result = run["manifest"][0], run["result"]
    return {
        "synthetic": True,
        "snapshot": {
            **{key: snapshot[key] for key in ("sha256", "start_date", "end_date", "rows", "version")},
            "suspension_dates": [SUSPENSION_DATE],
        },
        "parameters": config["strategy"]["parameters"],
        "period": {"start_date": START_DATE, "end_date": END_DATE, "observations": len(result["series"]),
                   "warmup_rows": snapshot["rows"] - len(result["series"])},
        "account": config["account"],
        "metrics": result["metrics"],
        "series": [{key: row[key] for key in ("date", "equity", "benchmark")} for row in result["series"]],
        "trades": result["trades"],
        "result_sha256": result_hash(result),
        "evidence": raw,
    }


def replay_demo(raw: str) -> dict:
    with TemporaryDirectory(prefix="quantsandbox-strategy-replay-") as temporary:
        replay, verification = recalculate_evidence(Path(temporary), raw)
    return {
        "synthetic": True,
        "snapshot_sha256": replay["manifest"][0]["sha256"],
        "result_sha256": result_hash(replay["result"]),
        **verification,
    }
