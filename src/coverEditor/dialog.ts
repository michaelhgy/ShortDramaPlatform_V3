/** Non-blocking, styled confirmations. Escape cancels the foremost dialog only. */
let finish: ((accepted: boolean) => void) | null = null;
export const confirmationOpen = () => finish !== null;
export function confirmAction(message: string, title = '确认操作', action = '确定'): Promise<boolean> {
  if (finish) return Promise.resolve(false);
  const modal=document.getElementById('confirm-modal')!,cancel=document.getElementById('confirm-cancel') as HTMLButtonElement;
  const accept=document.getElementById('confirm-accept') as HTMLButtonElement,close=document.getElementById('confirm-close') as HTMLButtonElement;
  const focus=document.activeElement as HTMLElement|null;
  const backgrounds=[document.querySelector('.workspace'),document.getElementById('flower-manager')].filter(Boolean) as HTMLElement[];
  const states=backgrounds.map(element=>element.inert);backgrounds.forEach(element=>element.inert=true);
  document.getElementById('confirm-title')!.textContent=title;document.getElementById('confirm-message')!.textContent=message;accept.textContent=action;
  modal.hidden=false;
  return new Promise(resolve=>{
    const key=(event:KeyboardEvent)=>{
      if(event.key==='Escape'){event.preventDefault();event.stopImmediatePropagation();finish?.(false);}
      else if(event.key==='Tab'){
        const buttons=[close,cancel,accept],index=buttons.indexOf(document.activeElement as HTMLButtonElement);
        event.preventDefault();buttons[(index+(event.shiftKey?-1:1)+buttons.length)%buttons.length].focus();
      }
    };
    finish=accepted=>{
      modal.hidden=true;finish=null;window.removeEventListener('keydown',key,true);
      backgrounds.forEach((element,index)=>element.inert=states[index]);
      if(focus?.isConnected)focus.focus();resolve(accepted);
    };
    cancel.onclick=close.onclick=()=>finish?.(false);accept.onclick=()=>finish?.(true);
    window.addEventListener('keydown',key,true);cancel.focus();
  });
}
