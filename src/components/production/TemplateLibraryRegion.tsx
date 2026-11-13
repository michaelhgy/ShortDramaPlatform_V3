import React, { useEffect, useMemo, useRef, useState } from 'react';
import { AlertCircle, Check, CheckCircle2, Film, FolderOpen, LoaderCircle, Play, RefreshCw, Trash2, X } from 'lucide-react';
import {
  loadPublicTemplates, openPublicTemplateFolder, refreshPublicTemplates, selectPublicTemplate, deletePublicTemplate,
  type PublicTemplate, type TemplateCatalogue,
} from '../../services/templateLibraryService';
import { formatElapsedSeconds } from '../../utils/duration';

interface Props {
  onMakeTemplate?: () => void;
  taskId: string;
  accountName: string;
  dramaName: string;
  materialCount: number;
  showToast: (message: string) => void;
}

const buttonStyle = 'inline-flex items-center justify-center gap-1.5 whitespace-nowrap rounded-xl border py-1.5 text-xs font-bold transition-colors disabled:cursor-not-allowed disabled:opacity-40';

export const TemplateLibraryRegion: React.FC<Props> = ({ taskId, accountName, dramaName, materialCount, showToast, onMakeTemplate }) => {
  const [catalogue, setCatalogue] = useState<TemplateCatalogue | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [filter, setFilter] = useState<'all' | 'available'>('all');
  const [sort, setSort] = useState<'name' | 'usage'>('name');
  const [saving, setSaving] = useState(false);
  const [previewId, setPreviewId] = useState<string | null>(null);
  const [mediaError, setMediaError] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const mounted = useRef(true);
  const requestId = useRef(0);
  const dialogRef = useRef<HTMLDivElement>(null);
  const closeRef = useRef<HTMLButtonElement>(null);
  const previousFocus = useRef<HTMLElement | null>(null);

  const load = async (scan = false) => {
    const request = ++requestId.current;
    setLoading(true);
    setError('');
    try {
      const result = await (scan ? refreshPublicTemplates(taskId) : loadPublicTemplates(taskId));
      if (!mounted.current || request !== requestId.current) return;
      setCatalogue(result);
    } catch (reason) {
      if (mounted.current && request === requestId.current) {
        setError(reason instanceof Error ? reason.message : '模板读取失败，请重试。');
      }
    } finally {
      if (mounted.current && request === requestId.current) setLoading(false);
    }
  };

  useEffect(() => {
    mounted.current = true;
    void load();
    let active = true;
    const timer = window.setInterval(() => {
      const request = requestId.current;
      void loadPublicTemplates(taskId).then(result => { if (active && mounted.current && request === requestId.current) setCatalogue(result); }).catch(() => undefined);
    }, 5000);
    return () => { active = false; window.clearInterval(timer); mounted.current = false; requestId.current += 1; };
  }, [taskId]);

  const preview = catalogue?.items.find(item => item.id === previewId);
  const previewIsSelected = Boolean(preview && preview.id === catalogue?.selected_template_id);
  const availableCount = catalogue?.items.filter(item => item.available).length ?? 0;
  const visibleItems = useMemo(() => (catalogue?.items ?? [])
    .filter(item => filter === 'all' || item.available || item.id === catalogue?.selected_template_id)
    .slice().sort((a, b) => sort === 'usage' ? a.usage_count - b.usage_count || a.name.localeCompare(b.name, 'zh-CN') : a.name.localeCompare(b.name, 'zh-CN')), [catalogue, filter, sort]);

  const closePreview = () => {
    setPreviewId(null);
    previousFocus.current?.focus();
  };

  useEffect(() => {
    if (!preview) return;
    closeRef.current?.focus();
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') { event.preventDefault(); closePreview(); }
      if (event.key === 'Tab') {
        const elements = [...(dialogRef.current?.querySelectorAll<HTMLElement>('button:not(:disabled),a[href],video[controls]') ?? [])];
        const first = elements[0];
        const last = elements[elements.length - 1];
        if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last?.focus(); }
        else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first?.focus(); }
      }
    };
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, [preview?.id]);

  const choose = async (id: string | null) => {
    if (saving || catalogue?.selection_locked) return;
    setSaving(true);
    requestId.current += 1;
    try {
      const next = await selectPublicTemplate(taskId, id);
      if (!mounted.current) return;
      setCatalogue(next);
      setError('');
      setPreviewId(null);
      showToast(id ? `本任务已选用：${next.items.find(item => item.id === id)?.name || '模板'}` : '已取消本任务的模板选择。');
    } catch (reason) {
      if (mounted.current) {
        showToast(reason instanceof Error ? reason.message : '模板选用失败，请重试。');
        void load();
      }
    } finally {
      if (mounted.current) setSaving(false);
    }
  };

  const openFolder = async () => {
    try { await openPublicTemplateFolder(); }
    catch (reason) { showToast(reason instanceof Error ? reason.message : '打开模板目录失败。'); }
  };

  const showPreview = (item: PublicTemplate) => {
    previousFocus.current = document.activeElement as HTMLElement;
    setMediaError(false);
    setConfirmDelete(false);
    setPreviewId(item.id);
  };

  const remove = async () => {
    if (!preview || saving) return;
    const id = preview.id;
    const video = dialogRef.current?.querySelector('video');
    video?.pause(); video?.removeAttribute('src'); video?.load();
    setSaving(true); requestId.current += 1;
    try {
      const next = await deletePublicTemplate(taskId, id);
      if (mounted.current) { setCatalogue(next); closePreview(); showToast('模板已删除，已生成成片保留。'); }
    } catch (reason) { showToast(reason instanceof Error ? reason.message : '删除失败，请重试'); }
    finally { if (mounted.current) { setSaving(false); setConfirmDelete(false); } }
  };

  return (
    <section className="grid min-w-0 grid-rows-[auto_auto] gap-2.5 rounded-2xl border border-black/[0.06] bg-[#F8FAFC] p-3.5 xl:row-span-2 xl:grid-rows-subgrid" aria-label="公共模板区域" data-testid="template-library">
      <div className="flex flex-wrap items-center gap-2.5" data-testid="template-toolbar">
        <div className="flex shrink-0 items-center gap-2">
          <span className="flex h-5 w-5 items-center justify-center rounded-full bg-[#1A1D2E] text-[11px] font-black text-[#DDFD00]">2</span>
          <h4 className="text-sm font-black text-[#1A1D2E]">模板区域</h4>
          {catalogue && !error && <span className="whitespace-nowrap text-[11px] text-[#64748B]">可用 {availableCount} / 共 {catalogue.items.length} 个</span>}
        </div>
        <div className="flex min-w-[230px] flex-1 flex-wrap items-center justify-between gap-2" data-testid="template-filters">
          <div className="flex shrink-0 gap-0.5 rounded-xl border border-black/[0.03] bg-black/[0.04] p-1" aria-label="模板显示范围">
            {(['all', 'available'] as const).map(value => <button key={value} type="button" aria-pressed={filter === value} onClick={() => setFilter(value)} className={`whitespace-nowrap rounded-lg px-3 py-1 text-[11px] font-bold ${filter === value ? 'bg-white text-[#1A1D2E] shadow-xs' : 'text-[#64748B] hover:text-[#1A1D2E]'}`}>{value === 'all' ? '全部模板' : '当前可用'}</button>)}
          </div>
          <select aria-label="模板排序" value={sort} onChange={event => setSort(event.target.value as 'name' | 'usage')} className="rounded-xl border border-black/[0.08] bg-white px-2.5 py-1.5 text-[11px] text-[#64748B]"><option value="name">按模板名称</option><option value="usage">使用少的优先</option></select>
        </div>
        <div className="ml-auto flex shrink-0 items-center gap-1.5">
          <button type="button" onClick={onMakeTemplate} className={`${buttonStyle} border-[#1A1D2E] bg-[#1A1D2E] px-2.5 text-[#DDFD00]`}>制作模板</button>
          <button type="button" onClick={() => void openFolder()} className={`${buttonStyle} border-black/[0.08] bg-white px-2.5 text-[#64748B] hover:bg-slate-50`}><FolderOpen className="h-3.5 w-3.5" />模板目录</button>
          <button type="button" onClick={() => void load(true)} disabled={loading || saving} className={`${buttonStyle} border-black/[0.08] bg-white px-2.5 text-[#1A1D2E] hover:bg-slate-50`}><RefreshCw className={`h-3.5 w-3.5 ${loading ? 'animate-spin' : ''}`} />刷新模板</button>
        </div>
      </div>

      <div className="min-w-0 space-y-2.5">
        {error && <div role="alert" className="flex items-center justify-between gap-3 rounded-xl border border-rose-200 bg-rose-50 p-3 text-xs text-rose-800"><span className="flex items-center gap-2"><AlertCircle className="h-4 w-4 shrink-0" />{error}</span><button type="button" onClick={() => void load()} className="shrink-0 font-bold underline">重试</button></div>}
        {catalogue?.warnings?.length ? <div role="status" className="rounded-xl border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-800">{catalogue.warnings.join('；')}</div> : null}

        {loading && !catalogue ? <div className="flex min-h-40 items-center justify-center gap-2 text-xs text-[#64748B]"><LoaderCircle className="h-4 w-4 animate-spin" />正在读取模板…</div> : !error && !catalogue?.items.length ? (
          <div className="flex min-h-44 flex-col items-center justify-center gap-2 rounded-xl border border-dashed border-slate-200 bg-white p-5 text-center">
            <Film className="h-7 w-7 text-slate-300" /><strong className="text-sm font-bold text-[#1A1D2E]">暂无可显示的模板</strong><p className="text-xs leading-5 text-[#64748B]">点击“制作模板”补充；已删除或达到使用上限的模板不再显示。</p><button type="button" onClick={() => void openFolder()} className={`${buttonStyle} mt-1 border-black/[0.08] bg-white px-2.5 text-[#1A1D2E] hover:bg-slate-50`}><FolderOpen className="h-3.5 w-3.5" />打开模板目录</button>
          </div>
        ) : !error && (
          <div className="overflow-x-auto pb-1.5 pt-1" aria-label="模板卡片列表">
            <div className="flex w-max items-stretch gap-3">
              {visibleItems.map(item => {
                const isSelected = item.id === catalogue?.selected_template_id;
                const canChangeSelection = (isSelected || item.available) && !catalogue?.selection_locked && !saving && !loading;
                return <article key={item.id} data-template-id={item.id} className={`flex w-32 shrink-0 flex-col gap-1.5 rounded-xl border bg-white p-2 transition-colors ${isSelected ? 'border-[#1A1D2E] ring-2 ring-[#DDFD00]/35' : 'border-black/[0.06] hover:border-black/15'}`}>
                  <button type="button" onClick={() => showPreview(item)} disabled={!item.preview_url} aria-label={`预览 ${item.name}`} title="点击画面预览" className="group relative aspect-[9/20] w-full shrink-0 overflow-hidden rounded-lg bg-slate-900 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#1A1D2E] disabled:cursor-not-allowed">
                    {item.thumbnail_url ? <img src={item.thumbnail_url} alt="" loading="lazy" className="h-full w-full object-contain" /> : <span className="absolute inset-0 flex items-center justify-center"><Film className="h-6 w-6 text-slate-500" /></span>}
                    {item.preview_url && <span className="absolute inset-0 flex items-center justify-center bg-black/25 opacity-0 transition-opacity group-hover:opacity-100 group-focus-visible:opacity-100"><span className="flex h-8 w-8 items-center justify-center rounded-full bg-white/90 text-[#1A1D2E] shadow-sm"><Play className="ml-0.5 h-3.5 w-3.5" /></span></span>}
                    {isSelected && <span className="absolute left-1.5 top-1.5 flex items-center gap-1 rounded-md bg-[#DDFD00] px-1.5 py-0.5 text-[11px] font-black text-[#1A1D2E]"><Check className="h-3 w-3" />已选用</span>}
                    <span className="absolute bottom-1.5 right-1.5 rounded bg-black/75 px-1 py-0.5 font-mono text-[11px] text-white">{formatElapsedSeconds(item.duration_seconds, '—')}</span>
                  </button>
                  <h5 title={item.file_name || item.name} className="flex min-w-0 items-center gap-1 text-[11px] font-black leading-5 text-[#1A1D2E]"><span data-testid="template-usage-count" title={`已用于 ${item.usage_count} / ${item.usage_limit} 部剧`} aria-label={`已用于 ${item.usage_count} 部剧`} className="flex h-5 min-w-5 shrink-0 items-center justify-center rounded-full bg-[#1A1D2E] px-1 text-[10px] font-black text-[#DDFD00]">{item.usage_count}</span><span className="min-w-0 truncate" data-testid="template-name">{item.name}</span></h5>
                  <div className="mt-auto grid">
                    <button type="button" onClick={() => void choose(isSelected ? null : item.id)} disabled={!canChangeSelection} aria-pressed={isSelected} title={catalogue?.selection_locked ? catalogue.selection_lock_reason : isSelected ? '再次点击取消选用' : item.unavailable_reason || '选用此模板'} className={`${buttonStyle} px-1.5 ${isSelected && canChangeSelection ? 'border-lime-200 bg-lime-50 text-lime-900 hover:bg-lime-100' : 'border-[#1A1D2E] bg-[#1A1D2E] text-[#DDFD00] enabled:hover:bg-black'}`}>{saving ? '保存中' : isSelected ? '已选用' : '选用'}</button>
                  </div>
                </article>;
              })}
            </div>
            {!visibleItems.length && <div className="py-10 text-center text-xs text-[#64748B]">当前任务没有可用模板，可切换“全部模板”查看原因。</div>}
          </div>
        )}
        {catalogue?.selection_locked && <p data-testid="template-selection-notice" className="text-[11px] leading-5 text-[#64748B]">{catalogue.selection_lock_reason}</p>}
      </div>

      {preview && <div className="fixed inset-0 z-50 flex items-center justify-center overflow-y-auto bg-black/65 p-4 backdrop-blur-xs" onClick={closePreview}>
        <div ref={dialogRef} role="dialog" aria-modal="true" aria-labelledby="public-template-preview-title" className="my-auto w-full max-w-2xl space-y-4 rounded-3xl border border-black/[0.08] bg-white p-5 shadow-2xl" onClick={event => event.stopPropagation()}>
          <header className="flex items-start justify-between gap-3 border-b border-black/[0.06] pb-3"><div className="min-w-0"><h3 id="public-template-preview-title" title={preview.file_name || preview.name} className="truncate text-base font-black text-[#1A1D2E]">{preview.name}</h3><p className="mt-1 text-xs text-[#64748B]">{formatElapsedSeconds(preview.duration_seconds, '—')} · {preview.resolution || '尺寸待识别'}</p></div><button ref={closeRef} type="button" onClick={closePreview} aria-label="关闭模板预览" className="shrink-0 rounded-lg p-1.5 text-slate-500 hover:bg-slate-100"><X className="h-4 w-4" /></button></header>
          <div className="grid gap-5 sm:grid-cols-[minmax(0,220px)_minmax(0,1fr)]">
            <div className="flex min-h-44 items-center justify-center overflow-hidden rounded-xl bg-slate-950">{mediaError ? <p role="alert" className="p-5 text-center text-xs text-slate-200">模板视频无法播放，请刷新模板后重试。</p> : <video key={preview.id} src={preview.preview_url || undefined} poster={preview.thumbnail_url || undefined} controls autoPlay muted playsInline preload="metadata" onError={() => setMediaError(true)} className="max-h-[55vh] w-full object-contain" />}</div>
            <div className="flex min-w-0 flex-col gap-4 py-1">
              <span className={`w-fit rounded-lg px-2 py-1 text-[11px] font-bold ${preview.available ? 'bg-lime-50 text-lime-900' : 'bg-amber-50 text-amber-800'}`}>{!preview.available ? preview.unavailable_reason : preview.id === catalogue?.selected_template_id ? '当前任务已选用' : '当前任务可选'}</span>
              <div className="flex items-baseline gap-1.5 text-xs text-[#64748B]">累计用于<strong className="font-mono text-3xl font-black text-[#1A1D2E]">{preview.usage_count}</strong>/ {preview.usage_limit} 部剧</div>
              <dl className="space-y-2 text-xs"><div className="flex justify-between gap-3"><dt className="text-[#64748B]">文件大小</dt><dd className="font-bold text-[#1A1D2E]">{(preview.size_bytes / 1024 / 1024).toFixed(1)} MB</dd></div><div className="flex justify-between gap-3"><dt className="text-[#64748B]">画面尺寸</dt><dd className="font-bold text-[#1A1D2E]">{preview.resolution || '—'}</dd></div></dl>
              <div className="space-y-1 rounded-xl border border-black/[0.06] bg-[#F8FAFC] p-3"><p className="text-[11px] text-[#64748B]">选用到当前任务</p><strong className="block break-all text-xs font-black text-[#1A1D2E]">{accountName} ×《{dramaName}》</strong><p className="text-[11px] text-[#64748B]">本批 {materialCount} 条素材统一使用</p></div>
              <button type="button" onClick={() => void choose(previewIsSelected ? null : preview.id)} disabled={saving || loading || (!preview.available && !previewIsSelected) || catalogue?.selection_locked} aria-pressed={previewIsSelected} title={catalogue?.selection_locked ? catalogue.selection_lock_reason : previewIsSelected ? '再次点击取消选用' : preview.unavailable_reason || '选用此模板'} className={`${buttonStyle} min-h-10 border-[#1A1D2E] bg-[#1A1D2E] px-2.5 text-[#DDFD00] hover:bg-black`}>{saving ? <LoaderCircle className="h-4 w-4 animate-spin" /> : <CheckCircle2 className="h-4 w-4" />}{previewIsSelected ? '已选用' : '选用此模板'}</button>
              <p className="text-[11px] text-[#64748B]">同一部剧首次成功生成成片计1次，补做不重复计次；删除剧集仍保留次数。</p>
              {confirmDelete ? <div className="rounded-xl bg-rose-50 p-3 space-y-3"><p className="text-xs text-rose-800">删除后将退出模板库，视频移入本地回收目录。已生成成片和历史计次保留。</p><div className="flex gap-2"><button type="button" disabled={saving} onClick={() => void remove()} className={`${buttonStyle} bg-rose-600 px-3 text-white`}>确认删除模板</button><button type="button" disabled={saving} onClick={() => setConfirmDelete(false)} className={`${buttonStyle} bg-white px-3`}>取消删除</button></div></div> : <button type="button" disabled={saving || !preview.can_delete} title={preview.can_delete ? '人工删除这个模板' : '排队或合成中的任务仍在使用此模板'} onClick={() => setConfirmDelete(true)} className={`${buttonStyle} border-rose-200 bg-white px-3 text-rose-600`}><Trash2 className="h-3.5 w-3.5"/>删除模板</button>}
            </div>
          </div>
        </div>
      </div>}
    </section>
  );
};
