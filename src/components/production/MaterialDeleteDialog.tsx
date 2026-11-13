import React, { useEffect, useRef, useState } from 'react';
import { AlertTriangle, LoaderCircle, Trash2, X } from 'lucide-react';
import { deleteV2Material, previewV2MaterialDelete, type MaterialDeletePreview, type V2ProductionTaskListItem } from '../../api/v2Production';

export function MaterialDeleteDialog({ materialId, onClose, onDeleted, onBeforeDelete, onFailure }: {
  materialId: string; onClose: () => void;
  onDeleted: (task: V2ProductionTaskListItem) => void | Promise<void>;
  onBeforeDelete?: () => void | Promise<void>; onFailure?: () => void;
}) {
  const [plan, setPlan] = useState<MaterialDeletePreview | null>(null);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(true);
  const [deleting, setDeleting] = useState(false);
  const [revision, setRevision] = useState(0);
  const dialogRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    let active = true;
    setLoading(true); setError(''); setPlan(null);
    previewV2MaterialDelete(materialId).then(value => { if (active) setPlan(value); })
      .catch(reason => { if (active) setError(reason instanceof Error ? reason.message : '读取删除范围失败'); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [materialId, revision]);
  useEffect(() => {
    const previous = document.activeElement as HTMLElement | null;
    dialogRef.current?.querySelector<HTMLButtonElement>('[data-cancel]')?.focus();
    return () => { if (previous?.isConnected) previous.focus(); };
  }, []);
  const confirm = async () => {
    if (!plan?.can_delete || deleting) return;
    setDeleting(true); setError('');
    try {
      await onBeforeDelete?.();
      const result = await deleteV2Material(materialId, plan.confirmation_token);
      await onDeleted(result.task);
      onClose();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : '删除失败，请稍后重试');
      setPlan(null); onFailure?.();
    } finally { setDeleting(false); }
  };
  return <div className="fixed inset-0 z-[110] flex items-center justify-center bg-black/50 p-4 backdrop-blur-xs" onClick={event => { event.stopPropagation(); if (!deleting) onClose(); }} onKeyDown={event => {
    event.stopPropagation();
    if (event.key === 'Escape' && !deleting) { event.preventDefault(); onClose(); }
    if (event.key === 'Tab') {
      const elements = dialogRef.current?.querySelectorAll<HTMLElement>('button:not(:disabled)');
      if (!elements?.length) return;
      const first = elements[0], last = elements[elements.length - 1];
      if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
      else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
    }
  }}>
    <div ref={dialogRef} role="alertdialog" aria-modal="true" aria-labelledby="material-delete-title" aria-describedby="material-delete-warning" className="flex max-h-[88vh] w-full max-w-xl flex-col rounded-3xl border border-black/[0.08] bg-white p-5 shadow-2xl" onClick={event => event.stopPropagation()}>
      <div className="flex items-center justify-between gap-3"><h3 id="material-delete-title" className="flex items-center gap-2 text-base font-black text-[#1A1D2E]"><AlertTriangle className="h-5 w-5 text-rose-600" />删除素材及对应成片</h3><button type="button" aria-label="关闭删除确认" disabled={deleting} onClick={onClose} className="rounded-lg p-1.5 hover:bg-slate-100"><X className="h-4 w-4" /></button></div>
      <p id="material-delete-warning" className="mt-3 rounded-xl bg-rose-50 p-3 text-xs font-semibold leading-6 text-rose-800">确认后直接删除磁盘上的原素材、对应成片及合成任务，包含排队中的对应任务。文件不进入回收站，无法撤销。</p>
      <div className="mt-3 min-h-0 space-y-3 overflow-y-auto text-xs">
        {loading && <p role="status" className="flex items-center gap-2 py-4 text-slate-500"><LoaderCircle className="h-4 w-4 animate-spin" />正在核对删除范围…</p>}
        {plan && <>
          <div><p className="break-all text-sm font-extrabold text-[#1A1D2E]">{plan.file_name}</p><p className="mt-1 break-all leading-5 text-slate-500">{plan.source_path}</p></div>
          <p className="font-bold text-slate-700">对应成片 {plan.video_count} 条 · 合成任务 {plan.job_count} 条</p>
          <div className="rounded-xl border border-black/[0.06] bg-slate-50 p-3"><p className="mb-2 font-bold text-slate-700">将删除的文件与缓存</p>{plan.files.map(file => <p key={file.path} className="break-all py-1 leading-5 text-slate-600">{file.path}{!file.exists && <span className="ml-1 text-slate-400">（已缺失）</span>}</p>)}{plan.cache_directories.map(path => <p key={path} className="break-all py-1 leading-5 text-slate-600">{path}（本条合成缓存）</p>)}</div>
          <p className="leading-5 text-slate-500">其他素材、公共模板和模板使用计次保留。此操作只删除本地内容。</p>
          {!plan.can_delete && <p role="alert" className="rounded-xl bg-amber-50 p-3 leading-5 text-amber-800">{plan.blocked_reason}</p>}
        </>}
        {error && <p role="alert" className="break-words rounded-xl bg-rose-50 p-3 leading-5 text-rose-700">{error}</p>}
      </div>
      <div className="mt-4 flex shrink-0 justify-end gap-2 border-t border-black/[0.06] pt-4">
        {!loading && (!plan || !plan.can_delete) && <button type="button" disabled={deleting} onClick={() => setRevision(value => value + 1)} className="rounded-xl bg-slate-100 px-3 py-2 text-xs font-bold">重新读取</button>}
        <button type="button" data-cancel disabled={deleting} onClick={onClose} className="rounded-xl bg-slate-100 px-4 py-2 text-xs font-bold text-[#1A1D2E]">取消</button>
        <button type="button" disabled={loading || deleting || !plan?.can_delete} onClick={() => void confirm()} className="flex items-center gap-1.5 rounded-xl bg-rose-600 px-4 py-2 text-xs font-bold text-white hover:bg-rose-700 disabled:opacity-40"><Trash2 className="h-3.5 w-3.5" />{deleting ? '正在删除…' : '确认删除原文件及成片'}</button>
      </div>
    </div>
  </div>;
}
