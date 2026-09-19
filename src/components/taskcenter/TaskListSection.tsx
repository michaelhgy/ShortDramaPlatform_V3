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
  templateTask?: TaskItem;
  rows: MaterialRow[];
  /** 与生产中心同一口径：视频=已导出、草稿=草稿已生成（含模板草稿）、素材=本组条目总数 */
  videoCount: number;
  draftCount: number;
  materialCount: number;
  abnormalCount: number;
  runningCount: number;
  firstCreatedAt: string;
}

function buildGroup(item: TaskItem, rows: TaskItem[]): DramaGroup {
  const materialRows = rows
    .filter((task) => task && task.taskCategory !== 'template')
    .map(toMaterialRow);
  const templateTask = rows.find((task) => task.taskCategory === 'template');
  const materialCount = materialRows.length + (templateTask ? 1 : 0);
  const videoCount = materialRows.filter((row) => row.statusWord === 'completed').length;
  const generatedDrafts = materialRows.filter((row) => row.statusWord === 'completed' || row.statusWord === 'exporting' || row.statusWord === 'queued').length;
  const templateDraftReady = Boolean(templateTask) && templateTask!.draftStage.status === 'done';
  const draftCount = generatedDrafts + (templateDraftReady ? 1 : 0);
  const abnormalCount = materialRows.filter((row) => row.statusWord === 'abnormal').length;
  const runningCount = materialRows.filter((row) => row.statusWord === 'exporting' || row.statusWord === 'drafting').length;
  const scheduled = item.scheduledPublishTime || '';
  const parsed = scheduled ? Date.parse(scheduled) : Number.NaN;
  return {
    key: item.productionTaskId || `fallback:${item.accountName}::${item.dramaName}`,
    accountName: item.accountName,
    dramaName: item.dramaName,
    scheduledPublishTime: scheduled,
    sortTimestamp: Number.isFinite(parsed) ? parsed : Number.MAX_SAFE_INTEGER,
    priorityRank: item.priorityRank,
    templateTask,
    rows: materialRows,
    videoCount,
    draftCount,
    materialCount,
    abnormalCount,
    runningCount,
    firstCreatedAt: rows.reduce((earliest, task) => (earliest === '' || task.createdAt < earliest ? task.createdAt : earliest), ''),
  };
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
                  group.abnormalCount > 0
                    ? 'border-rose-300 ring-2 ring-rose-500/10 shadow-xs'
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
                      {group.abnormalCount > 0 && (
                        <span className="text-[10px] px-1.5 py-0.5 rounded-md bg-rose-100 text-rose-800 font-bold shrink-0">
                          ⚠ {group.abnormalCount} 条异常
                        </span>
                      )}
                      {allDone && group.abnormalCount === 0 && (
                        <span className="text-[10px] px-1.5 py-0.5 rounded-md bg-emerald-100 text-emerald-800 font-bold shrink-0">
                          全部完成
                        </span>
                      )}
                    </div>

                    {/* 组头三段数字 + 色条（口径与生产中心一致） */}
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

                      <span className="flex-1 min-w-[80px] h-1.5 rounded-full overflow-hidden flex bg-slate-200/70">
                        {exported > 0 && <span className="h-full bg-emerald-500" style={{ width: `${exported}%` }} />}
                        {remaining > 0 && <span className="h-full bg-indigo-500" style={{ width: `${remaining}%` }} />}
                      </span>
                    </div>
                  </div>

                  <div className="flex items-center gap-1.5 shrink-0">
                    <span className="flex items-center gap-1 text-[10px] font-bold text-slate-600 bg-slate-100 px-1.5 py-0.5 rounded-md border border-black/[0.04]">
                      <Clock className="w-2.5 h-2.5 text-slate-500" />
                      {group.scheduledPublishTime ? formatTaskDateTime(group.scheduledPublishTime) : '未设置'}
                    </span>
                    {isExpanded ? <ChevronUp className="w-4 h-4 text-slate-400" /> : <ChevronDown className="w-4 h-4 text-slate-400" />}
                  </div>
                </div>

                {/* 展开后的素材列表 */}
                {isExpanded && (
                  <div className="border-t border-black/[0.05] bg-[#FCFDFE]">
                    {group.templateTask && (
                      <MaterialLine
                        key={group.templateTask.id}
                        label="模板"
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
                          label={row.sequence > 0 ? String(row.sequence) : '—'}
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
 * 一条素材行。用户要求：一行只看四样东西 —— 序号、状态、进度、耗时/产物。
 * 这里是这四个元素的唯一渲染处；不要在这里再加标签或图标，
 * 每加一个元素都会直接变成"看着很累"。
 */
const MaterialLine: React.FC<{
  label: string;
  row: MaterialRow;
  isTemplate?: boolean;
  onRetryTask: (task: TaskItem) => void;
  onRegenerateDraft: (task: TaskItem) => void;
  onReExportVideo: (task: TaskItem) => void;
  onViewTaskDetail: (task: TaskItem) => void;
}> = ({ label, row, isTemplate = false, onRetryTask, onRegenerateDraft, onReExportVideo, onViewTaskDetail }) => {
  const { task, statusWord, statusText, detail } = row;
  const allowedActions = getTaskCenterActions(task);
  const canRetry = allowedActions.includes('retry');
  const canRegenerate = allowedActions.includes('regenerate');
  const canReExport = allowedActions.includes('reExport');

  const statusStyle = statusWord === 'abnormal'
    ? 'text-rose-700'
    : statusWord === 'exporting'
    ? 'text-emerald-700'
    : statusWord === 'drafting'
    ? 'text-sky-700'
    : statusWord === 'completed'
    ? 'text-slate-600'
    : 'text-amber-700';

  return (
    <div className="group/line px-3.5 py-1.5 flex items-center gap-3 border-b border-black/[0.03] last:border-b-0 hover:bg-white transition-colors">
      <span className={`shrink-0 font-mono font-black text-[12px] text-center ${isTemplate ? 'w-10 text-amber-700' : 'w-6 text-[#1A1D2E]'}`}>
        {label}
      </span>

      <span className={`shrink-0 w-[104px] flex items-center gap-1 text-[11px] font-extrabold ${statusStyle}`}>
        {statusWord === 'completed' ? (
          <Check className="w-3 h-3 text-emerald-600 shrink-0 stroke-[3]" />
        ) : statusWord === 'abnormal' ? (
          <AlertTriangle className="w-3 h-3 text-rose-600 shrink-0" />
        ) : statusWord === 'exporting' || statusWord === 'drafting' ? (
          <RefreshCw className="w-3 h-3 shrink-0 animate-spin" />
        ) : statusWord === 'queued' ? (
          <Ban className="w-3 h-3 text-amber-500 shrink-0" />
        ) : null}
        <span className="truncate">{statusText}</span>
      </span>

      {/* 进度轨：只有真的在跑才画，排队不画（画了会让人以为做了一半） */}
      <span className="shrink-0 w-[90px] h-1.5 rounded-full bg-slate-100 overflow-hidden">
        {row.progress !== null && (
          <span
            className={`block h-full rounded-full transition-all duration-300 ${statusWord === 'drafting' ? 'bg-sky-500' : 'bg-emerald-500'}`}
            style={{ width: `${row.progress}%` }}
          />
        )}
      </span>

      <span className="flex-1 min-w-0 text-[11px] text-[#64748B] truncate">{detail}</span>

      {/* 动作只在悬停或异常时出现，平时不占视线 */}
      <span className={`shrink-0 flex items-center gap-1 ${statusWord === 'abnormal' ? '' : 'opacity-0 group-hover/line:opacity-100'} transition-opacity`}>
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
            className="p-1 rounded-lg hover:bg-slate-100 text-slate-500 hover:text-[#1A1D2E] cursor-pointer"
            title="保留现有草稿，重新排入视频导出队列"
          >
            <Video className="w-3 h-3" />
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
