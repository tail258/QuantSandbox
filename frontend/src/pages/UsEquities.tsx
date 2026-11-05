import { useEffect, useRef, useState } from 'react'
import { api, download, fmt, type Row } from '../api'
import { t, useLocale } from '../i18n'
import { useProject } from '../workspace/ProjectContext'
import './us-equities.css'
import { Chart } from '../components'
const metrics = ['revenue','net_income','operating_income','operating_cashflow','capex','free_cashflow','assets','liabilities','equity','diluted_eps']
const labels = ['收入','净利润','营业利润','经营现金流','资本支出','自由现金流','资产','负债','权益','稀释每股收益']
function safeUrl(value: unknown) { try { const u = new URL(String(value)); return u.protocol === 'https:' ? u.href : undefined } catch { return undefined } }
export default function UsEquities() {
  useLocale()
  const { activeProject, reloadProjects } = useProject()
  const [data,setData] = useState<Row | null>(null)
  const [busy,setBusy] = useState(false)
  const [error,setError] = useState(false)
  const [saved,setSaved] = useState('')
  const [showImport,setShowImport] = useState(false)
  const [text,setText] = useState('')
  const [source,setSource] = useState('')
  const sequence = useRef(0)
  const currentProject = useRef(activeProject?.id)
  currentProject.current = activeProject?.id
  useEffect(()=>setSaved(''),[activeProject?.id])
  useEffect(() => { let alive=true; void api('/us/catalog').catch(()=>{}); api('/us/company/MCD').then(d=>{if(alive)setData(d)}).catch(()=>{if(alive)setError(true)}); return()=>{alive=false; sequence.current++} },[])
  async function action(kind: 'refresh'|'prices'|'save') {
    const generation=++sequence.current
    const projectId=activeProject?.id
    setBusy(true); setError(false); setSaved('')
    try {
      const result=await api('/us/company/MCD/'+kind,kind==='prices'?{text,source_url:source}:kind==='save'?{project_id:projectId,snapshot_ids:data?.snapshot_ids || []}:{})
      if(generation!==sequence.current)return
      if(kind==='save'){if(currentProject.current===projectId)setSaved(result.id);void reloadProjects()}else{setData(result);if(kind==='prices')setShowImport(false)}
    } catch {if(generation===sequence.current)setError(true)} finally {if(generation===sequence.current)setBusy(false)}
  }
  const rows: Row[] = (data?.financials || []).slice(0, 6)
  return <main className="us-equities">
    <header><div><p className="us-eyebrow">NYSE · MCD · USD</p><h1>{t('美股研究')} · {t('麦当劳')}</h1><p>{t('特许经营、现金流与资本配置')}</p></div><button disabled={busy} onClick={()=>void action('refresh')}>{busy?t('处理中…'):t('获取 SEC 财报')}</button></header>
    {error && <p role="alert">{t('美股数据操作失败，请检查 SEC 联系方式配置或数据来源后重试。')}</p>}
    <section className="panel"><h2>{t('研究重点')}</h2><p><a href="https://corporate.mcdonalds.com/corpmcd/investors.html" target="_blank" rel="noreferrer">{t('麦当劳投资者关系')}</a> · <a href="https://www.sec.gov/edgar/browse/?CIK=63908" target="_blank" rel="noreferrer">SEC EDGAR</a></p><p>{t('核对特许经营占比、可比销售、门店增长、营业利润率、自由现金流、回购与债务。')}</p><p>{t('年度财务数据 · USD；每股收益为 USD/股。当前修订财报不代表历史时点可用版本。')}</p></section>
    {!rows.length ? <section className="panel"><h2>{t('尚无财务快照')}</h2><p>{t('点击获取 SEC 财报。首次获取需配置含有效联系邮箱的 QUANTSANDBOX_SEC_USER_AGENT。')}</p></section> : <section className="panel"><h2>{t('年度财务')}</h2><p>{t('显示最近六个年度；完整原始事实保留在快照和导出中。')}</p><div className="us-table"><table><thead><tr><th>{t('指标')}</th>{rows.map((r,i)=><th key={i}>{r.period_end}</th>)}</tr></thead><tbody>{metrics.map((m,i)=><tr key={m}><th>{t(labels[i])} · {m==='diluted_eps'?t('美元/股'):t('百万美元')}</th>{rows.map((r,j)=><td key={j}>{fmt((m==='free_cashflow'?r.free_cashflow:r.metrics?.[m]?.value) == null ? null : (m==='free_cashflow'?r.free_cashflow:r.metrics?.[m]?.value)/(m==='diluted_eps'?1:1e6))}</td>)}</tr>)}</tbody></table></div></section>}
    <section className="panel"><h2>{t('披露文件')}</h2>{(data?.filings || []).map((f:Row,i:number)=><p key={i}>{f.form} · {f.filed} · {f.report_date} {safeUrl(f.source_url)&&<a href={safeUrl(f.source_url)} target="_blank" rel="noreferrer">{t('查看原文')}</a>}</p>)}<details><summary>{t('来源与快照')}</summary><pre>{JSON.stringify({fetched_at:data?.fetched_at,snapshots:data?.snapshots,snapshot_ids:data?.snapshot_ids,facts:rows.map(r=>r.metrics),snapshot:data?.snapshot ? {id:data.snapshot.id,fetched_at:data.snapshot.fetched_at,source_url:data.snapshot.source_url}:null,last_attempt:data?.last_attempt,warnings:data?.warnings},null,2)}</pre></details></section>
    <section className="panel"><h2>{t('行情')}</h2><p>{t('仅供研究，不支持美股回测。行情价格须为未复权 USD，成交量为股。')}</p><p>{t('导入日线 CSV，保留来源和获取时间。缺失值不会补零。')}</p><button onClick={()=>setShowImport(!showImport)}>{t('导入行情')}</button>{showImport&&<form onSubmit={e=>{e.preventDefault();void action('prices')}}><label>{t('来源网址')}<input type="url" required value={source} onChange={e=>setSource(e.target.value)}/></label><label>CSV<textarea required value={text} onChange={e=>setText(e.target.value)}/></label><button type="button" onClick={()=>download('MCD-template.csv','date,open,high,low,close,volume\n','text/csv')}>{t('下载模板')}</button><button disabled={busy}>{t('保存行情快照')}</button></form>}{data?.prices?.rows?.length > 0 && <><Chart rows={data!.prices.rows} lines={[{key:'close',name:t('收盘价')}]} unit="USD"/><p>{data!.prices.rows[0]?.date} — {data!.prices.rows.at(-1)?.date}</p><p>{t('来源网址')}: <a href={safeUrl(data!.prices.source_url)} target="_blank" rel="noreferrer">{data!.prices.source_url}</a> · {t('获取时间（UTC）')}: {data!.prices.fetched_at}</p></>}<p>{t('行情样本数')}: {data?.prices?.rows?.length || 0}</p></section>
    <button disabled={busy || !data?.snapshot_ids?.length} onClick={()=>void action('save')}>{t('保存研究记录')}</button>{saved&&<p role="status">{t('已保存')} · <a href={'/api/research/export/'+encodeURIComponent(saved)}>{saved}</a></p>}
  </main>
}
