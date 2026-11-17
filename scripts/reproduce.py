"""Offline, isolated baseline -> evidence export -> import/replay release check."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.core.data_center import DEMO_VERSION, canonical_json
from backend.services.strategy_demo import SNAPSHOT_SHA256, recalculate_evidence, result_hash, study_config, write_baseline

EXPECTED = {
    "snapshot_sha256": SNAPSHOT_SHA256,
    "result_sha256": "306799b615aa54232776557d621acaa6c1dd480b2ebd58979f09c678dbbe5648",
    "observations": 130, "trades": 6,
}


def reproduce(output_dir: Path | None = None) -> dict:
    """Use fresh temporary stores only; optionally retain public evidence artifacts."""
    if output_dir is not None:
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        if not output_dir.is_dir() or any(output_dir.iterdir()):
            raise ValueError("Output directory must be empty; existing files are never overwritten")
    with tempfile.TemporaryDirectory(prefix="quantsandbox-reproduce-") as temporary:
        root = Path(temporary)
        config = study_config()
        baseline, raw = write_baseline(root / "baseline", config)
        manifest = baseline["manifest"][0]
        # A separate store proves replay uses the exported rows, not baseline files.
        replay, detailed_verification = recalculate_evidence(root / "replay", raw)
        verification = replay["result"]["replay_verification"]
        if replay["manifest"][0]["sha256"] != manifest["sha256"]:
            raise RuntimeError("Replayed execution-control snapshot differs")
        if not (verification["matched"] and detailed_verification["matched"]):
            raise RuntimeError("Evidence replay differs from the baseline")
        result = baseline["result"]
        stable = {
            "snapshot_sha256": manifest["sha256"],
            "result_sha256": result_hash(result),
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
