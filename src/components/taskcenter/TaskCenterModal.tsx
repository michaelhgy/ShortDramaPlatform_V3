import React, { useEffect, useMemo, useRef, useState } from 'react';
import { 
  Zap, 
  X, 
  RotateCcw, 
  Play, 
  Pause, 
  CheckCircle2, 
  AlertTriangle, 
  Clock, 
  Video, 
  Film, 
  Sparkles, 
  SlidersHorizontal,
  Maximize2,
  Minimize2,
  RefreshCw,
  Layers,
  Activity
} from 'lucide-react';
import { TaskItem, ExecutorInfo } from './taskCenterTypes';
import { INITIAL_EXECUTORS } from './taskCenterMockData';
import { INITIAL_PREVIEW_TASKS } from './taskCenterPreviewData';
import { ExecutorsOverview } from './ExecutorsOverview';
import { TaskListSection } from './TaskListSection';
import { TaskDetailDrawer } from './TaskDetailDrawer';
import { getCachedTaskCenterSnapshot, loadSharedTaskCenter, storeSharedTaskCenterSnapshot } from '../../services/taskCenterService';
import { cleanupV2OrphanTask, regenerateV2Template, reorderV2ProductionUnit, retryV2Template, reExportV2Task, setV2ExecutorPaused, setV2TaskCenterPaused } from '../../api/v2TaskCenter';
import { dataSource } from '../../services/dataSource';
import { useDataArea } from '../../hooks/useDataArea';

interface TaskCenterModalProps {
  isOpen: boolean;
  onClose: () => void;
  showToast: (msg: string) => void;
}

