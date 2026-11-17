from fastapi.testclient import TestClient
from backend.main import create_app
from backend.workbench import store


def test_intraday_cache_and_errors_do_not_break_public_dataset_catalog(tmp_path):
    token = store._scope_data.set(tmp_path / 'workbench')
    try:
        error = store.snapshot('etf:intraday:errors_quote:510300', {'errors': ['offline']})
        quote = store.snapshot('etf:intraday:quote:510300', {'rows': [{'last': 4.1}]})
        bars = store.snapshot('etf:intraday:bars:510300', {'rows': [{'time': '2026-11-06T15:00:00+08:00', 'amount_cny': 10}]})
        public = store.snapshot('import:example', {'kind': 'import', 'symbol': 'example', 'unit': 'CNY',
            'source': 'synthetic test', 'source_url': '', 'method': 'test only',
            'rows': [{'date': '2026-11-05', 'value': 1}]})
        assert [s['id'] for s in store.catalog()] == [public['id']]
        # Hidden cache remains retrievable as evidence by exact snapshot ID.
        assert store.get_snapshot(error['id'])['errors'] == ['offline']
        assert store.get_snapshot(quote['id'])['rows'][0]['last'] == 4.1
        assert store.get_snapshot(bars['id'])['rows'][0]['amount_cny'] == 10
    finally:
        store._scope_data.reset(token)
    with TestClient(create_app(tmp_path, run_jobs=False)) as client:
        response = client.get('/api/research/status')
        assert response.status_code == 200
        assert len(response.json()['datasets']) == 1
        assert len(response.json()['series']) == 1
