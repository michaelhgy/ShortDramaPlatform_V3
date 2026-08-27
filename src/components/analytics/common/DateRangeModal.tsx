import React, { useState } from 'react';
import { Calendar, Check, X, AlertCircle } from 'lucide-react';

interface DateRangeModalProps {
  isOpen: boolean;
  onClose: () => void;
  startDate: string;
  endDate: string;
  onApply: (start: string, end: string) => void;
}

export const DateRangeModal: React.FC<DateRangeModalProps> = ({
  isOpen,
  onClose,
  startDate,
  endDate,
  onApply,
}) => {
  const [tempStart, setTempStart] = useState<string>(startDate || '2026-08-03');
  const [tempEnd, setTempEnd] = useState<string>(endDate || '2026-08-17');
  const [errorMsg, setErrorMsg] = useState<string>('');

  if (!isOpen) return null;

  const minAvailable = '2026-07-25';
  const maxAvailable = '2026-08-23';

  const presets = [
    { label: '08-03 ～ 08-17 (近15天中期)', start: '2026-08-03', end: '2026-08-17' },
    { label: '08-10 ～ 08-23 (最近14天)', start: '2026-08-10', end: '2026-08-23' },
    { label: '08-01 ～ 08-15 (8月上半月)', start: '2026-08-01', end: '2026-08-15' },
    { label: '07-25 ～ 08-08 (早前周期)', start: '2026-07-25', end: '2026-08-08' },
  ];

  const handleApply = () => {
    if (!tempStart || !tempEnd) {
      setErrorMsg('请选择完整的开始与结束日期');
      return;
    }
    if (tempStart > tempEnd) {
      setErrorMsg('开始日期不能晚于结束日期');
      return;
    }
    if (tempStart < minAvailable || tempEnd > maxAvailable) {
      setErrorMsg(`当前数据有效采集区间为 ${minAvailable} 至 ${maxAvailable}`);
      return;
    }
    setErrorMsg('');
    onApply(tempStart, tempEnd);
    onClose();
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/40 backdrop-blur-xs animate-in fade-in duration-100">
      <div className="bg-white rounded-2xl shadow-2xl border border-black/10 w-full max-w-md overflow-hidden animate-in zoom-in-95 duration-150">
        {/* Header */}
        <div className="flex items-center justify-between px-5 py-4 border-b border-black/[0.06] bg-slate-50/70">
          <div className="flex items-center gap-2">
            <div className="p-1.5 rounded-lg bg-[#1A1D2E] text-[#DDFD00]">
              <Calendar className="w-4 h-4" />
            </div>
            <div>
              <h3 className="text-sm font-bold text-[#1A1D2E]">自定义日期范围</h3>
              <p className="text-[11px] text-[#64748B]">选择分析计算的具体起止日期（跨5页面保持）</p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="p-1.5 rounded-lg text-slate-400 hover:text-slate-700 hover:bg-black/[0.04] transition-colors"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Body */}
        <div className="p-5 space-y-4 text-xs">
          {/* Quick Presets */}
          <div className="space-y-1.5">
            <label className="text-[11px] font-semibold text-[#64748B]">快捷预设区间</label>
            <div className="grid grid-cols-1 gap-1.5">
              {presets.map((p) => {
                const isSelected = tempStart === p.start && tempEnd === p.end;
                return (
                  <button
                    key={p.label}
                    type="button"
                    onClick={() => {
                      setTempStart(p.start);
                      setTempEnd(p.end);
                      setErrorMsg('');
                    }}
                    className={`flex items-center justify-between px-3 py-2 rounded-xl text-left transition-all text-xs ${
                      isSelected
                        ? 'bg-[#1A1D2E] text-[#DDFD00] font-semibold shadow-xs'
                        : 'bg-slate-50 text-[#1A1D2E] hover:bg-slate-100 border border-black/[0.04]'
                    }`}
                  >
                    <span>{p.label}</span>
                    {isSelected && <Check className="w-3.5 h-3.5" />}
                  </button>
                );
              })}
            </div>
          </div>

          {/* Date Inputs */}
          <div className="space-y-2 pt-2 border-t border-black/[0.06]">
            <label className="text-[11px] font-semibold text-[#64748B]">自定义精确日期</label>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <span className="block text-[10px] text-slate-500 mb-1">开始日期</span>
                <input
                  type="date"
                  min={minAvailable}
                  max={maxAvailable}
                  value={tempStart}
                  onChange={(e) => {
                    setTempStart(e.target.value);
                    setErrorMsg('');
                  }}
                  className="w-full px-3 py-2 rounded-xl border border-black/10 bg-slate-50 font-mono text-xs focus:bg-white focus:outline-hidden focus:border-[#1A1D2E]"
                />
              </div>
              <div>
                <span className="block text-[10px] text-slate-500 mb-1">结束日期</span>
                <input
                  type="date"
                  min={minAvailable}
                  max={maxAvailable}
                  value={tempEnd}
                  onChange={(e) => {
                    setTempEnd(e.target.value);
                    setErrorMsg('');
                  }}
                  className="w-full px-3 py-2 rounded-xl border border-black/10 bg-slate-50 font-mono text-xs focus:bg-white focus:outline-hidden focus:border-[#1A1D2E]"
                />
              </div>
            </div>
            <div className="text-[10px] text-slate-400">
              数据源可用采集范围：2026-07-25 至 2026-08-23
            </div>
          </div>

          {errorMsg && (
            <div className="flex items-center gap-1.5 p-2 rounded-lg bg-rose-50 border border-rose-200 text-rose-700 text-[11px]">
              <AlertCircle className="w-3.5 h-3.5 shrink-0" />
              <span>{errorMsg}</span>
            </div>
          )}
        </div>

        {/* Footer Actions */}
        <div className="flex items-center justify-end gap-2 px-5 py-3.5 bg-slate-50 border-t border-black/[0.06]">
          <button
            type="button"
            onClick={onClose}
            className="px-4 py-1.5 rounded-xl border border-black/10 text-slate-600 font-medium hover:bg-black/[0.03] transition-colors text-xs"
          >
            取消
          </button>
          <button
            type="button"
            onClick={handleApply}
            className="px-5 py-1.5 rounded-xl bg-[#1A1D2E] text-[#DDFD00] font-semibold hover:bg-black transition-colors shadow-xs text-xs"
          >
            应用筛选
          </button>
        </div>
      </div>
    </div>
  );
};
