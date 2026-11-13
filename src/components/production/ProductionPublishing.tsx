import React, { useEffect, useMemo, useState } from 'react';
import { ChevronDown, ExternalLink, MapPin, RefreshCw } from 'lucide-react';
import { getProductionPublishProgress, getProductionPublishIndex, type ProductionPublishCard, type ProductionPublishProgress } from '../../api/publishing';
import { publicationsByVideo, publicationCounts, publicationLocation, publicationMount, publicationStatus, publicationSummary, publicationTime, type VideoPublication } from './productionPublishingModel';

const tones: Record<string, string> = { emerald: 'text-emerald-700', violet: 'text-violet-700', blue: 'text-sky-700', amber: 'text-amber-700', slate: 'text-slate-500' };
const badges: Record<string, string> = { emerald: 'border-emerald-100 bg-emerald-50 text-emerald-700', amber: 'border-amber-100 bg-amber-50 text-amber-700', slate: 'border-slate-100 bg-slate-100/80 text-slate-500' };

export function useProductionPublishIndex() {
  const [items, setItems] = useState<Record<string, ProductionPublishCard>>({});
  useEffect(() => {
    let active = true, loading = false;
    const read = async () => {
      if (!active || loading || document.hidden) return;
      loading = true;
      try { const next = await getProductionPublishIndex(); if (active) setItems(next.items); } catch { /* Keep the last local snapshot. */ }
      finally { loading = false; }
    };
    void read(); const timer = setInterval(() => void read(), 5000);
    const visible = () => { if (!document.hidden) void read(); };
    window.addEventListener('focus', visible);
    return () => { active = false; clearInterval(timer); window.removeEventListener('focus', visible); };
  }, []);
  return items;
}

export function ProductionPublishCardProgress({ value }: { value: ProductionPublishCard }) {
  const percent = value.total ? Math.round(value.done / value.total * 100) : 0;
  const states = [value.processing && `处理中 ${value.processing}`, value.queued && `排队 ${value.queued}`, value.paused && `已暂停 ${value.paused}`, value.issues && `待处理 ${value.issues}`].filter(Boolean);
  return <div data-testid="production-card-publishing" className="space-y-2 text-[11px]">
    <div className="flex items-center justify-between gap-2"><span className="font-bold text-slate-600">{value.draft_only ? '草稿就绪' : '发布提交'} <strong className="tabular-nums text-violet-700">{value.done}</strong><span className="font-normal text-slate-400"> / {value.total} 份</span></span><span className="font-bold tabular-nums text-violet-700">{percent}%</span></div>
    <div role="progressbar" aria-label="发布完成份数" aria-valuemin={0} aria-valuemax={value.total || 1} aria-valuenow={value.done} title="按小V猫确认成功的份数计算；官方接受定时即完成交付。" className="h-1.5 overflow-hidden rounded-full bg-violet-100"><div className="h-full rounded-full bg-violet-500 transition-[width] duration-300" style={{width:`${percent}%`}}/></div>
    <div className="flex flex-wrap gap-x-2 gap-y-1 text-slate-500">{states.length ? states.join(' · ') : value.draft_only ? '全部本地草稿已就绪' : value.scheduled ? (value.delivered === value.total ? '已交付官方，按设定时间发布' : '已提交平台定时，等待核实交付') : value.delivered === value.total ? '全部作品已交付官方' : '全部发布提交已完成'}</div>
  </div>;
}

export function useProductionPublishing(taskId: string, workbenchOpen: boolean) {
  const [data, setData] = useState<ProductionPublishProgress | null>(null);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState('');
  const [revision, setRevision] = useState(0);
  useEffect(() => {
    if (!taskId || workbenchOpen) return;
    let active = true, loading = false, timer: ReturnType<typeof setTimeout> | undefined;
    const read = async () => {
      if (!active || loading || document.hidden) return;
      loading = true; setRefreshing(true);
      if (timer) clearTimeout(timer);
      try {
        const next = await getProductionPublishProgress(taskId);
        if (!active) return;
        setData(next); setError(next.refresh_error || '');
        if (next.needs_poll) timer = setTimeout(() => void read(), next.refresh_error ? 15000 : 5000);
      } catch (e) {
        if (active) { setError(e instanceof Error ? e.message : '发布状态暂时读取失败'); timer = setTimeout(() => void read(), 15000); }
      } finally { loading = false; if (active) setRefreshing(false); }
    };
    const visible = () => { if (!document.hidden) void read(); };
    void read(); window.addEventListener('focus', visible); document.addEventListener('visibilitychange', visible);
    return () => { active = false; if (timer) clearTimeout(timer); window.removeEventListener('focus', visible); document.removeEventListener('visibilitychange', visible); };
  }, [taskId, workbenchOpen, revision]);
  const current = data?.task_id === taskId ? data : null;
  const videos = useMemo(() => publicationsByVideo(current), [current]);
  return { data: current, videos, refreshing, error, refresh: () => setRevision(n => n + 1) };
}

