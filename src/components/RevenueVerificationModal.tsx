import React, { useEffect, useRef, useState } from 'react';
import { AlertCircle, Loader2, RefreshCw, ShieldCheck, X } from 'lucide-react';
import { deferRevenueVerification, loadRevenueVerifications, refreshRevenueVerification, submitRevenueVerification, type RevenueVerification } from '../api/revenueQuerySettings';

/** Global: a background collection can ask for verification from any page. */
export function RevenueVerificationModal() {
  const [challenge, setChallenge] = useState<RevenueVerification | null>(null);
  const [answer, setAnswer] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [pollError, setPollError] = useState('');
  const [hidden, setHidden] = useState(false);
  const [count, setCount] = useState(0);
  const current = useRef('');
  const generation = useRef('');
  const suspended = useRef(false);
  const previousFocus = useRef<HTMLElement | null>(null);
  const input = useRef<HTMLInputElement>(null);
  useEffect(() => {
    let disposed = false;
    let timer: ReturnType<typeof setTimeout>;
    const poll = async () => {
      try {
        const data = await loadRevenueVerifications();
        if (disposed) return;
        setPollError(''); setCount(data.items.length);
        if (!suspended.current) {
          const next = data.items.find(item => item.id === current.current) || data.items[0] || null;
          if (next?.id !== current.current) { setHidden(false); setError(''); }
          if ((next?.generation || '') !== generation.current) setAnswer('');
          current.current = next?.id || ''; generation.current = next?.generation || '';
          setChallenge(next);
        }
      } catch {
        if (!disposed) setPollError('验证状态暂未刷新，请检查软件连接后重试');
      } finally { if (!disposed) timer = setTimeout(poll, 1500); }
    };
    void poll();
    return () => { disposed = true; clearTimeout(timer); };
  }, []);
  useEffect(() => {
    if (!challenge || hidden) return;
    previousFocus.current = document.activeElement as HTMLElement | null;
    input.current?.focus();
    return () => previousFocus.current?.focus();
  }, [challenge?.id, hidden]);
  if (!challenge) return null;
  if (hidden) return <button type="button" onClick={() => setHidden(false)} className="fixed bottom-6 right-6 z-[100] flex items-center gap-2 rounded-xl border border-black/[0.08] bg-[#1A1D2E] px-4 py-3 text-xs font-bold text-[#DDFD00] shadow-xl"><ShieldCheck className="h-4 w-4" />平阅等待验证码{count > 1 ? `（${count}项）` : ''}</button>;
  const act = async (action: 'submit' | 'refresh' | 'defer') => {
    setBusy(true); suspended.current = true; setError('');
    try {
      if (action === 'refresh') {
        const next = await refreshRevenueVerification(challenge.id);
        generation.current = next.generation; setChallenge(next); setAnswer(''); input.current?.focus();
      } else if (action === 'defer') {
        await deferRevenueVerification(challenge.id); setChallenge(null); current.current = ''; generation.current = '';
      } else {
        const result = await submitRevenueVerification(challenge.id, challenge.generation, answer);
        if (result.verified) {
          window.dispatchEvent(new CustomEvent('revenue-verification-completed', {detail: {id: challenge.id}}));
          setChallenge(null); current.current = ''; generation.current = ''; setAnswer('');
        } else {
          if (result.generation) { generation.current = result.generation; setChallenge({...challenge, ...result}); }
          setAnswer(''); setError(result.message || '验证未通过，请重新填写'); input.current?.focus();
        }
      }
    } catch (cause) { setError(cause instanceof Error ? cause.message : '操作未完成，请重试'); }
    finally { suspended.current = false; setBusy(false); }
  };
  return <div className="fixed inset-0 z-[100] flex items-center justify-center bg-[#1A1D2E]/40 p-4 backdrop-blur-sm">
    <section role="dialog" aria-modal="true" aria-labelledby="revenue-verification-title" className="w-full max-w-md overflow-hidden rounded-2xl border border-white/30 bg-white shadow-2xl" onKeyDown={event => {
      if (event.key === 'Escape' && !busy) setHidden(true);
      if (event.key === 'Tab') {
        const elements = Array.from<HTMLElement>(event.currentTarget.querySelectorAll('button:not(:disabled),input:not(:disabled)'));
        const first = elements[0], last = elements[elements.length-1];
        if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last?.focus(); }
        else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first?.focus(); }
      }
    }}>
      <header className="flex items-center justify-between border-b border-black/[0.06] px-5 py-4"><div><h3 id="revenue-verification-title" className="flex items-center gap-2 text-sm font-black text-[#1A1D2E]"><ShieldCheck className="h-4 w-4" />{challenge.collector_name} · 人工验证</h3><p className="mt-1 text-[10px] text-slate-400">看图填写，提交后继续未完成的查询</p></div><button type="button" aria-label="收起验证码弹窗" disabled={busy} onClick={() => setHidden(true)} className="rounded-lg p-2 text-slate-400 hover:bg-slate-100"><X className="h-4 w-4" /></button></header>
      <form onSubmit={event => { event.preventDefault(); if (!busy && answer.trim()) void act('submit'); }}>
        <div className="space-y-4 p-5">
          <div className="rounded-xl bg-slate-50 p-3 text-[11px] leading-5 text-slate-500">验证通过后复用当前查询会话；网站再次要求验证时会重新提示。其他采集项继续执行。<p className="mt-1 break-all text-[10px] text-slate-400">查单链接：{challenge.source_url}</p></div>
          <div className="flex min-h-20 items-center justify-center gap-4 rounded-xl border border-black/[0.06] bg-slate-50/50 p-4">{challenge.image ? <img src={challenge.image} alt="平阅原站验证码" className="max-h-20 max-w-[210px] rounded bg-white" /> : <span className="text-xs text-slate-400">图片未加载，请刷新</span>}<button type="button" disabled={busy} onClick={() => void act('refresh')} className="flex shrink-0 items-center gap-1 text-[11px] font-semibold text-slate-500 disabled:opacity-40"><RefreshCw className="h-3.5 w-3.5" />换一张</button></div>
          <label className="block text-xs font-semibold text-[#1A1D2E]">验证码<input ref={input} aria-label="验证码" value={answer} disabled={busy} onChange={event => setAnswer(event.target.value)} autoComplete="off" maxLength={12} className="mt-2 w-full rounded-xl border border-black/[0.08] bg-white px-3 py-2.5 text-sm font-normal outline-none focus:border-[#1A1D2E]" placeholder="请输入图片中的字符" /></label>
          {(error || challenge.message || pollError) && <p role="alert" className="flex items-start gap-1.5 rounded-xl bg-amber-50 p-3 text-[11px] leading-5 text-amber-800"><AlertCircle className="mt-0.5 h-3.5 w-3.5 shrink-0" />{error || challenge.message || pollError}</p>}
          <p className="text-[10px] leading-5 text-slate-400">提取码已从采集器详情读取。如已更换，请在资料中心 → 查单管理中修改。</p>
        </div>
        <footer className="flex items-center justify-between gap-3 border-t border-black/[0.06] bg-slate-50/50 px-5 py-4"><button type="button" disabled={busy} onClick={() => void act('defer')} className="text-xs font-semibold text-slate-500 disabled:opacity-40">本次稍后处理</button><button type="submit" disabled={busy || !answer.trim()} className="flex items-center gap-1.5 rounded-xl bg-[#1A1D2E] px-4 py-2.5 text-xs font-bold text-[#DDFD00] disabled:opacity-40">{busy && <Loader2 className="h-3.5 w-3.5 animate-spin" />}验证并继续</button></footer>
      </form>
    </section>
  </div>;
}
