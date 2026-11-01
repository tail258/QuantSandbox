import json
import zipfile
import pandas as pd
import pytest
from backend.workbench import national,store,national_sources

def fixture(tmp_path,monkeypatch):
    monkeypatch.setattr(store,'DATA',tmp_path/'data');monkeypatch.setattr(store,'ROOT',tmp_path)
    dates=pd.bdate_range('2026-01-01',periods=80).strftime('%Y-%m-%d').tolist()
    common={'source':'test','source_url':'https://example.org/source','unit':'test','method':'fixture'}
    def snap(kind,symbol,rows):return store.snapshot(kind+symbol,{**common,'kind':kind,'symbol':symbol,'rows':rows})
    snaps=[snap('etf_index','sh000300',[{'date':d,'close':4000+i} for i,d in enumerate(dates)]),
      snap('etf_shares','SSE',[{'date':d,'code':'510300','shares':100000+i*10} for i,d in enumerate(dates)]),
      snap('etf_nav','510300',[{'date':d,'nav':2} for d in dates]),
      snap('national_quotes','510300',[{'date':d,'close':2+i*.01,'turnover':100+i} for i,d in enumerate(dates)]),
      snap('national_margin','SSE',[{'date':d,'code':c,'balance':1000+i,'buy':10+i,'repay':5,'net':5+i,'net_basis':'买入额−偿还额','market':'SSE'} for i,d in enumerate(dates) for c in ['510300','600000']]),
      snap('national_margin','SZSE',[{'date':d,'code':'000001','balance':2000+i*2,'buy':20,'repay':None,'net':None,'net_basis':'相邻交易日余额差待计算','market':'SZSE'} for i,d in enumerate(dates)]),
      snap('national_constituents','000300',[{'date':dates[-1],'code':'600000'},{'date':dates[-1],'code':'000001'},{'date':dates[-1],'code':'000002'}])]
    p=national.parameters({'code':'510300','start':dates[0],'end':dates[-1],'window':60})
    return dates,snaps,p,snap

def test_rolling_excludes_current_future_and_uses_midrank():
    dates=[str(i) for i in range(10)];values={d:3 for d in dates}
    r=national.rolling(values,dates,5,5)
    assert r['4']['pct'] is None and r['5']['pct']==50
    values['8']=999;r2=national.rolling(values,dates,5,5)
    assert r2['7']==r['7'] and r2['8']['pct']==100
    assert r2['8']['n']==5 and r2['8']['end']=='7'

def test_abs_percentiles_and_missing_count():
    dates=[str(i) for i in range(7)];v={d:i+1 for i,d in enumerate(dates)};v['2']=None;v['6']=-10
    r=national.rolling(v,dates,6,5,absolute=True)
    assert r['6']['pct']==100 and r['6']['n']==5

def test_margins_and_fixed_constituent_coverage(tmp_path,monkeypatch):
    dates,s,p,_=fixture(tmp_path,monkeypatch);r=national.calculate(s,p);v=r['latest']
    assert v['component_coverage']==2 and v['component_expected']==3
    assert v['component_net_coverage']==2 and v['component_net']==86
    assert v['margin_net']==84
    assert r['components']['date']==dates[-1]
    assert v['flow']==20 and v['flow_n']==60
    assert r['inference']['identity_probability'] is None

def test_szse_net_needs_adjacent_day_not_last_available(tmp_path,monkeypatch):
    dates,s,p,_=fixture(tmp_path,monkeypatch)
    sz=next(x for x in s if x['symbol']=='SZSE');sz['rows']=[r for r in sz['rows'] if r['date']!=dates[-2]]
    r=national.calculate(s,p)
    assert r['latest']['component_coverage']==2
    assert r['latest']['component_net_coverage']==1

def test_asof_has_no_future_quotes_or_disclosures(tmp_path,monkeypatch):
    dates,s,p,snap=fixture(tmp_path,monkeypatch)
    s.append(snap('etf_evidence','510300',[{'date':'2025-12-31','code':'510300','holder':'中央汇金投资有限责任公司','shares':200,'ratio_pct':2,'report_date':'2025-12-31','publication_date':dates[-1],'verification':'original_recorded','page':'75','entity_type':'汇金主体'}]))
    early=national.calculate(s,p|{'asof':dates[-2]})
    assert early['asof']==dates[-2] and early['disclosures']['latest'] is None
    assert len(early['daily'])==len(dates)-1

