import React, { useEffect, useRef, useState } from 'react';
import { NavTab, TaskCenterTask } from '../types';
import { 
  Tv2, 
  Layers, 
  BarChart3, 
  FolderGit2, 
  SlidersHorizontal,
  Settings, 
  Zap, 
  Sparkles, 
  AlertTriangle
} from 'lucide-react';
import { TaskCenterPreviewPopover } from './taskcenter/TaskCenterPreviewPopover';
import { ExecutorId, ExecutorInfo, TaskItem } from './taskcenter/taskCenterTypes';
import { regenerateV2Template, reExportV2Task, retryV2Template, setV2ExecutorPaused, setV2TaskCenterPaused } from '../api/v2TaskCenter';
import { getCachedTaskCenterSnapshot, loadSharedTaskCenter, refreshSharedTaskCenterProductionTask, storeSharedTaskCenterSnapshot } from '../services/taskCenterService';
import { getTaskCenterActions } from './taskcenter/taskCenterActionPolicy';
import { changeAffects, eventDetail } from '../services/dataChangeEvents';
import { subscribeV2DataRefresh } from '../services/dataRefreshCoordinator';
import { dataSource } from '../services/dataSource';
import { getV2Accounts, getV2ProductionResources } from '../api/v2Catalog';
import { listV2ProductionTaskSummaries } from '../api/v2Production';
import { loadV2DailyAccountRevenueSummary } from '../api/v2Revenue';
import { calculateResourceMetrics } from '../utils/resourceMetrics';

interface HeaderProps {
  activeTab: NavTab;
  onTabChange: (tab: NavTab) => void;
  taskQueue: TaskCenterTask[];
  onOpenSettings: () => void;
  onQuickSchedule: () => void;
  workbenchMode?: 'standard' | 'explore';
  onWorkbenchModeChange?: (mode: 'standard' | 'explore') => void;
  onOpenTaskCenterModal?: () => void;
  showToast?: (msg: string) => void;
}

