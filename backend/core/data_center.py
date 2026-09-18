"""Validated, versioned local market data. Demo prices are always synthetic."""
from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEMO_START = "2019-01-01"
DEMO_END = "2026-09-18"
DEMO_VERSION = "synthetic-regimes-v2"
DEMO_NOTICE = "合成演示数据 · 非真实市场价格，不可用于投资结论。日期仅按工作日生成，未模拟交易所节假日。"
UNIVERSE = [
    {"ticker": "000858", "name": "五粮液", "sector": "消费", "demo_name": "消费样例 A"},
    {"ticker": "600519", "name": "贵州茅台", "sector": "消费", "demo_name": "消费样例"},
    {"ticker": "000001", "name": "平安银行", "sector": "金融", "demo_name": "金融样例"},
    {"ticker": "300750", "name": "宁德时代", "sector": "新能源", "demo_name": "新能源样例"},
    {"ticker": "600036", "name": "招商银行", "sector": "金融", "demo_name": "金融样例 B"},
    {"ticker": "601318", "name": "中国平安", "sector": "保险", "demo_name": "保险样例"},
]
COLUMNS = ["date", "open", "high", "low", "close", "volume"]


class DataUnavailable(RuntimeError):
    """An explicit data-source failure, never silently replaced by demo data."""


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def data_root() -> Path:
    return Path(os.environ.get("QUANT_SANDBOX_DATA_DIR", str(PROJECT_ROOT / "data"))).resolve()


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


def normalize_ticker(symbol: str) -> str:
    symbol = symbol.lower().removeprefix("sh").removeprefix("sz")
    if not re.fullmatch(r"\d{6}", symbol):
        raise ValueError("股票代码必须为六位数字")
    return symbol


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


def synthetic_frame(ticker: str) -> pd.DataFrame:
    """Generate from a fixed origin so changing a query cannot change past prices."""
    ticker = normalize_ticker(ticker)
    if ticker not in {item["ticker"] for item in UNIVERSE}:
        raise DataUnavailable("该代码没有演示数据，请选用示例股票池或切换 AKShare。")
    seed = int(hashlib.sha256(f"{DEMO_VERSION}:{ticker}".encode()).hexdigest()[:8], 16)
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range(DEMO_START, DEMO_END)
    time = np.arange(len(dates), dtype=float)
    index = [item["ticker"] for item in UNIVERSE].index(ticker)
    base = [132.0, 1180.0, 14.5, 138.0, 34.0, 47.0][index]
    drift = .00019 + .00135 * np.sin(time / 68 + index * .8) + .0007 * np.cos(time / 151)
    shock = np.where((time % 430 > 310) & (time % 430 < 342), -.0065, 0)
    returns = np.clip(drift + shock + rng.normal(0, .010 + index * .0018, len(dates)), -.085, .085)
    close = base * np.exp(np.cumsum(returns))
    opening = np.r_[base, close[:-1]] * np.exp(rng.normal(0, .003, len(dates)))
    spread = rng.uniform(.0015, .013, len(dates))
    high = np.maximum(opening, close) * (1 + spread)
    low = np.minimum(opening, close) * (1 - spread)
    volume = rng.lognormal(16.7 + index * .13, .35, len(dates)).astype(int)
    return validate_frame(pd.DataFrame({"date": dates, "open": np.round(opening, 2),
                                       "high": np.round(high, 2), "low": np.round(low, 2),
                                       "close": np.round(close, 2), "volume": volume}))


