"""Provider normalization and snapshot storage work independently of DataCenter."""
import hashlib
import sys
from types import SimpleNamespace

import pandas as pd
import pytest

from backend.core import data_center, data_format
from backend.core.providers import download_prices
from backend.core.snapshots import SnapshotStore


def prices():
    return pd.DataFrame({"date": ["2024-01-02"], "open": [10.], "high": [11.],
                         "low": [9.], "close": [10.5], "volume": [123.]})


def test_provider_normalizes_akshare_lots_without_changing_canonical_shares():
    canonical = prices()
    chinese = canonical.rename(columns={"date": "日期", "open": "开盘", "high": "最高",
                                         "low": "最低", "close": "收盘", "volume": "成交量"})
    actual = download_prices("600036", "2024-01-01", "2024-01-03", lambda *_: chinese)
    assert actual.volume.iloc[0] == 12300
    actual = download_prices("600036", "2024-01-01", "2024-01-03", lambda *_: canonical)
    assert actual.volume.iloc[0] == 123


def test_default_akshare_adapter_keeps_daily_raw_request_contract(monkeypatch):
    calls = []
    def fetch(**kwargs):
        calls.append(kwargs)
        return prices()
    monkeypatch.setitem(sys.modules, "akshare", SimpleNamespace(stock_zh_a_hist=fetch))
    download_prices("600036", "2024-01-01", "2024-01-03")
    assert calls == [{"symbol": "600036", "period": "daily", "start_date": "20240101",
                      "end_date": "20240103", "adjust": "", "timeout": 20}]


def test_provider_errors_keep_explicit_failure_and_original_cause():
    def offline(*_):
        raise ConnectionError("offline")
    with pytest.raises(data_center.DataUnavailable, match="offline") as failure:
        download_prices("600036", "2024-01-01", "2024-01-03", offline)
    assert isinstance(failure.value.__cause__, ConnectionError)


def test_snapshot_store_roundtrips_with_same_hash_and_manifest_contract(tmp_path):
    store = SnapshotStore(tmp_path)
    frame = data_format.validate_frame(prices())
    manifest = store.snapshot("600036", frame, "akshare", demo_version="demo", demo_notice="notice")
    pd.testing.assert_frame_equal(store.load_snapshot(manifest), frame)
    assert manifest["sha256"] == data_center.frame_hash(frame)
    assert manifest["file_sha256"] == hashlib.sha256((tmp_path / (manifest["sha256"] + ".parquet")).read_bytes()).hexdigest()
    assert manifest["price_basis"] == "raw_unadjusted" and manifest["version"] == "akshare-raw-v1"
    (tmp_path / "broken.json").write_text("not json", encoding="utf-8")
    assert store.manifests() == [manifest]
    with pytest.raises(data_center.DataUnavailable, match="无效"):
        store.load_snapshot({"sha256": "../invalid"})


def test_old_serialization_exports_are_shared_contract():
    for name in ("DataUnavailable", "canonical_json", "frame_records", "frame_hash", "validate_frame", "atomic_json", "atomic_parquet", "utc_now"):
        assert getattr(data_center, name) is getattr(data_format, name)
