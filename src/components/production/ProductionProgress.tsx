import React from 'react';
import type { ProductionUnit } from '../../productionTypes';
import type { FinalJob } from '../../api/finalComposition';
import { jobStatusText, productionProgress } from '../taskcenter/ffmpegTaskModel';

export function ProductionProgress({ unit, jobs, compact = false }: { unit: ProductionUnit; jobs?: FinalJob[]; compact?: boolean }) {
  const p = productionProgress(unit, jobs);
  const states = [p.running && `合成中 ${p.running}`, p.waiting && `排队 ${p.waiting}`, p.pending && `待合成 ${p.pending}`, p.cancelled && `已取消 ${p.cancelled}`].filter(Boolean);
  return <div data-testid="production-progress" className={`space-y-2 ${compact ? 'text-[11px]' : 'rounded-xl border border-slate-100 bg-white p-3 text-xs'}`}>
    <div className="flex items-center justify-between gap-2">
      <span className="font-bold text-slate-600">已生成 <strong className="text-emerald-700 tabular-nums">{p.done}</strong><span className="font-normal text-slate-400"> / {p.total} 条</span></span>
      <span className="font-bold tabular-nums text-emerald-700">{p.total ? `${p.percent}%` : '暂无素材'}</span>
    </div>
    <div role="progressbar" aria-label="成片完成数量" aria-valuemin={0} aria-valuemax={p.total || 1} aria-valuenow={p.done}
      title="按已完成条数计算；排队和正在合成的成片尚未计入完成数量。" className="h-1.5 rounded-full bg-slate-200 overflow-hidden">
      <div className="h-full bg-emerald-500 transition-[width] duration-300 rounded-full" style={{ width: `${p.percent}%` }} />
    </div>
    <div className="flex items-center flex-wrap gap-x-3 gap-y-1 text-slate-500">
      {states.length ? <span>{states.join(' · ')}</span> : <span>{p.total && p.done === p.total ? '全部成片已生成' : p.errors ? '等待处理失败任务' : '扫描素材后开始合成'}</span>}
      {p.errors > 0 && <span className="font-bold text-rose-600">失败 {p.errors}</span>}
    </div>
    {p.current && <p title={p.current.name} className="truncate text-indigo-700"><strong>{jobStatusText('running', p.current.progress, 'final')}</strong><span className="ml-2 text-slate-500">{p.current.name}</span></p>}
  </div>;
}
