import argparse
import json
from datetime import date,timedelta
from pathlib import Path
from . import service,store,etf,national

def main():
    p=argparse.ArgumentParser(description='QuantSandbox：供 Codex 调用的只读投资研究接口；JSON 输出')
    sub=p.add_subparsers(dest='cmd',required=True)
    for c in ['status','series','runs','etf-intraday-demo']:sub.add_parser(c)
    chan_demo = sub.add_parser('chan-demo', help='Export the offline daily Chan structure and replay evidence')
    chan_demo.add_argument('--output', required=True, type=Path)
    chan_replay = sub.add_parser('chan-replay', help='Verify original daily Chan evidence')
    chan_replay.add_argument('file', type=Path)
    a=sub.add_parser('us-company', help='Cached US company research; use --refresh for explicit SEC acquisition')
    a.add_argument('--symbol', default='MCD')
    a.add_argument('--refresh', action='store_true')
    f=sub.add_parser('fetch');f.add_argument('kind',choices=['quotes','finance','announcements','rubber','holders']);f.add_argument('--symbol',default='600519');f.add_argument('--start',default='2023-01-01');f.add_argument('--end',default=__import__('datetime').date.today().isoformat());f.add_argument('--adjust',default='3',choices=['1','2','3']);f.add_argument('--force',action='store_true')
    for c in ['analyze','profile']:
        a=sub.add_parser(c);a.add_argument('file',help='UTF-8 JSON 参数文件')
    a=sub.add_parser('import');a.add_argument('csv');a.add_argument('meta',help='UTF-8 JSON 来源/单位/口径/标识文件')
    a=sub.add_parser('import-execution-history', help='Import sourced unadjusted prices, execution controls and cash dividend notices');a.add_argument('file')
    for c in ['run','export','replay']:
        a=sub.add_parser(c);a.add_argument('id')
    a=sub.add_parser('research');a.add_argument('topic')
    a=sub.add_parser('etf-refresh');a.add_argument('--start',default=(date.today()-timedelta(days=75)).isoformat());a.add_argument('--end',default=date.today().isoformat());a.add_argument('--codes',default='');a.add_argument('--force',action='store_true')
    a=sub.add_parser('etf-dashboard');a.add_argument('--run-id');a.add_argument('--threshold',type=float,default=.03);a.add_argument('--asof');a.add_argument('--codes',default='')
    a=sub.add_parser('etf-intraday');a.add_argument('--codes',default='');a.add_argument('--refresh',action='store_true');a.add_argument('--history',action='store_true')
    a=sub.add_parser('etf-holders');a.add_argument('code')
    a=sub.add_parser('etf-evidence');a.add_argument('file')
    for name in ['national-refresh','national-dashboard']:
        a=sub.add_parser(name);a.add_argument('--code',default='510300');a.add_argument('--window',type=int,default=252);a.add_argument('--asof');a.add_argument('--start');a.add_argument('--end');a.add_argument('--no-components',action='store_true')
        if name=='national-dashboard':a.add_argument('--run-id')
    args=vars(p.parse_args());cmd=args.pop('cmd')
    try:
        if cmd=='status':r=service.status()
        elif cmd=='etf-intraday-demo':
            from .etf_demo import create_demo
            r=create_demo()
        elif cmd in {'chan-demo', 'chan-replay'}:
            from backend.services.chan_research import demo, replay
            if cmd == 'chan-demo':
                result = demo()
                with args['output'].open('x', encoding='utf-8', newline='\n') as output:
                    output.write(result['evidence'])
            else:
                result = replay(args['file'].read_bytes())
            r = {
                'input': result['input'],
                'frames': len(result['result']['frames']),
                'structures': {layer: len(items) for layer, items in result['result']['structures'].items()},
            }
            if cmd == 'chan-demo':
                r['path'] = str(args['output'])
            else:
                r['verified'] = result['verified']
        elif cmd=='us-company':
            from . import us_equities
            r=us_equities.refresh(args['symbol']) if args['refresh'] else us_equities.dashboard(args['symbol'])
        elif cmd=='series':r=service.all_series()
        elif cmd=='runs':r=store.runs()
        elif cmd=='fetch':r=service.retrieve(args)
        elif cmd=='import':r=service.import_csv(Path(args['csv']).read_text(encoding='utf-8-sig'),json.loads(Path(args['meta']).read_text(encoding='utf-8-sig')))
        elif cmd=='import-execution-history':
            from .execution_history import ExecutionHistory, import_execution_history
            saved=import_execution_history(ExecutionHistory.model_validate_json(Path(args['file']).read_text(encoding='utf-8-sig')))
            r={key:value for key,value in saved.items() if key!='rows'}
        elif cmd=='analyze':r=service.analyze(json.loads(Path(args['file']).read_text(encoding='utf-8-sig')))
        elif cmd=='profile':
            v=json.loads(Path(args['file']).read_text(encoding='utf-8-sig'));r=service.save_profile(v['symbol'],v)
        elif cmd=='run':r=store.get_run(args['id'])
        elif cmd=='export':r={'path':str(service.export_run(args['id']))}
        elif cmd=='replay':
            original=store.get_run(args['id'])
            if original['kind']=='statistics':
                r=service.analyze(original['params'])
                r={'equal':r['result']==original['result'],'run':r}
            elif original['kind']=='etf':
                replay=etf.build(original['inputs'],original['params']);r={'equal':replay['result']==original['result'],'run':replay}
            elif original['kind']=='national':
                replay=national.build(original['inputs'],original['params']);r={'equal':replay['result']==original['result'],'run':replay}
            else:r={'equal':True,'run':original,'mode':'读取归档财务结果及输入快照；不更新数据'}
        elif cmd=='research':r=service.research(args)
        elif cmd=='etf-refresh':
            args['codes']=args['codes'].split(',') if args['codes'] else None
            r=etf.refresh(args,lambda **s:print(json.dumps({'progress':s},ensure_ascii=False),file=__import__('sys').stderr,flush=True))
        elif cmd=='etf-dashboard':r=etf.dashboard(args['run_id'],args['codes'].split(',') if args['codes'] else None,args['threshold'],args['asof'])
        elif cmd=='etf-intraday':
            from . import etf_intraday
            import time
            codes=args['codes'].split(',') if args['codes'] else None
            jobs=[]
            if args['refresh'] or args['history']:
                jobs.append(etf_intraday.start_job({'codes':codes,'history':False}))
                if args['history']:
                    jobs.append(etf_intraday.start_job({'codes':codes,'history':True}))
                for index, job in enumerate(jobs):
                    while job['status'] in ('queued','running'):
                        time.sleep(.1);job=etf_intraday.get_job(job['id'])
                    jobs[index]=job
            r={**etf_intraday.dashboard(codes),'jobs':jobs,'errors':[error for job in jobs for error in job.get('errors',[])]}
        elif cmd=='etf-holders':r=etf.holder_data(args['code'])
        elif cmd=='etf-evidence':r=etf.save_evidence(json.loads(Path(args['file']).read_text(encoding='utf-8-sig')))
        elif cmd in ['national-refresh','national-dashboard']:
            args={k:v for k,v in args.items() if v is not None};args['include_components']=not args.pop('no_components')
            r=national.refresh(args,lambda **s:print(json.dumps({'progress':s},ensure_ascii=False),file=__import__('sys').stderr,flush=True)) if cmd=='national-refresh' else national.dashboard(args)
        print(json.dumps(r,ensure_ascii=False,allow_nan=False))
        if cmd=='etf-intraday' and r.get('errors'):
            raise SystemExit(1)
    except Exception as e:
        print(json.dumps({'error':str(e)},ensure_ascii=False));raise SystemExit(1)

if __name__=='__main__':main()
