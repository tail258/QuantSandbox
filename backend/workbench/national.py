from contextvars import copy_context
"""National-team footprints: dated disclosures, market proxies, frozen recipes."""
import math
import zipfile
from concurrent.futures import ThreadPoolExecutor,as_completed
from functools import lru_cache
from datetime import datetime,timedelta
from zoneinfo import ZoneInfo
from xml.sax.saxutils import escape
import pandas as pd
from . import etf,store

CORE={'中央汇金投资有限责任公司','中央汇金资产管理有限责任公司','中国证券金融股份有限公司'}
INDICES={'沪深300':'000300','中证500':'000905','中证1000':'000852','上证50':'000016','科创50':'000688','中证A500':'000510'}
METHOD='持仓按原文报告期与公告日记录；日频ETF份额、申赎估算与融资为市场代理。历史分位只使用此前交易日，不含当日或未来值；显示有效样本数。'

def today():return datetime.now(ZoneInfo('Asia/Shanghai')).date().isoformat()

def parameters(p):
    code=str(p.get('code','510300'));etf.codes_of([code])
    end=p.get('end',today());start=p.get('start',(pd.Timestamp(end)-pd.Timedelta(days=450)).date().isoformat())
    if pd.Timestamp(start)>pd.Timestamp(end) or (pd.Timestamp(end)-pd.Timestamp(start)).days>800:raise ValueError('国家队观察取数范围须在800个自然日内')
    window=int(p.get('window',252))
    if window not in [60,120,252,504]:raise ValueError('分位参考窗口须为60/120/252/504交易日')
    minimum=int(p.get('minimum',20))
    if not 5<=minimum<=window:raise ValueError('最少有效样本须在5至参考窗口之间')
    asof=p.get('asof') or end
    if not start<=asof<=end:raise ValueError('观察截至日期须在取数范围内')
    return {'code':code,'start':start,'end':end,'asof':asof,'window':window,'minimum':minimum,'include_components':bool(p.get('include_components',True))}

def merged(snaps,kind):
    """Later fetched revisions win; sources and all original snapshots remain frozen."""
    lookup={}
    for s in sorted(snaps,key=lambda x:(x.get('fetched_at',''),x['id'])):
        if s['kind']!=kind:continue
        for row in s['rows']:
            key=(row.get('date'),row.get('code',s.get('symbol')))
            if kind=='national_quotes' and key in lookup and lookup[key].get('turnover') is not None and row.get('turnover') is None:continue
            lookup[key]={**row,'snapshot_id':s['id'],'source_url':row.get('source_url',s.get('source_url'))}
    return list(lookup.values())

def rolling(values,dates,window,minimum,absolute=False):
    result={}
    for i,d in enumerate(dates):
        previous=[values.get(t) for t in dates[max(0,i-window):i]]
        previous=[v for v in previous if v is not None and math.isfinite(v)]
        value=values.get(d);n=len(previous);rank=None
        if n>=minimum and value is not None and math.isfinite(value):
            if absolute:previous=[abs(v) for v in previous];value=abs(value)
            # Midrank prevents a constant series being labelled an extreme event.
            rank=100*(sum(v<value for v in previous)+.5*sum(v==value for v in previous))/n
        result[d]={'pct':rank,'n':n,'start':dates[max(0,i-window)] if i else None,'end':dates[i-1] if i else None}
    return result

def disclosures(snaps,code,cutoff):
    records=[]
    for s in sorted(snaps,key=lambda s:s.get('fetched_at','')):
        if s['kind']!='etf_evidence' or s['symbol']!=code:continue
        for row in s['rows']:
            if row.get('verification')!='original_recorded' or row['publication_date']>cutoff:continue
            records.append({**row,'source_url':s['source_url'],'snapshot_id':s['id'],'is_core':row['holder'] in CORE})
    latest={}
    for row in records:latest[(row['report_date'],row['holder'])]=row
    records=sorted(latest.values(),key=lambda r:(r['report_date'],r['holder']))
    previous={};periods={}
    for row in records:
        before=previous.get(row['holder']);row['change']=row['shares']-before['shares'] if before else None
        row['previous_report_date']=before['report_date'] if before else None;previous[row['holder']]=row
        period=periods.setdefault(row['report_date'],{'report_date':row['report_date'],'publication_date':row['publication_date'],'shares':0,'ratio_pct':0,'ratio_complete':True,'core_count':0,'rows':[]})
        period['publication_date']=max(period['publication_date'],row['publication_date']);period['rows'].append(row)
        if row['is_core']:
            period['shares']+=row['shares'];period['core_count']+=1
            if row['ratio_pct'] is None:period['ratio_complete']=False
            else:period['ratio_pct']+=row['ratio_pct']
    for period in periods.values():
        if not period['core_count']:period['shares']=None;period['ratio_pct']=None
        elif not period['ratio_complete']:period['ratio_pct']=None
    return {'records':records,'periods':list(periods.values()),'latest':list(periods.values())[-1] if periods else None,'core_names':sorted(CORE)}

