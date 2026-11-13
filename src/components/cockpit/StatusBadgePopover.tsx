import { useEffect, useId, useLayoutEffect, useRef, useState, type ReactNode } from 'react';
import { createPortal } from 'react-dom';
import { ChevronRight, Film, HelpCircle, ShieldCheck, X } from 'lucide-react';
import { CockpitModal } from './CockpitModal';

export const STATUS_BADGE_FRAME = 'inline-flex w-max flex-none self-center items-center whitespace-nowrap align-middle border font-sans shadow-2xs outline-none transition-colors select-none focus-visible:ring-2 focus-visible:ring-indigo-300';

/** Badge geometry stays with its row; the reading panel lives outside clipped containers. */
export function StatusBadgePopover({ label, className, badge, children, onRules, kind, status, heading }: {
  label: string;
  className: string;
  badge: ReactNode;
  children: ReactNode;
  onRules: () => void;
  kind: 'account' | 'video';
  status: string;
  heading: ReactNode;
}) {
  const id = useId();
  const trigger = useRef<HTMLButtonElement>(null), panel = useRef<HTMLDivElement>(null);
  const timer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);
  const pinned = useRef(false);
  const skipFocus = useRef(false);
  const [open, setOpen] = useState(false);
  const [position, setPosition] = useState<{ left: number; top: number } | null>(null);
  const cancelTimer = () => clearTimeout(timer.current);
  const close = () => { cancelTimer(); pinned.current = false; setOpen(false); setPosition(null); };
  const focusTrigger = () => {
    if (document.activeElement !== trigger.current) { skipFocus.current = true; trigger.current?.focus({ preventScroll: true }); }
  };
  const dismiss = () => { close(); if (panel.current?.contains(document.activeElement)) focusTrigger(); };
  const show = () => {
    cancelTimer();
    document.dispatchEvent(new CustomEvent('cockpit-status-open', { detail: id }));
    setOpen(true);
  };
  const leave = () => { cancelTimer(); if (!pinned.current) timer.current = setTimeout(close, 140); };
  useEffect(() => () => clearTimeout(timer.current), []);
  useLayoutEffect(() => {
    if (!open) return;
    const place = () => {
      if (!trigger.current || !panel.current) return;
      const a = trigger.current.getBoundingClientRect(), b = panel.current.getBoundingClientRect();
      const margin = 12, gap = 8;
      const left = Math.max(margin, Math.min(a.left, window.innerWidth - b.width - margin));
      const below = a.bottom + gap, above = a.top - b.height - gap;
      const preferBelow = kind === 'video' ? below + b.height <= window.innerHeight - margin || above < margin : above < margin;
      const top = Math.max(margin, Math.min(preferBelow ? below : above, window.innerHeight - b.height - margin));
      setPosition(previous => previous?.left === left && previous.top === top ? previous : { left, top });
    };
    const outside = (event: PointerEvent) => {
      if (event.target instanceof Node && !trigger.current?.contains(event.target) && !panel.current?.contains(event.target)) close();
    };
    const keydown = (event: KeyboardEvent) => {
      if (event.key !== 'Escape') return;
      event.preventDefault(); event.stopImmediatePropagation(); dismiss();
    };
    const scroll = (event: Event) => { if (!(event.target instanceof Node) || !panel.current?.contains(event.target)) close(); };
    const other = (event: Event) => { if ((event as CustomEvent<string>).detail !== id) close(); };
    const observer = new ResizeObserver(place);
    if (panel.current) observer.observe(panel.current);
    if (trigger.current) observer.observe(trigger.current);
    place();
    window.addEventListener('resize', place);
    window.addEventListener('scroll', scroll, true);
    window.addEventListener('keydown', keydown, true);
    document.addEventListener('pointerdown', outside, true);
    document.addEventListener('cockpit-status-open', other);
    return () => {
      observer.disconnect();
      window.removeEventListener('resize', place);
      window.removeEventListener('scroll', scroll, true);
      window.removeEventListener('keydown', keydown, true);
      document.removeEventListener('pointerdown', outside, true);
      document.removeEventListener('cockpit-status-open', other);
    };
  }, [open, id, kind]);

  return <>
    <button ref={trigger} type="button" data-account-tag={kind === 'account' ? 'true' : undefined}
      data-video-traffic-tag={kind === 'video' ? status : undefined}
      aria-label={label} aria-haspopup="dialog" aria-expanded={open} aria-controls={open ? id : undefined}
      onMouseEnter={() => { cancelTimer(); timer.current = setTimeout(show, 160); }} onMouseLeave={leave}
      onFocus={() => { if (skipFocus.current) skipFocus.current = false; else show(); }} onBlur={event => {
        if (!(event.relatedTarget instanceof Node) || !panel.current?.contains(event.relatedTarget)) {
          if (!pinned.current) close();
        }
      }}
      onKeyDown={event => {
        if (open && event.key === 'Tab' && !event.shiftKey) {
          event.preventDefault(); pinned.current = true; panel.current?.querySelector('button')?.focus();
        }
      }}
      onClick={event => { event.stopPropagation(); if (pinned.current) close(); else { pinned.current = true; show(); } }}
      className={`${STATUS_BADGE_FRAME} ${className}`}>
      {badge}
    </button>
    {open && createPortal(<div ref={panel} id={id} role="dialog" aria-label={`${label}说明`}
      data-status-popover="true" data-account-rating-tooltip={kind === 'account' ? 'true' : undefined}
      data-video-rating-tooltip={kind === 'video' ? 'true' : undefined}
      onMouseEnter={cancelTimer} onMouseLeave={leave} onClick={event => event.stopPropagation()}
      onBlur={event => {
        if (!(event.relatedTarget instanceof Node) || (!panel.current?.contains(event.relatedTarget) && !trigger.current?.contains(event.relatedTarget))) close();
      }}
      onKeyDown={event => {
        if (event.key !== 'Tab') return;
        const buttons = panel.current?.querySelectorAll('button');
        if (buttons?.length && ((event.shiftKey && document.activeElement === buttons[0]) || (!event.shiftKey && document.activeElement === buttons[buttons.length - 1]))) {
          event.preventDefault(); dismiss();
        }
      }}
      style={{ left: position?.left ?? 0, top: position?.top ?? 0, visibility: position ? 'visible' : 'hidden' }}
      className={`fixed z-[100] max-h-[calc(100dvh-24px)] max-w-[calc(100vw-24px)] overflow-y-auto border border-slate-200/90 bg-white p-3.5 text-left font-sans text-xs leading-4 shadow-xl ${kind === 'account' ? 'w-80 rounded-xl text-slate-700' : 'w-76 rounded-2xl text-slate-600 backdrop-blur-md'}`}>
      <div className={`flex justify-between gap-1 border-b border-slate-100 ${kind === 'account' ? 'mb-2.5 items-center pb-2' : 'items-start pb-2.5'}`}>
        {heading}
        <button type="button" aria-label="关闭标签说明" onClick={dismiss} className="flex h-5 w-5 flex-none items-center justify-center rounded-md text-slate-400 hover:bg-slate-100 hover:text-slate-600"><X className="h-3.5 w-3.5" /></button>
      </div>
      {children}
      <div className={kind === 'account' ? 'mt-1' : 'mt-3 flex flex-wrap items-center justify-between gap-2 border-t border-slate-100 pt-2'}>
        {kind === 'video' && <span className="text-[10px] text-slate-400">短剧视频表现八阶梯队</span>}
        <button type="button" aria-label="查看完整标签规则" onClick={() => { close(); focusTrigger(); skipFocus.current = true; onRules(); }}
          className={kind === 'account' ? 'flex w-full items-center justify-center gap-1 rounded-md bg-indigo-50/70 px-2 py-1 text-[11px] font-semibold text-indigo-700 hover:bg-indigo-100' : 'flex items-center gap-0.5 text-xs font-bold text-indigo-600 hover:text-indigo-800'}>
          {kind === 'account' && <HelpCircle className="h-3 w-3 flex-none" />}{kind === 'account' ? '查看完整等级、阶段与指示符规则表' : '完整分级规则标准'}<ChevronRight className="h-3 w-3 flex-none" />
        </button>
      </div>
    </div>, document.body)}
  </>;
}

