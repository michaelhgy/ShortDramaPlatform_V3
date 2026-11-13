import React, { useEffect, useId, useMemo, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { Download, X } from 'lucide-react';
import { loadCompositionDiagnosticsCatalog, type CompositionDiagnosticsCatalog, type CompositionDiagnosticsOptions } from '../../api/finalComposition';

const control = 'rounded-lg border border-slate-200 bg-white px-3 py-2 text-xs text-slate-700 disabled:opacity-40';
const statusText: Record<string, string> = { running: '运行中', done: '已完成', error: '失败', cancelled: '已取消' };
const dateText = (value: string) => { const date = new Date(value); return Number.isNaN(date.getTime()) ? value : date.toLocaleString('zh-CN', { hour12: false }); };

export function CompositionDiagnosticsModal({ busy, onClose, onConfirm }: {
  busy: boolean; onClose: () => void; onConfirm: (options: CompositionDiagnosticsOptions) => Promise<void>;
}) {
  const [catalog, setCatalog] = useState<CompositionDiagnosticsCatalog | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState('');
  const [error, setError] = useState('');
  const [reload, setReload] = useState(0);
  const [scope, setScope] = useState<CompositionDiagnosticsOptions['scope']>('recent');
  const [limit, setLimit] = useState('30');
  const [baseline, setBaseline] = useState(true);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [query, setQuery] = useState('');
  const [page, setPage] = useState(0);
  const dialog = useRef<HTMLDivElement>(null);
  const cancel = useRef<HTMLButtonElement>(null);
  const titleId = useId();
  useEffect(() => {
    const previous = document.activeElement as HTMLElement | null;
    cancel.current?.focus();
    return () => previous?.focus();
  }, []);
  useEffect(() => {
    const handleEscape = (event: KeyboardEvent) => {
      if (event.key !== 'Escape') return;
      event.preventDefault(); event.stopPropagation();
      if (!busy) onClose();
    };
    document.addEventListener('keydown', handleEscape, true);
    return () => document.removeEventListener('keydown', handleEscape, true);
  }, [busy, onClose]);
  useEffect(() => { if (busy) dialog.current?.focus(); }, [busy]);
  useEffect(() => {
    let active = true;
    setLoading(true); setLoadError('');
    loadCompositionDiagnosticsCatalog().then(value => { if (active) setCatalog(value); })
      .catch(reason => { if (active) setLoadError(reason instanceof Error ? reason.message : String(reason)); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [reload]);
  const matches = useMemo(() => (catalog?.items || []).filter(item => item.name.toLowerCase().includes(query.trim().toLowerCase())), [catalog, query]);
  const pages = Math.max(1, Math.ceil(matches.length / 20));
  const currentPage = Math.min(page, pages - 1);
  const visible = matches.slice(currentPage * 20, (currentPage + 1) * 20);
  const count = Number(limit);
  const validCount = Number.isInteger(count) && count >= 1 && count <= 200;
  const invalid = loading || !!loadError || !catalog || (scope === 'recent' && !validCount) || (scope === 'selected' && (!selected.size || selected.size > 200));
  const confirm = async () => {
    if (busy || invalid || !catalog) return;
    setError('');
    try {
      await onConfirm({ scope, limit: scope === 'recent' ? count : 30, include_baseline: scope !== 'all' && baseline,
        ...(scope === 'selected' ? { attempt_keys: [...selected] } : {}),
        ...(scope === 'recent' ? { session_id: catalog.latest_session_id } : {}),
      });
    } catch (reason) { setError(reason instanceof Error ? reason.message : String(reason)); }
  };
  const toggle = (key: string) => setSelected(current => { const next = new Set(current); if (next.has(key)) next.delete(key); else next.add(key); return next; });
  return createPortal(<div className="fixed inset-0 z-[70] flex items-center justify-center bg-black/40 p-4 backdrop-blur-xs"
    onClick={event => { if (event.target === event.currentTarget && !busy) onClose(); }}>
    <div ref={dialog} role="dialog" aria-modal="true" aria-labelledby={titleId} tabIndex={-1}
      className="flex max-h-[90vh] w-full max-w-2xl flex-col overflow-hidden rounded-3xl border border-slate-200 bg-white shadow-2xl"
      onKeyDown={event => {
        if (event.key === 'Escape') { event.stopPropagation(); if (!busy) onClose(); }
        if (event.key === 'Tab') {
          const elements = Array.from<HTMLElement>(dialog.current?.querySelectorAll<HTMLElement>('button:not(:disabled), input:not(:disabled), select:not(:disabled)') || []);
          const first = elements[0], last = elements[elements.length - 1];
          if (!first) { event.preventDefault(); return; }
          if (event.shiftKey && (document.activeElement === first || document.activeElement === dialog.current)) { event.preventDefault(); last.focus(); }
          else if (!event.shiftKey && (document.activeElement === last || document.activeElement === dialog.current)) { event.preventDefault(); first.focus(); }
        }
      }}>
      <header className="flex shrink-0 items-center justify-between gap-3 border-b border-slate-100 px-5 py-4">
        <div><h3 id={titleId} className="text-base font-black text-slate-900">导出合成诊断</h3><p className="mt-1 text-xs text-slate-500">先选择范围，再生成分析报告和日志压缩包。</p></div>
        <button type="button" aria-label="关闭诊断导出设置" disabled={busy} onClick={onClose} className="rounded-lg p-2 text-slate-500 disabled:opacity-40"><X className="h-4 w-4" /></button>
      </header>
      <div className="min-h-0 space-y-4 overflow-y-auto p-5 text-sm text-slate-700">
        <fieldset disabled={busy} className="space-y-2">
          <legend className="mb-2 text-xs font-bold text-slate-900">导出范围</legend>
          {([['recent', '最近一轮运行（推荐）', '保留本轮简要统计，只附最近任务的详细日志。'],
             ['selected', '指定任务', '从已有诊断记录中选择要排查的任务。'],
             ['all', '全部历史', '包含当前仍保留的所有诊断记录，文件较多时导出会更久。']] as const).map(([value, label, help]) =>
            <label key={value} className={`flex cursor-pointer items-start gap-2 rounded-xl border p-3 ${scope === value ? 'border-indigo-300 bg-indigo-50/50' : 'border-slate-200'}`}>
              <input type="radio" name={titleId + '-scope'} value={value} checked={scope === value} onChange={() => { setScope(value); setError(''); }} className="mt-0.5" />
              <span><span className="block text-xs font-bold">{label}</span><span className="mt-1 block text-xs text-slate-500">{help}</span></span>
            </label>)}
        </fieldset>
        {loading && <p role="status" className="text-xs text-slate-500">正在读取诊断记录…</p>}
        {loadError && <div role="alert" className="rounded-xl bg-rose-50 p-3 text-xs text-rose-700">{loadError}<button type="button" className={`${control} ml-2`} onClick={() => setReload(value => value + 1)}>重新读取</button></div>}
        {catalog && !loading && !loadError && <>
          <p className="text-xs text-slate-500">共有 {catalog.total} 条记录；最近一轮 {catalog.latest_session_count} 条。每次重试单独计为一条记录。</p>
          {catalog.read_error_count > 0 && <p className="text-xs text-amber-700">有 {catalog.read_error_count} 项摘要无法完整读取，导出时会注明。</p>}
          {scope === 'recent' && <div className="space-y-2 rounded-xl bg-slate-50 p-3">
            <label className="flex items-center gap-2 text-xs font-bold">详细日志数量<input aria-label="详细日志数量" type="number" min={1} max={200} step={1} value={limit} disabled={busy} onChange={event => setLimit(event.target.value)} className={`${control} w-24`} /><span className="font-normal text-slate-500">条（1–200）</span></label>
            <p className="text-xs text-slate-500">默认最近30条，优先包含本轮运行中的任务；其余记录只保留简要统计。</p>
            {!validCount && <p role="alert" className="text-xs text-rose-700">请输入1至200的整数。</p>}
          </div>}
          {scope === 'selected' && <div className="space-y-2">
            <div className="flex flex-wrap items-center justify-between gap-2"><label className="min-w-0 flex-1"><span className="sr-only">搜索诊断任务</span><input type="search" value={query} disabled={busy} onChange={event => { setQuery(event.target.value); setPage(0); }} placeholder="按视频名称搜索" className={`${control} w-full`} /></label><span className="text-xs">已选 {selected.size} 条 / 最多200条</span><button type="button" disabled={busy || !selected.size} className={control} onClick={() => setSelected(new Set())}>清空选择</button></div>
            <div className="max-h-52 overflow-y-auto rounded-xl border border-slate-200">
              {visible.map(item => <label key={item.key} className="flex cursor-pointer items-start gap-2 border-b border-slate-100 px-3 py-2 last:border-0">
                <input type="checkbox" aria-label={`选择${item.name}，尝试${item.attempt}，${item.started_at}`} checked={selected.has(item.key)} disabled={busy || (!selected.has(item.key) && selected.size >= 200)} onChange={() => toggle(item.key)} className="mt-0.5" />
                <span className="min-w-0"><span className="block break-all text-xs font-bold">{item.name}</span><span className="mt-0.5 block text-[11px] text-slate-500">{dateText(item.started_at)} · 尝试{item.attempt} · {statusText[item.status] || '状态未明'}</span></span>
              </label>)}
              {!visible.length && <p className="p-3 text-xs text-slate-500">没有匹配的诊断记录。</p>}
            </div>
            <div className="flex items-center justify-between text-xs text-slate-500"><span>第 {currentPage + 1} / {pages} 页 · 共 {matches.length} 条</span><div className="flex gap-2"><button type="button" className={control} disabled={busy || currentPage === 0} onClick={() => setPage(currentPage - 1)}>上一页</button><button type="button" className={control} disabled={busy || currentPage + 1 >= pages} onClick={() => setPage(currentPage + 1)}>下一页</button></div></div>
          </div>}
          {scope !== 'all' && <label className="flex cursor-pointer items-start gap-2 rounded-xl border border-slate-200 p-3"><input type="checkbox" checked={baseline} disabled={busy} onChange={event => setBaseline(event.target.checked)} className="mt-0.5" /><span><span className="block text-xs font-bold">保留前段同条件正常样本作对照</span><span className="mt-1 block text-xs text-slate-500">每组最多3条，合计最多额外12条；用于比较前后速度，没有匹配样本时不补其他任务。</span></span></label>}
          {scope === 'all' && <p className="rounded-xl bg-amber-50 p-3 text-xs text-amber-800">将导出全部 {catalog.total} 条记录及仍保留的详细日志，可能生成较大的压缩包。</p>}
        </>}
        <p className="text-xs leading-relaxed text-slate-500">只导出诊断信息，不包含视频、素材或数据库；不会暂停合成。每个原始日志文件最多保留最近8MB，报告会注明选取范围和缺失记录。</p>
        {error && <p role="alert" className="break-all rounded-xl bg-rose-50 p-3 text-xs text-rose-700">{error}</p>}
      </div>
      <footer className="flex shrink-0 justify-end gap-2 border-t border-slate-100 px-5 py-4">
        <button ref={cancel} type="button" disabled={busy} onClick={onClose} className={control}>取消</button>
        <button type="button" disabled={busy || invalid} onClick={() => void confirm()} className="inline-flex items-center gap-1.5 rounded-lg bg-slate-900 px-4 py-2 text-xs font-bold text-white disabled:opacity-40"><Download className="h-3.5 w-3.5" />{busy ? '导出中…' : '开始导出'}</button>
      </footer>
    </div>
  </div>, document.body);
}
