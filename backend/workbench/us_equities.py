"""Explicitly requested SEC research; annual, current-revision facts only."""
import re
import csv
import io
import math
import os
import hashlib
import json
from datetime import date
import requests
from . import store

INSTRUMENTS = {'MCD': {'symbol':'MCD','name':"McDonald’s Corporation",'cik':'0000063908','exchange':'NYSE','currency':'USD','timezone':'America/New_York','market':'US'}}
TAGS = {'revenue':['RevenueFromContractWithCustomerExcludingAssessedTax','Revenues','SalesRevenueNet'], 'net_income':['NetIncomeLoss'], 'operating_income':['OperatingIncomeLoss'], 'operating_cashflow':['NetCashProvidedByUsedInOperatingActivities'], 'capex':['PaymentsToAcquirePropertyPlantAndEquipment'], 'assets':['Assets'], 'liabilities':['Liabilities'], 'equity':['StockholdersEquity'], 'diluted_eps':['EarningsPerShareDiluted'], 'shares':['WeightedAverageNumberOfDilutedSharesOutstanding']}

def catalog():
    return [dict(v) for v in INSTRUMENTS.values()]

def instrument(symbol):
    symbol = symbol.upper().strip()
    if symbol not in INSTRUMENTS: raise ValueError('Unsupported US equity symbol')
    return dict(INSTRUMENTS[symbol])

def normalize_facts(raw, cik):
    years = {}
    facts = raw.get('facts',{}).get('us-gaap',{})
    for metric,tags in TAGS.items():
        unit = 'USD/shares' if metric == 'diluted_eps' else 'shares' if metric == 'shares' else 'USD'
        candidates = []
        for priority,tag in enumerate(tags):
            for f in facts.get(tag,{}).get('units',{}).get(unit,[]):
                if not re.fullmatch(r'\d{10}-\d{2}-\d{6}',f.get('accn','')): continue
                try:
                    date.fromisoformat(f.get('end','')); date.fromisoformat(f.get('filed',''))
                except ValueError: continue
                if f.get('form') not in ('10-K','10-K/A') or not f.get('end') or not f.get('filed'): continue
                if metric not in ('assets','liabilities','equity'):
                    if not f.get('start'): continue
                    try: days = (date.fromisoformat(f['end'])-date.fromisoformat(f['start'])).days
                    except (ValueError,TypeError): continue
                    if not 330 <= days <= 380: continue
                val = f.get('val')
                if not isinstance(val,(int,float)) or not math.isfinite(val): continue
                candidates.append((f,priority,tag))
        for f,priority,tag in sorted(candidates,key=lambda x:(x[0]['filed'],x[0].get('accn',''),-x[1])):
            end=f['end']; row=years.setdefault(end,{'period_end':end,'metrics':{}})
            acc=f.get('accn','')
            row['metrics'][metric]={'value':f['val'],'unit':unit,'period_start':f.get('start'),'period_end':end,'filed':f['filed'],'accession':acc,'form':f['form'],'tag':tag,'source_url':f'https://www.sec.gov/Archives/edgar/data/{int(cik)}/{acc.replace("-", "")}/' if acc else None}
    annual_ends={end for end,row in years.items() if any(row['metrics'].get(k) for k in TAGS if k not in ('assets','liabilities','equity'))}
    years={end:row for end,row in years.items() if end in annual_ends}
    for row in years.values():
        m=row['metrics']; a=m.get('operating_cashflow'); b=m.get('capex')
        row['free_cashflow'] = a['value']-b['value'] if a and b and a['accession']==b['accession'] and a['period_start']==b['period_start'] else None
        for metric in TAGS: m.setdefault(metric,None)
    return sorted(years.values(),key=lambda r:r['period_end'],reverse=True)

def dashboard(symbol='MCD'):
    ins=instrument(symbol); symbol=ins['symbol']; snap=store.latest('us_equities:sec:'+symbol); prices=store.latest('us_equities:prices:'+symbol)
    return {'instrument':ins,'scope':'annual; current revised SEC facts, not point-in-time history','financials':normalize_facts(snap['companyfacts'],ins['cik']) if snap else [],'filings':snap.get('filings',[]) if snap else [],'snapshot':snap,'prices':prices,'snapshot_ids':[s['id'] for s in (snap,prices) if s],'last_attempt':store.latest('us_equities:attempt:'+symbol)}

def refresh(symbol='MCD'):
    ins=instrument(symbol); symbol=ins['symbol']
    try:
        agent=os.environ.get('QUANTSANDBOX_SEC_USER_AGENT','').strip()
        if not agent: raise ValueError('Set QUANTSANDBOX_SEC_USER_AGENT to your organization and real contact email before fetching SEC data.')
        raw={}; sources=[]
        for kind,path in [('submissions',f'submissions/CIK{ins["cik"]}.json'),('companyfacts',f'api/xbrl/companyfacts/CIK{ins["cik"]}.json')]:
            url='https://data.sec.gov/'+path
            response=requests.get(url,headers={'User-Agent':agent,'Accept':'application/json'},timeout=20)
            response.raise_for_status(); raw[kind]=response.json();
            if str(raw[kind].get('cik','')).zfill(10)!=ins['cik']: raise ValueError('SEC CIK does not match instrument')
            sources.append({'url':url,'sha256':hashlib.sha256(response.content).hexdigest()})
        recent=raw['submissions'].get('filings',{}).get('recent',{}); filings=[]
        for i,acc in enumerate(recent.get('accessionNumber',[])[:30]):
            doc=recent.get('primaryDocument',[])[i]
            if '/' in doc or '\\' in doc or '..' in doc: continue
            filings.append({'accession':acc,'form':recent['form'][i],'filed':recent['filingDate'][i],'report_date':recent.get('reportDate',['']*len(recent['accessionNumber']))[i],'source_url':f'https://www.sec.gov/Archives/edgar/data/{int(ins["cik"])}/{acc.replace("-", "")}/{doc}'})
        normalize_facts(raw['companyfacts'],ins['cik'])
        store.snapshot('us_equities:sec:'+symbol,{**raw,'kind':'us_sec','source':'SEC','source_url':'https://data.sec.gov/','method':'SEC JSON','unit':'mixed','rows':[],'sources':sources,'filings':filings,'symbol':symbol})
        store.snapshot('us_equities:attempt:'+symbol,{'ok':True,'rows':[]})
    except Exception as exc:
        store.snapshot('us_equities:attempt:'+symbol,{'ok':False,'error':str(exc),'rows':[]})
        raise ValueError(str(exc)) from exc
    return dashboard(symbol)

