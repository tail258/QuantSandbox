export type Row=Record<string,any>;
export async function api<T=any>(url:string,body?:unknown):Promise<T>{
 const r=await fetch('/api/research'+url,body===undefined?undefined:{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
 if(!r.ok){const e=await r.json().catch(()=>({detail:'服务暂不可用'}));throw new Error(typeof e.detail==='string'?e.detail:JSON.stringify(e.detail));}
 return r.json();
}
export const today=new Date().toLocaleDateString('sv-SE');
export const fmt=(v:any,d=2)=>v===null||v===undefined||!Number.isFinite(Number(v))?'—':Number(v).toLocaleString('zh-CN',{maximumFractionDigits:d});
export const pct=(v:any)=>v==null?'—':fmt(v*100)+'%';
export function download(name:string,text:string,type='text/plain'){const a=document.createElement('a');a.href=URL.createObjectURL(new Blob([text],{type}));a.download=name;a.click();setTimeout(()=>URL.revokeObjectURL(a.href),1000);}
