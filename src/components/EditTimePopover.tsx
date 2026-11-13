import React, { useEffect, useState } from 'react';
import { ScheduleTask } from '../types';
import { Calendar, X } from 'lucide-react';
import { plannedDate, planningDayOffset } from '../utils/plannedDate';

interface EditTimePopoverProps { task: ScheduleTask | null; isOpen: boolean; onClose: () => void; onUpdateTime: (taskId: string, newDate: string) => void }
export const EditTimePopover: React.FC<EditTimePopoverProps> = ({ task, isOpen, onClose, onUpdateTime }) => {
  const [value, setValue] = useState('');
  useEffect(() => { if (isOpen && task) setValue(plannedDate(task.plannedPublishAt) || plannedDate(task.publishTime)); }, [isOpen, task?.id]);
  useEffect(() => { if (!isOpen) return; const key = (event: KeyboardEvent) => { if (event.key === 'Escape') { event.preventDefault(); onClose(); } }; window.addEventListener('keydown', key); return () => window.removeEventListener('keydown', key); }, [isOpen, onClose]);
  if (!isOpen || !task) return null;
  return <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/25 p-4 backdrop-blur-sm"><div role="dialog" aria-modal="true" aria-label="修改计划发布日期" className="w-full max-w-sm space-y-4 rounded-2xl border border-slate-200 bg-white p-5 shadow-2xl">
    <div className="flex items-start justify-between"><div><h4 className="flex items-center gap-2 text-sm font-black"><Calendar size={16} />修改计划发布日期</h4><p className="mt-1 text-xs text-slate-500">{task.accountName} · 《{task.dramaName}》</p></div><button aria-label="关闭日期设置" onClick={onClose} className="rounded-lg p-1 text-slate-400 hover:bg-slate-100"><X size={16} /></button></div>
    <input aria-label="计划发布日期" type="date" value={value} onChange={e => setValue(e.target.value)} className="w-full rounded-xl border border-slate-200 px-3 py-2 text-sm" />
    <div className="flex gap-2 text-xs">{[0, 1, 2].map((offset, i) => <button key={offset} className="rounded-lg bg-slate-100 px-3 py-1.5" onClick={() => setValue(planningDayOffset(offset))}>{['今天', '明天', '后天'][i]}</button>)}<button className="rounded-lg bg-slate-100 px-3 py-1.5" onClick={() => setValue('')}>暂不设置</button></div>
    <p className="text-xs leading-5 text-slate-400">这里安排制作计划日期，实际发布的时分在自动发布中设置。</p><div className="flex justify-end gap-2"><button className="rounded-xl border border-slate-200 px-4 py-2 text-xs font-bold" onClick={onClose}>取消</button><button className="rounded-xl bg-[#1A1D2E] px-4 py-2 text-xs font-black text-[#DDFD00]" onClick={() => { onUpdateTime(task.id, value); onClose(); }}>保存日期</button></div>
  </div></div>;
};
