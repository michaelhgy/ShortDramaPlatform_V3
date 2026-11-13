import React, { useState, useMemo, useEffect, useRef } from 'react';
import { AccountCollectionRecords } from './AccountCollectionRecords';
import { CockpitModal } from './CockpitModal';
import { AccountAvatar } from '../AccountAvatar';
import { AccountLoginBadge } from './AccountLoginBadge';
import { BusinessAccountStatusBadge } from './BusinessAccountStatusBadge';
import { AccountProfileTotals } from './AccountProfileTotals';
import { useCollectionRuntime } from './useCollectionRuntime';
import { collectionToday, periodStart, planSummary, collectionStatusRows, collectionScenarios, scenarioCategories, taskAccountIds, collectionAccountSelectable, type CollectionScenario } from './geminiCollectionModel';
import { ACCOUNT_DISPLAY_SCOPES, matchesAccountScope, type AccountDisplayScope } from '../../services/accountVisibility';
import { buildCollectionRequest, supports } from './collectionPanelModel';
import { AccountInfo, TheaterInfo } from '../../types/shortDramaOps';
import {
  X,
  RefreshCw,
  CheckCircle2,
  AlertTriangle,
  Clock,
  Play,
  Square,
  RotateCcw,
  Layers,
  Film,
  DollarSign,
  ShieldAlert,
  Users,
  ChevronRight,
  ChevronDown,
  Sparkles,
  Info,
  Check,
  Database,
  Server,
  Sliders,
  Eye,
  Lock,
  ArrowRight,
  Filter,
  Search
} from 'lucide-react';

export type CollectionCategoryKey = 'daily_stats' | 'video_traffic' | 'optimization' | 'revenue';

export type AccountGapState = 
  | 'complete'         // 截至昨日已完整
  | 'missing_yesterday'// 仅缺昨日 (10-31)
  | 'missing_days'     // 缺近几日或部分字段待补缺
  | 'initial_backfill' // 新号首次接入，需向前倒查至连续7天全零边界
  | 'auth_expired'
  | 'unknown';    // 尚未取得采集元数据

export type TheaterRevenueMode = 'daily' | 'cumulative' | 'unknown';

export type ItemResultStatus =
  | 'pending'          // 排队等待中
  | 'running'          // 当前正在请求
  | 'added'            // 新增入库
  | 'updated'          // 更新已有记录
  | 'reused'           // 复用已有小V猫/本地有效记录
  | 'skipped'          // 跳过 (本地已完整有效)
  | 'source_unupdated' // 来源尚未出账/尚未更新
  | 'partial'          // 部分完成 (如中途停止或部分字段缺失)
  | 'failed'           // 请求失败 (保留原有效数据)
  | 'stopped';         // 随队列停止而未执行

export interface AccountCollectionProfile {
  account: AccountInfo;
  available: boolean;
  platformAvailable?: boolean;
  unavailableReason: string;
  optimizationNeedsCheck: boolean;
  lastFailed: boolean;
  dailyGapState: AccountGapState;
  dailyGapDesc: string;
  missingDates: string[];
  hasPartialFields?: boolean;
  historyBoundaryConfirmed: boolean;
  earliestActiveDate: string;
  videoTotalCount: number | null; // null 代表缺失，绝不填0
  followerCount: number | null;
  profileSourceTime: string; // 来源更新时间，不伪装成刚刷新
  recent7dVideoCount: number | null;
  uncollectedOptimizationCount: number | null;
  revenueMode: TheaterRevenueMode;
  revenueCollectorName?: string;
  revenueAvailable?: boolean;
  revenueState?: 'backfill' | 'missing' | 'complete' | 'unconfigured' | 'disabled';
  revenueStatusDesc: string;
  revenueUnupdated: boolean;
}

export interface CategoryExecutionItem {
  category: CollectionCategoryKey;
  status: ItemResultStatus;
  summaryText: string;
  detailBadge?: string;
  preservedOldData?: boolean;
  sourceTimeNote?: string;
}

export interface AccountExecutionRow {
  accountId: string;
  accountName: string;
  theaterName: string;
  revenueMode: TheaterRevenueMode;
  overallStatus: 'waiting' | 'running' | 'completed' | 'partial' | 'failed' | 'stopped' | 'skipped';
  categories: Partial<Record<CollectionCategoryKey, CategoryExecutionItem>>;
  errorReason?: string;
  profilePiggybacked?: {
    videos: number | null;
    followers: number | null;
    sourceUpdatedAt: string;
    isReusedCache: boolean;
  };
}

export interface ActiveJobSummary {
  isRunning: boolean;
  isStopping: boolean;
  status: 'idle' | 'running' | 'completed' | 'partial_failed' | 'stopped';
  completedAccounts: number;
  totalAccounts: number;
  currentAccountName?: string;
  currentActionText?: string;
  failedCount: number;
}

interface DataCollectionModalProps {
  isOpen: boolean;
  onClose: () => void;
  accounts: AccountInfo[];
  theaters: TheaterInfo[];
  defaultSelectedTheater?: string;
  defaultSelectedAccountId?: string;
  onJobStateChange?: (summary: ActiveJobSummary) => void;
  showToast?: (msg: string) => void;
  onDataSaved?: () => void;
  initialAccountIds?: string[];
}

// 收益来源类型由后端提供；不按剧场名字猜测。

