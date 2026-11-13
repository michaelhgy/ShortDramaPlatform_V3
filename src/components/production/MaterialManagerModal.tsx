import React, { useEffect, useRef, useState } from 'react';
import { ExternalLink, Film, FolderOpen, Search, Trash2, Volume2, VolumeX, X } from 'lucide-react';
import type { ProductionUnit, ScannedMaterialClip } from '../../productionTypes';
import { openV2File, openV2Folder } from '../../api/v2Catalog';
import { updateV2MaterialInsertionStrategy, type V2ProductionTaskListItem } from '../../api/v2Production';
import { InsertionSettingsModal, materialInsertionSummary } from './InsertionSettingsModal';
import { MaterialDeleteDialog } from './MaterialDeleteDialog';

export function MaterialManagerModal({ task, initialMaterialId, onClose, onTaskChanged, showToast }: {
  key?: string; task: ProductionUnit; initialMaterialId?: string; onClose: () => void;
  onTaskChanged: (task: V2ProductionTaskListItem) => void | Promise<void>; showToast: (message: string) => void;
}) {
  const [selectedId, setSelectedId] = useState(initialMaterialId || task.scannedMaterials[0]?.id || '');
  const [search, setSearch] = useState('');
  const [dirty, setDirty] = useState(false);
  const [saving, setSaving] = useState(false);
  const [editorEpoch, setEditorEpoch] = useState(0);
  const [pendingAction, setPendingAction] = useState<(() => void) | null>(null);
  const [deleteClip, setDeleteClip] = useState<ScannedMaterialClip | null>(null);
  const [muted, setMuted] = useState(() => localStorage.getItem('v2-material-preview-muted') !== 'false');
  const [mediaError, setMediaError] = useState('');
  const [actionContainer, setActionContainer] = useState<HTMLDivElement | null>(null);
  const player = useRef<HTMLVideoElement>(null);
  const dialog = useRef<HTMLDivElement>(null);
  const clips = task.scannedMaterials || [];
  const selected = clips.find(clip => clip.id === selectedId);
  const visible = clips.filter(clip => clip.title.toLowerCase().includes(search.trim().toLowerCase()));
  useEffect(() => {
    if (!clips.some(clip => clip.id === selectedId)) { setSelectedId(clips[0]?.id || ''); setDirty(false); }
  }, [clips, selectedId]);
  useEffect(() => { setMediaError(''); }, [selectedId]);
  useEffect(() => {
    const previous = document.activeElement as HTMLElement | null;
    dialog.current?.focus();
    const overflow = document.body.style.overflow; document.body.style.overflow = 'hidden';
    return () => { document.body.style.overflow = overflow; if (previous?.isConnected) previous.focus(); };
  }, []);
  const requestAction = (action: () => void) => {
    if (saving || deleteClip) return;
    if (dirty) setPendingAction(() => action);
    else action();
  };
  const openPath = (file = false) => {
    const path = file ? selected?.filePath : task.materialFolder;
    if (!path) { showToast('当前素材没有可打开的文件路径'); return; }
    (file ? openV2File(path) : openV2Folder(path)).catch(reason => showToast(reason instanceof Error ? reason.message : '打开文件失败'));
  };
  const releasePlayer = () => { if (player.current) { player.current.pause(); player.current.removeAttribute('src'); player.current.load(); } };
  return <div className="fixed inset-0 z-[70] flex items-center justify-center bg-black/45 p-3 backdrop-blur-xs" onClick={() => { if (!pendingAction) requestAction(onClose); }} onKeyDown={event => {
    if (deleteClip) return;
    if (event.key === 'Escape') { event.preventDefault(); event.stopPropagation(); if (pendingAction) setPendingAction(null); else requestAction(onClose); }
    if (event.key === 'Tab') {
      const focusRoot = dialog.current?.querySelector('[role="alertdialog"]') || dialog.current;
      const elements = focusRoot?.querySelectorAll<HTMLElement>('button:not(:disabled),input:not(:disabled),select:not(:disabled),video[controls]');
      const visibleElements = (Array.from(elements || []) as HTMLElement[]).filter(element => element.getClientRects().length);
      const first = visibleElements[0], last = visibleElements[visibleElements.length - 1];
      if (!first) return;
      if (event.shiftKey && (document.activeElement === first || document.activeElement === dialog.current)) { event.preventDefault(); last.focus(); }
      else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
    }
  }}>
    <div ref={dialog} tabIndex={-1} role="dialog" aria-modal="true" aria-label="素材管理" className="relative flex h-[90vh] max-h-[980px] w-[min(1440px,97vw)] min-w-0 flex-col overflow-hidden rounded-3xl border border-black/[0.08] bg-white text-[#1A1D2E] shadow-2xl outline-none" onClick={event => event.stopPropagation()}>
      <div className="flex shrink-0 items-center justify-between gap-3 border-b border-black/[0.06] px-5 py-4">
        <div className="min-w-0"><h2 className="flex items-center gap-2 text-base font-black"><Film className="h-5 w-5" />素材管理 <span className="rounded-md bg-[#1A1D2E] px-1.5 text-xs leading-5 text-[#DDFD00]">{clips.length}</span></h2><p className="mt-1 truncate text-xs text-slate-500" title={`${task.accountName} × ${task.dramaName}`}>{task.accountName} × 《{task.dramaName}》</p></div>
        <div className="flex shrink-0 items-center gap-2"><button type="button" onClick={() => openPath()} className="flex items-center gap-1.5 rounded-xl border border-black/[0.08] px-3 py-2 text-xs font-bold hover:bg-slate-50"><FolderOpen className="h-3.5 w-3.5" />素材目录</button><button type="button" disabled={saving} onClick={() => requestAction(onClose)} aria-label="关闭素材管理" className="rounded-xl p-2 hover:bg-slate-100 disabled:opacity-40"><X className="h-5 w-5" /></button></div>
      </div>
      <div className="grid min-h-0 flex-1 grid-cols-1 overflow-y-auto md:grid-cols-[168px_minmax(0,1fr)_300px] md:overflow-hidden xl:grid-cols-[220px_minmax(0,1fr)_340px]">
        <aside className="flex min-h-0 flex-col border-r border-black/[0.06] bg-slate-50/80 md:overflow-hidden">
          <div className="relative m-3 shrink-0"><Search className="pointer-events-none absolute left-2.5 top-2.5 h-3.5 w-3.5 text-slate-400" /><input aria-label="搜索素材" value={search} onChange={event => setSearch(event.target.value)} placeholder="搜索素材名称" className="w-full rounded-xl border border-black/[0.08] bg-white py-2 pl-8 pr-2 text-xs outline-none focus:border-slate-400" /></div>
          <div className="max-h-60 min-h-0 space-y-1 overflow-y-auto px-2 pb-3 md:max-h-none" aria-label="素材列表">{visible.map(clip => <button type="button" key={clip.id} aria-label={`选择素材 ${clip.title}`} aria-pressed={clip.id === selectedId} disabled={saving} onClick={() => { if (clip.id !== selectedId) requestAction(() => { setSelectedId(clip.id); setDirty(false); }); }} className={`flex w-full items-center gap-2 rounded-xl border p-2 text-left transition-colors ${clip.id === selectedId ? 'border-[#1A1D2E]/15 bg-white shadow-xs' : 'border-transparent hover:bg-white/80'} disabled:opacity-50`}>
            <div className="relative h-16 w-10 shrink-0 overflow-hidden rounded-lg bg-slate-900">{(clip.thumbnailUrl || task.coverUrl) && <img src={clip.thumbnailUrl || task.coverUrl} alt="" className="h-full w-full object-cover" />}<span className="absolute bottom-0 right-0 rounded-tl bg-black/70 px-1 text-[9px] text-white">{clip.sequenceNumber}</span></div><div className="min-w-0"><p className="truncate text-xs font-extrabold" title={clip.title}>{clip.title}</p><p className="mt-1 text-[11px] text-slate-500">{clip.durationText}</p><p className="mt-1 truncate text-[10px] text-slate-400">{materialInsertionSummary(clip.insertionStrategy)}</p></div>
          </button>)}{!visible.length && <p className="px-3 py-6 text-center text-xs text-slate-400">{clips.length ? '没有匹配的素材' : '暂无素材'}</p>}</div>
        </aside>
        <main className="flex min-h-[300px] min-w-0 flex-col bg-[#F8FAFC] p-3 md:min-h-0 xl:p-5">
          {selected ? <><div className="mb-3 flex shrink-0 items-center justify-between gap-2"><p className="min-w-0 truncate text-xs font-bold text-slate-600" title={selected.title}>{selected.title}</p><span className="shrink-0 text-[11px] text-slate-400">{clips.findIndex(clip => clip.id === selectedId) + 1} / {clips.length}</span></div><div className="relative flex min-h-[220px] flex-1 items-center justify-center overflow-hidden rounded-2xl bg-black md:min-h-0">
            {selected.videoUrl ? <video ref={player} key={selected.id} src={selected.videoUrl} poster={selected.thumbnailUrl || task.coverUrl} controls autoPlay muted={muted} playsInline preload="metadata" className="h-full max-h-[60vh] w-full object-contain md:max-h-none" onVolumeChange={event => { const value = event.currentTarget.muted; setMuted(value); localStorage.setItem('v2-material-preview-muted', String(value)); }} onError={() => setMediaError('视频暂时无法播放，请核对原文件是否存在，或使用外部播放器打开。')} /> : <p className="p-4 text-xs text-slate-300">暂无可播放的视频</p>}
          </div>{mediaError && <p role="alert" className="mt-2 text-xs text-rose-700">{mediaError}</p>}<div className="mt-3 flex shrink-0 flex-wrap items-center justify-end gap-2"><button type="button" onClick={() => setMuted(value => { const next = !value; localStorage.setItem('v2-material-preview-muted', String(next)); return next; })} className="flex items-center gap-1.5 rounded-xl bg-white px-3 py-2 text-xs font-bold hover:bg-slate-100">{muted ? <VolumeX className="h-3.5 w-3.5" /> : <Volume2 className="h-3.5 w-3.5" />}{muted ? '开启声音' : '静音'}</button><button type="button" onClick={() => openPath(true)} className="flex items-center gap-1.5 rounded-xl bg-white px-3 py-2 text-xs font-bold hover:bg-slate-100"><ExternalLink className="h-3.5 w-3.5" />打开播放器</button></div></> : <div className="flex h-full items-center justify-center text-sm text-slate-400">选择一条素材，查看预览和设置</div>}
        </main>
        <aside className="flex min-h-0 flex-col overflow-hidden border-l border-black/[0.06]">
          <div className="min-h-0 flex-1 overflow-y-auto p-4 xl:p-5">
          {selected && <><h3 className="mb-2 text-sm font-black">视频详情</h3>
          <p className="break-all text-xs font-bold leading-5">{selected.title}</p>
          <dl className="mb-3 mt-2 grid grid-cols-3 gap-2 text-xs">
            <div><dt className="text-slate-400">时长</dt><dd className="mt-1 font-semibold">{selected.durationText}</dd></div>
            <div><dt className="text-slate-400">大小</dt><dd className="mt-1 font-semibold">{selected.fileSizeText}</dd></div>
            <div><dt className="text-slate-400">分辨率</dt><dd className="mt-1 font-semibold">{selected.resolution || '暂无信息'}</dd></div>
          </dl>
          <details className="mb-3 text-xs"><summary className="cursor-pointer font-semibold text-slate-500">文件路径</summary><p className="mt-2 break-all leading-5 text-slate-500">{selected.filePath || task.materialFolder}</p></details>
          <div className="border-t border-black/[0.06] pt-4"><h3 className="mb-3 text-sm font-black">本素材插片设置{dirty && <span className="ml-2 text-[10px] font-medium text-amber-700">未保存</span>}</h3><InsertionSettingsModal key={`${selected.id}-${editorEpoch}`} embedded material actionContainer={actionContainer} readOnly={task.isCompleted || selected.status === 'deletion_failed'} readOnlyReason={selected.status === 'deletion_failed' ? '上次删除未完成，请先重试删除素材。' : undefined} title="本素材插片设置" subtitle={selected.title} initial={selected.insertionStrategy} taskOverride={task.insertionStrategy} onDirtyChange={setDirty} onBusyChange={setSaving} onClose={() => {}} onSave={async strategy => { await onTaskChanged(await updateV2MaterialInsertionStrategy(selected.id, strategy)); }} /></div>
          </>}
          </div>
          {selected && <div className="shrink-0 space-y-3 border-t border-black/[0.06] bg-white p-4">
            <div ref={setActionContainer} />
            <div className="flex items-center justify-between gap-2"><p className="text-[10px] leading-4 text-slate-400">删除将同时移除<br />原文件、成片和合成任务</p><button type="button" disabled={saving || task.isCompleted} onClick={() => requestAction(() => setDeleteClip(selected))} className="flex shrink-0 items-center gap-1.5 rounded-xl border border-rose-200 bg-rose-50 px-3 py-2 text-xs font-bold text-rose-700 hover:bg-rose-100 disabled:opacity-40"><Trash2 className="h-3.5 w-3.5" />删除素材</button></div>
          </div>}
        </aside>
      </div>
      <div className="flex shrink-0 items-center justify-between gap-3 border-t border-black/[0.06] px-5 py-3"><p className="text-[11px] text-slate-400">选择左侧素材，可连续预览和调整本片设置。</p><button type="button" disabled={saving} onClick={() => requestAction(onClose)} className="rounded-xl bg-[#1A1D2E] px-5 py-2 text-xs font-bold text-white disabled:opacity-40">关闭</button></div>
      {pendingAction && <div className="absolute inset-0 z-10 flex items-center justify-center bg-black/30 p-4"><div role="alertdialog" aria-modal="true" aria-label="未保存的素材设置" className="w-full max-w-sm rounded-2xl bg-white p-5 shadow-xl"><h3 className="text-sm font-black">本片设置尚未保存</h3><p className="mt-2 text-xs leading-6 text-slate-500">离开会放弃本次调整，你也可以返回后点击“保存本片设置”。</p><div className="mt-4 flex justify-end gap-2"><button autoFocus type="button" onClick={() => setPendingAction(null)} className="rounded-xl bg-slate-100 px-3 py-2 text-xs font-bold">继续编辑</button><button type="button" onClick={() => { const action = pendingAction; setPendingAction(null); setDirty(false); setEditorEpoch(value => value + 1); action(); }} className="rounded-xl bg-[#1A1D2E] px-3 py-2 text-xs font-bold text-[#DDFD00]">放弃修改并继续</button></div></div></div>}
    </div>
    {deleteClip && <MaterialDeleteDialog materialId={deleteClip.id} onClose={() => setDeleteClip(null)} onBeforeDelete={releasePlayer} onFailure={() => { if (player.current && selected?.videoUrl) { player.current.src = selected.videoUrl; player.current.load(); } }} onDeleted={async next => { await onTaskChanged(next); setDirty(false); showToast('已删除原素材、对应成片和合成任务'); }} />}
  </div>;
}
