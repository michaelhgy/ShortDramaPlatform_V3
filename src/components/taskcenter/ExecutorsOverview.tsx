import React from 'react';
import { 
  Video, 
  Layers, 
  Sparkles, 
  RotateCcw, 
  Play,
  Pause,
  Clock, 
  AlertTriangle, 
  CheckCircle2, 
  Flame, 
  FileText, 
  Film,
  Zap,
  ArrowRight,
  ShieldAlert,
  SlidersHorizontal,
  ChevronRight
} from 'lucide-react';
import { ExecutorInfo, TaskItem } from './taskCenterTypes';
import { taskElapsedLabel } from '../../utils/duration';

interface ExecutorsOverviewProps {
  executors: ExecutorInfo[];
  tasks: TaskItem[];
  onRetryTask: (task: TaskItem) => void;
  onViewTaskDetail: (task: TaskItem) => void;
  onToggleExecutor: (executor: ExecutorInfo) => void;
}

export const ExecutorsOverview: React.FC<ExecutorsOverviewProps> = ({
  executors,
  tasks,
  onRetryTask,
  onViewTaskDetail,
  onToggleExecutor,
}) => {
  const executorStageStatus = (task: TaskItem, executorId: string) => {
    if (executorId === 'video_exporter') {
      return task.videoStage.rawStatus ? task.videoStage.status : null;
    }
    return task.executorId === executorId ? task.draftStage.status : null;
  };

  const isOwnedByExecutor = (task: TaskItem, executorId: string) =>
    executorStageStatus(task, executorId) !== null;

  const getIconForExecutor = (id: string) => {
    switch (id) {
      case 'video_exporter':
        return <Video className="w-5 h-5" />;
      case 'final_generator':
        return <Film className="w-5 h-5" />;
      case 'template_generator':
        return <Sparkles className="w-5 h-5" />;
      default:
        return <Zap className="w-5 h-5" />;
    }
  };

  return (
    <div className="space-y-3">
      {/* Section Header */}
      <div className="flex flex-wrap items-center justify-between gap-2 px-1">
        <div className="flex items-center gap-2">
          <div className="w-2 h-2 rounded-full bg-emerald-500 animate-ping" />
          <h3 className="font-extrabold text-sm text-[#1A1D2E] tracking-tight">
            三大独立执行器实时状态
          </h3>
          <span className="text-[11px] px-2 py-0.5 rounded-md bg-[#1A1D2E]/5 text-[#64748B] font-medium border border-black/[0.04]">
            并行运转 · 内部串行（1任务/通道）
          </span>
        </div>

        <div className="text-[11px] text-[#64748B] flex items-center gap-3">
          <span className="flex items-center gap-1">
            <span className="w-2 h-2 rounded-full bg-emerald-500" />
            正常运行中
          </span>
          <span className="flex items-center gap-1">
            <span className="w-2 h-2 rounded-full bg-amber-500" />
            排队等待
          </span>
          <span className="flex items-center gap-1">
            <span className="w-2 h-2 rounded-full bg-rose-500" />
            超时预警
          </span>
        </div>
      </div>

      {/* 3 Executors Side-by-Side Cards */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        {executors.map((executor) => {
          const currentTask = tasks.find(
            t => t.id === executor.currentTaskId || t.videoExportTaskId === executor.currentTaskId
          );
          const waitingTasks = tasks.filter(
            t => isOwnedByExecutor(t, executor.id) && executorStageStatus(t, executor.id) === 'waiting'
          );
          const nextTask = waitingTasks[0];
          // 队列中的历史超时只应在对应任务卡和“超时 / 失败”列表中显示。
          // 执行器概览只反映它此刻正在执行的任务，避免旧记录把正常运行的
          // 视频导出器错误标成“超时警示”。
          const hasTimeout = Boolean(currentTask?.isTimeout || currentTask?.status === 'timeout');

          // Calculate completed percentage for this executor
          const total = executor.queueStats.total || 1;
          const completedPct = Math.round((executor.queueStats.completed / total) * 100);

          return (
            <div
              key={executor.id}
              className={`rounded-2xl border transition-all duration-200 flex flex-col justify-between overflow-hidden shadow-xs ${
                hasTimeout
                  ? 'bg-rose-50/40 border-rose-200/80 shadow-rose-500/5'
                  : 'bg-white border-black/[0.08] hover:border-black/[0.14]'
              }`}
            >
              {/* Card Top Header */}
              <div className="p-4 border-b border-black/[0.05] bg-slate-50/50">
                <div className="flex items-start justify-between gap-2">
                  <div className="flex items-center gap-2.5">
                    <div
                      className={`w-9 h-9 rounded-xl flex items-center justify-center font-bold shadow-xs ${
                        hasTimeout
                          ? 'bg-rose-500 text-white'
                          : 'bg-[#1A1D2E] text-[#DDFD00]'
                      }`}
                    >
                      {getIconForExecutor(executor.id)}
                    </div>
                    <div>
                      <div>
                        <h4 className="font-extrabold text-sm text-[#1A1D2E]">
                          {executor.name}
                        </h4>
                      </div>
                      <p className="text-[11px] text-[#64748B] line-clamp-1 mt-0.5">
                        {executor.subtitle}
                      </p>
                    </div>
                  </div>

                  {/* Status Badge */}
                  <div className="flex items-center gap-1.5">
                    <button
                      type="button"
                      onClick={() => onToggleExecutor(executor)}
                      disabled={executor.status === 'pausing'}
                      className={`p-1.5 rounded-lg border transition-colors cursor-pointer disabled:cursor-wait disabled:opacity-60 ${
                        executor.status === 'error_paused' ? 'border-rose-200 bg-rose-50 text-rose-700 hover:bg-rose-100' :
                        executor.status === 'manual_paused' ? 'border-amber-200 bg-amber-50 text-amber-700 hover:bg-amber-100' :
                        'border-black/[0.08] bg-white text-slate-500 hover:bg-slate-50 hover:text-slate-800'
                      }`}
                      title={executor.status === 'error_paused' ? '启动执行器并清除连续失败计数' : executor.status === 'manual_paused' ? '恢复执行器' : '暂停执行器（等待当前任务结束）'}
                      aria-label={executor.status === 'error_paused' || executor.status === 'manual_paused' ? '启动执行器' : '暂停执行器'}
                    >
                      {executor.status === 'error_paused' || executor.status === 'manual_paused' ? <Play className="w-3.5 h-3.5 fill-current" /> : <Pause className="w-3.5 h-3.5" />}
                    </button>
                    {executor.status === 'error_paused' ? (
                      <span className="inline-flex items-center gap-1 text-[11px] px-2.5 py-1 rounded-lg bg-rose-100 text-rose-800 font-bold border border-rose-200 animate-pulse">
                        <AlertTriangle className="w-3 h-3 text-rose-600" />
                        错误暂停
                      </span>
                    ) : executor.status === 'pausing' ? (
                      <span className="inline-flex items-center gap-1 text-[11px] px-2.5 py-1 rounded-lg bg-amber-50 text-amber-800 font-bold border border-amber-200">
                        <Pause className="w-3 h-3 text-amber-600" />
                        正在暂停
                      </span>
                    ) : executor.status === 'manual_paused' ? (
                      <span className="inline-flex items-center gap-1 text-[11px] px-2.5 py-1 rounded-lg bg-slate-100 text-slate-700 font-bold border border-slate-200">
                        <Pause className="w-3 h-3 text-slate-500" />
                        人工暂停
                      </span>
                    ) : hasTimeout ? (
                      <span className="inline-flex items-center gap-1 text-[11px] px-2.5 py-1 rounded-lg bg-rose-100 text-rose-800 font-bold border border-rose-200 animate-pulse">
                        <AlertTriangle className="w-3 h-3 text-rose-600" />
                        超时警示
                      </span>
                    ) : executor.status === 'running' ? (
                      <span className="inline-flex items-center gap-1 text-[11px] px-2.5 py-1 rounded-lg bg-emerald-50 text-emerald-800 font-bold border border-emerald-200/80">
                        <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-ping" />
                        执行中
                      </span>
                    ) : (
                      <span className="inline-flex items-center gap-1 text-[11px] px-2.5 py-1 rounded-lg bg-slate-100 text-slate-700 font-medium">
                        待机就绪
                      </span>
                    )}
                  </div>
                </div>
              </div>

              {/* Card Middle: Current Task Section */}
              <div className="p-4 flex-1 space-y-3">
                <div className="flex items-center justify-between text-xs">
                  <span className="font-bold text-[#1A1D2E] flex items-center gap-1.5">
                    <Clock className="w-3.5 h-3.5 text-[#64748B]" />
                    当前正在执行
                  </span>
                  {currentTask && (
                    <span className={`text-[11px] font-mono font-semibold ${
                      currentTask.isTimeout ? 'text-rose-700 font-bold' : 'text-[#64748B]'
                    }`}>
                      耗时: {taskElapsedLabel(currentTask.durationSeconds, currentTask.durationFormatted)}
                    </span>
                  )}
                </div>

                {currentTask ? (
                  <div className={`p-3 rounded-xl border transition-all ${
                    currentTask.isTimeout
                      ? 'bg-rose-100/40 border-rose-200'
                      : 'bg-[#F8FAFC] border-black/[0.04]'
                  }`}>
                    {/* Title and Drama */}
                    <div className="flex items-start justify-between gap-2">
                      <div className="min-w-0 flex-1">
                        <div className="flex items-center gap-1.5 flex-wrap">
                          {currentTask.priorityTag && (
                            <span className="text-[10px] px-1.5 py-0.5 rounded bg-amber-100/80 text-amber-900 font-bold">
                              {currentTask.priorityTag.split('·')[0]}
                            </span>
                          )}
                          <h5 className="font-extrabold text-xs text-[#1A1D2E] truncate">
                            {currentTask.title}
                          </h5>
                        </div>
                        <div className="flex flex-wrap items-center gap-x-2 gap-y-1 text-[11px] text-[#64748B] mt-1">
                          <span>剧集：《{currentTask.dramaName}》</span>
                          <span>·</span>
                          <span>账号：{currentTask.accountName}</span>
                        </div>
                        {currentTask.materialName && (
                          <div className="text-[10px] text-slate-500 truncate mt-1 flex items-center gap-1">
                            <span className="text-slate-400">素材:</span>
                            <code className="bg-white/80 px-1 py-0.5 rounded border border-black/[0.04] text-slate-600 truncate max-w-[200px]">
                              {currentTask.materialName}
                            </code>
                          </div>
                        )}
                      </div>

                      {/* Retry Action on the executing task */}
                      <button
                        onClick={() => onRetryTask(currentTask)}
                        className="shrink-0 flex items-center gap-1 px-2.5 py-1.5 rounded-lg bg-white border border-black/[0.1] hover:bg-slate-50 hover:border-black/[0.2] text-[11px] font-extrabold text-[#1A1D2E] shadow-2xs transition-all active:scale-95 cursor-pointer"
                        title={executor.id === 'video_exporter' ? '重新排入视频导出队列' : '若当前任务卡顿或异常，可中止并重新尝试执行'}
                      >
                        <RotateCcw className="w-3 h-3 text-[#1A1D2E]" />
                        <span>{executor.id === 'video_exporter' ? '重新导出' : '重试'}</span>
                      </button>
                    </div>

                    {/* Timeout Warning Message if applicable */}
                    {currentTask.isTimeout && (
                      <div className="mt-2.5 p-2 rounded-lg bg-rose-50 border border-rose-200 text-[11px] text-rose-900 leading-snug flex items-start gap-1.5">
                        <ShieldAlert className="w-3.5 h-3.5 text-rose-600 shrink-0 mt-0.5" />
                        <span>{currentTask.errorDetail || '任务运行超过常规阈值，建议核查日志或发起重试。'}</span>
                      </div>
                    )}

                    {/* Progress Bar & Stage Step */}
                    <div className="mt-3 space-y-1.5">
                      <div className="flex items-center justify-between text-[11px]">
                        <span className="text-[#64748B]">
                          {currentTask.stageInfo?.currentStage || '任务执行中'}
                          {currentTask.stageInfo && ` (${currentTask.stageInfo.stepIndex}/${currentTask.stageInfo.totalSteps})`}
                        </span>
                        <span className="font-mono font-extrabold text-[#1A1D2E]">
                          {currentTask.progress}%
                        </span>
                      </div>
                      <div className="w-full h-1.5 bg-black/[0.06] rounded-full overflow-hidden">
                        <div
                          className={`h-full transition-all duration-300 rounded-full ${
                            currentTask.isTimeout
                              ? 'bg-rose-500'
                              : 'bg-[#1A1D2E]'
                          }`}
                          style={{ width: `${currentTask.progress}%` }}
                        />
                      </div>
                    </div>
                  </div>
                ) : (
                  <div className="p-4 rounded-xl bg-slate-50 border border-dashed border-slate-200 text-center text-xs text-[#64748B]">
                    当前无执行中任务，待机就绪
                  </div>
                )}

                {/* Next in queue indicator */}
                {nextTask && (
                  <div className="flex items-center justify-between px-2.5 py-1.5 rounded-lg bg-amber-500/10 border border-amber-500/20 text-[11px] text-amber-950">
                    <span className="flex items-center gap-1 font-semibold truncate max-w-[210px]">
                      <ArrowRight className="w-3 h-3 text-amber-600 shrink-0" />
                      下一条: {nextTask.title.replace(/.*?·\s*/, '')}
                    </span>
                    <span className="text-[10px] text-amber-800 font-mono shrink-0 ml-1">
                      {nextTask.taskSubType === 'template_video_export' ? '⭐ 优先插队' : `排队 #${waitingTasks.length}`}
                    </span>
                  </div>
                )}
              </div>

              {/* Card Footer: Queue Stats Breakdown */}
              <div className="p-3.5 bg-[#F8FAFC] border-t border-black/[0.05] flex items-center justify-between text-[11px]">
                <div className="flex items-center gap-3">
                  <div>
                    <span className="text-[#64748B]">已完成 </span>
                    <strong className="font-bold text-[#1A1D2E]">{executor.queueStats.completed}</strong>
                  </div>
                  <div>
                    <span className="text-[#64748B]">进行中 </span>
                    <strong className="font-bold text-emerald-700">{executor.queueStats.running}</strong>
                  </div>
                  <div>
                    <span className="text-[#64748B]">等待中 </span>
                    <strong className="font-bold text-amber-700">{executor.queueStats.waiting}</strong>
                  </div>
                </div>

                <div className="flex items-center gap-1.5">
                  <span className="text-[#64748B]">阶段进度:</span>
                  <span className="font-bold text-[#1A1D2E] font-mono">{completedPct}%</span>
                </div>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
};
