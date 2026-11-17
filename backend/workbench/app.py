from pathlib import Path
from fastapi import FastAPI, APIRouter, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from . import service,store,etf,national

app=FastAPI(title='QuantSandbox',version=store.VERSION)
router=APIRouter(prefix='/api/research',tags=['investment research'])
app.add_middleware(TrustedHostMiddleware,allowed_hosts=['127.0.0.1','localhost','testserver'])

@app.middleware('http')
async def local_only(request:Request,call_next):
    origin=request.headers.get('origin','')
    if origin and origin not in ('http://127.0.0.1:8765','http://localhost:8765','http://127.0.0.1:5173','http://localhost:5173'):
        return JSONResponse({'detail':'仅允许本地工作台来源'},status_code=403)
    if request.headers.get('sec-fetch-site')=='cross-site':return JSONResponse({'detail':'拒绝跨站访问'},status_code=403)
    return await call_next(request)

@app.exception_handler(ValueError)
async def value_error(request,exc):return JSONResponse({'detail':str(exc)},status_code=400)

@app.exception_handler(KeyError)
async def missing_field(request,exc):return JSONResponse({'detail':f'缺少必要字段：{exc}'},status_code=400)

@router.get('/status')
def status():return service.status()
@router.get('/health')
def health():return {'ok':True,'app':'QuantSandbox','version':store.VERSION}
@router.post('/fetch')
def fetch(p:dict):return service.retrieve(p)
@router.post('/execution-history', status_code=201)
def execution_history(p: dict):
    from pydantic import ValidationError
    from .execution_history import ExecutionHistory, import_execution_history
    try:
        history = ExecutionHistory.model_validate(p)
    except ValidationError as exc:
        raise ValueError(str(exc)) from exc
    saved = import_execution_history(history)
    return {key: value for key, value in saved.items() if key != 'rows'}
@router.get('/series/{sid}')
def series(sid:str):return service.get_series(sid)
@router.get('/snapshot/{sid}')
def snap(sid:str):return store.get_snapshot(sid)
@router.post('/import')
def upload(p:dict):
    if len(p.get('text',''))>8_000_000:raise ValueError('CSV 最大 8 MB')
    return service.import_csv(p['text'],p['meta'])
@router.get('/finance')
def finance(symbols:str='600519'):return service.finance(symbols.split(',')[:6])
@router.get('/profile/{symbol}')
def profile(symbol:str):return store.profile(symbol)
@router.post('/profile/{symbol}')
def set_profile(symbol:str,p:dict):return service.save_profile(symbol,p)
@router.post('/analyze')
def analyze(p:dict):return service.analyze(p)
@router.post('/save-finance')
def save_finance(p:dict):return service.save_finance(p)
@router.get('/runs')
def runs():return store.runs()
@router.get('/runs/{rid}')
def run(rid:str):return store.get_run(rid)
@router.get('/export/{rid}')
def export(rid:str):return FileResponse(service.export_run(rid),filename=f'quantsandbox-{rid}.zip')
@router.post('/research')
def research(p:dict):return service.research(p)

@router.post('/etf/refresh')
def etf_refresh(p:dict):return etf.start_job(p)
@router.get('/etf/jobs/{jid}')
def etf_job(jid:str):return etf.get_job(jid)
@router.post('/etf/dashboard')
def etf_dashboard(p:dict):return etf.dashboard(p.get('run_id'),p.get('codes'),float(p.get('threshold',.03)),p.get('asof'))
@router.get('/etf/intraday')
def etf_intraday_dashboard(codes:str=''):
    from . import etf_intraday
    return etf_intraday.dashboard(codes.split(',') if codes else None)

@router.get('/etf/intraday-demo')
def etf_intraday_demo():
    from .etf_demo import create_demo
    return create_demo()

@router.post('/etf/intraday/refresh')
def etf_intraday_refresh(p:dict):
    from . import etf_intraday
    return etf_intraday.start_job(p)

@router.get('/etf/intraday/jobs/{jid}')
def etf_intraday_job(jid:str):
    from . import etf_intraday
    return etf_intraday.get_job(jid)

@router.get('/etf/holders/{code}')
def etf_holders(code:str,force:bool=False):return etf.holder_data(code,force)
@router.get('/etf/evidence')
def etf_evidence():return etf.evidence()
@router.post('/etf/evidence')
def etf_save_evidence(p:dict):return etf.save_evidence(p)

@router.post('/national/dashboard')
def national_dashboard(p:dict):return national.dashboard(p)
@router.post('/national/refresh')
def national_refresh(p:dict):return national.start_job(p)
@router.get('/national/jobs/{jid}')
def national_job(jid:str):return etf.get_job(jid)




@router.get('/etf/refresh-settings')
def etf_refresh_settings():
    from . import etf_schedule
    return etf_schedule.settings()

@router.patch('/etf/refresh-settings')
def etf_update_refresh_settings(p:dict):
    from . import etf_schedule
    return etf_schedule.settings(p)

@router.post('/etf/refresh-now')
def etf_refresh_now():
    from . import etf_schedule
    return etf_schedule.refresh_now()

app.include_router(router)