def calculate(snaps,p):
    code=p['code'];index=merged(snaps,'etf_index');shares=merged(snaps,'etf_shares')
    index=sorted([r for r in index if p['start']<=r['date']<=p['asof']],key=lambda r:r['date'])
    selected=[r for r in shares if r['code']==code and p['start']<=r['date']<=p['asof']]
    if not selected:raise ValueError('选定ETF尚无份额缓存，请先更新数据')
    navs={(r['date'],s['symbol']):r['nav'] for s in sorted(snaps,key=lambda x:x.get('fetched_at','')) if s['kind']=='etf_nav' for r in s['rows']}
    base=etf.calculate(selected,index,navs,[code]);dates=base['calendar']
    quotes={r['date']:r for r in merged(snaps,'national_quotes') if any(s['id']==r['snapshot_id'] and s['symbol']==code for s in snaps)}
    margins={(r['date'],r['code']):dict(r) for r in merged(snaps,'national_margin')}
    constituent_snaps=[s for s in snaps if s['kind']=='national_constituents']
    constituent=sorted(constituent_snaps,key=lambda s:s.get('fetched_at',''))[-1] if constituent_snaps else None
    members={r['code'] for r in constituent['rows']} if constituent and p['include_components'] else set()
    # Shenzhen publishes balance and buys but no repayment: adjacent balance change is a labelled proxy.
    for i,d in enumerate(dates):
        for c in members|{code}:
            row=margins.get((d,c))
            if not row or row.get('net') is not None:continue
            prev=margins.get((dates[i-1],c)) if i else None
            if prev is not None:row['net']=row['balance']-prev['balance']
    daily=[]
    for d in dates:
        q=quotes.get(d,{});m=margins.get((d,code),{});per=base['details'][d][0]
        component_rows=[margins[d,c] for c in members if (d,c) in margins]
        component_nets=[r['net'] for r in component_rows if r.get('net') is not None]
        daily.append({'date':d,'price':q.get('close'),'turnover':q.get('turnover'),'shares':per['shares'],'delta':None if per['suspect'] else per['delta'],'flow':per['flow'],'suspect':per['suspect'],
          'margin_balance':m.get('balance'),'margin_buy':m.get('buy'),'margin_net':m.get('net'),'margin_basis':m.get('net_basis'),
          'component_balance':sum(r['balance'] for r in component_rows) if component_rows else None,'component_net':sum(component_nets) if component_nets else None,
          'component_coverage':len(component_rows),'component_net_coverage':len(component_nets),'component_expected':len(members)})
    for key,absolute in [('turnover',False),('delta',True),('flow',True),('margin_net',True)]:
        ranks=rolling({r['date']:r[key] for r in daily},dates,p['window'],p['minimum'],absolute)
        for row in daily:
            item=ranks[row['date']];row[key+'_pct']=item['pct'];row[key+'_n']=item['n']
    proof=disclosures(snaps,code,p['asof']);catalog=[r for r in merged(snaps,'national_report_list') if r['code']==code and r['publication_date']<=p['asof']]
    catalog=sorted(catalog,key=lambda r:r['publication_date'],reverse=True)
    events=[]
    for period in proof['periods']:
        plot_date=next((d for d in dates if d>=period['publication_date']),None)
        events.append({**period,'plot_date':plot_date,'label':'原文披露 '+period['report_date']})
    latest=daily[-1];direction=None
    if latest['flow'] is not None and latest['margin_net'] is not None:
        direction='申赎估算与ETF融资净新增同向' if latest['flow']*latest['margin_net']>0 else '申赎估算与ETF融资净新增背离' if latest['flow']*latest['margin_net']<0 else '申赎估算或融资净新增为零'
    return {'code':code,'family':etf.UNIVERSE.get(code,'自选'),'asof':base['asof'],'research_asof':p['asof'],'daily':daily,'latest':latest,'windows':base['windows'],'events':events,'disclosures':proof,'reports':catalog,
      'components':{'index_code':constituent['symbol'] if constituent else None,'date':max((r['date'] for r in constituent['rows']),default=None) if constituent else None,'expected':len(members),'method':'固定本次成分名单回看；缺记录含非两融标的，不填零。'},
      'percentile':{'window':p['window'],'minimum':p['minimum'],'method':'仅此前交易日的滚动窗口；不含当天。绝对值分位用于份额/申赎/融资净新增；成交额用原值。相等值按中秩，缺失不填零。'},
      'inference':{'direction':direction,'basis':'ETF申赎估算、融资净新增为公开市场代理；不识别交易账户。','identity_probability':None},'method':METHOD}

