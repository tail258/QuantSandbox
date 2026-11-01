import math
import numpy as np
import pandas as pd

METRICS={'revenue':'营业收入','profit':'归母净利润','cashflow':'经营现金流净额','gross_margin':'毛利率','net_margin':'归母净利率','cash_ratio':'经营现金流 / 归母净利','assets':'总资产','liabilities':'总负债','leverage':'资产负债率'}

def quarters(rows):
    out=[]; lookup={r['date']:r for r in rows}
    for r in sorted(rows,key=lambda x:x['date']):
        d=pd.Timestamp(r['date']); q=(d.month-1)//3+1
        o={**r,'quarter':f'{d.year}Q{q}','warnings':[]}
        prev=(pd.Period(d,freq='Q')-1).end_time.strftime('%Y-%m-%d')
        for k in ['revenue','profit','total_profit','cost','cashflow']:
            v=r.get(k)
            if q!=1:
                a=lookup.get(prev,{}).get(k)
                v=v-a if v is not None and a is not None else None
                if v is None:o['warnings'].append(f'{k} 缺本期或前期累计值')
            o[k]=v
        def ratio(a,b):return a/b if a is not None and b is not None and b!=0 else None
        o['gross_margin']=ratio(o['revenue']-o['cost'],o['revenue']) if o.get('revenue') is not None and o.get('cost') is not None else None
        o['net_margin']=ratio(o.get('profit'),o.get('revenue'))
        o['cash_ratio']=ratio(o.get('cashflow'),o.get('profit'))
        o['leverage']=ratio(o.get('liabilities'),o.get('assets'))
        prevpub=lookup.get(prev,{}).get('available_date')
        if q!=1 and prevpub:o['available_date']=max(o.get('available_date') or prevpub,prevpub)
        out.append(o)
    return out

def wilson(k,n):
    if n==0:return None
    z=1.95996398454;p=k/n; den=1+z*z/n
    mid=(p+z*z/(2*n))/den;half=z*math.sqrt(p*(1-p)/n+z*z/(4*n*n))/den
    return [mid-half,mid+half]

def series_frame(rows,frequency):
    df=pd.DataFrame(rows)
    if df.empty:raise ValueError('所选序列没有数据')
    df['date']=pd.to_datetime(df['available_date'])
    df['value']=pd.to_numeric(df['value'],errors='coerce')
    s=df.sort_values('date').drop_duplicates('date',keep='last').set_index('date')['value']
    if frequency!='D':s=s.resample({'W':'W-FRI','M':'ME'}[frequency]).last()
    return s

def calculate(xrows,yrows,p):
    freq=p.get('frequency','D'); lag=int(p.get('lag',0)); horizon=int(p.get('horizon',5))
    if freq not in ['D','W','M'] or abs(lag)>120 or not 1<=horizon<=120:raise ValueError('频率、领先滞后或观察期超出范围')
    transform=p.get('transform','returns')
    if transform not in ['returns','diff','level']:raise ValueError('无效变换')
    x=series_frame(xrows,freq);y=series_frame(yrows,freq)
    data=pd.concat([x.rename('x'),y.rename('y')],axis=1).loc[p['start']:p['end']].dropna()
    if len(data)<8:raise ValueError('对齐后少于 8 个观测，请扩大区间或更换序列')
    if transform=='returns':z=data.pct_change(fill_method=None)
    elif transform=='diff':z=data.diff()
    else:z=data.copy()
    pair=pd.concat([z.x.rename('x'),z.y.shift(-lag).rename('y')],axis=1).replace([np.inf,-np.inf],np.nan).dropna()
    if len(pair)<3:raise ValueError('位移与变换后不足 3 对观测；请缩短滞后或扩大区间')
    corr=pair.x.corr(pair.y) if len(pair)>=3 else float('nan')
    # Positive lag: X at t paired with Y at t+lag. Outcomes start at that future Y close.
    cond=None
    if lag>=0:
        fwd=data.y.shift(-(lag+horizon))/data.y.shift(-lag)-1
        sample=pd.concat([z.x.rename('signal'),fwd.rename('outcome')],axis=1).replace([np.inf,-np.inf],np.nan).dropna()
        if p.get('nonoverlap',True):sample=sample.iloc[::max(1,lag+horizon)]
        threshold=float(p.get('threshold',0))
        if not math.isfinite(threshold):raise ValueError('阈值须为有限数值')
        operator=p.get('operator','gt')
        if operator not in ('gt','lt'):raise ValueError('无效条件')
        mask=sample.signal>threshold if operator=='gt' else sample.signal<threshold
        selected=sample[mask];n=len(selected);k=int((selected.outcome>0).sum())
        cond={'n':n,'up':k,'probability':k/n if n else None,'interval':wilson(k,n),'baseline':float((sample.outcome>0).mean()) if len(sample) else None,'baseline_n':len(sample),'mean_return':float(selected.outcome.mean()) if n else None}
    return {'correlation':float(corr) if math.isfinite(corr) else None,'n':len(pair),'conditional':cond,'points':[{'date':d.strftime('%Y-%m-%d'),'x':float(r.x),'y':float(r.y)} for d,r in pair.iterrows()], 'method':f'按可用日期精确对齐；{freq}频率；{transform}变换；正滞后 {lag} 表示 X(t) 对 Y(t+{lag})。概率使用 Y(t+lag+h)/Y(t+lag)-1。零收益不计上涨；不填充缺失；非重叠按固定步长抽样；95% Wilson 区间。最新修订数据不等于当时可得版本，结果为探索统计，不是回测。'}