class DataCenter:
    def __init__(self, cache_dir: str | Path | None = None,
                 provider: Callable | None = None, root: str | Path | None = None):
        self.root = Path(root).resolve() if root else data_root()
        self.cache_dir = Path(cache_dir).resolve() if cache_dir else self.root / "cache"
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.snapshots = self.root / "snapshots"
        self.snapshots.mkdir(parents=True, exist_ok=True)
        self.provider = provider

    def _download(self, ticker: str, start: str, end: str) -> pd.DataFrame:
        try:
            if self.provider:
                raw = self.provider(ticker, start, end)
            else:
                try:
                    import akshare as ak
                except ImportError as exc:
                    raise DataUnavailable("AKShare 未安装。请安装 requirements-market.txt 后重新请求真实行情。") from exc
                raw = ak.stock_zh_a_hist(symbol=ticker, period="daily", start_date=start.replace("-", ""),
                                         end_date=end.replace("-", ""), adjust="", timeout=20)
            renamed = raw.rename(columns={"日期": "date", "开盘": "open", "最高": "high",
                                          "最低": "low", "收盘": "close", "成交量": "volume"})
            if "成交量" in raw.columns:
                renamed["volume"] = pd.to_numeric(renamed["volume"]) * 100
            return validate_frame(renamed, allow_empty=True)
        except DataUnavailable:
            raise
        except Exception as exc:
            raise DataUnavailable(f"AKShare 获取 {ticker} 失败：{type(exc).__name__}: {exc}") from exc

    def fetch_stock_data(self, symbol: str, start_date="20240101", end_date="20251231",
                         force_update=False, source="akshare") -> pd.DataFrame:
        ticker = normalize_ticker(symbol)
        start, end = (pd.Timestamp(value).normalize() for value in [start_date, end_date])
        if start > end:
            raise ValueError("开始日期不能晚于结束日期")
        if source not in {"demo", "akshare"}:
            raise ValueError("未知行情来源")
        if source == "demo":
            if start < pd.Timestamp(DEMO_START) or end > pd.Timestamp(DEMO_END):
                raise DataUnavailable(f"合成演示数据支持 {DEMO_START} 至 {DEMO_END}")
            frame = synthetic_frame(ticker)
            return frame.loc[frame.date.between(start, end)].reset_index(drop=True)

        directory = self.cache_dir / source
        directory.mkdir(exist_ok=True)
        manifest_path = directory / f"{ticker}.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists() else None
        cached = pd.DataFrame(columns=COLUMNS)
        if manifest and not force_update:
            cached_path = directory / manifest["file"]
            if cached_path.exists():
                if hashlib.sha256(cached_path.read_bytes()).hexdigest() != manifest["file_sha256"]:
                    raise DataUnavailable("本地缓存校验失败，请强制更新该数据集")
                cached = validate_frame(pd.read_parquet(cached_path), allow_empty=True)
            else:
                manifest = None
        ranges = [(start, end)]
        if manifest and not force_update:
            covered_start, covered_end = pd.Timestamp(manifest["coverage_start"]), pd.Timestamp(manifest["coverage_end"])
            ranges = []
            if start < covered_start:
                ranges.append((start, covered_start - pd.Timedelta(days=1)))
            if end > covered_end:
                ranges.append((covered_end + pd.Timedelta(days=1), end))
        else:
            cached = pd.DataFrame(columns=COLUMNS)
        if ranges:
            pieces = [cached] if not cached.empty else []
            for range_start, range_end in ranges:
                downloaded = self._download(ticker, range_start.strftime("%Y-%m-%d"), range_end.strftime("%Y-%m-%d"))
                if not downloaded.empty:
                    pieces.append(downloaded)
            if not pieces:
                raise DataUnavailable(f"{ticker} 在请求时间内没有行情；未使用演示数据替代")
            cached = validate_frame(pd.concat(pieces, ignore_index=True))
            digest = frame_hash(cached)
            destination = directory / f"{ticker}-{digest}.parquet"
            atomic_parquet(destination, cached)
            coverage_start = min(start, pd.Timestamp(manifest["coverage_start"])) if manifest and not force_update else start
            coverage_end = max(end, pd.Timestamp(manifest["coverage_end"])) if manifest and not force_update else end
            manifest = {"ticker": ticker, "source": source, "synthetic": False, "file": destination.name,
                        "sha256": digest, "file_sha256": hashlib.sha256(destination.read_bytes()).hexdigest(),
                        "coverage_start": str(coverage_start.date()), "coverage_end": str(coverage_end.date()),
                        "first_bar": str(cached.date.min().date()), "last_bar": str(cached.date.max().date()),
                        "rows": len(cached), "updated_at": utc_now(), "price_basis": "raw_unadjusted",
                        "volume_unit": "shares", "notice": "未复权价格；当前模型未记账分红送转。上游历史数据可能修订。"}
            atomic_json(manifest_path, manifest)
        selected = cached.loc[cached.date.between(start, end)].reset_index(drop=True)
        return validate_frame(selected)

    def snapshot(self, ticker: str, frame: pd.DataFrame, source: str) -> dict:
        frame = validate_frame(frame)
        digest = frame_hash(frame)
        file = self.snapshots / f"{digest}.parquet"
        if not file.exists():
            atomic_parquet(file, frame)
        manifest = {"ticker": ticker, "source": source, "synthetic": source == "demo", "sha256": digest,
                    "file_sha256": hashlib.sha256(file.read_bytes()).hexdigest(), "rows": len(frame),
                    "start_date": str(frame.date.min().date()), "end_date": str(frame.date.max().date()),
                    "created_at": utc_now(), "volume_unit": "shares",
                    "version": DEMO_VERSION if source == "demo" else "akshare-raw-v1",
                    "price_basis": "synthetic" if source == "demo" else "raw_unadjusted",
                    "notice": DEMO_NOTICE if source == "demo" else "未复权价格；当前模型未记账分红送转。"}
        atomic_json(self.snapshots / f"{digest}.json", manifest)
        return manifest

    def load_snapshot(self, manifest: dict) -> pd.DataFrame:
        digest = manifest.get("sha256", "")
        if not re.fullmatch(r"[a-f0-9]{64}", digest):
            raise DataUnavailable("数据版本指纹无效")
        file = self.snapshots / f"{digest}.parquet"
        if not file.exists():
            raise DataUnavailable("研究数据快照缺失，请导入完整研究证据包")
        frame = validate_frame(pd.read_parquet(file))
        if frame_hash(frame) != digest:
            raise DataUnavailable("研究数据快照 SHA256 校验失败")
        return frame

    def status(self) -> dict:
        datasets = []
        for path in self.snapshots.glob("*.json"):
            try:
                datasets.append(json.loads(path.read_text(encoding="utf-8")))
            except (ValueError, OSError):
                continue
        return {"datasets": sorted(datasets, key=lambda row: row["created_at"], reverse=True),
                "sources": [{"id": "demo", "name": "合成演示行情", "available": True, "synthetic": True,
                             "notice": DEMO_NOTICE, "start_date": DEMO_START, "end_date": DEMO_END},
                            {"id": "akshare", "name": "AKShare · 东方财富", "available": importlib.util.find_spec("akshare") is not None,
                             "synthetic": False, "notice": "外部行情服务；失败时明确报错，不自动替换为演示数据。"}],
                "snapshot_count": len(datasets)}
