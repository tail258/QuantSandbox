from datetime import datetime, timedelta
from backend.workbench import etf_intraday as e, store


def fixture(days=20):
    current = datetime(2026, 11, 6, 10, 7, tzinfo=e.TZ)
    dates = [(current.date() - timedelta(days=i)).isoformat() for i in range(1, days+1)]
    rows = [{'time': d+'T'+s+':00+08:00','amount_cny':10} for d in dates + [current.date().isoformat()] for s in e.SLOTS]
    return current, dates, {'rows':rows}


def test_actual_completed_boundary_and_no_quote_total():
    clock, calendar, h = fixture()
    r = e.comparison({'source_time':clock.isoformat(),'amount_cny':999999999},h,clock,calendar)
    assert len(e.SLOTS)==48
    assert r['boundary'].endswith('10:05:00+08:00')
    assert r['ratio']==1 and r['sample_count']==20 and r['status']=='complete'
    assert r['current_amount']==70


def test_missing_entire_day_not_replaced_with_older_session():
    clock, calendar, h = fixture(21)
    missing=calendar[1]
    h['rows']=[r for r in h['rows'] if not r['time'].startswith(missing)]
    r=e.comparison({'source_time':clock.isoformat()},h,clock,calendar)
    assert r['sample_count']==19 and r['status']=='provisional'
    assert r['excluded_days']==[{'date':missing,'reason':'incomplete_or_duplicate_bars'}]


def test_gap_and_duplicate_exclude_whole_day_and_small_sample_null():
    clock, calendar, h=fixture(5)
    h['rows'].append(h['rows'][0])
    r=e.comparison({'source_time':clock.isoformat()},h,clock,calendar)
    assert r['sample_count']==4 and r['ratio'] is None
    h['rows']=[r for r in h['rows'] if r['time']!=clock.date().isoformat()+'T09:35:00+08:00']
    assert e.comparison({'source_time':clock.isoformat()},h,clock,calendar)['ratio'] is None


def test_lunch_stale_unknown_future_and_observed_calendar():
    clock, calendar,h=fixture()
    lunch=clock.replace(hour=12)
    r=e.comparison({'source_time':lunch.isoformat()},h,lunch,calendar)
    assert r['boundary'].endswith('11:30:00+08:00') and r['ratio']==1
    assert e.comparison({},h,clock,calendar)['ratio'] is None
    assert e.comparison({'source_time':clock.isoformat()},h,clock+timedelta(days=1),calendar)['ratio'] is None
    assert e.comparison({'source_time':(clock+timedelta(days=1)).isoformat()},h,clock,calendar)['ratio'] is None
    assert e.comparison({'source_time':clock.isoformat()},h,clock)['status']=='provisional'
    assert e.comparison({'source_time':clock.isoformat()},h,clock)['calendar_status']=='unverified'


def test_cached_api_never_fetches_and_errors_preserve_cache(tmp_path,monkeypatch):
    from fastapi.testclient import TestClient
    from backend.workbench.app import app
    from backend.workbench import etf_intraday_sources as source
    monkeypatch.setattr(store,'DATA',tmp_path)
    clock,_,h=fixture()
    monkeypatch.setattr(e,'now',lambda:clock)
    old=store.snapshot(e._key('quote','510300'),{'rows':[{'code':'510300','source_time':clock.isoformat(),'last':3}], 'source':'fixture'})
    def fail(codes): raise ValueError('offline fixture')
    monkeypatch.setattr(source,'fetch_quotes',fail)
    client=TestClient(app)
    assert client.get('/api/research/etf/intraday?codes=510300').json()['items'][0]['quote_snapshot_id']==old['id']
    jid='b'*32;e._JOBS[jid]={'id':jid,'data_scope':str(tmp_path),'status':'queued','completed':0,'errors':[],'key':('fixture',)}
    e._run(jid,['510300'],False,True)
    row=client.get('/api/research/etf/intraday?codes=510300').json()['items'][0]
    assert row['quote_snapshot_id']==old['id'] and row['stale'] and row['errors']==['offline fixture']


def test_close_lunch_age_and_job_scope(tmp_path, monkeypatch):
    import pytest
    monkeypatch.setattr(store, 'DATA', tmp_path)
    clock, calendar, history = fixture()
    close = clock.replace(hour=15, minute=0)
    r = e.comparison({'source_time':close.isoformat()},history,close.replace(hour=18),calendar)
    assert r['ratio'] == 1 and not r['stale']
    lunch = clock.replace(hour=11, minute=30)
    assert not e.quote_stale(lunch, lunch.replace(hour=12,minute=50))
    assert e.quote_stale(clock, clock + timedelta(minutes=3))
    jid='c'*32
    e._JOBS[jid]={'id':jid,'data_scope':'other-workspace','status':'completed'}
    with pytest.raises(ValueError):e.get_job(jid)
    e._JOBS.pop(jid)
    e._persist_job({'id':jid,'data_scope':str(tmp_path),'status':'running','errors':[]})
    assert e.get_job(jid)['status']=='interrupted'


