import {useEffect,useRef,type ReactNode} from 'react';
import {X} from 'lucide-react';

export default function Drawer({title,onClose,children}:{title:string;onClose:()=>void;children:ReactNode}){
 const container=useRef<HTMLElement>(null),close=useRef(onClose);close.current=onClose;
 useEffect(()=>{
  const previous=document.activeElement as HTMLElement|null,overflow=document.body.style.overflow;
  document.body.style.overflow='hidden';
  container.current?.querySelector<HTMLElement>('input,select,button,textarea')?.focus();
  const key=(event:KeyboardEvent)=>{
   if(event.key==='Escape'){event.preventDefault();close.current();return}
   if(event.key!=='Tab')return;
   const items=Array.from(container.current?.querySelectorAll<HTMLElement>('button:not([disabled]),input:not([disabled]),select:not([disabled]),textarea:not([disabled]),a[href],summary')||[]).filter(node=>!node.closest('details:not([open])')||node.tagName==='SUMMARY');
   const first=items[0],last=items.at(-1);
   if(event.shiftKey&&document.activeElement===first){event.preventDefault();last?.focus()}
   else if(!event.shiftKey&&document.activeElement===last){event.preventDefault();first?.focus()}
  };
  document.addEventListener('keydown',key);
  return()=>{document.removeEventListener('keydown',key);document.body.style.overflow=overflow;previous?.focus()};
 },[]);
 return <div className="simulation-backdrop" onMouseDown={e=>{if(e.target===e.currentTarget)onClose()}}><section ref={container} className="simulation-drawer" role="dialog" aria-modal="true" aria-label={title}><div className="simulation-drawer-head"><div><span className="eyebrow">策略实验</span><h2>{title}</h2></div><button type="button" className="secondary icon-button" aria-label="关闭配置" onClick={onClose}><X size={18}/></button></div>{children}</section></div>;
}
