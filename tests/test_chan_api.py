"""Chan evidence replays independently and project lookup never fetches data."""
import hashlib
import json

import pytest
from fastapi.testclient import TestClient

from backend.core.data_format import canonical_json
from backend.main import create_app
from backend.services import chan_research
from backend.workbench import store

DEMO = '/api/chan/demo'
REPLAY = '/api/chan/replay'


@pytest.fixture
def workspace(tmp_path, monkeypatch):
    def unexpected_fetch(*args, **kwargs):
        pytest.fail('Daily Chan analysis must consume the selected frozen snapshot')

    monkeypatch.setattr('backend.workbench.service.retrieve', unexpected_fetch)
    root = tmp_path / 'workspace'
    with TestClient(create_app(root, run_jobs=False)) as client:
        yield client, root


def quotes(root, symbol='000338', *, adjustment='3', source='Fixture source', extra=None):
    sample = chan_research._demo_inputs()[1]
    token = store._scope_data.set(root / 'workbench')
    try:
        return store.snapshot(f'quotes:{symbol}', {
            'kind': 'quotes', 'symbol': symbol, 'request': {'adjust': adjustment},
            'source': source, 'source_url': 'https://www.example.com/quotes',
            'method': '日线；成交量统一为股', 'rows': sample, **(extra or {}),
        })
    finally:
        store._scope_data.reset(token)


def create_project(client, symbol='000338'):
    response = client.post('/api/projects', json={'name': 'Chan test project', 'symbols': [symbol]})
    assert response.status_code == 201, response.text
    return f'/api/projects/{response.json()["id"]}/chan'


def digest(value):
    return hashlib.sha256(canonical_json(value).encode()).hexdigest()


def rehash(package):
    return canonical_json({**package, 'sha256': digest({k: v for k, v in package.items() if k != 'sha256'})})


def test_project_scope_and_original_price_basis_for_all_frozen_versions(workspace, tmp_path):
    client, root = workspace
    base = create_project(client)
    assert client.get(f'{base}/snapshots').json() == {'snapshots': []}
    assert not (root / 'workbench').exists()
    first = quotes(root)
    later = quotes(root, source='Another fixture source')
    adjusted = quotes(root, adjustment='2')
    other = quotes(root, symbol='000962')
    listed = client.get(f'{base}/snapshots')
    assert listed.status_code == 200, listed.text
    assert [row['id'] for row in listed.json()['snapshots']] == [later['id'], first['id']]
    assert client.post(f'{base}/analyze', json={'snapshot_id': other['id']}).status_code == 404
    assert client.post(f'{base}/analyze', json={'snapshot_id': adjusted['id']}).status_code == 422
    assert client.post(f'{base}/analyze', json={'snapshot_id': '../workbench.sqlite'}).status_code == 422

    result = client.post(f'{base}/analyze', json={'snapshot_id': first['id']})
    assert result.status_code == 200, result.text
    payload = result.json()
    assert payload['input']['snapshot_id'] == first['id']
    assert payload['input']['price_basis'] == 'raw_unadjusted'
    assert payload['input']['source_sha256'] == hashlib.sha256(store.encode(first).encode()).hexdigest()
    assert payload['input']['coverage']['missing_session_dates'] is None
    assert payload['input']['coverage']['unknown_suspension_count'] == len(first['rows'])
    assert payload['bars'] == first['rows']
    with TestClient(create_app(tmp_path / 'other_workspace', run_jobs=False)) as isolated:
        replay = isolated.post(REPLAY, content=payload['evidence'])
    assert replay.status_code == 200, replay.text
    assert replay.json() == {**payload, 'verified': True}


def test_project_input_records_suspensions_and_reviewed_gaps(workspace):
    client, root = workspace
    base = create_project(client)
    bars = chan_research._demo_inputs()[1][:16]
    missing, suspended, ex_date = (bars[i]['date'] for i in (3, 6, 9))
    calendar = [bar['date'] for bar in bars]
    bars[6]['is_suspended'] = True
    bars[7]['dividend_ex_date'] = ex_date
    bars.pop(3)
    frozen = quotes(root, extra={'rows': bars, 'execution_history': {'calendar': {'sessions': calendar}}})
    response = client.post(f'{base}/analyze', json={'snapshot_id': frozen['id']})
    assert response.status_code == 200, response.text
    data = response.json()
    assert data['input']['coverage'] == {
        'observed_rows': 15, 'excluded_suspension_dates': [suspended], 'missing_session_dates': [missing],
        'unknown_suspension_count': 14, 'cash_dividend_ex_dates': [ex_date], 'calendar_verified': True,
    }
    assert [frame['date'] for frame in data['result']['frames']] == [d for d in calendar if d not in (missing, suspended)]


def test_demo_displays_all_layers_and_replays_in_another_empty_workspace(workspace, tmp_path):
    client, root = workspace
    response = client.post(DEMO)
    assert response.status_code == 200, response.text
    data = response.json()
    assert data['input']['symbol'] == 'CHAN-DEMO'
    assert data['input']['mode'] == 'synthetic'
    for layer in ('merged_bars', 'fractals', 'strokes', 'segments', 'centers'):
        assert any(row['status'] == 'confirmed' for row in data['result']['structures'][layer]), layer
    assert not (root / 'workbench').exists()

    other_root = tmp_path / 'empty'
    with TestClient(create_app(other_root, run_jobs=False)) as other:
        replay = other.post(REPLAY, content=data['evidence'], headers={'content-type': 'application/json'})
    assert replay.status_code == 200, replay.text
    assert replay.json() == {**data, 'verified': True}
    assert not (other_root / 'workbench').exists()


def test_raw_evidence_detects_tampering_version_and_result_mismatch(workspace):
    client, _ = workspace
    raw = client.post(DEMO).json()['evidence']
    package = json.loads(raw)
    assert client.post(REPLAY, content='{"sha256":""}').status_code == 422
    assert client.post(REPLAY, content='{"duplicate":1,"duplicate":2}').status_code == 422
    assert client.post(REPLAY, content=b' ' * (chan_research.MAX_EVIDENCE_BYTES + 1)).status_code == 413
    altered = {**package, 'algorithm': 'unknown-version'}
    assert client.post(REPLAY, content=rehash(altered)).status_code == 422
    package['result_sha256'] = '0' * 64
    assert client.post(REPLAY, content=canonical_json(package)).status_code == 422
    assert client.post(REPLAY, content=rehash(package)).status_code == 409
    package['bars'][0]['volume'] += 1
    package['input']['sha256'] = digest(package['bars'])
    assert client.post(REPLAY, content=rehash(package)).status_code == 422
