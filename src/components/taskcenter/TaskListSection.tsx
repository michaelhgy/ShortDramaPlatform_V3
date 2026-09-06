import React, { useState, useMemo } from 'react';
import { 
  Search, 
  RotateCcw, 
  RefreshCw, 
  Video, 
  Film, 
  Sparkles, 
  Clock, 
  AlertTriangle, 
  CheckCircle2, 
  Bug, 
  ChevronDown, 
  ChevronUp, 
  Info,
  Check,
  Play,
  ArrowRight,
  Flame,
  AlertCircle
} from 'lucide-react';
import { TaskItem, TaskCategory } from './taskCenterTypes';
import { getTaskCenterActions } from './taskCenterActionPolicy';
import { formatTaskDateTime } from './taskCenterFormat';
import { taskElapsedLabel } from '../../utils/duration';

interface TaskListSectionProps {
  tasks: TaskItem[];
  onRetryTask: (task: TaskItem) => void;
  onRegenerateDraft: (task: TaskItem) => void;
  onReExportVideo: (task: TaskItem) => void;
  onViewTaskDetail: (task: TaskItem) => void;
}

/** Keep the persisted exporter phase visible instead of reducing all active work to "正在导出". */
function exportPhaseLabel(rawStatus?: string): string {
  const labels: Record<string, string> = {
    queued: '排队中',
    preparing: '准备中',
    submitting: '提交导出',
    observing_output: '观察输出',
    finalizing: '验收收口',
    completed: '已完成',
    failed: '导出失败',
    timeout: '导出超时',
  };
  return labels[rawStatus || ''] || '';
}

