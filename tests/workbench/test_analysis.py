import math
import pandas as pd
import pytest
from backend.workbench.analysis import quarters,calculate,wilson,series_frame

def test_quarter_flows_stocks_ratios_and_missing():
    rows=[{'date':'2024-03-31','revenue':100,'profit':10,'cost':60,'cashflow':7,'assets':200,'liabilities':80},
          {'date':'2024-06-30','revenue':250,'profit':40,'cost':140,'cashflow':20,'assets':230,'liabilities':100},
          {'date':'2024-12-31','revenue':500,'profit':70,'cost':300,'cashflow':40,'assets':260,'liabilities':120},
          {'date':'2025-03-31','revenue':90,'profit':8,'cost':50,'cashflow':5,'assets':270,'liabilities':110}]
    q=quarters(rows)
    assert q[1]['revenue']==150 and q[1]['profit']==30 and q[1]['cashflow']==13
    assert q[1]['assets']==230 and q[1]['leverage']==100/230
    assert q[1]['gross_margin']==70/150 and q[1]['net_margin']==.2
    assert q[2]['revenue'] is None and q[2]['assets']==260
    assert q[3]['revenue']==90

def observations(values,delay=0):
    return [{'date':d.strftime('%Y-%m-%d'),'available_date':(d+pd.Timedelta(days=delay)).strftime('%Y-%m-%d'),'value':v} for d,v in zip(pd.date_range('2024-01-01',periods=len(values)),values)]

def params(**kw):return dict(start='2024-01-01',end='2024-12-31',frequency='D',transform='level',lag=1,horizon=2,threshold=0,operator='gt',nonoverlap=False,**kw)

def test_lag_direction_and_conditional_denominator():
    x=[3,6,2,9,1,5,8,4,7,2,6,4]
    y=[99]+x[:-1]
    r=calculate(observations(x),observations(y),params())
    assert r['correlation']==pytest.approx(1)
    assert r['n']==11
    assert r['conditional']['n']==9
    assert r['conditional']['baseline_n']==9
    assert r['points'][0]['x']==3 and r['points'][0]['y']==3

def test_available_dates_not_observation_dates():
    s=series_frame(observations([1,2,3],delay=7),'D')
    assert s.index[0]==pd.Timestamp('2024-01-08')
    assert pd.Timestamp('2024-01-01') not in s.index

def test_no_trigger_and_negative_lag():
    p=params();p['threshold']=999
    r=calculate(observations(range(1,20)),observations(range(2,21)),p)
    assert r['conditional']['n']==0 and r['conditional']['probability'] is None
    p['lag']=-1
    assert calculate(observations(range(1,20)),observations(range(2,21)),p)['conditional'] is None

def test_nonoverlap_and_wilson():
    p=params();p.update(lag=0,horizon=3,nonoverlap=True)
    r=calculate(observations(range(1,21)),observations(range(1,21)),p)
    assert r['conditional']['baseline_n']==6
    lo,hi=wilson(5,10)
    assert lo==pytest.approx(.236593,abs=1e-5) and hi==pytest.approx(.763407,abs=1e-5)
    assert wilson(0,0) is None

def test_invalid_lag_and_no_infinity():
    with pytest.raises(ValueError):calculate(observations(range(10)),observations(range(10)),params()|{'lag':100})
    r=calculate(observations([0,1,2,3,4,5,6,7,8,9]),observations(range(1,11)),params()|{'transform':'returns'})
    assert all(math.isfinite(row['x']) for row in r['points'])
