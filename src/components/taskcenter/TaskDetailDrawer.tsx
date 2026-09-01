import React from 'react';
import { 
  X, 
  ShieldCheck, 
  RotateCcw, 
  RefreshCw, 
  Play, 
  AlertTriangle, 
  Clock, 
  FileText, 
  FolderOpen, 
  Film, 
  Sparkles, 
  Video,
  CheckCircle2,
  Bug,
  HardDrive
} from 'lucide-react';
import { TaskItem } from './taskCenterTypes';
import { getTaskCenterActions } from './taskCenterActionPolicy';
import { formatTaskDateTime } from './taskCenterFormat';
import { taskElapsedLabel } from '../../utils/duration';

interface TaskDetailDrawerProps {
  task: TaskItem | null;
  onClose: () => void;
  onRetryTask: (task: TaskItem) => void;
  onRegenerateDraft: (task: TaskItem) => void;
  onReExportVideo: (task: TaskItem) => void;
  onCleanupOrphan: (task: TaskItem) => void;
}

function exportPhaseLabel(rawStatus?: string): string {
  const labels: Record<string, string> = {
    queued: '排队中', preparing: '准备中', submitting: '提交导出',
    observing_output: '观察输出', finalizing: '验收收口', completed: '已完成',
    failed: '导出失败', timeout: '导出超时',
  };
  return labels[rawStatus || ''] || '';
}

