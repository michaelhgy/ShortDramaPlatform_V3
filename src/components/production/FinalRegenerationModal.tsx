import React, { useEffect, useRef } from 'react';
import { AlertCircle, RotateCcw, X } from 'lucide-react';
import type { ProductionUnit } from '../../productionTypes';

export function FinalRegenerationModal({ task, busy, onClose, onConfirm }: {
  task: ProductionUnit; busy: boolean; onClose: () => void; onConfirm: () => void;
}) {
  const dialogRef = useRef<HTMLDivElement>(null);
  const cancelRef = useRef<HTMLButtonElement>(null);
  const videos = (task.videos || []).filter(video => video.engine === 'ffmpeg');
  const running = videos.some(video => video.status === 'exporting');
  useEffect(() => {
    const previous = document.activeElement as HTMLElement | null;
    cancelRef.current?.focus();
    return () => previous?.focus();
  }, []);
  useEffect(() => { if (busy) dialogRef.current?.focus(); }, [busy]);
  return <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4 backdrop-blur-xs" onClick={() => { if (!busy) onClose(); }}>
    <div ref={dialogRef} tabIndex={-1} role="dialog" aria-modal="true" aria-label="全部成品重新生成" aria-describedby="regeneration-description"
      className="max-h-[85vh] w-full max-w-lg space-y-4 overflow-y-auto rounded-3xl border border-black/[0.08] bg-white p-5 shadow-2xl"
      onClick={event => event.stopPropagation()} onKeyDown={event => {
        if (event.key === 'Escape' && !busy) { event.stopPropagation(); onClose(); }
        if (event.key === 'Tab') {
          const buttons = Array.from<HTMLButtonElement>(dialogRef.current?.querySelectorAll<HTMLButtonElement>('button:not(:disabled)') || []);
          if (!buttons.length) { event.preventDefault(); return; }
          const first = buttons[0], last = buttons[buttons.length - 1];
          if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last?.focus(); }
          else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first?.focus(); }
        }
      }}>
      <div className="flex items-start justify-between gap-3 border-b border-black/[0.06] pb-3">
        <div><h3 className="text-base font-black text-[#1A1D2E]">全部成品重新生成</h3>
          <p className="mt-1 text-xs text-slate-500 break-words">{task.accountName} × 《{task.dramaName}》</p></div>
        <button type="button" aria-label="关闭重新生成提醒" disabled={busy} onClick={onClose} className="rounded-lg p-1 text-slate-500 hover:bg-slate-100 cursor-pointer disabled:opacity-40"><X className="h-4 w-4" /></button>
      </div>
      <div id="regeneration-description" className="space-y-3 text-sm leading-relaxed text-[#1A1D2E]">
        <div className="flex items-start gap-2 rounded-2xl border border-amber-200 bg-amber-50 p-3 text-amber-900">
          <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" />
          <p>将重新生成本剧集已提交的全部 <strong>{videos.length}</strong> 条成品，包括已完成、失败、已取消及等待中的记录。确认后立即删除这些记录对应的旧成品，再重新合成；生成失败也不会恢复旧视频。</p>
        </div>
        <p>确认后重新读取当前的<strong>中插、尾插设置</strong>，按“全局 → 本剧集 → 本素材”逐层生效，不沿用首次提交的插片配方。请先保存需要修改的设置。</p>
        <p className="text-xs text-slate-500">沿用原素材和原模板；重新生成沿用原文件名，不另存版本。不会重新生成模板，也不重复增加模板使用次数。已提交的发布任务不会自动替换视频，重新生成期间请勿继续发布。</p>
        {running && <p role="alert" className="rounded-xl bg-rose-50 p-3 text-xs text-rose-700">本剧集正在合成。请先在任务中心暂停后续队列，等待当前一条结束后再操作。暂停后重新生成的任务仍会等待，需手动继续队列。</p>}
      </div>
      <div className="flex justify-end gap-2 border-t border-black/[0.06] pt-3">
        <button ref={cancelRef} type="button" disabled={busy} onClick={onClose} className="rounded-xl border border-black/[0.08] px-4 py-2 text-xs font-bold text-slate-600 hover:bg-slate-50 cursor-pointer disabled:opacity-40">取消</button>
        <button type="button" disabled={busy || running} onClick={onConfirm} className="flex items-center gap-1.5 rounded-xl bg-[#1A1D2E] px-4 py-2 text-xs font-black text-[#DDFD00] hover:bg-black cursor-pointer disabled:opacity-40 disabled:cursor-not-allowed">
          <RotateCcw className={`h-3.5 w-3.5 ${busy ? 'animate-spin' : ''}`} />{busy ? '提交中…' : '确认全部重新生成'}
        </button>
      </div>
    </div>
  </div>;
}
