import { sceneryAction, type ScenerySnapshot } from '../../api/scenery';
import React, { useState } from 'react';
import { Pause, Play, Film, Sparkles, Download } from 'lucide-react';
import { finalAction, exportCompositionDiagnostics, type CompositionDiagnosticsExport, type CompositionDiagnosticsOptions, type FinalSnapshot } from '../../api/finalComposition';
import { generationAction, type GenerationSnapshot } from '../../api/templateGeneration';
import { refreshArea } from '../../services/dataHub';
import { formatElapsedSeconds } from '../../utils/duration';
import { JobProgress } from './JobProgress';
import { CompositionDiagnosticsModal } from './CompositionDiagnosticsModal';
import { EncoderNotice } from './EncoderNotice';
import { jobStatusText, queueState, type JobStatus, type QueueKind } from './ffmpegTaskModel';

type Props = {
  kind: QueueKind;
  snapshot?: FinalSnapshot | GenerationSnapshot | ScenerySnapshot;
  compact?: boolean;
  showToast: (message: string) => void;
};
const button = 'rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-xs font-bold text-slate-700 disabled:opacity-40 disabled:cursor-not-allowed';
const tones: Record<JobStatus, string> = {
  running: 'bg-indigo-50 text-indigo-700', waiting: 'bg-slate-100 text-slate-600',
  done: 'bg-emerald-50 text-emerald-700', error: 'bg-rose-50 text-rose-700', cancelled: 'bg-slate-100 text-slate-400',
};
const order: Record<JobStatus, number> = { running: 0, waiting: 1, error: 2, done: 3, cancelled: 4 };