export const DataCollectionModal: React.FC<DataCollectionModalProps> = ({
  isOpen,
  onClose,
  accounts,
  theaters,
  defaultSelectedTheater = 'ALL',
  defaultSelectedAccountId = 'ALL',
  onJobStateChange,
  showToast = (_msg: string) => {},
  onDataSaved,
  initialAccountIds
}) => {
  const runtime = useCollectionRuntime({isOpen, accounts, onDataSaved, onJobStateChange});
  const {state: collectionState, accountProfiles, executionRows, jobState, viewStage, setViewStage,
    currentWaitExplanation, activeRunningAccountId, isRetryRun, busy, error, pollError, notice} = runtime;
  const yesterday = collectionState?.yesterday || '';
  const today = collectionToday(collectionState);
  const capabilities = collectionState?.capabilities;
  const revenueReady = supports(capabilities, 'revenue');
  const dateRangeReady = supports(capabilities, 'works_publication_range');
  const forceDailyReady = supports(capabilities, 'daily_reset_online');
  const opened = useRef(false);
  const defaultsApplied = useRef(false);
  const categoryCards = useRef<HTMLDivElement>(null);
  const dailyCard = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const card = dailyCard.current, container = categoryCards.current;
    if (!isOpen || viewStage !== 'plan' || !card || !container) return;
    const header = card.firstElementChild as HTMLElement | null;
    const align = () => {
      container.style.setProperty('--collection-card-height', getComputedStyle(card).height);
      if (header) container.style.setProperty('--collection-card-header-height', getComputedStyle(header).height);
    };
    const observer = new ResizeObserver(align);
    observer.observe(card);
    if (header) observer.observe(header);
    align();
    return () => observer.disconnect();
  }, [isOpen, viewStage]);


  // ============================================================================
  // 2. 账号范围选择状态 (支持快速选缺口账号 / 按剧场 / 自由勾选)
  // ============================================================================
  const [accountFilterMode, setAccountFilterMode] = useState<'task' | 'all' | 'custom'>('task');
  const [activeScenario, setActiveScenario] = useState<CollectionScenario | null>('daily_routine');
  const [theaterFilter, setTheaterFilter] = useState<string>('ALL');
  const [accountSearch, setAccountSearch] = useState<string>('');
  const [accountStatusScope, setAccountStatusScope] = useState<AccountDisplayScope | 'recommended'>('recommended');
  const [pausedPlatformIds, setPausedPlatformIds] = useState<Set<string>>(new Set());
  const [selectedAccountIds, setSelectedAccountIds] = useState<Set<string>>(new Set());
  const customize = () => {setActiveScenario(null); setAccountFilterMode('custom');};

  const toggleAccountSelection = (id: string) => {
    const profile=accountProfiles.find(p=>p.account.id===id);
    if (!profile || !collectionAccountSelectable(profile,enabledCategories)) return;
    customize();
    if (profile.account.businessStatus === '停用' && !selectedAccountIds.has(id) && (enabledCategories.daily_stats||enabledCategories.video_traffic||enabledCategories.optimization)) {
      setPausedPlatformIds(old=>new Set([...old,id]));
    }
    setSelectedAccountIds(prev => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const accountTheaters = useMemo(() => theaters.filter(t => accountProfiles.some(p => p.account.theaterId === t.id || p.account.theaterName === t.name)), [theaters, accountProfiles]);



  // ============================================================================
  // 3. 四大采集类别独立开关与专属范围参数 (互不串扰！)
  // ============================================================================
  const [enabledCategories, setEnabledCategories] = useState<Record<CollectionCategoryKey, boolean>>({
    daily_stats: true,
    video_traffic: false,
    optimization: false,
    revenue: revenueReady
  });

  const filteredProfilesForList = useMemo(() => {
    return accountProfiles.filter(p => {
      const scope = accountStatusScope === 'recommended' ? (enabledCategories.revenue ? 'all' : 'current') : accountStatusScope;
      if (accountStatusScope === 'recommended' && p.account.businessStatus === '注销') return false;
      if (!matchesAccountScope(p.account.businessStatus,scope)) return false;
      if (theaterFilter !== 'ALL' && p.account.theaterName !== theaterFilter) return false;
      if (accountSearch.trim()) {
        const q = accountSearch.toLowerCase();
        if (!p.account.name.toLowerCase().includes(q) && !p.account.theaterName.toLowerCase().includes(q)) {
          return false;
        }
      }
      return true;
    });
  }, [accountProfiles, theaterFilter, accountSearch, accountStatusScope, enabledCategories.revenue]);

  const platformIds = useMemo(() => new Set(accountProfiles.filter(p => selectedAccountIds.has(p.account.id) &&
    (matchesAccountScope(p.account.businessStatus,'current') || pausedPlatformIds.has(p.account.id))).map(p=>p.account.id)), [accountProfiles,selectedAccountIds,pausedPlatformIds]);

  // 3.1 账号每日数据专属配置
  const [dailyStatsMode, setDailyStatsMode] = useState<'smart_gap' | 'reset_online'>('smart_gap');

  // 3.2 视频最新累计流量专属配置
  const [forceVideoUpdate, setForceVideoUpdate] = useState(false);
  const [videoRangeMode, setVideoRangeMode] = useState<'publish_7d' | 'publish_14d' | 'all_pages'>('all_pages');
  const [videoWaitMinSec, setVideoWaitMinSec] = useState<number>(1);
  const [videoWaitMaxSec, setVideoWaitMaxSec] = useState<number>(2);

  // 3.3 优化记录与作品分析专属配置
  const [optMinMinutes, setOptMinMinutes] = useState(50);
  const [optMaxMinutes, setOptMaxMinutes] = useState(70);
  const detectionReady = supports(capabilities, 'optimization_detection');
  const detection = collectionState?.optimization_detection;
  const validDetectionInterval = Number.isInteger(optMinMinutes) && Number.isInteger(optMaxMinutes) && optMinMinutes >= 1 && optMaxMinutes <= 1440 && optMinMinutes <= optMaxMinutes;
  const nextDetectionTime = detection?.enabled && detection.accounts.filter(a => accountProfiles.some(p => p.available && matchesAccountScope(p.account.businessStatus,'current') && p.account.id === a.account_id)).reduce((min, a) => Math.min(min, a.next_due), Infinity);


  const parametersInitialized = useRef(false);
  useEffect(() => {
    if (!collectionState || parametersInitialized.current) return;
    parametersInitialized.current = true;
    const savedDetection = collectionState.optimization_detection;
    if (savedDetection) {setOptMinMinutes(savedDetection.min_minutes); setOptMaxMinutes(savedDetection.max_minutes);}
    setVideoWaitMaxSec(collectionState.page_interval_seconds); setVideoWaitMinSec(collectionState.page_interval_seconds / 2);
    setEnabledCategories(prev => ({...prev, revenue: supports(collectionState.capabilities, 'revenue')}));
    setVideoRangeMode(supports(collectionState.capabilities, 'works_publication_range') ? 'publish_7d' : 'all_pages');
  }, [collectionState]);
  useEffect(()=>{
    setSelectedAccountIds(previous=>{
      const next=new Set([...previous].filter(id=>{const p=accountProfiles.find(p=>p.account.id===id);return !!p && collectionAccountSelectable(p,enabledCategories) && (p.account.businessStatus !== '停用' || (enabledCategories.revenue && p.revenueAvailable) || pausedPlatformIds.has(id));}));
      return next.size===previous.size?previous:next;
    });
  },[accountProfiles,enabledCategories,pausedPlatformIds]);
  const recommendedIds = taskAccountIds(filteredProfilesForList, enabledCategories, dailyStatsMode);
  const hiddenSelectedCount = accountProfiles.filter(p => selectedAccountIds.has(p.account.id) && !filteredProfilesForList.some(v => v.account.id===p.account.id)).length;
  const handleSelectPresetAccounts = (mode: 'task' | 'all' | 'clear') => {
    setActiveScenario(null); setAccountFilterMode(mode==='clear'?'custom':mode);
    setPausedPlatformIds(new Set(mode==='all' && (enabledCategories.daily_stats||enabledCategories.video_traffic||enabledCategories.optimization) ? filteredProfilesForList.filter(p=>p.account.businessStatus==='停用' && p.platformAvailable).map(p=>p.account.id) : []));
    setSelectedAccountIds(new Set(mode==='task' ? recommendedIds : mode==='all' ? filteredProfilesForList.filter(p=>collectionAccountSelectable(p,enabledCategories)).map(p=>p.account.id) : []));
  };
  useEffect(() => {
    if (isOpen && !opened.current) {setForceVideoUpdate(false); defaultsApplied.current=false; setTheaterFilter(defaultSelectedTheater || 'ALL'); setAccountSearch('');setAccountStatusScope('recommended');setPausedPlatformIds(new Set());}
    if (isOpen && collectionState && !defaultsApplied.current) {
      const candidates=accountProfiles.filter(p=>defaultSelectedTheater==='ALL'||p.account.theaterName===defaultSelectedTheater);
      const explicit=defaultSelectedAccountId!=='ALL' ? [defaultSelectedAccountId] : initialAccountIds?.length===1 ? initialAccountIds : null;
      const categories=scenarioCategories('daily_routine',revenueReady);
      setEnabledCategories(categories); setDailyStatsMode('smart_gap');
      setSelectedAccountIds(new Set(explicit ? explicit.filter(id=>candidates.some(p=>collectionAccountSelectable(p,categories)&&p.account.id===id)) : taskAccountIds(candidates,categories,'smart_gap')));
      setActiveScenario(explicit?null:'daily_routine');setAccountFilterMode(explicit?'custom':'task');
      if(runtime.summary.isRunning) setViewStage('monitor'); defaultsApplied.current=true;
    }
    opened.current=isOpen;
  }, [isOpen,collectionState,accountProfiles,defaultSelectedTheater,defaultSelectedAccountId]);
  const applyScenarioPreset = (scenario: CollectionScenario) => {
    const categories=scenarioCategories(scenario,revenueReady);
    setEnabledCategories(categories); setDailyStatsMode('smart_gap');setAccountStatusScope('recommended');setPausedPlatformIds(new Set());
    if(scenario==='targeted_video_7d') {setVideoRangeMode('publish_7d');setVideoWaitMaxSec(collectionState?.page_interval_seconds ?? 2);setVideoWaitMinSec((collectionState?.page_interval_seconds ?? 2)/2);}
    setSelectedAccountIds(new Set(taskAccountIds(accountProfiles.filter(p=>(theaterFilter==='ALL'||p.account.theaterName===theaterFilter)&&(!accountSearch.trim()||`${p.account.name} ${p.account.theaterName}`.toLowerCase().includes(accountSearch.toLowerCase()))),categories,'smart_gap')));
    setAccountFilterMode('task');setActiveScenario(scenario);runtime.setError('');
  };
  const scenarioLabel=collectionScenarios.find(s=>s.id===activeScenario)?.label;

  // ============================================================================
  // 4. 执行前透明计划预演 (Execution Plan Preview)
  // ============================================================================
  const executionPlanSummary = useMemo(() => planSummary(accountProfiles, selectedAccountIds, enabledCategories, dailyStatsMode, videoRangeMode, platformIds), [accountProfiles, selectedAccountIds, enabledCategories, dailyStatsMode, videoRangeMode, platformIds]);
  const selectedCategories = [enabledCategories.daily_stats && 'daily', enabledCategories.video_traffic && 'works', enabledCategories.optimization && 'optimization', enabledCategories.revenue && 'revenue'].filter(Boolean) as Array<'daily' | 'works' | 'optimization' | 'revenue'>;
  const request = buildCollectionRequest({
    accountIds: accountProfiles.filter(p => collectionAccountSelectable(p,enabledCategories) && selectedAccountIds.has(p.account.id)).map(p => p.account.id), categories: selectedCategories,
    platformAccountIds: [...platformIds],
    interval: String(videoWaitMaxSec), cooldown: '1', forceWorks: forceVideoUpdate,
    dailyMode: dailyStatsMode === 'reset_online' ? 'reset_online' : 'fill_missing', dailyStart: '', dailyEnd: '',
    worksMode: videoRangeMode === 'all_pages' ? 'all' : 'custom',
    worksStart: periodStart(today, videoRangeMode === 'publish_14d' ? 14 : 7),
    worksEnd: today,
    revenueMode: 'routine', revenueStart: '', revenueEnd: '',
  }, yesterday, capabilities);
  const executionError = enabledCategories.optimization && !detectionReady ? '优化检测尚未接入当前后端' : request.error;
  const startCollectionJob = (targetRowsToRetry?: AccountExecutionRow[]) => {
    if (jobState === 'running' || jobState === 'stopping') {setViewStage('monitor'); return;}
    if (targetRowsToRetry?.length) {void runtime.submit('retry', undefined, targetRowsToRetry.map(row => row.accountId)); return;}
    if (executionError || !request.options) {runtime.setError(executionError || request.error || '请选择有效范围'); return;}
    void runtime.submit('start', {...request.options, force_optimization: enabledCategories.optimization});
  };
  const handleStopJob = () => {void runtime.submit('stop');};

  if (!isOpen) return null;

  return (
    <CockpitModal label="数据采集与补缺中心" onClose={onClose} width="max-w-[1280px]" rounding="rounded-3xl" testId="gemini-collection-panel">
      <div 
        className="flex min-h-0 flex-col overflow-hidden bg-[#F8FAFC]"
        onClick={e => e.stopPropagation()}
      >
        {/* =================================================================== */}
        {/* 顶部全局标题栏：明确区分「关闭窗口(后台继续)」与「停止采集任务」 */}
        {/* =================================================================== */}
        <div className="px-6 py-4 bg-white border-b border-slate-200/90 flex flex-wrap items-center justify-between gap-4 shrink-0">
          <div className="flex min-w-0 flex-1 basis-[600px] items-start gap-3.5">
            <div className="shrink-0 w-10 h-10 rounded-2xl bg-[#1E1644] text-[#DDFD00] flex items-center justify-center shadow-sm">
              <Database className="w-5 h-5" />
            </div>
            <div className="min-w-0">
              <div className="flex flex-wrap items-center gap-2.5">
                <h2 className="text-base font-extrabold text-slate-900 tracking-tight">
                  运营数据智能采集与补缺中心
                </h2>
                <span className="text-[11px] font-bold px-2.5 py-0.5 rounded-full bg-indigo-50 text-indigo-700 border border-indigo-200 font-mono">
                  业务时区: Asia/Shanghai (截至昨日 {yesterday || '读取中'})
                </span>
                <span className="text-[11px] font-semibold px-2 py-0.5 rounded-full bg-amber-50 text-amber-800 border border-amber-200">
                  已有结果保留 · 缺失不补 0
                </span>
              </div>
              <p className="text-xs text-slate-500 mt-0.5">
                本地完整数据自动跳过 · 各数据类别范围独立控制 · 失败或未更新绝不伪造为 0 · 账号视频数与关注者数顺带读取不单列任务
              </p>
            </div>
          </div>

          {/* 顶部阶段切换 & 窗口关闭控制 */}
          <div className="ml-auto flex flex-wrap items-center gap-3">
            {/* 视图切换：方案配置 vs 实时执行流水 */}
            <button type="button" aria-label="刷新登录状态" disabled={runtime.loginBusy || busy || jobState==='running' || jobState==='stopping'}
              onClick={()=>void runtime.refreshLogins()} title="读取小V猫本地保存的登录信息，不发起在线登录检测"
              className="inline-flex shrink-0 items-center gap-1.5 rounded-xl border border-slate-200 bg-white px-3 py-2 text-xs font-bold text-slate-600 hover:bg-indigo-50 hover:text-indigo-600 disabled:opacity-40">
              <RefreshCw className={`h-3.5 w-3.5 ${runtime.loginBusy?'animate-spin':''}`}/>{runtime.loginBusy?'正在刷新':'刷新登录状态'}
            </button>
            <div className="inline-flex p-1 bg-slate-100 rounded-xl border border-slate-200/80 text-xs">
              <button
                type="button"
                onClick={() => setViewStage('plan')}
                className={`px-3.5 py-1.5 rounded-lg font-bold transition-all cursor-pointer flex items-center gap-1.5 ${
                  viewStage === 'plan'
                    ? 'bg-white text-slate-900 shadow-xs'
                    : 'text-slate-600 hover:text-slate-900'
                }`}
              >
                <Sliders className="w-3.5 h-3.5 text-indigo-600" />
                <span>采集配置</span>
              </button>
              <button
                type="button"
                onClick={() => setViewStage('monitor')}
                className={`px-3.5 py-1.5 rounded-lg font-bold transition-all cursor-pointer flex items-center gap-1.5 ${
                  viewStage === 'monitor'
                    ? 'bg-white text-indigo-600 shadow-xs'
                    : 'text-slate-600 hover:text-slate-900'
                }`}
              >
                <RefreshCw className={`w-3.5 h-3.5 ${jobState === 'running' || jobState === 'stopping' ? 'animate-spin text-indigo-600' : ''}`} />
                <span>任务记录</span>
                {executionRows.length > 0 && (
                  <span className="px-1.5 py-0.2 rounded-full text-[10px] bg-indigo-100 text-indigo-700 font-mono">
                    {executionRows.filter(r => r.overallStatus !== 'waiting' && r.overallStatus !== 'running').length}/{executionRows.length}
                  </span>
                )}
              </button>
            </div>

            {/* 仅关闭窗口，后台任务继续；保留右上角关闭图标。 */}
            <button
              type="button"
              onClick={onClose}
              aria-label="关闭采集窗口"
              className="rounded-lg p-1.5 text-slate-400 hover:bg-slate-100 hover:text-slate-700 transition-colors cursor-pointer"
              title="仅关闭弹窗界面，若有正在运行的采集任务将在后台继续完成，也不会因开关窗口触发新采集"
            >
              <X className="w-4 h-4" />
            </button>
          </div>
        </div>

        {/* =================================================================== */}
        {/* STAGE 1: 缺口诊断与自由范围配置视图 */}
        {/* =================================================================== */}
        {viewStage === 'plan' && (
          <div className="flex-1 overflow-y-auto p-6 space-y-5">
            {/* 顶部：4大典型运营场景一键填入（透明提示，不锁死任何选项） */}
            <div className="bg-white rounded-2xl p-4 border border-slate-200/80 shadow-2xs flex flex-col lg:flex-row lg:items-center justify-between gap-3">
              <div className="flex items-center gap-2.5">
                <span className="px-2.5 py-1 rounded-lg bg-indigo-50 text-indigo-700 font-extrabold text-xs flex items-center gap-1.5 shrink-0">
                  <Sparkles className="w-3.5 h-3.5" />
                  <span>常用运营采集场景快选</span>
                </span>
              </div>

              <div className="flex flex-wrap items-center gap-2" data-collection-scenarios>
                {collectionScenarios.map(scenario => <button key={scenario.id} type="button"
                  disabled={!collectionState || (scenario.id==='targeted_video_7d'&&!dateRangeReady) || (scenario.id==='optimization_now'&&!detectionReady) || (scenario.id==='revenue_only'&&!revenueReady)}
                  aria-pressed={activeScenario===scenario.id} title={scenario.description}
                  onClick={()=>applyScenarioPreset(scenario.id)}
                  className={`px-3 py-1.5 rounded-xl text-xs font-bold border transition-all cursor-pointer disabled:opacity-40 ${activeScenario===scenario.id?'bg-indigo-600 text-white border-indigo-600 shadow-xs':'bg-white text-slate-700 border-slate-200 hover:bg-indigo-50 hover:text-indigo-700'}`}>
                  {scenario.label}
                </button>)}
              </div>
            </div>

            {/* 核心双栏：左侧「第一步：选账号与查看缺口诊断」 + 右侧「第二步：选数据类别与独立范围」 */}
            <div data-collection-columns className="grid grid-cols-1 lg:grid-cols-12 gap-5 items-stretch">
              
              {/* --------------------------------------------------------------- */}
              {/* 左侧 (6列)：账号选择与本地缺口实时体检清单 */}
              {/* --------------------------------------------------------------- */}
              <div data-collection-accounts className="lg:col-span-6 min-h-0 bg-white rounded-2xl border border-slate-200/90 shadow-xs overflow-hidden flex flex-col">
                <div className="shrink-0 p-4 border-b border-slate-100 bg-slate-50/70 space-y-3">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <Users className="w-4 h-4 text-indigo-600" />
                      <h3 className="text-sm font-extrabold text-slate-900">
                        采集对象账号 ({selectedAccountIds.size} / {accountProfiles.length} 已选)
                      </h3>
                    </div>
                    <span className="text-[11px] text-slate-400">
                      附带顺手更新视频数/关注者数
                    </span>
                  </div>

                  <div className="flex flex-wrap items-center gap-1.5 text-[11px]">
                    <button type="button" onClick={()=>handleSelectPresetAccounts('task')}
                      className={`px-2.5 py-1 rounded-lg font-bold border cursor-pointer ${accountFilterMode==='task'?'bg-indigo-600 text-white border-indigo-600':'bg-white text-slate-700 border-slate-200 hover:bg-slate-100'}`}>
                      按本次任务选择 ({recommendedIds.length})
                    </button>
                    <button type="button" onClick={()=>handleSelectPresetAccounts('all')} className="px-2 py-1 rounded-lg font-semibold border border-slate-200 bg-white text-slate-600 hover:bg-slate-100 cursor-pointer">
                      全选当前可采集账号 ({filteredProfilesForList.filter(p=>collectionAccountSelectable(p,enabledCategories)).length})
                    </button>
                    <button type="button" onClick={()=>handleSelectPresetAccounts('clear')} className="px-2 py-1 rounded-lg font-semibold border border-slate-200 bg-white text-slate-400 hover:text-slate-700 cursor-pointer">清空选择</button>
                  </div>
                  {hiddenSelectedCount>0 && <p className="text-[11px] text-amber-700" data-hidden-selection>另有 {hiddenSelectedCount} 个已选账号不在当前列表；点击场景或快捷选择将按当前列表重新选择。</p>}

                  <div className="flex flex-wrap items-center gap-2">
                    <label className="text-xs text-slate-500">账号状态 <select aria-label="采集账号状态" value={accountStatusScope}
                      onChange={e=>{customize();setAccountStatusScope(e.target.value as AccountDisplayScope|'recommended');}}
                      className="ml-1 rounded-xl border border-slate-200 bg-white px-2 py-1.5 text-xs text-slate-700">
                      <option value="recommended">{enabledCategories.revenue?'推荐范围（含停用）':'推荐范围（未停用、未注销）'}</option>
                      {ACCOUNT_DISPLAY_SCOPES.map(scope=><option key={scope.value} value={scope.value}>{scope.label}</option>)}
                    </select></label>
                    <span className="text-[11px] text-slate-500">停用账号默认仅采收益；注销账号停止采集。</span>
                  </div>
                  {/* 剧场过滤 + 关键词搜索 */}
                  <div className="flex items-center gap-2">
                    <select
                      value={theaterFilter}
                      onChange={e => {customize();setTheaterFilter(e.target.value);}}
                      className="bg-white border border-slate-200 rounded-xl px-2.5 py-1.5 text-xs font-bold text-slate-700 focus:outline-none"
                    >
                      <option value="ALL">全部剧场 ({accountTheaters.length})</option>
                      {accountTheaters.map(t => (
                        <option key={t.id} value={t.name}>{t.name}</option>
                      ))}
                    </select>

                    <div className="relative flex-1">
                      <Search className="w-3.5 h-3.5 text-slate-400 absolute left-2.5 top-1/2 -translate-y-1/2" />
                      <input
                        type="text"
                        value={accountSearch}
                        onChange={e => {customize();setAccountSearch(e.target.value);}}
                        placeholder="搜索账号名或剧场..."
                        className="w-full pl-8 pr-2.5 py-1.5 bg-white border border-slate-200 rounded-xl text-xs text-slate-800 focus:outline-none focus:border-indigo-500"
                      />
                    </div>
                  </div>
                </div>

                {/* 账号列表与右侧等高；只在列表内部滚动。 */}
                <div className="relative min-h-0 flex-1">
                  <div data-collection-account-scroll className="divide-y divide-slate-100 max-h-[480px] overflow-y-auto overscroll-contain lg:absolute lg:inset-0 lg:max-h-none">
                    {filteredProfilesForList.map(p => {
                      const isChecked = selectedAccountIds.has(p.account.id) && collectionAccountSelectable(p,enabledCategories);
                      const account = {...p.account, videoTotal:p.videoTotalCount, followerTotal:p.followerCount};
                      const statuses = collectionStatusRows(p, collectionState);
                      return (
                        <div key={p.account.id} data-collection-account={p.account.id}
                          onClick={() => toggleAccountSelection(p.account.id)}
                          className={`px-3 py-2 transition-colors cursor-pointer ${isChecked ? 'bg-indigo-50/40 hover:bg-indigo-50/70' : 'hover:bg-slate-50'}`}>
                          <div className="flex items-center gap-2.5">
                            <input type="checkbox" checked={isChecked} aria-label={`采集账号 ${account.name}`}
                              disabled={!collectionAccountSelectable(p,enabledCategories) || !collectionState}
                              onClick={e => e.stopPropagation()} onChange={() => toggleAccountSelection(account.id)}
                              className="shrink-0 rounded border-slate-300 text-indigo-600 focus:ring-indigo-500 cursor-pointer" />
                            <div data-collection-account-content className="grid min-w-0 flex-1 grid-cols-[minmax(0,0.85fr)_minmax(0,1.15fr)] items-center gap-3">
                              <div data-collection-account-identity className="min-w-0">
                                <div className="flex items-center gap-2.5">
                                  <span className="relative inline-flex h-9 w-9 flex-none" onClick={e => e.stopPropagation()}>
                                    <AccountAvatar name={account.name} url={account.avatarUrl} className="w-9 h-9" />
                                    <AccountLoginBadge account={account} />
                                  </span>
                                  <div className="min-w-0 flex-1">
                                    <div className="flex min-w-0 items-center gap-1.5">
                                      <span className="min-w-0 truncate font-extrabold text-xs text-slate-900" title={account.name}>{account.name}</span>
                                      <span className="shrink-0"><BusinessAccountStatusBadge status={account.businessStatus} /></span>
                                    </div>
                                    <p className="mt-0.5 truncate text-[10px] leading-3 text-slate-400" title={account.theaterName}>{account.theaterName}</p>
                                  </div>
                                </div>
                                <AccountProfileTotals account={account} />
                                {account.businessStatus==='停用' && (enabledCategories.daily_stats||enabledCategories.video_traffic||enabledCategories.optimization) &&
                                  <label onClick={e=>e.stopPropagation()} className="mt-1 flex items-center gap-1 text-[11px] text-amber-700">
                                    <input type="checkbox" aria-label={`停用账号 ${account.name} 本次采集平台数据`} checked={pausedPlatformIds.has(account.id)} disabled={!p.platformAvailable}
                                      onChange={e=>{const checked=e.target.checked;customize();setPausedPlatformIds(old=>{const next=new Set(old);checked?next.add(account.id):next.delete(account.id);return next;});if(checked)setSelectedAccountIds(old=>new Set([...old,account.id]));}} />本次也采集平台数据
                                  </label>}
                                {p.unavailableReason && <p className="mt-1 text-[10px] text-amber-700">{p.unavailableReason}</p>}
                              </div>
                              <div className="grid min-w-0 grid-cols-2 gap-x-2 gap-y-1 border-l border-slate-200/70 pl-3 text-[10px] leading-[13px]" data-collection-account-statuses>
                                {statuses.map(row => (
                                  <div key={row.key} data-collection-status={row.key} className="flex min-w-0 items-center gap-1 whitespace-nowrap" title={row.detail}>
                                    <span className="shrink-0 text-slate-400">{row.label}</span>
                                    <span className={`min-w-0 flex-1 truncate ${row.tone==='danger'?'text-rose-600':row.tone==='warning'?'text-amber-700':row.tone==='ready'?'text-emerald-700':'text-slate-500'}`}>{row.text.replace(/^(?:上次|检测)\s+(?=\d{2}\/\d{2})/, '')}</span>
                                  </div>
                                ))}
                              </div>
                            </div>
                          </div>
                        </div>
                      );
                    })}
                    {filteredProfilesForList.length === 0 && <p className="p-6 text-center text-xs text-slate-400">没有匹配的账号</p>}
                  </div>
                </div>
              </div>

              {/* --------------------------------------------------------------- */}
              {/* 右侧 (6列)：四大采集数据类别独立卡片与专属范围设定 */}
              {/* --------------------------------------------------------------- */}
              <div ref={categoryCards} data-collection-categories onChangeCapture={e=>{if(!(e.target as HTMLElement).closest('[data-auto-detection-settings]')) customize();}} className="lg:col-span-6 min-w-0 space-y-3.5">
                
                {/* 类别 1：账号每日数据 (含顺带读取账号视频数、关注者数) */}
                <div ref={dailyCard} data-collection-category="daily" className={`rounded-2xl border transition-all p-4 bg-white ${
                  enabledCategories.daily_stats ? 'border-indigo-300 shadow-xs ring-1 ring-indigo-500/10' : 'border-slate-200 opacity-75'
                }`}>
                  <div className="flex items-start justify-between gap-3">
                    <label className="flex min-w-0 items-start gap-3 cursor-pointer flex-1">
                      <input
                        type="checkbox"
                        aria-label="账号每日数据" checked={enabledCategories.daily_stats}
                        onChange={e => setEnabledCategories(prev => ({ ...prev, daily_stats: e.target.checked }))}
                        className="mt-1 w-4 h-4 shrink-0 rounded border-slate-300 text-indigo-600 focus:ring-indigo-500 cursor-pointer"
                      />
                      <div>
                        <div className="flex items-center gap-2 flex-wrap">
                          <span className="text-sm font-extrabold text-slate-900">
                            账号每日数据 (官方每日统计)
                          </span>
                          <span className="text-[10px] font-bold px-2 py-0.5 rounded-full bg-emerald-50 text-emerald-700 border border-emerald-200">
                            后端已就绪 · 本地优先+小V猫补缺
                          </span>
                        </div>
                        <p className="text-xs text-slate-500 mt-1">
                          含总播放量、关注者总量(可缺失)、新增/取消/净增关注(可为负)、爱心、点赞(不作收藏)、评论、分享。顺带读取账号当前总作品数与关注者数（复用请求，不单列任务）。
                        </p>
                      </div>
                    </label>
                  </div>

                  <div className="mt-3.5 pt-3.5 border-t border-slate-100 pl-7 space-y-3 text-xs">
                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-2.5">
                      <button
                        type="button"
                        onClick={() => {customize();setDailyStatsMode('smart_gap');}}
                        aria-pressed={dailyStatsMode === 'smart_gap'}
                        className={`p-3 rounded-xl border text-left cursor-pointer transition-all ${
                          dailyStatsMode === 'smart_gap'
                            ? 'bg-indigo-50/60 border-indigo-300 text-indigo-950'
                            : 'bg-slate-50 border-slate-200 text-slate-600 hover:bg-slate-100'
                        }`}
                      >
                        <span className="font-bold flex items-center justify-between">
                          <span>日常智能补齐缺口 (推荐)</span>
                          {dailyStatsMode === 'smart_gap' && <CheckCircle2 className="w-4 h-4 text-indigo-600" />}
                        </span>
                        <span className="block text-[11px] text-slate-500 mt-1 leading-relaxed">
                          补齐截至昨日({yesterday || '读取中'})缺失日与缺失字段；完整日跳过；历史边界未确认时继续向前补齐，缺失不当成全零。
                        </span>
                      </button>
                      <button
                        type="button"
                        disabled={!forceDailyReady}
                        onClick={() => {customize();setDailyStatsMode('reset_online');}}
                        aria-pressed={dailyStatsMode === 'reset_online'}
                        title={forceDailyReady ? undefined : '每日数据在线重置尚待后端接入'}
                        className={`p-3 rounded-xl border text-left transition-all disabled:cursor-not-allowed ${
                          dailyStatsMode === 'reset_online'
                            ? 'bg-amber-50 border-amber-400 text-amber-950'
                            : 'bg-slate-50 border-slate-200 text-slate-600 hover:bg-slate-100 cursor-pointer'
                        }`}
                      >
                        <span className="font-bold flex items-center justify-between gap-2">
                          <span>强制获取在线数据（重置）</span>
                          {dailyStatsMode === 'reset_online' && <CheckCircle2 className="w-4 h-4 text-amber-600" />}
                        </span>
                        <span className="block text-[11px] text-slate-500 mt-1 leading-relaxed">
                          重新获取所选账号的每日数据，补齐到历史边界；获取失败时保留原有效数据。
                        </span>
                      </button>
                    </div>
                  </div>
                </div>

                {/* 类别 2：与账号每日数据卡片同高 */}
                <section aria-label="视频累计流量设置" data-collection-category="works" data-collection-video-card
                  style={{height:'var(--collection-card-height)'}} className={`flex min-w-0 flex-col rounded-2xl border bg-white p-4 transition-colors ${
                  enabledCategories.video_traffic ? 'border-indigo-300 shadow-xs ring-1 ring-indigo-500/10' : 'border-slate-200 opacity-75'
                }`}>
                  <div className="shrink-0"><div className="flex min-w-0 items-start justify-between gap-3">
                    <label className="flex min-w-0 flex-1 cursor-pointer items-start gap-3">
                      <input type="checkbox" aria-label="视频累计流量（作品在线浏览）" checked={enabledCategories.video_traffic}
                        onChange={e => setEnabledCategories(prev => ({...prev,video_traffic:e.target.checked}))}
                        className="mt-1 h-4 w-4 shrink-0 cursor-pointer rounded border-slate-300 text-indigo-600 focus:ring-indigo-500" />
                      <span className="min-w-0">
                        <span className="flex flex-wrap items-center gap-x-2 gap-y-1">
                          <span className="text-sm font-extrabold leading-5 text-slate-900">视频累计流量（作品在线浏览）</span>
                          <span className="rounded-full border border-indigo-200 bg-indigo-50 px-2 py-0.5 text-[10px] font-bold leading-4 text-indigo-700">采作品当前累计值 · 非区间新增播放</span>
                        </span>
                      </span>
                    </label>
                    <label className={`inline-flex shrink-0 items-center gap-1.5 rounded-lg border px-2 py-1 text-[11px] font-semibold ${forceVideoUpdate ? 'border-amber-300 bg-amber-50 text-amber-800' : 'border-slate-200 text-slate-600'} ${enabledCategories.video_traffic ? 'cursor-pointer' : 'cursor-not-allowed'}`}
                      title="默认跳过1小时内完整采集的范围。勾选后本次重新获取，仍保留所选范围和逐页等待。">
                      <input type="checkbox" aria-label="强制更新" checked={forceVideoUpdate} disabled={!enabledCategories.video_traffic}
                        onChange={e=>setForceVideoUpdate(e.target.checked)} className="h-3.5 w-3.5 rounded border-slate-300 text-indigo-600 focus:ring-indigo-500" />强制更新
                    </label>
                  </div>
                    <p className="mt-1 pl-7 text-xs leading-4 text-slate-500">更新作品累计播放、爱心、点赞、评论、分享、完播率及在线封面/播放地址。关联V3发布记录显示文件名(剧名-n)，未关联显示作品ID。</p>
                  </div>
                  <div data-collection-card-body className="mt-3.5 flex min-h-0 flex-1 flex-col justify-center gap-1.5 overflow-y-auto border-t border-slate-100 pl-7 pt-1 text-xs">
                    <fieldset className="min-w-0">
                      <legend className="sr-only">作品发布时间范围</legend>
                      <div data-collection-video-ranges className="grid grid-cols-3 gap-2">
                        {(['publish_7d','publish_14d','all_pages'] as const).map(mode=>{
                          const days=mode==='publish_14d'?14:7,active=videoRangeMode===mode;
                          const start=periodStart(today,days),dates=`${start || '—'} 至 ${today || '—'}`;
                          return <button key={mode} type="button" aria-pressed={active}
                            aria-label={mode==='all_pages'?'全量作品翻页':`近 ${days} 天发布作品`}
                            disabled={mode!=='all_pages'&&!dateRangeReady}
                            title={mode==='all_pages'?'读取账号全部作品':dateRangeReady?dates:'按发布时间停止翻页待后端接入'}
                            onClick={()=>{customize();setVideoRangeMode(mode);}}
                            className={`flex min-w-0 flex-col justify-center gap-1 rounded-xl border px-2 py-1.5 text-left disabled:cursor-not-allowed ${active?'border-indigo-300 bg-indigo-50/70 text-indigo-950':'cursor-pointer border-slate-200 bg-slate-50 text-slate-600 hover:bg-slate-100'}`}>
                            <span className="text-[11px] font-bold leading-4">{mode==='all_pages'?'全量作品翻页':`近 ${days} 天发布作品`}</span>
                            <span className="flex flex-wrap gap-x-1 text-[10px] leading-4 tabular-nums text-slate-500">{mode==='all_pages'?'读取账号全部作品':<><span className="whitespace-nowrap">{start||'—'}</span><span>至</span><span className="whitespace-nowrap">{today||'—'}</span></>}</span>
                          </button>;
                        })}
                      </div>
                    </fieldset>
                    <div data-collection-video-wait className="flex flex-wrap items-center justify-between gap-x-2 gap-y-1 text-[11px] text-slate-600" title="等待下限为上限的50%，两个数值联动">
                      <span className="inline-flex items-center gap-1"><Clock className="h-3 w-3 shrink-0 text-indigo-600"/>逐页随机等待</span>
                      <span className="flex items-center gap-1.5 tabular-nums">
                        <input type="number" step="0.05" min="0.05" max="30" aria-label="逐页等待下限" value={videoWaitMinSec}
                          onChange={e=>{const value=Number(e.target.value);if(Number.isFinite(value)){const min=Math.min(30,Math.max(0.05,value));setVideoWaitMinSec(min);setVideoWaitMaxSec(min*2);}}}
                          className="w-12 rounded-md border border-slate-200 bg-white px-1 py-0.5 text-center" />
                        <span>～</span>
                        <input type="number" step="0.1" min="0.1" max="60" aria-label="逐页等待上限" value={videoWaitMaxSec}
                          onChange={e=>{const value=Number(e.target.value);if(Number.isFinite(value)){const max=Math.min(60,Math.max(0.1,value));setVideoWaitMaxSec(max);setVideoWaitMinSec(max/2);}}}
                          className="w-12 rounded-md border border-slate-200 bg-white px-1 py-0.5 text-center" />
                        <span>秒</span>
                      </span>
                    </div>
                  </div>
                </section>

                {/* 类别 3：优化记录与作品分析 */}
                <div data-collection-category="optimization" style={{height:'var(--collection-card-height)'}} className={`flex min-w-0 flex-col rounded-2xl border transition-colors p-4 bg-white ${
                  enabledCategories.optimization ? 'border-indigo-300 shadow-xs ring-1 ring-indigo-500/10' : 'border-slate-200'
                }`}>
                  <div className="flex shrink-0 items-start justify-between gap-3">
                    <label className="flex min-w-0 items-start gap-3 cursor-pointer flex-1">
                      <input
                        type="checkbox"
                        aria-label="账号优化记录（优化作品分析）" checked={enabledCategories.optimization}
                        onChange={e => setEnabledCategories(prev => ({ ...prev, optimization: e.target.checked }))}
                        className="mt-1 w-4 h-4 shrink-0 rounded border-slate-300 text-indigo-600 focus:ring-indigo-500 cursor-pointer"
                      />
                      <div>
                        <div className="flex items-center gap-2 flex-wrap">
                          <span className="text-sm font-extrabold text-slate-900">
                            账号优化记录（优化作品分析）
                          </span>
                          <span className="text-[10px] font-bold px-2 py-0.5 rounded-full bg-emerald-50 text-emerald-700 border border-emerald-200">
                            定时检测 · 分析原文永久保留
                          </span>
                        </div>
                        <p className="text-xs text-slate-500 mt-1">
                          主动检测优化名单并保存分析；仅关联V3发布记录的作品计入优化率。
                        </p>
                      </div>
                    </label>
                  </div>

                    <div data-collection-card-body className="mt-3.5 flex min-h-0 flex-1 flex-col justify-center overflow-y-auto border-t border-slate-100 pl-7 pt-1 text-xs">
                      <div className="grid grid-cols-1 sm:grid-cols-2 gap-2.5 items-stretch">
                        <button type="button" aria-label="立即检测" aria-pressed={enabledCategories.optimization}
                          disabled={!detectionReady || busy} onClick={() => {customize();setEnabledCategories(prev => ({...prev, optimization: !prev.optimization}));}}
                          className={`px-3 py-1 rounded-xl border text-left cursor-pointer transition-all disabled:opacity-40 ${enabledCategories.optimization
                            ? 'bg-amber-50 border-amber-400 text-amber-950' : 'bg-slate-50 border-slate-200 text-slate-600 hover:bg-slate-100'}`}>
                          <span className="font-bold flex items-center justify-between gap-2">
                            <span>立即检测</span>
                            {enabledCategories.optimization && <CheckCircle2 className="w-4 h-4 text-amber-600" />}
                          </span>
                          <span className="block text-[11px] text-slate-500 mt-1 leading-relaxed">选择账号，统一点击右下角执行。<br />本次直接检测，不等待自动周期。</span>
                        </button>
                        <div data-auto-detection-settings className="px-3 py-1 rounded-xl border border-slate-200 bg-slate-50 text-slate-700">
                          <div className="flex items-center justify-between gap-2">
                            <span className="font-bold">自动检测设置 <span className="font-normal text-[10px] text-slate-500">全局</span></span>
                            <label className="inline-flex items-center gap-1 text-[11px] cursor-pointer">
                              <input type="checkbox" aria-label="自动检测优化记录" checked={!!detection?.enabled}
                                disabled={!detectionReady || runtime.detectionBusy}
                                onChange={e => void runtime.saveDetection({enabled: e.target.checked, min_minutes: detection?.min_minutes ?? 50, max_minutes: detection?.max_minutes ?? 70})}
                                className="rounded border-slate-300 text-indigo-600" />启用
                            </label>
                          </div>
                          <p className="mt-1 text-[10px] leading-3.5 text-slate-500">自动检测排除停用、注销和登录失效账号；停用及登录失效账号可手动选择，执行时重新核对。</p>
                          <div className="mt-1.5 flex flex-wrap items-center gap-0.5 text-[11px]">
                            <span>间隔</span>
                            <input type="number" aria-label="优化检测最短间隔" min={1} max={1440} step={1} value={Number.isFinite(optMinMinutes) ? optMinMinutes : ''}
                              disabled={!detectionReady || runtime.detectionBusy} onChange={e => setOptMinMinutes(e.target.value === '' ? NaN : Number(e.target.value))}
                              className="w-8 px-0.5 py-0.5 rounded-md border border-slate-200 bg-white outline-none focus:border-indigo-400 disabled:bg-slate-100" />
                            <span>～</span>
                            <input type="number" aria-label="优化检测最长间隔" min={1} max={1440} step={1} value={Number.isFinite(optMaxMinutes) ? optMaxMinutes : ''}
                              disabled={!detectionReady || runtime.detectionBusy} onChange={e => setOptMaxMinutes(e.target.value === '' ? NaN : Number(e.target.value))}
                              className="w-8 px-0.5 py-0.5 rounded-md border border-slate-200 bg-white outline-none focus:border-indigo-400 disabled:bg-slate-100" />
                            <span>分钟</span>
                            <button type="button" aria-label="保存自动检测间隔" disabled={!detectionReady || runtime.detectionBusy || !validDetectionInterval}
                              onClick={() => void runtime.saveDetection({enabled: !!detection?.enabled, min_minutes: optMinMinutes, max_minutes: optMaxMinutes})}
                              className="px-1 py-0.5 rounded-md border border-indigo-200 bg-white text-indigo-700 font-bold hover:bg-indigo-50 disabled:opacity-40 cursor-pointer">
                              {runtime.detectionBusy ? '保存中' : '保存'}
                            </button>
                          </div>
                        </div>
                      </div>
                      <p className="mt-0.5 text-[11px] text-slate-500" role="status">
                        {!detectionReady ? '检测功能尚未连接。' : detection?.paused_reason || (detection?.enabled
                          ? `全局自动检测已开启：${detection.min_minutes}～${detection.max_minutes}分钟${nextDetectionTime && Number.isFinite(nextDetectionTime) ? `，下次最早 ${new Date(nextDetectionTime * 1000).toLocaleTimeString('zh-CN', {timeZone: 'Asia/Shanghai', hour: '2-digit', minute: '2-digit'})}（北京时间）` : ''}。`
                          : '全局自动检测未开启；启用即时生效，间隔修改后在卡片内保存。')}
                      </p>
                      {!validDetectionInterval && <p role="alert" className="mt-1 text-[11px] text-amber-700">请输入1～1440分钟的整数，最短间隔不能大于最长间隔。</p>}
                    </div>
                </div>

                {/* 类别 4：剧场收益 */}
                <div data-collection-category="revenue" style={{height:'var(--collection-card-height)'}} className={`flex min-w-0 flex-col rounded-2xl border transition-colors p-4 bg-white ${
                  enabledCategories.revenue ? 'border-indigo-300 shadow-xs ring-1 ring-indigo-500/10' : 'border-slate-200 opacity-75'
                }`}>
                  <label style={{height:'var(--collection-card-header-height)'}} className="flex shrink-0 items-start gap-3 cursor-pointer">
                    <input type="checkbox" aria-label="剧场收益" checked={enabledCategories.revenue}
                      disabled={!revenueReady} onChange={e => setEnabledCategories(prev => ({...prev, revenue: e.target.checked}))}
                      className="mt-1 w-4 h-4 shrink-0 rounded border-slate-300 text-indigo-600 focus:ring-indigo-500 cursor-pointer" />
                    <div>
                      <span className="text-sm font-extrabold text-slate-900">剧场收益</span>
                      <p className="text-xs text-slate-500 mt-1">自动补齐历史及缺失收益，已确认的日期不重复查询。</p>
                    </div>
                  </label>
                  <div data-collection-card-body className="mt-3.5 flex min-h-0 flex-1 flex-col justify-center gap-1 overflow-y-auto border-t border-slate-100 pl-7 pt-1 text-xs text-slate-600" aria-label="收益采集计划">
                    <div className="grid grid-cols-3 gap-2">
                      <div className="rounded-xl border border-slate-200 bg-slate-50 px-2 py-1"><span className="block text-[11px]">历史待补齐</span><strong className="mt-1 block text-sm text-indigo-700">{executionPlanSummary.revenueBackfillCount}<span className="ml-1 text-[10px] font-normal text-slate-500">个账号</span></strong></div>
                      <div className="rounded-xl border border-slate-200 bg-slate-50 px-2 py-1"><span className="block text-[11px]">待更新</span><strong className="mt-1 block text-sm text-indigo-700">{executionPlanSummary.revenueMissingCount}<span className="ml-1 text-[10px] font-normal text-slate-500">个账号</span></strong></div>
                      <div className="rounded-xl border border-slate-200 bg-slate-50 px-2 py-1"><span className="block text-[11px]">已完成跳过</span><strong className="mt-1 block text-sm text-indigo-700">{executionPlanSummary.revenueCompleteCount}<span className="ml-1 text-[10px] font-normal text-slate-500">个账号</span></strong></div>
                    </div>
                    {executionPlanSummary.revenueUnavailableCount > 0 && <p className="text-amber-700">{executionPlanSummary.revenueUnavailableCount} 个账号的收益采集器未配置或已停用，请在账号列表查看原因。</p>}
                    <p className="text-[11px] text-slate-400">历史补齐遇连续7天确认无收益后停止；查询失败或待更新会保留，下次继续。</p>
                  </div>
                </div>

              </div>
            </div>
          </div>
        )}

        {/* =================================================================== */}
        {/* STAGE 2: 实时执行流水、原因解释与未完成项精准重试视图 */}
        {/* =================================================================== */}
        {viewStage === 'monitor' && <AccountCollectionRecords profiles={accountProfiles} state={collectionState} busy={busy}
          progress={currentWaitExplanation} onStop={handleStopJob} onRetry={runtime.retryRecord} />}

        <div className="shrink-0 space-y-1.5 border-t border-slate-200/70 bg-white px-6 py-2 text-[11px]">
          {error && <p role="alert" className="text-rose-700">{error}</p>}
          {pollError && <p role="alert" className="text-amber-700">{pollError}；未重新发起采集。</p>}
          {notice && <p role="status" className="text-indigo-700">{notice}</p>}
          {!revenueReady && <p className="text-slate-500">剧场收益统一队列待接入；暂不能在此启动收益采集。{!dateRangeReady && '作品当前支持全量，按发布时间停止翻页待接入。'}{!forceDailyReady && '每日数据在线重置待接入。'}</p>}
          {viewStage==='plan' && executionError && !error && <p className="text-amber-700">{executionError}</p>}
        </div>
        {/* =================================================================== */}
        {/* 底部执行前透明摘要与主操作栏 */}
        {/* =================================================================== */}
        {viewStage==='plan' && <div className="px-6 py-4 bg-white border-t border-slate-200/90 flex flex-col lg:flex-row lg:items-center justify-between gap-4 shrink-0">
          {/* 执行前透明预演摘要：让用户清楚知道将处理什么、跳过什么 */}
          <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-slate-600">
            <span className="font-extrabold text-slate-900 flex items-center gap-1.5">
              <Eye className="w-4 h-4 text-indigo-600" />
              <span>本次执行预演 · {scenarioLabel || '自定义'}:</span>
            </span>
            <span>
              目标账号 <strong className="text-indigo-600 font-mono">{executionPlanSummary.selectedCount}</strong> 个
            </span>
            {enabledCategories.daily_stats && (
              <span>
                · 日数据: 需查 <strong className="text-slate-900 font-mono">{executionPlanSummary.dailyNeedFetchCount}</strong> 号
                (含历史待补齐 <strong className="text-purple-700 font-mono">{executionPlanSummary.dailyInitialBackfillCount}</strong> 号，自动跳过已完整 <strong className="text-emerald-600 font-mono">{executionPlanSummary.dailySkipCompleteCount}</strong> 号)
              </span>
            )}
            {(enabledCategories.daily_stats || enabledCategories.video_traffic || enabledCategories.optimization) && executionPlanSummary.platformUnavailableCount>0 && <span>· 平台类数据不适用 {executionPlanSummary.platformUnavailableCount} 号</span>}
            {enabledCategories.video_traffic && (
              <span>
                · 视频累计流量: 预计翻页 <strong className="text-indigo-600 font-mono">{executionPlanSummary.estimatedVideoPages === null ? '待分页确认' : `约${executionPlanSummary.estimatedVideoPages}`} </strong> 页 ({videoWaitMinSec}~{videoWaitMaxSec}s随机间隔){forceVideoUpdate && <strong className="ml-1 text-amber-700">· 强制更新</strong>}
              </span>
            )}
            {enabledCategories.revenue && (
              <span>
                · 收益: 待采集 <strong className="font-mono">{executionPlanSummary.revenueBackfillCount + executionPlanSummary.revenueMissingCount}</strong> 号 / 已完成跳过 <strong className="font-mono">{executionPlanSummary.revenueCompleteCount}</strong> 号
                {executionPlanSummary.revenueUnavailableCount>0 && <> / 未配置跳过 {executionPlanSummary.revenueUnavailableCount} 号</>}
              </span>
            )}
          </div>

          <div className="flex items-center gap-3 shrink-0">
            {jobState === 'running' || jobState === 'stopping' ? (
              <button
                type="button"
                onClick={handleStopJob}
                disabled={busy || jobState === 'stopping'}
                className="px-5 py-2.5 rounded-xl bg-rose-600 hover:bg-rose-700 disabled:opacity-50 text-white text-xs font-extrabold flex items-center gap-2 shadow-md transition-all cursor-pointer"
              >
                <Square className="w-3.5 h-3.5 fill-white" />
                <span>{jobState === 'stopping' ? '等待当前请求返回...' : '停止后续请求'}</span>
              </button>
            ) : (
              <button
                type="button"
                onClick={() => startCollectionJob()}
                disabled={busy || !collectionState || !!executionError}
                className="px-6 py-2.5 rounded-xl bg-gradient-to-r from-indigo-600 to-violet-600 hover:from-indigo-700 hover:to-violet-700 disabled:opacity-40 text-white text-xs font-extrabold flex items-center gap-2 shadow-md shadow-indigo-500/20 transition-all cursor-pointer"
              >
                <Play className="w-3.5 h-3.5 fill-white" />
                <span>
                  开始{scenarioLabel || '自定义采集'} ({executionPlanSummary.selectedCount}个账号 · {executionPlanSummary.activeCats.length}类数据)
                </span>
              </button>
            )}
          </div>
        </div>}
      </div>
    </CockpitModal>
  );
};
