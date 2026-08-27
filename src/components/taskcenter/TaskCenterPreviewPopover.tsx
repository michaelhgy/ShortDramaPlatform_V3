import React from 'react';
import { 
  Zap, 
  X, 
  RotateCcw, 
  AlertTriangle, 
  Clock, 
  Video, 
  Film, 
  Sparkles, 
  ArrowUpRight,
  ShieldAlert,
  AlertCircle
} from 'lucide-react';
import { TaskItem, ExecutorId } from './taskCenterTypes';

interface TaskCenterPreviewPopoverProps {
  tasks: TaskItem[];
  onRetryTask: (task: TaskItem) => void;
  onOpenFullTaskCenter: () => void;
  onClose: () => void;
}

// Fixed display order of the 3 executors
const EXECUTOR_ORDER: { id: ExecutorId; label: string; icon: React.ReactNode }[] = [
  { id: 'video_exporter', label: '视频导出器', icon: <Video className="w-3.5 h-3.5" /> },
  { id: 'final_generator', label: '成片生成器', icon: <Film className="w-3.5 h-3.5" /> },
  { id: 'template_generator', label: '模板生成器', icon: <Sparkles className="w-3.5 h-3.5" /> },
];

export const TaskCenterPreviewPopover: React.FC<TaskCenterPreviewPopoverProps> = ({
  tasks,
  onRetryTask,
  onOpenFullTaskCenter,
  onClose,
}) => {
  // 1. Get currently executing tasks for each executor (strictly at most 1 per executor)
  const currentRunningSlots = EXECUTOR_ORDER.map(({ id, label, icon }) => {
    // Find task currently occupying this executor
    const currentTask = tasks.find(
      t => t.executorId === id && (t.status === 'running' || t.status === 'timeout')
    );
    return {
      executorId: id,
      label,
      icon,
      task: currentTask || null,
    };
  }).filter(slot => slot.task !== null); // Only show when there is an active task

  const runningTaskIds = new Set(
    currentRunningSlots
      .map(s => s.task?.id)
      .filter((id): id is string => Boolean(id))
  );

  // 2. Terminated/aborted error tasks (excluding tasks currently occupying an executor which are shown above)
  const separateErrorTasks = tasks.filter(
    t => t.status === 'error' && !runningTaskIds.has(t.id)
  );

  const hasAnyActiveOrError = currentRunningSlots.length > 0 || separateErrorTasks.length > 0;
  const hasAnyTimeout = currentRunningSlots.some(s => s.task?.isTimeout || s.task?.status === 'timeout');

  const getTaskTypeDisplay = (task: TaskItem) => {
    if (task.taskType === 'video_export') {
      return task.taskSubType === 'template_video_export' ? '视频导出 · 模板' : '视频导出 · 成片';
    }
    if (task.taskType === 'template_draft') {
      return '模板草稿生成';
    }
    return '成片草稿生成';
  };

  return (
    <div className="absolute right-0 mt-2 w-[380px] sm:w-[410px] rounded-2xl bg-white border border-black/[0.08] shadow-2xl z-50 overflow-hidden animate-in fade-in slide-in-from-top-2 duration-150">
      {/* Popover Header */}
      <div className="px-4 py-3 bg-[#F8FAFC] border-b border-black/[0.06] flex items-center justify-between">
        <div className="flex items-center gap-2">
          <div className="w-6 h-6 rounded-lg bg-[#1A1D2E] text-[#DDFD00] flex items-center justify-center font-bold text-xs shadow-2xs">
            <Zap className="w-3.5 h-3.5" />
          </div>
          <div>
            <div className="flex items-center gap-1.5">
              <span className="font-extrabold text-xs text-[#1A1D2E]">当前任务监控</span>
              {hasAnyTimeout && (
                <span className="text-[10px] px-1.5 py-0.2 rounded bg-rose-500 text-white font-extrabold animate-pulse">
                  有超时
                </span>
              )}
            </div>
            <p className="text-[10px] text-[#64748B]">
              {currentRunningSlots.length > 0
                ? `${currentRunningSlots.length} 个执行器正在运转`
                : '所有执行器待命就绪'}
            </p>
          </div>
        </div>

        <button
          onClick={onClose}
          className="p-1 rounded-lg hover:bg-black/[0.05] text-slate-400 hover:text-slate-600 transition-colors cursor-pointer"
        >
          <X className="w-4 h-4" />
        </button>
      </div>

      {/* Body: Current Executing Tasks & Error Tasks */}
      <div className="p-3 space-y-3 max-h-[380px] overflow-y-auto">
        {/* Section 1: Current Tasks (Fixed 3-executor order: Video -> Final -> Template) */}
        {currentRunningSlots.length > 0 ? (
          <div className="space-y-2">
            <div className="text-[11px] font-bold text-[#64748B] px-1 flex items-center justify-between">
              <span>正在执行的任务</span>
              <span className="text-[10px] font-mono text-slate-400">固定通道串行</span>
            </div>

            {currentRunningSlots.map(({ executorId, label, icon, task }) => {
              if (!task) return null;
              const isTimeout = task.isTimeout || task.status === 'timeout';

              return (
                <div
                  key={executorId}
                  className={`p-3 rounded-xl border transition-all ${
                    isTimeout
                      ? 'bg-rose-50/60 border-rose-200/90 shadow-2xs'
                      : 'bg-white border-black/[0.06] hover:border-black/[0.12] shadow-2xs'
                  }`}
                >
                  {/* Executor Tag & Status Badge */}
                  <div className="flex items-center justify-between gap-2">
                    <div className="flex items-center gap-1.5">
                      <span className="text-slate-700">{icon}</span>
                      <span className="font-extrabold text-[11px] text-[#1A1D2E]">{label}</span>
                      <span className="text-[10px] text-slate-400">·</span>
                      <span className="text-[10px] text-[#64748B] font-medium">
                        {getTaskTypeDisplay(task)}
                      </span>
                    </div>

                    {isTimeout ? (
                      <span className="inline-flex items-center gap-1 text-[10px] px-2 py-0.5 rounded-md font-extrabold bg-rose-100 text-rose-800 border border-rose-200 animate-pulse">
                        <AlertTriangle className="w-2.5 h-2.5 text-rose-600" />
                        已超时
                      </span>
                    ) : (
                      <span className="inline-flex items-center gap-1 text-[10px] px-2 py-0.5 rounded-md font-bold bg-emerald-50 text-emerald-800 border border-emerald-200/60">
                        <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-ping" />
                        执行中
                      </span>
                    )}
                  </div>

                  {/* Drama + Account */}
                  <div className="mt-2 flex items-center justify-between text-xs">
                    <div className="flex items-center gap-1.5 min-w-0">
                      <span className="font-extrabold text-[#1A1D2E] truncate">
                        《{task.dramaName}》
                      </span>
                      <span className="text-slate-300">/</span>
                      <span className="text-[#64748B] text-[11px] truncate">
                        {task.accountName}
                      </span>
                    </div>
                  </div>

                  {/* Material Name if available */}
                  {task.materialName && (
                    <div className="mt-1 text-[10px] text-slate-500 truncate flex items-center gap-1">
                      <span className="text-slate-400 shrink-0">素材:</span>
                      <code className="bg-slate-100 text-slate-700 px-1 py-0.5 rounded truncate max-w-[280px]">
                        {task.materialName}
                      </code>
                    </div>
                  )}

                  {/* Card Bottom: Elapsed Time + Retry Button */}
                  <div className="mt-2.5 pt-2 border-t border-black/[0.04] flex items-center justify-between">
                    <div className="flex items-center gap-1 text-[11px]">
                      <Clock className="w-3 h-3 text-slate-400" />
                      <span className="text-[#64748B]">已耗时:</span>
                      <strong className={`font-mono ${isTimeout ? 'text-rose-700 font-bold' : 'text-[#1A1D2E]'}`}>
                        {task.durationFormatted}
                      </strong>
                    </div>

                    <button
                      onClick={() => onRetryTask(task)}
                      className="flex items-center gap-1 px-2.5 py-1 rounded-lg bg-white border border-black/[0.1] hover:bg-slate-50 text-[11px] font-extrabold text-[#1A1D2E] shadow-2xs transition-all active:scale-95 cursor-pointer"
                      title="若当前任务卡顿或异常，重新启动该任务"
                    >
                      <RotateCcw className="w-3 h-3 text-[#1A1D2E]" />
                      <span>重试</span>
                    </button>
                  </div>
                </div>
              );
            })}
          </div>
        ) : null}

        {/* Section 2: Abnormal / Error Tasks (Only shown when errors exist) */}
        {separateErrorTasks.length > 0 && (
          <div className="space-y-2 pt-1">
            <div className="text-[11px] font-bold text-rose-800 px-1 flex items-center gap-1.5">
              <ShieldAlert className="w-3.5 h-3.5 text-rose-600" />
              <span>待处理异常任务 ({separateErrorTasks.length})</span>
            </div>

            {separateErrorTasks.map((task) => (
              <div
                key={task.id}
                className="p-3 rounded-xl bg-rose-50/70 border border-rose-200 text-xs space-y-2"
              >
                <div className="flex items-start justify-between gap-2">
                  <div className="min-w-0">
                    <div className="flex items-center gap-1.5">
                      <span className="font-extrabold text-xs text-rose-950">
                        《{task.dramaName}》
                      </span>
                      <span className="text-[10px] text-rose-700 font-medium">
                        · {task.accountName}
                      </span>
                    </div>
                    <p className="text-[10px] text-rose-800 line-clamp-1 mt-0.5">
                      {task.errorDetail || '任务执行中断，需要人工重试'}
                    </p>
                  </div>

                  <button
                    onClick={() => onRetryTask(task)}
                    className="shrink-0 flex items-center gap-1 px-2 py-1 rounded-lg bg-white border border-rose-200 hover:bg-rose-100 text-[11px] font-extrabold text-rose-900 transition-all cursor-pointer"
                  >
                    <RotateCcw className="w-3 h-3 text-rose-700" />
                    <span>重试</span>
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}

        {/* Empty State when no active tasks & no errors */}
        {!hasAnyActiveOrError && (
          <div className="py-6 px-4 text-center rounded-xl bg-slate-50 border border-dashed border-slate-200 text-xs text-[#64748B] space-y-1">
            <div className="w-7 h-7 mx-auto rounded-full bg-emerald-50 text-emerald-600 flex items-center justify-center font-bold">
              ✓
            </div>
            <p className="font-bold text-[#1A1D2E] mt-1.5">当前无正在执行的任务</p>
            <p className="text-[11px] text-slate-400">三大执行器已就绪待命</p>
          </div>
        )}
      </div>

      {/* Popover Footer: Clear Single Action to Open Full Task Center */}
      <div className="p-3 bg-[#F8FAFC] border-t border-black/[0.06] flex items-center justify-between">
        <span className="text-[11px] text-[#64748B]">
          更多队列调度与历史明细
        </span>

        <button
          onClick={() => {
            onClose();
            onOpenFullTaskCenter();
          }}
          className="flex items-center gap-1 px-3 py-1.5 rounded-xl bg-[#1A1D2E] text-[#DDFD00] hover:bg-black text-xs font-bold transition-all shadow-2xs active:scale-95 cursor-pointer"
        >
          <span>展开全局任务中心</span>
          <ArrowUpRight className="w-3.5 h-3.5 stroke-[2.5]" />
        </button>
      </div>
    </div>
  );
};