export const TaskCenterModal: React.FC<TaskCenterModalProps> = ({
  isOpen,
  onClose,
  showToast,
}) => {
  const cachedSnapshot = getCachedTaskCenterSnapshot();
  const [executors, setExecutors] = useState<ExecutorInfo[]>(dataSource === 'mock' ? INITIAL_EXECUTORS : (cachedSnapshot?.executors || []));
  const [tasks, setTasks] = useState<TaskItem[]>(dataSource === 'mock' ? INITIAL_PREVIEW_TASKS : (cachedSnapshot?.tasks || []));
  const [isQueuePaused, setIsQueuePaused] = useState(false);
  const [lastRefreshAt, setLastRefreshAt] = useState<Date | null>(() => {
    try { const value = localStorage.getItem('v2-task-center-snapshot-v1:updated-at'); return value ? new Date(value) : null; } catch { return null; }
  });
  const [selectedTaskForDetail, setSelectedTaskForDetail] = useState<TaskItem | null>(null);
  const [isFullscreen, setIsFullscreen] = useState(false);
  const [retryConfirmTask, setRetryConfirmTask] = useState<TaskItem | null>(null);
  const [orphanCleanupTask, setOrphanCleanupTask] = useState<TaskItem | null>(null);
  const [clockNow, setClockNow] = useState(() => Date.now());
  const tasksRef = useRef<TaskItem[]>([]);

  // Durations are display-only: the backend supplies started/completed times,
  // while this lightweight clock keeps active timers ticking without polling.
  useEffect(() => {
    if (!isOpen) return;
    const timer = window.setInterval(() => setClockNow(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, [isOpen]);

  const liveTasks = useMemo(() => tasks.map((task) => {
    if (!task.startedAt || task.completedAt || task.status !== 'running') return task;
    const started = Date.parse(task.startedAt);
    if (!Number.isFinite(started)) return task;
    return { ...task, durationSeconds: Math.max(0, Math.floor((clockNow - started) / 1000)) };
  }), [tasks, clockNow]);

  const liveExecutors = useMemo(() => executors.map((executor) => {
    const task = liveTasks.find((item) => item.id === executor.currentTaskId);
    if (!task || !task.startedAt || executor.status !== 'running') return executor;
    const started = Date.parse(task.startedAt);
    return Number.isFinite(started) ? { ...executor, runningSeconds: Math.max(0, Math.floor((clockNow - started) / 1000)) } : executor;
  }), [executors, liveTasks, clockNow]);

  // ── 统一数据层接入（刷新大修 · 第 2 步）──────────────────────────────
  // 与顶栏、生产中心**共用同一份任务快照**（数据层每 3 秒统一拉一次），
  // 不再各自 loadSharedTaskCenter + 各自订阅变更事件 —— 那正是三处数字偶尔对不上的原因。
  // 「更新于」改用数据层的 updatedAt：只在成功时前进，不会再显示上次会话的时间。
  const taskCenterArea = useDataArea<Awaited<ReturnType<typeof loadSharedTaskCenter>>>(
    'taskCenter',
    () => loadSharedTaskCenter(true),
  );

  useEffect(() => {
    if (dataSource === 'mock') return;
    const snapshot = taskCenterArea.data;
    if (!snapshot) return;
    setExecutors(snapshot.executors);
    tasksRef.current = snapshot.tasks;
    setTasks(snapshot.tasks);
    setLastRefreshAt(taskCenterArea.updatedAt ? new Date(taskCenterArea.updatedAt) : null);
    if (typeof snapshot.isQueuePaused === 'boolean') setIsQueuePaused(snapshot.isQueuePaused);
  }, [taskCenterArea.data, taskCenterArea.updatedAt]);

  if (!isOpen) return null;

  // Calculate high-level KPIs across the 3 independent stages
  const totalTasksCount = tasks.length;
  const runningTasksCount = tasks.filter(t => t.status === 'running').length;
  const timeoutTasksCount = tasks.filter(t => t.isTimeout || t.status === 'timeout').length;
  const waitingTasksCount = tasks.filter(t => t.status === 'waiting').length;
  const doneTasksCount = tasks.filter(t => t.status === 'done').length;
  const retryIsVideoExport = retryConfirmTask?.executorId === 'video_exporter' || retryConfirmTask?.taskType === 'video_export' || ['error', 'timeout'].includes(retryConfirmTask?.videoStage?.status || '');

  // Action 1: 重试 (Retry) -> 先确认，再针对当前任务重新执行
  const executeRetryTask = (task: TaskItem) => {
    if (dataSource !== 'mock') {
      const retryRequest = task.executorId === 'video_exporter' || task.taskType === 'video_export' || ['error', 'timeout'].includes(task.videoStage?.status || '')
        ? reExportV2Task(task.videoExportTaskId || task.id)
        : retryV2Template(task.id);
      retryRequest.then(() => {
        showToast(`⚡ [重试] 已停止并重新排队：《${task.title}》`);
        return loadSharedTaskCenter(true);
      }).then((snapshot) => {
        setExecutors(snapshot.executors); setTasks(snapshot.tasks);
      }).catch((error: unknown) => showToast(error instanceof Error ? error.message : '任务重新执行失败，请稍后重试。'));
      setRetryConfirmTask(null);
      return;
    }
    setTasks(prev =>
      prev.map(t => {
        if (t.id === task.id) {
          return {
            ...t,
            status: 'running',
            isTimeout: false,
            durationSeconds: 1,
            durationFormatted: '01秒 (已重试重启)',
            progress: 10,
            diagnosticLog: `[${new Date().toLocaleTimeString()}] User triggered [RETRY]. Process aborted and cleanly re-spawned.\n` + (t.diagnosticLog || ''),
          };
        }
        return t;
      })
    );

    // Also update executor timeout status
    setExecutors(prev =>
      prev.map(exec => {
        if (exec.id === task.executorId) {
          return {
            ...exec,
            isTimeout: false,
            runningSeconds: 1,
            queueStats: {
              ...exec.queueStats,
              timeoutCount: 0,
            },
          };
        }
        return exec;
      })
    );

    showToast(`⚡ [重试] 已中止并重新启动任务：《${task.title}》`);
    setRetryConfirmTask(null);
  };

  const handleRetryTask = (task: TaskItem) => {
    setRetryConfirmTask(task);
  };

  const executeOrphanCleanup = (task: TaskItem) => {
    cleanupV2OrphanTask(task.id).then(() => {
      showToast('异常任务记录已清理');
      return loadSharedTaskCenter(true);
    }).then((snapshot) => {
      setExecutors(snapshot.executors); setTasks(snapshot.tasks);
      setSelectedTaskForDetail(null);
    }).catch((error: unknown) => showToast(error instanceof Error ? error.message : '异常记录清理失败，请稍后重试。'));
    setOrphanCleanupTask(null);
  };

  // Action 2: 重新生成 (Regenerate) -> 仅针对模板草稿
  const handleRegenerateDraft = (task: TaskItem) => {
    if (dataSource !== 'mock') {
      regenerateV2Template(task.id).then(() => {
        showToast(`模板已重新排入队列：《${task.dramaName}》`);
      return loadSharedTaskCenter(true);
      }).then((snapshot) => {
        setExecutors(snapshot.executors); setTasks(snapshot.tasks);
      }).catch((error: unknown) => showToast(error instanceof Error ? error.message : '模板重新生成失败，请稍后重试。'));
      return;
    }
    setTasks(prev => prev.map(current => current.id === task.id ? {
      ...current,
      status: 'waiting',
      progress: 0,
      isTimeout: false,
      durationSeconds: 0,
      durationFormatted: '排队等待重新生成',
      draftStage: {
        ...current.draftStage,
        status: 'waiting',
        progress: 0,
        errorDetail: undefined,
      },
      videoStage: {
        ...current.videoStage,
        status: 'idle',
        progress: 0,
        errorDetail: undefined,
      },
      priorityTag: '⭐ 模板重新生成队列',
    } : current));
    showToast(`🔄 [重新生成] 已将原模板任务重新排入模板生成器队列`);
  };

  // Action 3: 重新导出 (Re-export) -> 针对模板或成片重新走剪映导出
  const handleReExportVideo = (task: TaskItem) => {
    if (dataSource !== 'mock') {
      reExportV2Task(task.videoExportTaskId || task.id).then(() => loadSharedTaskCenter(true)).then((snapshot) => {
        setExecutors(snapshot.executors); setTasks(snapshot.tasks);
        showToast(`视频已重新排入导出队列：《${task.dramaName}》`);
      }).catch((error: unknown) => showToast(error instanceof Error ? error.message : '重新导出失败，请稍后重试。'));
      return;
    }
    const isTemplate = task.taskCategory === 'template';
    setTasks(prev => prev.map(current => current.id === task.id ? {
      ...current,
      status: 'waiting',
      progress: 0,
      isTimeout: false,
      durationSeconds: 0,
      durationFormatted: isTemplate ? '排队等待模板导出' : '排队等待成片导出',
      videoStage: {
        ...current.videoStage,
        status: 'waiting',
        progress: 0,
        errorDetail: undefined,
      },
      executorId: 'video_exporter',
      executorName: '视频导出器',
      priorityTag: isTemplate
        ? '⭐ 模板最高导出优先权 · 下一条出库'
        : current.priorityTag,
    } : current));
    showToast(`📤 [重新导出] 已保留原任务卡和草稿，重新排入视频导出器队列`);
  };

  // Action 4: 队列暂停/继续控制
  const handleToggleQueue = () => {
    const next = !isQueuePaused;
    setIsQueuePaused(next);
    if (dataSource !== 'mock') {
      setV2TaskCenterPaused(next).then((snapshot) => {
        storeSharedTaskCenterSnapshot(snapshot);
        setExecutors(snapshot.executors);
        setTasks(snapshot.tasks);
      }).catch(() => {
        setIsQueuePaused(!next);
        showToast('任务中心状态更新失败，请检查 V2 服务是否启动');
      });
    }
    showToast(next ? '⏸️ 全局后台执行队列已暂停' : '▶️ 全局后台执行队列已恢复调度');
  };

  // 手动调整生产顺序：后端把"手动位次"和"三个执行器的取任务顺序"算成同一个东西，
  // 所以这里只要把动作发过去、把回来的顺序落进界面即可，前端不再自己排序。
  const handleReorderUnit = (productionTaskId: string, action: 'top' | 'up' | 'down') => {
    if (dataSource === 'mock') {
      showToast('Mock 模式下不调整顺序');
      return;
    }
    reorderV2ProductionUnit(productionTaskId, action)
      .then(() => loadSharedTaskCenter(true))
      .then((snapshot) => {
        setTasks(snapshot.tasks);
        setExecutors(snapshot.executors);
      })
      .then(() => showToast(action === 'top' ? '已置顶 —— 执行器下一个就做这部剧' : action === 'up' ? '已上移一位' : '已下移一位'))
      .catch((error: unknown) => showToast(error instanceof Error ? error.message : '顺序调整失败，请稍后重试。'));
  };

  const handleToggleExecutor = (executor: ExecutorInfo) => {
    const shouldPause = executor.status !== 'manual_paused' && executor.status !== 'error_paused';
    setV2ExecutorPaused(executor.id, shouldPause).then((snapshot) => {
      storeSharedTaskCenterSnapshot(snapshot);
      setExecutors(snapshot.executors);
      setTasks(snapshot.tasks);
      showToast(shouldPause ? `${executor.name} 已请求暂停，当前任务结束后生效` : `${executor.name} 已恢复运行`);
    }).catch((error: unknown) => showToast(error instanceof Error ? error.message : '执行器状态更新失败，请稍后重试。'));
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-2 sm:p-4 bg-black/50 backdrop-blur-xs animate-in fade-in duration-150">
      <div
        className={`bg-[#F8FAFC] rounded-3xl border border-black/[0.08] shadow-2xl w-full flex flex-col overflow-hidden transition-all duration-200 ${
          isFullscreen
            ? 'h-full max-w-full rounded-none'
            : 'max-w-6xl max-h-[92vh]'
        }`}
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header Section */}
        <div className="px-6 py-4 bg-white border-b border-black/[0.06] flex items-center justify-between shrink-0">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-2xl bg-[#1A1D2E] text-[#DDFD00] flex items-center justify-center font-bold shadow-xs">
              <Zap className="w-5 h-5" />
            </div>
            <div>
              <div className="flex items-center gap-2 flex-wrap">
                <h2 className="font-extrabold text-base text-[#1A1D2E]">
                  全局任务中心 (Full Task Center)
                </h2>
                <span className="text-xs px-2 py-0.5 rounded-full bg-[#1A1D2E] text-[#DDFD00] font-bold">
                  3大执行器 · 剧集优先级调度 · 异常自愈
                </span>
                {timeoutTasksCount > 0 && (
                  <span className="text-xs px-2.5 py-0.5 rounded-full bg-rose-500 text-white font-extrabold animate-pulse">
                    ⚠️ {timeoutTasksCount} 个任务超时
                  </span>
                )}
              </div>
              <p className="text-[11px] text-[#64748B] mt-0.5">
                实时把控视频导出器、成片生成器、模板生成器运行状态与整体生产节奏{lastRefreshAt && <span className="ml-2 text-slate-400">更新于 {lastRefreshAt.toLocaleTimeString('zh-CN')}</span>}
              </p>
            </div>
          </div>

          {/* Top Actions: Pause Queue, Fullscreen Toggle, Close */}
          <div className="flex items-center gap-2">
            <button
              onClick={handleToggleQueue}
              className={`flex items-center gap-1.5 px-3 py-1.5 rounded-xl text-xs font-bold transition-all cursor-pointer ${
                isQueuePaused
                  ? 'bg-amber-500 text-white shadow-xs'
                  : 'bg-slate-100 hover:bg-slate-200 text-[#1A1D2E]'
              }`}
            >
              {isQueuePaused ? <Play className="w-3.5 h-3.5 fill-white" /> : <Pause className="w-3.5 h-3.5" />}
              <span>{isQueuePaused ? '恢复执行队列' : '暂停执行队列'}</span>
            </button>

            <button
              onClick={() => setIsFullscreen(!isFullscreen)}
              className="p-2 rounded-xl text-slate-400 hover:text-slate-700 hover:bg-black/[0.04] transition-colors cursor-pointer"
              title={isFullscreen ? '还原窗口' : '全屏展开'}
            >
              {isFullscreen ? <Minimize2 className="w-4 h-4" /> : <Maximize2 className="w-4 h-4" />}
            </button>

            <button
              onClick={onClose}
              className="p-2 rounded-xl text-slate-400 hover:text-slate-700 hover:bg-black/[0.04] transition-colors cursor-pointer"
              title="关闭"
            >
              <X className="w-5 h-5" />
            </button>
          </div>
        </div>

        {/* Global Pipeline Health Ticker Bar */}
        <div className="px-6 py-2.5 bg-slate-100/70 border-b border-black/[0.04] flex flex-wrap items-center justify-between gap-3 text-xs shrink-0">
          <div className="flex items-center gap-4 flex-wrap">
            <div className="flex items-center gap-1.5">
              <span className="w-2 h-2 rounded-full bg-emerald-500" />
              <span className="text-[#64748B]">正在执行:</span>
              <strong className="text-emerald-700 font-extrabold">{runningTasksCount} 个</strong>
            </div>

            <div className="flex items-center gap-1.5">
              <span className="w-2 h-2 rounded-full bg-amber-500" />
              <span className="text-[#64748B]">排队等待:</span>
              <strong className="text-amber-700 font-extrabold">{waitingTasksCount} 个</strong>
            </div>

            <div className="flex items-center gap-1.5">
              <span className="w-2 h-2 rounded-full bg-slate-400" />
              <span className="text-[#64748B]">今日已完成:</span>
              <strong className="text-[#1A1D2E] font-extrabold">{doneTasksCount} 个</strong>
            </div>

            {timeoutTasksCount > 0 && (
              <div className="flex items-center gap-1.5 bg-rose-100 px-2 py-0.5 rounded-lg border border-rose-200">
                <span className="w-2 h-2 rounded-full bg-rose-500 animate-ping" />
                <span className="text-rose-900 font-bold">异常超时:</span>
                <strong className="text-rose-900 font-extrabold">{timeoutTasksCount} 个</strong>
              </div>
            )}
          </div>

          {/* 这里原来写死"剪映 IPC 通信：在线 (端口 49152)"——永远绿色、跟真实状态无关，已删除。
             保留下来的"调度算法"是真实配置（不是状态），所以留着。 */}
          <div className="text-[11px] text-[#64748B] flex items-center gap-3">
            <span>调度算法：<strong className="text-[#1A1D2E]">动态剧集优先级 + 模板最高优先</strong></span>
          </div>
        </div>

        {/* Modal Scrollable Content */}
        <div className="p-6 overflow-y-auto flex-1 space-y-6">
          {/* Section 1: Three Independent Executors (Top Core) */}
          <ExecutorsOverview
            executors={liveExecutors}
            tasks={liveTasks}
            onRetryTask={handleRetryTask}
            onViewTaskDetail={(task) => setSelectedTaskForDetail(task)}
            onToggleExecutor={handleToggleExecutor}
          />

          {/* 原来这里有一块「今日账号×剧集动态生产优先级调度」卡片横幅。
              用户 2026-09-19 拍板：它的功能并进下面的任务列表（账号×剧集分组 + 组头名次），
              独立横幅取消 —— 同一件事显示两遍正是"看着很累"的来源。 */}

          {/* Section 2: Task List Section（账号 × 剧集优先级分组） */}
          <TaskListSection
            tasks={liveTasks}
            onRetryTask={handleRetryTask}
            onRegenerateDraft={handleRegenerateDraft}
            onReExportVideo={handleReExportVideo}
            onViewTaskDetail={(task) => setSelectedTaskForDetail(task)}
            onReorderUnit={handleReorderUnit}
          />
        </div>

        {/* Footer */}
        {/* 这里原来写死"三个执行器：就绪"——即使执行器报错暂停也照样显示绿色，与上面的真实状态自相矛盾。
            真实的执行器状态就在 ExecutorsOverview 里，所以直接删掉。 */}
        <div className="px-6 py-3.5 bg-white border-t border-black/[0.06] flex items-center justify-end text-xs text-[#64748B] shrink-0">
          <div className="flex items-center gap-2">
            <button
              onClick={onClose}
              className="px-4 py-1.5 rounded-xl bg-[#1A1D2E] text-[#DDFD00] text-xs font-bold hover:bg-black transition-all cursor-pointer shadow-xs"
            >
              完成查看
            </button>
          </div>
        </div>
      </div>

      {/* Task Diagnostic & Deep Detail Drawer Modal */}
      <TaskDetailDrawer
        task={selectedTaskForDetail}
        onClose={() => setSelectedTaskForDetail(null)}
        onRetryTask={handleRetryTask}
        onRegenerateDraft={handleRegenerateDraft}
        onReExportVideo={handleReExportVideo}
        onCleanupOrphan={(task) => setOrphanCleanupTask(task)}
      />

      {retryConfirmTask && (
        <div
          className="fixed inset-0 z-[60] flex items-center justify-center p-4 bg-black/50 backdrop-blur-xs animate-in fade-in duration-150"
          role="presentation"
          onClick={() => setRetryConfirmTask(null)}
        >
          <div
            className="w-full max-w-md rounded-2xl border border-black/[0.08] bg-white shadow-2xl overflow-hidden animate-in zoom-in-95 duration-150"
            role="dialog"
            aria-modal="true"
            aria-labelledby="retry-confirm-title"
            onClick={(event) => event.stopPropagation()}
          >
            <div className="px-5 py-4 border-b border-black/[0.06] flex items-start gap-3">
              <div className="w-9 h-9 rounded-xl bg-rose-50 text-rose-600 flex items-center justify-center shrink-0">
                <AlertTriangle className="w-4.5 h-4.5" />
              </div>
              <div className="min-w-0">
                <h3 id="retry-confirm-title" className="text-sm font-extrabold text-[#1A1D2E]">
                  {retryIsVideoExport ? '确认重新导出视频？' : '确认重新执行任务？'}
                </h3>
                <p className="mt-1 text-xs leading-5 text-[#64748B] break-words">
                  {retryIsVideoExport ? '将保留现有草稿，并重新排入视频导出队列：' : '将结束当前异常任务并重新执行：'}{retryConfirmTask.title}
                </p>
              </div>
              <button
                type="button"
                onClick={() => setRetryConfirmTask(null)}
                className="ml-auto p-1.5 rounded-lg text-slate-400 hover:text-slate-700 hover:bg-black/[0.04] transition-colors cursor-pointer"
                title="关闭"
                aria-label="关闭确认窗口"
              >
                <X className="w-4 h-4" />
              </button>
            </div>
            <div className="px-5 py-3.5 bg-slate-50/70 flex items-center justify-end gap-2">
              <button
                type="button"
                onClick={() => setRetryConfirmTask(null)}
                className="px-3.5 py-1.5 rounded-xl border border-black/[0.08] bg-white text-[#64748B] text-xs font-bold hover:bg-slate-100 transition-colors cursor-pointer"
              >
                取消
              </button>
              <button
                type="button"
                onClick={() => executeRetryTask(retryConfirmTask)}
                className="px-3.5 py-1.5 rounded-xl bg-[#1A1D2E] text-[#DDFD00] text-xs font-bold hover:bg-black transition-all cursor-pointer shadow-xs"
              >
                {retryIsVideoExport ? '确认重新导出' : '确认重试'}
              </button>
            </div>
          </div>
        </div>
      )}
      {orphanCleanupTask && (
        <div className="fixed inset-0 z-[60] flex items-center justify-center p-4 bg-black/50 backdrop-blur-xs animate-in fade-in duration-150" role="presentation" onClick={() => setOrphanCleanupTask(null)}>
          <div className="w-full max-w-md rounded-2xl border border-black/[0.08] bg-white shadow-2xl overflow-hidden animate-in zoom-in-95 duration-150" role="dialog" aria-modal="true" onClick={(event) => event.stopPropagation()}>
            <div className="px-5 py-4 border-b border-black/[0.06] flex items-start gap-3">
              <div className="w-9 h-9 rounded-xl bg-rose-50 text-rose-600 flex items-center justify-center shrink-0"><AlertTriangle className="w-4 h-4" /></div>
              <div><h3 className="text-sm font-extrabold text-[#1A1D2E]">确认清理异常记录？</h3><p className="mt-1 text-xs leading-5 text-[#64748B]">该记录所属生产任务已不存在，将从任务中心移除。</p></div>
            </div>
            <div className="px-5 py-3.5 bg-slate-50/70 flex justify-end gap-2">
              <button type="button" onClick={() => setOrphanCleanupTask(null)} className="px-3.5 py-1.5 rounded-xl border border-black/[0.08] bg-white text-[#64748B] text-xs font-bold hover:bg-slate-100 cursor-pointer">取消</button>
              <button type="button" onClick={() => executeOrphanCleanup(orphanCleanupTask)} className="px-3.5 py-1.5 rounded-xl bg-[#1A1D2E] text-[#DDFD00] text-xs font-bold hover:bg-black cursor-pointer">确认清理</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
