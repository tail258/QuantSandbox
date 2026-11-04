import {t,useLocale} from '../i18n';
import {useCallback,useEffect,useLayoutEffect,useMemo,useRef,useState} from 'react';
import {Download,Upload,Play,Square,FlaskConical,RefreshCw,Save} from 'lucide-react';
import type {PageProps} from '../App';
import {fmt,type Row} from '../api';
import {request,post,download} from '../http';
import {Panel,Note,Empty,Metric,LoadingButton} from '../components';
import {useProject} from '../workspace/ProjectContext';
import {useSimulationData} from '../simulation/useSimulationData';
import {usePlayback} from '../simulation/usePlayback';
import {kindName,statusName,isSimulation,projectForChild,queryRun,sourceName,sampleCaption} from '../simulation/model';
import Composer from '../simulation/Composer';
import Comparison from '../simulation/Comparison';
import Terminal from '../simulation/Terminal';
import Results from '../simulation/Results';
import '../simulation/simulation.css';

export default function Simulation({status}:PageProps){
 useLocale();
 const records=useSimulationData();
 const {catalog,runs,selectedId,active,notes,setNotes,choose,selection,loadRuns,error,setError,mounted}=records;
 const {activeProject,projects,linkRecord}=useProject();
 const projectId=activeProject?.id||null,projectRef=useRef(projectId);projectRef.current=projectId;
 const playback=usePlayback(active);
 const [composer,setComposer]=useState(false),[comparison,setComparison]=useState(false),[busy,setBusy]=useState(false),[message,setMessage]=useState(''),[tab,setTab]=useState('terminal'),[drafts,setDrafts]=useState<Record<string,{title:string;body:string}>>({});
 const busyRef=useRef(false);
 const draft=drafts[selectedId]||{title:t("实验观察"),body:''};
 const quoteSets=useMemo(()=>status.datasets.filter((s:Row)=>s.kind==='quotes'&&s.request?.adjust==='3'),[status.datasets]);
 const linkedIds=useMemo(()=>new Set(activeProject?.links?.filter((link:Row)=>link.kind==='simulation').map((link:Row)=>link.run_id)||[]),[activeProject]);
 const projectRuns=activeProject?runs.filter(run=>linkedIds.has(run.id)):runs;
 const shownRuns=active&&!projectRuns.some(run=>run.id===active.id)?[active,...projectRuns]:projectRuns;
 useEffect(()=>{
  if(selectedId||queryRun()||!runs.length)return;
  if(new URLSearchParams(location.hash.split('?')[1]||'').get('project')&&!activeProject)return;
  const eligible=activeProject?runs.filter(run=>linkedIds.has(run.id)):runs;
  const prior=localStorage.getItem('quantsandbox.lastRun');
  const wanted=eligible.find(run=>run.id===prior)||eligible[0];
  if(wanted)choose(wanted.id);
 },[runs,selectedId,activeProject,linkedIds,choose]);
 useLayoutEffect(()=>{setComparison(false);if(active)setTab(['pressure','parameter'].includes(active.kind)?'lab':'terminal')},[active?.id]);
 const selectRun=useCallback((id:string)=>{playback.exitBlind();choose(id);setMessage('');setTab('terminal')},[choose,playback.exitBlind]);
 async function act<T,>(operation:()=>Promise<T>):Promise<T|null>{
  if(busyRef.current)return null;
  busyRef.current=true;setBusy(true);setError('');setMessage('');
  const originRun=selection.current,originProject=projectRef.current;
  try{return await operation()}
  catch(e:any){if(mounted.current&&selection.current===originRun&&projectRef.current===originProject)setError(e.message);return null}
  finally{busyRef.current=false;if(mounted.current)setBusy(false)}
 }
 async function associate(run:Row,owner:string|null){
  if(!owner)return;
  try{await linkRecord('simulation',run.id,owner)}
  catch(e:any){if(mounted.current)setMessage('实验已保存；项目关联失败：'+e.message)}
 }
 async function submit(config:Row,snapshots:string[]){
  const owner=projectId;
  await act(async()=>{
   const run=await post<Row>(config.source==='snapshot'?'/bridge/backtests':'/runs',config.source==='snapshot'?{snapshot_ids:snapshots,config,project_id:owner||undefined}:config);
   if(config.source!=='snapshot')await associate(run,owner);
   await loadRuns();
   if(mounted.current&&projectRef.current===owner){selectRun(run.id);setComposer(false)}
   else if(mounted.current)setMessage('实验已保存到提交时的研究项目。');
  });
 }
 async function importFile(file:File){
  const owner=projectId;
  await act(async()=>{
   const raw=await file.text();
   const run=await request<Row>('/import',{method:'POST',body:raw});
   await associate(run,owner);await loadRuns();
   if(mounted.current&&projectRef.current===owner)selectRun(run.id);
  });
 }
 async function compare(type:string,body:Row){
  if(!active)return;
  const parent=active.id,originProject=projectId,owner=projectForChild(activeProject,projects,parent)||null;
  await act(async()=>{
   const run=await post<Row>('/runs/'+parent+(type==='branch'?'/branch':'/experiments'),body);
   await associate(run,owner);await loadRuns();
   if(mounted.current&&selection.current===parent&&projectRef.current===originProject){selectRun(run.id);setComparison(false);setTab(type==='branch'?'terminal':'lab')}
  });
 }
 async function saveNote(){
  const runId=selectedId,captured={...draft};
  await act(async()=>{
   await post('/notes',{run_id:runId,title:captured.title,body:captured.body});
   const saved=await request<Row>('/notes?run_id='+runId);
   if(!mounted.current)return;
   setDrafts(previous=>{const current=previous[runId];return current?.body===captured.body&&current?.title===captured.title?{...previous,[runId]:{...current,body:''}}:previous});
   if(selection.current===runId){setNotes(saved.notes);setMessage('实验笔记已保存。')}
  });
 }
 const onAction=async(operation:()=>Promise<void>)=>{await act(operation)};
 const result=playback.result;
 const canCompare=active?.status==='completed'&&isSimulation(active)&&!playback.session;
 const primaryComparison=tab==='lab'&&canCompare;
 const metrics=playback.metrics||{};
 const updateDraft=(change:Partial<typeof draft>)=>setDrafts(previous=>({...previous,[selectedId]:{...(previous[selectedId]||{title:t("实验观察"),body:''}),...change}}));
 return <div className="simulation-page"><div className="page-title"><div><h1>{t("策略与推演")}</h1><p>{t("从账户路径与成交证据，检验研究中的规则。")}</p></div><div className="actions"><details className="simulation-record-menu"><summary>{t("记录操作")}</summary><div><button className="secondary" onClick={()=>setComposer(true)}>{t("新建基线")}</button><label className="file-button secondary"><Upload size={14}/>{t("导入证据包")}<input aria-label={t("导入证据包")} type="file" accept=".json" disabled={busy} onChange={e=>{const file=e.target.files?.[0];if(file)importFile(file);e.target.value=''}}/></label>{active?.status==='completed'&&<button className="secondary" disabled={busy} onClick={()=>act(()=>download('/runs/'+selectedId+'/export','quantsandbox-'+selectedId.slice(0,10)+'.json'))}><Download size={14}/>{t("导出证据")}</button>}</div></details><button onClick={()=>primaryComparison?setComparison(true):setComposer(true)}>{primaryComparison?<FlaskConical size={15}/>:<Play size={15}/>} {primaryComparison?t("新建对照"):t("新建回测")}</button></div></div>
 {error&&<div role="alert"><Note tone="warn">{t(error)}</Note></div>}{message&&<div role="status"><Note>{t(message)}</Note></div>}
 <div className="simulation-record-picker"><label>{t("当前记录")}<select aria-label={t("当前策略记录")} value={selectedId} onChange={e=>selectRun(e.target.value)}><option value="">{t("选择已保存实验")}</option>{shownRuns.map(run=><option key={run.id} value={run.id}>{run.name} · {t(kindName[run.kind])} · {t(statusName[run.status])}</option>)}</select></label><button className="secondary" aria-label={t("刷新任务")} disabled={busy} onClick={()=>act(loadRuns)}><RefreshCw size={14}/><span>{t("刷新任务")}</span></button>{active&&['queued','running'].includes(active.status)&&<button className="secondary" disabled={busy} onClick={()=>act(async()=>{await post('/runs/'+selectedId+'/cancel');await loadRuns()})}><Square size={14}/>{t("取消计算")}</button>}</div>
 {!active?<Panel title={t("实验空间")}><Empty>{selectedId?t("正在加载记录…"):activeProject?t("这个项目还没有策略实验。新建回测时将采用当前项目的证券和可用快照。"):t("新建基线回测，或导入已有证据包。")}</Empty></Panel>:<>
 <div className="simulation-record-summary"><div><strong>{active.name}</strong><span className={'tag '+(active.status==='completed'?'good':'')}>{t(statusName[active.status])}{active.status==='running'?' '+active.progress+'%':''}</span><span className="tag">{t(sourceName(active))}</span></div><p><span>{active.config.tickers.join(' / ')}</span><span>{active.config.start_date}{t("至")}{active.config.end_date}</span><span>{t(sampleCaption(active,playback.session))}</span><code>{t("记录")}{active.id}</code></p>{activeProject&&!linkedIds.has(active.id)&&<small>{t("当前记录尚未关联到「{name}」；显示的证券与数据来自这条记录。",{name:activeProject.name})}</small>}</div>
 {active.error&&<Note tone="warn">{active.error.message}</Note>}{['queued','running'].includes(active.status)&&<Panel title={t("计算任务")}><progress value={active.progress} max={100}/><p className="muted">{t("固定输入与计算结果会保存到本机，可取消当前计算。")}</p></Panel>}
 {active.status==='completed'&&result&&<><div className="metrics simulation-metrics"><Metric label={playback.session?t("盲测当前收益"):['pressure','parameter'].includes(active.kind)?t("基线收益"):t("累计收益")} value={metrics.total_return==null?'—':fmt(metrics.total_return)+'%'} sub={t("已计交易费用")}/><Metric label={t("最大回撤")} value={metrics.max_drawdown==null?'—':fmt(metrics.max_drawdown)+'%'} sub={playback.session?t("截至盲测游标"):t("账户相对历史峰值")}/><Metric label={t("成交次数")} value={fmt(metrics.trade_count,0)} sub={t("买卖执行笔数")}/><Metric label={t("当前视图")} value={t(kindName[active.kind])} sub={playback.session?t("盲测截至 {v0}", {v0:playback.session.date}):t("引擎 {v0}", {v0:active.result.engine?.version||active.result.engine_version||'—'})}/></div>
 <div className="simulation-view-tabs"><div className="tabs" role="tablist" aria-label={t("实验内容")}>{[['terminal',t("推演终端")],['lab',t("实验室")],['notes',t("笔记与证据")]].map(([id,label])=><button key={id} role="tab" aria-selected={tab===id} className={tab===id?'selected':''} onClick={()=>setTab(id)}>{label}</button>)}</div><a className="text-button" href={'#obsidian?kind=simulation&run='+selectedId+(projectId?'&project='+projectId:'')}>{t("整理研究笔记")}</a></div>
 {tab==='terminal'&&(isSimulation(active)||active.kind==='walk_forward')?<Terminal key={active.id} active={active} playback={playback} busy={busy} onAction={onAction}/>:tab==='terminal'?<Panel title={t(kindName[active.kind])}><p>{t("这条记录包含情景或参数对照结果。")}</p><button className="secondary" onClick={()=>setTab('lab')}>{t("查看实验结果")}</button></Panel>:null}
 {tab==='lab'&&<><Results active={active} result={result} runs={runs} blind={!!playback.session} onChoose={selectRun}/>{!canCompare&&active.parent_id&&!playback.session&&<button className="secondary" onClick={()=>selectRun(active.parent_id)}>{t("返回父记录，建立新对照")}</button>}</>}
 {tab==='notes'&&<div className="grid-two"><Panel title={t("实验笔记")}><label>{t("标题")}<input value={draft.title} onChange={e=>updateDraft({title:e.target.value})}/></label><label>{t("观察与结论")}<textarea value={draft.body} onChange={e=>updateDraft({body:e.target.value})} placeholder={t("记录判断、反例与后续验证计划。")}/></label><LoadingButton busy={busy} disabled={!draft.body.trim()} onClick={saveNote}><Save size={15}/>{t("保存实验笔记")}</LoadingButton>{notes.map(note=><article className="saved-note" key={note.id}><strong>{note.title}</strong><small>{note.updated_at?.slice(0,16).replace('T',' ')}</small><p>{note.body}</p></article>)}</Panel><Panel title={t("计算口径与证据")}><ul>{(result.assumptions||[]).map((text:string)=><li key={text}>{t(text)}</li>)}</ul><details><summary>{t("配置、数据清单与实现指纹")}</summary><pre>{JSON.stringify({config:active.config,manifest:active.manifest,engine:active.result.engine,replay_verification:active.result.replay_verification},null,2)}</pre></details><p className="muted">{t("导出 JSON 保留原始数值与完整性校验。导入原文件会使用当前引擎重算并报告差异。")}</p>{active.result.replay_verification&&<Note tone={active.result.replay_verification.matched?'info':'warn'}>{active.result.replay_verification.matched?t("证据重放一致。"):t("重放存在差异，请核对实现版本与差异字段。")}</Note>}</Panel></div>}
 </>}
 </>}
 {composer&&<Composer catalog={catalog} project={activeProject} quoteSets={quoteSets} busy={busy} onClose={()=>setComposer(false)} onSubmit={submit} onPlan={async(prompt,config)=>await act(()=>post<Row>('/assistant/plan',{prompt,base_config:config}))}/>} {comparison&&active&&<Comparison active={active} catalog={catalog} date={playback.currentDate||active.config.end_date} busy={busy} blind={!!playback.session} onClose={()=>setComparison(false)} onSubmit={compare}/>}
 </div>;
}
