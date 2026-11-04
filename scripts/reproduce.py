"""Offline, isolated baseline -> evidence export -> import/replay release check."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.api.schemas import RunConfig
from backend.core.data_center import DEMO_VERSION, DataCenter, canonical_json, synthetic_frame
from backend.services.evidence import EvidenceService
from backend.services.research import ResearchService
from backend.services.runner import execute_job
from backend.services.store import Store

# Freeze the study, including indicator warm-up and explicit synthetic controls.
CONFIG = {
    "name": "Offline reproducibility example", "source": "demo", "tickers": ["600036"],
    "start_date": "2024-01-01", "end_date": "2024-06-28",
    "strategy": {"name": "dual_ma", "parameters": {"fast_period": 5, "slow_period": 20}},
    "account": {"initial_cash": 1000000, "commission_rate": .0003, "tax_rate": .0005,
                "min_commission": 5, "slippage_bps": 5, "position_size": .3},
}
EXPECTED = {
    "snapshot_sha256": "0afe8b3aff2f16a919b4c367ed5743942856e93b2abe17df6578dd2a853b4281",
    "result_sha256": "306799b615aa54232776557d621acaa6c1dd480b2ebd58979f09c678dbbe5648",
    "observations": 130, "trades": 6,
}


def digest(value):
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def complete(store, run):
    store.patch_run(run["id"], status="running")
    execute_job(str(store.root), run["id"])
    finished = store.get_run(run["id"])
    if finished["status"] != "completed":
        raise RuntimeError(f"Offline calculation failed: {finished.get('error')}")
    return finished


def reproduce(output_dir: Path | None = None) -> dict:
    """Use fresh temporary stores only; optionally retain public evidence artifacts."""
    if output_dir is not None:
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        if not output_dir.is_dir() or any(output_dir.iterdir()):
            raise ValueError("Output directory must be empty; existing files are never overwritten")
    with tempfile.TemporaryDirectory(prefix="quantsandbox-reproduce-") as temporary:
        root = Path(temporary)
        store = Store(root / "baseline")
        center = DataCenter(root=store.root)
        research = ResearchService(store)
        evidence = EvidenceService(research, center)
        frame = synthetic_frame("600036")
        frame = frame.loc[frame.date.between("2023-10-02", "2024-06-28")].reset_index(drop=True)
        # Test fixture controls, not inferred exchange rules or real market data.
        frame["is_suspended"] = False
        frame.loc[frame.date.eq("2024-03-04"), "is_suspended"] = True
        frame["limit_up"] = None
        frame["limit_down"] = None
        manifest = center.snapshot("600036", frame, "demo")
        config = RunConfig.model_validate(CONFIG).model_dump(mode="json")
        baseline = complete(store, research.schedule(config, manifest=[manifest]))
        package = evidence.export_run(baseline["id"])
        raw = canonical_json(package)
        # A separate store proves replay uses the exported rows, not baseline files.
        replay_store = Store(root / "replay")
        replay_center = DataCenter(root=replay_store.root)
        replay_research = ResearchService(replay_store)
        imported = EvidenceService(replay_research, replay_center).import_run(json.loads(raw))
        replay = complete(replay_store, imported)
        verification = replay["result"]["replay_verification"]
        if replay["manifest"][0]["sha256"] != manifest["sha256"]:
            raise RuntimeError("Replayed execution-control snapshot differs")
        if replay["result"]["decisions"] != baseline["result"]["decisions"]:
            raise RuntimeError("Replayed decision evidence differs")
        if not verification["matched"]:
            raise RuntimeError("Evidence replay differs from the baseline")
        result = baseline["result"]
        stable = {
            "snapshot_sha256": manifest["sha256"],
            "result_sha256": digest({key: result[key] for key in ("metrics", "series", "trades", "decisions")}),
            "observations": len(result["series"]), "trades": len(result["trades"]),
        }
        if stable != EXPECTED:
            raise RuntimeError(f"Canonical reference differs: {canonical_json(stable)}")
        report = {
            "format": "quantsandbox-reproducibility-v1", "synthetic": True,
            "demo_version": DEMO_VERSION, "config": config,
            **stable, "execution_fields": manifest["execution_fields"],
            "metrics": result["metrics"], "engine": result["engine"],
            "replay": {key: verification[key] for key in ("matched", "compared_fields", "different_fields")},
            "artifacts": ["evidence.json", "report.json"] if output_dir is not None else [],
        }
        if output_dir is not None:
            # Exclusive creation also prevents overwrites after the empty-directory check.
            with (output_dir / "evidence.json").open("x", encoding="utf-8") as stream:
                stream.write(raw + "\n")
            with (output_dir / "report.json").open("x", encoding="utf-8") as stream:
                stream.write(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
        return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", "--output", type=Path, help="New or empty directory for public evidence and report")
    args = parser.parse_args(argv)
    try:
        report = reproduce(args.output_dir)
    except (ValueError, OSError, RuntimeError) as error:
        parser.exit(1, f"Reproducibility check failed: {error}\n")
    print(json.dumps(report, ensure_ascii=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
