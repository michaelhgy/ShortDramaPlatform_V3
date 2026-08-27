import React, { useState } from 'react';
import { ScheduleTask } from '../types';
import { Clock, X } from 'lucide-react';

interface EditTimePopoverProps {
  task: ScheduleTask | null;
  isOpen: boolean;
  onClose: () => void;
  onUpdateTime: (taskId: string, newTime: string) => void;
}

export const EditTimePopover: React.FC<EditTimePopoverProps> = ({
  task,
  isOpen,
  onClose,
  onUpdateTime,
}) => {
  const [selectedTime, setSelectedTime] = useState(task?.publishTime || '今天 18:30');
  const [customTime, setCustomTime] = useState('18:30');
  const [isCustom, setIsCustom] = useState(false);

  if (!isOpen || !task) return null;

  const quickPresets = [
    '今天 12:00',
    '今天 18:00',
    '今天 18:30',
    '今天 19:45',
    '今天 21:00',
    '今天 22:30',
    '明天 09:00',
    '明天 12:00',
    '明天 18:30',
  ];

  const handleSave = () => {
    const finalTime = isCustom ? `今天 ${customTime}` : selectedTime;
    onUpdateTime(task.id, finalTime);
    onClose();
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/25 backdrop-blur-xs p-4">
      <div className="w-full max-w-sm rounded-2xl bg-white p-5 shadow-2xl border border-black/[0.08]">
        <div className="flex items-center justify-between pb-3 border-b border-slate-100">
          <div>
            <h4 className="font-bold text-sm text-[#1A1D2E]">修改发布时间</h4>
            <p className="text-[11px] text-[#64748B] truncate max-w-[200px] mt-0.5">
              {task.accountName} · 《{task.dramaName}》
            </p>
          </div>
          <button
            onClick={onClose}
            className="p-1 rounded-lg text-slate-400 hover:text-slate-700 hover:bg-slate-100"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Quick Presets Grid */}
        <div className="mt-4">
          <label className="text-[11px] font-semibold text-[#64748B] block mb-2">
            快捷时段：
          </label>
          <div className="grid grid-cols-3 gap-2">
            {quickPresets.map(preset => (
              <button
                key={preset}
                type="button"
                onClick={() => {
                  setSelectedTime(preset);
                  setIsCustom(false);
                }}
                className={`py-1.5 px-2 text-xs rounded-lg font-semibold transition-all border ${
                  !isCustom && selectedTime === preset
                    ? 'bg-[#1A1D2E] text-[#DDFD00] border-[#1A1D2E]'
                    : 'bg-[#F8FAFC] text-[#334155] border-black/[0.06] hover:bg-white'
                }`}
              >
                {preset}
              </button>
            ))}
          </div>
        </div>

        {/* Custom Input */}
        <div className="mt-3.5 pt-3 border-t border-slate-100 flex items-center justify-between">
          <button
            type="button"
            onClick={() => setIsCustom(true)}
            className={`text-xs px-2.5 py-1 rounded-lg border font-medium ${
              isCustom ? 'bg-[#1A1D2E] text-[#DDFD00] border-[#1A1D2E]' : 'bg-[#F8FAFC] text-[#64748B] border-black/[0.06]'
            }`}
          >
            自定义时刻
          </button>

          {isCustom && (
            <div className="flex items-center gap-1.5 text-xs">
              <span className="text-[#64748B]">今天</span>
              <input
                type="time"
                value={customTime}
                onChange={(e) => setCustomTime(e.target.value)}
                className="px-2 py-0.5 rounded border border-slate-300 bg-white text-xs font-bold text-[#1A1D2E]"
              />
            </div>
          )}
        </div>

        {/* Actions */}
        <div className="mt-5 flex items-center justify-end gap-2">
          <button
            onClick={onClose}
            className="px-3 py-1.5 rounded-xl text-xs font-semibold text-slate-500 hover:bg-slate-100"
          >
            取消
          </button>
          <button
            onClick={handleSave}
            className="px-4 py-1.5 rounded-xl bg-[#1A1D2E] text-[#DDFD00] text-xs font-bold hover:bg-black transition-colors"
          >
            确认更新
          </button>
        </div>
      </div>
    </div>
  );
};
