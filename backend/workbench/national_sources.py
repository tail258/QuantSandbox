"""Public inputs for national-team footprint research; no account identity inference."""
from io import BytesIO
import re
import warnings
import requests
import pandas as pd
from .providers import clean_date,number,records

HEADERS={'User-Agent':'Mozilla/5.0','Referer':'https://www.sse.com.cn/'}

def margin_sse(raw,date):
    rows=[]
    for r in raw:
        if clean_date(r.get('opDate'))!=date:continue
        balance=number(r.get('rzye'));buy=number(r.get('rzmre'));repay=number(r.get('rzche'))
        if balance is None or balance<0:continue
        rows.append({'date':date,'code':str(r['stockCode']).zfill(6),'name':r.get('securityAbbr',''),'balance':balance,'buy':buy,'repay':repay,'net':buy-repay if buy is not None and repay is not None else None,'net_basis':'买入额−偿还额','market':'SSE'})
    return rows

def margin_szse(df,date):
    # Export column captions can include units. Values are already yuan.
    cols={str(c).split('(')[0].split('（')[0]:c for c in df.columns}
    required=['证券代码','证券简称','融资余额','融资买入额']
    if not all(c in cols for c in required):raise ValueError('深交所融资表缺少必要列')
    rows=[]
    for r in records(df):
        balance=number(r[cols['融资余额']]);buy=number(r[cols['融资买入额']])
        if balance is None or balance<0:continue
        rows.append({'date':date,'code':str(r[cols['证券代码']]).zfill(6),'name':str(r[cols['证券简称']]),'balance':balance,'buy':buy,'repay':None,'net':None,'net_basis':'相邻交易日余额差待计算','market':'SZSE'})
    return rows

