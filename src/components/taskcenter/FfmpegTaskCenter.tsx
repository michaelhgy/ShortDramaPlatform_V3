import React, { useEffect, useState } from 'react';
import { X, Zap, Maximize2, Minimize2 } from 'lucide-react';
import type { V2TaskCenterSnapshot } from '../../api/v2TaskCenter';
import { FfmpegQueue } from './FfmpegQueue';
import { currentCounts } from './ffmpegTaskModel';

export function FfmpegTaskCenter({ snapshot, error, updatedAt, onClose, onLegacy, showToast }: {
  snapshot: V2TaskCenterSnapshot | null; error?: string | null; updatedAt?: number | null;
  onClose: () => void; onLegacy: () => void; showToast: (message: string) => void;
}) {
  const [tab, setTab] = useState<'final' | 'template' | 'scenery'>('final');
  const [full, setFull] = useState(false);
  const c = currentCounts(snapshot?.finalComposition, snapshot?.templateGeneration, snapshot?.sceneryProcessing);
  const legacy = snapshot?.tasks || [];
  useEffect(() => {
    const handleKey = (event: KeyboardEvent) => { if (event.key === 'Escape') onClose(); };
    document.addEventListener('keydown', handleKey);
    return () => document.removeEventListener('keydown', handleKey);
  }, [onClose]);
  return <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/50 backdrop-blur-xs">
    <div role="dialog" aria-modal="true" aria-label="全局任务中心" className={`w-full bg-slate-50 border border-slate-200 shadow-2xl flex flex-col overflow-hidden ${full ? 'h-full' : 'max-w-5xl max-h-[92vh] rounded-3xl'}`}>
      <header className="flex items-start justify-between gap-3 bg-white border-b border-slate-100 px-6 py-5 shrink-0">
        <div className="flex gap-3"><span className="h-10 w-10 flex items-center justify-center rounded-xl bg-slate-900 text-[#DDFD00]"><Zap className="w-5 h-5" /></span>
          <div><h2 className="font-black text-lg text-slate-900">全局任务中心</h2><p className="text-xs text-slate-500 mt-1">成片、模板与风景处理分别管理，暂停后当前一条继续完成。</p></div>
        </div>
        <div className="flex gap-2"><button type="button" aria-label={full ? '还原窗口' : '全屏展开'} onClick={() => setFull(!full)} className="p-2 text-slate-400 hover:bg-slate-100 rounded-lg">{full ? <Minimize2 className="w-4 h-4" /> : <Maximize2 className="w-4 h-4" />}</button><button autoFocus type="button" aria-label="关闭任务中心" onClick={onClose} className="p-2 text-slate-500 hover:bg-slate-100 rounded-lg"><X className="w-5 h-5" /></button></div>
      </header>
      <div className="overflow-y-auto p-6 space-y-5">
        {error && <p role="alert" className="rounded-xl bg-amber-50 p-3 text-xs text-amber-800">任务状态暂未更新，下面保留上次读取结果。{error}</p>}
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3" aria-label="任务统计">
          {[['正在执行', c.running, 'text-indigo-600'], ['排队等待', c.waiting, 'text-slate-800'], ['已完成', c.done, 'text-emerald-600'], ['失败', c.error, c.error ? 'text-rose-600' : 'text-slate-400']].map(([label, value, color]) =>
            <div key={label} className="rounded-2xl border border-slate-200 bg-white p-4"><p className="text-xs text-slate-500">{label}</p><strong className={`block text-2xl tabular-nums mt-1 ${color}`}>{value}</strong></div>)}
        </div>
        <div className="flex items-center justify-between gap-3 flex-wrap">
          <div role="tablist" aria-label="任务类型" className="flex bg-slate-200/60 p-1 rounded-xl">
            {(['final', 'template', 'scenery'] as const).map(key => <button key={key} role="tab" aria-selected={tab === key} onClick={() => setTab(key)} className={`rounded-lg px-4 py-2 text-sm font-bold ${tab === key ? 'bg-slate-900 text-[#DDFD00]' : 'text-slate-500'}`}>
              {key === 'final' ? '成片合成' : key === 'scenery' ? '风景处理' : '模板制作'} <span className="ml-1 text-xs tabular-nums">{key === 'final' ? snapshot?.finalComposition?.jobs.length || 0 : key === 'scenery' ? snapshot?.sceneryProcessing?.jobs.length || 0 : snapshot?.templateGeneration?.jobs.length || 0}</span>
            </button>)}
          </div>
          <span className="text-[11px] text-slate-400">{updatedAt ? `更新于 ${new Date(updatedAt).toLocaleTimeString('zh-CN', { timeZone: 'Asia/Shanghai' })}` : '正在读取任务状态…'}</span>
        </div>
        <FfmpegQueue key={tab} kind={tab} snapshot={tab === 'final' ? snapshot?.finalComposition : tab === 'scenery' ? snapshot?.sceneryProcessing : snapshot?.templateGeneration} showToast={showToast} />
        {legacy.length > 0 && <button type="button" onClick={onLegacy} className="text-xs text-slate-500 underline underline-offset-4">剪映历史任务（{legacy.length}项{legacy.some(t => t.status === 'running') ? '，有任务运行中' : ''}）</button>}
      </div>
    </div>
  </div>;
}
