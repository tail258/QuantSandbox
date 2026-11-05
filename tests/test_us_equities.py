from backend.workbench.us_equities import normalize_facts, import_prices
import pytest

def test_annual_noncalendar_and_missing():
    raw={'facts':{'us-gaap':{'NetIncomeLoss':{'units':{'USD':[{'start':'2022-10-01','end':'2023-09-30','filed':'2023-11-01','form':'10-K','accn':'0000063908-23-000001','val':5}]}}}}}
    rows=normalize_facts(raw,'0000063908')
    assert rows[0]['period_end']=='2023-09-30'
    assert rows[0]['metrics']['net_income']['value']==5
    assert rows[0]['free_cashflow'] is None
    assert rows[0]['metrics']['revenue'] is None

def test_invalid_price():
    with pytest.raises(ValueError): import_prices('MCD','date,open,high,low,close,volume\n2024-01-01,5,2,1,4,0')


def test_cik_rejected():
    from backend.workbench.us_equities import import_sec
    with pytest.raises(ValueError,match='CIK'): import_sec('MCD',{'cik':1},{'cik':1})

def test_header_rejected():
    with pytest.raises(ValueError,match='columns'): import_prices('MCD','foo\nbar','https://example.org/data')

def test_fcf_different_filings_not_combined():
    base={'start':'2022-10-01','end':'2023-09-30','filed':'2023-11-01','form':'10-K','accn':'0000063908-23-000001','val':10}
    other={**base,'accn':'0000063908-23-000002','val':3}
    raw={'facts':{'us-gaap':{'NetCashProvidedByUsedInOperatingActivities':{'units':{'USD':[base]}},'PaymentsToAcquirePropertyPlantAndEquipment':{'units':{'USD':[other]}}}}}
    assert normalize_facts(raw,'0000063908')[0]['free_cashflow'] is None
    other['accn']=base['accn']
    assert normalize_facts(raw,'0000063908')[0]['free_cashflow']==7

def test_balance_only_endpoint_excluded():
    f={'end':'2023-06-30','filed':'2023-11-01','form':'10-K','accn':'0000063908-23-000001','val':10}
    assert normalize_facts({'facts':{'us-gaap':{'Assets':{'units':{'USD':[f]}}}}},'0000063908')==[]

def test_scope_isolation(tmp_path):
    from backend.workbench import store
    from backend.workbench.us_equities import dashboard, dashboard_from_snapshots
    token=store._scope_data.set(tmp_path)
    try:
        assert dashboard()['snapshot_ids']==[]
        bad=store.snapshot('test',{'symbol':'MCD','rows':[]})
        with pytest.raises(ValueError,match='schema'): dashboard_from_snapshots('MCD',[bad['id']])
        with pytest.raises(ValueError,match='Duplicate'): dashboard_from_snapshots('MCD',[bad['id'],bad['id']])
    finally: store._scope_data.reset(token)
