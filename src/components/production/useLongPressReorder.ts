import {useEffect,useRef,useState} from 'react';
import type {PointerEvent,MouseEvent,RefObject} from 'react';
interface Drag {id:string;x:number;y:number;target:string;placement:'before'|'after'}
export function useLongPressReorder(container:RefObject<HTMLDivElement|null>,move:(source:string,target:string,placement:'before'|'after')=>Promise<void>,disabled:boolean){
  const [pressing,setPressing]=useState(''),[drag,setDrag]=useState<Drag|null>(null);
  const current=useRef<Drag|null>(null),press=useRef<{id:string;x:number;y:number;timer:ReturnType<typeof setTimeout>}|null>(null),suppress=useRef(false);
  const callback=useRef(move);callback.current=move;
  const cancel=()=>{if(press.current)clearTimeout(press.current.timer);press.current=null;current.current=null;setPressing('');setDrag(null);};
  const locate=(x:number,y:number)=>{
    if(!current.current)return;
    const card=document.elementFromPoint(x,y)?.closest<HTMLElement>('[data-production-task]');
    const target=card?.dataset.productionTask||'';
    const next={...current.current,x,y,target:card?.dataset.reorderable==='true'&&target!==current.current.id?target:'',placement:card&&y>card.getBoundingClientRect().top+card.getBoundingClientRect().height/2?'after' as const:'before' as const};
    current.current=next;setDrag(next);
  };
  useEffect(()=>{
    const onMove=(event:globalThis.PointerEvent)=>{
      if(current.current){event.preventDefault();locate(event.clientX,event.clientY);}
      else if(press.current&&Math.hypot(event.clientX-press.current.x,event.clientY-press.current.y)>8)cancel();
    };
    const end=(event:globalThis.PointerEvent)=>{
      const item=current.current;
      if(item){event.preventDefault();suppress.current=true;setTimeout(()=>suppress.current=false,150);}
      cancel();if(item?.target&&event.type!=='pointercancel')void callback.current(item.id,item.target,item.placement);
    };
    const escape=(event:KeyboardEvent)=>{if(event.key==='Escape'&&(current.current||press.current)){event.preventDefault();event.stopImmediatePropagation();cancel();}};
    window.addEventListener('pointermove',onMove,{passive:false});window.addEventListener('pointerup',end);window.addEventListener('pointercancel',end);window.addEventListener('keydown',escape,true);window.addEventListener('blur',cancel);
    return()=>{window.removeEventListener('pointermove',onMove);window.removeEventListener('pointerup',end);window.removeEventListener('pointercancel',end);window.removeEventListener('keydown',escape,true);window.removeEventListener('blur',cancel);if(press.current)clearTimeout(press.current.timer);};
  },[]);
  useEffect(()=>{
    if(!drag)return;
    let frame=0;
    const scroll=()=>{const list=container.current,item=current.current;if(list&&item){const rect=list.getBoundingClientRect();const delta=item.y<rect.top+35?-9:item.y>rect.bottom-35?9:0;if(delta){list.scrollTop+=delta;locate(item.x,item.y);}}frame=requestAnimationFrame(scroll);};
    frame=requestAnimationFrame(scroll);return()=>cancelAnimationFrame(frame);
  },[!!drag]);
  const pointerDown=(id:string,reorderable:boolean)=>(event:PointerEvent<HTMLDivElement>)=>{
    if(disabled||!reorderable||event.button!==0||(event.target as HTMLElement).closest('button,input,a,select'))return;
    cancel();const {clientX:x,clientY:y}=event;setPressing(id);
    press.current={id,x,y,timer:setTimeout(()=>{if(!press.current)return;const next={id,x,y,target:'',placement:'before' as const};current.current=next;setDrag(next);setPressing('');},1000)};
  };
  const clickCapture=(event:MouseEvent)=>{if(suppress.current){event.preventDefault();event.stopPropagation();}};
  return{pressing,drag,pointerDown,clickCapture};
}