export const Header: React.FC<HeaderProps> = ({
  activeTab,
  onTabChange,
  taskQueue: _taskQueue,
  onOpenSettings,
  onQuickSchedule,
  workbenchMode = 'explore',
  onWorkbenchModeChange,
  onOpenTaskCenterModal,
  showToast = (_msg: string) => {},
}) => {
  const [showTaskCenter, setShowTaskCenter] = useState(false);
  const [tasks, setTasks] = useState<TaskItem[]>(() => getCachedTaskCenterSnapshot()?.tasks || []);
  const [executors, setExecutors] = useState<ExecutorInfo[]>(() => getCachedTaskCenterSnapshot()?.executors || []);
  const [isQueuePaused, setIsQueuePaused] = useState(() => getCachedTaskCenterSnapshot()?.isQueuePaused === true);
  const [isQueuePauseUpdating, setIsQueuePauseUpdating] = useState(false);
  const [executorUpdatingId, setExecutorUpdatingId] = useState<ExecutorId | null>(null);
  const [yesterdayRevenue, setYesterdayRevenue] = useState<{ amount: number; incompleteCount: number } | null>(null);
  const [supportableDramas, setSupportableDramas] = useState<number | null>(null);
  const [accountArrangement, setAccountArrangement] = useState<{ arranged: number; total: number } | null>(null);
  const tasksRef = useRef<TaskItem[]>([]);
  const resourceRefreshAtRef = useRef(0);

  useEffect(() => {
    let active = true;
    const localDate = (offsetDays: number) => {
      const value = new Date();
      value.setDate(value.getDate() + offsetDays);
      const offset = value.getTimezoneOffset() * 60_000;
      return new Date(value.getTime() - offset).toISOString().slice(0, 10);
    };
    const refreshRevenue = () => void loadV2DailyAccountRevenueSummary(localDate(-1)).then((summary) => {
      if (!active) return;
      const completed = summary.items.filter((item) => item.collection_status === 'success');
      setYesterdayRevenue({
        amount: completed.reduce((sum, item) => sum + Number(item.amount || 0), 0),
        incompleteCount: summary.items.filter((item) => item.collection_status === 'uncollected' || item.collection_status === 'failed').length,
      });
    }).catch(() => undefined);
    const refreshResources = () => {
      // Resource scanning refreshes its metadata index, which in turn emits a
      // resource event. Debounce that self-originated event so the header does
      // not create a scan loop while still picking up later real changes.
      if (Date.now() - resourceRefreshAtRef.current < 10_000) return;
      resourceRefreshAtRef.current = Date.now();
      void getV2ProductionResources().then((response) => {
        if (active) setSupportableDramas(calculateResourceMetrics(response.items).supportableDramas);
      }).catch(() => undefined);
    };
    const refreshAccountArrangement = () => void Promise.all([getV2Accounts(), listV2ProductionTaskSummaries()]).then(([accounts, tasks]) => {
      if (!active) return;
      const normalAccounts = accounts.items.filter((account) => account.status === '正常');
      const normalNames = new Set(normalAccounts.map((account) => account.nickname));
      const arrangedNames = new Set(tasks.items
        .filter((task) => task.created_date === localDate(0) && normalNames.has(task.account_name))
        .map((task) => task.account_name));
      setAccountArrangement({ arranged: arrangedNames.size, total: normalAccounts.length });
    }).catch(() => undefined);
    refreshRevenue();
    refreshResources();
    refreshAccountArrangement();
    const onDataChanged = (event: Event) => {
      const detail = eventDetail(event);
      if (detail.changeType === 'revenue_changed') refreshRevenue();
      if (detail.changeType === 'resource_changed') refreshResources();
      if (detail.changeType === 'account_changed' || detail.changeType === 'production_task_changed') refreshAccountArrangement();
    };
    window.addEventListener('v2-data-changed', onDataChanged);
    return () => { active = false; window.removeEventListener('v2-data-changed', onDataChanged); };
  }, []);

  useEffect(() => {
    let active = true;
    const refresh = () => loadSharedTaskCenter(true).then((snapshot) => {
      if (active) {
        tasksRef.current = snapshot.tasks;
        setTasks(snapshot.tasks);
        setExecutors(snapshot.executors);
        setIsQueuePaused(snapshot.isQueuePaused === true);
      }
    }).catch(() => {
      // Keep the last confirmed snapshot; the header must not create a toast
      // every second while the local service is restarting.
    });
    refresh();
    const refreshForChange = async (detail?: import('../services/dataChangeEvents').V2DataChangeDetail) => {
      if (detail?.productionTaskId) {
        await refreshSharedTaskCenterProductionTask(detail.productionTaskId).then((changed) => {
          if (!active) return;
          setTasks((previous) => [...previous.filter((item) => item.productionTaskId !== detail.productionTaskId), ...changed]);
          tasksRef.current = [...tasksRef.current.filter((item) => item.productionTaskId !== detail.productionTaskId), ...changed];
        });
      } else { await refresh(); }
    };
    const unsubscribe = subscribeV2DataRefresh('task_center', ({ detail }) => refreshForChange(detail).catch(() => undefined));
    return () => { active = false; unsubscribe(); };
  }, []);

  // Counts come from the backend snapshot. The header never turns a task into
  // a running task locally, because the executor is the source of truth.
  const runningTasksCount = tasks.filter(t => t.status === 'running').length;
  const timeoutTasksCount = tasks.filter(t => t.isTimeout || t.status === 'timeout').length;
  const errorTasksCount = tasks.filter(t => t.status === 'error').length;
  const abnormalTasksCount = timeoutTasksCount + errorTasksCount;
  // Keep the header aligned with the task-center ticker: these are task
  // statuses, not a second progress calculation across executor queues.
  const waitingTasksCount = tasks.filter(t => t.status === 'waiting').length;
  const doneTasksCount = tasks.filter(t => t.status === 'done').length;
  const accountUnarrangedCount = accountArrangement ? Math.max(0, accountArrangement.total - accountArrangement.arranged) : 0;
  const formattedYesterdayRevenue = yesterdayRevenue
    ? new Intl.NumberFormat('zh-CN', { minimumFractionDigits: 0, maximumFractionDigits: 2 }).format(yesterdayRevenue.amount)
    : '';

  const handleTaskAction = async (task: TaskItem) => {
    const action = getTaskCenterActions(task)[0] || 'retry';
    try {
      if (action === 'regenerate') await regenerateV2Template(task.id);
      else if (action === 'reExport' || task.executorId === 'video_exporter' || task.taskType === 'video_export' || ['error', 'timeout'].includes(task.videoStage?.status || '')) {
        // 视频导出器上的“重试”实际是重新导出，必须使用导出尝试编号。
        await reExportV2Task(task.videoExportTaskId || task.id);
      }
      else await retryV2Template(task.id);
      const snapshot = await loadSharedTaskCenter(true);
      setTasks(snapshot.tasks);
    } catch (error) {
      showToast(error instanceof Error ? error.message : '任务操作失败，请稍后重试。');
    }
  };

  const handleToggleQueuePause = async () => {
    if (isQueuePauseUpdating) return;
    const nextPaused = !isQueuePaused;
    setIsQueuePauseUpdating(true);
    try {
      if (dataSource === 'mock') {
        setIsQueuePaused(nextPaused);
        return;
      }
      const snapshot = await setV2TaskCenterPaused(nextPaused);
      storeSharedTaskCenterSnapshot(snapshot);
      tasksRef.current = snapshot.tasks;
      setTasks(snapshot.tasks);
      setExecutors(snapshot.executors);
      setIsQueuePaused(snapshot.isQueuePaused === true);
      showToast(nextPaused ? '后台执行队列已暂停：正在执行的任务不会被强行中断。' : '后台执行队列已继续：三个执行器会按原规则领取下一项任务。');
    } catch (error) {
      showToast(error instanceof Error ? error.message : '队列状态更新失败，请检查 V2 服务是否正常运行。');
    } finally {
      setIsQueuePauseUpdating(false);
    }
  };

  const handleToggleExecutor = async (executor: ExecutorInfo) => {
    if (executorUpdatingId || executor.status === 'pausing') return;
    const shouldPause = executor.status !== 'manual_paused' && executor.status !== 'error_paused';
    setExecutorUpdatingId(executor.id);
    try {
      if (dataSource === 'mock') return;
      const snapshot = await setV2ExecutorPaused(executor.id, shouldPause);
      storeSharedTaskCenterSnapshot(snapshot);
      tasksRef.current = snapshot.tasks;
      setTasks(snapshot.tasks);
      setExecutors(snapshot.executors);
      setIsQueuePaused(snapshot.isQueuePaused === true);
      showToast(shouldPause ? `${executor.name} 已请求暂停，当前任务结束后生效。` : `${executor.name} 已继续执行。`);
    } catch (error) {
      showToast(error instanceof Error ? error.message : `${executor.name} 状态更新失败，请检查 V2 服务是否正常运行。`);
    } finally {
      setExecutorUpdatingId(null);
    }
  };

  return (
    <header className="sticky top-0 z-40 px-6 py-3 bg-[#EEF2F6]/90 backdrop-blur-md border-b border-black/[0.06] flex items-center justify-between">
      {/* Left: Brand Identity + Navigation Tabs + Workbench Version Switcher */}
      <div className="flex items-center gap-6">
        {/* App Title */}
        <div className="flex items-center gap-2.5 select-none">
          <div className="w-8 h-8 rounded-xl bg-[#1A1D2E] flex items-center justify-center text-[#DDFD00] shadow-sm">
            <Tv2 className="w-4 h-4 stroke-[2.2]" />
          </div>
          <div>
            <div className="flex items-center gap-1.5 leading-none">
              <h1 className="font-extrabold text-[15px] tracking-tight text-[#1A1D2E]">
                短剧推广运营系统
              </h1>
            </div>
            <p className="text-[11px] text-[#64748B] font-medium mt-1 leading-none">
              个人运营工作台
            </p>
          </div>
        </div>

        {/* First-Level Navigation */}
        <nav className="flex items-center p-1 bg-black/[0.04] rounded-xl gap-0.5 border border-black/[0.03]">
          <button
            id="nav-workbench"
            onClick={() => onTabChange('workbench')}
            className={`flex items-center gap-1.5 px-3.5 py-1.5 rounded-lg text-xs font-semibold transition-all duration-150 cursor-pointer ${
              activeTab === 'workbench'
                ? 'bg-white text-[#1A1D2E] shadow-xs font-bold'
                : 'text-[#64748B] hover:text-[#1A1D2E] hover:bg-white/40'
            }`}
          >
            <span className={`w-1.5 h-1.5 rounded-full ${activeTab === 'workbench' ? 'bg-[#1A1D2E]' : 'bg-transparent'}`} />
            工作台
          </button>

          <button
            id="nav-production"
            onClick={() => onTabChange('production')}
            className={`flex items-center gap-1.5 px-3.5 py-1.5 rounded-lg text-xs font-semibold transition-all duration-150 cursor-pointer ${
              activeTab === 'production'
                ? 'bg-white text-[#1A1D2E] shadow-xs font-bold'
                : 'text-[#64748B] hover:text-[#1A1D2E] hover:bg-white/40'
            }`}
          >
            <Layers className="w-3.5 h-3.5" />
            生产中心
          </button>

          <button
            id="nav-analytics"
            onClick={() => onTabChange('analytics')}
            className={`flex items-center gap-1.5 px-3.5 py-1.5 rounded-lg text-xs font-semibold transition-all duration-150 cursor-pointer ${
              activeTab === 'analytics'
                ? 'bg-white text-[#1A1D2E] shadow-xs font-bold'
                : 'text-[#64748B] hover:text-[#1A1D2E] hover:bg-white/40'
            }`}
          >
            <BarChart3 className="w-3.5 h-3.5" />
            数据分析
          </button>

          <button
            id="nav-assets"
            onClick={() => onTabChange('assets')}
            className={`flex items-center gap-1.5 px-3.5 py-1.5 rounded-lg text-xs font-semibold transition-all duration-150 cursor-pointer ${
              activeTab === 'assets'
                ? 'bg-white text-[#1A1D2E] shadow-xs font-bold'
                : 'text-[#64748B] hover:text-[#1A1D2E] hover:bg-white/40'
            }`}
          >
            <FolderGit2 className="w-3.5 h-3.5" />
            资料中心
          </button>

          <button
            id="nav-parameters"
            onClick={() => onTabChange('parameters')}
            className={`flex items-center gap-1.5 px-3.5 py-1.5 rounded-lg text-xs font-semibold transition-all duration-150 cursor-pointer ${
              activeTab === 'parameters'
                ? 'bg-white text-[#1A1D2E] shadow-xs font-bold'
                : 'text-[#64748B] hover:text-[#1A1D2E] hover:bg-white/40'
            }`}
          >
            <SlidersHorizontal className="w-3.5 h-3.5" />
            参数中心
          </button>
        </nav>

        {/* Workbench Mode Segmented Toggle (Only shown when activeTab is workbench) */}
        {activeTab === 'workbench' && onWorkbenchModeChange && (
          <div className="hidden md:flex items-center p-1 bg-black/[0.04] rounded-xl border border-black/[0.03] gap-1">
            <button
              onClick={() => onWorkbenchModeChange('explore')}
              className={`flex items-center gap-1.5 px-3 py-1 rounded-lg text-xs font-extrabold transition-all cursor-pointer ${
                workbenchMode === 'explore'
                  ? 'bg-[#1A1D2E] text-[#DDFD00] shadow-sm'
                  : 'text-[#64748B] hover:text-[#1A1D2E]'
              }`}
            >
              <Sparkles className="w-3 h-3 fill-current" />
              <span>探索版 (Explore ✨)</span>
            </button>

            <button
              onClick={() => onWorkbenchModeChange('standard')}
              className={`flex items-center gap-1.5 px-3 py-1 rounded-lg text-xs font-semibold transition-all cursor-pointer ${
                workbenchMode === 'standard'
                  ? 'bg-white text-[#1A1D2E] shadow-xs'
                  : 'text-[#64748B] hover:text-[#1A1D2E]'
              }`}
            >
              <span>标准版</span>
            </button>
          </div>
        )}
      </div>

      {/* Right Side: Integrated Status Indicators + Quick Action + Task Center + Settings */}
      <div className="flex items-center gap-3">
        {/* Subtle Status Summaries in Header */}
        <div className="hidden lg:flex items-center gap-3 text-xs pr-2 border-r border-black/[0.06]">
          <button
            onClick={() => onOpenTaskCenterModal?.()}
            title={`正在执行 ${runningTasksCount} 个；排队等待 ${waitingTasksCount} 个；今日已完成 ${doneTasksCount} 个`}
            className="flex items-center gap-2.5 px-2.5 py-1 rounded-lg hover:bg-black/[0.04] transition-colors text-left cursor-pointer whitespace-nowrap"
          >
            <span className="flex items-center gap-1"><span className="w-2 h-2 rounded-full bg-emerald-500" /><span className="text-[#64748B]">执行</span><strong className="text-emerald-700 font-extrabold">{runningTasksCount}</strong></span>
            <span className="flex items-center gap-1"><span className="w-2 h-2 rounded-full bg-amber-500" /><span className="text-[#64748B]">等待</span><strong className="text-amber-700 font-extrabold">{waitingTasksCount}</strong></span>
            <span className="flex items-center gap-1"><span className="w-2 h-2 rounded-full bg-slate-400" /><span className="text-[#64748B]">完成</span><strong className="text-[#1A1D2E] font-extrabold">{doneTasksCount}</strong></span>
          </button>

          {yesterdayRevenue && (
            <button
              onClick={() => onTabChange('analytics')}
              title={yesterdayRevenue.incompleteCount > 0 ? `昨日仍有 ${yesterdayRevenue.incompleteCount} 个账号未采集成功` : '昨日收益已采集成功'}
              className="flex items-center gap-1.5 px-2.5 py-1 rounded-lg hover:bg-black/[0.04] transition-colors cursor-pointer"
            >
              <span className="text-[#64748B]">昨日收益</span>
              <span className="font-mono font-extrabold text-[#1A1D2E]">¥{formattedYesterdayRevenue}</span>
              {yesterdayRevenue.incompleteCount > 0 && <span className="text-[11px] font-bold text-amber-700">{yesterdayRevenue.incompleteCount}未采</span>}
            </button>
          )}

          {supportableDramas !== null && (
            <button onClick={() => onTabChange('assets')} className="flex items-center gap-1.5 px-2.5 py-1 rounded-lg hover:bg-black/[0.04] transition-colors cursor-pointer">
              <span className="text-[#64748B]">资源</span>
              <span className="font-semibold text-[#1A1D2E]">支持 {supportableDramas} 部</span>
            </button>
          )}

          {accountArrangement && (
            <button
              onClick={onQuickSchedule}
              title={accountUnarrangedCount > 0 ? `今天还有 ${accountUnarrangedCount} 个正常账号未安排生产任务` : '今天所有正常账号均已安排生产任务'}
              className={`flex items-center gap-1.5 px-2.5 py-1 rounded-lg transition-colors cursor-pointer ${accountUnarrangedCount > 0 ? 'text-amber-900 hover:bg-amber-500/10' : 'hover:bg-black/[0.04]'}`}
            >
              <span className="text-[#64748B]">账号</span>
              <span className={`font-mono font-extrabold ${accountUnarrangedCount > 0 ? 'text-amber-700' : 'text-emerald-700'}`}>{accountArrangement.arranged}/{accountArrangement.total}</span>
            </button>
          )}
        </div>

        {/* Global Action Button */}
        <button
          id="btn-global-quick-schedule"
          onClick={onQuickSchedule}
          className="flex items-center gap-1.5 px-3.5 py-1.5 rounded-xl bg-[#1A1D2E] text-[#DDFD00] hover:bg-black font-extrabold text-xs transition-all shadow-xs active:scale-98 cursor-pointer"
        >
          <Sparkles className="w-3.5 h-3.5 fill-[#DDFD00]" />
          <span>安排今天</span>
        </button>

        {/* Task Center Secondary Global Entry & Clean Preview Popover */}
        <div className="relative">
          <button
            id="btn-task-center"
            onClick={() => setShowTaskCenter(!showTaskCenter)}
            className={`flex items-center gap-2 px-3 py-1.5 rounded-xl text-xs transition-all border cursor-pointer ${
              showTaskCenter
                ? 'bg-[#1A1D2E] text-white border-[#1A1D2E]'
                : abnormalTasksCount > 0
                ? 'bg-rose-50/80 text-rose-900 border-rose-200 hover:bg-rose-100/80'
                : 'bg-white/80 text-[#1A1D2E] border-black/[0.08] hover:bg-white'
            }`}
          >
            {abnormalTasksCount > 0 ? (
              <AlertTriangle className="w-3.5 h-3.5 text-rose-600 animate-pulse" />
            ) : (
              <Zap className={`w-3.5 h-3.5 ${showTaskCenter ? 'text-[#DDFD00]' : 'text-[#64748B]'}`} />
            )}

            <span className="font-bold">任务监控</span>
            
            <div className="flex items-center gap-1">
              <span className="text-emerald-600 font-extrabold text-[11px]">
                {runningTasksCount} 执行中
              </span>
              {abnormalTasksCount > 0 && (
                <span className="px-1.5 py-0.2 bg-rose-500 text-white rounded text-[10px] font-bold">
                  {abnormalTasksCount} 异常
                </span>
              )}
            </div>
          </button>

          {/* Clean Dedicated Task Center Preview Popover */}
          {showTaskCenter && (
            <TaskCenterPreviewPopover
              tasks={tasks}
              onTaskAction={handleTaskAction}
              isQueuePaused={isQueuePaused}
              isQueuePauseUpdating={isQueuePauseUpdating}
              onToggleQueuePause={handleToggleQueuePause}
              executors={executors}
              executorUpdatingId={executorUpdatingId}
              onToggleExecutor={handleToggleExecutor}
              onOpenFullTaskCenter={() => {
                setShowTaskCenter(false);
                if (onOpenTaskCenterModal) {
                  onOpenTaskCenterModal();
                }
              }}
              onClose={() => setShowTaskCenter(false)}
            />
          )}
        </div>

        {/* Settings Button */}
        <button
          id="btn-settings"
          onClick={onOpenSettings}
          title="系统设置"
          className="p-2 rounded-xl text-[#64748B] hover:text-[#1A1D2E] hover:bg-black/[0.04] transition-colors cursor-pointer"
        >
          <Settings className="w-4 h-4" />
        </button>
      </div>
    </header>
  );
};
