import type { ScenerySnapshot } from '../../api/scenery';
import React, { useEffect } from 'react';
import { X, ArrowUpRight, Zap } from 'lucide-react';
import type { FinalSnapshot } from '../../api/finalComposition';
import type { GenerationSnapshot } from '../../api/templateGeneration';
import { FfmpegQueue } from './FfmpegQueue';

interface Props {
  sceneryProcessing?: ScenerySnapshot;
  finalComposition?: FinalSnapshot;
  templateGeneration?: GenerationSnapshot;
  error?: string | null;
  updatedAt?: number | null;
  onOpenFullTaskCenter: () => void;
  onClose: () => void;
  showToast: (message: string) => void;
}
export function TaskCenterPreviewPopover({ finalComposition, templateGeneration, sceneryProcessing, error, updatedAt, onOpenFullTaskCenter, onClose, showToast }: Props) {
  useEffect(() => {
    const key = (event: KeyboardEvent) => { if (event.key === 'Escape') onClose(); };
    document.addEventListener('keydown', key);
    return () => document.removeEventListener('keydown', key);
  }, [onClose]);
  return <div role="dialog" aria-label="任务监控" className="absolute top-full right-0 mt-3 w-[480px] max-w-[calc(100vw-24px)] rounded-2xl border border-slate-200 shadow-2xl bg-slate-50 overflow-hidden z-50">
    <div className="px-5 py-4 flex items-center justify-between bg-white border-b border-slate-100">
      <div className="flex items-center gap-2"><Zap className="w-4 h-4 text-indigo-600"/><strong className="text-sm">任务监控</strong></div>
      <button autoFocus type="button" aria-label="关闭任务监控" onClick={onClose} className="text-slate-400 p-1 hover:bg-slate-100 rounded-lg"><X className="w-4 h-4"/></button>
    </div>
    <div className="p-4 space-y-3 max-h-[65vh] overflow-y-auto">
      {error && <p role="alert" className="text-xs text-amber-700">暂未更新，显示上次读取的状态。</p>}
      <FfmpegQueue compact kind="final" snapshot={finalComposition} showToast={showToast}/>
      <FfmpegQueue compact kind="template" snapshot={templateGeneration} showToast={showToast}/>
      <FfmpegQueue compact kind="scenery" snapshot={sceneryProcessing} showToast={showToast}/>
    </div>
    <div className="bg-white border-t border-slate-100 px-5 py-3 flex items-center justify-between gap-2">
      <span className="text-[11px] text-slate-400">{updatedAt ? `更新于 ${new Date(updatedAt).toLocaleTimeString('zh-CN', { timeZone: 'Asia/Shanghai' })}` : '正在读取…'}</span>
      <button type="button" onClick={onOpenFullTaskCenter} className="bg-slate-900 text-[#DDFD00] rounded-xl px-3 py-2 text-xs font-bold">打开任务中心 <ArrowUpRight className="inline w-3.5 h-3.5 ml-1"/></button>
    </div>
  </div>;
}
