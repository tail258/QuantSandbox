from contextvars import copy_context
"""ETF share research, calculated independently from investor identity claims."""
import csv
import hashlib
import io
import json
import math
import re
import subprocess
import sys
import threading
import uuid
import zipfile
from concurrent.futures import ThreadPoolExecutor,as_completed
from datetime import datetime,timezone,timedelta
from pathlib import Path
from urllib.parse import urlparse
from xml.sax.saxutils import escape
import pandas as pd
from . import store

UNIVERSE={
 '510050':'上证50','510300':'沪深300','510330':'沪深300','510310':'沪深300','159919':'沪深300',
 '510500':'中证500','510510':'中证500','510580':'中证500','159922':'中证500','512500':'中证500',
 '512100':'中证1000','159845':'中证1000','159633':'中证1000','159629':'中证1000',
 '588000':'科创50','588080':'科创50','588050':'科创50','588090':'科创50',
 '159915':'创业板指','159949':'创业板50','159901':'深证100',
 '159338':'中证A500','159339':'中证A500','159351':'中证A500','159352':'中证A500'}
ENTITY_TYPES={'中央汇金投资有限责任公司':'汇金主体','中央汇金资产管理有限责任公司':'汇金主体','中国证券金融股份有限公司':'证券金融机构','国新投资有限公司':'国有资本投资主体','香港中央结算有限公司':'名义持股渠道'}
METHOD='份额变化=S(t)−S(t−k)，窗口按指数交易日历；金额为逐日Δ份额×同日单位净值之和。缺失不填零；窗口资金估算需每日齐全。份额大幅变化需核对拆分/合并，不能据此识别投资者。沪深来源统计时点可能不同。'

def codes_of(codes=None):
    codes=list(dict.fromkeys(codes or UNIVERSE))
    if not codes or len(codes)>40 or any(not re.fullmatch(r'(?:5\d{5}|15\d{4})',c) for c in codes):raise ValueError('ETF代码须为5或15开头的六位数字；最多40只')
    return codes

def source(p,key,force=False,ttl=86400):
    old=store.latest(key)
    if old and not old['rows']:ttl=min(ttl,900)
    if old and not force and old.get('request')==p and (datetime.now(timezone.utc)-datetime.fromisoformat(old['fetched_at'])).total_seconds()<ttl:return old
    try:
        proc=subprocess.run([sys.executable,'-m','backend.workbench.etf_sources',json.dumps(p)],cwd=store.ROOT,capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=35)
        try:r=json.loads(proc.stdout.strip().splitlines()[-1])
        except (ValueError,IndexError):raise ValueError('源进程未返回有效JSON：'+proc.stderr[-150:])
        if not r['ok']:raise ValueError(r['error'])
        return store.snapshot(key,r['data'])
    except (ValueError,subprocess.TimeoutExpired) as e:
        if old and old.get('request')==p:return {**old,'warning':str(e),'cache_status':'旧缓存'}
        raise ValueError(str(e))

def classify(name):
    if name in ENTITY_TYPES:return ENTITY_TYPES[name]
    if name.startswith('全国社保基金') or name.startswith('基本养老保险基金'):return '社保/养老组合'
    if '保险' in name or '人寿' in name:return '保险相关主体'
    if '基金' in name:return '基金相关主体'
    return '未分类'

