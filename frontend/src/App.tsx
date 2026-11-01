import {Component,lazy,Suspense,useCallback,useEffect,useState,type ReactNode} from 'react';
import {Database,ChartNoAxesCombined,ChartLine,FlaskConical,Users,Files,ShieldCheck,Layers3,Footprints,FolderKanban,NotebookPen,Play} from 'lucide-react';
import {api,type Row} from './api';
import {Empty,Note} from './components';
const pages={projects:lazy(()=>import('./pages/Projects')),data:lazy(()=>import('./pages/DataCenter')),finance:lazy(()=>import('./pages/Finance')),industry:lazy(()=>import('./pages/Industry')),etf:lazy(()=>import('./pages/EtfFlows')),national:lazy(()=>import('./pages/NationalTeam')),stats:lazy(()=>import('./pages/Statistics')),evidence:lazy(()=>import('./pages/Evidence')),simulation:lazy(()=>import('./pages/Simulation')),runs:lazy(()=>import('./pages/Runs')),obsidian:lazy(()=>import('./pages/Obsidian'))};
const nav=[['projects','研究项目',FolderKanban],['data','数据中心',Database],['finance','公司与财务',ChartNoAxesCombined],['industry','产业周期',ChartLine],['etf','ETF 资金',Layers3],['national','国家队足迹',Footprints],['stats','统计实验',FlaskConical],['evidence','筹码与情绪',Users],['simulation','策略与推演',Play],['runs','分析记录',Files],['obsidian','Obsidian',NotebookPen]] as const;
const route=()=>location.hash.slice(1).split('?')[0]||'projects';
export type PageProps={status:Row;reload:()=>Promise<void>;setPage:(p:string)=>void};
class PageBoundary extends Component<{children:ReactNode},{failed:boolean}>{
 state={failed:false};
 static getDerivedStateFromError(){return {failed:true}}
 render(){return this.state.failed?<Note tone="warn"><p>页面加载失败，请重新加载工作台。</p><button className="secondary" onClick={()=>location.reload()}>重新加载</button></Note>:this.props.children}
}
export default function App(){
 const [page,setPage]=useState(route),[status,setStatus]=useState<Row>({datasets:[],series:[],templates:{},metrics:{},events:[]}),[error,setError]=useState('');
 const reload=useCallback(async()=>{setStatus(await api('/status'));setError('');},[]);
 useEffect(()=>{let live=true;reload().catch(e=>{if(live)setError(e.message)});const onhash=()=>setPage(route());window.addEventListener('hashchange',onhash);return()=>{live=false;window.removeEventListener('hashchange',onhash)}},[reload]);
 useEffect(()=>{window.scrollTo(0,0)},[page]);
 const go=useCallback((p:string)=>{location.hash=p;setPage(p.split('?')[0]);},[]);
 const active=nav.find(n=>n[0]===page)||nav[0],Page=pages[active[0]];
 return <div className="shell"><aside><a className="brand" href="#projects">QuantSandbox<small>投资研究 · 策略验证</small></a><nav aria-label="主导航">{nav.map(([id,label,Icon])=><button key={id} className={page===id?'active':''} aria-current={page===id?'page':undefined} onClick={()=>go(id)}><Icon size={18}/>{label}</button>)}</nav><div className="sidebar-foot"><ShieldCheck size={17}/><div>本地研究 · 市场只读<small>数据与计算留在你的设备</small></div></div></aside><div className="workspace"><header><span>工作台 <b>/</b> {active[1]}</span><span className="status-dot">研究与模拟 <code>v3.0.0</code></span></header><main>{error&&<Note tone="warn">研究数据服务：{error}<button className="text-button" onClick={()=>reload().catch(e=>setError(e.message))}>重试</button></Note>}<PageBoundary key={page}><Suspense fallback={<Empty>正在打开{active[1]}…</Empty>}><Page status={status} reload={reload} setPage={go}/></Suspense></PageBoundary></main><footer>QuantSandbox <span>来源可追溯 · 参数可复算 · 研究与验证相连</span></footer></div></div>
}
