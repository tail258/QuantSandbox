import argparse
import json
from datetime import date,timedelta
from pathlib import Path
from . import service,store,etf,national

def main():
    p=argparse.ArgumentParser(description='QuantSandbox：供 Codex 调用的只读投资研究接口；JSON 输出')
    sub=p.add_subparsers(dest='cmd',required=True)
    for c in ['status','series','runs']:sub.add_parser(c)
    f=sub.add_parser('fetch');f.add_argument('kind',choices=['quotes','finance','announcements','rubber','holders']);f.add_argument('--symbol',default='600519');f.add_argument('--start',default='2023-01-01');f.add_argument('--end',default=__import__('datetime').date.today().isoformat());f.add_argument('--adjust',default='3',choices=['1','2','3']);f.add_argument('--force',action='store_true')
    for c in ['analyze','profile']:
        a=sub.add_parser(c);a.add_argument('file',help='UTF-8 JSON 参数文件')
    a=sub.add_parser('import');a.add_argument('csv');a.add_argument('meta',help='UTF-8 JSON 来源/单位/口径/标识文件')
    for c in ['run','export','replay']:
        a=sub.add_parser(c);a.add_argument('id')
    a=sub.add_parser('research');a.add_argument('topic')
    a=sub.add_parser('etf-refresh');a.add_argument('--start',default=(date.today()-timedelta(days=75)).isoformat());a.add_argument('--end',default=date.today().isoformat());a.add_argument('--codes',default='');a.add_argument('--force',action='store_true')
    a=sub.add_parser('etf-dashboard');a.add_argument('--run-id');a.add_argument('--threshold',type=float,default=.03);a.add_argument('--asof');a.add_argument('--codes',default='')
    a=sub.add_parser('etf-holders');a.add_argument('code')
    a=sub.add_parser('etf-evidence');a.add_argument('file')
    for name in ['national-refresh','national-dashboard']:
        a=sub.add_parser(name);a.add_argument('--code',default='510300');a.add_argument('--window',type=int,default=252);a.add_argument('--asof');a.add_argument('--start');a.add_argument('--end');a.add_argument('--no-components',action='store_true')
        if name=='national-dashboard':a.add_argument('--run-id')
    args=vars(p.parse_args());cmd=args.pop('cmd')
    try:
        if cmd=='status':r=service.status()
        elif cmd=='series':r=service.all_series()
        elif cmd=='runs':r=store.runs()
        elif cmd=='fetch':r=service.retrieve(args)
        elif cmd=='import':r=service.import_csv(Path(args['csv']).read_text(encoding='utf-8-sig'),json.loads(Path(args['meta']).read_text(encoding='utf-8-sig')))
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
        elif cmd=='etf-holders':r=etf.holder_data(args['code'])
        elif cmd=='etf-evidence':r=etf.save_evidence(json.loads(Path(args['file']).read_text(encoding='utf-8-sig')))
        elif cmd in ['national-refresh','national-dashboard']:
            args={k:v for k,v in args.items() if v is not None};args['include_components']=not args.pop('no_components')
            r=national.refresh(args,lambda **s:print(json.dumps({'progress':s},ensure_ascii=False),file=__import__('sys').stderr,flush=True)) if cmd=='national-refresh' else national.dashboard(args)
        print(json.dumps(r,ensure_ascii=False,allow_nan=False))
    except Exception as e:
        print(json.dumps({'error':str(e)},ensure_ascii=False));raise SystemExit(1)

if __name__=='__main__':main()