def calculate(shares,index,navs,codes,threshold=.03,asof=None):
    codes=codes_of(codes)
    if not math.isfinite(threshold) or not .001<=threshold<=1:raise ValueError('异常阈值范围为0.1%—100%')
    calendar=sorted({r['date'] for r in index if r.get('close') is not None})
    if not calendar:raise ValueError('没有指数交易日历')
    indexmap={r['date']:r['close'] for r in index};lookup={}
    names={}
    for r in shares:
        if r['code'] not in codes:continue
        value=r.get('shares')
        if value is None or not math.isfinite(value) or value<0:continue
        key=(r['date'],r['code'])
        if key in lookup and lookup[key]!=value:raise ValueError('同一日期ETF份额冲突，请核对来源')
        lookup[key]=value;names[r['code']]=r.get('name',r['code'])
    available=sorted({d for d,c in lookup if d in indexmap})
    if not available:raise ValueError('ETF份额与指数日历没有共同日期')
    asof=asof or available[-1]
    if asof not in calendar:raise ValueError('所选日期不在指数交易日历中')
    calendar=[d for d in calendar if d<=asof];daily=[];details={}
    for i,d in enumerate(calendar):
        per=[]
        for c in codes:
            current=lookup.get((d,c));prev=lookup.get((calendar[i-1],c)) if i else None
            delta=current-prev if current is not None and prev is not None else None
            rate=delta/prev if delta is not None and prev else None
            suspect=rate is not None and abs(rate)>=.5
            nav=navs.get((d,c));flow=delta*nav if delta is not None and nav and not suspect else None
            per.append({'code':c,'name':names.get(c,c),'family':UNIVERSE.get(c,'自选'),'shares':current,'delta':delta,'rate':rate,'nav':nav,'flow':flow,'suspect':suspect,'abnormal':rate is not None and abs(rate)>=threshold})
        valid=[r for r in per if r['delta'] is not None and not r['suspect']];flows=[r['flow'] for r in valid if r['flow'] is not None]
        daily.append({'date':d,'index_close':indexmap[d],'delta':sum(r['delta'] for r in valid) if valid else None,'flow':sum(flows) if flows else None,'coverage':len(valid),'nav_coverage':len(flows),'expected':len(codes),'positive':sum(r['delta']>0 for r in valid),'suspect_count':sum(r['suspect'] for r in per)})
        details[d]=per
    pos=len(calendar)-1;last=daily[-1];end=calendar[-1]
    windows={}
    for k in [1,7,30]:
        per=[]
        for c in codes:
            current=lookup.get((end,c));begin=lookup.get((calendar[pos-k],c)) if pos>=k else None
            sequence=[details[d][codes.index(c)] for d in calendar[max(0,pos-k+1):pos+1]]
            suspect=any(r['suspect'] for r in sequence)
            delta=current-begin if current is not None and begin is not None and not suspect else None
            flows=[r['flow'] for r in sequence]
            flow=sum(flows) if pos>=k and len(flows)==k and all(v is not None for v in flows) else None
            per.append({'code':c,'name':names.get(c,c),'family':UNIVERSE.get(c,'自选'),'delta':delta,'flow':flow,'rate':delta/begin if delta is not None and begin else None,'suspect':suspect})
        valid=[r for r in per if r['delta'] is not None];validflows=[r['flow'] for r in per if r['flow'] is not None]
        windows[str(k)]={'days':k,'start':calendar[pos-k] if pos>=k else None,'end':end,'delta':sum(r['delta'] for r in valid) if valid else None,'flow':sum(validflows) if validflows else None,'coverage':len(valid),'nav_coverage':len(validflows),'expected':len(codes),'rows':per}
    rows=[]
    for i,c in enumerate(codes):
        row={**details[end][i]}
        for k in [1,7,30]:row[f'delta_{k}']=windows[str(k)]['rows'][i]['delta'];row[f'flow_{k}']=windows[str(k)]['rows'][i]['flow']
        rows.append(row)
    groups=[]
    for family in sorted({r['family'] for r in rows}):
        subset=[r for r in rows if r['family']==family];valid=[r for r in subset if r['delta'] is not None and not r['suspect']]
        groups.append({'family':family,'count':len(subset),'coverage':len(valid),'delta':sum(r['delta'] for r in valid) if valid else None,'positive':sum(r['delta']>0 for r in valid)})
    return {'asof':end,'calendar':calendar,'dates':available,'daily':daily,'details':details,'windows':windows,'rows':rows,'groups':groups,'latest':last,'method':METHOD,'threshold':threshold,'universe':codes,'coverage_note':'份额合计只表示选定样本；不同基金每份价值不同，不可据份额合计直接推断资金金额。待核验大幅变化不计入合计。'}

def build(snapshot_ids,params):
    snaps=[store.get_snapshot(s) for s in snapshot_ids]
    shares=[r for s in snaps if s['kind']=='etf_shares' for r in s['rows']]
    idx=next((s['rows'] for s in snaps if s['kind']=='etf_index'),[])
    navs={(r['date'],s['symbol']):r['nav'] for s in snaps if s['kind']=='etf_nav' for r in s['rows']}
    result=calculate(shares,idx,navs,params['codes'],float(params.get('threshold',.03)),params.get('asof'))
    sources=[{k:v for k,v in s.items() if k not in ['rows','raw']}|{'count':len(s['rows'])} for s in snaps]
    return store.save_run({'kind':'etf','title':'宽基ETF资金观察 · '+result['asof'],'params':params,'inputs':list(dict.fromkeys(snapshot_ids)),'sources':sources,'result':result})

