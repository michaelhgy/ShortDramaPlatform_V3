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
  ArrowRight,
  Ban
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
  /** 手动调整生产顺序；顺序同时决定三个执行器先做谁（后端统一算，两边不会不一致）。 */
  onReorderUnit?: (productionTaskId: string, action: 'top' | 'up' | 'down') => void;
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

/**
 * 一行素材的全部状态判断集中在这里。
 *
 * 卡片上的"状态"必须是**唯一一处**判断，否则又会出现同一个状态在卡片里
 * 被写成三种说法（历史问题）。用户要求：不看颜色也能分辨这四种状态。
 */
interface MaterialRow {
  task: TaskItem;
  sequence: number;
  statusWord: 'completed' | 'exporting' | 'drafting' | 'queued' | 'abnormal';
  statusText: string;
  progress: number | null;
  detail: string;
}

function toMaterialRow(task: TaskItem): MaterialRow {
  const draftStatus = task.draftStage.status;
  const videoStatus = task.videoStage.status;
  const isAbnormal = draftStatus === 'error' || draftStatus === 'timeout' || videoStatus === 'error' || videoStatus === 'timeout';

  if (isAbnormal) {
    const draftSide = draftStatus === 'error' || draftStatus === 'timeout';
    return {
      task,
      sequence: task.sequenceNo ?? 0,
      statusWord: 'abnormal',
      statusText: draftSide ? '草稿异常' : '导出异常',
      progress: null,
      detail: draftSide
        ? (task.draftStage.errorDetail || '组装中断或超时')
        : (task.videoStage.errorDetail || '剪映渲染中断或超时'),
    };
  }

  if (videoStatus === 'done' || task.status === 'done') {
    const totalSeconds = (task.draftStage.durationSeconds ?? 0) + (task.videoStage.durationSeconds ?? 0);
    const parts: string[] = [];
    if (totalSeconds > 0) parts.push(formatElapsedSeconds(totalSeconds));
    if (task.fileSizeMb) parts.push(`${task.fileSizeMb.toFixed(1)}MB`);
    return {
      task,
      sequence: task.sequenceNo ?? 0,
      statusWord: 'completed',
      statusText: '完成',
      progress: null,
      detail: parts.join(' · '),
    };
  }

  if (videoStatus === 'running') {
    return {
      task,
      sequence: task.sequenceNo ?? 0,
      statusWord: 'exporting',
      statusText: `导出中 ${task.videoStage.progress ?? 0}%`,
      progress: task.videoStage.progress ?? 0,
      detail: exportPhaseLabel(task.videoStage.rawStatus) || (task.durationSeconds > 0 ? `已耗时 ${taskElapsedLabel(task.durationSeconds)}` : ''),
    };
  }

  if (draftStatus === 'running') {
    return {
      task,
      sequence: task.sequenceNo ?? 0,
      statusWord: 'drafting',
      statusText: `草稿生成中 ${task.draftStage.progress ?? 0}%`,
      progress: task.draftStage.progress ?? 0,
      detail: task.durationSeconds > 0 ? `已耗时 ${taskElapsedLabel(task.durationSeconds)}` : '',
    };
  }

  // 草稿已生成、等导出；或整个任务还在排队。两者对用户都是"排队"，但话要说清。
  const waitingText = draftStatus === 'done' ? '待导出' : '排队';
  const detail = draftStatus === 'done'
    ? (task.hasCompletedFirstExport === false && task.taskCategory === 'template' ? '模板草稿已就绪，等待导出' : '草稿已就绪，等待导出')
    : '等待调度';
  return {
    task,
    sequence: task.sequenceNo ?? 0,
    statusWord: 'queued',
    statusText: waitingText,
    progress: null,
    detail,
  };
}

/** 一个账号 × 剧集分组的汇总数字与状态。 */
interface DramaGroup {
  key: string;
  accountName: string;
  dramaName: string;
  scheduledPublishTime: string;
  sortTimestamp: number;
  priorityRank: number;
  /** 后端算出的「账号 × 剧集」生产顺序位次，与执行器取任务顺序同源。 */
  orderRank: number;
  templateTask?: TaskItem;
  rows: MaterialRow[];
  /** 与生产中心同一口径：视频=已导出的素材、草稿=草稿已生成的素材（含模板草稿）、素材=已登记素材条数 */
  videoCount: number;
  draftCount: number;
  materialCount: number;
  /** 模板异常 + 素材异常，都算（用户 2026-09-19："异常都算"）。 */
  abnormalCount: number;
  /** 只有素材行异常的数量，用来决定组头是红框还是橙框。 */
  materialAbnormalCount: number;
  templateAbnormal: boolean;
  runningCount: number;
  /** 此刻真正在做这个组的执行器（可能同时有 2~3 个，也可能一个都没有）。 */
  activeExecutors: Array<'template' | 'final' | 'export'>;
  firstCreatedAt: string;
}

