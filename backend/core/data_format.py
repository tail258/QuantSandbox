"""Canonical market-frame validation, hashing and atomic persistence primitives."""
from __future__ import annotations
import hashlib
import json
import os
import tempfile
from datetime import date, datetime, timezone
from pathlib import Path
import numpy as np
import pandas as pd

COLUMNS = ["date", "open", "high", "low", "close", "volume"]
EXECUTION_COLUMNS = ["is_suspended", "limit_up", "limit_down"]
DIVIDEND_COLUMNS = ["cash_dividend_per_share", "dividend_ex_date", "dividend_payment_date"]


def market_columns(frame: pd.DataFrame) -> list[str]:
    return COLUMNS + [column for column in EXECUTION_COLUMNS + DIVIDEND_COLUMNS if column in frame.columns]


class DataUnavailable(RuntimeError):
    """An explicit data-source failure, never silently replaced by demo data."""


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def canonical_json(value) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def frame_records(frame: pd.DataFrame) -> list[dict]:
    output = frame[market_columns(frame)].copy()
    output["date"] = pd.to_datetime(output["date"]).dt.strftime("%Y-%m-%d")
    # Python's float repr preserves the exact round-trip value; pandas.to_json
    # truncates precision and can change an execution at a lot-size boundary.
    # Optional unknown controls stay null; legacy OHLCV-only hashes stay identical.
    return output.astype(object).where(pd.notna(output), None).to_dict(orient="records")


def frame_hash(frame: pd.DataFrame) -> str:
    return hashlib.sha256(canonical_json(frame_records(frame)).encode("utf-8")).hexdigest()


def validate_dividend_rows(frame: pd.DataFrame) -> None:
    """Normalize optional cash-distribution data on the stock's record-date bar."""
    present = [column for column in DIVIDEND_COLUMNS if column in frame]
    if not present:
        return
    if present != DIVIDEND_COLUMNS:
        raise DataUnavailable("现金分红字段须同时包含每股税前红利、除息日和派息日")
    fields = frame[DIVIDEND_COLUMNS]
    missing = fields.isna()
    events = fields.loc[~missing.all(axis=1)]
    if missing.loc[events.index].any(axis=None):
        raise DataUnavailable("同一股权登记日的现金分红字段须全部填写或全部留空")
    record_dates = frame.loc[events.index, "date"]
    if frame.loc[frame.date.isin(record_dates), "date"].duplicated().any():
        raise DataUnavailable("行情包含重复股权登记日期")

    amounts = events["cash_dividend_per_share"]
    numeric_amounts = pd.to_numeric(amounts, errors="coerce").astype(float)
    if (amounts.map(lambda value: isinstance(value, (bool, np.bool_))).any()
            or not np.isfinite(numeric_amounts).all() or not numeric_amounts.gt(0).all()):
        raise DataUnavailable("每股税前现金红利须为有限正数")
    frame["cash_dividend_per_share"] = numeric_amounts.reindex(frame.index)
    for index, row in events.iterrows():
        ex_text, payment_text = row["dividend_ex_date"], row["dividend_payment_date"]
        try:
            ex = date.fromisoformat(ex_text)
            payment = date.fromisoformat(payment_text)
            record = pd.Timestamp(frame.at[index, "date"]).date()
        except (TypeError, ValueError) as exc:
            raise DataUnavailable("分红的除息日和派息日须使用 YYYY-MM-DD 格式") from exc
        if pd.isna(record) or ex_text != ex.isoformat() or payment_text != payment.isoformat():
            raise DataUnavailable("分红的除息日和派息日须使用 YYYY-MM-DD 格式")
        if not record < ex <= payment:
            raise DataUnavailable("分红日期须满足股权登记日早于除息日，派息日不早于除息日")
    for column in DIVIDEND_COLUMNS[1:]:
        frame[column] = frame[column].astype("string")


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
    result = frame[market_columns(frame)].copy()
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
    for column in ("limit_up", "limit_down"):
        if column in result:
            result[column] = pd.to_numeric(result[column], errors="raise")
            known = result[column].dropna()
            if not np.isfinite(known.to_numpy(dtype=float)).all() or (known <= 0).any():
                raise DataUnavailable(f"{column} 须为正的有限价格或 null")
    if "is_suspended" in result:
        def suspension(value):
            if pd.isna(value):
                return None
            if isinstance(value, (bool, np.bool_)) or isinstance(value, (int, float, np.number)) and value in (0, 1):
                return bool(value)
            raise DataUnavailable("is_suspended 须为布尔值、0、1 或 null")
        result["is_suspended"] = result["is_suspended"].map(suspension).astype(object)
    if "limit_up" in result and "limit_down" in result:
        both = result[["limit_up", "limit_down"]].dropna()
        if (both.limit_up < both.limit_down).any():
            raise DataUnavailable("涨停价不能小于跌停价")
    result = result.reset_index(drop=True)
    validate_dividend_rows(result)
    return result.sort_values("date").drop_duplicates("date", keep="last").reset_index(drop=True)