export const TaskDetailDrawer: React.FC<TaskDetailDrawerProps> = ({
  task,
  onClose,
  onRetryTask,
  onRegenerateDraft,
  onReExportVideo,
  onCleanupOrphan,
}) => {
  if (!task) return null;

  const isRunning = task.status === 'running';
  const isTimeout = task.status === 'timeout' || task.isTimeout;
  const isDone = task.status === 'done';
  const isTemplateDraft = task.taskType === 'template_draft';
  const isVideoExport = task.taskType === 'video_export';
  const videoPhase = exportPhaseLabel(task.videoStage.rawStatus);
  const activeExecutorName = task.videoStage.rawStatus ? '视频导出器' : task.executorName;
  const allowedActions = getTaskCenterActions(task);

  return (
    <div
      className="fixed inset-0 z-60 flex items-center justify-center p-4 bg-black/60 backdrop-blur-xs animate-in fade-in duration-150"
      onClick={onClose}
    >
      <div
        className="bg-white rounded-3xl border border-black/[0.08] shadow-2xl w-full max-w-2xl max-h-[88vh] flex flex-col overflow-hidden animate-in zoom-in-95 duration-150"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Modal Header */}
        <div className="px-6 py-4 bg-[#F8FAFC] border-b border-black/[0.06] flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div
              className={`w-9 h-9 rounded-xl flex items-center justify-center font-bold text-sm shadow-xs ${
                isTimeout
                  ? 'bg-rose-500 text-white'
                  : isRunning
                  ? 'bg-emerald-500 text-white'
                  : isDone
                  ? 'bg-[#1A1D2E] text-[#DDFD00]'
                  : 'bg-amber-500 text-white'
              }`}
            >
              {isVideoExport ? (
                <Video className="w-5 h-5" />
              ) : isTemplateDraft ? (
                <Sparkles className="w-5 h-5" />
              ) : (
                <Film className="w-5 h-5" />
              )}
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h3 className="font-extrabold text-base text-[#1A1D2E]">
                  任务详情与诊断
                </h3>
                <span
                  className={`text-[11px] px-2 py-0.5 rounded-full font-bold ${
                    isTimeout
                      ? 'bg-rose-100 text-rose-800 animate-pulse'
                      : isRunning
                      ? 'bg-emerald-100 text-emerald-800'
                      : isDone
                      ? 'bg-slate-100 text-slate-700'
                      : 'bg-amber-100 text-amber-800'
                  }`}
                >
                  {isTimeout
                    ? '超时预警'
                    : isRunning
                    ? '执行中'
                    : isDone
                    ? '已完成'
                    : '排队等待'}
                </span>
              </div>
              <p className="text-[11px] text-[#64748B] mt-0.5">
                执行器: <strong className="text-[#1A1D2E]">{activeExecutorName}</strong>
                {videoPhase ? <> · 导出阶段: <strong className="text-[#1A1D2E]">{videoPhase}</strong></> : null}
                {' · '}任务ID: {task.id}
              </p>
            </div>
          </div>

          <button
            onClick={onClose}
            className="p-1.5 rounded-xl hover:bg-black/[0.05] text-slate-400 hover:text-slate-700 transition-colors cursor-pointer"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Modal Body */}
        <div className="p-6 overflow-y-auto flex-1 space-y-4 text-xs text-[#1A1D2E]">
          {/* Main Info Box */}
          <div className="p-4 rounded-2xl bg-slate-50 border border-black/[0.04] space-y-2.5">
            <h4 className="font-extrabold text-sm text-[#1A1D2E] leading-snug">
              {task.title}
            </h4>

            <div className="grid grid-cols-2 sm:grid-cols-3 gap-2.5 pt-2 border-t border-black/[0.05] text-[11px] text-[#64748B]">
              <div>
                <span>所属剧集:</span>
                <p className="font-bold text-[#1A1D2E] mt-0.5">《{task.dramaName}》</p>
              </div>
              <div>
                <span>投放账号:</span>
                <p className="font-bold text-[#1A1D2E] mt-0.5">{task.accountName}</p>
              </div>
              <div>
                <span>计划发布时间:</span>
                <p className="font-bold text-[#1A1D2E] mt-0.5">{formatTaskDateTime(task.scheduledPublishTime)}</p>
              </div>
              <div>
                <span>创建时间:</span>
                <p className="font-mono text-[#1A1D2E] mt-0.5">{formatTaskDateTime(task.createdAt)}</p>
              </div>
              <div>
                <span>开始执行时间:</span>
                <p className="font-mono text-[#1A1D2E] mt-0.5">{formatTaskDateTime(task.startedAt) || '等待调度'}</p>
              </div>
              <div>
                <span>当前/最终耗时:</span>
                <p className={`font-mono font-bold mt-0.5 ${isTimeout ? 'text-rose-700' : 'text-[#1A1D2E]'}`}>
                  {taskElapsedLabel(task.durationSeconds, task.durationFormatted)}
                </p>
              </div>
            </div>
          </div>

          {/* Warning banner if timeout */}
          {isTimeout && (
            <div className="p-3 rounded-2xl bg-rose-50 border border-rose-200 text-rose-900 space-y-1">
              <div className="flex items-center gap-1.5 font-extrabold">
                <AlertTriangle className="w-4 h-4 text-rose-600" />
                <span>任务执行超时警示</span>
              </div>
              <p className="text-[11px] leading-relaxed text-rose-800">
                {task.errorDetail || '任务运行时间异常偏长，剪映进程可能在等待文件写入或渲染卡顿，可点击右上角发起【重试】。'}
              </p>
            </div>
          )}

          {/* Priority & Scheduling Rule */}
          {task.priorityTag && (
            <div className="p-3 rounded-xl bg-amber-500/10 border border-amber-500/20 text-amber-950 flex items-center justify-between">
              <span className="font-semibold text-[11px]">调度优先级说明:</span>
              <span className="font-bold text-[11px]">{task.priorityTag}</span>
            </div>
          )}

          {/* Material & Path Details */}
          <div className="space-y-2">
            <h5 className="font-bold text-xs text-[#1A1D2E] flex items-center gap-1.5">
              <HardDrive className="w-3.5 h-3.5 text-[#64748B]" />
              文件与工程路径
            </h5>

            {task.materialName && (
              <div className="p-2.5 rounded-xl bg-[#F8FAFC] border border-black/[0.04] text-[11px] flex items-start gap-2">
                <span className="text-[#64748B] shrink-0">源素材文件:</span>
                <code className="text-[#1A1D2E] break-all font-mono">{task.materialName}</code>
              </div>
            )}

            {task.draftPath && (
              <div className="p-2.5 rounded-xl bg-[#F8FAFC] border border-black/[0.04] text-[11px] flex items-start gap-2">
                <span className="text-[#64748B] shrink-0">剪映草稿目录:</span>
                <code className="text-[#1A1D2E] break-all font-mono">{task.draftPath}</code>
              </div>
            )}

            {task.outputPath && (
              <div className="p-2.5 rounded-xl bg-[#F8FAFC] border border-black/[0.04] text-[11px] flex items-start gap-2">
                <span className="text-[#64748B] shrink-0">导出视频产物:</span>
                <code className="text-emerald-700 font-bold break-all font-mono">
                  {task.outputPath} {task.fileSizeMb ? `(${task.fileSizeMb}MB)` : ''}
                </code>
              </div>
            )}
          </div>

          {/* Pipeline Stage Diagnostic Log */}
          <div className="space-y-1.5">
            <h5 className="font-bold text-xs text-[#1A1D2E] flex items-center gap-1.5">
              <Bug className="w-3.5 h-3.5 text-[#64748B]" />
              执行器底层诊断日志 (IPC &amp; Pipeline Trace)
            </h5>
            <pre className="p-3.5 rounded-2xl bg-[#1A1D2E] text-[#DDFD00] font-mono text-[11px] overflow-x-auto whitespace-pre-wrap leading-relaxed">
              {task.diagnosticLog || 'Executor IPC initialized. No fatal errors recorded.'}
            </pre>
          </div>
        </div>

        {/* Modal Footer with Contextual Actions */}
        <div className="px-6 py-3.5 bg-[#F8FAFC] border-t border-black/[0.06] flex items-center justify-between gap-3">
          <span className="text-[11px] text-[#64748B]">
            剪映自动化服务：监听端口 49152
          </span>

          <div className="flex items-center gap-2">
            {task.isOrphan && (
              <button
                onClick={() => onCleanupOrphan(task)}
                className="flex items-center gap-1.5 px-3 py-1.5 rounded-xl bg-rose-50 border border-rose-200 hover:bg-rose-100 text-xs font-bold text-rose-800 transition-all cursor-pointer"
                title="清理所属生产任务已不存在的异常记录"
              >
                <AlertTriangle className="w-3.5 h-3.5" />
                <span>清理异常记录</span>
              </button>
            )}
            {/* Retry: only if running or timeout */}
            {allowedActions.includes('retry') && (
              <button
                onClick={() => {
                  onRetryTask(task);
                  onClose();
                }}
                className="flex items-center gap-1.5 px-3 py-1.5 rounded-xl bg-white border border-black/[0.1] hover:bg-slate-50 text-xs font-bold text-[#1A1D2E] shadow-2xs transition-all cursor-pointer"
                title="中止当前执行并重新尝试执行"
              >
                <RotateCcw className="w-3.5 h-3.5 text-[#1A1D2E]" />
                <span>重试当前任务</span>
              </button>
            )}

            {/* Regenerate: template draft */}
            {allowedActions.includes('regenerate') && (
              <button
                onClick={() => {
                  onRegenerateDraft(task);
                  onClose();
                }}
                className="flex items-center gap-1.5 px-3 py-1.5 rounded-xl bg-slate-100 hover:bg-slate-200 text-xs font-bold text-slate-800 transition-all cursor-pointer"
                title="重新制作模板草稿内容（重新切片分镜）"
              >
                <RefreshCw className="w-3.5 h-3.5" />
                <span>重新生成草稿</span>
              </button>
            )}

            {/* Re-export: video export or finished draft */}
            {allowedActions.includes('reExport') && (
              <button
                onClick={() => {
                  onReExportVideo(task);
                  onClose();
                }}
                className="flex items-center gap-1.5 px-3 py-1.5 rounded-xl bg-white border border-black/[0.1] hover:bg-slate-50 text-xs font-bold text-slate-800 transition-all cursor-pointer"
                title="保留现有草稿，仅重新从剪映导出视频"
              >
                <Video className="w-3.5 h-3.5" />
                <span>重新导出视频</span>
              </button>
            )}

            <button
              onClick={onClose}
              className="px-4 py-1.5 rounded-xl bg-[#1A1D2E] text-[#DDFD00] text-xs font-bold hover:bg-black transition-all cursor-pointer"
            >
              关闭
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};
