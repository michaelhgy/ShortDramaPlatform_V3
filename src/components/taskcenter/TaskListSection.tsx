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
  Bug, 
  ChevronDown, 
  ChevronUp, 
  Info,
  Check,
  ArrowRight
} from 'lucide-react';
import { TaskItem, TaskCategory } from './taskCenterTypes';
import { getTaskCenterActions } from './taskCenterActionPolicy';
import { formatTaskDateTime } from './taskCenterFormat';
import { formatElapsedSeconds, taskElapsedLabel } from '../../utils/duration';

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

        {/* Legend：图例必须解释卡片上真实存在的颜色，否则就是摆设。
            卡片现在的颜色语义 = 蓝=草稿在跑 / 绿=导出在跑或已完成 / 红=异常 / 浅灰=还没轮到。 */}
        <div className="hidden lg:flex items-center gap-3 text-[11px] text-[#64748B]">
          <span className="flex items-center gap-1.5 font-medium">
            <span className="w-2 h-2 rounded-full bg-sky-500" />
            草稿装配
          </span>
          <span className="flex items-center gap-1.5 font-medium">
            <span className="w-2 h-2 rounded-full bg-emerald-500" />
            剪映导出
          </span>
          <span className="flex items-center gap-1.5 font-medium">
            <span className="w-2 h-2 rounded-full bg-rose-500" />
            异常
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
            <p className="font-bold text-[#1A1D2E]">当前没有可显示的任务</p>
            <p className="text-[11px] text-slate-400">可能是筛选条件没有匹配，也可能是本地服务暂时读不到数据</p>
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
            const isDraftRunning = draftStatus === 'running';
            const isDraftDone = draftStatus === 'done';
            const isDraftAbnormal = draftStatus === 'error' || draftStatus === 'timeout';

            // Video Stage conditions
            const videoStatus = task.videoStage.status;
            const videoPhaseLabel = exportPhaseLabel(task.videoStage.rawStatus);
            const isVideoWaiting = videoStatus === 'waiting';
            const isVideoRunning = videoStatus === 'running';
            const isVideoDone = videoStatus === 'done';
            const isVideoAbnormal = videoStatus === 'error' || videoStatus === 'timeout';

            const allowedActions = getTaskCenterActions(task);
            const canRegenerate = allowedActions.includes('regenerate');
            const canRetry = allowedActions.includes('retry');
            const canReExport = allowedActions.includes('reExport');

            // 三个阶段耗时相加得到这张卡的真实总耗时。原来卡片上下两处
            // 分别写"总耗时"和"已执行"，它们说的其实是同一件事，这里是唯一出处。
            const totalSeconds = (task.draftStage.durationSeconds ?? 0) + (task.videoStage.durationSeconds ?? 0);

            // 卡片高度依赖这两条轨道的语义，必须先算清楚：
            // 「已完成」是 100%，「正在跑」用真实进度，「排队/未开始」留一条浅灰待办轨。
            const draftPercent = isDraftDone ? 100 : isDraftRunning ? (task.draftStage.progress ?? 0) : 0;
            const draftTrackClass = isDraftAbnormal
              ? 'bg-rose-500'
              : isDraftRunning
                ? 'bg-sky-500'
                : isDraftDone
                  ? 'bg-slate-700'
                  : 'bg-transparent';
            const videoPercent = isVideoDone ? 100 : isVideoRunning ? (task.videoStage.progress ?? 0) : isVideoWaiting ? 15 : 0;
            const videoTrackClass = isVideoAbnormal
              ? 'bg-rose-500'
              : isVideoRunning
                ? 'bg-emerald-500'
                : isVideoDone
                  ? 'bg-emerald-500'
                  : isVideoWaiting
                    ? 'bg-amber-400'
                    : 'bg-transparent';
            const draftValueLabel = isDraftAbnormal
              ? '异常'
              : isDraftRunning
                ? `${task.draftStage.progress ?? 0}%`
                : isDraftDone
                  ? '已完成'
                  : '等待';
            const videoValueLabel = videoPhaseLabel
              || (isVideoAbnormal ? '异常' : isVideoRunning ? `${task.videoStage.progress ?? 0}%` : isVideoDone ? '已完成' : isVideoWaiting ? '排队' : '未开始');

            return (
              <div
                key={task.id}
                className={`rounded-2xl border bg-white transition-all duration-150 overflow-hidden ${
                  isOverallAbnormal
                    ? 'border-rose-300 ring-2 ring-rose-500/10 shadow-xs'
                    : isOverallRunning
                    ? 'border-emerald-400 ring-2 ring-emerald-500/10 shadow-xs'
                    : 'border-black/[0.06] hover:border-black/[0.12]'
                }`}
              >
                <div className="px-3.5 py-2.5 space-y-2">
                  {/* 第 1 行：身份 + 发布时间 + 优先级（同一行讲完"我是谁"） */}
                  <div className="flex items-center justify-between gap-2 flex-wrap">
                    <div className="flex items-center gap-2 flex-wrap min-w-0">
                      {isTemplate ? (
                        <span className="inline-flex items-center gap-1 text-[10px] px-1.5 py-0.5 rounded-md font-black bg-amber-100 text-amber-900 border border-amber-300/80 shrink-0">
                          <Sparkles className="w-2.5 h-2.5 text-amber-700" />
                          模板
                        </span>
                      ) : (
                        <span className="inline-flex items-center gap-1 text-[10px] px-1.5 py-0.5 rounded-md font-black bg-indigo-50 text-indigo-800 border border-indigo-200 shrink-0">
                          <Film className="w-2.5 h-2.5 text-indigo-600" />
                          成片
                        </span>
                      )}

                      <span className="font-extrabold text-xs text-slate-800 tracking-tight truncate max-w-[130px]">
                        {task.accountName}
                      </span>
                      <span className="text-slate-300 font-light text-xs">×</span>
                      <h4 className="font-black text-xs text-[#1A1D2E] tracking-tight truncate max-w-[220px]">
                        《{task.dramaName}》
                      </h4>

                      {isFinalVideo && task.materialName ? (
                        <span className="px-1.5 py-0.5 rounded-md bg-slate-900 text-white font-mono font-extrabold text-[10px] shrink-0">
                          {task.materialName}
                        </span>
                      ) : isTemplate ? (
                        <span className="text-[10px] text-amber-900 bg-amber-50 px-1.5 py-0.5 rounded-md border border-amber-200 font-bold shrink-0">
                          通用母本
                        </span>
                      ) : null}
                    </div>

                    <div className="flex items-center gap-1.5 shrink-0 text-[10px]">
                      <span className="flex items-center gap-1 font-bold text-slate-600 bg-slate-100 px-1.5 py-0.5 rounded-md border border-black/[0.04]">
                        <Clock className="w-2.5 h-2.5 text-slate-500" />
                        {formatTaskDateTime(task.scheduledPublishTime)}
                      </span>

                      {task.priorityTag?.includes('模板') || task.priorityTag?.includes('最高') ? (
                        <span className="font-black px-1.5 py-0.5 rounded-md bg-amber-500/15 text-amber-950 border border-amber-500/30">
                          ⭐ 模板优先
                        </span>
                      ) : (
                        <span className="font-black px-1.5 py-0.5 rounded-md bg-[#1A1D2E] text-[#DDFD00] font-mono">
                          #{task.priorityRank}
                        </span>
                      )}
                    </div>
                  </div>

                  {/* 第 2 行：两阶段流程条（草稿装配 → 剪映导出）——状态与进度只在这里说一次 */}
                  <div className="flex items-center gap-2.5">
                    <div className="w-[132px] shrink-0 space-y-1">
                      <div className="flex items-center justify-between gap-1 text-[10px]">
                        <span className={`font-extrabold flex items-center gap-0.5 truncate ${
                          isDraftAbnormal ? 'text-rose-700' : isDraftRunning ? 'text-sky-800' : isDraftDone ? 'text-slate-800' : 'text-slate-400'
                        }`}>
                          {isDraftDone ? (
                            <Check className="w-2.5 h-2.5 text-emerald-600 shrink-0 stroke-[3]" />
                          ) : (
                            <span className="w-1.5 h-1.5 rounded-full bg-current shrink-0" />
                          )}
                          1.草稿装配
                        </span>
                        <span className={`font-mono font-bold shrink-0 ${
                          isDraftAbnormal ? 'text-rose-600' : isDraftDone ? 'text-slate-500' : isDraftRunning ? 'text-sky-700' : 'text-slate-400'
                        }`}>
                          {draftValueLabel}
                        </span>
                      </div>
                      <div className="w-full h-1.5 bg-slate-100 rounded-full overflow-hidden">
                        <div className={`h-full rounded-full transition-all duration-300 ${draftTrackClass}`} style={{ width: `${draftPercent}%` }} />
                      </div>
                    </div>

                    <ArrowRight className={`w-3 h-3 shrink-0 ${isDraftDone ? 'text-slate-500' : 'text-slate-300'}`} />

                    <div className="flex-1 min-w-[132px] space-y-1">
                      <div className="flex items-center justify-between gap-1 text-[10px]">
                        <span className={`font-extrabold flex items-center gap-0.5 truncate ${
                          isVideoAbnormal ? 'text-rose-700' : isVideoRunning ? 'text-emerald-800' : isVideoDone ? 'text-slate-800' : 'text-slate-400'
                        }`}>
                          {isVideoDone ? (
                            <Check className="w-2.5 h-2.5 text-emerald-600 shrink-0 stroke-[3]" />
                          ) : (
                            <span className="w-1.5 h-1.5 rounded-full bg-current shrink-0" />
                          )}
                          2.剪映导出
                        </span>
                        <span className={`font-mono font-bold shrink-0 ${
                          isVideoAbnormal ? 'text-rose-600' : isVideoDone ? 'text-slate-500' : isVideoRunning ? 'text-emerald-700' : isVideoWaiting ? 'text-amber-700' : 'text-slate-400'
                        }`}>
                          {videoValueLabel}
                        </span>
                      </div>
                      <div className="w-full h-1.5 bg-slate-100 rounded-full overflow-hidden">
                        <div className={`h-full rounded-full transition-all duration-300 ${videoTrackClass}`} style={{ width: `${videoPercent}%` }} />
                      </div>
                    </div>
                  </div>

                  {/* 异常摘要（只有真异常才出现，保留原来那句可执行的提示） */}
                  {isOverallAbnormal && (
                    <div className="flex items-center gap-1.5 text-[10px] text-rose-800 bg-rose-50 border border-rose-200 rounded-lg px-2 py-1">
                      <AlertTriangle className="w-3 h-3 text-rose-600 shrink-0" />
                      <span className="font-extrabold shrink-0">
                        {isDraftAbnormal ? '草稿异常' : '视频异常'}
                      </span>
                      <span className="truncate">
                        {isDraftAbnormal
                          ? (task.draftStage.errorDetail || '组装中断或超时')
                          : (task.videoStage.errorDetail || '剪映渲染中断或超时')}
                      </span>
                    </div>
                  )}

                  {/* 第 3 行：耗时/产物（只说一次）+ 操作 */}
                  <div className="flex items-center justify-between gap-2 pt-0.5">
                    <div className="flex items-center gap-2 text-[10px] text-[#64748B] min-w-0">
                      {isOverallRunning ? (
                        <span className="flex items-center gap-1 font-bold text-emerald-800 shrink-0">
                          <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse" />
                          已耗时 <strong className="font-mono text-[#1A1D2E]">{taskElapsedLabel(task.durationSeconds, task.durationFormatted)}</strong>
                        </span>
                      ) : isOverallDone ? (
                        <span className="shrink-0">
                          总耗时 <strong className="font-mono font-bold text-[#1A1D2E]">{totalSeconds > 0 ? formatElapsedSeconds(totalSeconds) : taskElapsedLabel(task.durationSeconds, task.durationFormatted)}</strong>
                        </span>
                      ) : (
                        <span className="shrink-0 text-slate-400">
                          {totalSeconds > 0 ? `已耗时 ${formatElapsedSeconds(totalSeconds)}` : '尚未开始'}
                        </span>
                      )}

                      {isOverallDone && task.fileSizeMb ? (
                        <span className="flex items-center gap-1 shrink-0">
                          <span className="text-slate-300">·</span>
                          产物 <strong className="font-mono text-emerald-700 font-bold">{task.fileSizeMb.toFixed(1)}MB</strong>
                        </span>
                      ) : null}
                    </div>

                    <div className="flex items-center gap-1 shrink-0">
                      {canRegenerate && isTemplate && !isOverallAbnormal && (
                        <button
                          onClick={() => onRegenerateDraft(task)}
                          className="flex items-center gap-0.5 px-1.5 py-0.5 rounded-lg bg-slate-100 hover:bg-slate-200 text-[10px] font-bold text-slate-700 transition-all active:scale-95 cursor-pointer"
                          title="保留现有模板草稿，重新构建"
                        >
                          <RefreshCw className="w-2.5 h-2.5 text-slate-500" />
                          <span>重新生成</span>
                        </button>
                      )}

                      {canReExport && !isOverallAbnormal && (
                        <button
                          onClick={() => onReExportVideo(task)}
                          className="flex items-center gap-0.5 px-1.5 py-0.5 rounded-lg bg-slate-100 hover:bg-slate-200 text-[10px] font-bold text-slate-700 transition-all active:scale-95 cursor-pointer"
                          title="保留现有草稿，重新排入视频导出队列"
                        >
                          <Video className="w-2.5 h-2.5 text-slate-500" />
                          <span>重新导出</span>
                        </button>
                      )}

                      {canRetry && !isOverallAbnormal && (
                        <button
                          onClick={() => onRetryTask(task)}
                          className="flex items-center gap-0.5 px-1.5 py-0.5 rounded-lg bg-rose-50 hover:bg-rose-100 text-[10px] font-bold text-rose-700 transition-all active:scale-95 cursor-pointer"
                          title="结束当前任务并重新执行"
                        >
                          <RotateCcw className="w-2.5 h-2.5" />
                          <span>重试</span>
                        </button>
                      )}

                      <button
                        onClick={() => onViewTaskDetail(task)}
                        className="p-1 rounded-lg hover:bg-slate-100 text-slate-500 hover:text-[#1A1D2E] transition-all cursor-pointer"
                        title="诊断 / 详情"
                      >
                        <Bug className="w-3 h-3" />
                      </button>

                      <button
                        onClick={() => toggleExpand(task.id)}
                        className="p-1 rounded-lg hover:bg-slate-100 text-slate-400 hover:text-slate-700 transition-colors cursor-pointer"
                        title={isExpanded ? '收起文件路径' : '展开文件路径'}
                      >
                        {isExpanded ? <ChevronUp className="w-3 h-3" /> : <ChevronDown className="w-3 h-3" />}
                      </button>
                    </div>
                  </div>
                </div>

                {/* Inline Expandable File Path Drawer */}
                {isExpanded && (
                  <div className="px-3.5 pb-2.5 pt-1.5 border-t border-black/[0.04] bg-slate-50/80 space-y-1.5 text-xs text-[#64748B] animate-in fade-in duration-100">
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-1.5 text-[11px]">
                      {task.materialFullName && (
                        <div className="flex items-center gap-2 p-1.5 rounded-lg bg-white border border-black/[0.04]">
                          <span className="text-[#64748B] shrink-0 font-medium">源素材:</span>
                          <code className="text-[#1A1D2E] truncate font-mono">{task.materialFullName}</code>
                        </div>
                      )}

                      {task.draftPath && (
                        <div className="flex items-center gap-2 p-1.5 rounded-lg bg-white border border-black/[0.04]">
                          <span className="text-[#64748B] shrink-0 font-medium">剪映草稿:</span>
                          <code className="text-[#1A1D2E] truncate font-mono">{task.draftPath}</code>
                        </div>
                      )}

                      {task.outputPath && (
                        <div className="flex items-center gap-2 p-1.5 rounded-lg bg-white border border-black/[0.04]">
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