def import_prices(symbol,text,source_url=''):
    ins=instrument(symbol); rows=[]; seen=set()
    if len(text.encode())>8*1024*1024: raise ValueError('CSV exceeds 8 MB')
    from urllib.parse import urlsplit
    u=urlsplit(source_url)
    if u.scheme not in ('http','https') or not u.hostname or u.username or u.password or u.query: raise ValueError('Provide a public source URL without credentials or query parameters')
    if not {'date','open','high','low','close','volume'}.issubset(csv.DictReader(io.StringIO(text)).fieldnames or []): raise ValueError('Missing OHLCV columns')
    for row in csv.DictReader(io.StringIO(text)):
        day=date.fromisoformat(row['date']).isoformat()
        if day in seen: raise ValueError('Duplicate price date')
        seen.add(day)
        values={k:float(row[k]) for k in ('open','high','low','close','volume')}
        if any(not math.isfinite(v) for v in values.values()) or any(values[k]<=0 for k in ('open','high','low','close')) or values['volume']<0: raise ValueError('Invalid OHLCV value')
        if values['high']<max(values['open'],values['close'],values['low']) or values['low']>min(values['open'],values['close']): raise ValueError('Invalid OHLC range')
        rows.append({'date':day,**values})
    if len(rows)>100000: raise ValueError('CSV exceeds 100000 rows')
    if not rows: raise ValueError('Price CSV is empty')
    return store.snapshot('us_equities:prices:'+ins['symbol'],{'kind':'us_prices','source':'CSV import','method':'manual import','unit':'USD','symbol':ins['symbol'],'currency':'USD','adjustment':'unadjusted','source_url':source_url,'rows':sorted(rows,key=lambda r:r['date']),'sha256':hashlib.sha256(text.encode()).hexdigest()})

def export_markdown(symbol='MCD'):
    d=dashboard(symbol); s=d['snapshot']; lines=['# '+d['instrument']['symbol']+' company research','',d['scope'],'','Snapshot: '+(s['id'] if s else 'none'),'Fetched: '+(s['fetched_at'] if s else 'never'),'']
    for r in d['financials']:
        lines.append('## '+r['period_end'])
        for k,v in r['metrics'].items():
            lines.append(f'- {k}: '+(f'{v["value"]} {v["unit"]}; filed {v["filed"]}; accession {v["accession"]}; {v["source_url"]}' if v else 'missing'))
    return '\n'.join(lines)

# Resolve displayed immutable snapshots when saving a research record.
def dashboard_from_snapshots(symbol, snapshot_ids):
    ins=instrument(symbol)
    if len(snapshot_ids)!=len(set(snapshot_ids)): raise ValueError('Duplicate snapshot IDs')
    snapshots=[store.get_snapshot(sid) for sid in snapshot_ids]
    if any(not ('companyfacts' in s or s.get('adjustment')=='unadjusted') for s in snapshots): raise ValueError('Unsupported snapshot schema')
    if any(s.get('symbol')!=ins['symbol'] for s in snapshots): raise ValueError('Snapshot symbol mismatch')
    kinds=[s.get('kind') for s in snapshots]
    if any(k not in ('us_sec','us_prices') for k in kinds) or len(kinds)!=len(set(kinds)): raise ValueError('Unsupported or duplicate snapshot kinds')
    sec=next((s for s in snapshots if 'companyfacts' in s),None)
    prices=next((s for s in snapshots if s.get('adjustment')=='unadjusted'),None)
    return {'instrument':ins,'scope':'annual; current revised SEC facts, not point-in-time history','financials':normalize_facts(sec['companyfacts'],ins['cik']) if sec else [],'filings':sec.get('filings',[]) if sec else [],'snapshot':sec,'prices':prices,'snapshot_ids':list(snapshot_ids)}

def import_sec(symbol, submissions, companyfacts):
    ins=instrument(symbol)
    if isinstance(submissions,str): submissions=json.loads(submissions)
    if isinstance(companyfacts,str): companyfacts=json.loads(companyfacts)
    if any(str(x.get('cik','')).zfill(10)!=ins['cik'] for x in (submissions,companyfacts)): raise ValueError('SEC CIK does not match instrument')
    normalize_facts(companyfacts,ins['cik'])
    return store.snapshot('us_equities:sec:'+ins['symbol'],{'symbol':ins['symbol'],'source':'SEC','source_url':'https://data.sec.gov/','method':'manual SEC JSON import','unit':'mixed','kind':'us_sec','rows':[],'submissions':submissions,'companyfacts':companyfacts,'filings':[],'sha256':hashlib.sha256(store.encode({'submissions':submissions,'companyfacts':companyfacts}).encode()).hexdigest()})
