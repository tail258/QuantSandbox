import {useEffect,useLayoutEffect,useMemo,useRef,useState} from 'react';
import type {Row} from '../api';
import {post} from '../http';
import {createResponseScope} from '../response-scope';
import {partialMetrics} from './model';

export function usePlayback(active:Row|null){
 const scope=useRef(createResponseScope());
 const [session,setSession]=useState<Row|null>(null),[ticker,setTicker]=useState(''),[cursor,setCursor]=useState(0),[selectedDate,setSelectedDate]=useState(''),[selectedTrade,setSelectedTrade]=useState<Row|null>(null);
 const identity=active?.id;
 useLayoutEffect(()=>{
  scope.current.invalidate();setSession(null);setSelectedDate('');setSelectedTrade(null);
  setTicker(active?.config.tickers[0]||'');setCursor(Math.max(0,(active?.result?.series?.length||1)-1));
  return()=>scope.current.invalidate();
 },[identity]);
 // A queued record gains its result after polling without changing identity.
 useEffect(()=>{if(active?.status==='completed')setCursor(Math.max(0,(active.result?.series?.length||1)-1))},[active?.status,identity]);
 const result=session?.result||active?.result;
 const series:Row[]=result?.series||[];
 const currentDate=session?.date||series[cursor]?.date||'';
 const visibleSeries=useMemo(()=>session?series:series.slice(0,cursor+1),[session,series,cursor]);
 const visibleBars:Row[]=useMemo(()=>(result?.bars?.[ticker]||[]).filter((row:Row)=>!currentDate||row.date<=currentDate),[result,ticker,currentDate]);
 const trades:Row[]=useMemo(()=>(result?.trades||[]).filter((row:Row)=>!currentDate||row.date<=currentDate),[result,currentDate]);
 const decisions:Row[]=useMemo(()=>(result?.decisions||[]).filter((row:Row)=>!currentDate||row.date<=currentDate),[result,currentDate]);
 const metrics=session?result.metrics:result?partialMetrics(result,visibleSeries,trades,active?.config.account.initial_cash||1,cursor>=series.length-1):{};
 const resetEvidence=()=>{setSelectedDate('');setSelectedTrade(null)};
 const pickDate=(date:string)=>{setSelectedDate(date);setSelectedTrade([...trades].reverse().find(row=>row.date===date&&row.ticker===ticker)||null)};
 const pickTrade=(trade:Row)=>{setTicker(trade.ticker);setSelectedDate(trade.date);setSelectedTrade(trade)};
 const changeTicker=(value:string)=>{setTicker(value);resetEvidence()};
 const changeCursor=(value:number)=>{setCursor(value);resetEvidence()};
 const exitBlind=()=>{scope.current.invalidate();setSession(null);resetEvidence()};
 async function blind(){
  if(!active)return;
  const ticket=scope.current.begin();
  const next=await post<Row>('/runs/'+active.id+'/sessions',{cursor:0});
  if(!scope.current.isCurrent(ticket))return;
  setSession(next);resetEvidence();
 }
 async function advance(operation:'advance'|'reveal',steps?:number){
  if(!session)return;
  const ticket=scope.current.begin();
  const next=await post<Row>('/sessions/'+session.id+'/'+operation,operation==='advance'?{steps}:{});
  if(!scope.current.isCurrent(ticket))return;
  setSession(next);resetEvidence();
 }
 return {session,result,series,currentDate,visibleSeries,visibleBars,trades,decisions,metrics,ticker,cursor,selectedDate,selectedTrade,pickDate,pickTrade,changeTicker,changeCursor,blind,advance,exitBlind};
}
