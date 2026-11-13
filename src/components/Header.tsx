import { currentCounts } from './taskcenter/ffmpegTaskModel';
import { loadSharedTaskCenter } from '../services/taskCenterService';
import React, { useEffect, useState } from 'react';
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
import { eventDetail } from '../services/dataChangeEvents';
import { useDataArea } from '../hooks/useDataArea';
import { loadV2DailyAccountRevenueSummary } from '../api/v2Revenue';
import { calculateResourceMetrics } from '../utils/resourceMetrics';
import { loadProductionResources } from '../services/assetsCenterService';
import type { ProductionResourceItem } from '../assetsTypes';
import { planningDayOffset } from '../utils/plannedDate';

interface HeaderProps {
  activeTab: NavTab;
  onTabChange: (tab: NavTab) => void;
  onOpenScenery: () => void;
  taskQueue: TaskCenterTask[];
  onOpenSettings: () => void;
  onQuickSchedule: () => void;
  onOpenTaskCenterModal?: () => void;
  showToast?: (msg: string) => void;
}

export const Header: React.FC<HeaderProps> = ({
  activeTab,
  onTabChange,
  onOpenScenery,
  taskQueue: _taskQueue,
  onOpenSettings,
  onQuickSchedule,
  onOpenTaskCenterModal,
  showToast = (_msg: string) => {},
}) => {
  const [showTaskCenter, setShowTaskCenter] = useState(false);
  const [yesterdayRevenue, setYesterdayRevenue] = useState<{ amount: number; incompleteCount: number } | null>(null);
  const resourceArea = useDataArea<ProductionResourceItem[]>('resourceIndex', loadProductionResources);
  const sceneryVideoCount = resourceArea.data ? calculateResourceMetrics(resourceArea.data).videoCount : null;

  useEffect(() => {
    let active = true;
    const localDate = (offsetDays: number) => planningDayOffset(offsetDays);
    const refreshRevenue = () => void loadV2DailyAccountRevenueSummary(localDate(-1)).then((summary) => {
      if (!active) return;
      const completed = summary.items.filter((item) => item.collection_status === 'success');
      setYesterdayRevenue({
        amount: completed.reduce((sum, item) => sum + Number(item.amount || 0), 0),
        incompleteCount: summary.items.filter((item) => item.collection_status === 'uncollected' || item.collection_status === 'failed').length,
      });
    }).catch(() => undefined);
    refreshRevenue();
    const onDataChanged = (event: Event) => {
      const detail = eventDetail(event);
      if (detail.changeType === 'revenue_changed' || detail.changeType === 'account_changed') refreshRevenue();
    };
    window.addEventListener('v2-data-changed', onDataChanged);
    return () => { active = false; window.removeEventListener('v2-data-changed', onDataChanged); };
  }, []);

  // ── 统一数据层接入（刷新大修 · 第 2 步）──────────────────────────────
  // 这份「任务快照」现在由数据层每 3 秒统一拉一次，顶栏 / 任务中心 / 生产中心**共用同一份**。
  // 旧实现是三处各自 loadSharedTaskCenter + 各自订阅变更事件 —— 那正是三处数字偶尔对不上的原因。
  // 失败时数据层保留旧快照（不清空、不弹提示），与原来注释的意图一致。
  const taskCenterArea = useDataArea<Awaited<ReturnType<typeof loadSharedTaskCenter>>>(
    'taskCenter',
    () => loadSharedTaskCenter(true),
  );

  const queueCounts = currentCounts(taskCenterArea.data?.finalComposition, taskCenterArea.data?.templateGeneration, taskCenterArea.data?.sceneryProcessing);
  const runningTasksCount = queueCounts.running;
  const abnormalTasksCount = queueCounts.error;
  const waitingTasksCount = queueCounts.waiting;
  const doneTasksCount = queueCounts.done;
  const formattedYesterdayRevenue = yesterdayRevenue
    ? new Intl.NumberFormat('zh-CN', { minimumFractionDigits: 0, maximumFractionDigits: 2 }).format(yesterdayRevenue.amount)
    : '';


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
            id="nav-dashboard"
            onClick={() => onTabChange('dashboard')}
            className={`flex items-center gap-1.5 px-3.5 py-1.5 rounded-lg text-xs font-semibold transition-all duration-150 cursor-pointer ${
              activeTab === 'dashboard'
                ? 'bg-white text-[#1A1D2E] shadow-xs font-bold'
                : 'text-[#64748B] hover:text-[#1A1D2E] hover:bg-white/40'
            }`}
          >
            <BarChart3 className="w-3.5 h-3.5" />
            运营总览
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
            id="nav-content"
            onClick={() => onTabChange('content')}
            className={`flex items-center gap-1.5 px-3.5 py-1.5 rounded-lg text-xs font-semibold transition-all duration-150 cursor-pointer ${
              activeTab === 'content'
                ? 'bg-white text-[#1A1D2E] shadow-xs font-bold'
                : 'text-[#64748B] hover:text-[#1A1D2E] hover:bg-white/40'
            }`}
          >
            <Sparkles className="w-3.5 h-3.5" />
            内容生产
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

      </div>

      {/* Right Side: Integrated Status Indicators + Quick Action + Task Center + Settings */}
      <div className="flex items-center gap-3">
        {/* Subtle Status Summaries in Header */}
        <div className="hidden lg:flex items-center gap-3 text-xs pr-2 border-r border-black/[0.06]">
          <button
            onClick={() => onOpenTaskCenterModal?.()}
            title={`正在执行 ${runningTasksCount} 个；排队等待 ${waitingTasksCount} 个；已完成 ${doneTasksCount} 个`}
            className="flex items-center gap-2.5 px-2.5 py-1 rounded-lg hover:bg-black/[0.04] transition-colors text-left cursor-pointer whitespace-nowrap"
          >
            <span className="flex items-center gap-1"><span className="w-2 h-2 rounded-full bg-emerald-500" /><span className="text-[#64748B]">执行</span><strong className="text-emerald-700 font-extrabold">{runningTasksCount}</strong></span>
            <span className="flex items-center gap-1"><span className="w-2 h-2 rounded-full bg-amber-500" /><span className="text-[#64748B]">等待</span><strong className="text-amber-700 font-extrabold">{waitingTasksCount}</strong></span>
            <span className="flex items-center gap-1"><span className="w-2 h-2 rounded-full bg-slate-400" /><span className="text-[#64748B]">完成</span><strong className="text-[#1A1D2E] font-extrabold">{doneTasksCount}</strong></span>
          </button>

          {yesterdayRevenue && (
            <button
              onClick={() => onTabChange('dashboard')}
              title={yesterdayRevenue.incompleteCount > 0 ? `昨日仍有 ${yesterdayRevenue.incompleteCount} 个账号未采集成功` : '昨日收益已采集成功'}
              className="flex items-center gap-1.5 px-2.5 py-1 rounded-lg hover:bg-black/[0.04] transition-colors cursor-pointer"
            >
              <span className="text-[#64748B]">昨日收益</span>
              <span className="font-mono font-extrabold text-[#1A1D2E]">¥{formattedYesterdayRevenue}</span>
              {yesterdayRevenue.incompleteCount > 0 && <span className="text-[11px] font-bold text-amber-700">{yesterdayRevenue.incompleteCount}未采</span>}
            </button>
          )}

          {sceneryVideoCount !== null && (
            <button onClick={onOpenScenery} title="查看可用风景素材" className="flex items-center gap-1.5 px-2.5 py-1 rounded-lg hover:bg-black/[0.04] transition-colors cursor-pointer">
              <span className="text-[#64748B]">资源</span>
              <span className="font-semibold text-[#1A1D2E]">风景 {sceneryVideoCount} 条</span>
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
              finalComposition={taskCenterArea.data?.finalComposition}
              templateGeneration={taskCenterArea.data?.templateGeneration}
              sceneryProcessing={taskCenterArea.data?.sceneryProcessing}
              showToast={showToast}
              error={taskCenterArea.error}
              updatedAt={taskCenterArea.updatedAt}
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
