import {useEffect,useRef,useState} from 'react'
import {api,fmt,type Row} from './api'
import {t,useLocale} from './i18n'
import {Panel} from './components'
import './EtfIntraday.css'
import {quotePrice} from './marketFormat'
const statusText=(value:string)=>t(({queued:'排队中',running:'运行中',pending:'排队中',completed:'已完成',completed_with_errors:'完成但有错误',failed:'失败',interrupted:'中断',current:'当前',stale:'已陈旧',after_close_snapshot:'盘后快照',complete:'完整',provisional:'暂定',insufficient:'样本不足',unavailable:'不可用',unverified:'日历未核验',verified_index_sessions:'指数日历覆盖',observed_source_sessions_only:'仅观测到的来源日期',incomplete_or_duplicate_bars:'分钟数据不完整或重复'} as Record<string,string>)[value]||value)
const active=(job:Row)=>['queued','running','pending'].includes(job.status)
export function intradayEligible(items:Row[],clock=new Date()) {
 const parts=new Intl.DateTimeFormat('sv-SE',{timeZone:'Asia/Shanghai',year:'numeric',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',hourCycle:'h23'}).format(clock)
 const date=parts.slice(0,10),time=parts.slice(11,16)
 const weekday=new Date(date+'T00:00:00Z').getUTCDay()
 return weekday!==0&&weekday!==6&&((time>='09:30'&&time<'11:30')||(time>='13:00'&&time<'15:00'))&&items.some(i=>i.quote?.source_time?.slice(0,10)===date)
}
export default function EtfIntraday({codes}:{codes:string}) {
 useLocale()
 const [items,setItems]=useState<Row[]>([]),[error,setError]=useState(''),[jobs,setJobs]=useState<Row[]>([]),[auto,setAuto]=useState(false),[tab,setTab]=useState('comparison')
 const generation=useRef(0),pending=useRef(new Set<string>()),cacheVersion=useRef(0)
 const lastBootstrap=useRef<number|null>(null)
 const cache=async(version=generation.current)=>{const request=++cacheVersion.current;const next=await api('/etf/intraday?codes='+encodeURIComponent(codes));if(version===generation.current&&request===cacheVersion.current){setItems(next.items||[]);setError('')}}
 const refresh=async(history=false)=>{
  const key=history?'history':'quote',version=generation.current
  if(!codes||pending.current.has(key))return
  pending.current.add(key)
  try{const job=await api('/etf/intraday/refresh',{codes:codes.split(',').filter(Boolean),history,force:false});if(version!==generation.current)return;setJobs(old=>[...old.filter(j=>j.id!==job.id),job,...(job.bar_job_id&&!old.some(j=>j.id===job.bar_job_id)?[{id:job.bar_job_id,status:'queued'}]:[])]);await cache(version)}
  catch(e){if(version===generation.current)setError(String(e instanceof Error?e.message:e))}
  finally{if(version===generation.current)pending.current.delete(key)}
 }
 useEffect(()=>{generation.current++;pending.current.clear();setItems([]);setJobs([]);setError('');const version=generation.current;void cache(version).catch(e=>{if(version===generation.current)setError(String(e))});return()=>{generation.current++;cacheVersion.current++}},[codes])
 useEffect(()=>{
  if(!jobs.some(active))return
  let cancelled=false,inflight=false;const version=generation.current
  const timer=setInterval(async()=>{if(inflight)return;inflight=true;try{
   const updates=await Promise.all(jobs.filter(active).map(j=>api('/etf/intraday/jobs/'+j.id)))
   if(cancelled||version!==generation.current)return
   setJobs(old=>{const map=new Map(old.map(j=>[j.id,j]));for(const j of updates){map.set(j.id,j);if(j.bar_job_id&&!map.has(j.bar_job_id))map.set(j.bar_job_id,{id:j.bar_job_id,status:'queued'})}return [...map.values()]})
   if(updates.some(j=>!active(j)))await cache(version)
  }catch(e){if(!cancelled)setError(String(e))}finally{inflight=false}},2000)
  return()=>{cancelled=true;clearInterval(timer)}
 },[jobs,codes])
 useEffect(()=>{
  const tick=()=>{
   if(!auto||document.visibilityState!=='visible')return
   const clock=new Date()
   if(intradayEligible(items,clock)){void refresh();return}
   // A weekday is only a candidate session: retry old/empty sources slowly.
   const today=new Intl.DateTimeFormat('sv-SE',{timeZone:'Asia/Shanghai'}).format(clock)
   if(intradayEligible([{quote:{source_time:today}}],clock)&&(lastBootstrap.current===null||clock.getTime()-lastBootstrap.current>=300000)){
    lastBootstrap.current=clock.getTime();void refresh()
   }
  }
  const timer=setInterval(tick,20000);document.addEventListener('visibilitychange',tick)
  return()=>{clearInterval(timer);document.removeEventListener('visibilitychange',tick)}
 },[auto,items,codes])
 const headers=tab==='comparison'?['证券','成交额比','有效样本 / 20','完整5分钟时点','本日同时点成交额（元）','历史均额（元）','时效']:['证券','价格','涨跌幅','累计成交额（元）','来源时间','时效']
 return <Panel title={t('ETF盘中行情与同时点成交额')}>
  <div className="actions"><button disabled={!codes} onClick={()=>void refresh()}>{t('刷新轻量行情')}</button><button disabled={!codes} onClick={()=>{void refresh(true);if(!items.some(i=>i.quote))void refresh()}}>{t('更新历史基准')}</button></div>
  <details><summary>{t('盘中自动更新设置')}</summary><label><input type="checkbox" checked={auto} onChange={e=>setAuto(e.target.checked)}/>{t('交易时段每20秒更新')}</label><p>{t('仅来源时间有效且页面可见时轮询；午休与盘后暂停。历史基准单独更新。')}</p><p>{t('隔夜或缺失报价在工作日交易时段每5分钟尝试恢复；工作日不代表交易所开市，未获新来源前保留陈旧状态。周末与隐藏页面暂停。')}</p></details>
  {jobs.map(job=><p key={job.id} role="status">{t('历史与行情任务')} · {statusText(job.status||'queued')} {job.completed??''}/{job.total??''}</p>)}
  {error&&<p role="alert">{t('更新失败，保留旧数据（已陈旧）')} · {error}</p>}
  <div className="etf-intraday-tabs" role="tablist" aria-label={t('盘中视图')}><button role="tab" aria-selected={tab==='comparison'} onClick={()=>setTab('comparison')}>{t('同时点比较')}</button><button role="tab" aria-selected={tab==='quotes'} onClick={()=>setTab('quotes')}>{t('轻量行情')}</button></div>
  <p>{t('腾讯提供报价累计额；东方财富提供本日及历史5分钟成交额。来源口径可能存在差异。')}</p>
  <div className="table-wrap etf-intraday-table"><table><thead><tr>{headers.map(x=><th key={x}>{t(x)}</th>)}</tr></thead><tbody>{items.map(item=>{const q=item.quote||{},c=item.comparison||{};return <tr key={item.code}><td>{item.code}</td>{tab==='comparison'?<><td>{fmt(c.ratio)}</td><td>{c.sample_count??'—'} / {c.target_samples??20} · {statusText(c.status||'unavailable')}</td><td>{c.boundary||'—'}</td><td>{fmt(c.current_amount)}</td><td>{fmt(c.historical_mean_amount)}</td><td>{c.stale||error?t('已陈旧'):statusText('current')} · {statusText(c.calendar_status||'unverified')}</td></>:<><td>{quotePrice(q)}</td><td>{q.change_pct==null?'—':fmt(q.change_pct)+'%'}</td><td>{fmt(q.amount)}</td><td>{q.source_time||'—'}</td><td>{item.stale||error?t('已陈旧'):statusText(q.freshness||'未记录')}</td></>}</tr>})}</tbody></table></div>
  <details><summary>{t('样本、缺口与来源证据')}</summary>{items.map(i=><div key={i.code}><strong>{i.code}</strong><p>{t('单位')} · CNY · {t('价格口径')} · {t('未复权')} · {t('历史窗口')} · {t(i.comparison?.calendar_status==='verified_index_sessions'?'此前20个指数日历日期':'此前20个来源日期（日历未核验）')} · {i.comparison?.window_start||'—'} → {i.comparison?.window_end||'—'}</p><details><summary>{t('实际有效样本日期')}</summary><p>{(i.comparison?.sample_dates||[]).join('、')||'—'}</p></details><p>{t('缺口')} · {(i.comparison?.excluded_days||[]).map((d:Row)=>d.date+' '+statusText(d.reason)).join('；')||'—'}</p><p>{t('报价来源')} · {i.quote_source||'—'} · {i.quote_snapshot_id||'—'} · {i.quote_fetched_at||'—'}</p><p>{t('5分钟来源')} · {i.history_source||'—'} · {i.history_snapshot_id||'—'} · {i.history_fetched_at||'—'}</p><pre>{JSON.stringify(i.provenance,null,2)}</pre>{(i.errors||[]).map((e:string)=><p key={e}>{e}</p>)}</div>)}</details>
  <p>{t('累计报价与完整5分钟成交额分别展示；成交额比较不代表申赎或任何机构交易。')}</p>
 </Panel>
}