export const TaskListSection: React.FC<TaskListSectionProps> = ({
  tasks,
  onRetryTask,
  onRegenerateDraft,
  onReExportVideo,
  onViewTaskDetail,
}) => {
  const [statusFilter, setStatusFilter] = useState<'all' | 'running' | 'abnormal' | 'waiting' | 'done'>('all');
  const [categoryFilter, setCategoryFilter] = useState<'all' | TaskCategory>('all');
  const [dramaFilter, setDramaFilter] = useState<string>('all');
  const [accountFilter, setAccountFilter] = useState<string>('all');
  const [searchQuery, setSearchQuery] = useState<string>('');
  const [expandedTaskId, setExpandedTaskId] = useState<string | null>(null);

  // Extract unique dramas & accounts
  const uniqueDramas = useMemo(() => {
    const set = new Set<string>();
    tasks.forEach(t => set.add(t.dramaName));
    return Array.from(set);
  }, [tasks]);

  const uniqueAccounts = useMemo(() => {
    const set = new Set<string>();
    tasks.forEach(t => set.add(t.accountName));
    return Array.from(set);
  }, [tasks]);

  // Compute counts for status badges
  const counts = useMemo(() => {
    const running = tasks.filter(t => t.status === 'running').length;
    const abnormal = tasks.filter(t => t.status === 'timeout' || t.status === 'error' || t.isTimeout).length;
    const waiting = tasks.filter(t => t.status === 'waiting').length;
    const done = tasks.filter(t => t.status === 'done').length;
    return { all: tasks.length, running, abnormal, waiting, done };
  }, [tasks]);

  // Filter tasks
  const filteredTasks = useMemo(() => {
    const statusOrder: Record<string, number> = { running: 0, timeout: 1, error: 2, waiting: 3, done: 4 };
    return tasks.filter(t => {
      // 1. Status Filter
      if (statusFilter === 'running' && t.status !== 'running') return false;
      if (statusFilter === 'abnormal' && t.status !== 'timeout' && t.status !== 'error' && !t.isTimeout) return false;
      if (statusFilter === 'waiting' && t.status !== 'waiting') return false;
      if (statusFilter === 'done' && t.status !== 'done') return false;

      // 2. Category Filter
      if (categoryFilter !== 'all' && t.taskCategory !== categoryFilter) return false;

      // 3. Drama Filter
      if (dramaFilter !== 'all' && t.dramaName !== dramaFilter) return false;

      // 4. Account Filter
      if (accountFilter !== 'all' && t.accountName !== accountFilter) return false;

      // 5. Search query
      if (searchQuery.trim()) {
        const q = searchQuery.toLowerCase();
        const matchTitle = t.title.toLowerCase().includes(q);
        const matchDrama = t.dramaName.toLowerCase().includes(q);
        const matchAccount = t.accountName.toLowerCase().includes(q);
        const matchMaterial = t.materialName?.toLowerCase().includes(q) || false;
        const matchId = t.id.toLowerCase().includes(q);
        if (!matchTitle && !matchDrama && !matchAccount && !matchMaterial && !matchId) {
          return false;
        }
      }

      return true;
    }).sort((a, b) => {
      const statusDiff = (statusOrder[a.status] ?? 3) - (statusOrder[b.status] ?? 3);
      if (statusDiff) return statusDiff;
      const priorityDiff = (a.priorityRank > 0 ? a.priorityRank : Number.MAX_SAFE_INTEGER)
        - (b.priorityRank > 0 ? b.priorityRank : Number.MAX_SAFE_INTEGER);
      if (priorityDiff) return priorityDiff;
      const sequenceDiff = (a.sequenceNo ?? Number.MAX_SAFE_INTEGER) - (b.sequenceNo ?? Number.MAX_SAFE_INTEGER);
      if (sequenceDiff) return sequenceDiff;
      return a.createdAt.localeCompare(b.createdAt) || a.id.localeCompare(b.id);
    });
  }, [tasks, statusFilter, categoryFilter, dramaFilter, accountFilter, searchQuery]);

  const toggleExpand = (id: string) => {
    setExpandedTaskId(prev => (prev === id ? null : id));
  };

  /**
   * Helper to derive the single primary focal state of the task
   * so users can scan and immediately understand what's happening right now.
   */
  const getTaskPrimaryFocalState = (task: TaskItem) => {
    const { draftStage, videoStage, status } = task;

    // 1. Draft abnormal states
    if (draftStage.status === 'timeout') {
      return {
        label: '草稿生成超时',
        subtext: '耗时超出设定阈值',
        phase: 'draft' as const,
        tone: 'danger' as const,
        icon: AlertTriangle,
      };
    }
    if (draftStage.status === 'error') {
      return {
        label: '草稿生成中断',
        subtext: '装配过程遇到异常',
        phase: 'draft' as const,
        tone: 'danger' as const,
        icon: AlertCircle,
      };
    }

    // 2. Video abnormal states
    if (videoStage.status === 'timeout') {
      return {
        label: task.taskCategory === 'template' && task.hasCompletedFirstExport
          ? '新版本导出超时（正式模板已保留）'
          : '视频导出超时',
        subtext: task.taskCategory === 'template' && task.hasCompletedFirstExport
          ? '当前正式模板视频仍可正常使用'
          : '剪映渲染响应挂起',
        phase: 'video' as const,
        tone: 'danger' as const,
        icon: AlertTriangle,
      };
    }
    if (videoStage.status === 'error') {
      return {
        label: task.taskCategory === 'template' && task.hasCompletedFirstExport
          ? '新版本导出失败（正式模板已保留）'
          : '视频导出失败',
        subtext: task.taskCategory === 'template' && task.hasCompletedFirstExport
          ? '当前正式模板视频仍可正常使用'
          : '编码渲染中断',
        phase: 'video' as const,
        tone: 'danger' as const,
        icon: AlertCircle,
      };
    }

    // 3. Actively Running States
    if (videoStage.status === 'running') {
      return {
        label: `正在导出视频 ${videoStage.progress || task.progress}%`,
        subtext: task.durationSeconds > 0 ? `已耗时 ${taskElapsedLabel(task.durationSeconds)}` : '剪映硬件编码中',
        phase: 'video' as const,
        tone: 'running' as const,
        icon: Video,
      };
    }
    if (draftStage.status === 'running') {
      return {
        label: `正在组装草稿 ${draftStage.progress || task.progress}%`,
        subtext: task.durationSeconds > 0 ? `已耗时 ${taskElapsedLabel(task.durationSeconds)}` : '工程组装中',
        phase: 'draft' as const,
        tone: 'running' as const,
        icon: RefreshCw,
      };
    }

    // 4. Waiting states
    if (draftStage.status === 'done' && videoStage.status === 'waiting') {
      return {
        label: '草稿就绪 · 等待首次导出',
        subtext: '已加入视频导出器排队',
        phase: 'video' as const,
        tone: 'waiting_export' as const,
        icon: Clock,
      };
    }
    if (draftStage.status === 'waiting') {
      return {
        label: '等待草稿生成',
        subtext: '排队等待调度执行',
        phase: 'draft' as const,
        tone: 'waiting_draft' as const,
        icon: Clock,
      };
    }

    // 5. Completed
    if (status === 'done' || (draftStage.status === 'done' && videoStage.status === 'done')) {
      return {
        label: '全流程已完成',
        subtext: task.durationSeconds > 0 ? `总耗时 ${taskElapsedLabel(task.durationSeconds)}` : '产物已就绪',
        phase: 'done' as const,
        tone: 'done' as const,
        icon: CheckCircle2,
      };
    }

    return {
      label: '等待中',
        subtext: task.durationSeconds > 0 ? taskElapsedLabel(task.durationSeconds) : '尚未开始',
      phase: 'draft' as const,
      tone: 'neutral' as const,
      icon: Clock,
    };
  };

  return (
    <div className="space-y-3.5">
      {/* Section Header */}
      <div className="flex flex-wrap items-center justify-between gap-3 px-1">
        <div className="flex items-center gap-2.5">
          <div className="w-2.5 h-2.5 rounded-full bg-[#1A1D2E]" />
          <h3 className="font-extrabold text-sm text-[#1A1D2E] tracking-tight">
            任务全生命周期列表 (任务主轴卡片)
          </h3>
          <span className="text-xs text-[#64748B] font-medium">
            共 {tasks.length} 项制作任务 · 当前显示 {filteredTasks.length} 项
          </span>
        </div>

        {/* Legend */}
        <div className="hidden lg:flex items-center gap-3 text-[11px] text-[#64748B]">
          <span className="flex items-center gap-1.5 font-medium">
            <span className="w-2 h-2 rounded-full bg-emerald-500" />
            聚焦当前活跃阶段
          </span>
          <span className="flex items-center gap-1.5 font-medium">
            <span className="w-2 h-2 rounded-full bg-rose-500" />
            异常精准定位与恢复
          </span>
        </div>
      </div>

      {/* Filter Control Bar */}
      <div className="bg-white rounded-2xl border border-black/[0.06] p-3 shadow-xs space-y-2.5">
        {/* Row 1: Status Tabs & Search Box */}
        <div className="flex flex-wrap items-center justify-between gap-3">
          {/* Status Tabs */}
          <div className="flex items-center gap-1 p-1 bg-slate-100/90 rounded-xl overflow-x-auto">
            <button
              onClick={() => setStatusFilter('all')}
              className={`px-3 py-1.5 rounded-lg text-xs font-bold transition-all cursor-pointer whitespace-nowrap ${
                statusFilter === 'all'
                  ? 'bg-white text-[#1A1D2E] shadow-2xs'
                  : 'text-[#64748B] hover:text-[#1A1D2E]'
              }`}
            >
              全部 ({counts.all})
            </button>
            <button
              onClick={() => setStatusFilter('running')}
              className={`px-3 py-1.5 rounded-lg text-xs font-bold transition-all cursor-pointer whitespace-nowrap flex items-center gap-1.5 ${
                statusFilter === 'running'
                  ? 'bg-white text-emerald-800 shadow-2xs'
                  : 'text-[#64748B] hover:text-emerald-700'
              }`}
            >
              <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse" />
              执行中 ({counts.running})
            </button>
            <button
              onClick={() => setStatusFilter('abnormal')}
              className={`px-3 py-1.5 rounded-lg text-xs font-bold transition-all cursor-pointer whitespace-nowrap flex items-center gap-1.5 ${
                statusFilter === 'abnormal'
                  ? 'bg-white text-rose-800 shadow-2xs'
                  : 'text-[#64748B] hover:text-rose-700'
              }`}
            >
              {counts.abnormal > 0 && <span className="w-1.5 h-1.5 rounded-full bg-rose-500" />}
              超时 / 失败 ({counts.abnormal})
            </button>
            <button
              onClick={() => setStatusFilter('waiting')}
              className={`px-3 py-1.5 rounded-lg text-xs font-bold transition-all cursor-pointer whitespace-nowrap ${
                statusFilter === 'waiting'
                  ? 'bg-white text-amber-800 shadow-2xs'
                  : 'text-[#64748B] hover:text-amber-700'
              }`}
            >
              排队等待 ({counts.waiting})
            </button>
            <button
              onClick={() => setStatusFilter('done')}
              className={`px-3 py-1.5 rounded-lg text-xs font-bold transition-all cursor-pointer whitespace-nowrap ${
                statusFilter === 'done'
                  ? 'bg-white text-slate-900 shadow-2xs'
                  : 'text-[#64748B] hover:text-slate-900'
              }`}
            >
              已完成 ({counts.done})
            </button>
          </div>

          {/* Search Box */}
          <div className="relative min-w-[200px] flex-1 max-w-xs">
            <Search className="w-3.5 h-3.5 absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
            <input
              type="text"
              placeholder="搜索剧名 / 账号 / 素材..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="w-full pl-8.5 pr-3 py-1.5 bg-[#F8FAFC] border border-black/[0.06] rounded-xl text-xs text-[#1A1D2E] placeholder:text-slate-400 focus:outline-none focus:bg-white focus:border-black/[0.15] transition-all"
            />
          </div>
        </div>

        {/* Row 2: Secondary Filters */}
        <div className="flex flex-wrap items-center justify-between gap-2.5 pt-2 border-t border-black/[0.04] text-xs">
          {/* Category Selector */}
          <div className="flex items-center gap-1.5">
            <span className="text-[#64748B] font-medium text-[11px]">业务类型:</span>
            <button
              onClick={() => setCategoryFilter('all')}
              className={`px-2.5 py-1 rounded-lg text-[11px] font-bold transition-all cursor-pointer ${
                categoryFilter === 'all'
                  ? 'bg-[#1A1D2E] text-[#DDFD00]'
                  : 'bg-slate-100 text-[#64748B] hover:text-[#1A1D2E]'
              }`}
            >
              全部
            </button>
            <button
              onClick={() => setCategoryFilter('template')}
              className={`px-2.5 py-1 rounded-lg text-[11px] font-bold transition-all cursor-pointer flex items-center gap-1 ${
                categoryFilter === 'template'
                  ? 'bg-amber-500 text-white shadow-2xs'
                  : 'bg-slate-100 text-[#64748B] hover:text-[#1A1D2E]'
              }`}
            >
              <Sparkles className="w-3 h-3" />
              模板制作
            </button>
            <button
              onClick={() => setCategoryFilter('final_video')}
              className={`px-2.5 py-1 rounded-lg text-[11px] font-bold transition-all cursor-pointer flex items-center gap-1 ${
                categoryFilter === 'final_video'
                  ? 'bg-indigo-600 text-white shadow-2xs'
                  : 'bg-slate-100 text-[#64748B] hover:text-[#1A1D2E]'
              }`}
            >
              <Film className="w-3 h-3" />
              成片制作
            </button>
          </div>

          {/* Drama & Account selects */}
          <div className="flex items-center gap-2 flex-wrap">
            <select
              value={dramaFilter}
              onChange={(e) => setDramaFilter(e.target.value)}
              className="px-2.5 py-1 bg-[#F8FAFC] border border-black/[0.06] rounded-lg text-xs font-bold text-[#1A1D2E] focus:outline-none cursor-pointer"
            >
              <option value="all">全部剧集 ({uniqueDramas.length})</option>
              {uniqueDramas.map((drama) => (
                <option key={drama} value={drama}>
                  《{drama}》
                </option>
              ))}
            </select>

            <select
              value={accountFilter}
              onChange={(e) => setAccountFilter(e.target.value)}
              className="px-2.5 py-1 bg-[#F8FAFC] border border-black/[0.06] rounded-lg text-xs font-bold text-[#1A1D2E] focus:outline-none cursor-pointer"
            >
              <option value="all">全部账号 ({uniqueAccounts.length})</option>
              {uniqueAccounts.map((acc) => (
                <option key={acc} value={acc}>
                  {acc}
                </option>
              ))}
            </select>
          </div>
        </div>
      </div>

      {/* Task Cards List with Streamlined Visual Architecture */}
      <div className="space-y-3">
        {filteredTasks.length === 0 ? (
          <div className="py-12 px-4 bg-white rounded-2xl border border-black/[0.06] text-center text-xs text-[#64748B] space-y-2">
            <Info className="w-6 h-6 text-slate-300 mx-auto" />
            <p className="font-bold text-[#1A1D2E]">未找到匹配的任务卡片</p>
            <p className="text-[11px] text-slate-400">请尝试切换筛选条件或清除搜索关键字</p>
          </div>
        ) : (
          filteredTasks.map((task) => {
            const isTemplate = task.taskCategory === 'template';
            const isFinalVideo = task.taskCategory === 'final_video';

            const isOverallDone = task.status === 'done';
            const isOverallRunning = task.status === 'running';
            const isOverallTimeout = task.status === 'timeout' || task.isTimeout;
            const isOverallError = task.status === 'error';
            const isOverallAbnormal = isOverallTimeout || isOverallError;

            const isExpanded = expandedTaskId === task.id;

            // Draft Stage conditions
            const draftStatus = task.draftStage.status;
            const isDraftWaiting = draftStatus === 'waiting';
            const isDraftRunning = draftStatus === 'running';
            const isDraftDone = draftStatus === 'done';
            const isDraftAbnormal = draftStatus === 'error' || draftStatus === 'timeout';

            // Video Stage conditions
            const videoStatus = task.videoStage.status;
            const videoPhaseLabel = exportPhaseLabel(task.videoStage.rawStatus);
            const isVideoIdle = videoStatus === 'idle';
            const isVideoWaiting = videoStatus === 'waiting';
            const isVideoRunning = videoStatus === 'running';
            const isVideoDone = videoStatus === 'done';
            const isVideoAbnormal = videoStatus === 'error' || videoStatus === 'timeout';

            // Current Focal State
            const focalState = getTaskPrimaryFocalState(task);
            const FocalIcon = focalState.icon;

            const allowedActions = getTaskCenterActions(task);
            const canRegenerate = allowedActions.includes('regenerate');
            const canRetry = allowedActions.includes('retry');
            const canReExport = allowedActions.includes('reExport');

            return (
              <div
                key={task.id}
                className={`rounded-2xl border transition-all duration-150 overflow-hidden bg-white ${
                  isOverallAbnormal
                    ? 'border-rose-300 ring-2 ring-rose-500/10 shadow-xs'
                    : isOverallRunning
                    ? 'border-emerald-400 ring-2 ring-emerald-500/10 shadow-xs'
                    : isOverallDone
                    ? 'border-black/[0.06] hover:border-black/[0.12] shadow-2xs'
                    : 'border-black/[0.06] hover:border-black/[0.12]'
                }`}
              >
                {/* Main Card Header & Focal Line */}
                <div className="p-4 space-y-3">
                  {/* Top Row: Identity Anchor (Left) + Focal Status Spotlight (Middle/Right) + Schedule/Priority (Right) */}
                  <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-3">
                    {/* Left: Task Identity Header */}
                    <div className="flex items-center gap-2.5 flex-wrap min-w-0">
                      {/* Category Tag */}
                      {isTemplate ? (
                        <span className="inline-flex items-center gap-1 text-[11px] px-2.5 py-1 rounded-lg font-black bg-amber-100 text-amber-900 border border-amber-300/80 shadow-2xs shrink-0">
                          <Sparkles className="w-3 h-3 text-amber-700" />
                          模板
                        </span>
                      ) : (
                        <span className="inline-flex items-center gap-1 text-[11px] px-2.5 py-1 rounded-lg font-black bg-indigo-50 text-indigo-800 border border-indigo-200 shadow-2xs shrink-0">
                          <Film className="w-3 h-3 text-indigo-600" />
                          成片
                        </span>
                      )}

                      {/* Clear, High-Contrast Typography Hierarchy */}
                      <div className="flex items-center gap-2 flex-wrap min-w-0">
                        <span className="font-extrabold text-sm text-slate-800 tracking-tight">
                          {task.accountName}
                        </span>
                        <span className="text-slate-300 font-light">×</span>
                        <h4 className="font-black text-sm text-[#1A1D2E] tracking-tight">
                          《{task.dramaName}》
                        </h4>

                        {/* Material Specificity */}
                        {isFinalVideo && task.materialName ? (
                          <span className="px-2 py-0.5 rounded-md bg-slate-900 text-white font-mono font-extrabold text-xs shadow-2xs">
                            {task.materialName}
                          </span>
                        ) : isTemplate ? (
                          <span className="text-[11px] text-amber-900 bg-amber-50 px-2 py-0.5 rounded-md border border-amber-200 font-bold">
                            通用母本草稿
                          </span>
                        ) : null}
                      </div>
                    </div>

                    {/* Right Meta Anchor: Publish Time & Schedule Priority */}
                    <div className="flex items-center gap-2 self-start lg:self-auto shrink-0">
                      {/* Scheduled Time */}
                      <div className="flex items-center gap-1 text-xs font-bold text-slate-700 bg-slate-100 px-2.5 py-1 rounded-xl border border-black/[0.04]">
                        <Clock className="w-3.5 h-3.5 text-slate-500" />
                        <span>{formatTaskDateTime(task.scheduledPublishTime)} 发布</span>
                      </div>

                      {/* Priority Badge */}
                      {task.priorityTag?.includes('模板') || task.priorityTag?.includes('最高') ? (
                        <span className="text-[11px] font-black px-2.5 py-1 rounded-xl bg-amber-500/15 text-amber-950 border border-amber-500/30">
                          ⭐ 模板最高优先
                        </span>
                      ) : (
                        <span className="text-[11px] font-black px-2.5 py-1 rounded-xl bg-[#1A1D2E] text-[#DDFD00]">
                          优先 #{task.priorityRank}
                        </span>
                      )}
                    </div>
                  </div>

                  {/* Middle Row: The Unified Stage Progress Strip (Visual Flow Architecture) */}
                  <div className="rounded-xl bg-[#F8FAFC] border border-black/[0.04] p-3 flex flex-col md:flex-row md:items-center justify-between gap-3">
                    {/* Left Spotlight Box: Single Primary Focal State */}
                    <div className="flex items-center gap-3 min-w-[260px]">
                      <div className={`w-9 h-9 rounded-xl flex items-center justify-center shrink-0 shadow-2xs ${
                        focalState.tone === 'danger'
                          ? 'bg-rose-500 text-white animate-pulse'
                          : focalState.tone === 'running'
                          ? 'bg-emerald-500 text-white'
                          : focalState.tone === 'done'
                          ? 'bg-[#1A1D2E] text-[#DDFD00]'
                          : focalState.tone === 'waiting_export'
                          ? 'bg-amber-400 text-amber-950'
                          : 'bg-slate-200 text-slate-600'
                      }`}>
                        <FocalIcon className={`w-5 h-5 ${focalState.tone === 'running' ? 'animate-spin' : ''}`} />
                      </div>

                      <div className="min-w-0">
                        <div className="flex items-center gap-1.5">
                          <span className={`text-xs font-black tracking-tight ${
                            focalState.tone === 'danger'
                              ? 'text-rose-700'
                              : focalState.tone === 'running'
                              ? 'text-emerald-800'
                              : focalState.tone === 'done'
                              ? 'text-slate-900'
                              : focalState.tone === 'waiting_export'
                              ? 'text-amber-900'
                              : 'text-slate-700'
                          }`}>
                            {focalState.label}
                          </span>
                        </div>
                        <p className="text-[11px] text-[#64748B] truncate mt-0.5">
                          {focalState.subtext}
                        </p>
                      </div>
                    </div>

                    {/* Right Flow Stepper (Two-Phase Integrated Track) */}
                    <div className="flex-1 max-w-lg flex items-center gap-2 bg-white px-3 py-2 rounded-xl border border-black/[0.05]">
                      {/* Step 1: 草稿装配 */}
                      <div className="flex-1 min-w-0 space-y-1">
                        <div className="flex items-center justify-between text-[11px]">
                          <span className={`font-extrabold flex items-center gap-1 truncate ${
                            isDraftAbnormal
                              ? 'text-rose-700'
                              : isDraftRunning
                              ? 'text-emerald-800'
                              : isDraftDone
                              ? 'text-slate-800'
                              : 'text-slate-400'
                          }`}>
                            {isDraftDone ? (
                              <Check className="w-3 h-3 text-emerald-600 shrink-0 stroke-[3]" />
                            ) : (
                              <span className="w-1.5 h-1.5 rounded-full bg-current shrink-0" />
                            )}
                            1. 草稿装配
                          </span>
                          <span className="font-mono text-[10px] text-slate-400 font-bold shrink-0">
                            {isDraftAbnormal ? '异常' : isDraftRunning ? `${task.draftStage.progress}%` : isDraftDone ? '已完成' : '等待'}
                          </span>
                        </div>
                        <div className="w-full h-1.5 bg-slate-100 rounded-full overflow-hidden">
                          <div
                            className={`h-full rounded-full transition-all duration-300 ${
                              isDraftAbnormal
                                ? 'bg-rose-500'
                                : isDraftRunning
                                ? 'bg-emerald-500'
                                : isDraftDone
                                ? 'bg-slate-700'
                                : 'bg-transparent'
                            }`}
                            style={{ width: isDraftDone ? '100%' : `${task.draftStage.progress || 0}%` }}
                          />
                        </div>
                      </div>

                      {/* Stepper Arrow */}
                      <div className={`shrink-0 px-0.5 ${isDraftDone ? 'text-slate-600' : 'text-slate-300'}`}>
                        <ArrowRight className="w-3.5 h-3.5 stroke-[2.5]" />
                      </div>

                      {/* Step 2: 视频导出 */}
                      <div className="flex-1 min-w-0 space-y-1">
                        <div className="flex items-center justify-between text-[11px]">
                          <span className={`font-extrabold flex items-center gap-1 truncate ${
                            isVideoAbnormal
                              ? 'text-rose-700'
                              : isVideoRunning
                              ? 'text-emerald-800'
                              : isVideoDone
                              ? 'text-slate-800'
                              : 'text-slate-400'
                          }`}>
                            {isVideoDone ? (
                              <Check className="w-3 h-3 text-emerald-600 shrink-0 stroke-[3]" />
                            ) : (
                              <span className="w-1.5 h-1.5 rounded-full bg-current shrink-0" />
                            )}
                            2. 剪映导出
                          </span>
                          <span className="font-mono text-[10px] text-slate-400 font-bold shrink-0">
                            {videoPhaseLabel || (isVideoAbnormal ? '异常' : isVideoRunning ? `${task.videoStage.progress}%` : isVideoDone ? '已完成' : isVideoWaiting ? '排队' : '未开始')}
                          </span>
                        </div>
                        <div className="w-full h-1.5 bg-slate-100 rounded-full overflow-hidden">
                          <div
                            className={`h-full rounded-full transition-all duration-300 ${
                              isVideoAbnormal
                                ? 'bg-rose-500'
                                : isVideoRunning
                                ? 'bg-emerald-500'
                                : isVideoDone
                                ? 'bg-[#1A1D2E]'
                                : isVideoWaiting
                                ? 'bg-amber-400'
                                : 'bg-transparent'
                            }`}
                            style={{ width: isVideoDone ? '100%' : `${task.videoStage.progress || (isVideoWaiting ? 15 : 0)}%` }}
                          />
                        </div>
                      </div>
                    </div>
                  </div>

                  {/* Abnormal Callout Alert (Displays clearly when something failed or timed out) */}
                  {isOverallAbnormal && (
                    <div className="p-3 rounded-xl bg-rose-50 border border-rose-200 text-rose-900 flex flex-col sm:flex-row sm:items-center justify-between gap-2.5 animate-in fade-in">
                      <div className="flex items-start gap-2 text-xs">
                        <AlertTriangle className="w-4 h-4 text-rose-600 shrink-0 mt-0.5" />
                        <div>
                          <p className="font-extrabold text-rose-900">
                            {isDraftAbnormal
                              ? `【草稿阶段异常】${task.draftStage.errorDetail || '组装中断或超时'}`
                              : `【视频阶段异常】${task.videoStage.errorDetail || '剪映渲染中断或超时'}`}
                          </p>
                          <p className="text-[11px] text-rose-700 mt-0.5">
                            {isDraftAbnormal
                              ? isTemplate
                                ? '草稿异常，请点击右侧【重新生成】重新构建模板'
                                : '草稿异常，请点击右侧【重试】重新调度'
                              : isTemplate && task.hasCompletedFirstExport
                                ? '之前的正式模板视频已保留并可使用；这次新版本导出未成功，可按需点击右侧【重新导出】。'
                                : '草稿已完好保留，仅需点击右侧【重新导出】即可重新渲染'}
                          </p>
                        </div>
                      </div>

                      {/* Right Action Button Inside Alert for immediate recovery */}
                      <div className="shrink-0 flex items-center gap-1.5 self-end sm:self-auto">
                        {canRegenerate && (
                          <button
                            onClick={() => onRegenerateDraft(task)}
                            className="flex items-center gap-1 px-3 py-1.5 rounded-xl bg-amber-500 hover:bg-amber-600 text-xs font-black text-white shadow-xs transition-all active:scale-95 cursor-pointer"
                          >
                            <RefreshCw className="w-3.5 h-3.5" />
                            <span>重新生成</span>
                          </button>
                        )}

                        {canRetry && (
                          <button
                            onClick={() => onRetryTask(task)}
                            className="flex items-center gap-1 px-3 py-1.5 rounded-xl bg-rose-600 hover:bg-rose-700 text-xs font-black text-white shadow-xs transition-all active:scale-95 cursor-pointer"
                          >
                            <RotateCcw className="w-3.5 h-3.5" />
                            <span>重试</span>
                          </button>
                        )}

                        {canReExport && (
                          <button
                            onClick={() => onReExportVideo(task)}
                            className="flex items-center gap-1 px-3 py-1.5 rounded-xl bg-[#1A1D2E] hover:bg-black text-xs font-black text-[#DDFD00] shadow-xs transition-all active:scale-95 cursor-pointer"
                          >
                            <Video className="w-3.5 h-3.5" />
                            <span>重新导出</span>
                          </button>
                        )}
                      </div>
                    </div>
                  )}

                  {/* Bottom Row: Footnote Stats & Secondary Actions */}
                  <div className="flex flex-wrap items-center justify-between gap-3 pt-0.5 text-xs text-[#64748B]">
                    {/* Left Timing Narrative */}
                    <div className="flex items-center gap-2.5 text-[11px] flex-wrap">
                      {isOverallRunning ? (
                        <div className="flex items-center gap-1.5 font-bold text-emerald-800">
                          <span className="w-2 h-2 rounded-full bg-emerald-500 animate-ping" />
                          <span>已执行: <strong className="font-mono text-[#1A1D2E]">{taskElapsedLabel(task.durationSeconds, task.durationFormatted)}</strong></span>
                        </div>
                      ) : isOverallDone ? (
                        <div className="flex items-center gap-2 text-slate-700 font-medium">
                          <span>总耗时: <strong className="font-mono font-bold text-[#1A1D2E]">{taskElapsedLabel(task.durationSeconds, task.durationFormatted)}</strong></span>
                          {task.fileSizeMb && (
                            <>
                              <span>·</span>
                              <span>产物文件: <strong className="font-mono text-emerald-700 font-bold">{task.fileSizeMb.toFixed(1)}MB</strong></span>
                            </>
                          )}
                        </div>
                      ) : !isOverallAbnormal ? (
                        <div className="flex items-center gap-1 text-slate-500 font-medium">
                          <span>{task.durationSeconds > 0 ? taskElapsedLabel(task.durationSeconds) : '尚未开始'}</span>
                        </div>
                      ) : null}
                    </div>

                    {/* Right Footnote Actions (Only for completed or non-abnormal tasks) */}
                    <div className="flex items-center gap-2 shrink-0 ml-auto">
                      {/* Completed Task Options */}
                      {canRegenerate && isTemplate && !isOverallAbnormal && (
                        <>
                          <button
                            onClick={() => onRegenerateDraft(task)}
                            className="flex items-center gap-1 px-2.5 py-1 rounded-xl bg-slate-100 hover:bg-slate-200 text-[11px] font-bold text-slate-700 transition-all active:scale-95 cursor-pointer"
                          >
                            <RefreshCw className="w-3 h-3 text-slate-500" />
                            <span>重新生成</span>
                          </button>
                          <button
                            onClick={() => onReExportVideo(task)}
                            className="flex items-center gap-1 px-2.5 py-1 rounded-xl bg-slate-100 hover:bg-slate-200 text-[11px] font-bold text-slate-700 transition-all active:scale-95 cursor-pointer"
                          >
                            <Video className="w-3 h-3 text-slate-500" />
                            <span>重新导出</span>
                          </button>
                        </>
                      )}

                      {canReExport && isFinalVideo && !isOverallAbnormal && (
                        <button
                          onClick={() => onReExportVideo(task)}
                          className="flex items-center gap-1 px-2.5 py-1 rounded-xl bg-slate-100 hover:bg-slate-200 text-[11px] font-bold text-slate-700 transition-all active:scale-95 cursor-pointer"
                        >
                          <Video className="w-3 h-3 text-slate-500" />
                          <span>重新导出</span>
                        </button>
                      )}

                      {/* Diagnostic Drawer */}
                      <button
                        onClick={() => onViewTaskDetail(task)}
                        className="flex items-center gap-1 px-2.5 py-1 rounded-xl hover:bg-slate-100 text-[11px] font-bold text-slate-600 hover:text-[#1A1D2E] transition-all cursor-pointer"
                      >
                        <Bug className="w-3 h-3 text-slate-400" />
                        <span>诊断 / 详情</span>
                      </button>

                      {/* Expand paths */}
                      <button
                        onClick={() => toggleExpand(task.id)}
                        className="p-1 rounded-xl hover:bg-slate-100 text-slate-400 hover:text-slate-700 transition-colors cursor-pointer"
                        title={isExpanded ? '收起文件路径' : '展开文件路径'}
                      >
                        {isExpanded ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
                      </button>
                    </div>
                  </div>
                </div>

                {/* Inline Expandable File Path Drawer */}
                {isExpanded && (
                  <div className="px-4 pb-3.5 pt-2 border-t border-black/[0.04] bg-slate-50/80 space-y-2 text-xs text-[#64748B] animate-in fade-in duration-100">
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-2 text-[11px]">
                      {task.materialFullName && (
                        <div className="flex items-center gap-2 p-2 rounded-lg bg-white border border-black/[0.04]">
                          <span className="text-[#64748B] shrink-0 font-medium">源素材:</span>
                          <code className="text-[#1A1D2E] truncate font-mono">{task.materialFullName}</code>
                        </div>
                      )}

                      {task.draftPath && (
                        <div className="flex items-center gap-2 p-2 rounded-lg bg-white border border-black/[0.04]">
                          <span className="text-[#64748B] shrink-0 font-medium">剪映草稿:</span>
                          <code className="text-[#1A1D2E] truncate font-mono">{task.draftPath}</code>
                        </div>
                      )}

                      {task.outputPath && (
                        <div className="flex items-center gap-2 p-2 rounded-lg bg-white border border-black/[0.04]">
                          <span className="text-[#64748B] shrink-0 font-medium">成片产物:</span>
                          <code className="text-emerald-700 font-bold truncate font-mono">
                            {task.outputPath} {task.fileSizeMb ? `(${task.fileSizeMb}MB)` : ''}
                          </code>
                        </div>
                      )}
                    </div>
                  </div>
                )}
              </div>
            );
          })
        )}
      </div>
    </div>
  );
};