def test_quote_dedup_and_slow_history_does_not_block_quote(tmp_path,monkeypatch):
    import threading
    import time
    from backend.workbench import etf_intraday_sources as source
    monkeypatch.setattr(store,'DATA',tmp_path)
    clock,_,h=fixture()
    monkeypatch.setattr(e,'now',lambda:clock)
    monkeypatch.setattr(store,'now',lambda:clock.isoformat())
    entered=threading.Event();release=threading.Event();calls=[]
    def bars(code):
        entered.set()
        assert release.wait(3)
        return {**h,'amount_basis':'reported_actual','timestamp_convention':'bar_end'}
    def quotes(codes):
        calls.append(codes)
        return {'rows':[{'code':c,'source_time':clock.isoformat(),'last':3} for c in codes]}
    monkeypatch.setattr(source,'fetch_bars',bars)
    monkeypatch.setattr(source,'fetch_quotes',quotes)
    history=e.start_job({'codes':['510300'],'history':True})
    try:
        assert entered.wait(2)
        assert e.start_job({'codes':['510300'],'history':True})['id']==history['id']
        quote=e.start_job({'codes':['510300']})
        deadline=time.monotonic()+2
        while e.get_job(quote['id'])['status'] in ('queued','running') and time.monotonic()<deadline:
            time.sleep(.01)
        assert e.get_job(quote['id'])['status']=='completed'
        assert e.get_job(history['id'])['status']=='running'
        quote2=e.start_job({'codes':['510300']})
        deadline=time.monotonic()+2
        while e.get_job(quote2['id'])['status'] in ('queued','running') and time.monotonic()<deadline:
            time.sleep(.01)
        assert len(calls)==1
    finally:
        release.set()
        deadline=time.monotonic()+2
        while e.get_job(history['id'])['status'] in ('queued','running') and time.monotonic()<deadline:
            time.sleep(.01)


def test_outdated_calendar_and_after_close_provider_timestamp():
    clock, calendar, history=fixture(21)
    result=e.comparison({'source_time':clock.isoformat()},history,clock,calendar[1:])
    assert result['calendar_status']=='unverified' and result['status']=='provisional'
    assert 'predates' in result['calendar_warning']
    provider=clock.replace(hour=16,minute=14)
    result=e.comparison({'source_time':provider.isoformat()},history,provider.replace(hour=18),calendar)
    assert result['boundary'].endswith('15:00:00+08:00') and result['ratio']==1


def test_cli_history_fetches_quotes_and_bars(monkeypatch,capsys):
    from backend.workbench import cli
    import json
    calls=[]
    def start(params):
        calls.append(params)
        return {'id':str(len(calls)), 'status':'completed', 'errors':[]}
    monkeypatch.setattr(e,'start_job',start)
    monkeypatch.setattr(e,'dashboard',lambda codes:{'items':[]})
    monkeypatch.setattr('sys.argv',['cli','etf-intraday','--codes','510300','--history'])
    cli.main()
    assert [p['history'] for p in calls]==[False,True]
    assert len(json.loads(capsys.readouterr().out)['jobs'])==2


def test_calendar_duplicates_are_not_independent_samples():
    clock, calendar, history=fixture(5)
    result=e.comparison({'source_time':clock.isoformat()},history,clock,calendar*4)
    assert result['sample_count']==5 and result['status']=='provisional'
    assert result['calendar_status']=='unverified'


def test_session_valid_excludes_after_close_and_lunch(tmp_path,monkeypatch):
    monkeypatch.setattr(store,'DATA',tmp_path)
    clock,_,_=fixture()
    for hour,minute,valid in [(10,7,True),(12,0,False),(16,14,False)]:
        current=clock.replace(hour=hour,minute=minute)
        monkeypatch.setattr(e,'now',lambda:current)
        store.snapshot(e._key('quote','510300'),{'rows':[{'code':'510300','source_time':current.isoformat()}]})
        assert e.dashboard(['510300'])['items'][0]['quote']['session_valid'] is valid