def test_evidence_unknown_is_not_zero_and_identity_is_explicit(tmp_path,monkeypatch):
    dates,s,p,snap=fixture(tmp_path,monkeypatch)
    rows=[]
    for period,pub,name,shares in [('2025-06-30','2025-08-29','中央汇金投资有限责任公司',100),('2025-12-31','2026-03-31','某国有企业',200)]:
        rows.append({'date':period,'code':'510300','holder':name,'shares':shares,'ratio_pct':2,'report_date':period,'publication_date':pub,'verification':'original_recorded','entity_type':'未分类','page':'1'})
    s.append(snap('etf_evidence','510300',rows));proof=national.disclosures(s,'510300',dates[-1])
    assert proof['records'][0]['change'] is None
    assert proof['periods'][0]['shares']==100
    assert proof['periods'][1]['shares'] is None # no explicit core entity in this period
    assert proof['periods'][1]['core_count']==0

def test_frozen_run_replay_and_export(tmp_path,monkeypatch):
    dates,s,p,_=fixture(tmp_path,monkeypatch);ids=[x['id'] for x in s]
    r=national.build(ids,p);assert national.build(ids,p)['result']==r['result']
    with zipfile.ZipFile(national.export_run(r)) as z:
        assert {'recipe.json','snapshots.json','daily.csv','disclosures.csv','report.md','footprints.svg','financing.svg'}<=set(z.namelist())
        from xml.etree import ElementTree
        ElementTree.fromstring(z.read('footprints.svg'));ElementTree.fromstring(z.read('financing.svg'))
        assert json.loads(z.read('recipe.json'))['inputs']==ids

def test_sse_exact_date_yuan_units_and_szse_columns():
    raw=[{'opDate':'20261028','stockCode':'510300','rzye':100,'rzmre':20,'rzche':30},{'opDate':'20261027','stockCode':'510300','rzye':999}]
    rows=national_sources.margin_sse(raw,'2026-10-28')
    assert len(rows)==1 and rows[0]['balance']==100 and rows[0]['net']==-10
    df=pd.DataFrame([{'证券代码':'159919','证券简称':'300ETF','融资余额(元)':'1,000','融资买入额(元)':'200'}])
    row=national_sources.margin_szse(df,'2026-10-28')[0]
    assert row['balance']==1000 and row['net'] is None

def test_invalid_parameters():
    for p in [{'code':'../secret'},{'window':1},{'minimum':0},{'start':'2026-10-29','end':'2026-01-01'},{'asof':'2027-01-01','end':'2026-10-29'}]:
        with pytest.raises(ValueError):national.parameters(p)

def test_partial_quote_fallback_does_not_mask_actual_turnover(tmp_path,monkeypatch):
    dates,s,p,snap=fixture(tmp_path,monkeypatch)
    s.append(snap('national_quotes','510300',[{'date':dates[-1],'close':999,'turnover':None}]))
    r=national.calculate(s,p)
    assert r['latest']['turnover']==179 and r['latest']['price']!=999

def test_chunk_boundaries_have_no_gaps():
    ranges=list(national.chunks('2025-08-05','2026-10-29',60))
    assert ranges[0][0]=='2025-08-05' and ranges[-1][1]=='2026-10-29'
    for i,(a,b) in enumerate(ranges):
        assert (pd.Timestamp(b)-pd.Timestamp(a)).days<=59
        if i:assert pd.Timestamp(a)==pd.Timestamp(ranges[i-1][1])+pd.Timedelta(days=1)

def test_calculation_version_is_part_of_run_identity(tmp_path,monkeypatch):
    _,s,p,_=fixture(tmp_path,monkeypatch);ids=[x['id'] for x in s];first=national.build(ids,p)
    monkeypatch.setattr(store,'VERSION','test-new-version');second=national.build(ids,p)
    assert first['result']==second['result'] and first['id']!=second['id']
