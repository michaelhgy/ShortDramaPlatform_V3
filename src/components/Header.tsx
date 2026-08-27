import React, { useState } from 'react';
import { NavTab, TaskCenterTask, ProductionSummary } from '../types';
import { 
  Tv2, 
  Layers, 
  BarChart3, 
  FolderGit2, 
  Settings, 
  Zap, 
  Sparkles, 
  AlertCircle,
  AlertTriangle
} from 'lucide-react';
import { TaskCenterPreviewPopover } from './taskcenter/TaskCenterPreviewPopover';
import { INITIAL_TASKS } from './taskcenter/taskCenterMockData';
import { TaskItem } from './taskcenter/taskCenterTypes';

interface HeaderProps {
  activeTab: NavTab;
  onTabChange: (tab: NavTab) => void;
  taskQueue: TaskCenterTask[];
  onOpenSettings: () => void;
  onQuickSchedule: () => void;
  productionSummary?: ProductionSummary;
  unassignedCount?: number;
  onOpenUnassigned?: () => void;
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
  productionSummary,
  unassignedCount = 0,
  onOpenUnassigned,
  workbenchMode = 'explore',
  onWorkbenchModeChange,
  onOpenTaskCenterModal,
  showToast = (_msg: string) => {},
}) => {
  const [showTaskCenter, setShowTaskCenter] = useState(false);
  const [tasks, setTasks] = useState<TaskItem[]>(INITIAL_TASKS);

  // Filter currently active & timeout tasks
  const runningTasksCount = tasks.filter(t => t.status === 'running').length;
  const timeoutTasksCount = tasks.filter(t => t.isTimeout || t.status === 'timeout').length;
  const errorTasksCount = tasks.filter(t => t.status === 'error').length;

  const handleRetryTask = (task: TaskItem) => {
    setTasks(prev =>
      prev.map(t => {
        if (t.id === task.id) {
          return {
            ...t,
            status: 'running',
            isTimeout: false,
            durationSeconds: 1,
            durationFormatted: '01秒 (已重新启动)',
            progress: 15,
          };
        }
        return t;
      })
    );
    showToast(`⚡ 已重新启动任务：《${task.dramaName}》-${task.accountName}`);
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
          {productionSummary && (
            <button
              onClick={() => onTabChange('production')}
              className="flex items-center gap-2 px-2.5 py-1 rounded-lg hover:bg-black/[0.04] transition-colors text-left cursor-pointer"
            >
              <span className="w-2 h-2 rounded-full bg-emerald-500" />
              <span className="text-[#64748B]">生产:</span>
              <span className="font-semibold text-[#1A1D2E]">
                制作中 {productionSummary.inProgress} · 就绪 {productionSummary.completed}
              </span>
            </button>
          )}

          {unassignedCount > 0 && (
            <button
              onClick={onOpenUnassigned}
              className="flex items-center gap-1.5 px-2.5 py-1 rounded-lg bg-amber-500/10 hover:bg-amber-500/15 text-amber-900 border border-amber-500/20 font-medium transition-colors cursor-pointer"
            >
              <AlertCircle className="w-3.5 h-3.5 text-amber-600" />
              <span>{unassignedCount} 个账号待安排</span>
            </button>
          )}

          <div className="flex items-center gap-1.5 text-[#64748B] pl-1">
            <span className="w-1.5 h-1.5 rounded-full bg-[#1A1D2E]/40" />
            <span>小V猫就绪</span>
          </div>
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
                : timeoutTasksCount > 0
                ? 'bg-rose-50/80 text-rose-900 border-rose-200 hover:bg-rose-100/80'
                : 'bg-white/80 text-[#1A1D2E] border-black/[0.08] hover:bg-white'
            }`}
          >
            {timeoutTasksCount > 0 ? (
              <AlertTriangle className="w-3.5 h-3.5 text-rose-600 animate-pulse" />
            ) : (
              <Zap className={`w-3.5 h-3.5 ${showTaskCenter ? 'text-[#DDFD00]' : 'text-[#64748B]'}`} />
            )}

            <span className="font-bold">任务监控</span>
            
            <div className="flex items-center gap-1">
              <span className="text-emerald-600 font-extrabold text-[11px]">
                {runningTasksCount + timeoutTasksCount} 执行中
              </span>
              {timeoutTasksCount > 0 && (
                <span className="px-1.5 py-0.2 bg-rose-500 text-white rounded text-[10px] font-bold">
                  {timeoutTasksCount} 超时
                </span>
              )}
            </div>
          </button>

          {/* Clean Dedicated Task Center Preview Popover */}
          {showTaskCenter && (
            <TaskCenterPreviewPopover
              tasks={tasks}
              onRetryTask={handleRetryTask}
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
