import {useEffect,useRef,useState,type FormEvent} from 'react';
import type {Row} from '../api';
import {Note,LoadingButton} from '../components';
import Drawer from './Drawer';
import {initialDraft,parseTickers} from './model';
import {createResponseScope} from '../response-scope';

export function StrategyFields({catalog,strategy,onChange}:{catalog:Row|null;strategy:Row;onChange:(value:Row)=>void}){
 const selected=catalog?.strategies.find((s:Row)=>s.name===strategy.name);
 return <><label>策略<select value={strategy.name} onChange={e=>{const spec=catalog?.strategies.find((s:Row)=>s.name===e.target.value);onChange({name:e.target.value,parameters:Object.fromEntries((spec?.parameters||[]).map((p:Row)=>[p.key,p.default]))})}}>{catalog?.strategies.map((s:Row)=><option value={s.name} key={s.name}>{s.label}</option>)}</select></label><div className="controls wrap">{selected?.parameters.map((p:Row)=><label key={p.key}>{p.label}<input type="number" required min={p.min} max={p.max} step={p.step||1} value={strategy.parameters[p.key]??p.default} onChange={e=>onChange({...strategy,parameters:{...strategy.parameters,[p.key]:Number(e.target.value)}})}/></label>)}</div></>;
}

export default function Composer({catalog,project,quoteSets,busy,onClose,onSubmit,onPlan}:{catalog:Row|null;project:Row|null;quoteSets:Row[];busy:boolean;onClose:()=>void;onSubmit:(config:Row,snapshots:string[])=>Promise<void>;onPlan:(prompt:string,config:Row)=>Promise<Row|null>}){
 const initial=()=>initialDraft(catalog,project,quoteSets);
 const [draft,setDraft]=useState(initial),[prompt,setPrompt]=useState(''),[planNote,setPlanNote]=useState('');
 const planScope=useRef(createResponseScope());
 const {config,tickers,snapshots}=draft;
 // Only the new draft follows the project. An archived run remains unchanged.
 useEffect(()=>{setDraft(initial());setPlanNote('');return()=>planScope.current.invalidate()},[project?.id]);
 const setConfig=(value:Row)=>setDraft(d=>({...d,config:value}));
 const demoSet=new Set((catalog?.tickers||[]).map((row:Row)=>row.ticker));
 const unsupported=config.source==='demo'?parseTickers(tickers).filter(t=>!demoSet.has(t)):[];
 function pickSnapshot(id:string,checked:boolean){
  const next=checked?[...snapshots,id]:snapshots.filter(s=>s!==id),chosen=quoteSets.filter(s=>next.includes(s.id));
  setDraft(d=>({...d,snapshots:next,tickers:chosen.length?chosen.map(s=>s.symbol).join(','):d.tickers,config:chosen.length?{...d.config,start_date:chosen.map(s=>s.start).sort().at(-1),end_date:chosen.map(s=>s.end).sort()[0]}:d.config}));
 }
 async function submit(event:FormEvent){event.preventDefault();await onSubmit({...config,tickers:parseTickers(tickers)},snapshots)}
 return <Drawer title="建立基线回测" onClose={onClose}><p className="muted">{project?`研究项目：${project.name}`:'独立实验；之后可关联到研究项目。'}</p><form onSubmit={submit} className="simulation-form"><label>实验名称<input required value={config.name} onChange={e=>setConfig({...config,name:e.target.value})}/></label><label>数据来源<select value={config.source} onChange={e=>setConfig({...config,source:e.target.value})}><option value="snapshot">研究数据固定快照</option><option value="akshare">AKShare 真实行情</option><option value="demo">合成演示行情</option></select></label>
 {config.source==='demo'&&<Note>合成演示行情，覆盖 2019-01-01 至 2026-09-18；仅用于操作与规则验证。</Note>}{unsupported.length>0&&<Note tone="warn">当前证券 {unsupported.join('、')} 没有合成演示行情。请明确选择真实行情或固定快照；证券不会自动替换。<div className="actions"><button type="button" className="secondary" onClick={()=>setConfig({...config,source:'akshare'})}>改用真实行情</button><button type="button" className="secondary" onClick={()=>setConfig({...config,source:'snapshot'})}>选择固定快照</button></div></Note>}
 {config.source==='snapshot'&&<fieldset className="simulation-snapshots"><legend>固定输入快照</legend><small>不重新取数。各证券需覆盖实验区间，指标预热使用快照内已有历史。</small>{quoteSets.length?quoteSets.map(s=><label className="checkbox" key={s.id}><input type="checkbox" checked={snapshots.includes(s.id)} onChange={e=>pickSnapshot(s.id,e.target.checked)}/><span>{s.symbol}<small>{s.start} 至 {s.end}</small><code>{s.id}</code></span></label>):<p>暂无未复权股票行情，请先在数据中心获取。</p>}</fieldset>}
 <label>证券代码（逗号分隔）<input required value={tickers} onChange={e=>setDraft(d=>({...d,tickers:e.target.value}))} placeholder="000858,600036"/></label><div className="controls wrap"><label>开始日期<input type="date" required value={config.start_date} onChange={e=>setConfig({...config,start_date:e.target.value})} onInput={e=>setConfig({...config,start_date:e.currentTarget.value})}/></label><label>结束日期<input type="date" required value={config.end_date} onChange={e=>setConfig({...config,end_date:e.target.value})} onInput={e=>setConfig({...config,end_date:e.currentTarget.value})}/></label></div>
 <StrategyFields catalog={catalog} strategy={config.strategy} onChange={strategy=>setConfig({...config,strategy})}/><details className="cost-details"><summary>资金、仓位与交易成本</summary><div className="controls wrap">{[['initial_cash','初始资金（元）',1000,1e10,1000],['position_size','单标的仓位（0–1）',.01,1,.01],['commission_rate','佣金率',0,.1,.0001],['min_commission','最低佣金（元）',0,10000,1],['tax_rate','卖出税率',0,.1,.0001],['slippage_bps','双边滑点（bps）',0,1000,1]].map(([key,label,min,max,step])=><label key={String(key)}>{label}<input type="number" required min={Number(min)} max={Number(max)} step={Number(step)} value={config.account[String(key)]} onChange={e=>setConfig({...config,account:{...config.account,[String(key)]:Number(e.target.value)}})}/></label>)}</div></details><p className="muted">收盘信号在后续可交易日开盘执行。未复权行情尚未记账分红送转。</p><div className="simulation-drawer-footer"><LoadingButton type="submit" busy={busy} disabled={!catalog||!!unsupported.length||config.source==='snapshot'&&!snapshots.length}>提交回测</LoadingButton><button type="button" className="secondary" onClick={onClose}>返回研究</button></div></form>
 <details className="cost-details"><summary>用研究指令生成配置草稿</summary><label>研究指令<input value={prompt} onChange={e=>setPrompt(e.target.value)} placeholder="例如：使用动量策略，初始资金100万"/></label><button className="secondary" disabled={!prompt||busy} onClick={async()=>{const ticket=planScope.current.begin();const planned=await onPlan(prompt,config);if(planned&&planScope.current.isCurrent(ticket)){setDraft(d=>({...d,config:planned.config,tickers:planned.config.tickers.join(',')}));setPlanNote(planned.explanation+' '+(planned.warnings||[]).join(' '))}}}>生成草稿</button><small>本地规则解析，仅填写配置。</small>{planNote&&<Note>{planNote}</Note>}</details></Drawer>;
}