def refresh(p,progress=lambda **kw:None):
    start=p.get('start',(datetime.now().date()-timedelta(days=75)).isoformat());end=p.get('end',datetime.now().date().isoformat());codes=codes_of(p.get('codes'))
    a=pd.Timestamp(start);b=pd.Timestamp(end)
    if a>b or (b-a).days>120:raise ValueError('单次刷新最多120个自然日，开始不得晚于结束')
    force=bool(p.get('force'));ids=[];errors=[]
    progress(stage='获取沪深300交易日历',done=0,total=1)
    idx=source({'kind':'index','start':start,'end':end},f'etf_cache:index:{start}:{end}',force);ids.append(idx['id'])
    dates=[r['date'] for r in idx['rows']]
    tasks=[({'kind':'sse','start':d,'end':d},'etf_cache:shares:SSE:'+d) for d in dates if any(c.startswith('5') for c in codes)]
    if any(c.startswith('15') for c in codes):tasks.append(({'kind':'szse','start':start,'end':end},f'etf_cache:shares:SZSE:{start}:{end}'))
    tasks.extend(({'kind':'nav','code':c,'start':start,'end':end},f'etf_cache:nav:{c}:{start}:{end}') for c in codes)
    total=len(tasks);done=0
    def run(task):
        s=source(*task,force=force)
        if not s['rows']:return s,'上游尚未发布或无记录'
        return s,s.get('warning')
    with ThreadPoolExecutor(4) as pool:
        futures={pool.submit(copy_context().run,run,t):t[0] for t in tasks}
        for f in as_completed(futures):
            request=futures[f];done+=1
            try:
                s,warn=f.result();ids.append(s['id'])
                if warn:errors.append({'request':request,'error':warn})
            except Exception as e:errors.append({'request':request,'error':str(e)})
            progress(stage='获取交易所份额与基金净值',done=done,total=total,errors=len(errors))
    params={'codes':codes,'threshold':float(p.get('threshold',.03)),'start':start,'end':end}
    run=build(ids,params)
    store.snapshot('etf_dashboard',{'kind':'etf_dashboard','symbol':'宽基ETF','source':'沪深交易所份额 / 东方财富净值 / BaoStock指数','source_url':'https://www.sse.com.cn/assortment/fund/etf/list/scale/','unit':'份 / 元（估算）','method':METHOD,'run_id':run['id'],'rows':[{'date':r['date'],'delta':r['delta'],'coverage':r['coverage']} for r in run['result']['daily']],'errors':errors})
    return {'run_id':run['id'],'asof':run['result']['asof'],'errors':errors,'inputs':len(ids)}

_jobs={};_lock=threading.Lock()
def job_path(jid):
    if not re.fullmatch(r'[a-f0-9]{32}',jid):raise ValueError('无效任务ID')
    return store.data_path()/'etf-jobs'/(jid+'.json')

def write_job(job):
    path=job_path(job['id']);path.parent.mkdir(parents=True,exist_ok=True)
    temp=path.with_suffix('.tmp');temp.write_text(store.encode(job),encoding='utf-8');temp.replace(path)

def start_job(p):
    codes_of(p.get('codes'))
    with _lock:
        running=next((j for j in _jobs.values() if j['status']=='running' and j['params'].get('job_kind')==p.get('job_kind')),None)
        if running:return running
        jid=uuid.uuid4().hex;job={'id':jid,'status':'running','stage':'准备','done':0,'total':1,'created_at':store.now(),'params':p};_jobs[jid]=job;write_job(job)
    def work():
        def progress(**kw):
            with _lock:job.update(kw);write_job(job)
        try:
            if p.get('job_kind')=='national':
                from .national import refresh as national_refresh
                result=national_refresh(p,progress)
            else:result=refresh(p,progress)
            with _lock:job.update(status='completed',stage='完成',result=result,completed_at=store.now());write_job(job)
        except Exception as e:
            with _lock:job.update(status='failed',stage='失败',error=str(e));write_job(job)
    context=copy_context()
    threading.Thread(target=lambda:context.run(work),name='etf-manual-refresh',daemon=True).start()
    return dict(job)

