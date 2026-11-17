from datetime import datetime
from backend.workbench import etf_schedule as s, store

def test_schedule_persistence_and_daily_dedup(tmp_path, monkeypatch):
    monkeypatch.setattr(store, 'DATA', tmp_path)
    monkeypatch.setattr(s, 'now', lambda: datetime(2026, 11, 6, 15, 31, tzinfo=s.TZ))
    jobs=[]
    monkeypatch.setattr(s.etf, 'start_job', lambda p: jobs.append(p) or {'id':'a'*32,'status':'running'})
    monkeypatch.setattr(s.etf, 'get_job', lambda jid: {'status':'interrupted'})
    assert s.settings()['time']=='15:30'
    assert s.settings()['timezone']=='Asia/Shanghai'
    s.tick(); s.tick()
    assert len(jobs)==1
    assert s.settings()['status']=='interrupted'
    assert s.settings()['next_run'].startswith('2026-11-07T15:30')
    s.settings({'enabled':False,'time':'16:01'})
    assert s.read()['time']=='16:01'
    assert s.settings()['next_run'] is None

def test_invalid_time(tmp_path, monkeypatch):
    import pytest
    monkeypatch.setattr(store, 'DATA', tmp_path)
    with pytest.raises(ValueError): s.settings({'time':'25:00'})

def test_incremental_source_keeps_history_and_provenance(tmp_path, monkeypatch):
    from backend.workbench import etf
    monkeypatch.setattr(store, 'DATA', tmp_path)
    old=store.snapshot('old', {'kind':'etf_index','symbol':'sh000300','rows':[{'date':'2026-10-01','close':1},{'date':'2026-11-05','close':2}]})
    monkeypatch.setattr(store,'get_run',lambda rid: {'inputs':[old['id']]})
    original=store.latest
    monkeypatch.setattr(store,'latest',lambda key: {'run_id':'r'} if key=='etf_dashboard' else original(key))
    calls=[]
    def fetch(p,key,force=False):
        calls.append((p,force))
        return store.snapshot(key,{'kind':'etf_index','symbol':'sh000300','rows':[{'date':'2026-11-06','close':3}]})
    monkeypatch.setattr(etf,'source',fetch)
    result=etf.incremental_source({'kind':'index','start':'2026-10-01','end':'2026-11-06'},'idx',5)
    assert calls[0][0]['start']=='2026-11-01'
    assert calls[0][1] is True
    assert len(result['rows'])==3
    assert result['parent_snapshot_ids'][0]==old['id']
    assert result['actual_source_dates']==['2026-11-06']
    assert store.get_snapshot(old['id'])['rows']==old['rows']

def test_incremental_catches_offline_gap_and_failure_preserves(tmp_path, monkeypatch):
    import pytest
    from backend.workbench import etf
    monkeypatch.setattr(store,'DATA',tmp_path)
    old=store.snapshot('old',{'kind':'etf_index','symbol':'sh000300','rows':[{'date':'2026-10-01','close':1},{'date':'2026-10-28','close':2}]})
    original=store.latest
    monkeypatch.setattr(store,'latest',lambda key: {'run_id':'r'} if key=='etf_dashboard' else original(key))
    monkeypatch.setattr(store,'get_run',lambda rid:{'inputs':[old['id']]})
    calls=[]
    def fetch(p,key,force=False):
        calls.append(p)
        return store.snapshot(key,{'kind':'etf_index','symbol':'sh000300','rows':[]})
    monkeypatch.setattr(etf,'source',fetch)
    request={'kind':'index','start':'2026-10-01','end':'2026-11-06'}
    result=etf.incremental_source(request,'idx',5)
    assert calls[-1]['start']=='2026-10-29'
    assert result['warning']
    assert result['rows']==old['rows']
    etf.incremental_source({**request,'start':'2026-09-01'},'idx2',5)
    assert calls[-1]['start']=='2026-09-01'
    def failure(*args,**kwargs): raise ValueError('offline')
    monkeypatch.setattr(etf,'source',failure)
    with pytest.raises(ValueError,match='offline'):etf.incremental_source(request,'idx',5)
    assert store.get_snapshot(old['id'])['rows']==old['rows']

def test_corrupt_settings_pause_and_allow_explicit_repair(tmp_path, monkeypatch):
    monkeypatch.setattr(store, 'DATA', tmp_path)
    s.path().write_text('{bad', encoding='utf-8')
    monkeypatch.setattr(s.etf, 'start_job', lambda p: (_ for _ in ()).throw(AssertionError('unexpected fetch')))
    assert s.settings()['enabled'] is False
    assert s.settings()['warning']
    s.tick()
    repaired = s.settings({'enabled': False, 'time': '16:00'})
    assert 'warning' not in repaired
    assert s.read()['time'] == '16:00'


def test_missing_scheduled_job_does_not_prevent_settings_repair(tmp_path, monkeypatch):
    monkeypatch.setattr(store, 'DATA', tmp_path)
    s.write({'enabled': False, 'time': '15:30', 'last_job_id': 'f'*32})
    assert s.settings()['status'] == 'unavailable'
    assert s.settings({'time': '16:00'})['time'] == '16:00'

def test_schedule_restart_next_day_and_workspace_are_independent(tmp_path, monkeypatch):
    clock = [datetime(2026, 11, 6, 15, 31, tzinfo=s.TZ)]
    monkeypatch.setattr(s, 'now', lambda: clock[0])
    calls = []
    monkeypatch.setattr(s.etf, 'start_job', lambda p: calls.append(str(store.data_path())) or {'id': 'a'*32})
    monkeypatch.setattr(store, 'DATA', tmp_path/'first')
    s.tick()
    # Persisted daily marker, no in-memory scheduler state, survives restart.
    s.tick()
    assert len(calls) == 1
    monkeypatch.setattr(store, 'DATA', tmp_path/'second')
    s.tick()
    assert len(calls) == 2
    monkeypatch.setattr(store, 'DATA', tmp_path/'first')
    clock[0] = datetime(2026, 11, 9, 15, 31, tzinfo=s.TZ)
    s.tick(); s.tick()
    assert len(calls) == 3
