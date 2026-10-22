"""Canonical market-frame validation, hashing and atomic persistence primitives."""
from __future__ import annotations
import hashlib
import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
import numpy as np
import pandas as pd

COLUMNS = ["date", "open", "high", "low", "close", "volume"]


class DataUnavailable(RuntimeError):
    """An explicit data-source failure, never silently replaced by demo data."""


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def canonical_json(value) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def frame_records(frame: pd.DataFrame) -> list[dict]:
    output = frame[COLUMNS].copy()
    output["date"] = pd.to_datetime(output["date"]).dt.strftime("%Y-%m-%d")
    # Python's float repr preserves the exact round-trip value; pandas.to_json
    # truncates precision and can change an execution at a lot-size boundary.
    return output.to_dict(orient="records")


def frame_hash(frame: pd.DataFrame) -> str:
    return hashlib.sha256(canonical_json(frame_records(frame)).encode("utf-8")).hexdigest()


def atomic_json(path: Path, content) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp = tempfile.mkstemp(prefix=f".{path.stem}-", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(canonical_json(content))
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp, path)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)


def atomic_parquet(path: Path, frame: pd.DataFrame) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp = tempfile.mkstemp(prefix=f".{path.stem}-", suffix=".parquet", dir=path.parent)
    os.close(fd)
    try:
        frame.to_parquet(temp, index=False)
        os.replace(temp, path)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)


def validate_frame(frame: pd.DataFrame, allow_empty: bool = False) -> pd.DataFrame:
    if frame.empty:
        if allow_empty:
            return pd.DataFrame(columns=COLUMNS)
        raise DataUnavailable("请求范围内没有行情，请检查上市日期、停牌情况或数据源。")
    missing = set(COLUMNS) - set(frame.columns)
    if missing:
        raise DataUnavailable(f"行情字段缺失：{', '.join(sorted(missing))}")
    result = frame[COLUMNS].copy()
    result["date"] = pd.to_datetime(result["date"], errors="raise").dt.normalize()
    for column in COLUMNS[1:]:
        result[column] = pd.to_numeric(result[column], errors="raise")
    values = result[COLUMNS[1:]].to_numpy(dtype=float)
    if not np.isfinite(values).all():
        raise DataUnavailable("行情包含缺失值或非有限数值")
    if (result[["open", "high", "low", "close"]] <= 0).any().any() or (result["volume"] < 0).any():
        raise DataUnavailable("行情价格或成交量不合法")
    if ((result["high"] < result[["open", "close", "low"]].max(axis=1)) |
            (result["low"] > result[["open", "close", "high"]].min(axis=1))).any():
        raise DataUnavailable("行情最高价/最低价与开收盘价不一致")
    return result.sort_values("date").drop_duplicates("date", keep="last").reset_index(drop=True)


