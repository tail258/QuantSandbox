from datetime import datetime
from fastapi.testclient import TestClient
from backend.main import create_app
from backend.workbench import etf, etf_schedule, store


def test_refresh_api_settings_and_manual_job_are_workspace_scoped(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(etf, 'start_job', lambda p: calls.append((p, store.data_path())) or {'id': 'a' * 32, 'status': 'running'})
    monkeypatch.setattr(etf, 'get_job', lambda jid: {'status': 'running'})
    with TestClient(create_app(tmp_path, run_jobs=False)) as client:
        base = '/api/research/etf/'
        assert client.get(base + 'refresh-settings').json()['time'] == '15:30'
        assert client.patch(base + 'refresh-settings', json={'enabled': False, 'time': '16:15'}).json()['next_run'] is None
        assert client.patch(base + 'refresh-settings', json={'time': '24:01'}).status_code == 400
        assert client.patch(base + 'refresh-settings', json={'enabled': 'false'}).status_code == 400
        assert client.patch(base + 'refresh-settings', json={'vault': '/outside'}).status_code == 400
        assert client.post(base + 'refresh-now', json={}).json()['id'] == 'a' * 32
        assert calls == [({'recent_days': 5}, tmp_path / 'workbench')]
    assert (tmp_path / 'workbench/etf-refresh-settings.json').exists()


def test_disabled_and_before_time_never_fetch(tmp_path, monkeypatch):
    monkeypatch.setattr(store, 'DATA', tmp_path)
    monkeypatch.setattr(etf_schedule, 'now', lambda: datetime(2026, 11, 6, 15, 29, tzinfo=etf_schedule.TZ))
    monkeypatch.setattr(etf, 'start_job', lambda p: (_ for _ in ()).throw(AssertionError('unexpected fetch')))
    etf_schedule.tick()
    etf_schedule.settings({'enabled': False})
    monkeypatch.setattr(etf_schedule, 'now', lambda: datetime(2026, 11, 6, 17, 0, tzinfo=etf_schedule.TZ))
    etf_schedule.tick()


def test_restart_reports_persisted_running_job_interrupted(tmp_path, monkeypatch):
    monkeypatch.setattr(store, 'DATA', tmp_path)
    jid = 'e' * 32
    etf.write_job({'id': jid, 'status': 'running', 'params': {}})
    assert etf.get_job(jid)['status'] == 'interrupted'
    assert '中断' in etf.get_job(jid)['error']


def test_job_dedup_does_not_cross_workspace(tmp_path, monkeypatch):
    class PausedThread:
        def __init__(self, **kwargs): pass
        def start(self): pass
    monkeypatch.setattr(etf.threading, 'Thread', PausedThread)
    monkeypatch.setattr(etf, '_jobs', {})
    monkeypatch.setattr(store, 'DATA', tmp_path / 'first')
    first = etf.start_job({})
    assert etf.start_job({})['id'] == first['id']
    monkeypatch.setattr(store, 'DATA', tmp_path / 'second')
    assert etf.start_job({})['id'] != first['id']


def test_progress_updates_and_poll_reads_do_not_race_windows_replacement(tmp_path, monkeypatch):
    import threading
    monkeypatch.setattr(store, 'DATA', tmp_path)
    job = {'id': 'f' * 32, 'status': 'running', 'done': 0}
    etf.write_job(job)
    errors = []
    def update():
        token = store._scope_data.set(tmp_path)
        try:
            for i in range(100):
                etf.write_job({**job, 'done': i})
        except Exception as error:
            errors.append(error)
        finally:
            store._scope_data.reset(token)
    worker = threading.Thread(target=update)
    worker.start()
    for _ in range(100):
        assert isinstance(etf.get_job(job['id'])['done'], int)
    worker.join(timeout=5)
    assert not worker.is_alive()
    assert errors == []
    assert etf.get_job(job['id'])['done'] == 99

def test_daily_job_transient_io_and_corruption(tmp_path, monkeypatch):
    import pytest
    from pathlib import Path
    monkeypatch.setattr(store, 'DATA', tmp_path)
    monkeypatch.setattr(etf.time, 'sleep', lambda seconds: None)
    original_replace = Path.replace
    calls = []
    def replace(path, target):
        calls.append(path)
        if len(calls) == 1: raise PermissionError('temporary Windows sharing violation')
        return original_replace(path, target)
    monkeypatch.setattr(Path, 'replace', replace)
    jid = '7'*32
    etf.write_job({'id':jid, 'status':'running'})
    assert len(calls) == 2
    assert etf.get_job(jid)['status'] == 'interrupted'
    assert not list(etf.job_path(jid).parent.glob('*.tmp'))
    etf.job_path(jid).write_text('{bad', encoding='utf-8')
    with pytest.raises(ValueError, match='损坏'): etf.get_job(jid)


def test_failed_initial_persistence_does_not_poison_daily_dedup(tmp_path, monkeypatch):
    import pytest
    monkeypatch.setattr(store, 'DATA', tmp_path)
    monkeypatch.setattr(etf, '_jobs', {})
    monkeypatch.setattr(etf, 'write_job', lambda job: (_ for _ in ()).throw(PermissionError('disk unavailable')))
    with pytest.raises(PermissionError): etf.start_job({})
    assert etf._jobs == {}
