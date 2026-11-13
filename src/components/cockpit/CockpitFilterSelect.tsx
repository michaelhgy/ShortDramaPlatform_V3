import { useEffect, useId, useLayoutEffect, useRef, useState, type ReactNode } from 'react';
import { createPortal } from 'react-dom';
import { Check, ChevronDown, Search, X } from 'lucide-react';

interface FilterOption {
  value: string;
  label: string;
  description?: string;
  meta?: string;
  searchText?: string;
  leading?: ReactNode;
  trailing?: ReactNode;
}

interface Placement { left: number; width: number; maxHeight: number; top?: number; bottom?: number }

export function CockpitFilterSelect({ label, icon, value, allOption, options, onChange, placeholder, minWidth = 288 }: {
  label: string;
  icon: ReactNode;
  value: string;
  allOption: FilterOption;
  options: FilterOption[];
  onChange: (value: string) => void;
  placeholder: string;
  minWidth?: number;
}) {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState('');
  const [activeIndex, setActiveIndex] = useState(0);
  const [placement, setPlacement] = useState<Placement | null>(null);
  const trigger = useRef<HTMLButtonElement>(null);
  const panel = useRef<HTMLDivElement>(null);
  const search = useRef<HTMLInputElement>(null);
  const listId = useId();
  const selected = options.find(option => option.value === value) || allOption;
  const needle = query.trim().toLowerCase();
  const matches = options.filter(option => [option.label, option.description, option.meta, option.searchText].join(' ').toLowerCase().includes(needle));
  const visible = [allOption, ...matches];
  const active = Math.min(activeIndex, visible.length - 1);

  useLayoutEffect(() => {
    if (!open) return;
    const position = () => {
      const bounds = trigger.current?.getBoundingClientRect();
      if (!bounds) return;
      if (bounds.bottom <= 0 || bounds.top >= window.innerHeight) { setOpen(false); return; }
      const width = Math.min(Math.max(bounds.width, minWidth), window.innerWidth - 24);
      const below = Math.max(0, window.innerHeight - bounds.bottom - 20);
      const above = Math.max(0, bounds.top - 20);
      const upwards = below < 240 && above > below;
      setPlacement({
        width, left: Math.max(12, Math.min(bounds.left, window.innerWidth - width - 12)),
        maxHeight: Math.min(360, upwards ? above : below),
        ...(upwards ? { bottom: window.innerHeight - bounds.top + 8 } : { top: bounds.bottom + 8 }),
      });
    };
    const scroll = (event: Event) => { if (!(event.target instanceof Node) || !panel.current?.contains(event.target)) position(); };
    position();
    window.addEventListener('resize', position);
    window.addEventListener('scroll', scroll, true);
    return () => { window.removeEventListener('resize', position); window.removeEventListener('scroll', scroll, true); };
  }, [open, minWidth]);

  useEffect(() => {
    if (!open) return;
    const outside = (event: PointerEvent) => {
      if (!trigger.current?.contains(event.target as Node) && !panel.current?.contains(event.target as Node)) setOpen(false);
    };
    document.addEventListener('pointerdown', outside);
    return () => document.removeEventListener('pointerdown', outside);
  }, [open]);

  useEffect(() => {
    if (open) document.getElementById(`${listId}-option-${active}`)?.scrollIntoView({ block: 'nearest' });
  }, [open, placement, active, query, listId]);

  const close = () => { setOpen(false); trigger.current?.focus(); };
  const show = () => {
    setQuery(''); setPlacement(null);
    setActiveIndex(Math.max(0, [allOption, ...options].findIndex(option => option.value === value)));
    setOpen(true);
  };
  const choose = (option: FilterOption) => { onChange(option.value); close(); };

  return <>
    <button ref={trigger} type="button" aria-label={`${label}筛选：${selected.label}`} aria-haspopup="listbox"
      aria-expanded={open} aria-controls={open ? listId : undefined}
      onClick={() => open ? close() : show()}
      onKeyDown={event => { if (event.key === 'ArrowDown' || event.key === 'ArrowUp') { event.preventDefault(); show(); } }}
      className={`inline-flex max-w-full items-center gap-1.5 rounded-xl border px-2.5 py-1.5 text-xs outline-none transition-colors focus-visible:ring-2 focus-visible:ring-indigo-300 ${open ? 'border-indigo-200 bg-indigo-50/50' : 'border-slate-200 bg-slate-50 hover:border-indigo-200 hover:bg-indigo-50/30'}`}>
      <span aria-hidden="true" className="flex shrink-0 text-indigo-600">{icon}</span>
      <span className="shrink-0 font-medium text-slate-500">{label}:</span>
      <span className="max-w-[180px] truncate font-bold text-slate-800">{selected.label}</span>
      <ChevronDown aria-hidden="true" className={`ml-1 h-3.5 w-3.5 shrink-0 text-slate-500 transition-transform ${open ? 'rotate-180' : ''}`} />
    </button>
    {open && placement && createPortal(<div ref={panel} data-cockpit-filter-menu={label} style={placement}
      className="fixed z-[60] flex flex-col overflow-hidden rounded-2xl border border-slate-200/80 bg-white p-1.5 shadow-[0_12px_36px_rgba(15,23,42,0.14)]"
      onKeyDown={event => {
        if (event.key === 'Escape') { event.preventDefault(); event.stopPropagation(); close(); }
        else if (event.key === 'Tab') close();
        else if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
          event.preventDefault(); setActiveIndex(index => (Math.min(index, visible.length - 1) + (event.key === 'ArrowDown' ? 1 : -1) + visible.length) % visible.length);
        } else if (event.key === 'Enter') { event.preventDefault(); choose(visible[active]); }
      }}>
      <div className="shrink-0 border-b border-slate-100 px-1.5 pb-2 pt-1">
        <div className="flex items-center gap-2 rounded-lg border border-slate-200/70 bg-slate-50 px-2.5 focus-within:border-indigo-200 focus-within:ring-2 focus-within:ring-indigo-100">
          <Search aria-hidden="true" className="h-3.5 w-3.5 shrink-0 text-slate-400" />
          <input ref={search} autoFocus aria-label={`${label}搜索`} aria-controls={listId} aria-activedescendant={`${listId}-option-${active}`}
            value={query} placeholder={placeholder} className="min-w-0 flex-1 bg-transparent py-2 text-xs text-slate-800 outline-none placeholder:text-slate-400"
            onChange={event => { setQuery(event.target.value); setActiveIndex(event.target.value.trim() ? 1 : 0); }} />
          {query && <button type="button" tabIndex={-1} aria-label={`清空${label}搜索`} className="text-slate-400 hover:text-slate-600"
            onClick={() => { setQuery(''); setActiveIndex(0); search.current?.focus(); }}><X className="h-3.5 w-3.5" /></button>}
        </div>
      </div>
      <div id={listId} role="listbox" aria-label={`${label}列表`} className="min-h-0 overflow-y-auto overscroll-contain pt-1">
        {visible.map((option, index) => <button key={option.value} id={`${listId}-option-${index}`} type="button" role="option" tabIndex={-1}
          aria-selected={value === option.value} onPointerMove={() => setActiveIndex(index)} onClick={() => choose(option)}
          className={`flex w-full items-center gap-2 rounded-xl px-2.5 py-2 text-left outline-none transition-colors ${value === option.value ? 'bg-indigo-50 text-indigo-700' : active === index ? 'bg-slate-50 text-slate-900' : 'text-slate-700'}`}>
          {option.leading && <span aria-hidden="true" className="flex shrink-0 items-center justify-center">{option.leading}</span>}
          <span className="min-w-0 flex-1"><span className="block truncate text-xs font-semibold">{option.label}</span>{option.description && <span className="mt-0.5 block truncate text-[10px] text-slate-400">{option.description}</span>}</span>
          {option.trailing ? <span className="flex shrink-0 items-center">{option.trailing}</span> : option.meta && <span className="shrink-0 text-[10px] font-medium text-slate-400">{option.meta}</span>}
          <Check aria-hidden="true" className={`h-3.5 w-3.5 shrink-0 text-indigo-600 ${value === option.value ? '' : 'invisible'}`} />
        </button>)}
      </div>
      {matches.length === 0 && <p role="status" className="px-3 py-5 text-center text-xs text-slate-400">没有找到匹配的{label}</p>}
    </div>, document.body)}
  </>;
}
