import sqlite3

from fastapi.testclient import TestClient

from backend.main import create_app
from backend.services.projects import ProjectStore


def test_existing_project_schema_is_migrated_without_losing_links(tmp_path):
    with sqlite3.connect(tmp_path / 'projects.sqlite3') as connection:
        connection.execute('CREATE TABLE projects(id TEXT PRIMARY KEY,name TEXT NOT NULL,question TEXT NOT NULL,symbols TEXT NOT NULL,created_at TEXT NOT NULL,updated_at TEXT NOT NULL)')
        connection.execute("INSERT INTO projects VALUES('existing','旧研究','原问题','[\"601118\"]','before','before')")
    store = ProjectStore(tmp_path)
    before = store.require('existing')
    assert before['conclusion'] == '' and before['question'] == '原问题'
    changed = store.update('existing', {'conclusion': '继续核对现金流与库存。'})
    assert changed['name'] == before['name'] and changed['symbols'] == ['601118']
    assert ProjectStore(tmp_path).require('existing')['conclusion'] == '继续核对现金流与库存。'
    assert store.create('新研究', '', ['000962'])['conclusion'] == ''


def test_project_patch_is_partial_validated_and_persistent(tmp_path):
    with TestClient(create_app(tmp_path, run_jobs=False)) as client:
        project = client.post('/api/projects', json={'name': '公司观察', 'symbols': ['601118']}).json()
        url = '/api/projects/' + project['id']
        changed = client.patch(url, json={'conclusion': '观察到的事实与后续验证问题。'})
        assert changed.status_code == 200
        assert changed.json()['symbols'] == ['601118']
        assert client.get(url).json()['conclusion'] == '观察到的事实与后续验证问题。'
        for invalid in ({}, {'name': ' '}, {'name': None}, {'symbols': ['../../vault']}, {'symbols': ['601118', '601118']}, {'unsupported': 'x'}):
            assert client.patch(url, json=invalid).status_code == 422
        assert client.patch(url, json={'conclusion': ''}).json()['conclusion'] == ''
        assert client.patch('/api/projects/missing', json={'name': 'x'}).status_code == 404