@lru_cache(maxsize=4)
def prepared(ids,code):
    snaps=store.get_snapshots(list(ids));members={code}
    for s in snaps:
        if s['kind']=='national_constituents':members.update(r['code'] for r in s['rows'])
    result=[]
    for s in snaps:
        rows=s['rows']
        if s['kind']=='etf_shares':rows=[r for r in rows if r['code']==code]
        elif s['kind']=='national_margin':rows=[r for r in rows if r['code'] in members]
        result.append({**s,'original_count':len(s['rows']),'rows':rows})
    return result

def build(ids,p):
    p=parameters(p);ids=list(dict.fromkeys(ids));snaps=prepared(tuple(ids),p['code'])
    result=calculate(snaps,p)
    sources=[{k:v for k,v in s.items() if k not in ['rows','raw','original_count']}|{'count':s.get('original_count',len(s['rows']))} for s in snaps]
    return store.save_run({'kind':'national','title':f'国家队足迹 · {p["code"]} · {result["asof"]}','params':p,'inputs':ids,'sources':sources,'result':result})

def chunks(start,end,span=120):
    cursor=pd.Timestamp(start)
    while cursor<=pd.Timestamp(end):
        stop=min(cursor+pd.Timedelta(days=span-1),pd.Timestamp(end))
        yield cursor.date().isoformat(),stop.date().isoformat()
        cursor=stop+pd.Timedelta(days=1)

