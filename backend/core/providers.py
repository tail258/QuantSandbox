"""Replaceable daily market-data acquisition and upstream unit normalization."""
from __future__ import annotations
from typing import Protocol
import pandas as pd
from backend.core.data_format import DataUnavailable, validate_frame


class MarketDataProvider(Protocol):
    """Injected callables return daily OHLCV, using canonical or AKShare columns."""
    def __call__(self, ticker: str, start: str, end: str) -> pd.DataFrame: ...


def download_prices(ticker: str, start: str, end: str, provider: MarketDataProvider | None = None) -> pd.DataFrame:
    try:
        if provider:
            raw = provider(ticker, start, end)
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