def get_job(jid):
    path=job_path(jid)
    if not path.exists():raise ValueError('找不到任务')
    job=json.loads(path.read_text(encoding='utf-8'))
    if job['status']=='running' and jid not in _jobs:job.update(status='interrupted',error='服务重启，原刷新任务已中断，可重新运行并复用已完成缓存')
    return job

def dashboard(run_id=None,codes=None,threshold=.03,asof=None):
    state=store.latest('etf_dashboard')
    if not run_id and not state:return {'empty':True,'universe':UNIVERSE}
    original=store.get_run(run_id or state['run_id'])
    if original['kind']!='etf':raise ValueError('不是ETF分析记录')
    params={**original['params'],'codes':codes_of(codes or original['params']['codes']),'threshold':threshold}
    if asof:params['asof']=asof
    else:params.pop('asof',None)
    run=build(original['inputs'],params)
    return {'empty':False,'run':run,'universe':UNIVERSE,'errors':state.get('errors',[]) if state and not run_id else []}

def holder_data(code,force=False):
    codes_of([code]);p={'kind':'holders','code':code,'start':'','end':''}
    s=source(p,'etf_cache:holders:'+code,force)
    return {**s,'rows':[{**r,'entity_type':classify(r['holder'])} for r in s['rows']]}

def save_evidence(p):
    code=p['code'];codes_of([code]);name=str(p.get('holder','')).strip();period=p.get('report_date','');published=p.get('publication_date','');url=p.get('source_url','')
    if not name or not re.fullmatch(r'\d{4}-\d{2}-\d{2}',period) or not re.fullmatch(r'\d{4}-\d{2}-\d{2}',published):raise ValueError('持有人名称、报告期与公告日必填')
    if pd.Timestamp(published)<pd.Timestamp(period):raise ValueError('公告日不得早于统计期末')
    if urlparse(url).scheme not in ['http','https'] or not urlparse(url).netloc:raise ValueError('请填写公开原文HTTP(S)链接')
    if p.get('shares') in [None,'']:raise ValueError('持有份额必填')
    shares=float(p['shares']);ratio=p.get('ratio_pct')
    if not math.isfinite(shares) or shares<0:raise ValueError('持有份额须为非负有限数')
    if ratio is not None:
        ratio=float(ratio)
        if not math.isfinite(ratio) or not 0<=ratio<=100:raise ValueError('占比范围0—100%')
    row={'code':code,'holder':name,'shares':shares,'ratio_pct':ratio,'report_date':period,'publication_date':published,'entity_type':classify(name),'verification':'original_recorded','page':str(p.get('page','')),'note':str(p.get('note',''))}
    key=hashlib.sha256((code+period+name).encode()).hexdigest()[:20]
    return store.snapshot('etf_evidence:'+key,{'kind':'etf_evidence','symbol':code,'source':'用户/Codex原文核验登记','source_url':url,'unit':'份 / %','method':'按原始披露登记，主体分类不代表投资行为归因。','rows':[{'date':period,**row}]})

def evidence():return [s for s in store.catalog() if s['kind']=='etf_evidence']

