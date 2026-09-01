import React, { useEffect, useState } from 'react';
import { Calendar, Check, X, AlertCircle } from 'lucide-react';

interface DateRangeModalProps {
  isOpen: boolean;
  onClose: () => void;
  startDate: string;
  endDate: string;
  onApply: (start: string, end: string) => void;
}

const localDateOffset = (days: number) => {
  const value = new Date();
  value.setHours(12, 0, 0, 0);
  value.setDate(value.getDate() + days);
  return `${value.getFullYear()}-${String(value.getMonth() + 1).padStart(2, '0')}-${String(value.getDate()).padStart(2, '0')}`;
};

export const DateRangeModal: React.FC<DateRangeModalProps> = ({ isOpen, onClose, startDate, endDate, onApply }) => {
  const yesterday = localDateOffset(-1);
  const defaultStart = localDateOffset(-7);
  const [tempStart, setTempStart] = useState<string>(startDate || defaultStart);
  const [tempEnd, setTempEnd] = useState<string>(endDate || yesterday);
  const [errorMsg, setErrorMsg] = useState<string>('');

  useEffect(() => {
    if (!isOpen) return;
    setTempStart(startDate || defaultStart);
    setTempEnd(endDate || yesterday);
    setErrorMsg('');
  }, [isOpen, startDate, endDate, defaultStart, yesterday]);

  if (!isOpen) return null;

  const presets = [
    { label: '昨日', start: yesterday, end: yesterday },
    { label: '最近 7 天', start: localDateOffset(-7), end: yesterday },
    { label: '最近 30 天', start: localDateOffset(-30), end: yesterday },
    { label: '本月截至昨日', start: `${yesterday.slice(0, 8)}01`, end: yesterday },
  ];

  const handleApply = () => {
    if (!tempStart || !tempEnd) { setErrorMsg('请选择完整的开始与结束日期'); return; }
    if (tempStart > tempEnd) { setErrorMsg('开始日期不能晚于结束日期'); return; }
    if (tempEnd > yesterday) { setErrorMsg('当天收益尚未结算，截止日期最多只能选昨天'); return; }
    setErrorMsg('');
    onApply(tempStart, tempEnd);
    onClose();
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4 backdrop-blur-xs animate-in fade-in duration-100">
      <div className="w-full max-w-md overflow-hidden rounded-2xl border border-black/10 bg-white shadow-2xl animate-in zoom-in-95 duration-150">
        <div className="flex items-center justify-between border-b border-black/[0.06] bg-slate-50/70 px-5 py-4"><div className="flex items-center gap-2"><div className="rounded-lg bg-[#1A1D2E] p-1.5 text-[#DDFD00]"><Calendar className="h-4 w-4" /></div><div><h3 className="text-sm font-bold text-[#1A1D2E]">自定义日期范围</h3><p className="text-[11px] text-[#64748B]">选择收益分析使用的数据日期范围</p></div></div><button onClick={onClose} className="rounded-lg p-1.5 text-slate-400 transition-colors hover:bg-black/[0.04] hover:text-slate-700"><X className="h-4 w-4" /></button></div>
        <div className="space-y-4 p-5 text-xs"><div className="space-y-1.5"><label className="text-[11px] font-semibold text-[#64748B]">快捷日期</label><div className="grid grid-cols-2 gap-1.5">{presets.map((preset) => { const isSelected = tempStart === preset.start && tempEnd === preset.end; return <button key={preset.label} type="button" onClick={() => { setTempStart(preset.start); setTempEnd(preset.end); setErrorMsg(''); }} className={`flex items-center justify-between rounded-xl px-3 py-2 text-left text-xs transition-all ${isSelected ? 'bg-[#1A1D2E] font-semibold text-[#DDFD00] shadow-xs' : 'border border-black/[0.04] bg-slate-50 text-[#1A1D2E] hover:bg-slate-100'}`}><span>{preset.label}</span>{isSelected && <Check className="h-3.5 w-3.5" />}</button>; })}</div></div><div className="space-y-2 border-t border-black/[0.06] pt-3"><label className="text-[11px] font-semibold text-[#64748B]">自定义精确日期</label><div className="grid grid-cols-2 gap-3"><div><span className="mb-1 block text-[10px] text-slate-500">开始日期</span><input type="date" max={yesterday} value={tempStart} onChange={(event) => { setTempStart(event.target.value); setErrorMsg(''); }} className="w-full rounded-xl border border-black/10 bg-slate-50 px-3 py-2 font-mono text-xs focus:border-[#1A1D2E] focus:bg-white focus:outline-hidden" /></div><div><span className="mb-1 block text-[10px] text-slate-500">结束日期</span><input type="date" max={yesterday} value={tempEnd} onChange={(event) => { setTempEnd(event.target.value); setErrorMsg(''); }} className="w-full rounded-xl border border-black/10 bg-slate-50 px-3 py-2 font-mono text-xs focus:border-[#1A1D2E] focus:bg-white focus:outline-hidden" /></div></div><div className="text-[10px] text-slate-400">可查询任意历史日期；当天收益尚未结算，最多可选昨天。</div></div>{errorMsg && <div className="flex items-center gap-1.5 rounded-lg border border-rose-200 bg-rose-50 p-2 text-[11px] text-rose-700"><AlertCircle className="h-3.5 w-3.5 shrink-0" /><span>{errorMsg}</span></div>}</div>
        <div className="flex items-center justify-end gap-2 border-t border-black/[0.06] bg-slate-50 px-5 py-3.5"><button type="button" onClick={onClose} className="rounded-xl border border-black/10 px-4 py-1.5 text-xs font-medium text-slate-600 transition-colors hover:bg-black/[0.03]">取消</button><button type="button" onClick={handleApply} className="rounded-xl bg-[#1A1D2E] px-5 py-1.5 text-xs font-semibold text-[#DDFD00] shadow-xs transition-colors hover:bg-black">应用筛选</button></div>
      </div>
    </div>
  );
};
