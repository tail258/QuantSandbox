import {useState} from 'react'
import {api,fmt,type Row} from './api'
import {t,useLocale} from './i18n'
import {Panel} from './components'
import {quotePrice} from './marketFormat'
import './EtfGettingStarted.css'

export default function EtfGettingStarted() {
 useLocale()
 const [open,setOpen]=useState(true),[demo,setDemo]=useState<Row|null>(null),[busy,setBusy]=useState(false),[error,setError]=useState('')
 const loadDemo=async()=>{setBusy(true);setError('');try{setDemo(await api('/etf/intraday-demo'))}catch(e){setError(e instanceof Error?e.message:String(e))}finally{setBusy(false)}}
 return <Panel title={t('ETF使用引导')} className="etf-getting-started">
  <button aria-expanded={open} onClick={()=>setOpen(!open)}>{t(open?'收起引导':'打开引导')}</button>
  {open&&<div>
   <p>{t('先选研究项目，再核对证券与来源日期。首次使用可先查看离线合成演示。')}</p>
   <ol>
    <li>{t('刷新轻量行情：获取报价与累计成交额；保留来源精度和时间。')}</li>
    <li>{t('更新历史基准：单独获取5分钟数据，以完整时点比较此前20日；检查有效样本与缺口。')}</li>
    <li>{t('立即刷新与每日15:30：更新日频份额和净值，用于估算申赎；不等同于盘中成交额。')}</li>
   </ol>
   <p>{t('自动取数仅在本地服务运行时执行。缺失值保留为空，成交与申赎不能归因具体机构。')}</p>
  </div>}
  <div className="actions"><button disabled={busy} onClick={()=>demo?setDemo(null):void loadDemo()}>{t(demo?'关闭合成演示':busy?'正在加载演示':'查看合成演示')}</button></div>
  {error&&<p role="alert">{error}</p>}
  {demo&&<section aria-label={t('合成演示')}>
   <h3>{t('合成演示 · 人工数据')}</h3>
   <p>{t('固定演示时钟与人工工作日日历，不代表真实行情或真实交易日。仅在内存计算，不联网，不写入缓存、项目或笔记。')}</p>
   <p>{t('演示时钟')} · {demo.clock} · DEMO-ETF</p>
   <div className="table-wrap"><table><thead><tr>{['演示价格','成交额比','有效样本 / 20','完整5分钟时点','本日同时点成交额（元）','历史均额（元）'].map(x=><th key={x}>{t(x)}</th>)}</tr></thead><tbody><tr>
    <td>{quotePrice(demo.inputs.quote)}</td><td>{fmt(demo.comparison.ratio)}</td><td>{demo.comparison.sample_count} / 20</td><td>{demo.comparison.boundary}</td><td>{fmt(demo.comparison.current_amount)}</td><td>{fmt(demo.comparison.historical_mean_amount)}</td>
   </tr></tbody></table></div>
   <p>{t('演示解读：1.50表示完整时点成交额为此前20个人工日期均值的1.5倍，不代表净流入。')}</p>
   <details><summary>{t('合成输入与复算证据')}</summary><p>{demo.source} · SHA-256 · {demo.input_sha256}</p><p>{demo.inputs.history.rows.length} {t('条人工5分钟记录')}</p><pre>{JSON.stringify(demo,null,2)}</pre></details>
  </section>}
 </Panel>
}
