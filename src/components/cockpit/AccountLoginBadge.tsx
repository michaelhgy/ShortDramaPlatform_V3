import { useEffect, useId, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { Check, CircleAlert, HelpCircle, X } from 'lucide-react';
import type { AccountInfo } from '../../types/shortDramaOps';
import { getLoginState } from '../../services/accountMatrixSort';

const themes = {
  valid: { label: '登录有效', color: 'bg-emerald-500 text-white', icon: Check, description: '小V猫最近一次核验时登录有效。' },
  invalid: { label: '登录失效', color: 'bg-rose-500 text-white', icon: CircleAlert, description: '请在小V猫重新登录此账号，再更新数据核验。' },
  unknown: { label: '未获取', color: 'bg-slate-400 text-white', icon: HelpCircle, description: '尚未取得明确的登录结果，可通过更新数据核验。' },
};

function checkedTime(value?: string) {
  if (!value) return '尚未核验';
  const date = new Date(value);
  if (!Number.isFinite(date.getTime())) return '核验时间未知';
  return new Intl.DateTimeFormat('zh-CN', { timeZone: 'Asia/Shanghai', year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', hour12: false }).format(date);
}

/** A login observation, separate from the revenue freshness indicator. */
export function AccountLoginBadge({ account }: { account: AccountInfo }) {
  const theme = themes[getLoginState(account.loginStatus)], Icon = theme.icon;
  const [open, setOpen] = useState(false);
  const [position, setPosition] = useState<{ left: number; top: number } | null>(null);
  const trigger = useRef<HTMLButtonElement>(null), panel = useRef<HTMLDivElement>(null);
  const pinned = useRef(false), timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const id = useId(), skipFocus = useRef(false);
  const cancel = () => { if (timer.current) clearTimeout(timer.current); };
  const close = () => { cancel(); pinned.current = false; setOpen(false); };
  const dismiss = () => {
    close();
    if (trigger.current && document.activeElement !== trigger.current) { skipFocus.current = true; trigger.current.focus({ preventScroll: true }); }
  };
  const show = () => {
    cancel();
    const bounds = trigger.current?.getBoundingClientRect();
    if (bounds) setPosition({ left: Math.max(12, Math.min(bounds.left - 8, window.innerWidth - 268)), top: bounds.bottom + 8 });
    setOpen(true);
  };
  const leave = () => { cancel(); if (!pinned.current) timer.current = setTimeout(() => setOpen(false), 120); };
  useEffect(() => () => { if (timer.current) clearTimeout(timer.current); }, []);
  useEffect(() => {
    if (!open) return;
    // Flip upward for cards close to the viewport bottom.
    const bounds = trigger.current?.getBoundingClientRect();
    const height = panel.current?.getBoundingClientRect().height || 180;
    if (bounds) setPosition({ left: Math.max(12, Math.min(bounds.left - 8, window.innerWidth - 268)),
      top: bounds.bottom + 8 + height > window.innerHeight - 12 ? Math.max(12, bounds.top - height - 8) : bounds.bottom + 8 });
    const outside = (event: PointerEvent) => { if (!trigger.current?.contains(event.target as Node) && !panel.current?.contains(event.target as Node)) close(); };
    const escape = (event: KeyboardEvent) => { if (event.key === 'Escape') dismiss(); };
    const moved = () => close();
    document.addEventListener('pointerdown', outside);
    document.addEventListener('keydown', escape);
    window.addEventListener('resize', moved);
    window.addEventListener('scroll', moved, true);
    return () => { document.removeEventListener('pointerdown', outside); document.removeEventListener('keydown', escape); window.removeEventListener('resize', moved); window.removeEventListener('scroll', moved, true); };
  }, [open]);
  return <>
    <button ref={trigger} type="button" data-account-login={getLoginState(account.loginStatus)}
      aria-label={`${account.name}：${theme.label}`} aria-expanded={open} aria-controls={open ? id : undefined} aria-haspopup="dialog"
      onMouseEnter={show} onMouseLeave={leave} onFocus={() => { if (skipFocus.current) skipFocus.current = false; else show(); }}
      onBlur={event => { if (!panel.current?.contains(event.relatedTarget as Node)) close(); }}
      onClick={event => { event.stopPropagation(); pinned.current = true; show(); }}
      className={`absolute -bottom-0.5 -right-0.5 z-10 flex h-[18px] w-[18px] items-center justify-center rounded-full border-2 border-white shadow-xs outline-none focus-visible:ring-2 focus-visible:ring-indigo-400 focus-visible:ring-offset-1 ${theme.color}`}>
      <Icon aria-hidden="true" className="h-3 w-3" strokeWidth={2.8} />
    </button>
    {open && position && createPortal(<div ref={panel} id={id} role="dialog" aria-label={`${account.name}的登录状态`}
      onMouseEnter={cancel} onMouseLeave={leave} onClick={event => event.stopPropagation()}
      onBlur={event => { if (!panel.current?.contains(event.relatedTarget as Node) && !trigger.current?.contains(event.relatedTarget as Node)) close(); }}
      style={position} className="fixed z-[110] w-64 max-w-[calc(100vw-24px)] rounded-xl border border-slate-200 bg-white p-3 text-left text-xs leading-5 text-slate-600 shadow-xl">
      <div className="mb-1.5 flex items-center justify-between gap-2 border-b border-slate-100 pb-1.5">
        <strong className="flex items-center gap-1.5 text-slate-900"><span className={`inline-flex h-4 w-4 items-center justify-center rounded-full ${theme.color}`}><Icon className="h-3 w-3" aria-hidden="true" /></span>{theme.label}</strong>
        <button type="button" aria-label="关闭登录状态说明" onClick={dismiss} className="rounded p-0.5 text-slate-400 hover:bg-slate-100"><X className="h-3.5 w-3.5" /></button>
      </div>
      <p>{theme.description}</p>
      {getLoginState(account.loginStatus) === 'unknown' && account.loginStatus && <p>最近返回：{account.loginStatus}</p>}
      <p className="mt-1 text-[11px] text-slate-400">最近核验：{checkedTime(account.loginCheckedAt)}</p>
      <p className="mt-1 text-[11px] text-slate-400">显示最近核验结果，当前登录情况可能已变化。</p>
    </div>, document.body)}
  </>;
}