export function ProductionPublishMount({ value }: { value?: VideoPublication }) {
  const badge = publicationMount(value);
  return badge ? <span title={badge.title} data-testid="production-mount" className={`shrink-0 whitespace-nowrap rounded-md border px-1.5 py-0.5 text-[10px] font-bold ${badges[badge.tone]}`}>{badge.text}</span> : null;
}

export function ProductionPublishLocation({ videos }: { videos: Record<string, VideoPublication> }) {
  const location = publicationLocation(videos);
  return location ? <span data-testid="production-location" className="flex max-w-full min-w-0 items-center gap-1 text-xs text-slate-500" title={location.title}><MapPin size={13} className="shrink-0 text-slate-400"/><span className="shrink-0">发布位置：</span><span className="min-w-0 truncate">{location.text}</span></span> : null;
}

export function ProductionPublishTotal({ videos, refreshing, error, onRefresh }: { videos: Record<string, VideoPublication>; refreshing: boolean; error: string; onRefresh: () => void }) {
  const rows = Object.values(videos).flatMap(v => v.items), n = publicationCounts(rows);
  const onlyDrafts = Object.values(videos).every(v => v.kind === 'draft');
  return <div className="flex min-w-0 flex-wrap items-center gap-2 text-[11px] text-slate-500" data-testid="production-publish-total">
    {rows.length > 0 && <><span className="font-bold">{onlyDrafts ? '草稿就绪' : '发布提交'} <strong className="text-emerald-700">{n.done}</strong>/{n.total} 份</span>{n.processing > 0 && <span>处理中 {n.processing}</span>}{n.queued > 0 && <span>排队 {n.queued}</span>}{n.paused > 0 && <span className="text-amber-700">已暂停 {n.paused}</span>}{n.issues > 0 && <span className="text-amber-700">待处理 {n.issues}</span>}</>}
    <button type="button" title={error || '只读取发布状态，不提交或恢复任务'} aria-label="同步成片发布状态" disabled={refreshing} onClick={onRefresh} className={`inline-flex items-center gap-1 rounded-md px-1.5 py-1 hover:bg-white disabled:opacity-40 ${error ? 'text-amber-700' : 'text-slate-400'}`}><RefreshCw size={12} className={refreshing ? 'animate-spin' : ''}/>{error ? '同步失败，重试' : '同步状态'}</button>
  </div>;
}

export function ProductionPublishVideo({ value, onOpen }: { value?: VideoPublication; onOpen: () => void }) {
  if (!value?.items.length) return <div className="min-w-0 flex-1 basis-60 pl-2 text-[11px] text-slate-400">未提交</div>;
  const summary = publicationSummary(value);
  return <details data-testid="production-video-publishing" className="group min-w-0 flex-1 basis-60 rounded-lg px-2 py-1 open:bg-slate-50/80">
    <summary className="flex cursor-pointer list-none items-center justify-between gap-2 [&::-webkit-details-marker]:hidden"><span className="min-w-0"><span className={`block text-[11px] font-bold ${tones[summary.tone]}`}>{summary.text}</span><span className="mt-1 block text-[10px] text-slate-400">{publicationTime(value)}</span></span><ChevronDown size={13} className="shrink-0 text-slate-400 transition-transform group-open:rotate-180"/></summary>
    <div className="mt-2 space-y-1.5 border-t border-slate-200/70 pt-2">
      {value.items.map(item => <div key={item.key} className="rounded-md bg-white px-2 py-1.5 text-[10px]" data-testid="production-copy-detail"><div className="flex flex-wrap items-center justify-between gap-x-2 gap-y-0.5"><span className="font-bold text-slate-700">第{item.copy}份</span><span className={tones[['success','ready'].includes(item.status) ? (value.kind === 'draft' ? 'violet' : 'emerald') : ['uncertain','failed','needs_help','paused','canceled','rejected'].includes(item.status) ? 'amber' : 'blue']}>{item.status === 'success' && item.delivery_confirmed ? (item.schedule_type === 'timing' ? '官方已定时' : '发布完成') : item.status === 'success' && item.schedule_type === 'timing' ? '定时已提交' : publicationStatus[item.status] || item.status}</span><span className="text-slate-400">{item.time || (value.kind === 'draft' ? '本地草稿' : '立即发布')}</span></div>{item.error && <p className="mt-1 break-words text-amber-700">{item.error}</p>}{(item.local_id || item.draft_id) && <p className="mt-0.5 truncate text-slate-400" title={item.local_id || String(item.draft_id)}>{item.local_id ? `任务 ${item.local_id}` : `草稿 ${item.draft_id}`}</p>}</div>)}
      <button type="button" onClick={onOpen} className="inline-flex items-center gap-1 rounded-md px-1 py-1 text-[10px] font-bold text-slate-600 hover:text-slate-900"><ExternalLink size={11}/>打开发布工作台</button>
    </div>
  </details>;
}