def refresh(raw,progress=lambda **kw:None):
    p=parameters(raw);code=p['code'];force=bool(raw.get('force'));start=p['start'];end=p['end'];ids=[];errors=[]
    progress(stage='获取历史交易日历',done=0,total=1)
    idx=etf.source({'kind':'national_index','start':start,'end':end},f'etf_cache:national:index:{start}:{end}',force);ids.append(idx['id'])
    dates=[r['date'] for r in idx['rows']];tasks=[]
    if code.startswith('5'):tasks.extend(({'kind':'sse','start':d,'end':d},'etf_cache:shares:SSE:'+d) for d in dates)
    else:
        for a,b in chunks(start,end):tasks.append(({'kind':'szse','start':a,'end':b},f'etf_cache:shares:SZSE:{a}:{b}'))
    for a,b in chunks(start,end,60):tasks.append(({'kind':'etf_quotes','code':code,'start':a,'end':b},f'etf_cache:national:quotes:{code}:{a}:{b}'))
    tasks.extend([({'kind':'nav','code':code,'start':start,'end':end},f'etf_cache:nav:{code}:{start}:{end}'),({'kind':'report_list','code':code,'start':start,'end':end},f'etf_cache:national:reports:{code}:{end}')])
    index_code=INDICES.get(etf.UNIVERSE.get(code)) if p['include_components'] else None
    if index_code:tasks.insert(0,({'kind':'constituents','code':index_code,'start':'','end':end},f'etf_cache:national:constituents:{index_code}:{end}'))
    margin_dates=[d for d in dates if d>=(pd.Timestamp(end)-pd.Timedelta(days=75)).date().isoformat()]
    markets=['sse','szse'] if index_code else ['sse' if code.startswith('5') else 'szse']
    for d in margin_dates:
        for market in markets:tasks.append(({'kind':'margin_'+market,'start':d,'end':d},f'etf_cache:national:margin:{market}:{d}'))
    total=len(tasks);done=0
    def fetch(task):
        old=store.latest(task[1]) if task[0]['kind']=='etf_quotes' else None
        s=etf.source(*task,force=force or bool(old and old.get('upstream_warning')))
        return s,s.get('warning') or s.get('upstream_warning') or (None if s['rows'] else '上游未发布或无记录')
    with ThreadPoolExecutor(4) as pool:
        futures={pool.submit(copy_context().run,fetch,t):t[0] for t in tasks}
        for f in as_completed(futures):
            request=futures[f];done+=1
            try:
                s,warning=f.result();ids.append(s['id'])
                if warning:errors.append({'request':request,'error':warning})
            except Exception as e:errors.append({'request':request,'error':str(e)})
            progress(stage='补历史份额、行情、融资与披露目录',done=done,total=total,errors=len(errors))
    ids.extend(s['id'] for s in etf.evidence() if s['symbol']==code)
    ids.extend(s['id'] for s in store.latest_prefix('etf_cache:national:quotes:'+code+':'))
    run=build(ids,p)
    store.snapshot('national_dashboard:'+code,{'kind':'national_dashboard','symbol':code,'source':'交易所份额/融资、中证名单、ETF原文证据','source_url':'https://www.sse.com.cn/market/othersdata/margin/detail/','unit':'份 / 元','method':METHOD,'run_id':run['id'],'errors':errors,'rows':[{'date':r['date'],'flow':r['flow'],'margin_net':r['margin_net']} for r in run['result']['daily']]})
    return {'run_id':run['id'],'asof':run['result']['asof'],'errors':errors,'inputs':len(ids)}

def dashboard(p):
    code=p.get('code','510300');etf.codes_of([code]);state=store.latest('national_dashboard:'+code)
    if p.get('run_id'):
        original=store.get_run(p['run_id'])
        if original['kind']!='national':raise ValueError('不是国家队观察记录')
        params={**original['params'],**{k:v for k,v in p.items() if k!='run_id'}};ids=original['inputs'];errors=[]
    elif state:
        original=store.get_run(state['run_id']);params={**original['params'],**p};ids=original['inputs'];errors=state.get('errors',[])
        ids=ids+[s['id'] for s in etf.evidence() if s['symbol']==code]
        ids=ids+[s['id'] for s in store.latest_prefix('etf_cache:national:quotes:'+code+':')]
    else:return {'empty':True,'universe':etf.UNIVERSE}
    return {'empty':False,'universe':etf.UNIVERSE,'run':build(ids,params),'errors':errors}

def start_job(p):
    parameters(p)
    return etf.start_job({**p,'job_kind':'national'})

