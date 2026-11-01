import {useEffect,useMemo,useRef,useState} from 'react';
import {Check,Download,FileText,Save,Send,Settings2,Eye,Code2} from 'lucide-react';
import type {PageProps} from '../App';
import {api,type Row} from '../api';
import {request,post} from '../http';
import {Panel,Note,LoadingButton,Empty} from '../components';
import MarkdownPreview from '../MarkdownPreview';
import {createResponseScope} from '../response-scope';
import {useProject} from '../workspace/ProjectContext';
import '../obsidian.css';

const hashRecord=()=>{const q=new URLSearchParams(location.hash.split('?')[1]||'');return {kind:q.get('kind')==='simulation'?'simulation':'research',run:q.get('run')||''}};
type Operation='preview'|'export'|'publish'|'save'|'';
export default function Obsidian(_:PageProps){
 const {activeProject}=useProject();
 const scope=useRef(createResponseScope());
 const [config,setConfig]=useState<Row>({enabled:false,vault_path:'',folder:'QuantSandbox'}),[research,setResearch]=useState<Row[]>([]),[simulations,setSimulations]=useState<Row[]>([]);
 const [kind,setKind]=useState(()=>hashRecord().kind),[runId,setRunId]=useState(()=>hashRecord().run),[title,setTitle]=useState(''),[notes,setNotes]=useState('');
 const [preview,setPreview]=useState<Row|null>(null),[operation,setOperation]=useState<Operation>(''),[loading,setLoading]=useState(true),[message,setMessage]=useState(''),[error,setError]=useState('');
 const [settingsOpen,setSettingsOpen]=useState(false),[sourceView,setSourceView]=useState(false),[showAll,setShowAll]=useState(false),[configDirty,setConfigDirty]=useState(false);
 const busy=!!operation,controlsLocked=busy&&operation!=='preview';
 const records=kind==='research'?research:simulations,links=activeProject?.links||[];
 const choices=useMemo(()=>activeProject&&!showAll?records.filter(r=>links.some(link=>link.kind===kind&&link.run_id===r.id)):records,[activeProject,showAll,records,links,kind]);
 const selected=records.find(r=>r.id===runId),payload={kind,run_id:runId,title:title||undefined,notes:notes||undefined};
 function invalidate(){scope.current.invalidate();setPreview(null);setMessage('')}
 function updateHash(nextKind:string,nextRun:string){const q=new URLSearchParams(location.hash.split('?')[1]||'');q.set('kind',nextKind);if(nextRun)q.set('run',nextRun);else q.delete('run');history.replaceState(null,'','#obsidian?'+q.toString())}
 function selectRecord(nextKind:string,nextRun:string){setKind(nextKind);setRunId(nextRun);setSourceView(false);invalidate();updateHash(nextKind,nextRun)}
 useEffect(()=>{let live=true;Promise.all([request<Row>('/obsidian/config'),api<Row[]>('/runs'),request<Row>('/runs')]).then(([c,r,s])=>{if(live){setConfig(c);setResearch(r);setSimulations(s.runs.filter((r:Row)=>r.status==='completed'))}}).catch(e=>{if(live)setError(e.message)}).finally(()=>{if(live)setLoading(false)});const hash=()=>{const next=hashRecord();setKind(next.kind);setRunId(next.run);scope.current.invalidate();setPreview(null)};window.addEventListener('hashchange',hash);return()=>{live=false;scope.current.invalidate();window.removeEventListener('hashchange',hash)}},[]);
 useEffect(()=>{invalidate()},[activeProject?.id]);
 useEffect(()=>{if(!loading&&activeProject&&runId&&records.some(r=>r.id===runId)&&!links.some(link=>link.kind===kind&&link.run_id===runId))setShowAll(true)},[loading,activeProject?.id,runId,kind,records]);
 async function act(name:Operation,fn:()=>Promise<void>){setOperation(name);setError('');setMessage('');try{await fn()}catch(e){setError(e instanceof Error?e.message:'操作失败，请重试')}finally{setOperation('')}}
 async function save(){const draft={...config};await act('save',async()=>{const saved=await request<Row>('/obsidian/config',{method:'PUT',body:JSON.stringify(draft)});setConfig(saved);setConfigDirty(false);invalidate();setMessage('本机配置已保存。重新预览后可手动写入本次笔记。')})}
 async function inspect(){const ticket=scope.current.begin(),body={...payload};await act('preview',async()=>{const next=await post<Row>('/obsidian/preview',body);if(scope.current.isCurrent(ticket)){setPreview(next);setSourceView(false)}})}
 async function exportZip(){if(!preview)return;await act('export',async()=>{const r=await fetch('/api/obsidian/export',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});if(!r.ok){const e=await r.json();throw new Error(typeof e.detail==='string'?e.detail:'导出失败')}const href=URL.createObjectURL(await r.blob()),a=document.createElement('a');a.href=href;a.download='quantsandbox-obsidian-'+runId.slice(0,12)+'.zip';a.click();setTimeout(()=>URL.revokeObjectURL(href),1000);setMessage('Markdown 与附件包已下载。解压后保留笔记与同名附件目录即可。')})}
 async function publish(){if(!preview||configDirty)return;const body={...payload,preview_token:preview.preview_token};await act('publish',async()=>{const result=await post<Row>('/obsidian/publish',body);invalidate();setMessage('已写入本次笔记：'+result.filename)})}
 function editConfig(change:Row){setConfig({...config,...change});setConfigDirty(true);invalidate()}
 const range=selected?.params||selected?.config||{};
 return <div className="obsidian-page"><div className="page-title"><div><h1>研究笔记</h1><p>选择研究或实验，核对笔记，再下载到 Obsidian。</p></div><button className="secondary" aria-expanded={settingsOpen} onClick={()=>setSettingsOpen(v=>!v)}><Settings2 size={15}/>笔记库设置（可选）</button></div>
 <ol className="obsidian-steps" aria-label="导出步骤"><li className={runId?'complete':''}>{runId?<Check size={14}/>:<span>1</span>}选择记录</li><li className={preview?'complete':''}>{preview?<Check size={14}/>:<span>2</span>}核对预览</li><li><span>3</span>下载或手动写入</li></ol>
 {error&&<div role="alert"><Note tone="warn">{error}</Note></div>}{message&&<div role="status"><Note>{message}</Note></div>}
 {settingsOpen&&<Panel title="可选的本机笔记库" className="obsidian-settings"><p className="muted">无需配置即可下载。开启后，也只在你点击“写入本次笔记”时保存当前预览。</p><div className="controls wrap"><label className="checkbox"><input type="checkbox" checked={config.enabled} disabled={controlsLocked} onChange={e=>editConfig({enabled:e.target.checked})}/>允许手动写入</label><label className="grow">笔记库绝对路径<input value={config.vault_path} disabled={controlsLocked} onChange={e=>editConfig({vault_path:e.target.value})} placeholder="选择你自己的本机笔记库" autoComplete="off"/></label><label>库内保存目录<input value={config.folder} disabled={controlsLocked} onChange={e=>editConfig({folder:e.target.value})}/></label><LoadingButton busy={operation==='save'} disabled={busy||loading||!configDirty} onClick={save}><Save size={15}/>保存本机配置</LoadingButton></div><p className="muted">配置仅存本机；不扫描或读取笔记，不覆盖同名文件。</p></Panel>}
 <Panel title="选择记录" className="obsidian-selection" action={activeProject&&<label className="checkbox"><input type="checkbox" checked={showAll} disabled={controlsLocked} onChange={e=>{const checked=e.target.checked;if(!checked&&!links.some(link=>link.kind===kind&&link.run_id===runId))selectRecord(kind,'');setShowAll(checked)}}/>显示全部记录</label>}>
 {activeProject&&<p className="obsidian-project-hint">{showAll?'全部记录':'当前项目'} · <strong>{activeProject.name}</strong>{!showAll&&` · ${choices.length} 条可用记录`}</p>}
 <div className="controls wrap"><label>记录类型<select value={kind} disabled={controlsLocked} onChange={e=>selectRecord(e.target.value,'')}><option value="research">研究分析</option><option value="simulation">策略实验</option></select></label><label className="grow">已保存记录<select value={runId} disabled={controlsLocked||loading} onChange={e=>selectRecord(kind,e.target.value)}><option value="">{loading?'正在读取记录…':'请选择记录'}</option>{choices.map(r=><option value={r.id} key={r.id}>{r.title||r.name} · {r.id.slice(0,10)}</option>)}</select></label><LoadingButton busy={operation==='preview'} disabled={busy||!runId||loading} onClick={inspect}><Eye size={15}/>生成预览</LoadingButton></div>
 {selected&&<div className="obsidian-record-meta"><span>{selected.title||selected.name}</span>{(range.start||range.start_date)&&<span>{range.start||range.start_date} — {range.end||range.end_date}</span>}<code>{runId.slice(0,12)}</code></div>}
 {!loading&&!choices.length&&<p className="muted">{activeProject&&!showAll?'当前项目还没有这类记录。可先关联研究或实验，或勾选“显示全部记录”。':'尚无已保存记录。完成研究分析或策略实验后再来导出。'}</p>}
 <details className="obsidian-customize"><summary>调整标题与补充结论（可选）</summary><div className="obsidian-draft"><label>笔记标题<input value={title} maxLength={160} disabled={controlsLocked} onChange={e=>{setTitle(e.target.value);invalidate()}} placeholder="默认沿用记录标题"/></label><label>补充结论<textarea value={notes} maxLength={20000} disabled={controlsLocked} onChange={e=>{setNotes(e.target.value);invalidate()}} placeholder="判断、待验证问题或后续观察"/></label>{activeProject?.conclusion&&<button className="text-button" disabled={controlsLocked} onClick={()=>{setNotes(activeProject.conclusion||'');invalidate()}}>填入当前项目结论</button>}</div></details>
 </Panel>
 <section className="obsidian-preview-panel" aria-labelledby="note-preview-title"><div className="obsidian-preview-toolbar"><div><FileText size={17}/><h2 id="note-preview-title">笔记预览</h2>{preview&&<span className="muted">{preview.files?.length||0} 个文件</span>}</div>{preview&&<div className="segmented" aria-label="预览方式"><button className={!sourceView?'active':''} onClick={()=>setSourceView(false)}><Eye size={14}/>阅读预览</button><button className={sourceView?'active':''} onClick={()=>setSourceView(true)}><Code2 size={14}/>Markdown 源码</button></div>}</div>
 {preview?<>{sourceView?<pre className="obsidian-source" aria-label="Markdown 源码">{preview.markdown}</pre>:<MarkdownPreview markdown={preview.markdown} charts={preview.charts||[]}/>}<details className="obsidian-attachments"><summary>附件清单 · {preview.files?.length||0} 个文件</summary><ul>{preview.files?.map((f:Row)=><li key={f.path}><span>{f.path}</span><small>{(f.size/1024).toLocaleString('zh-CN',{maximumFractionDigits:1})} KB</small></li>)}</ul></details></>:<div className="obsidian-empty-preview"><Empty>选择一条记录并生成预览，来源、样本和图表会整理在这里。</Empty></div>}
 <div className="obsidian-export-bar"><div><strong>{preview?'核对后即可导出':'笔记与图表保持相对链接'}</strong><p>{config.enabled?'笔记库已启用；每次写入仍需手动点击。':'无需设置笔记库路径，可直接下载附件包。'}</p></div><div className="actions"><button disabled={busy||!preview} onClick={exportZip}><Download size={15}/>下载 Markdown 与附件</button><button className="secondary" disabled={busy||!preview?.can_publish||configDirty} onClick={publish}><Send size={14}/>写入本次笔记</button></div></div>
 </section></div>;
}
