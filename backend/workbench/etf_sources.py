"""Read-only upstream adapters. All dates and units are retained explicitly."""
import contextlib
import io
import json
import re
import sys
from .providers import clean_date,number,records

def fetch(p):
    import akshare as ak
    kind=p['kind'];start=p['start'];end=p['end']
    if kind in ['national_index','margin_sse','margin_szse','etf_quotes','constituents','report_list']:
        from .national_sources import fetch as national_fetch
        return national_fetch(p)
    if kind=='index':
        import baostock as bs
        try:
            login=bs.login()
            if login.error_code!='0':raise ValueError(login.error_msg)
            q=bs.query_history_k_data_plus('sh.000300','date,close',start_date=start,end_date=end,frequency='d')
            if q.error_code!='0':raise ValueError(q.error_msg)
            rows=[{'date':r['date'],'close':number(r['close'])} for r in records(q.get_data()) if number(r['close']) is not None]
            bs.logout()
            if not rows:raise ValueError('指数为空')
            source_name='BaoStock 沪深300日线';source_url='https://www.baostock.com'
        except Exception:
            df=ak.stock_zh_index_daily_em(symbol='sh000300',start_date=start.replace('-',''),end_date=end.replace('-',''))
            rows=[{'date':clean_date(r['date']),'close':number(r['close'])} for r in records(df)]
            source_name='东方财富 沪深300日线 / AKShare';source_url='https://quote.eastmoney.com/zs000300.html'
        return {'kind':'etf_index','symbol':'sh000300','source':source_name,'source_url':source_url,'unit':'点','method':'沪深300指数收盘；日期用于确定共同交易日历。','rows':rows,'request':p}
    if kind=='sse':
        # Official endpoint returns TOT_VOL in ten-thousand units.
        import requests
        url='https://query.sse.com.cn/commonQuery.do'
        params={'isPagination':'true','pageHelp.pageSize':'10000','pageHelp.pageNo':'1','sqlId':'COMMON_SSE_ZQPZ_ETFZL_XXPL_ETFGM_SEARCH_L','STAT_DATE':end}
        r=requests.get(url,params=params,headers={'Referer':'https://www.sse.com.cn/','User-Agent':'Mozilla/5.0'},timeout=15);r.raise_for_status()
        raw=r.json().get('result') or []
        rows=[]
        for row in raw:
            d=clean_date(row.get('STAT_DATE'));v=number(row.get('TOT_VOL'));code=str(row.get('SEC_CODE','')).zfill(6)
            if d!=end or v is None or v<0:continue
            rows.append({'date':d,'code':code,'name':str(row.get('SEC_NAME',code)),'shares':v*10000,'market':'SSE','source_date':d,'raw_unit':'万份'})
        return {'kind':'etf_shares','symbol':'SSE','source':'上海证券交易所 ETF规模日报','source_url':'https://www.sse.com.cn/assortment/fund/etf/list/scale/','unit':'份','method':'来源统计日期原样保留；TOT_VOL 万份 × 10000 转为份。空返回表示未发布或无记录。','rows':rows,'request':p}
    if kind=='szse':
        df=ak.fund_scale_daily_szse(start_date=start.replace('-',''),end_date=end.replace('-',''),symbol='ETF')
        rows=[{'date':clean_date(r['日期']),'code':str(r['基金代码']).zfill(6),'name':r['基金简称'],'shares':number(r['基金份额']),'market':'SZSE','source_date':clean_date(r['日期']),'raw_unit':'份'} for r in records(df)]
        rows=[r for r in rows if r['shares'] is not None and r['shares']>=0 and start<=r['date']<=end]
        return {'kind':'etf_shares','symbol':'SZSE','source':'深圳证券交易所 ETF规模日报','source_url':'https://www.szse.cn/market/fund/volume/etf/index.html','unit':'份','method':'基金规模(份)不再乘万；按来源日期保留，未人为平移至别的交易日。沪深份额统计时点可能不同，来源日期对齐不代表同时成交。','rows':rows,'request':p}
    if kind=='nav':
        code=p['code'];df=ak.fund_etf_fund_info_em(fund=code,start_date=start.replace('-',''),end_date=end.replace('-',''))
        rows=[{'date':clean_date(r['净值日期']),'nav':number(r['单位净值'])} for r in records(df)]
        rows=[r for r in rows if r['nav'] is not None and r['nav']>0 and start<=r['date']<=end]
        return {'kind':'etf_nav','symbol':code,'source':'东方财富基金净值 / AKShare','source_url':f'https://fundf10.eastmoney.com/jjjz_{code}.html','unit':'元/份','method':'单位净值，按净值所属日期匹配；缺失不以前值或收盘价替代。披露时间不等于净值日期，不作时点回测。','rows':rows,'request':p}
    if kind=='holders':
        import requests
        from bs4 import BeautifulSoup
        code=p['code'];url=f'https://stock.finance.sina.com.cn/fundInfo/view/FundInfo_JJCYR.php?symbol={code}'
        r=requests.get(url,timeout=15);r.raise_for_status();r.encoding='gb18030';soup=BeautifulSoup(r.text,'html.parser')
        periods=[o.get('value','').strip() or o.get_text(strip=True) for o in soup.select('select option')]
        periods=[v for v in periods if re.fullmatch(r'\d{4}-\d{2}-\d{2}',v)]
        period=periods[0] if periods else None
        rows=[]
        for table in soup.find_all('table'):
            if '持有人名称' not in table.get_text():continue
            candidate=[]
            for tr in table.find_all('tr'):
                cells=[c.get_text(' ',strip=True) for c in tr.find_all(['td','th'],recursive=False)]
                if len(cells)==4 and cells[0].isdigit() and number(cells[2]) is not None:
                    candidate.append({'code':code,'holder':cells[1],'shares':number(cells[2]),'ratio_pct':number(cells[3]),'report_date':period,'publication_date':None,'verification':'vendor_unverified'})
            if candidate:rows=candidate;break
        if not rows:raise ValueError('未解析到持有人表格')
        return {'kind':'etf_holders','symbol':code,'source':'新浪基金十大持有人','source_url':url,'unit':'份 / %','method':'网页报告期与持有人表一并解析；来源未给公告日，保持未知，须原始定期报告核验。','rows':rows,'request':p}
    raise ValueError('未知 ETF 数据任务')

if __name__=='__main__':
    try:
        with contextlib.redirect_stdout(io.StringIO()):result=fetch(json.loads(sys.argv[1]))
        print(json.dumps({'ok':True,'data':result},ensure_ascii=True,allow_nan=False))
    except Exception as e:print(json.dumps({'ok':False,'error':f'{type(e).__name__}: {e}'},ensure_ascii=True))