def chart_svg(run,margin=False):
    rows=run['result']['daily'];keys=['component_balance','margin_balance'] if margin else ['price','shares']
    labels=['成分股融资（亿元，左轴）','ETF融资（亿元，右轴）'] if margin else ['ETF价格（元，左轴）','ETF总份额（亿份，右轴）']
    title='融资资金对照' if margin else 'ETF价格、份额与原文披露';elements=[];colors=['#6c8ca4','#087d79']
    for i,key in enumerate(keys):
        scale=1e8 if margin or key=='shares' else 1
        values=[r[key]/scale for r in rows if r[key] is not None]
        if not values:continue
        lo=min(values);hi=max(values);pad=(hi-lo or max(abs(hi)*.05,1))*.1;lo-=pad;hi+=pad;span=hi-lo;commands=[];last=None
        for j,row in enumerate(rows):
            value=row[key]
            if value is None:last=None;continue
            x=90+j*940/max(1,len(rows)-1);y=355-(value/scale-lo)/span*245
            commands.append(f'{"L" if last is not None else "M"}{x:.2f},{y:.2f}');last=j
        elements.append(f'<path d="{" ".join(commands)}" fill="none" stroke="{colors[i]}" stroke-width="1.7"/>')
        elements.append(f'<text x="{45+i*540}" y="65" fill="{colors[i]}" font-size="13">{labels[i]}；范围 {lo:,.2f} 至 {hi:,.2f}</text>')
    for j in range(0,len(rows),max(1,len(rows)//6)):
        elements.append(f'<text x="{90+j*940/max(1,len(rows)-1):.2f}" y="385" text-anchor="middle" font-size="11">{rows[j]["date"]}</text>')
    if not margin:
        dates=[r['date'] for r in rows]
        for event in run['result']['events']:
            if event['plot_date'] not in dates:continue
            x=90+dates.index(event['plot_date'])*940/max(1,len(rows)-1)
            elements.append(f'<path d="M{x:.2f},90V355" stroke="#b28b49" stroke-dasharray="4 4"/><text x="{x+5:.2f}" y="100" font-size="10">披露 {event["report_date"]}</text>')
    caption='固定本次成分名单回看；双轴各自缩放；每日覆盖见CSV。' if margin else '双轴各自缩放；披露节点使用公告可用日；份额变化不识别交易账户。'
    return f'<svg xmlns="http://www.w3.org/2000/svg" width="1120" height="470" viewBox="0 0 1120 470"><rect width="100%" height="100%" fill="white"/><g font-family="Microsoft YaHei,sans-serif" fill="#304b56"><text x="40" y="32" font-size="20">{escape(run["params"]["code"])} · {title}</text>{"".join(elements)}<text x="40" y="425" font-size="12">{caption}</text><text x="40" y="452" font-size="11">记录 {run["id"]}；来源、参数、快照与口径见 report.md / recipe.json。</text></g></svg>'

def export_run(run):
    folder=store.ROOT/'exports'/run['id'];folder.mkdir(parents=True,exist_ok=True);r=run['result']
    (folder/'recipe.json').write_text(store.encode(run),encoding='utf-8')
    (folder/'snapshots.json').write_text(store.encode(store.get_snapshots(run['inputs'])),encoding='utf-8')
    pd.DataFrame(r['daily']).to_csv(folder/'daily.csv',index=False,encoding='utf-8-sig')
    pd.DataFrame(r['disclosures']['records']).to_csv(folder/'disclosures.csv',index=False,encoding='utf-8-sig')
    pd.DataFrame(r['reports']).to_csv(folder/'report-catalog.csv',index=False,encoding='utf-8-sig')
    (folder/'footprints.svg').write_text(chart_svg(run),encoding='utf-8')
    (folder/'financing.svg').write_text(chart_svg(run,True),encoding='utf-8')
    text=f'# {run["title"]}\n\n研究截至 {r["research_asof"]}；份额截至 {r["asof"]}。\n\n{METHOD}\n\n分位参考 {run["params"]["window"]} 个此前交易日，最少 {run["params"]["minimum"]} 个有效样本；逐日样本数见 daily.csv。\n\n融资净新增：沪市为买入−偿还，深市为相邻交易日余额差代理。成分融资按 {r["components"]["date"]} 固定名单回看，覆盖数另列；不作为历史时点回测。\n\n## 持仓披露\n\n'
    for period in r['disclosures']['periods']:
        text+=f'- 期末 {period["report_date"]}；已登记记录最晚公告 {period["publication_date"]}；核心主体已识别 {period["core_count"]} 家；合计份额 {period["shares"]}。\n'
    text+='\n![价格、份额与披露](footprints.svg)\n\n![融资资金对照](financing.svg)\n\n目录条目不代表已核验原文；未进入前十大不代表零持仓。资金异动不直接归因国家队；不输出未校准的主体概率。\n\n## 来源\n\n'
    seen=set()
    for s in run['sources']:
        key=(s['source'],s.get('source_url',''))
        if key in seen:continue
        seen.add(key);text+=f'- [{s["source"]}]({s.get("source_url","")})：{s["method"]}\n'
    text+=f'\n版本 {run["version"]}；记录 {run["id"]}；输入 {len(run["inputs"])} 个快照；详细请求、抓取时间、计算参数在 recipe.json。\n'
    (folder/'report.md').write_text(text,encoding='utf-8')
    dest=store.ROOT/'exports'/(run['id']+'.zip')
    with zipfile.ZipFile(dest,'w',zipfile.ZIP_DEFLATED) as z:
        for f in folder.iterdir():z.write(f,f.name)
    return dest
