import json
from types import SimpleNamespace
import pandas as pd
import pytest
from backend.workbench import etf,store,etf_sources

def fixture(n=40):
    dates=pd.bdate_range('2026-01-01',periods=n).strftime('%Y-%m-%d').tolist()
    index=[{'date':d,'close':4000+i} for i,d in enumerate(dates)]
    shares=[{'date':d,'code':c,'name':c,'shares':(1000+i*10 if c=='510300' else 1000-i*5)} for i,d in enumerate(dates) for c in ['510300','159919']]
    nav={(d,c):(2 if c=='510300' else 3) for d in dates for c in ['510300','159919']}
    return dates,index,shares,nav

def test_windows_are_trading_days_and_nav_estimates():
    dates,index,shares,nav=fixture()
    r=etf.calculate(shares,index,nav,['510300','159919'])
    assert r['asof']==dates[-1]
    assert r['windows']['7']['start']==dates[-8]
    assert r['windows']['7']['delta']==35
    assert r['windows']['7']['flow']==35 # 7 * (10*2 - 5*3)
    assert r['windows']['30']['delta']==150
    assert r['latest']['coverage']==2 and r['latest']['positive']==1
    assert sum(g['delta'] for g in r['groups'])==r['latest']['delta']

def test_missing_not_zero_or_previous_day_substitute():
    dates,index,shares,nav=fixture()
    shares=[s for s in shares if not (s['code']=='510300' and s['date']==dates[-2])]
    r=etf.calculate(shares,index,nav,['510300','159919'])
    assert r['latest']['coverage']==1
    assert r['latest']['delta']==-5
    assert r['rows'][0]['delta'] is None
    assert r['windows']['7']['nav_coverage']==1
    # Endpoint difference remains observable; daily estimated flows are incomplete.
    assert r['windows']['7']['coverage']==2

def test_nav_missing_and_split_suspect_are_not_money_flows():
    dates,index,shares,nav=fixture()
    del nav[(dates[-1],'159919')]
    next(s for s in shares if s['date']==dates[-1] and s['code']=='510300')['shares']=6000
    r=etf.calculate(shares,index,nav,['510300','159919'])
    assert r['latest']['suspect_count']==1
    assert r['latest']['coverage']==1 and r['latest']['nav_coverage']==0
    assert r['latest']['flow'] is None
    assert r['windows']['30']['coverage']==1

def test_no_lookahead_date_and_short_history():
    dates,index,shares,nav=fixture(10)
    r=etf.calculate(shares,index,nav,['510300','159919'],asof=dates[-3])
    assert r['daily'][-1]['date']==dates[-3]
    assert r['windows']['30']['delta'] is None
    assert r['windows']['30']['coverage']==0
    with pytest.raises(ValueError):etf.calculate(shares,index,nav,['bad'])
    with pytest.raises(ValueError):etf.calculate(shares,index,nav,['510300'],threshold=0)

def test_conflicting_share_observations_fail():
    dates,index,shares,nav=fixture()
    shares.append({**shares[0],'shares':3000})
    with pytest.raises(ValueError,match='冲突'):etf.calculate(shares,index,nav,['510300','159919'])

def test_sse_unit_and_exact_date_validation(monkeypatch):
    import requests
    raw=[{'STAT_DATE':'2026-10-28','TOT_VOL':'123.4','SEC_CODE':'510300','SEC_NAME':'300ETF'}, {'STAT_DATE':'2026-10-27','TOT_VOL':'999','SEC_CODE':'510300','SEC_NAME':'300ETF'}]
    monkeypatch.setattr(requests,'get',lambda *a,**k:SimpleNamespace(raise_for_status=lambda:None,json=lambda:{'result':raw}))
    r=etf_sources.fetch({'kind':'sse','start':'2026-10-28','end':'2026-10-28'})
    assert len(r['rows'])==1 and r['rows'][0]['shares']==1234000
    assert r['rows'][0]['raw_unit']=='万份'

def test_evidence_dates_identity_and_catalog_hides_cache(tmp_path,monkeypatch):
    monkeypatch.setattr(store,'DATA',tmp_path)
    valid={'code':'510300','holder':'中央汇金投资有限责任公司','report_date':'2026-06-30','publication_date':'2026-08-29','shares':100,'ratio_pct':1,'source_url':'https://example.org/original.pdf','page':'12'}
    with pytest.raises(ValueError):etf.save_evidence(valid|{'publication_date':''})
    with pytest.raises(ValueError):etf.save_evidence(valid|{'publication_date':'2026-06-29'})
    with pytest.raises(ValueError):etf.save_evidence(valid|{'source_url':'javascript:alert(1)'})
    with pytest.raises(ValueError):etf.save_evidence(valid|{'shares':''})
    saved=etf.save_evidence(valid)
    assert saved['rows'][0]['entity_type']=='汇金主体'
    assert etf.classify('全国社保基金一零八组合')=='社保/养老组合'
    assert etf.classify('某国有企业')=='未分类'
    store.snapshot('etf_cache:private',{'kind':'etf_shares','rows':[]})
    assert len(store.catalog())==1

def test_szse_units_remain_shares_and_dates_are_not_shifted(monkeypatch):
    import akshare
    monkeypatch.setattr(akshare,'fund_scale_daily_szse',lambda **kw:pd.DataFrame([
        {'日期':'2026-10-28','基金代码':'159919','基金简称':'300ETF','基金份额':1234000},
        {'日期':'2026-10-29','基金代码':'159919','基金简称':'300ETF','基金份额':2000000}]))
    r=etf_sources.fetch({'kind':'szse','start':'2026-10-28','end':'2026-10-28'})
    assert len(r['rows'])==1
    assert r['rows'][0]['shares']==1234000
    assert r['rows'][0]['date']=='2026-10-28' and r['rows'][0]['raw_unit']=='份'

def test_replay_and_export_use_frozen_snapshots(tmp_path,monkeypatch):
    monkeypatch.setattr(store,'DATA',tmp_path/'data');monkeypatch.setattr(store,'ROOT',tmp_path)
    dates,index,shares,nav=fixture()
    common={'source':'test','source_url':'https://example.org','method':'fixture','unit':'份'}
    snaps=[store.snapshot('index',{**common,'kind':'etf_index','symbol':'sh000300','rows':index}),store.snapshot('shares',{**common,'kind':'etf_shares','symbol':'SSE','rows':shares})]
    for code in ['510300','159919']:
        snaps.append(store.snapshot('nav:'+code,{**common,'kind':'etf_nav','symbol':code,'rows':[{'date':d,'nav':nav[d,code]} for d in dates]}))
    ids=[s['id'] for s in snaps];params={'codes':['510300','159919'],'threshold':.03}
    r=etf.build(ids,params)
    assert etf.build(ids,params)['result']==r['result']
    import zipfile
    with zipfile.ZipFile(etf.export_run(r)) as z:
        assert {'report.md','recipe.json','snapshots.json','daily.csv','etf-detail.csv','daily-etf-detail.csv','chart-delta.svg','chart-flow.svg'}<=set(z.namelist())
        from xml.etree import ElementTree
        chart=ElementTree.fromstring(z.read('chart-flow.svg'))
        assert len(chart.findall('.//{http://www.w3.org/2000/svg}circle'))==len(dates)-1
