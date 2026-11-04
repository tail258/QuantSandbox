import {t,useLocale} from '../i18n';
import {useState,type FormEvent} from 'react';
import type {Row} from '../api';
import {Note,LoadingButton} from '../components';
import Drawer from './Drawer';
import {StrategyFields} from './Composer';
import {cloneConfig,isSimulation} from './model';

export default function Comparison({active,catalog,date,busy,blind,onClose,onSubmit}:{active:Row;catalog:Row|null;date:string;busy:boolean;blind:boolean;onClose:()=>void;onSubmit:(type:string,body:Row)=>Promise<void>}){
 useLocale();
 const [type,setType]=useState(active.kind==='branch'?'branch':'pressure'),[name,setName]=useState(t("仓位对照")),[forkDate,setForkDate]=useState(date),[position,setPosition]=useState(.5),[changeStrategy,setChangeStrategy]=useState(false),[strategy,setStrategy]=useState<Row>(cloneConfig(active.config.strategy)),[parameter,setParameter]=useState(''),[values,setValues]=useState(''),[training,setTraining]=useState(120),[testing,setTesting]=useState(40);
 async function submit(event:FormEvent){
  event.preventDefault();
  const body:Row=type==='branch'?{name,fork_date:forkDate,account:{position_size:position},...(changeStrategy?{strategy}:{})}:{kind:type};
  if(type==='parameter'&&parameter){body.parameter=parameter;if(values.trim())body.values=values.split(/[,，\s]+/).filter(Boolean).map(Number)}
  if(type==='walk_forward'){body.training_days=training;body.test_days=testing}
  await onSubmit(type,body);
 }
 return <Drawer title={t("新建对照实验")} onClose={onClose}><p className="muted">{t("基于「{name}」保存的固定行情。对照保留父记录和输入快照。",{name:active.name})}</p><form onSubmit={submit} className="simulation-form"><label>{t("对照类型")}<select value={type} onChange={e=>setType(e.target.value)}>{active.kind==='backtest'&&<><option value="pressure">{t("费用、滑点、延迟与仓位压力")}</option><option value="parameter">{t("参数敏感性")}</option><option value="walk_forward">{t("滚动样本外验证")}</option></>}{isSimulation(active)&&<option value="branch">{t("历史时点分叉")}</option>}</select></label>
 {type==='branch'?<><label>{t("分叉名称")}<input required value={name} onChange={e=>setName(e.target.value)}/></label><div className="controls wrap"><label>{t("分叉日期")}<input required type="date" value={forkDate} min={active.config.start_date} max={active.config.end_date} onChange={e=>setForkDate(e.target.value)} onInput={e=>setForkDate(e.currentTarget.value)}/></label><label>{t("新仓位（0–1）")}<input required type="number" min={.01} max={1} step={.01} value={position} onChange={e=>setPosition(Number(e.target.value))}/></label></div><label className="checkbox"><input type="checkbox" checked={changeStrategy} onChange={e=>setChangeStrategy(e.target.checked)}/>{t("同时修改后续策略")}</label>{changeStrategy&&<StrategyFields catalog={catalog} strategy={strategy} onChange={setStrategy}/>}<Note>{t("分叉日收盘后的调整影响后续订单；从起点确定性重放，分叉之前的历史保持一致。")}</Note></>:<>
 {type==='parameter'&&<><label>{t("参数名")}<input value={parameter} onChange={e=>setParameter(e.target.value)} placeholder={t("留空使用策略默认参数")}/></label><label>{t("候选值")}<input value={values} onChange={e=>setValues(e.target.value)} placeholder={t("例如 5,10,20；留空自动生成")}/></label></>}
 {type==='walk_forward'&&<div className="controls wrap"><label>{t("训练交易日")}<input required type="number" min={30} max={1000} value={training} onChange={e=>setTraining(Number(e.target.value))}/></label><label>{t("测试交易日")}<input required type="number" min={10} max={250} value={testing} onChange={e=>setTesting(Number(e.target.value))}/></label></div>}
 <Note>{type==='parameter'?t("同区间参数比较用于观察敏感性，最优参数不代表样本外有效。"):type==='walk_forward'?t("按训练窗口选参后验证后续区间，目前不含独立最终保留测试集。"):t("在同一份行情上改变费用、滑点、延迟和仓位，核对结果对执行假设的敏感性。")}</Note></>}
 {blind&&<Note tone="warn">{t("请先退出盲测，再创建对照。")}</Note>}<div className="simulation-drawer-footer"><LoadingButton type="submit" busy={busy} disabled={blind}>{t("提交对照")}</LoadingButton><button type="button" className="secondary" onClick={onClose}>{t("返回结果")}</button></div></form></Drawer>;
}