export function StatusBadgeRulesDialog({ title, onClose, children, kind }: { title: string; onClose: () => void; children: ReactNode; kind: 'account' | 'video' }) {
  const video = kind === 'video';
  return <CockpitModal label={title} onClose={onClose} width={video ? 'max-w-2xl' : 'max-w-xl'} rounding={video ? 'rounded-3xl' : 'rounded-2xl'} testId="status-rules-backdrop">
    <div className={`flex flex-none items-center justify-between gap-3 ${video ? 'bg-gradient-to-r from-slate-900 via-indigo-950 to-slate-900 px-6 py-5 text-white' : 'mx-5 mt-5 border-b border-slate-100 pb-3 text-slate-900'}`}>
      <div className="flex min-w-0 items-center gap-3">
        {video && <div className="flex h-10 w-10 flex-none items-center justify-center rounded-2xl border border-indigo-400/30 bg-indigo-500/20 text-amber-300"><Film className="h-5 w-5" /></div>}
        <div><h3 className="flex items-center gap-2 text-base font-extrabold">{!video && <ShieldCheck className="h-5 w-5 flex-none text-indigo-600" />}{video ? '短剧视频表现分级与采集状态判定规则' : '账号状态规则与指示符标准'}</h3>
          <p className={`mt-0.5 text-xs ${video ? 'text-indigo-200/80' : 'text-slate-500'}`}>{video ? '基于播放量阈值与12/24小时观察窗口，规范8类作品表现评级' : '单一复合状态标签：融合「收益等级 + 生命周期阶段 + 数据更新状态」三维一体'}</p></div>
      </div>
      <button type="button" aria-label="关闭标签规则" onClick={onClose} className={`flex h-8 w-8 flex-none items-center justify-center rounded-xl ${video ? 'bg-white/10 text-white/80 hover:bg-white/20' : 'text-slate-400 hover:bg-slate-100'}`}><X className="h-4 w-4" /></button>
    </div>
    <div className={`min-h-0 space-y-4 overflow-y-auto text-xs leading-relaxed text-slate-600 ${video ? 'p-6' : 'p-5'}`}>{children}</div>
    <div className={`flex flex-none items-center justify-end border-t border-slate-100 ${video ? 'bg-slate-50 px-6 py-4' : 'px-5 py-3'}`}><button type="button" onClick={onClose} className="rounded-xl bg-slate-900 px-5 py-2 text-xs font-bold text-white hover:bg-slate-800">我已了解</button></div>
  </CockpitModal>;
}