def test_atomic_job_replace_and_disk_read_retry(tmp_path,monkeypatch):
    from pathlib import Path
    monkeypatch.setattr(store,'DATA',tmp_path)
    jid='d'*32
    original_replace=Path.replace
    attempts=[]
    def replace(path,target):
        attempts.append(path)
        if len(attempts)==1:
            raise PermissionError('Windows reader open')
        return original_replace(path,target)
    monkeypatch.setattr(Path,'replace',replace)
    monkeypatch.setattr(e.time,'sleep',lambda seconds:None)
    e._persist_job({'id':jid,'data_scope':str(tmp_path),'status':'running','errors':[]})
    assert len(attempts)==2 and not list((tmp_path/'etf-intraday-jobs').glob('*.tmp'))
    original_read=Path.read_text
    reads=[]
    def read(path,*args,**kwargs):
        reads.append(path)
        if len(reads)==1:
            raise PermissionError('Windows replacement open')
        return original_read(path,*args,**kwargs)
    monkeypatch.setattr(Path,'read_text',read)
    assert e.get_job(jid)['status']=='interrupted'
    assert len(reads)==2

def test_final_persistence_failure_releases_active_job(tmp_path, monkeypatch):
    import pytest
    from backend.workbench import etf_intraday_sources as source
    monkeypatch.setattr(store, 'DATA', tmp_path)
    monkeypatch.setattr(source, 'fetch_quotes', lambda codes: {'rows': []})
    jid = '9'*32
    key = (str(tmp_path), ('510300',), False)
    monkeypatch.setattr(e, '_JOBS', {jid: {'id':jid, 'status':'queued', 'errors':[], 'completed':0, 'key':key}})
    monkeypatch.setattr(e, '_ACTIVE', {key:jid})
    monkeypatch.setattr(e, '_persist_job', lambda job: (_ for _ in ()).throw(PermissionError('disk unavailable')))
    with pytest.raises(PermissionError): e._run(jid, ['510300'], False, True)
    assert key not in e._ACTIVE
    assert e._JOBS[jid]['status'] == 'completed_with_errors'


def test_corrupt_persisted_job_is_recoverable_refresh_error(tmp_path, monkeypatch):
    import pytest
    monkeypatch.setattr(store, 'DATA', tmp_path)
    monkeypatch.setattr(e.time, 'sleep', lambda seconds: None)
    jid = '8'*32
    path = e._job_path(jid)
    path.parent.mkdir(parents=True)
    path.write_text('{bad', encoding='utf-8')
    with pytest.raises(ValueError, match='damaged'): e.get_job(jid)

def test_lunch_reopen_and_overnight_source_recovery():
    morning = datetime(2026, 11, 6, 11, 30, tzinfo=e.TZ)
    assert not e.quote_stale(morning, morning.replace(hour=12, minute=59))
    reopened = morning.replace(hour=13, minute=1)
    assert e.quote_stale(morning, reopened)
    assert not e.quote_stale(reopened, reopened)
    next_session = datetime(2026, 11, 9, 9, 31, tzinfo=e.TZ)
    assert e.quote_stale(morning.replace(hour=15, minute=0), next_session)
    assert not e.quote_stale(next_session, next_session)


def test_all_history_workers_busy_still_allow_quotes(tmp_path, monkeypatch):
    import threading
    import time
    from concurrent.futures import ThreadPoolExecutor
    from backend.workbench import etf_intraday_sources as source
    monkeypatch.setattr(store, 'DATA', tmp_path)
    clock, _, h = fixture()
    monkeypatch.setattr(e, 'now', lambda: clock)
    monkeypatch.setattr(store, 'now', lambda: clock.isoformat())
    release = threading.Event()
    entered = [threading.Event() for _ in range(3)]
    codes = ['510300', '510500', '510050']
    def bars(code):
        entered[codes.index(code)].set()
        assert release.wait(5)
        return {**h, 'amount_basis':'reported_actual', 'timestamp_convention':'bar_end'}
    monkeypatch.setattr(source, 'fetch_bars', bars)
    monkeypatch.setattr(source, 'fetch_quotes', lambda codes: {'rows':[{'code':c, 'source_time':clock.isoformat()} for c in codes]})
    with ThreadPoolExecutor(max_workers=3) as pool:
        monkeypatch.setattr(e, '_POOL', pool)
        histories = [e.start_job({'codes':[c], 'history':True}) for c in codes]
        try:
            assert all(event.wait(2) for event in entered)
            quote = e.start_job({'codes':['510300']})
            deadline = time.monotonic()+2
            while e.get_job(quote['id'])['status'] in ('queued','running') and time.monotonic()<deadline:
                time.sleep(.01)
            assert e.get_job(quote['id'])['status'] == 'completed'
            assert all(e.get_job(j['id'])['status']=='running' for j in histories)
        finally: release.set()
