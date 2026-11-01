import {useCallback,useEffect,useRef,useState} from 'react';
import type {Row} from '../api';
import {request} from '../http';
import {queryRun} from './model';

/** List requests and selected-record requests have separate, cancellable lifetimes. */
export function useSimulationData(){
 const mounted=useRef(true),selection=useRef(queryRun()),listGeneration=useRef(0);
 const [catalog,setCatalog]=useState<Row|null>(null),[runs,setRuns]=useState<Row[]>([]),[selectedId,setSelectedId]=useState(queryRun),[active,setActive]=useState<Row|null>(null),[notes,setNotes]=useState<Row[]>([]),[error,setError]=useState('');
 useEffect(()=>{mounted.current=true;return()=>{mounted.current=false;listGeneration.current++}},[]);
 const loadRuns=useCallback(async()=>{
  const generation=++listGeneration.current;
  const result=await request<Row>('/runs');
  if(mounted.current&&generation===listGeneration.current)setRuns(result.runs);
  return result.runs as Row[];
 },[]);
 const choose=useCallback((id:string)=>{
  selection.current=id;setSelectedId(id);setActive(null);setNotes([]);setError('');
  const query=new URLSearchParams(location.hash.split('?')[1]||'');
  if(id)query.set('run',id);else query.delete('run');
  location.hash='simulation'+(query.size?'?'+query.toString():'');
  if(id)localStorage.setItem('quantsandbox.lastRun',id);
 },[]);
 useEffect(()=>{
  const controller=new AbortController();let live=true;
  request<Row>('/catalog',{signal:controller.signal}).then(value=>{if(live)setCatalog(value)}).catch(e=>{if(live&&e.name!=='AbortError')setError(e.message)});
  loadRuns().catch(e=>{if(live)setError(e.message)});
  const hash=()=>{if(location.hash.slice(1).split('?')[0]!=='simulation')return;const id=queryRun();if(id!==selection.current){selection.current=id;setSelectedId(id);setActive(null);setNotes([])}};
  window.addEventListener('hashchange',hash);
  return()=>{live=false;controller.abort();window.removeEventListener('hashchange',hash)};
 },[loadRuns]);
 useEffect(()=>{
  if(!selectedId){setActive(null);return}
  selection.current=selectedId;let live=true;let timer:ReturnType<typeof setTimeout>;
  const controller=new AbortController();
  async function poll(){
   try{
    const run=await request<Row>('/runs/'+selectedId,{signal:controller.signal});
    if(!live||selection.current!==selectedId)return;
    setActive(run);
    if(['queued','running'].includes(run.status))timer=setTimeout(poll,1200);
    else loadRuns().catch(()=>{});
   }catch(e:any){if(live&&e.name!=='AbortError')setError(e.message)}
  }
  poll();
  request<Row>('/notes?run_id='+selectedId,{signal:controller.signal}).then(r=>{if(live&&selection.current===selectedId)setNotes(r.notes)}).catch(e=>{if(live&&e.name!=='AbortError')setError(e.message)});
  return()=>{live=false;controller.abort();clearTimeout(timer)};
 },[selectedId,loadRuns]);
 return {catalog,runs,selectedId,active,notes,setNotes,choose,selection,loadRuns,error,setError,mounted};
}
