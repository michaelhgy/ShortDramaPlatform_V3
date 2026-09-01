import React, { useEffect, useMemo, useState } from 'react';
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
  Pause,
  Play,
  ShieldAlert,
  AlertCircle
} from 'lucide-react';
import { TaskItem, ExecutorId, ExecutorInfo } from './taskCenterTypes';
import { taskElapsedLabel } from '../../utils/duration';
import { getTaskCenterActions } from './taskCenterActionPolicy';

interface TaskCenterPreviewPopoverProps {
  tasks: TaskItem[];
  onTaskAction: (task: TaskItem) => void;
  isQueuePaused: boolean;
  isQueuePauseUpdating?: boolean;
  onToggleQueuePause: () => void;
  executors: ExecutorInfo[];
  executorUpdatingId?: ExecutorId | null;
  onToggleExecutor: (executor: ExecutorInfo) => void;
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
  onTaskAction,
  isQueuePaused,
  isQueuePauseUpdating = false,
  onToggleQueuePause,
  executors,
  executorUpdatingId = null,
  onToggleExecutor,
  onOpenFullTaskCenter,
  onClose,
}) => {
  const [clockNow, setClockNow] = useState(() => Date.now());

  useEffect(() => {
    const timer = window.setInterval(() => setClockNow(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, []);

  const liveTasks = useMemo(() => tasks.map((task) => {
    if (!task.startedAt || task.completedAt || task.status !== 'running') return task;
    const started = Date.parse(task.startedAt);
    if (!Number.isFinite(started)) return task;
    return { ...task, durationSeconds: Math.max(0, Math.floor((clockNow - started) / 1000)) };
  }), [tasks, clockNow]);

  const stageStatusForExecutor = (task: TaskItem, executorId: ExecutorId) => {
    if (executorId === 'video_exporter') {
      return task.videoStage.rawStatus ? task.videoStage.status : null;
    }
    return task.executorId === executorId ? task.draftStage.status : null;
  };

  // 1. Get currently executing tasks for each executor (strictly at most 1 per executor)
  const currentRunningSlots = EXECUTOR_ORDER.map(({ id, label, icon }) => {
    // Find task currently occupying this executor
    const currentTask = liveTasks.find(
      t => {
        const stage = stageStatusForExecutor(t, id);
        return stage === 'running';
      }
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
  const separateErrorTasks = liveTasks.filter(
    t => (t.status === 'error' || t.status === 'timeout') && !runningTaskIds.has(t.id)
  );

  const hasAnyActiveOrError = currentRunningSlots.length > 0 || separateErrorTasks.length > 0;
  const hasAnyTimeout = separateErrorTasks.some(task => task.isTimeout || task.status === 'timeout');

  const getTaskTypeDisplay = (task: TaskItem) => {
    if (task.taskType === 'video_export') {
      return task.taskSubType === 'template_video_export' ? '视频导出 · 模板' : '视频导出 · 成片';
    }
    if (task.taskType === 'template_draft') {
      return '模板草稿生成';
    }
    return '成片草稿生成';
  };

  const executorIcon = (id: ExecutorId) => {
    if (id === 'video_exporter') return <Video className="w-3.5 h-3.5" />;
    if (id === 'final_generator') return <Film className="w-3.5 h-3.5" />;
    return <Sparkles className="w-3.5 h-3.5" />;
  };

  const executorStatus = (executor: ExecutorInfo) => {
    if (executor.status === 'error_paused') return { label: '错误暂停，点击继续会清除连续失败计数', dot: 'bg-rose-500', icon: <Play className="w-3 h-3 fill-current" /> };
    if (executor.status === 'manual_paused') return { label: '人工暂停，点击继续执行器', dot: 'bg-slate-500', icon: <Play className="w-3 h-3 fill-current" /> };
    if (executor.status === 'pausing') return { label: '正在暂停，等待当前任务结束', dot: 'bg-amber-500 animate-pulse', icon: <Pause className="w-3 h-3" /> };
    if (executor.status === 'running') return { label: '正在执行，点击后将在当前任务结束后暂停', dot: 'bg-emerald-500 animate-pulse', icon: <Pause className="w-3 h-3" /> };
    if (executor.status === 'waiting') return { label: '排队等待，点击暂停执行器', dot: 'bg-amber-500', icon: <Pause className="w-3 h-3" /> };
    return { label: '待机就绪，点击暂停执行器', dot: 'bg-emerald-500', icon: <Pause className="w-3 h-3" /> };
  };

  return (
    <div className="absolute right-0 mt-2 w-[380px] sm:w-[410px] rounded-2xl bg-white border border-black/[0.08] shadow-2xl z-50 overflow-hidden animate-in fade-in slide-in-from-top-2 duration-150">
      {/* Popover Header */}
      <div className="px-4 py-3 bg-[#F8FAFC] border-b border-black/[0.06] flex items-center justify-between gap-3">
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

        <div className="flex items-center gap-2 shrink-0">
          <button
            onClick={onToggleQueuePause}
            disabled={isQueuePauseUpdating}
            className={`flex items-center gap-1.5 px-3 py-1.5 rounded-xl text-xs font-bold transition-all cursor-pointer disabled:cursor-wait disabled:opacity-60 ${
              isQueuePaused
                ? 'bg-amber-500 text-white shadow-xs hover:bg-amber-600'
                : 'bg-slate-100 hover:bg-slate-200 text-[#1A1D2E]'
            }`}
            title={isQueuePaused ? '继续全部执行器领取任务' : '暂停全部执行器继续领取任务；正在执行的任务不会被中断'}
          >
            {isQueuePaused ? <Play className="w-3.5 h-3.5 fill-current" /> : <Pause className="w-3.5 h-3.5" />}
            <span>{isQueuePauseUpdating ? '正在更新…' : (isQueuePaused ? '继续执行队列' : '暂停执行队列')}</span>
          </button>
          <button
            onClick={onClose}
            className="p-1 rounded-lg hover:bg-black/[0.05] text-slate-400 hover:text-slate-600 transition-colors cursor-pointer"
          >
            <X className="w-4 h-4" />
          </button>
        </div>
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
              return (
                <div
                  key={executorId}
                  className={`p-3 rounded-xl border transition-all ${
                    'bg-white border-black/[0.06] hover:border-black/[0.12] shadow-2xs'
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

                    <span className="inline-flex items-center gap-1 text-[10px] px-2 py-0.5 rounded-md font-bold bg-emerald-50 text-emerald-800 border border-emerald-200/60">
                      <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-ping" />
                      执行中
                    </span>
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
                      <strong className="font-mono text-[#1A1D2E]">
                        {taskElapsedLabel(task.durationSeconds, task.durationFormatted)}
                      </strong>
                    </div>

                    <button
                      onClick={() => onTaskAction(task)}
                      className="flex items-center gap-1 px-2.5 py-1 rounded-lg bg-white border border-black/[0.1] hover:bg-slate-50 text-[11px] font-extrabold text-[#1A1D2E] shadow-2xs transition-all active:scale-95 cursor-pointer"
                      title={executorId === 'video_exporter' ? '重新排入视频导出队列' : '若当前任务卡顿或异常，重新启动该任务'}
                    >
                      <RotateCcw className="w-3 h-3 text-[#1A1D2E]" />
                      <span>{executorId === 'video_exporter' ? '重新导出' : '重试'}</span>
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

            {separateErrorTasks.map((task) => {
              const action = getTaskCenterActions(task)[0] || 'retry';
              const actionLabel = action === 'regenerate' ? '重新生成' : action === 'reExport' ? '重新导出' : '重试';
              return <div
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
                    onClick={() => onTaskAction(task)}
                    className="shrink-0 flex items-center gap-1 px-2 py-1 rounded-lg bg-white border border-rose-200 hover:bg-rose-100 text-[11px] font-extrabold text-rose-900 transition-all cursor-pointer"
                  >
                    <RotateCcw className="w-3 h-3 text-rose-700" />
                    <span>{actionLabel}</span>
                  </button>
                </div>
              </div>;
            })}
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

      {/* Popover Footer: compact controls for the three independent executors */}
      <div className="p-3 bg-[#F8FAFC] border-t border-black/[0.06] flex items-center justify-between">
        <div className="flex items-center gap-2">
          {EXECUTOR_ORDER.map(({ id, label }) => {
            const executor = executors.find((item) => item.id === id);
            if (!executor) return null;
            const status = executorStatus(executor);
            const isUpdating = executorUpdatingId === id;
            return (
              <div key={id} className="flex items-center gap-1">
                <div
                  className="relative w-7 h-7 rounded-lg bg-[#1A1D2E] text-[#DDFD00] flex items-center justify-center shadow-2xs"
                  title={`${label}：${status.label}`}
                >
                  {executorIcon(id)}
                  <span className={`absolute -right-0.5 -bottom-0.5 w-2.5 h-2.5 rounded-full border-2 border-[#F8FAFC] ${status.dot}`} />
                </div>
                <button
                  type="button"
                  onClick={() => onToggleExecutor(executor)}
                  disabled={isUpdating || executor.status === 'pausing'}
                  title={`${label}：${status.label}`}
                  aria-label={`${label}：${status.label}`}
                  className={`p-1.5 rounded-lg border transition-colors cursor-pointer disabled:cursor-wait disabled:opacity-60 ${
                    executor.status === 'error_paused' ? 'border-rose-200 bg-rose-50 text-rose-700 hover:bg-rose-100' :
                    executor.status === 'manual_paused' ? 'border-amber-200 bg-amber-50 text-amber-700 hover:bg-amber-100' :
                    'border-black/[0.08] bg-white text-slate-500 hover:bg-slate-50 hover:text-slate-800'
                  }`}
                >
                  {isUpdating ? <span className="block w-3 h-3 rounded-full border-2 border-current border-t-transparent animate-spin" /> : status.icon}
                </button>
              </div>
            );
          })}
        </div>

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