const EXECUTOR_LABEL: Record<'template' | 'final' | 'export', string> = {
  template: '模板生成中',
  final: '成片生成中',
  export: '视频导出中',
};

function buildGroup(item: TaskItem, rows: TaskItem[]): DramaGroup {
  const materialRows = rows
    .filter((task) => task && task.taskCategory !== 'template')
    .map(toMaterialRow);
  const templateTask = rows.find((task) => task.taskCategory === 'template');
  // 素材就是素材，模板不算素材（2026-09-19 修正：原来把模板当成第 N+1 条素材，
  // 导致「素材 11」比真实素材 10 条多一个，草稿数也跟着虚高）。
  const materialCount = materialRows.length;
  const videoCount = materialRows.filter((row) => row.statusWord === 'completed').length;
  const generatedDrafts = materialRows.filter((row) => row.statusWord === 'completed' || row.statusWord === 'exporting' || row.statusWord === 'queued').length;
  const templateDraftReady = Boolean(templateTask) && templateTask!.draftStage.status === 'done';
  const draftCount = generatedDrafts + (templateDraftReady ? 1 : 0);
  const materialAbnormalCount = materialRows.filter((row) => row.statusWord === 'abnormal').length;
  const templateRow = templateTask ? toMaterialRow(templateTask) : null;
  const templateAbnormal = templateRow?.statusWord === 'abnormal';
  const abnormalCount = materialAbnormalCount + (templateAbnormal ? 1 : 0);
  const runningCount = materialRows.filter((row) => row.statusWord === 'exporting' || row.statusWord === 'drafting').length;

  // 一个组可以用三个执行器同时干活（调度每 0.5 秒同时尝试派模板/成片/导出）。
  // 所以这里是"正在做这个组的执行器清单"，不是单个执行器。
  const activeExecutors: Array<'template' | 'final' | 'export'> = [];
  if (templateTask && templateTask.draftStage.status === 'running') activeExecutors.push('template');
  if (materialRows.some((row) => row.statusWord === 'drafting')) activeExecutors.push('final');
  if (materialRows.some((row) => row.statusWord === 'exporting')) activeExecutors.push('export');

  const scheduled = item.scheduledPublishTime || '';
  const parsed = scheduled ? Date.parse(scheduled) : Number.NaN;
  return {
    key: item.productionTaskId || `fallback:${item.accountName}::${item.dramaName}`,
    accountName: item.accountName,
    dramaName: item.dramaName,
    scheduledPublishTime: scheduled,
    sortTimestamp: Number.isFinite(parsed) ? parsed : Number.MAX_SAFE_INTEGER,
    priorityRank: item.priorityRank,
    orderRank: item.orderRank ?? 0,
    templateTask,
    rows: materialRows,
    videoCount,
    draftCount,
    materialCount,
    abnormalCount,
    materialAbnormalCount,
    templateAbnormal,
    runningCount,
    activeExecutors,
    firstCreatedAt: rows.reduce((earliest, task) => (earliest === '' || task.createdAt < earliest ? task.createdAt : earliest), ''),
  };
}

