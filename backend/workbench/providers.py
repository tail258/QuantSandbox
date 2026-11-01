"""Upstream calls run in a disposable process: timeouts cannot leave hung workers."""
import contextlib
import io
import json
import math
import re
import sys
from datetime import date

def clean_date(v):
    import pandas as pd
    if v is None or str(v) in ('nan','NaT','None',''): return None
    s=str(v).replace('.0','')
    try: return pd.to_datetime(s).strftime('%Y-%m-%d')
    except (ValueError,TypeError): return None

def number(v):
    try:
        x=float(str(v).replace(',',''))
        return x if math.isfinite(x) else None
    except (TypeError,ValueError): return None

def records(df):
    return json.loads(df.to_json(orient='records',force_ascii=False,date_format='iso'))

def market(symbol):
    if not re.fullmatch(r'\d{6}',symbol): raise ValueError('股票代码须为 6 位数字')
    if symbol.startswith(('4','8','920')):return 'bj'
    return 'sh' if symbol.startswith(('5','6','9')) else 'sz'

def fetch(p):
    import akshare as ak
    kind=p['kind']; symbol=p.get('symbol','600519'); start=p.get('start','2023-01-01'); end=p.get('end',date.today().isoformat())
    base={'kind':kind,'symbol':symbol,'request':p,'rows':[],'unit':'','method':'','source_url':''}
    if kind=='quotes':
        import baostock as bs
        mk=market(symbol)
        fields='date,code,open,high,low,close,volume,amount,turn,pctChg,peTTM,pbMRQ'
        adjustment=p.get('adjust','3')
        if adjustment not in ('1','2','3'): raise ValueError('无效复权方式')
        try:
            login=bs.login()
            if login.error_code!='0': raise ValueError(login.error_msg)
            q=bs.query_history_k_data_plus(f'{mk}.{symbol}',fields,start_date=start,end_date=end,frequency='d',adjustflag=adjustment)
            if q.error_code!='0': raise ValueError(q.error_msg)
            df=q.get_data()
            rows=[{k:(v if k in ('date','code') else number(v)) for k,v in r.items()} for r in records(df)]
            source='BaoStock'; url='https://www.baostock.com'
            bs.logout()
        except Exception:
            df=ak.stock_zh_a_hist(symbol=symbol,period='daily',start_date=start.replace('-',''),end_date=end.replace('-',''),adjust={'3':'','2':'qfq','1':'hfq'}[adjustment])
            mapping={'日期':'date','开盘':'open','收盘':'close','最高':'high','最低':'low','成交量':'volume','成交额':'amount','换手率':'turn','涨跌幅':'pctChg'}
            rows=[{mapping[k]:clean_date(v) if k=='日期' else number(v) for k,v in r.items() if k in mapping} for r in records(df)]
            for r in rows:
                if r.get('volume') is not None:r['volume']*=100
            source='东方财富 / AKShare'; url='https://quote.eastmoney.com'
        base.update(rows=rows,source=source,source_url=url,unit='元 / 股',method={'3':'不复权','2':'前复权','1':'后复权'}[adjustment]+'日线；成交量统一为股；换手率为%；PE/PB为数据商口径，缺失不估算。')
    elif kind=='finance':
        mk=market(symbol); tables={}
        for label in ['利润表','现金流量表','资产负债表']:
            tables[label]=records(ak.stock_financial_report_sina(stock=mk+symbol,symbol=label))
        mapped={}
        fields={'营业收入':'revenue','归属于母公司所有者的净利润':'profit','净利润':'total_profit','营业成本':'cost','经营活动产生的现金流量净额':'cashflow','资产总计':'assets','负债合计':'liabilities','归属于母公司股东权益合计':'equity'}
        for label,rows in tables.items():
            for r in rows:
                d=clean_date(r.get('报告日'))
                if not d:continue
                o=mapped.setdefault(d,{'date':d,'available_date':None,'publication_dates':{}})
                pub=clean_date(r.get('公告日期'));o['publication_dates'][label]=pub
                if pub:o['available_date']=max(o['available_date'] or pub,pub)
                for k,v in fields.items():
                    if k in r:o[v]=number(r[k])
        base.update(rows=sorted(mapped.values(),key=lambda r:r['date']),raw=tables,source='新浪财经 / AKShare',source_url=f'https://money.finance.sina.com.cn/corp/go.php/vFD_FinanceSummary/stockid/{symbol}.phtml',unit='元 CNY',method='合并报表；利润与现金流为年初至报告期累计；资产负债为时点。接口为当前修订数据，不能还原历史披露版本。')
    elif kind=='announcements':
        market(symbol)
        df=ak.stock_zh_a_disclosure_report_cninfo(symbol=symbol,market='沪深京',start_date=start.replace('-',''),end_date=end.replace('-',''))
        rows=[{'date':clean_date(r.get('公告时间')),**r} for r in records(df)]
        base.update(rows=rows,source='巨潮资讯 / AKShare',source_url='https://www.cninfo.com.cn',method='按发布日期检索；点击原文核实，以正式公告为准。空返回只表示接口没有返回记录，不证明期间没有公告。')
    elif kind=='rubber':
        df=ak.futures_zh_daily_sina(symbol='RU0')
        rows=[{'date':clean_date(r['date']),'value':number(r.get('close')),'volume':number(r.get('volume'))} for r in records(df)]
        rows=[r for r in rows if r['date'] and start<=r['date']<=end]
        base.update(symbol='RU0',rows=rows,source='新浪期货 / AKShare',source_url='https://finance.sina.com.cn/futures/quotes/RU0.shtml',unit='元/吨',method='RU0 数据商主力连续收盘价；换月规则未披露，未做跨合约调整，跨换月收益可能失真。')
    elif kind=='holders':
        market(symbol)
        df=ak.stock_zh_a_gdhs_detail_em(symbol=symbol)
        rows=[{'date':clean_date(r.get('股东户数统计截止日')),'available_date':clean_date(r.get('股东户数公告日期')),**r} for r in records(df)]
        base.update(rows=rows,source='东方财富 / AKShare',source_url=f'https://data.eastmoney.com/gdhs/detail/{symbol}.html',method='股东户数的统计截止日与公告日不同；户数变化不能直接判断散户净买卖。')
    else:raise ValueError('不支持的数据类型')
    if kind!='announcements' and not base['rows']:raise ValueError('上游未返回数据；请检查代码、日期和接口状态')
    return base

if __name__=='__main__':
    try:
        with contextlib.redirect_stdout(io.StringIO()): result=fetch(json.loads(sys.argv[1]))
        print(json.dumps({'ok':True,'data':result},ensure_ascii=True,allow_nan=False))
    except Exception as e:
        print(json.dumps({'ok':False,'error':f'{type(e).__name__}: {e}'},ensure_ascii=True))
