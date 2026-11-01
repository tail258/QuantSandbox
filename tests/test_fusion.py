"""Research -> fixed snapshots -> replay -> project links, without market access."""
import copy

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from backend.main import create_app
from backend.services.runner import execute_job
from backend.workbench import store


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(store, 'DATA', tmp_path / 'workbench')
    with TestClient(create_app(tmp_path, run_jobs=False)) as client:
        yield client


def quote_snapshot(**changes):
    dates = pd.bdate_range('2023-01-02', '2024-06-28').strftime('%Y-%m-%d').tolist()
    rows = [{'date': day, 'open': 20 + i / 100, 'high': 21 + i / 100,
             'low': 19 + i / 100, 'close': 20.5 + i / 100, 'volume': 100000 + i}
            for i, day in enumerate(dates)]
    payload = {'kind': 'quotes', 'symbol': '600519', 'source': 'test upstream',
               'source_url': 'https://example.org/prices', 'unit': '元 / 股',
               'method': '不复权日线；成交量统一为股',
               'request': {'kind': 'quotes', 'symbol': '600519', 'adjust': '3',
                           'start': '2023-01-01', 'end': '2024-06-30'}, 'rows': rows}
    payload.update(changes)
    return store.snapshot('quotes:600519', payload)


def bridge_body(snapshot_id, **changes):
    body = {'snapshot_ids': [snapshot_id], 'config': {'name': '固定行情研究', 'source': 'snapshot',
            'tickers': ['600519'], 'start_date': '2024-01-01', 'end_date': '2024-06-30'}}
    body.update(changes)
    return body


def complete(client, run):
    client.app.state.store.patch_run(run['id'], status='running')
    execute_job(str(client.app.state.store.root), run['id'])
    result = client.get('/api/runs/' + run['id']).json()
    assert result['status'] == 'completed', result.get('error')
    return result


def test_bridge_replay_and_origin_survive_source_change(client, monkeypatch):
    original = quote_snapshot()
    project = client.post('/api/projects', json={'name': '企业观察', 'symbols': ['600519'], 'question': '价格规则是否稳健'}).json()
    def no_network(*args, **kwargs):
        raise AssertionError('fixed snapshot must never download')
    monkeypatch.setattr('backend.core.data_center.download_prices', no_network)
    response = client.post('/api/bridge/backtests', json=bridge_body(original['id'], project_id=project['id']))
    assert response.status_code == 202, response.text
    run = complete(client, response.json())
    origin = run['manifest'][0]['origin']
    assert origin['snapshot_id'] == original['id'] and origin['source'] == 'test upstream'
    assert origin['price_basis'] == 'raw_unadjusted' and origin['volume_unit'] == 'shares'
    assert run['result']['data_provenance']['origins'] == [origin]
    # A newer upstream version does not replace a running or archived input.
    revised = copy.deepcopy(original['rows']); revised[-1]['close'] += .1
    quote_snapshot(rows=revised)
    exported = client.get('/api/runs/' + run['id'] + '/export')
    assert exported.status_code == 200
    replay_response = client.post('/api/import', content=exported.content, headers={'Content-Type': 'application/json'})
    assert replay_response.status_code == 202, replay_response.text
    replay = complete(client, replay_response.json())
    assert replay['result']['replay_verification']['matched'] is True
    assert replay['manifest'][0]['origin'] == origin
    linked = client.get('/api/projects/' + project['id']).json()
    assert linked['links'][0]['run_id'] == run['id']


def test_bridge_rejects_ambiguous_prices_and_missing_inputs(client):
    raw = quote_snapshot()
    adjusted = quote_snapshot(request={**raw['request'], 'adjust': '2'})
    assert client.post('/api/bridge/backtests', json=bridge_body(adjusted['id'])).status_code == 422
    unknown = quote_snapshot(method='daily prices')
    assert client.post('/api/bridge/backtests', json=bridge_body(unknown['id'])).status_code == 422
    assert client.post('/api/bridge/backtests', json=bridge_body('../secret')).status_code == 422
    assert client.post('/api/bridge/backtests', json=bridge_body('a' * 20)).status_code == 404
    body = bridge_body(raw['id']); body['config']['end_date'] = '2024-07-01'
    assert client.post('/api/bridge/backtests', json=body).status_code == 422
    assert client.post('/api/runs', json=bridge_body(raw['id'])['config']).status_code == 422
    assert client.get('/api/runs').json()['runs'] == []


def test_projects_validate_and_link_both_record_types(client):
    assert client.post('/api/projects', json={'name': 'x', 'symbols': ['../secret']}).status_code == 422
    project = client.post('/api/projects', json={'name': '公司观察', 'symbols': ['600519']}).json()
    research = store.save_run({'kind': 'statistics', 'inputs': [], 'params': {}, 'result': {}})
    link = client.post('/api/projects/' + project['id'] + '/links', json={'kind': 'research', 'run_id': research['id']})
    assert link.status_code == 200
    assert client.post('/api/projects/' + project['id'] + '/links', json={'kind': 'simulation', 'run_id': 'missing'}).status_code == 404
    assert client.get('/api/projects').json()['projects'][0]['links'][0]['kind'] == 'research'
    assert client.get('/api/research/status').json()['readonly_market'] is True


def test_app_roots_and_cross_site_are_isolated(tmp_path):
    first, second = tmp_path / 'first', tmp_path / 'second'
    payload = {'text': 'date,value,available_date\n2024-01-01,2,2024-01-02',
               'meta': {'name': '指标', 'symbol': 'test', 'source': 'test', 'unit': '元', 'method': 'fixture'}}
    with TestClient(create_app(first, run_jobs=False)) as a, TestClient(create_app(second, run_jobs=False)) as b:
        assert a.post('/api/research/import', json=payload).status_code == 200
        assert len(a.get('/api/research/status').json()['datasets']) == 1
        assert b.get('/api/research/status').json()['datasets'] == []
        assert a.post('/api/projects', json={'name': 'blocked'}, headers={'Origin': 'https://external.example'}).status_code == 403
        assert a.post('/api/runs', json={'tickers': ['000858']}, headers={'Origin': 'http://localhost.attacker.example:5173'}).status_code == 403
        assert a.post('/api/runs', json={'tickers': ['000858']}, headers={'Sec-Fetch-Site': 'cross-site'}).status_code == 403
        assert a.get('/api/runs').json()['runs'] == []
        assert a.get('/api/projects', headers={'Origin': 'http://localhost:5174'}).status_code == 200
        assert a.get('/api/health', headers={'Host': 'external.example'}).status_code == 400
