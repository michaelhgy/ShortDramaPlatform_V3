import { useEffect, useId, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { History, Search, Trash2, X } from 'lucide-react';

const field = 'w-full rounded-xl border border-slate-200 bg-white px-2.5 py-2 text-xs outline-none focus:border-slate-500 focus:ring-2 focus:ring-slate-100 disabled:bg-slate-100';

export function PublishingHistoryField({ label, value, onChange, history, onDelete, multiline = false, placeholder = '', className = '', disabled = false }: {
  label: string; value: string; onChange: (text: string) => void; history: string[]; onDelete: (text: string) => void; multiline?: boolean; placeholder?: string; className?: string; disabled?: boolean;
}) {
  const id = useId();
  const [open, setOpen] = useState(false), [query, setQuery] = useState('');
  const [position, setPosition] = useState({ left: 0, top: 0, width: 360, height: 320 });
  const trigger = useRef<HTMLButtonElement>(null), popup = useRef<HTMLDivElement>(null), search = useRef<HTMLInputElement>(null);
  function close(restoreFocus = false) { setOpen(false); if (restoreFocus) trigger.current?.focus(); }
  function toggle() {
    if (open) { close(); return; }
    const rect=trigger.current!.getBoundingClientRect();
    const width=Math.min(360,window.innerWidth-24),height=Math.min(320,window.innerHeight-24);
    const below=window.innerHeight-rect.bottom-12;
    // Set coordinates in the opening event, before the portal can be painted.
    setPosition({width,height,left:Math.max(12,Math.min(rect.right-width,window.innerWidth-width-12)),top:below>=height?rect.bottom+6:Math.max(12,rect.top-height-6)});
    setQuery('');setOpen(true);
  }
  useEffect(() => {
    if (!open) return;
    const rect = trigger.current!.getBoundingClientRect();
    search.current?.focus({ preventScroll: true });
    function outside(e: PointerEvent) { if (!popup.current?.contains(e.target as Node) && !trigger.current?.contains(e.target as Node)) close(); }
    function scroll(e: Event) {
      if (popup.current?.contains(e.target as Node)) return;
      const current = trigger.current?.getBoundingClientRect();
      if (current && (Math.abs(current.top - rect.top) > 1 || Math.abs(current.left - rect.left) > 1)) close();
    }
    function resize() { close(); }
    function escape(e: KeyboardEvent) { if (e.key === 'Escape' && !e.repeat && !e.defaultPrevented) { e.preventDefault(); e.stopPropagation(); close(true); } }
    document.addEventListener('pointerdown', outside); window.addEventListener('scroll', scroll, true); window.addEventListener('resize', resize);
    window.addEventListener('keydown', escape);
    return () => { document.removeEventListener('pointerdown', outside); window.removeEventListener('scroll', scroll, true); window.removeEventListener('resize', resize); window.removeEventListener('keydown', escape); };
  }, [open]);
  const rows = history.filter(text => text.toLocaleLowerCase().includes(query.trim().toLocaleLowerCase()));
  return <div className={`flex min-w-0 flex-col gap-1.5 ${className}`}>
    <div className="flex items-center justify-between gap-2"><label htmlFor={id} className="text-xs font-bold text-slate-600">{label}</label><button ref={trigger} disabled={disabled} type="button" aria-label={`${label}历史`} aria-expanded={open} aria-controls={open ? `${id}-history` : undefined} className="inline-flex shrink-0 items-center gap-1 rounded-lg px-1.5 py-1 text-[11px] text-slate-500 hover:bg-slate-100 hover:text-slate-800" onClick={toggle}><History size={12} />历史<span className="tabular-nums">{history.length}</span></button></div>
    {multiline ? <textarea id={id} disabled={disabled} aria-label={label} className={`${field} min-h-24 flex-1 resize-y font-normal`} value={value} onChange={e => onChange(e.target.value)} placeholder={placeholder} />
      : <input id={id} disabled={disabled} aria-label={label} className={`${field} font-normal`} value={value} onChange={e => onChange(e.target.value)} placeholder={placeholder} />}
    {open && createPortal(<div ref={popup} data-publishing-history id={`${id}-history`} role="dialog" aria-label={`${label}历史记录`} className="fixed z-[130] flex flex-col overflow-hidden rounded-2xl border border-slate-200 bg-white p-3 shadow-2xl" style={{ left: position.left, top: position.top, width: position.width, maxHeight: position.height }} onKeyDown={e => { if (e.key === 'Escape') { e.stopPropagation(); close(true); } }}>
      <div className="mb-2 flex items-center justify-between gap-2"><h4 className="text-xs font-black text-[#1A1D2E]">{label} · 历史记录</h4><button aria-label="关闭历史记录" className="rounded-lg p-1 text-slate-400 hover:bg-slate-100" onClick={() => close(true)}><X size={14} /></button></div>
      <div className="relative mb-2"><Search className="pointer-events-none absolute left-2.5 top-2 text-slate-400" size={14} /><input ref={search} disabled={disabled} aria-label={`搜索${label}历史`} className={`${field} !pl-8`} placeholder="搜索用过的内容" value={query} onChange={e => setQuery(e.target.value)} /></div>
      <div className="min-h-0 overflow-y-auto space-y-1">{rows.map(text => <div key={text} className="flex items-start gap-1 rounded-xl bg-slate-50 p-1"><button disabled={disabled} title={text} className="min-w-0 flex-1 rounded-lg px-2 py-2 text-left text-xs leading-5 text-slate-700 hover:bg-lime-50" onClick={() => { onChange(text); close(true); }}><span className="line-clamp-3 whitespace-pre-wrap break-words">{text}</span></button><button disabled={disabled} aria-label={`删除历史：${text}`} title="删除这条历史" className="shrink-0 rounded-lg p-2 text-slate-400 hover:bg-rose-50 hover:text-rose-600" onClick={() => onDelete(text)}><Trash2 size={13} /></button></div>)}{!rows.length && <p className="px-2 py-4 text-xs leading-5 text-slate-400">{history.length ? '没有匹配的记录，换个关键词试试。' : '暂无记录，保存设置后会自动记住。'}</p>}</div>
    </div>, document.body)}
  </div>;
}