/** Both task-center surfaces use the same state and the same queue controls. */
export const FfmpegQueue: React.FC<Props> = ({ kind, snapshot, compact = false, showToast }) => {
  const [busy, setBusy] = useState(false);
  const [exporting, setExporting] = useState(false);
  const [exportOpen, setExportOpen] = useState(false);
  const [exportResult, setExportResult] = useState<CompositionDiagnosticsExport | null>(null);
  const exportDiagnostics = async (options: CompositionDiagnosticsOptions) => {
    if (exporting) return;
    setExporting(true);
    try {
      const result = await exportCompositionDiagnostics(options);
      setExportResult(result);
      showToast(result.opened ? '合成诊断已导出，已打开文件夹' : '合成诊断已导出，请按显示路径打开');
      setExportOpen(false);
    }
    finally { setExporting(false); }
  };
  const [filter, setFilter] = useState<'all' | 'active' | 'error' | 'done' | 'cancelled'>('all');
  const title = kind === 'final' ? '成片合成' : kind === 'scenery' ? '风景处理' : '模板制作';
  const action = async (path: string) => {
    setBusy(true);
    try {
      await (kind === 'final' ? finalAction(path) : kind === 'scenery' ? sceneryAction(path) : generationAction(path));
      await Promise.all([refreshArea('taskCenter'), refreshArea('production'), refreshArea('resourceIndex')]);
    } catch (error) { showToast(error instanceof Error ? error.message : String(error)); }
    finally { setBusy(false); }
  };
  if (!snapshot) return <section className="rounded-2xl bg-white p-4 text-sm text-slate-500">正在读取{title}…</section>;
  const { counts: c, paused } = snapshot;
  const jobs = snapshot.jobs.map(job => ({ ...job,
    title: 'name' in job ? job.name : job.display_name || `模板 · 第${job.ordinal}份`,
    context: 'account_name' in job ? job.account_name : 'seconds' in job ? `${job.seconds}秒 · ${job.family}` : job.stage,
    doneLabel: 'availability' in job && job.availability === 'exhausted' ? '使用次数已满' : kind === 'template' ? '已入库' : '已完成',
  })).sort((a, b) => order[a.status] - order[b.status]);
  const current = jobs.filter(j => j.status === 'running');
  const visible = compact ? current : jobs.filter(j => filter === 'all' || (filter === 'active' ? ['waiting', 'running'].includes(j.status) : j.status === filter));
  const filters = [ ['all', '全部', jobs.length], ['active', '进行中', c.running + c.waiting], ['error', '失败', c.error], ['done', '已完成', c.done], ['cancelled', '已取消', c.cancelled] ] as const;
  const Icon = kind === 'final' ? Film : Sparkles;
  return <section aria-label={`${title}队列`} className={`rounded-2xl border border-slate-200 bg-white ${compact ? 'p-4' : 'p-5'} space-y-3`}>
    <div className="flex flex-wrap items-center justify-between gap-3">
      <div className="flex flex-wrap items-center gap-2">
        <span className={`rounded-xl p-2 ${kind === 'final' ? 'bg-indigo-50 text-indigo-600' : 'bg-lime-50 text-lime-700'}`}><Icon className="h-4 w-4" /></span>
        <div><h3 className="font-black text-sm text-slate-900">{title}</h3><p className={`text-[11px] mt-0.5 ${paused ? 'text-amber-700' : 'text-slate-500'}`}>{queueState(snapshot)}</p></div>
      </div>
      <div className="ml-auto flex items-center gap-2">
        {kind === 'final' && !compact && <button type="button" className={`${button} inline-flex items-center gap-1.5`} disabled={exporting}
          title="导出中文分析报告和诊断日志ZIP，不包含视频、素材或数据库；不会暂停合成。" onClick={() => setExportOpen(true)}>
          <Download className="h-3.5 w-3.5" />{exporting ? '导出中…' : '导出合成诊断'}
        </button>}
      <button type="button" className={button} disabled={busy} title="仅控制本类任务；暂停后当前一条会继续完成。"
        onClick={() => void action(paused ? 'resume' : 'pause')}>
        {paused ? <Play className="inline h-3 w-3 mr-1" /> : <Pause className="inline h-3 w-3 mr-1" />}
        {busy ? '更新中…' : paused ? `继续${title}` : `暂停后续${kind === 'final' ? '成片' : kind === 'scenery' ? '风景处理' : '模板'}`}
      </button>
      </div>
    </div>
    {kind === 'final' && !compact && exportResult && <div role="status" className="rounded-lg bg-slate-50 px-3 py-2 text-xs text-slate-600">
      <p>已导出：简要统计 {exportResult.summary_attempts} 条，详细记录 {exportResult.attempts} 条（含正常对照 {exportResult.selection.baseline_attempts} 条），共 {exportResult.files} 份诊断文件。</p>
      <p>文件：合成诊断报告.md、合成诊断日志.zip</p>
      <p className="mt-1 break-all select-text">保存位置：{exportResult.directory}</p>
      {exportResult.warnings.map((warning, index) => <p key={index} className="mt-1 text-amber-700">{warning}</p>)}
    </div>}
    <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-slate-500">
      <span>执行 <strong className="text-indigo-700 tabular-nums">{c.running}</strong></span>
      <span>排队 <strong className="text-slate-800 tabular-nums">{c.waiting}</strong></span>
      <span>已完成 <strong className="text-emerald-700 tabular-nums">{c.done}</strong></span>
      {c.error > 0 && <span className="text-rose-600">失败 <strong>{c.error}</strong></span>}
    </div>
    {!compact && <div className="flex gap-1 flex-wrap border-t border-slate-100 pt-3" aria-label={`${title}记录筛选`}>
      {filters.map(([key, label, count]) => <button type="button" key={key} aria-pressed={filter === key} onClick={() => setFilter(key)}
        className={`rounded-lg px-2.5 py-1.5 text-xs font-bold ${filter === key ? 'bg-slate-900 text-white' : 'text-slate-500 hover:bg-slate-100'}`}>{label} <span className="tabular-nums ml-1">{count}</span></button>)}
    </div>}
    {visible.length === 0 ? <p className="rounded-xl bg-slate-50 px-3 py-4 text-xs text-slate-500">{compact
      ? paused ? `队列已暂停${c.waiting ? `，${c.waiting}项等待恢复` : '，暂无等待任务'}` : c.waiting ? '任务已排队，等待开始' : c.error ? '当前无运行任务，请到任务中心查看失败原因' : '当前没有执行中的任务'
      : jobs.length ? '没有符合条件的记录' : kind === 'final' ? '在生产中心选择模板后，点击“批量合成”。' : kind === 'scenery' ? '在资料中心选择原始风景，人工裁切后提交。' : '点击“生成模板”开始制作。'}</p>
      : <div className={compact ? 'space-y-2' : 'max-h-[420px] overflow-y-auto space-y-2 pr-1'}>{visible.map(job => <article key={job.id} className="rounded-xl bg-slate-50 p-3 space-y-2">
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0"><p title={job.title} className="truncate font-bold text-sm text-slate-800">{job.title}</p><p title={job.context} className="truncate text-xs text-slate-500 mt-1">{job.context}</p></div>
          <span className={`shrink-0 whitespace-nowrap rounded-md px-2 py-1 text-[11px] font-bold tabular-nums ${tones[job.status]}`}>{job.status === 'done' ? job.doneLabel : jobStatusText(job.status, job.progress, kind, paused)}</span>
        </div>
        {'encoding' in job && <EncoderNotice encoding={job.encoding} compact={compact} />}
        {job.status === 'running' && <><JobProgress value={job.progress} label={`${job.title}进度`} /><p title={job.stage} className="truncate text-[11px] text-slate-500">{job.stage || '正在准备'}</p></>}
        <div className="flex flex-wrap justify-between items-center gap-2 text-[11px] text-slate-500">
          <span>{job.status === 'waiting' ? ('auto_held' in job&&job.auto_held?'等待开启自动合成':'尚未开始') : `生成耗时 ${formatElapsedSeconds(job.elapsed_seconds, '—')}`}</span>
          {!compact && <div className="flex gap-2">
            {(job.status === 'error' || (kind === 'final' && job.status === 'cancelled')) && <button type="button" className={button} disabled={busy} onClick={() => void action(`jobs/${job.id}/retry`)}>重试{kind === 'final' ? '合成' : '制作'}</button>}
            {job.status === 'waiting' && <button type="button" className={button} disabled={busy} onClick={() => void action(`jobs/${job.id}/cancel`)}>取消排队</button>}
          </div>}
        </div>
        {job.status === 'error' && job.error && <p className="break-all text-xs text-rose-700">{job.error}</p>}
      </article>)}</div>}
    {kind === 'final' && !compact && exportOpen && <CompositionDiagnosticsModal busy={exporting} onClose={() => { if (!exporting) setExportOpen(false); }} onConfirm={exportDiagnostics} />}
  </section>;
}
