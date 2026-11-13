import { useEffect, useId, useRef, useState } from 'react';
import { CalendarDays, Check, ChevronDown, X } from 'lucide-react';
import { type CockpitDateRange, dateRangeError, shiftDate } from '../../services/cockpitDateRange';
import { useCockpitData } from './CockpitDataContext';
import { CockpitModal } from './CockpitModal';

const shortcuts = [['yesterday', '昨天'], ['7days', '近7天'], ['14days', '近14天'], ['month', '本月']] as const;
const morePresets = [['30days', '近30天'], ['all', '全部历史']] as const;

export function CockpitDateFilter({ value, onChange }: { value: CockpitDateRange; onChange: (value: CockpitDateRange) => void }) {
  const { today, getDateBounds } = useCockpitData();
  const bounds = getDateBounds(value);
  const [menuOpen, setMenuOpen] = useState(false);
  const [rangeOpen, setRangeOpen] = useState(false);
  const [start, setStart] = useState('');
  const [end, setEnd] = useState('');
  const menu = useRef<HTMLDivElement>(null);
  const moreButton = useRef<HTMLButtonElement>(null);
  const menuId = useId();
  const isDay = typeof value === 'object' && value.kind === 'day';
  const isRange = typeof value === 'object' && value.kind === 'range';
  const isMore = isRange || morePresets.some(([key]) => key === value);
  const error = dateRangeError(start, end, today);
  const compactDate = (date: string) => (date.slice(0, 4) === today.slice(0, 4) ? date.slice(5) : date).replaceAll('-', '.');
  const buttonStyle = (active: boolean) => `relative flex items-center gap-1 whitespace-nowrap rounded-lg px-2.5 py-1.5 text-xs font-semibold transition-colors cursor-pointer focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-400 ${active ? 'bg-white text-indigo-600 shadow-xs' : 'text-slate-600 hover:bg-white/60 hover:text-slate-900'}`;

  useEffect(() => {
    if (!menuOpen) return;
    menu.current?.querySelector<HTMLButtonElement>('[role="menuitem"]')?.focus();
    const outside = (event: PointerEvent) => {
      if (!menu.current?.contains(event.target as Node)) setMenuOpen(false);
    };
    const escape = (event: KeyboardEvent) => {
      if (event.key === 'Escape') { setMenuOpen(false); moreButton.current?.focus(); }
    };
    document.addEventListener('pointerdown', outside);
    document.addEventListener('keydown', escape);
    return () => { document.removeEventListener('pointerdown', outside); document.removeEventListener('keydown', escape); };
  }, [menuOpen]);

  const openRange = () => {
    setStart(isRange ? value.start : shiftDate(today, -7));
    setEnd(isRange ? value.end : shiftDate(today, -1));
    setMenuOpen(false);
    setRangeOpen(true);
  };

  return <>
    <div aria-label="日期筛选" className="inline-flex max-w-full flex-wrap items-center rounded-xl border border-slate-200 bg-slate-100 p-0.5"
      title={`${bounds.start} 至 ${bounds.end}（${bounds.days}天）`}>
      {shortcuts.map(([key, label]) => <button key={key} type="button" aria-pressed={value === key}
        className={buttonStyle(value === key)} onClick={() => { onChange(key); setMenuOpen(false); }}>{label}</button>)}
      <label className={`${buttonStyle(isDay)} focus-within:ring-2 focus-within:ring-indigo-400`}>
        <CalendarDays className="h-3.5 w-3.5" />
        <span>{isDay ? value.date.replaceAll('-', '.') : '指定某日'}</span>
        <input aria-label="指定某日" type="date" max={today} value={isDay ? value.date : ''}
          className="absolute inset-0 h-full w-full cursor-pointer opacity-0"
          onClick={event => { try { event.currentTarget.showPicker?.(); } catch { /* Native input remains usable. */ } }}
          onChange={event => {
            const date = event.target.value;
            if (!dateRangeError(date, date, today)) { onChange({ kind: 'day', date }); setMenuOpen(false); }
          }} />
      </label>
      <div ref={menu} className="relative">
        <button ref={moreButton} type="button" className={buttonStyle(isMore)} aria-haspopup="menu" aria-expanded={menuOpen} aria-controls={menuId}
          onClick={() => setMenuOpen(open => !open)}>
          <span className="max-w-40 truncate">{isRange ? `${compactDate(value.start)}–${compactDate(value.end)}` : isMore ? bounds.label : '更多'}</span>
          <ChevronDown className={`h-3 w-3 transition-transform ${menuOpen ? 'rotate-180' : ''}`} />
        </button>
        {menuOpen && <div id={menuId} role="menu" aria-label="更多日期" className="absolute right-0 top-full z-40 mt-2 w-40 rounded-xl border border-slate-200 bg-white p-1.5 shadow-xl">
          {morePresets.map(([key, label]) => <button key={key} type="button" role="menuitem"
            className="flex w-full items-center justify-between rounded-lg px-3 py-2 text-left text-xs font-medium text-slate-700 hover:bg-indigo-50 focus:bg-indigo-50 focus:outline-none"
            onClick={() => { onChange(key); setMenuOpen(false); moreButton.current?.focus(); }}>
            {label}{value === key && <Check className="h-3.5 w-3.5 text-indigo-600" />}
          </button>)}
          <div className="my-1 border-t border-slate-100" />
          <button type="button" role="menuitem" onClick={openRange}
            className="flex w-full items-center justify-between rounded-lg px-3 py-2 text-left text-xs font-medium text-slate-700 hover:bg-indigo-50 focus:bg-indigo-50 focus:outline-none">
            自定义区间{isRange && <Check className="h-3.5 w-3.5 text-indigo-600" />}
          </button>
        </div>}
      </div>
    </div>
    {rangeOpen && <CockpitModal label="自定义日期区间" onClose={() => setRangeOpen(false)} width="max-w-md">
      <form className="p-6" onSubmit={event => { event.preventDefault(); if (!error) { onChange({ kind: 'range', start, end }); setRangeOpen(false); } }}>
        <div className="mb-5 flex items-center justify-between">
          <h3 className="text-base font-bold text-slate-900">自定义日期区间</h3>
          <button type="button" aria-label="关闭日期选择" className="rounded-lg p-1.5 text-slate-400 hover:bg-slate-100" onClick={() => setRangeOpen(false)}><X className="h-4 w-4" /></button>
        </div>
        <div className="grid grid-cols-2 gap-3">
          <label className="space-y-2 text-xs font-medium text-slate-500">开始日期
            <input type="date" aria-label="开始日期" required value={start} max={today} onChange={event => setStart(event.target.value)}
              className="mt-2 w-full rounded-xl border border-slate-200 bg-slate-50 px-3 py-2 text-sm text-slate-800 focus:border-indigo-500 focus:outline-none" />
          </label>
          <label className="space-y-2 text-xs font-medium text-slate-500">结束日期
            <input type="date" aria-label="结束日期" required value={end} max={today} onChange={event => setEnd(event.target.value)}
              className="mt-2 w-full rounded-xl border border-slate-200 bg-slate-50 px-3 py-2 text-sm text-slate-800 focus:border-indigo-500 focus:outline-none" />
          </label>
        </div>
        <p aria-live="polite" className={`mt-3 min-h-5 text-xs ${error ? 'text-rose-600' : 'text-slate-400'}`}>{error || '包含开始和结束当天'}</p>
        <div className="mt-5 flex justify-end gap-2">
          <button type="button" onClick={() => setRangeOpen(false)} className="rounded-xl px-4 py-2 text-xs font-semibold text-slate-600 hover:bg-slate-100">取消</button>
          <button type="submit" disabled={Boolean(error)} className="rounded-xl bg-indigo-600 px-4 py-2 text-xs font-semibold text-white disabled:cursor-not-allowed disabled:opacity-40">应用</button>
        </div>
      </form>
    </CockpitModal>}
  </>;
}
