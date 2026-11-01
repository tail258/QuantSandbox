import json
import zipfile
import pytest
from backend.workbench import store,service
from fastapi.testclient import TestClient
from backend.workbench.app import app

@pytest.fixture(autouse=True)
def isolated(tmp_path,monkeypatch):
    monkeypatch.setattr(store,'DATA',tmp_path/'data')
    monkeypatch.setattr(store,'ROOT',tmp_path)

def meta(symbol='test'):
    return {'name':'测试指标','symbol':symbol,'source':'测试来源','source_url':'https://example.org/data','unit':'元','method':'测试用例，非市场数据'}

def test_import_validation_and_metadata():
    with pytest.raises(ValueError):service.import_csv('date,value\n2024-01-01,3',meta())
    with pytest.raises(ValueError):service.import_csv('date,value,available_date\n2024-01-02,3,2024-01-01',meta())
    with pytest.raises(ValueError):service.import_csv('date,value,available_date\n2024-01-02,inf,2024-01-03',meta())
    with pytest.raises(ValueError):service.import_csv('date,value,available_date\n2024-01-02,1,2024-01-03',meta('../escape'))
    s=service.import_csv('date,value,available_date\n2024-01-02,3,2024-01-05',meta())
    assert service.get_series(s['id']+':value')['rows'][0]['available_date']=='2024-01-05'

def test_snapshot_replay_export_keeps_old_inputs():
    csv='date,value,available_date\n'+'\n'.join(f'2024-01-{i:02d},{i},2024-01-{i:02d}' for i in range(1,21))
    a=service.import_csv(csv,meta('a'));b=service.import_csv(csv,meta('b'))
    p={'x':a['id']+':value','y':b['id']+':value','start':'2024-01-01','end':'2024-01-20','lag':0,'horizon':2,'transform':'returns'}
    run=service.analyze(p)
    service.import_csv(csv.replace(',10,',',99,'),meta('a'))
    assert service.analyze(p)['result']==run['result']
    path=service.export_run(run['id'])
    with zipfile.ZipFile(path) as z:
        assert {'report.md','recipe.json','snapshots.json','chart.svg','data.csv'}<=set(z.namelist())
        assert json.loads(z.read('snapshots.json'))[0]['id']==a['id']
    with pytest.raises(ValueError):service.export_run('../../not-a-run')

def test_company_profile_and_http_boundary():
    p={'template':'bank','metrics':['profit','assets'],'peers':['601398'],'focus':'净息差、不良率','name':'测试银行'}
    service.save_profile('600000',p)
    assert store.profile('600000')['template']=='bank'
    with pytest.raises(ValueError):service.save_profile('600000',p|{'peers':['bad']})
    c=TestClient(app)
    assert c.get('/api/research/health').json()['app']=='QuantSandbox'
    assert c.post('/api/research/research',json={'topic':'test'},headers={'Origin':'https://untrusted.example'}).status_code==403
    assert c.get('/api/research/status',headers={'Host':'evil.example'}).status_code==400
    assert c.post('/api/research/import',json={'text':'date,value\n2024-01-01,1','meta':meta()}).status_code==400

def test_failed_refresh_only_reuses_same_request(monkeypatch):
    class Response:
        stderr=''
        def __init__(self,payload):self.stdout=json.dumps(payload)
    request={'kind':'quotes','symbol':'600519','start':'2024-01-01','end':'2024-02-01','adjust':'3'}
    payload={'kind':'quotes','symbol':'600519','request':request,'source':'fixture','method':'test','unit':'元','rows':[{'date':'2024-01-02','close':100}]}
    monkeypatch.setattr(service.subprocess,'run',lambda *a,**k:Response({'ok':True,'data':payload}))
    original=service.retrieve(request)
    monkeypatch.setattr(service.subprocess,'run',lambda *a,**k:Response({'ok':False,'error':'upstream failed'}))
    stale=service.retrieve(request|{'force':True})
    assert stale['id']==original['id'] and stale['warning']=='upstream failed'
    with pytest.raises(ValueError):service.retrieve(request|{'force':True,'adjust':'2'})

def test_finance_export_respects_ytd():
    rows=[{'date':'2024-03-31','revenue':100,'profit':10,'cost':60,'cashflow':7}, {'date':'2024-06-30','revenue':250,'profit':40,'cost':140,'cashflow':20}]
    store.snapshot('finance:600519',{'kind':'finance','symbol':'600519','source':'fixture','source_url':'https://example.org','method':'test','unit':'元','rows':rows})
    run=service.save_finance({'symbols':['600519'],'mode':'ytd','metric':'revenue'})
    with zipfile.ZipFile(service.export_run(run['id'])) as z:
        import io,pandas as pd
        csv=pd.read_csv(io.BytesIO(z.read('data.csv')))
        assert csv.iloc[-1]['revenue']==250
        assert 'chart.svg' in z.namelist()
