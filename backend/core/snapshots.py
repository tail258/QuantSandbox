"""Content-addressed, validated market snapshots and their evidence manifests."""
from __future__ import annotations
import hashlib
import json
import re
from pathlib import Path
import pandas as pd
from backend.core.data_format import (DataUnavailable, atomic_json, atomic_parquet,
                                      frame_hash, utc_now, validate_frame)


class SnapshotStore:
    def __init__(self, directory: str | Path):
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)

    def snapshot(self, ticker: str, frame: pd.DataFrame, source: str, *, demo_version: str, demo_notice: str) -> dict:
        frame = validate_frame(frame)
        digest = frame_hash(frame)
        file = self.directory / f"{digest}.parquet"
        if not file.exists():
            atomic_parquet(file, frame)
        manifest = {"ticker": ticker, "source": source, "synthetic": source == "demo", "sha256": digest,
                    "file_sha256": hashlib.sha256(file.read_bytes()).hexdigest(), "rows": len(frame),
                    "start_date": str(frame.date.min().date()), "end_date": str(frame.date.max().date()),
                    "created_at": utc_now(), "volume_unit": "shares",
                    "version": demo_version if source == "demo" else "akshare-raw-v1",
                    "price_basis": "synthetic" if source == "demo" else "raw_unadjusted",
                    "notice": demo_notice if source == "demo" else "未复权价格；当前模型未记账分红送转。"}
        atomic_json(self.directory / f"{digest}.json", manifest)
        return manifest

    def load_snapshot(self, manifest: dict) -> pd.DataFrame:
        digest = manifest.get("sha256", "")
        if not re.fullmatch(r"[a-f0-9]{64}", digest):
            raise DataUnavailable("数据版本指纹无效")
        file = self.directory / f"{digest}.parquet"
        if not file.exists():
            raise DataUnavailable("研究数据快照缺失，请导入完整研究证据包")
        frame = validate_frame(pd.read_parquet(file))
        if frame_hash(frame) != digest:
            raise DataUnavailable("研究数据快照 SHA256 校验失败")
        return frame

    def manifests(self) -> list[dict]:
        datasets = []
        for path in self.directory.glob("*.json"):
            try:
                datasets.append(json.loads(path.read_text(encoding="utf-8")))
            except (ValueError, OSError):
                continue
        return datasets
