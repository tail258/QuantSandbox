import json
import zipfile
from io import BytesIO

from fastapi.testclient import TestClient
from backend.main import create_app
from backend.workbench import store, us_equities

CSV = 'date,open,high,low,close,volume\n2025-01-02,100,103,99,102,1000\n'


def test_us_project_archive_export_and_market_boundary(tmp_path, monkeypatch):
    monkeypatch.setattr(store, 'ROOT', tmp_path)
    with TestClient(create_app(tmp_path, run_jobs=False)) as client:
        assert client.get('/api/research/us/company/MCD').json()['snapshot_ids'] == []
        assert client.get('/api/research/us/company/UNKNOWN').status_code == 400
        project = client.post('/api/projects', json={'name': 'MCD research', 'symbols': ['US:MCD', '601118']}).json()
        assert project['symbols'] == ['US:MCD', '601118']
        imported = client.post('/api/research/us/company/MCD/prices', json={'text': CSV, 'source_url': 'https://example.org/synthetic'}).json()
        ids = imported['snapshot_ids']
        saved = client.post('/api/research/us/company/MCD/save', json={'snapshot_ids': ids, 'project_id': project['id']})
        assert saved.status_code == 201
        record = saved.json()
        assert client.get('/api/projects/' + project['id']).json()['links'][0]['run_id'] == record['id']
        client.post('/api/research/us/company/MCD/prices', json={'text': CSV.replace(',102,', ',101,'), 'source_url': 'https://example.org/synthetic'})
        assert client.get('/api/research/runs/' + record['id']).json()['result']['prices']['rows'][0]['close'] == 102
        response = client.get('/api/research/export/' + record['id'])
        assert response.status_code == 200
        with zipfile.ZipFile(BytesIO(response.content)) as archive:
            assert {'report.md', 'report.zh-CN.md', 'recipe.json', 'snapshots.json', 'prices.csv'} <= set(archive.namelist())
            assert json.loads(archive.read('snapshots.json'))[0]['id'] == ids[0]
            assert b'point-in-time' in archive.read('report.md')
            assert str(tmp_path).encode() not in archive.read('recipe.json')
        assert client.get('/api/research/status').status_code == 200
        assert client.post('/api/runs', json={'tickers': ['US:MCD']}).status_code == 422


def test_invalid_import_and_save_do_not_create_evidence(tmp_path):
    with TestClient(create_app(tmp_path, run_jobs=False)) as client:
        base = '/api/research/us/company/MCD'
        for source in ('file:///secret', 'https://name:password@example.org/data', 'https://example.org/data?apikey=secret'):
            assert client.post(base + '/prices', json={'text': CSV, 'source_url': source}).status_code == 400
        assert client.post(base + '/save', json={'snapshot_ids': []}).status_code == 422
        assert client.post(base + '/save', json={'snapshot_ids': ['unknown'], 'project_id': 'missing'}).status_code == 404
        assert client.get('/api/research/runs').json() == []


def test_sec_failure_retains_old_data_and_separates_workspaces(tmp_path, monkeypatch):
    monkeypatch.delenv('QUANTSANDBOX_SEC_USER_AGENT', raising=False)
    with TestClient(create_app(tmp_path / 'one', run_jobs=False)) as client:
        client.post('/api/research/us/company/MCD/prices', json={'text': CSV, 'source_url': 'https://example.org/synthetic'})
        assert client.post('/api/research/us/company/MCD/refresh').status_code == 400
        cached = client.get('/api/research/us/company/MCD').json()
        assert cached['prices']['rows'][0]['close'] == 102
        assert cached['last_attempt']['ok'] is False
        assert client.get('/api/research/status').status_code == 200
    with TestClient(create_app(tmp_path / 'two', run_jobs=False)) as client:
        assert client.get('/api/research/us/company/MCD').json()['snapshot_ids'] == []