def fetch(p):
    kind=p['kind'];start=p.get('start','');end=p.get('end','')
    if kind=='national_index':
        r=requests.get('https://web.ifzq.gtimg.cn/appstock/app/fqkline/get',params={'param':f'sh000300,day,{start},{end},640,qfq'},timeout=15);r.raise_for_status()
        data=r.json().get('data',{}).get('sh000300',{});raw=data.get('day',data.get('qfqday',[]))
        rows=[{'date':v[0],'close':number(v[2])} for v in raw if start<=v[0]<=end and number(v[2]) is not None]
        if not rows:raise ValueError('沪深300交易日历返回为空')
        return {'kind':'etf_index','symbol':'sh000300','source':'腾讯沪深300历史日线','source_url':'https://gu.qq.com/sh000300/zs','unit':'点','method':'沪深300收盘与交易日历；用于日频对齐。腾讯指数收盘精度与其他供应商可能不同。','rows':rows,'request':p}
    if kind=='margin_sse':
        url='https://query.sse.com.cn/marketdata/tradedata/queryMargin.do'
        r=requests.get(url,params={'isPagination':'true','tabType':'mxtype','detailsDate':end.replace('-',''),'stockCode':'','pageHelp.pageSize':'5000','pageHelp.pageNo':'1'},headers=HEADERS,timeout=15);r.raise_for_status();raw=r.json()
        return {'kind':'national_margin','symbol':'SSE','source':'上交所融资融券交易明细','source_url':'https://www.sse.com.cn/market/othersdata/margin/detail/','unit':'元','method':'融资净新增=融资买入额−融资偿还额；保留交易日期，不代表投资者身份。','rows':margin_sse(raw.get('result') or [],end),'request':p}
    if kind=='margin_szse':
        url='https://www.szse.cn/api/report/ShowReport'
        r=requests.get(url,params={'SHOWTYPE':'xlsx','CATALOGID':'1837_xxpl','txtDate':end,'TABKEY':'tab2'},timeout=15);r.raise_for_status()
        with warnings.catch_warnings():
            warnings.simplefilter('ignore',UserWarning);df=pd.read_excel(BytesIO(r.content),dtype={'证券代码':str})
        return {'kind':'national_margin','symbol':'SZSE','source':'深交所融资融券交易明细','source_url':'https://www.szse.cn/disclosure/margin/margin/index.html','unit':'元','method':'融资余额/买入额原值；未单列偿还额，净新增使用相邻交易日融资余额差，缺前日留空。日期为查询交易日，来源导出不含逐行日期。','rows':margin_szse(df,end),'request':p}
    if kind=='etf_quotes':
        import akshare as ak
        code=p['code'];symbol=('sh' if code.startswith('5') else 'sz')+code
        try:
            df=ak.fund_etf_hist_em(symbol=code,period='daily',start_date=start.replace('-',''),end_date=end.replace('-',''),adjust='')
            rows=[{'date':clean_date(r['日期']),'close':number(r['收盘']),'turnover':number(r['成交额']),'volume_lots':number(r['成交量'])} for r in records(df)]
            if not rows:raise ValueError('东方财富ETF日线为空')
            return {'kind':'national_quotes','symbol':code,'source':'东方财富ETF日线 / AKShare','source_url':f'https://quote.eastmoney.com/{symbol}.html','unit':'价格元 / 成交额元 / 成交量手','method':'不复权日线；原始成交额用于历史分位。除权、拆分等事件可能影响价格可比性。','rows':rows,'request':p}
        except Exception as e:
            r=requests.get('https://web.ifzq.gtimg.cn/appstock/app/fqkline/get',params={'param':f'{symbol},day,{start},{end},640,'},timeout=12);r.raise_for_status()
            raw=r.json().get('data',{}).get(symbol,{}).get('day',[])
            rows=[{'date':v[0],'close':number(v[2]),'turnover':None,'volume_lots':number(v[5])} for v in raw if start<=v[0]<=end]
            if not rows:raise ValueError('ETF两个行情来源均未获取到有效日线')
            return {'kind':'national_quotes','symbol':code,'source':'腾讯ETF不复权日线（成交额缺失）','source_url':f'https://gu.qq.com/{symbol}/gp','unit':'价格元 / 成交量手','method':'东方财富失败后使用腾讯价格；此接口无成交额，保持缺失，不用价格×成交量估算替代。除权、拆分可能影响可比性。','upstream_warning':str(e),'rows':rows,'request':p}
    if kind=='constituents':
        code=p['code'];url=f'https://oss-ch.csindex.com.cn/static/html/csindex/public/uploads/file/autofile/cons/{code}cons.xls'
        r=requests.get(url,timeout=15);r.raise_for_status();df=pd.read_excel(BytesIO(r.content))
        if len(df.columns)!=9:raise ValueError('中证成分目录结构变化')
        df.columns=['date','index_code','index_name','index_en','code','name','name_en','market','market_en']
        rows=[{'date':clean_date(str(r['date'])),'code':str(r['code']).zfill(6),'name':r['name'],'market':'SSE' if '上海' in r['market'] else 'SZSE'} for r in records(df)]
        return {'kind':'national_constituents','symbol':code,'source':'中证指数公司最新成分目录','source_url':url,'unit':'证券名单','method':'使用此次获取的固定成分名单汇总整段历史；不代表历史各日当时成分。缺融资记录不填零，不作为历史时点回测。','rows':rows,'request':p}
    if kind=='report_list':
        code=p['code'];url='https://api.fund.eastmoney.com/f10/JJGG'
        r=requests.get(url,params={'fundcode':code,'pageIndex':1,'pageSize':100,'type':3},headers={'Referer':f'https://fundf10.eastmoney.com/jjgg_{code}_3.html','User-Agent':'Mozilla/5.0'},timeout=15);r.raise_for_status();data=r.json()
        if data.get('ErrCode') not in [0,None]:raise ValueError('基金报告目录接口失败')
        rows=[]
        for v in data.get('Data') or []:
            title=v['TITLE'];match=re.search(r'(20\d{2})年(年度报告|中期报告|半年度报告)',title)
            if not match or '摘要' in title:continue
            period=match[1]+('-12-31' if match[2]=='年度报告' else '-06-30');published=clean_date(v['PUBLISHDATE'])
            if published>end:continue
            rows.append({'date':published,'code':code,'title':title,'report_date':period,'publication_date':published,'report_id':v['ID'],'source_url':f'https://fundf10.eastmoney.com/jjgg_{code}_{v["ID"]}.html','pdf_url':f'https://pdf.dfcfw.com/pdf/H2_{v["ID"]}_1.pdf','verification':'catalog_only'})
        return {'kind':'national_report_list','symbol':code,'source':'东方财富基金定期报告目录','source_url':f'https://fundf10.eastmoney.com/jjgg_{code}_3.html','unit':'公告','method':'仅目录，不代表已读取原文；公告日期和统计期末分别记录。报告原文核实后独立登记。','rows':rows,'request':p}
    raise ValueError('未知国家队观察数据任务')
