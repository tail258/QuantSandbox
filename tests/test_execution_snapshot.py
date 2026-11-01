"""Execution controls must survive acquisition, caching, evidence and replay."""
import copy
import hashlib

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from backend.api.schemas import RunConfig
from backend.core.data_format import DataUnavailable, canonical_json, frame_hash, frame_records, validate_frame
from backend.core.providers import download_prices
from backend.core.snapshots import SnapshotStore
from backend.main import create_app
from backend.services.runner import execute_job


def prices():
    dates = pd.bdate_range('2024-01-02', periods=30)
    close = [10.0 + i / 10 for i in range(len(dates))]
    return pd.DataFrame({'date': dates, 'open': close, 'high': [v + .2 for v in close],
                         'low': [v - .2 for v in close], 'close': close, 'volume': 100000.0})


def complete(client, run):
    client.app.state.store.patch_run(run['id'], status='running')
    execute_job(str(client.app.state.store.root), run['id'])
    result = client.get('/api/runs/' + run['id']).json()
    assert result['status'] == 'completed', result.get('error')
    return result


def test_legacy_ohlcv_fingerprint_is_unchanged():
    frame = validate_frame(prices())
    records = frame.copy()
    records['date'] = records.date.dt.strftime('%Y-%m-%d')
    old_hash = hashlib.sha256(canonical_json(records.to_dict(orient='records')).encode()).hexdigest()
    assert frame_hash(frame) == old_hash


def test_optional_unknowns_and_prices_roundtrip_with_hash(tmp_path):
    frame = prices()
    frame['is_suspended'] = [None, False, True] * 10
    frame['limit_up'] = [None, 20.0, 20.0] * 10
    frame['limit_down'] = [5.0, None, 5.0] * 10
    normalized = download_prices('600036', '2024-01-01', '2024-02-15', lambda *_: frame)
    assert frame_records(normalized)[0]['is_suspended'] is None
    assert frame_records(normalized)[1]['is_suspended'] is False
    store = SnapshotStore(tmp_path)
    manifest = store.snapshot('600036', normalized, 'akshare', demo_version='demo', demo_notice='test')
    restored = store.load_snapshot(manifest)
    assert frame_records(restored) == frame_records(normalized)
    assert manifest['execution_fields'] == ['is_suspended', 'limit_up', 'limit_down']
    assert manifest['data_schema'] == 'market-daily-v2'
    altered = restored.copy()
    altered.loc[0, 'limit_up'] = 19.0
    assert frame_hash(altered) != frame_hash(restored)


@pytest.mark.parametrize('field,value', [('is_suspended', 'False'), ('is_suspended', 2),
                                        ('limit_up', float('inf')), ('limit_down', -1)])
def test_invalid_execution_controls_are_not_silently_accepted(field, value):
    frame = prices()
    frame[field] = value
    with pytest.raises(DataUnavailable):
        validate_frame(frame)


def test_controls_survive_provider_cache_engine_export_and_replay(tmp_path):
    with TestClient(create_app(tmp_path, run_jobs=False)) as client:
        center = client.app.state.center
        frame = prices()
        frame['is_suspended'] = True
        frame['limit_up'], frame['limit_down'] = 20.0, 5.0
        center.provider = lambda *_: frame
        fetched = center.fetch_stock_data('600036', '2024-01-01', '2024-02-15', source='akshare')
        assert fetched.is_suspended.all()
        manifest = center.snapshot('600036', fetched, 'akshare')
        config = RunConfig.model_validate({'source': 'akshare', 'tickers': ['600036'],
                 'start_date': '2024-01-02', 'end_date': '2024-02-15',
                 'strategy': {'name': 'dual_ma', 'parameters': {'fast_period': 2, 'slow_period': 3}}}).model_dump(mode='json')
        baseline_manifest = center.snapshot('600036', prices(), 'akshare')
        baseline = complete(client, client.app.state.research.schedule(config, manifest=[baseline_manifest]))
        blocked = complete(client, client.app.state.research.schedule(config, manifest=[manifest]))
        assert baseline['result']['metrics']['trade_count'] > 0
        assert blocked['result']['metrics']['trade_count'] == 0
        package = client.get('/api/runs/' + blocked['id'] + '/export').json()
        assert all(row['is_suspended'] is True for row in package['datasets'][0]['rows'])
        response = client.post('/api/import', content=canonical_json(package), headers={'Content-Type': 'application/json'})
        assert response.status_code == 202, response.text
        replay = complete(client, response.json())
        assert replay['result']['replay_verification']['matched']
        tampered = copy.deepcopy(package)
        tampered['datasets'][0]['rows'][0]['is_suspended'] = False
        tampered['sha256'] = hashlib.sha256(canonical_json({k: v for k, v in tampered.items() if k != 'sha256'}).encode()).hexdigest()
        assert client.post('/api/import', json=tampered).status_code == 422
