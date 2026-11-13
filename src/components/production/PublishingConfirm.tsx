import { useEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { AlertCircle, X } from 'lucide-react';

type Question = { title: string; message: string; confirmText?: string };

function ConfirmDialog({ question, answer }: { question: Question; answer: (yes: boolean) => void }) {
  const panel = useRef<HTMLDivElement>(null);
  const cancel = useRef<HTMLButtonElement>(null);
  useEffect(() => {
    const previous = document.activeElement as HTMLElement | null;
    cancel.current?.focus();
    return () => { if (previous?.isConnected) previous.focus(); };
  }, []);
  return createPortal(<div className="fixed inset-0 z-[150] flex items-center justify-center bg-slate-950/35 p-4 backdrop-blur-sm" onMouseDown={e => { if (e.target === e.currentTarget) answer(false); }}>
    <div ref={panel} role="alertdialog" aria-modal="true" aria-label={question.title} aria-describedby="publishing-confirm-message" className="w-full max-w-md rounded-2xl border border-slate-200 bg-white p-5 shadow-2xl" onKeyDown={e => {
      if (e.key === 'Escape') { e.stopPropagation(); answer(false); }
      if (e.key === 'Tab') {
        const buttons = [...panel.current!.querySelectorAll<HTMLButtonElement>('button')];
        const first = buttons[0], last = buttons[buttons.length - 1];
        if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus(); }
        if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
      }
    }}>
      <div className="flex items-start gap-3"><span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-[#1A1D2E] text-[#DDFD00]"><AlertCircle size={20} /></span><div className="min-w-0 flex-1"><h3 className="pt-1 text-base font-black text-[#1A1D2E]">{question.title}</h3><p id="publishing-confirm-message" className="mt-3 max-h-64 overflow-y-auto whitespace-pre-wrap break-words text-sm leading-6 text-slate-600">{question.message}</p></div><button aria-label="关闭确认窗口" className="rounded-lg p-1 text-slate-400 hover:bg-slate-100" onClick={() => answer(false)}><X size={17} /></button></div>
      <div className="mt-6 flex justify-end gap-2"><button ref={cancel} className="rounded-xl border border-slate-200 px-4 py-2 text-xs font-bold text-slate-600 hover:bg-slate-50" onClick={() => answer(false)}>取消</button><button className="rounded-xl bg-[#1A1D2E] px-4 py-2 text-xs font-black text-[#DDFD00] hover:bg-slate-800" onClick={() => answer(true)}>{question.confirmText || '确认'}</button></div>
    </div>
  </div>, document.body);
}

export function usePublishingConfirm() {
  const [question, setQuestion] = useState<Question | null>(null);
  const resolve = useRef<((answer: boolean) => void) | null>(null);
  useEffect(() => () => resolve.current?.(false), []);
  function answer(value: boolean) { const done = resolve.current; resolve.current = null; setQuestion(null); done?.(value); }
  function confirm(value: Question) {
    resolve.current?.(false);
    setQuestion(value);
    return new Promise<boolean>(done => { resolve.current = done; });
  }
  return { confirm, confirmation: question ? <ConfirmDialog question={question} answer={answer} /> : null };
}