def chart_svg(run,key):
    """Export the same frozen daily series; missing flow never becomes zero."""
    rows=run['result']['daily'];lo=min(r['index_close'] for r in rows);hi=max(r['index_close'] for r in rows)
    span=hi-lo or 1;pad=span*.1;lo-=pad;hi+=pad;span=hi-lo
    width=1120;height=500;left=85;right=1070;top=100;bottom=365
    unit='亿元' if key=='flow' else '亿份';name='估算净申赎' if key=='flow' else '净份额变化'
    maximum=max([abs(r[key]) for r in rows if r[key] is not None] or [1]) or 1
    elements=[];points=[]
    for j in range(5):
        y=top+(bottom-top)*j/4;value=hi-span*j/4
        elements.append(f'<path d="M{left} {y}H{right}" stroke="#edf0f2"/><text x="{left-12}" y="{y+4}" text-anchor="end" font-size="12">{value:,.0f}</text>')
    for i,r in enumerate(rows):
        x=left+(right-left)*i/max(1,len(rows)-1);y=bottom-(r['index_close']-lo)/span*(bottom-top);points.append(f'{x:.2f},{y:.2f}')
        if r[key] is not None and r[key]!=0:
            value=r[key];radius=3+math.sqrt(abs(value)/maximum)*14;color='#bf6065' if value>0 else '#309281'
            tip=f"{r['date']}；{name} {value/1e8:,.2f}{unit}；份额覆盖 {r['coverage']}/{r['expected']}；净值覆盖 {r['nav_coverage']}/{r['expected']}"
            elements.append(f'<circle cx="{x:.2f}" cy="{y:.2f}" r="{radius:.2f}" fill="{color}" fill-opacity=".74" stroke="white"><title>{escape(tip)}</title></circle>')
        if i in {0,len(rows)-1} or i%max(1,len(rows)//6)==0:
            elements.append(f'<text x="{x:.2f}" y="{bottom+28}" text-anchor="middle" font-size="11">{r["date"]}</text>')
    line=f'<polyline points="{" ".join(points)}" fill="none" stroke="#8d9da6" stroke-width="1.5"/>'
    # Draw the line beneath circles while retaining the source dates in title nodes.
    elements.insert(5,line)
    subtitle=f"红色净增 / 绿色净减；点大小为{name}绝对值；纵轴为沪深300点位；样本{len(run['result']['universe'])}只"
    return f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}"><rect width="100%" height="100%" fill="white"/><g font-family="Microsoft YaHei,sans-serif" fill="#243c42"><text x="40" y="35" font-size="21">沪深300 × {name}</text><text x="40" y="65" font-size="13">{subtitle}</text>{"".join(elements)}<text x="40" y="435" font-size="12">最新份额 {run["result"]["asof"]}；来源日期对齐，沪深统计时点可能不同。缺失保留，金额为份额差×同日净值估算。</text><text x="40" y="465" font-size="12">记录 {run["id"]}；来源、参数与逐日覆盖见 report.md / recipe.json / daily.csv。份额变化不识别买卖主体。</text></g></svg>'

def export_run(run):
    folder=store.ROOT/'exports'/run['id'];folder.mkdir(parents=True,exist_ok=True)
    (folder/'recipe.json').write_text(store.encode(run),encoding='utf-8')
    (folder/'snapshots.json').write_text(store.encode([store.get_snapshot(i) for i in run['inputs']]),encoding='utf-8')
    pd.DataFrame(run['result']['daily']).to_csv(folder/'daily.csv',index=False,encoding='utf-8-sig')
    pd.DataFrame(run['result']['rows']).to_csv(folder/'etf-detail.csv',index=False,encoding='utf-8-sig')
    pd.DataFrame([{'date':d,**r} for d,rows in run['result']['details'].items() for r in rows]).to_csv(folder/'daily-etf-detail.csv',index=False,encoding='utf-8-sig')
    for key in ['delta','flow']:(folder/f'chart-{key}.svg').write_text(chart_svg(run,key),encoding='utf-8')
    r=run['result'];w=r['windows'];body=f"# {run['title']}\n\n{METHOD}\n\n截止：{r['asof']}；样本 {len(r['universe'])} 只；异常阈值 {r['threshold']:.2%}。\n\n|窗口（交易日）|净份额变化（份）|份额覆盖|估算申赎（元）|金额覆盖|\n|---|---:|---:|---:|---:|\n"
    show=lambda value:'缺失' if value is None else f'{value:,.2f}'
    for k,v in w.items():body+=f"|{k}|{show(v['delta'])}|{v['coverage']}/{v['expected']}|{show(v['flow'])}|{v['nav_coverage']}/{v['expected']}|\n"
    body+='\n份额变化不代表国家队买卖；估算申赎不等于二级市场净买入或基金资产规模变化。缺失和疑似拆分不填零。\n\n![份额脉冲](chart-delta.svg)\n\n![估算申赎](chart-flow.svg)\n\n## 来源\n\n'
    seen=set()
    for s in run['sources']:
        source_key=(s['source'],s.get('source_url',''))
        if source_key in seen:continue
        seen.add(source_key);body+=f"- [{s['source']}]({s.get('source_url','')})；{s['method']}\n"
    body+=f"\n分析版本 {run['version']}；记录 {run['id']}；输入快照 {len(run['inputs'])} 个。完整请求、抓取时间、快照ID与参数见 recipe.json；原始输入见 snapshots.json；逐日有效数量见 daily.csv。\n"
    (folder/'report.md').write_text(body,encoding='utf-8')
    dest=store.ROOT/'exports'/(run['id']+'.zip')
    with zipfile.ZipFile(dest,'w',zipfile.ZIP_DEFLATED) as z:
        for f in folder.iterdir():z.write(f,f.name)
    return dest