export const TaskListSection: React.FC<TaskListSectionProps> = ({
  tasks,
  onRetryTask,
  onRegenerateDraft,
  onReExportVideo,
  onViewTaskDetail,
  onReorderUnit,
}) => {
  const [statusFilter, setStatusFilter] = useState<'all' | 'running' | 'abnormal' | 'waiting' | 'done'>('all');
  const [categoryFilter, setCategoryFilter] = useState<'all' | TaskCategory>('all');
  const [dramaFilter, setDramaFilter] = useState<string>('all');
  const [accountFilter, setAccountFilter] = useState<string>('all');
  const [searchQuery, setSearchQuery] = useState<string>('');
  // 一次只展开一个组：默认全收起，9 个组头一眼看完今天要做什么。
  const [expandedGroupKey, setExpandedGroupKey] = useState<string | null>(null);

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

  // 顶部页签的计数按"素材条目"算，和分组里的行保持一致。
  const counts = useMemo(() => {
    const rows = tasks.map(toMaterialRow);
    const running = rows.filter(r => r.statusWord === 'exporting' || r.statusWord === 'drafting').length;
    const abnormal = rows.filter(r => r.statusWord === 'abnormal').length;
    const waiting = rows.filter(r => r.statusWord === 'queued').length;
    const done = rows.filter(r => r.statusWord === 'completed').length;
    return { all: rows.length, running, abnormal, waiting, done };
  }, [tasks]);

  /**
   * 排序（2026-09-19 用户拍板）：
   *   第 1 层 账号 × 剧集：计划发布时间早 → 开工时间早
   *   第 2 层 组内素材：序号升序；正在执行的那条拎到本组最前（只影响本组，不影响整组名次）
   * 特意**不再**按"执行中/排队/完成"分层排序 —— 那正是素材序号被排成 5,1,2,3,4 的原因。
   */
  const groups = useMemo(() => {
    const filtered = tasks.filter(t => {
      if (categoryFilter !== 'all' && t.taskCategory !== categoryFilter) return false;
      if (dramaFilter !== 'all' && t.dramaName !== dramaFilter) return false;
      if (accountFilter !== 'all' && t.accountName !== accountFilter) return false;
      if (searchQuery.trim()) {
        const q = searchQuery.toLowerCase();
        const haystack = [t.title, t.dramaName, t.accountName, t.materialName, t.materialFullName, t.id]
          .filter(Boolean)
          .join(' ')
          .toLowerCase();
        if (!haystack.includes(q)) return false;
      }
      return true;
    });

    const byUnit = new Map<string, TaskItem[]>();
    filtered.forEach(task => {
      const key = task.productionTaskId || `fallback:${task.accountName}::${task.dramaName}`;
      const bucket = byUnit.get(key);
      if (bucket) bucket.push(task);
      else byUnit.set(key, [task]);
    });

    const built = Array.from(byUnit.values()).map(rows => buildGroup(rows[0], rows));

    built.forEach(group => {
      group.rows.sort((a, b) => {
        const aActive = a.statusWord === 'exporting' || a.statusWord === 'drafting' ? 0 : 1;
        const bActive = b.statusWord === 'exporting' || b.statusWord === 'drafting' ? 0 : 1;
        if (aActive !== bActive) return aActive - bActive;
        return a.sequence - b.sequence || a.task.createdAt.localeCompare(b.task.createdAt);
      });
    });

    const visible = built.filter(group => {
      if (statusFilter === 'all') return true;
      if (statusFilter === 'running') return group.runningCount > 0;
      if (statusFilter === 'abnormal') return group.abnormalCount > 0;
      if (statusFilter === 'waiting') return group.rows.some(row => row.statusWord === 'queued');
      if (statusFilter === 'done') return group.materialCount > 0 && group.videoCount === group.materialCount;
      return true;
    });

    return visible.sort((a, b) => {
      // 已做完的整部剧沉到最后（用户 2026-09-19 选定）
      const aDone = a.materialCount > 0 && a.videoCount === a.materialCount ? 1 : 0;
      const bDone = b.materialCount > 0 && b.videoCount === b.materialCount ? 1 : 0;
      if (aDone !== bDone) return aDone - bDone;
      // 再做手动的位次；后端把"手动位次"和"执行器取任务顺序"算成同一个东西
      const aRank = a.orderRank > 0 ? a.orderRank : Number.MAX_SAFE_INTEGER;
      const bRank = b.orderRank > 0 ? b.orderRank : Number.MAX_SAFE_INTEGER;
      if (aRank !== bRank) return aRank - bRank;
      if (a.sortTimestamp !== b.sortTimestamp) return a.sortTimestamp - b.sortTimestamp;
      const created = a.firstCreatedAt.localeCompare(b.firstCreatedAt);
      if (created) return created;
      return a.accountName.localeCompare(b.accountName) || a.dramaName.localeCompare(b.dramaName);
    });
  }, [tasks, statusFilter, categoryFilter, dramaFilter, accountFilter, searchQuery]);

  const toggleGroup = (key: string) => {
    setExpandedGroupKey(prev => (prev === key ? null : key));
  };

  /** 组头那三段进度条：绿=视频，蓝=草稿（视频已含在内，所以画剩余部分），底=素材总数。 */
  const railSegments = (group: DramaGroup) => {
    const total = group.materialCount || 0;
    if (total === 0) return { exported: 0, remaining: 0 };
    const exported = Math.min(100, (group.videoCount / total) * 100);
    const drafts = Math.min(100 - exported, Math.max(0, ((group.draftCount - group.videoCount) / total) * 100));
    return { exported, remaining: drafts };
  };

  return (
    <div className="space-y-3.5">
      {/* Section Header */}
      <div className="flex flex-wrap items-center justify-between gap-3 px-1">
        <div className="flex items-center gap-2.5">
          <div className="w-2.5 h-2.5 rounded-full bg-[#1A1D2E]" />
          <h3 className="font-extrabold text-sm text-[#1A1D2E] tracking-tight">
            任务列表（按账号 × 剧集优先级）
          </h3>
          <span className="text-xs text-[#64748B] font-medium">
            共 {groups.length} 部剧 · 点组头展开素材
          </span>
        </div>

        {/* Legend：图例必须解释卡片上真实存在的颜色 */}
        <div className="hidden lg:flex items-center gap-3 text-[11px] text-[#64748B]">
          <span className="flex items-center gap-1.5 font-medium">
            <span className="w-2 h-2 rounded-full bg-emerald-500" />
            视频已导出
          </span>
          <span className="flex items-center gap-1.5 font-medium">
            <span className="w-2 h-2 rounded-full bg-indigo-500" />
            草稿已生成
          </span>
          <span className="flex items-center gap-1.5 font-medium">
            <span className="w-2 h-2 rounded-full bg-slate-400" />
            素材总数
          </span>
        </div>
      </div>

      {/* Filter Control Bar */}
      <div className="bg-white rounded-2xl border border-black/[0.06] p-3 shadow-xs space-y-2.5">
        {/* Row 1: Status Tabs & Search Box */}
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="flex items-center gap-1 p-1 bg-slate-100/90 rounded-xl overflow-x-auto">
            <button
              onClick={() => setStatusFilter('all')}
              className={`px-3 py-1.5 rounded-lg text-xs font-bold transition-all cursor-pointer whitespace-nowrap ${
                statusFilter === 'all' ? 'bg-white text-[#1A1D2E] shadow-2xs' : 'text-[#64748B] hover:text-[#1A1D2E]'
              }`}
            >
              全部 ({counts.all})
            </button>
            <button
              onClick={() => setStatusFilter('running')}
              className={`px-3 py-1.5 rounded-lg text-xs font-bold transition-all cursor-pointer whitespace-nowrap flex items-center gap-1.5 ${
                statusFilter === 'running' ? 'bg-white text-emerald-800 shadow-2xs' : 'text-[#64748B] hover:text-emerald-700'
              }`}
            >
              <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse" />
              执行中 ({counts.running})
            </button>
            <button
              onClick={() => setStatusFilter('abnormal')}
              className={`px-3 py-1.5 rounded-lg text-xs font-bold transition-all cursor-pointer whitespace-nowrap flex items-center gap-1.5 ${
                statusFilter === 'abnormal' ? 'bg-white text-rose-800 shadow-2xs' : 'text-[#64748B] hover:text-rose-700'
              }`}
            >
              {counts.abnormal > 0 && <span className="w-1.5 h-1.5 rounded-full bg-rose-500" />}
              异常 ({counts.abnormal})
            </button>
            <button
              onClick={() => setStatusFilter('waiting')}
              className={`px-3 py-1.5 rounded-lg text-xs font-bold transition-all cursor-pointer whitespace-nowrap ${
                statusFilter === 'waiting' ? 'bg-white text-amber-800 shadow-2xs' : 'text-[#64748B] hover:text-amber-700'
              }`}
            >
              排队等待 ({counts.waiting})
            </button>
            <button
              onClick={() => setStatusFilter('done')}
              className={`px-3 py-1.5 rounded-lg text-xs font-bold transition-all cursor-pointer whitespace-nowrap ${
                statusFilter === 'done' ? 'bg-white text-slate-900 shadow-2xs' : 'text-[#64748B] hover:text-slate-900'
              }`}
            >
              已完成 ({counts.done})
            </button>
          </div>

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
          <div className="flex items-center gap-1.5">
            <span className="text-[#64748B] font-medium text-[11px]">业务类型:</span>
            <button
              onClick={() => setCategoryFilter('all')}
              className={`px-2.5 py-1 rounded-lg text-[11px] font-bold transition-all cursor-pointer ${
                categoryFilter === 'all' ? 'bg-[#1A1D2E] text-[#DDFD00]' : 'bg-slate-100 text-[#64748B] hover:text-[#1A1D2E]'
              }`}
            >
              全部
            </button>
            <button
              onClick={() => setCategoryFilter('template')}
              className={`px-2.5 py-1 rounded-lg text-[11px] font-bold transition-all cursor-pointer flex items-center gap-1 ${
                categoryFilter === 'template' ? 'bg-amber-500 text-white shadow-2xs' : 'bg-slate-100 text-[#64748B] hover:text-[#1A1D2E]'
              }`}
            >
              <Sparkles className="w-3 h-3" />
              模板制作
            </button>
            <button
              onClick={() => setCategoryFilter('final_video')}
              className={`px-2.5 py-1 rounded-lg text-[11px] font-bold transition-all cursor-pointer flex items-center gap-1 ${
                categoryFilter === 'final_video' ? 'bg-indigo-600 text-white shadow-2xs' : 'bg-slate-100 text-[#64748B] hover:text-[#1A1D2E]'
              }`}
            >
              <Film className="w-3 h-3" />
              成片制作
            </button>
          </div>

          <div className="flex items-center gap-2 flex-wrap">
            <select
              value={dramaFilter}
              onChange={(e) => setDramaFilter(e.target.value)}
              className="px-2.5 py-1 bg-[#F8FAFC] border border-black/[0.06] rounded-lg text-xs font-bold text-[#1A1D2E] focus:outline-none cursor-pointer"
            >
              <option value="all">全部剧集 ({uniqueDramas.length})</option>
              {uniqueDramas.map((drama) => (
                <option key={drama} value={drama}>《{drama}》</option>
              ))}
            </select>

            <select
              value={accountFilter}
              onChange={(e) => setAccountFilter(e.target.value)}
              className="px-2.5 py-1 bg-[#F8FAFC] border border-black/[0.06] rounded-lg text-xs font-bold text-[#1A1D2E] focus:outline-none cursor-pointer"
            >
              <option value="all">全部账号 ({uniqueAccounts.length})</option>
              {uniqueAccounts.map((acc) => (
                <option key={acc} value={acc}>{acc}</option>
              ))}
            </select>
          </div>
        </div>
      </div>

      {/* Grouped Task List */}
      <div className="space-y-2">
        {groups.length === 0 ? (
          <div className="py-12 px-4 bg-white rounded-2xl border border-black/[0.06] text-center text-xs text-[#64748B] space-y-2">
            <Info className="w-6 h-6 text-slate-300 mx-auto" />
            <p className="font-bold text-[#1A1D2E]">当前没有可显示的任务</p>
            <p className="text-[11px] text-slate-400">可能是筛选条件没有匹配，也可能是本地服务暂时读不到数据</p>
          </div>
        ) : (
          groups.map((group, index) => {
            const isExpanded = expandedGroupKey === group.key;
            const { exported, remaining } = railSegments(group);
            const allDone = group.materialCount > 0 && group.videoCount === group.materialCount;

            return (
              <div
                key={group.key}
                className={`rounded-2xl border bg-white transition-all duration-150 overflow-hidden ${
                  group.materialAbnormalCount > 0
                    ? 'border-rose-300 ring-2 ring-rose-500/10 shadow-xs'
                    : group.templateAbnormal
                    ? 'border-amber-300 ring-2 ring-amber-500/10 shadow-xs'
                    : group.runningCount > 0
                    ? 'border-emerald-400 ring-2 ring-emerald-500/10 shadow-xs'
                    : 'border-black/[0.06] hover:border-black/[0.12]'
                }`}
              >
                {/* 组头：账号 × 剧集只在这里出现一次 */}
                <div
                  onClick={() => toggleGroup(group.key)}
                  className="px-3.5 py-2.5 flex items-center gap-3 cursor-pointer select-none"
                >
                  <span className="w-6 h-6 rounded-lg bg-[#1A1D2E] text-[#DDFD00] font-mono font-black text-[11px] flex items-center justify-center shrink-0">
                    {index + 1}
                  </span>

                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-1.5 min-w-0">
                      <span className="font-extrabold text-xs text-slate-700 truncate max-w-[130px] shrink-0">
                        {group.accountName}
                      </span>
                      <span className="text-slate-300 font-light text-xs shrink-0">×</span>
                      <span className="font-black text-xs text-[#1A1D2E] truncate">《{group.dramaName}》</span>
                      {allDone && group.abnormalCount === 0 && (
                        <span className="text-[10px] px-1.5 py-0.5 rounded-md bg-emerald-100 text-emerald-800 font-bold shrink-0">
                          全部完成
                        </span>
                      )}
                    </div>

                    {/* 组头三段数字 + 异常数 + 色条（口径与生产中心一致）。
                        素材数不含模板；异常 = 模板异常 + 素材异常，都算。 */}
                    <div className="mt-1 flex items-center gap-2">
                      <span className="flex items-center gap-1 text-[10px] font-bold text-[#64748B] shrink-0">
                        <span className="w-1.5 h-1.5 rounded-full bg-emerald-500" />
                        视频 <strong className="font-mono text-emerald-800">{group.videoCount}</strong>
                      </span>
                      <span className="flex items-center gap-1 text-[10px] font-bold text-[#64748B] shrink-0">
                        <span className="w-1.5 h-1.5 rounded-full bg-indigo-500" />
                        草稿 <strong className="font-mono text-indigo-800">{group.draftCount}</strong>
                      </span>
                      <span className="flex items-center gap-1 text-[10px] font-bold text-[#64748B] shrink-0">
                        <span className="w-1.5 h-1.5 rounded-full bg-slate-400" />
                        素材 <strong className="font-mono text-[#1A1D2E]">{group.materialCount}</strong>
                      </span>
                      <span
                        className={`flex items-center gap-1 text-[10px] font-bold shrink-0 ${
                          group.abnormalCount > 0 ? 'text-rose-700' : 'text-[#64748B]'
                        }`}
                        title={
                          group.abnormalCount === 0
                            ? '没有异常'
                            : `模板异常 ${group.templateAbnormal ? 1 : 0} 条 · 素材异常 ${group.materialAbnormalCount} 条`
                        }
                      >
                        <span className={`w-1.5 h-1.5 rounded-full ${group.abnormalCount > 0 ? 'bg-rose-500 animate-pulse' : 'bg-slate-400'}`} />
                        异常 <strong className={`font-mono ${group.abnormalCount > 0 ? 'text-rose-700' : 'text-[#1A1D2E]'}`}>{group.abnormalCount}</strong>
                      </span>

                      <span className="flex-1 min-w-[60px] h-1.5 rounded-full overflow-hidden flex bg-slate-200/70">
                        {exported > 0 && <span className="h-full bg-emerald-500" style={{ width: `${exported}%` }} />}
                        {remaining > 0 && <span className="h-full bg-indigo-500" style={{ width: `${remaining}%` }} />}
                      </span>
                    </div>

                    {/* 色条上方：此刻正在做这个组的执行器。有几个显示几个，没有就整行不占位。
                        一个组可以同时被 2~3 个执行器处理（调度每 0.5 秒同时尝试派模板/成片/导出）。 */}
                    {group.activeExecutors.length > 0 && (
                      <div className="mt-1 flex items-center gap-1.5 flex-wrap">
                        {group.activeExecutors.map((executor) => (
                          <span
                            key={executor}
                            className="flex items-center gap-1 text-[10px] font-bold text-emerald-800 bg-emerald-50 border border-emerald-200 rounded-md px-1.5 py-0.5"
                          >
                            <RefreshCw className="w-2.5 h-2.5 animate-spin" />
                            {EXECUTOR_LABEL[executor]}
                          </span>
                        ))}
                      </div>
                    )}
                  </div>

                  <div className="flex items-center gap-1.5 shrink-0">
                    {/* 手动调整生产顺序：这个顺序同时是三个执行器的取任务顺序 */}
                    {onReorderUnit && !allDone && (
                      <span
                        className="flex items-center gap-0.5"
                        onClick={(event) => event.stopPropagation()}
                      >
                        <button
                          onClick={() => onReorderUnit(group.key, 'top')}
                          disabled={index === 0}
                          className="px-1 py-0.5 rounded-md bg-slate-100 hover:bg-[#1A1D2E] hover:text-[#DDFD00] text-slate-600 text-[10px] font-bold transition-colors cursor-pointer disabled:opacity-30 disabled:cursor-not-allowed"
                          title="置顶：让三个执行器下一个就做这部剧"
                        >
                          置顶
                        </button>
                        <button
                          onClick={() => onReorderUnit(group.key, 'up')}
                          disabled={index === 0}
                          className="p-0.5 rounded-md bg-slate-100 hover:bg-slate-200 text-slate-600 transition-colors cursor-pointer disabled:opacity-30 disabled:cursor-not-allowed"
                          title="上移一位"
                        >
                          <ChevronUp className="w-3 h-3" />
                        </button>
                        <button
                          onClick={() => onReorderUnit(group.key, 'down')}
                          disabled={index === groups.length - 1}
                          className="p-0.5 rounded-md bg-slate-100 hover:bg-slate-200 text-slate-600 transition-colors cursor-pointer disabled:opacity-30 disabled:cursor-not-allowed"
                          title="下移一位"
                        >
                          <ChevronDown className="w-3 h-3" />
                        </button>
                      </span>
                    )}

                    <span className="flex items-center gap-1 text-[10px] font-bold text-slate-600 bg-slate-100 px-1.5 py-0.5 rounded-md border border-black/[0.04]">
                      <Clock className="w-2.5 h-2.5 text-slate-500" />
                      {group.scheduledPublishTime ? formatTaskDateTime(group.scheduledPublishTime) : '未设置'}
                    </span>
                    <button
                      onClick={(event) => { event.stopPropagation(); toggleGroup(group.key); }}
                      className="p-0.5 rounded-md hover:bg-slate-100 text-slate-400 hover:text-slate-700 transition-colors cursor-pointer"
                      title={isExpanded ? '收起素材列表' : '展开素材列表'}
                    >
                      {isExpanded ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
                    </button>
                  </div>
                </div>

                {/* 展开后的素材列表 */}
                {isExpanded && (
                  <div className="border-t border-black/[0.05] bg-[#FCFDFE]">
                    {group.templateTask && (
                      <MaterialLine
                        key={group.templateTask.id}
                        row={toMaterialRow(group.templateTask)}
                        isTemplate
                        onRetryTask={onRetryTask}
                        onRegenerateDraft={onRegenerateDraft}
                        onReExportVideo={onReExportVideo}
                        onViewTaskDetail={onViewTaskDetail}
                      />
                    )}

                    {group.rows.length === 0 && !group.templateTask ? (
                      <div className="px-4 py-3 text-[11px] text-slate-400">这部剧还没有可显示的素材任务</div>
                    ) : (
                      group.rows.map((row) => (
                        <MaterialLine
                          key={row.task.id}
                          row={row}
                          onRetryTask={onRetryTask}
                          onRegenerateDraft={onRegenerateDraft}
                          onReExportVideo={onReExportVideo}
                          onViewTaskDetail={onViewTaskDetail}
                        />
                      ))
                    )}
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

/**
 * 一条素材行。
 *
 * 2026-09-19 用户纠正："你这1234是干嘛？有什么用？放素材名啊，放1234干嘛"。
 * 素材的身份就是**文件名**（`神农宝库，医武镇九州-3.mp4`），序号只是文件名里的一段，
 * 单独拎出来用户根本对不上哪条是哪条。所以第一列永远是素材名，序号不再单独成列。
 *
 * 四列各讲一件事：素材名 / 状态 / 进度 / 产物。
 * 不在这里加第五样东西 —— 每加一个元素都会直接变成"看着很累"。
 */
const MaterialLine: React.FC<{
  row: MaterialRow;
  isTemplate?: boolean;
  onRetryTask: (task: TaskItem) => void;
  onRegenerateDraft: (task: TaskItem) => void;
  onReExportVideo: (task: TaskItem) => void;
  onViewTaskDetail: (task: TaskItem) => void;
}> = ({ row, isTemplate = false, onRetryTask, onRegenerateDraft, onReExportVideo, onViewTaskDetail }) => {
  const { task, statusWord, statusText, detail } = row;
  const allowedActions = getTaskCenterActions(task);
  const canRetry = allowedActions.includes('retry');
  const canRegenerate = allowedActions.includes('regenerate');
  const canReExport = allowedActions.includes('reExport');
  const isAbnormal = statusWord === 'abnormal';

  const materialLabel = isTemplate ? '模板草稿' : (task.materialFullName || task.materialName || '（未记录素材名）');

  const statusStyle = isAbnormal
    ? 'text-rose-700'
    : statusWord === 'exporting'
    ? 'text-emerald-700'
    : statusWord === 'drafting'
    ? 'text-sky-700'
    : statusWord === 'completed'
    ? 'text-slate-500'
    : 'text-amber-700';

  // 耗时与大小分成两段：数字用等宽字体，大小单独右对齐，才能上下比较。
  const [durationText, sizeText] = detail.includes(' · ') ? detail.split(' · ') : [detail, ''];

  return (
    <div
      className={`group/line px-3.5 py-1 flex items-center gap-3 border-b border-black/[0.03] last:border-b-0 transition-colors ${
        isAbnormal ? 'bg-rose-50/40' : 'hover:bg-white'
      }`}
    >
      {/* 第 1 列：素材名（主信息） */}
      <span
        className={`shrink-0 w-[252px] truncate text-[11px] ${
          isTemplate ? 'font-bold text-amber-800' : 'text-[#1A1D2E] font-medium'
        }`}
        title={materialLabel}
      >
        {materialLabel}
      </span>

      {/* 第 2 列：状态。完成了只给一个 ✓，不写"完成"两个字 */}
      <span className={`shrink-0 w-[96px] flex items-center gap-1 text-[11px] font-extrabold ${statusStyle}`}>
        {statusWord === 'completed' ? (
          <Check className="w-3 h-3 text-emerald-600 shrink-0 stroke-[3]" />
        ) : statusWord === 'abnormal' ? (
          <AlertTriangle className="w-3 h-3 text-rose-600 shrink-0" />
        ) : statusWord === 'exporting' || statusWord === 'drafting' ? (
          <RefreshCw className="w-3 h-3 shrink-0 animate-spin" />
        ) : (
          <Ban className="w-3 h-3 text-amber-500 shrink-0" />
        )}
        {statusWord !== 'completed' && <span className="truncate">{statusText}</span>}
      </span>

      {/* 第 3 列：进度。只有真的在跑才画，其余行这一列是空的 —— 空轨道配"完成"是自相矛盾 */}
      <span className="shrink-0 w-[104px] flex items-center gap-1.5">
        {row.progress !== null ? (
          <>
            <span className="flex-1 h-1.5 rounded-full bg-slate-100 overflow-hidden">
              <span
                className={`block h-full rounded-full transition-all duration-300 ${statusWord === 'drafting' ? 'bg-sky-500' : 'bg-emerald-500'}`}
                style={{ width: `${row.progress}%` }}
              />
            </span>
            <span className="font-mono text-[10px] font-bold text-slate-500 w-[28px] text-right">{row.progress}%</span>
          </>
        ) : null}
      </span>

      {/* 第 4 列：产物 / 异常原因 */}
      <span className="flex-1 min-w-0 flex items-center gap-3 text-[11px]">
        {isAbnormal ? (
          <span className="text-rose-700 truncate">{detail}</span>
        ) : (
          <>
            <span className="flex-1" />
            <span className="font-mono text-slate-600 w-[62px] text-right shrink-0">{durationText || ''}</span>
            <span className="font-mono text-slate-500 w-[74px] text-right shrink-0">{sizeText || ''}</span>
          </>
        )}
      </span>

      {/* 操作：异常行常驻（要你马上处理），其余行鼠标移上去才出现 */}
      <span className={`shrink-0 flex items-center gap-1 ${isAbnormal ? '' : 'opacity-0 group-hover/line:opacity-100'} transition-opacity`}>
        {canRegenerate && (
          <button
            onClick={() => onRegenerateDraft(task)}
            className="p-1 rounded-lg hover:bg-slate-100 text-slate-500 hover:text-amber-700 cursor-pointer"
            title="保留现有模板草稿，重新构建"
          >
            <Sparkles className="w-3 h-3" />
          </button>
        )}
        {canReExport && (
          <button
            onClick={() => onReExportVideo(task)}
            className="px-1.5 py-0.5 rounded-lg bg-[#1A1D2E] text-[#DDFD00] text-[10px] font-bold hover:bg-black cursor-pointer whitespace-nowrap"
            title="保留现有草稿，重新排入视频导出队列"
          >
            重新导出
          </button>
        )}
        {canRetry && (
          <button
            onClick={() => onRetryTask(task)}
            className="p-1 rounded-lg hover:bg-rose-50 text-rose-600 cursor-pointer"
            title="结束当前任务并重新执行"
          >
            <RotateCcw className="w-3 h-3" />
          </button>
        )}
        <button
          onClick={() => onViewTaskDetail(task)}
          className="p-1 rounded-lg hover:bg-slate-100 text-slate-400 hover:text-[#1A1D2E] cursor-pointer"
          title="诊断 / 详情"
        >
          <Bug className="w-3 h-3" />
        </button>
      </span>
    </div>
  );
};
