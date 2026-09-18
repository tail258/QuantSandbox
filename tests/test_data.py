import hashlib
import json

import pandas as pd
import pytest

from backend.core.data_center import DataCenter, DataUnavailable, frame_hash, synthetic_frame


def fake_prices(start, end):
    dates = pd.bdate_range(start, end)
    return pd.DataFrame({"date": dates, "open": 10.0, "high": 11.0, "low": 9.0,
                         "close": 10.5, "volume": 50000})


def test_disjoint_request_fills_gap_and_reuses_complete_cache(tmp_path):
    requests = []

    def provider(ticker, start, end):
        requests.append((start, end))
        return fake_prices(start, end)

    center = DataCenter(root=tmp_path, provider=provider)
    first = center.fetch_stock_data("600036", "2024-01-01", "2024-01-31")
    march = center.fetch_stock_data("600036", "2024-03-01", "2024-03-31")
    february = center.fetch_stock_data("600036", "2024-02-01", "2024-02-29")
    assert len(first) == 23 and len(march) == 21 and len(february) == 21
    assert requests == [("2024-01-01", "2024-01-31"), ("2024-02-01", "2024-03-31")]
    center.fetch_stock_data("600036", "2023-11-01", "2023-11-30")
    december = center.fetch_stock_data("600036", "2023-12-01", "2023-12-31")
    assert len(december) == 21
    assert requests[-1] == ("2023-11-01", "2023-12-31")
    assert len(requests) == 3


def test_failed_expansion_preserves_existing_cache_and_never_returns_demo(tmp_path):
    def provider(ticker, start, end):
        if start >= "2024-02-01":
            raise ConnectionError("offline")
        return fake_prices(start, end)

    center = DataCenter(root=tmp_path, provider=provider)
    before = center.fetch_stock_data("600036", "2024-01-01", "2024-01-31")
    with pytest.raises(DataUnavailable, match="offline"):
        center.fetch_stock_data("600036", "2024-02-01", "2024-02-29")
    after = center.fetch_stock_data("600036", "2024-01-01", "2024-01-31")
    pd.testing.assert_frame_equal(before, after)


def test_demo_prefix_is_independent_of_requested_end_and_snapshots_detect_tampering(tmp_path):
    center = DataCenter(root=tmp_path)
    short = center.fetch_stock_data("000858", "2024-01-01", "2024-02-29", source="demo")
    long = center.fetch_stock_data("000858", "2024-01-01", "2025-12-31", source="demo")
    pd.testing.assert_frame_equal(short, long.iloc[:len(short)].reset_index(drop=True))
    manifest = center.snapshot("000858", short, "demo")
    assert manifest["synthetic"] is True
    assert "合成" in manifest["notice"]
    assert frame_hash(center.load_snapshot(manifest)) == manifest["sha256"]
    path = tmp_path / "snapshots" / f"{manifest['sha256']}.parquet"
    assert hashlib.sha256(path.read_bytes()).hexdigest() == manifest["file_sha256"]
    corrupted = short.copy()
    corrupted.loc[0, ["open", "close", "high", "low"]] *= 2
    corrupted.to_parquet(path, index=False)
    with pytest.raises(DataUnavailable, match="SHA256"):
        center.load_snapshot(manifest)


def test_corrupted_cache_is_rejected_not_silently_used(tmp_path):
    center = DataCenter(root=tmp_path, provider=lambda _, start, end: fake_prices(start, end))
    center.fetch_stock_data("600036", "2024-01-01", "2024-01-31")
    manifest = json.loads((tmp_path / "cache" / "akshare" / "600036.json").read_text(encoding="utf-8"))
    path = tmp_path / "cache" / "akshare" / manifest["file"]
    path.write_bytes(b"corrupt")
    with pytest.raises(DataUnavailable, match="校验"):
        center.fetch_stock_data("600036", "2024-01-01", "2024-01-31")


def test_demo_ohlcv_valid_and_unknown_tickers_rejected():
    frame = synthetic_frame("000858")
    assert len(frame) > 1900
    assert frame.date.is_monotonic_increasing and frame.date.is_unique
    assert (frame.high >= frame[["open", "close"]].max(axis=1)).all()
    assert (frame.low <= frame[["open", "close"]].min(axis=1)).all()
    with pytest.raises(DataUnavailable):
        synthetic_frame("999999")
