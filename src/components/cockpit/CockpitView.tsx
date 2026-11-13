import { DataCollectionModal, type ActiveJobSummary } from './DataCollectionModal';
import { AccountLoginBadge } from './AccountLoginBadge';
import { MATRIX_SORT_OPTIONS, defaultMatrixSortOrder, sortMatrixAccounts, type MatrixSortKey, type MatrixSortOrder } from '../../services/accountMatrixSort';
import { AccountRatingBadge } from './AccountRatingBadge';
import { BusinessAccountStatusBadge } from './BusinessAccountStatusBadge';
import { AccountYesterdayMetrics } from './AccountYesterdayMetrics';
import { CockpitFilterSelect } from './CockpitFilterSelect';
import { AccountProfileTotals } from './AccountProfileTotals';
import { OverviewKpiCards } from './OverviewKpiCards';
import { eventDetail } from '../../services/dataChangeEvents';
import { VideoTrafficTags } from './VideoTrafficTags';
import { VideoTrafficFilter } from './VideoTrafficFilter';
import { VideoPagination } from './VideoPagination';
import { CockpitDateFilter } from './CockpitDateFilter';
import type { CockpitDateRange } from '../../services/cockpitDateRange';
import { AccountAvatar } from '../AccountAvatar';
import { WorkVideoCover } from './WorkVideoCover';
import React, { useState, useMemo, useEffect, useCallback, useRef } from 'react';
import { loadOperationsDashboard, type OperationsDashboardData } from '../../api/operationsDashboard';
import { createCockpitModel } from '../../services/cockpitModel';
import { ACCOUNT_DISPLAY_SCOPES, type AccountDisplayScope } from '../../services/accountVisibility';
import { getOptimizationHealth, formatOptimizationRate } from '../../services/optimizationHealth';
import { rateVideoTraffic, VIDEO_TRAFFIC_RULES, type VideoTrafficStatus } from '../../services/videoTrafficRating';
import { CockpitDataContext, useCockpitData } from './CockpitDataContext';
import { 
  AccountInfo, 
  VideoTrafficItem, 
  SimplifiedOptimizationReason,
  OFFICIAL_OPTIMIZATION_DEFINITIONS
} from '../../types/shortDramaOps';
import { 
  DualTrendChart, 
  DualTrendLegend,
  OptimizationReasonBarChart
} from './InteractiveCharts';
import { AccountDetailDrawer } from './AccountDetailDrawer';
import { VideoDetailDrawer } from './VideoDetailDrawer';
import { AccountOptimizationView } from './AccountOptimizationView';
import { DataPivotView } from './DataPivotView';
import { 
  Tv, 
  Search, 
  TrendingUp, 
  DollarSign, 
  Play, 
  Users, 
  Heart, 
  AlertTriangle, 
  Film, 
  ArrowUpDown, 
  Clock, 
  ChevronRight, 
  Sparkles, 
  ShieldAlert, 
  RefreshCw, 
  Building2, 
  Eye, 
  Award,
  Crown,
  Medal,
  Table,
  CheckCircle2,
  ExternalLink,
  MessageSquare,
  Share2,
  ThumbsUp
} from 'lucide-react';

interface CockpitViewProps {
  showToast?: (msg: string) => void;
}

type CockpitTab = 'overview' | 'matrix' | 'accountOptimization' | 'videos' | 'pivot';
const DEFAULT_ACCOUNT_SCOPES: Record<CockpitTab, AccountDisplayScope> = {overview:'all',matrix:'current',accountOptimization:'current',videos:'current',pivot:'all'};

const interactionCount = (value: number) => value >= 10_000
  ? new Intl.NumberFormat('zh-CN', { notation: 'compact', maximumFractionDigits: value >= 1_000_000 ? 0 : 1 }).format(value)
  : value.toLocaleString('zh-CN');

export const CockpitView: React.FC<CockpitViewProps> = ({ showToast = () => {} }) => {
  const [data, setData] = useState<OperationsDashboardData | null>(null);
  const [error, setError] = useState('');
  const [workScope, setWorkScope] = useState<'all' | 'software'>('all');
  const [activeTab, setActiveTab] = useState<CockpitTab>('overview');
  const [accountScopes, setAccountScopes] = useState(DEFAULT_ACCOUNT_SCOPES);
  const accountScope = accountScopes[activeTab];
  const changeAccountScope = (scope: AccountDisplayScope) => setAccountScopes(previous => ({...previous,[activeTab]:scope}));
  const [refreshing, setRefreshing] = useState(false);
  const request = useRef(0);
  const reload = useCallback(async () => {
    const current = ++request.current;
    setRefreshing(true);
    try {
      const result = await loadOperationsDashboard();
      if (current !== request.current) return;
      setData(result);
      setError('');
    } catch (e) {
      if (current === request.current) setError(e instanceof Error ? e.message : '数据库读取失败');
    } finally {
      if (current === request.current) setRefreshing(false);
    }
  }, []);
  useEffect(() => { void reload(); return () => { ++request.current; }; }, [reload]);
  useEffect(() => {
    const changed = (event: Event) => { if (['account_changed', 'theater_changed'].includes(eventDetail(event).changeType || '')) void reload(); };
    window.addEventListener('v2-data-changed', changed);
    return () => window.removeEventListener('v2-data-changed', changed);
  }, [reload]);
  const fullModel = useMemo(() => data ? createCockpitModel(data,workScope) : null, [data,workScope]);
  const model = useMemo(() => accountScope === 'all' ? fullModel : data ? createCockpitModel(data,workScope,accountScope) : null, [data,workScope,accountScope,fullModel]);
  if (!model) return <div className="min-h-[500px] flex flex-col items-center justify-center gap-4 text-slate-500">
    <p>{error || '正在读取运营数据…'}</p>
    {error && <button onClick={() => void reload()} className="rounded-xl bg-indigo-600 px-5 py-2 text-white">重新读取</button>}
  </div>;
  return <CockpitDataContext.Provider value={model}>
    {error && <div role="alert" className="mb-3 rounded-xl bg-amber-50 p-3 text-sm text-amber-800">读取失败，保留上次数据：{error}</div>}
    <CockpitContent activeTab={activeTab} setActiveTab={setActiveTab} accountScope={accountScope} onAccountScopeChange={changeAccountScope} allAccounts={fullModel!.ACCOUNTS} onWorkScopeChange={setWorkScope} showToast={showToast} refreshing={refreshing} onRefresh={() => void reload()} />
  </CockpitDataContext.Provider>;
};

const CockpitContent: React.FC<CockpitViewProps & { refreshing: boolean; onRefresh: () => void; onWorkScopeChange: (scope:'all'|'software')=>void; activeTab: CockpitTab; setActiveTab: (tab:CockpitTab)=>void; accountScope: AccountDisplayScope; onAccountScopeChange:(scope:AccountDisplayScope)=>void; allAccounts:AccountInfo[] }> = ({
  showToast = () => {}, refreshing, onRefresh, onWorkScopeChange, activeTab, setActiveTab, accountScope, onAccountScopeChange, allAccounts,
}) => {
  const model = useCockpitData();
  const { ENABLED_THEATERS, ACCOUNTS, VIDEO_TRAFFIC_DATA, HISTORY_VIDEOS, HISTORICAL_REVENUE, HISTORICAL_TRAFFIC,
    OPTIMIZATION_RECORDS, getKPISummary, filterRevenue, filterTraffic, filterTrafficDetails, filterVideos, getAccountRankings,
    getAccountOptimizationStats, getOptimizationReasonDistribution, getDateBounds, latestDate } = model;
  const enabledTheaterCount = ENABLED_THEATERS.length;
  const availableAccountCount = ACCOUNTS.length;
  // 1. 全局筛选状态
  const [selectedTheater, setSelectedTheater] = useState<string>('ALL'); // 剧场
  const [selectedAccountId, setSelectedAccountId] = useState<string>('ALL'); // 账号 (级联)
  const [dateRange, setDateRange] = useState<CockpitDateRange>('7days');
  const searchQuery = '';
  const [selectedReasonFilter, setSelectedReasonFilter] = useState<SimplifiedOptimizationReason | null>(null);
  useEffect(() => {
    if (selectedReasonFilter !== null && !Object.hasOwn(model.optimizationDefinitions, selectedReasonFilter)) setSelectedReasonFilter(null);
  }, [model.optimizationDefinitions, selectedReasonFilter]);

  // 2. 主导航 Tab：5大业务视角
  // 1: 经营大盘 (以账号为单位的收益与播放大盘)
  // 2: 矩阵账号运营概览 (每张卡显示全量流量数据)
  // 3: 账号发视频优化分析 (以账号为核心，替代旧剧目留存)
  // 4: 视频流量明细 (以账号发布视频为重点)
  // 5: 数据透视导出；优化统计与通知统一在账号优化内。


  // 3. 经营大盘榜单排序切换 (按收益 / 按播放量 / 按发片量 / 按优化率)
  const [overviewLeaderboardSort, setOverviewLeaderboardSort] = useState<'revenue' | 'views' | 'optimizationRate' | 'videoCount'>('revenue');

  const [matrixSort, setMatrixSort] = useState<{ key: MatrixSortKey; order: MatrixSortOrder }>({ key: 'revenue', order: 'desc' });

  // 4. 视频排序
  const [videoSortBy, setVideoSortBy] = useState<'views' | 'completionRate' | 'publishTime' | 'hearts'>('views');
  const [sortOrder, setSortOrder] = useState<'desc' | 'asc'>('desc');
  const [videoViewMode, setVideoViewMode] = useState<'card' | 'grouped'>('card');
  const [selectedVideoTag,setSelectedVideoTag]=useState<VideoTrafficStatus|'ALL'>('ALL');
  const [videoTagRevision,setVideoTagRevision]=useState(0);
  const [videoPage,setVideoPage]=useState(1);
  const [videoPageSize,setVideoPageSize]=useState(24);
  const videoListStart=useRef<HTMLDivElement>(null);

  // 5. 抽屉状态
  const [activeAccount, setActiveAccount] = useState<AccountInfo | null>(null);
  const [activeVideo, setActiveVideo] = useState<VideoTrafficItem | null>(null);

  useEffect(() => {
    setSelectedAccountId(current => current === 'ALL' || ACCOUNTS.some(a => a.id === current) ? current : 'ALL');
    setActiveAccount(current => current ? ACCOUNTS.find(a => a.id === current.id) || null : null);
    setActiveVideo(current => current ? [...HISTORY_VIDEOS,...VIDEO_TRAFFIC_DATA].find(v => v.id === current.id && v.accountId === current.accountId) || null : null);
  }, [model]);

  const isRefreshing = refreshing;
  const [collectionOpen, setCollectionOpen] = useState(false);
  const [collectionSummary, setCollectionSummary] = useState<ActiveJobSummary>({isRunning: false, isStopping: false, status: 'idle', completedAccounts: 0, totalAccounts: 0, failedCount: 0});
  const collectionRunning = collectionSummary.isRunning;
  const [collectionAccountIds, setCollectionAccountIds] = useState<string[]>([]);

  useEffect(() => {
    if (selectedTheater !== 'ALL' && !model.THEATERS.some(theater => theater.name === selectedTheater)) {
      setSelectedTheater('ALL');
      setSelectedAccountId('ALL');
    }
  }, [model, selectedTheater]);

  // 级联处理：根据选中的剧场动态计算可用账号 (硬约束：1账号绑定1剧场，1剧场绑定多账号)
  const availableAccounts = useMemo(() => {
    if (selectedTheater === 'ALL') {
      return ACCOUNTS;
    }
    return ACCOUNTS.filter(a => a.theaterName === selectedTheater);
  }, [selectedTheater, model]);

  // 当切换剧场时，如果当前选中的账号不属于该剧场，重置为 'ALL'
  const handleTheaterChange = (theater: string) => {
    setSelectedTheater(theater);
    if (theater !== 'ALL') {
      const match = ACCOUNTS.find(a => a.id === selectedAccountId && a.theaterName === theater);
      if (!match) {
        setSelectedAccountId('ALL');
      }
    }
  };

  // 综合指标汇总
  const kpi = useMemo(() => {
    return getKPISummary(selectedTheater, selectedAccountId, dateRange);
  }, [selectedTheater, selectedAccountId, dateRange, model]);

  // 过滤后的收益数据
  const currentRevenueList = useMemo(() => {
    return filterRevenue(selectedTheater, selectedAccountId, dateRange);
  }, [selectedTheater, selectedAccountId, dateRange, model]);

  // 过滤后的账号日流量
  const currentTrafficList = useMemo(() => {
    return filterTraffic(selectedTheater, selectedAccountId, dateRange);
  }, [selectedTheater, selectedAccountId, dateRange, model]);

  // 过滤后的视频切片数据 (严格按账号过滤和剧名-n搜索)
  const currentVideos = useMemo(() => {
    let list = filterVideos(selectedTheater, selectedAccountId, dateRange, searchQuery);

    return [...list].sort((a, b) => {
      let valA = a[videoSortBy];
      let valB = b[videoSortBy];
      if (typeof valA === 'string') {
        return sortOrder === 'desc' 
          ? (valB as string).localeCompare(valA as string) 
          : (valA as string).localeCompare(valB as string);
      }
      return sortOrder === 'desc' ? (valB as number) - (valA as number) : (valA as number) - (valB as number);
    });
  }, [selectedTheater, selectedAccountId, dateRange, searchQuery, videoSortBy, sortOrder, model]);

  // Count before tag filtering; only the work-performance views apply the selected tag.
  const videoTagStats=useMemo(()=>{
    const now=Date.now();
    const ratings=new Map<string,ReturnType<typeof rateVideoTraffic>>(currentVideos.map(video=>[video.id,rateVideoTraffic(video,now)] as const));
    const counts=Object.fromEntries(VIDEO_TRAFFIC_RULES.map(item=>[item.status,0])) as Record<VideoTrafficStatus,number>;
    let nextEvaluationAt:number|undefined;
    for(const rating of ratings.values()){
      counts[rating.status]++;
      if(rating.nextEvaluationAt!==undefined&&(nextEvaluationAt===undefined||rating.nextEvaluationAt<nextEvaluationAt))nextEvaluationAt=rating.nextEvaluationAt;
    }
    return {ratings,counts,nextEvaluationAt};
  },[currentVideos,videoTagRevision,activeTab]);
  useEffect(()=>{
    if(activeTab!=='videos'||videoTagStats.nextEvaluationAt===undefined)return;
    const timer=setTimeout(()=>setVideoTagRevision(n=>n+1),Math.max(1000,videoTagStats.nextEvaluationAt-Date.now()+50));
    return ()=>clearTimeout(timer);
  },[activeTab,videoTagStats.nextEvaluationAt,videoTagRevision]);
  const tagFilteredVideos=useMemo(()=>selectedVideoTag==='ALL'?currentVideos:currentVideos.filter(video=>videoTagStats.ratings.get(video.id)?.status===selectedVideoTag),[currentVideos,selectedVideoTag,videoTagStats]);
  const videoPageCount=Math.max(1,Math.ceil(tagFilteredVideos.length/videoPageSize));
  const visibleVideoPage=Math.max(1,Math.min(videoPage,videoPageCount));
  useEffect(()=>setVideoPage(1),[selectedTheater,selectedAccountId,dateRange,searchQuery,selectedVideoTag,videoSortBy,sortOrder,videoPageSize,model]);
  useEffect(()=>setVideoPage(page=>Math.max(1,Math.min(page,videoPageCount))),[videoPageCount]);
  const pagedVideos=useMemo(()=>tagFilteredVideos.slice((visibleVideoPage-1)*videoPageSize,visibleVideoPage*videoPageSize),[tagFilteredVideos,visibleVideoPage,videoPageSize]);
  const renderVideoPagination=(position:'top'|'bottom')=><VideoPagination total={tagFilteredVideos.length} page={visibleVideoPage} pageSize={videoPageSize} position={position}
    onPageChange={page=>{
      setVideoPage(page);
      if(position==='bottom')requestAnimationFrame(()=>videoListStart.current?.scrollIntoView({block:'start'}));
    }}
    onPageSizeChange={size=>{
      setVideoPageSize(size);
      if(position==='bottom')requestAnimationFrame(()=>videoListStart.current?.scrollIntoView({block:'start'}));
    }}/>

  // 账号发视频优化分析数据 (以账号为单位)
  const accountOptimizationStats = useMemo(() => {
    return getAccountOptimizationStats(selectedTheater, dateRange).filter(s => selectedAccountId === 'ALL' || s.accountId === selectedAccountId);
  }, [selectedTheater, dateRange, selectedAccountId, model]);
  const accountOptimizationVideos=useMemo(()=>HISTORY_VIDEOS.filter(v=>(selectedTheater==='ALL'||v.theater===selectedTheater)&&(selectedAccountId==='ALL'||v.accountId===selectedAccountId)&&model.isDateInRange(v.publishTime.slice(0,10),dateRange)),[selectedTheater,selectedAccountId,dateRange,model]);

  // 暂行作品分析标签分布
  const reasonDistribution = useMemo(() => {
    return getOptimizationReasonDistribution(selectedTheater, selectedAccountId, dateRange);
  }, [selectedTheater, selectedAccountId, dateRange, model]);

  // 账号经营与流量榜单 (以账号为单位)
  const accountRankings = useMemo(() => {
    return getAccountRankings(selectedTheater, dateRange, overviewLeaderboardSort).filter(s => selectedAccountId === 'ALL' || s.account.id === selectedAccountId);
  }, [selectedTheater, dateRange, selectedAccountId, overviewLeaderboardSort, model]);

  const matrixAccounts = useMemo(() => {
    // Build equal-value ties in catalog order, independently of the overview leaderboard.
    const ranks = new Map(getAccountRankings(selectedTheater, dateRange).map(item => [item.account.id, item]));
    const items = ACCOUNTS.filter(account => selectedAccountId === 'ALL' || account.id === selectedAccountId)
      .flatMap(account => { const item = ranks.get(account.id); return item ? [item] : []; });
    return sortMatrixAccounts(items, matrixSort.key, matrixSort.order);
  }, [selectedTheater, dateRange, selectedAccountId, matrixSort, model]);

  const periodBounds = getDateBounds(dateRange);
  const handleRefresh = () => {
    setCollectionAccountIds(selectedAccountId === 'ALL' ? availableAccounts.map(a => a.id) : [selectedAccountId]);
    setCollectionOpen(true);
  };

  return (
    <div className="min-h-screen bg-[#F4F6F9] text-slate-800 pb-16">
      {/* 顶部系统公告与导航条 */}
      <header className="bg-white border-b border-slate-200/90 sticky top-0 z-30 shadow-xs">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex items-center justify-between h-16">
            {/* 左侧品牌 */}
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 rounded-xl bg-gradient-to-tr from-indigo-600 via-indigo-500 to-purple-600 flex items-center justify-center text-white shadow-md shadow-indigo-100 ring-2 ring-indigo-500/10">
                <Film className="w-5 h-5" />
              </div>
              <div>
                <div className="flex items-center gap-2">
                  <h1 className="text-base font-extrabold text-slate-900 tracking-tight">
                    短剧运营驾驶舱
                  </h1>
                </div>
                <p className="text-[11px] text-slate-400">
                  {enabledTheaterCount} 个剧场 · {availableAccountCount} 个账号 · 数据截至 {latestDate || '暂无记录'}
                </p>
              </div>
            </div>

            {/* 中间 5大业务Tab导航 */}
            <nav className="hidden lg:flex items-center gap-1 bg-slate-100/90 p-1 rounded-xl border border-slate-200/80">
              <button
                onClick={() => setActiveTab('overview')}
                className={`px-3.5 py-1.5 rounded-lg text-xs font-bold transition-all flex items-center gap-1.5 cursor-pointer ${
                  activeTab === 'overview'
                    ? 'bg-white text-indigo-600 shadow-xs'
                    : 'text-slate-600 hover:text-slate-900'
                }`}
              >
                <TrendingUp className="w-3.5 h-3.5" />
                <span>经营总览</span>
              </button>

              <button
                onClick={() => setActiveTab('matrix')}
                className={`px-3.5 py-1.5 rounded-lg text-xs font-bold transition-all flex items-center gap-1.5 cursor-pointer ${
                  activeTab === 'matrix'
                    ? 'bg-white text-indigo-600 shadow-xs'
                    : 'text-slate-600 hover:text-slate-900'
                }`}
              >
                <Building2 className="w-3.5 h-3.5" />
                <span>账号矩阵</span>
              </button>

              <button
                onClick={() => setActiveTab('accountOptimization')}
                className={`px-3.5 py-1.5 rounded-lg text-xs font-bold transition-all flex items-center gap-1.5 cursor-pointer ${
                  activeTab === 'accountOptimization'
                    ? 'bg-white text-indigo-600 shadow-xs'
                    : 'text-slate-600 hover:text-slate-900'
                }`}
              >
                <ShieldAlert className="w-3.5 h-3.5 text-rose-500" />
                <span>账号优化</span>
              </button>

              <button
                onClick={() => setActiveTab('videos')}
                className={`px-3.5 py-1.5 rounded-lg text-xs font-bold transition-all flex items-center gap-1.5 cursor-pointer ${
                  activeTab === 'videos'
                    ? 'bg-white text-indigo-600 shadow-xs'
                    : 'text-slate-600 hover:text-slate-900'
                }`}
              >
                <Play className="w-3.5 h-3.5" />
                <span>作品表现</span>
                <span className="text-[10px] px-1.5 py-0.2 rounded-full bg-slate-200 text-slate-700">
                  {currentVideos.length}
                </span>
              </button>



              <button
                onClick={() => setActiveTab('pivot')}
                className={`px-3.5 py-1.5 rounded-lg text-xs font-bold transition-all flex items-center gap-1.5 cursor-pointer ${
                  activeTab === 'pivot'
                    ? 'bg-white text-indigo-600 shadow-xs'
                    : 'text-slate-600 hover:text-slate-900'
                }`}
              >
                <Table className="w-3.5 h-3.5" />
                <span>数据导出</span>
              </button>
            </nav>

            {/* 右侧动作 */}
            <div className="flex items-center gap-2">
              <button
                onClick={handleRefresh}
                disabled={isRefreshing}
                className="flex items-center gap-1.5 px-3 py-2 text-xs font-semibold text-slate-600 hover:text-indigo-600 hover:bg-slate-100 rounded-xl transition-all cursor-pointer"
                title="打开V3数据采集与补缺中心"
              >
                <RefreshCw className={`w-4 h-4 ${collectionRunning ? 'animate-spin text-indigo-600' : ''}`} />
                {collectionRunning ? `采集中 ${collectionSummary.completedAccounts}/${collectionSummary.totalAccounts}` : collectionSummary.failedCount > 0 ? `数据采集 (${collectionSummary.failedCount}项待重试)` : '数据采集 / 刷新'}
              </button>
              <button onClick={onRefresh} disabled={isRefreshing} aria-label="重新读取已保存数据" title="只重新读取已保存数据，不发起外部采集" className="rounded-xl p-2 text-slate-400 hover:bg-slate-100 hover:text-indigo-600"><RefreshCw className={`h-3.5 w-3.5 ${isRefreshing ? 'animate-spin' : ''}`} /></button>
            </div>
          </div>
        </div>

        {/* 移动端横向滚动Tab栏 */}
        <div className="lg:hidden flex items-center gap-2 px-4 py-2 border-t border-slate-100 overflow-x-auto bg-slate-50">
          <button
            onClick={() => setActiveTab('overview')}
            className={`px-3 py-1 rounded-lg text-xs font-bold whitespace-nowrap ${
              activeTab === 'overview' ? 'bg-indigo-600 text-white' : 'text-slate-600'
            }`}
          >
            经营总览
          </button>
          <button
            onClick={() => setActiveTab('matrix')}
            className={`px-3 py-1 rounded-lg text-xs font-bold whitespace-nowrap ${
              activeTab === 'matrix' ? 'bg-indigo-600 text-white' : 'text-slate-600'
            }`}
          >
            账号矩阵
          </button>
          <button
            onClick={() => setActiveTab('accountOptimization')}
            className={`px-3 py-1 rounded-lg text-xs font-bold whitespace-nowrap ${
              activeTab === 'accountOptimization' ? 'bg-indigo-600 text-white' : 'text-slate-600'
            }`}
          >
            账号优化
          </button>
          <button
            onClick={() => setActiveTab('videos')}
            className={`px-3 py-1 rounded-lg text-xs font-bold whitespace-nowrap ${
              activeTab === 'videos' ? 'bg-indigo-600 text-white' : 'text-slate-600'
            }`}
          >
            作品表现
          </button>

          <button
            onClick={() => setActiveTab('pivot')}
            className={`px-3 py-1 rounded-lg text-xs font-bold whitespace-nowrap ${
              activeTab === 'pivot' ? 'bg-indigo-600 text-white' : 'text-slate-600'
            }`}
          >
            数据导出
          </button>
        </div>
      </header>

      {/* 全局业务控制与筛选条 (级联筛选 剧场 × 账号) */}
      <div className="bg-white border-b border-slate-200/80 mb-6 shadow-xs">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-3">
          <div className="flex flex-wrap items-center justify-between gap-3">
            {/* 左侧：剧场与账号 1:N 级联筛选 */}
            <div className="flex flex-wrap items-center gap-2.5">
              {/* 剧场选择 (支持十几个剧场) */}
              <CockpitFilterSelect label="剧场" icon={<Tv className="h-3.5 w-3.5" />} value={selectedTheater}
                allOption={{ value: 'ALL', label: `全部剧场 (${model.THEATERS.length}大剧场)` }}
                options={model.THEATERS.map(theater => ({ value: theater.name, label: theater.name, description: theater.code || undefined }))}
                onChange={handleTheaterChange} placeholder="搜索剧场名称" />

              <div role="group" aria-label="账号状态范围" className="flex flex-wrap items-center gap-1 rounded-xl bg-slate-100 p-1">
                {ACCOUNT_DISPLAY_SCOPES.map(scope => <button key={scope.value} type="button" aria-pressed={accountScope===scope.value}
                  onClick={() => {onAccountScopeChange(scope.value);setSelectedAccountId('ALL');}}
                  className={`rounded-lg px-2.5 py-1.5 text-xs font-semibold ${accountScope===scope.value?'bg-white text-indigo-700 shadow-sm':'text-slate-500 hover:text-slate-800'}`}>{scope.label}</button>)}
              </div>

              {/* 账号选择 (级联) */}
              <CockpitFilterSelect label="账号" icon={<Users className="h-3.5 w-3.5" />} value={selectedAccountId}
                allOption={{ value: 'ALL', label: `全部账号 (${availableAccounts.length}个)` }}
                options={availableAccounts.map(account => ({ value: account.id, label: account.name, description: `${account.theaterName} · ${account.businessStatus || '正常'}`,
                  meta: `${account.tier}${account.rating ? ` · ${account.rating.phase}` : ''}`, searchText: account.channelId,
                  trailing: <AccountRatingBadge account={account} size="sm" displayOnly />,
                  leading: <AccountAvatar name={account.name} url={account.avatarUrl} className="h-7 w-7" /> }))}
                onChange={setSelectedAccountId} placeholder="搜索账号名称或 ID" minWidth={336} />

              <CockpitDateFilter value={dateRange} onChange={setDateRange} />
            </div>

            {/* 右侧：快速过滤与搜索 */}
            <div role="group" aria-label="作品统计范围" className="flex items-center gap-1 rounded-xl bg-slate-100 p-1">
              {([['all','全部作品'],['software','仅看软件']] as const).map(([scope,label]) =>
                <button key={scope} type="button" aria-pressed={model.workScope===scope} onClick={()=>onWorkScopeChange(scope)}
                  className={`rounded-lg px-4 py-1.5 text-xs font-semibold ${model.workScope===scope ? 'bg-white text-indigo-700 shadow-sm' : 'text-slate-500 hover:text-slate-800'}`}>{label}</button>)}
            </div>
          </div>
        </div>
      </div>

      {/* 主体内容区 */}
      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        {/* ========================================================= */}
        {/* TAB 1: 经营大盘 (Overview) - 彻底以账号为单位展现收益与播放 */}
        {/* ========================================================= */}
        {activeTab === 'overview' && (
          <div className="space-y-6">
            <p data-account-scope-summary className="text-xs text-slate-500">统计范围：{ACCOUNT_DISPLAY_SCOPES.find(scope=>scope.value===accountScope)?.label} · 金额、走势、排行及明细使用同一范围{accountScope==='all'?'，包含停用和注销账号的历史数据。':'。'}</p>
            <OverviewKpiCards summary={kpi} days={periodBounds.days} />

            {/* 2. 双轴走势图 (收益 vs 播放量 全月走势) */}
            <section aria-label="矩阵收益与播放走势" className="bg-white rounded-2xl p-6 border border-slate-200/80 shadow-xs">
              <div data-trend-header className="mb-4 flex flex-col gap-3 border-b border-slate-100 pb-4 md:flex-row md:items-center md:justify-between">
                <div className="flex min-w-0 items-center gap-2">
                  <span className="shrink-0 p-2 bg-indigo-50 text-indigo-600 rounded-xl">
                    <TrendingUp className="w-4 h-4" />
                  </span>
                  <div>
                    <h3 className="text-sm font-bold text-slate-800">全矩阵日收益与总播放量双轴联动走势</h3>
                    <p className="text-[11px] text-slate-400">追踪每日收益变现高峰与公域流量波动的耦合关联</p>
                  </div>
                </div>
                <div data-trend-meta className="flex shrink-0 flex-col items-start gap-2 md:items-end">
                  <span aria-label="走势日期范围" className="text-[11px] font-mono text-slate-400">{periodBounds.start} 至 {periodBounds.end}</span>
                  <DualTrendLegend />
                </div>
              </div>
              <DualTrendChart 
                showHeader={false}
                dateBounds={periodBounds}
                revenueData={currentRevenueList.filter(r => r.periodType !== 'month_cumulative')}
                trafficData={currentTrafficList}
              />
            </section>

            {/* 3. 经营大盘核心改版：以账号为单位的收益与播放大盘 (排行榜与分布矩阵) */}
            <div className="bg-white rounded-2xl p-6 border border-slate-200/80 shadow-xs space-y-6">
              {/* 标题与控制切换 */}
              <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 pb-4 border-b border-slate-100">
                <div className="flex items-center gap-2.5">
                  <span className="p-2 bg-indigo-50 text-indigo-600 rounded-xl">
                    <Crown className="w-5 h-5 text-amber-500" />
                  </span>
                  <div>
                    <h3 className="text-base font-bold text-slate-900">
                      账号经营与流量表现大盘 ({accountRankings.length}个账号)
                    </h3>
                    <p className="text-xs text-slate-500 mt-0.5">
                      以账号为核心核算创收贡献、播放流量、发片产出与风险指标
                    </p>
                  </div>
                </div>

                {/* 榜单排序维度切换 */}
                <div className="flex items-center gap-2">
                  <span className="text-xs text-slate-400 font-medium">排序维度:</span>
                  <div className="inline-flex p-1 bg-slate-100 rounded-xl text-xs font-medium">
                    <button
                      onClick={() => setOverviewLeaderboardSort('revenue')}
                      className={`px-3 py-1.5 rounded-lg transition-all ${
                        overviewLeaderboardSort === 'revenue'
                          ? 'bg-white text-emerald-700 font-bold shadow-xs'
                          : 'text-slate-600 hover:text-slate-900'
                      }`}
                    >
                      按收益排行
                    </button>
                    <button
                      onClick={() => setOverviewLeaderboardSort('views')}
                      className={`px-3 py-1.5 rounded-lg transition-all ${
                        overviewLeaderboardSort === 'views'
                          ? 'bg-white text-indigo-700 font-bold shadow-xs'
                          : 'text-slate-600 hover:text-slate-900'
                      }`}
                    >
                      按播放量排行
                    </button>
                    <button
                      onClick={() => setOverviewLeaderboardSort('videoCount')}
                      className={`px-3 py-1.5 rounded-lg transition-all ${
                        overviewLeaderboardSort === 'videoCount'
                          ? 'bg-white text-slate-800 font-bold shadow-xs'
                          : 'text-slate-600 hover:text-slate-900'
                      }`}
                    >
                      按发片量
                    </button>
                    <button
                      onClick={() => setOverviewLeaderboardSort('optimizationRate')}
                      className={`px-3 py-1.5 rounded-lg transition-all ${
                        overviewLeaderboardSort === 'optimizationRate'
                          ? 'bg-white text-rose-700 font-bold shadow-xs'
                          : 'text-slate-600 hover:text-slate-900'
                      }`}
                    >
                      按优化率 (风险)
                    </button>
                  </div>
                </div>
              </div>

              {/* 前三甲领奖台视觉卡片 (Top 3 突出显示) */}
              {accountRankings.length >= 3 && (
                <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                  {accountRankings.slice(0, 3).map((item, idx) => {
                    const medalBg = idx === 0 
                      ? 'bg-gradient-to-br from-amber-50 to-orange-50 border-amber-200/90 text-amber-900' 
                      : idx === 1 
                      ? 'bg-gradient-to-br from-slate-50 to-zinc-100 border-slate-300 text-slate-800' 
                      : 'bg-gradient-to-br from-amber-50/40 to-yellow-100/50 border-amber-300/70 text-amber-800';
                    const medalBadge = idx === 0 ? '🥇 TOP 1 · 王牌' : idx === 1 ? '🥈 TOP 2 · 主力' : '🥉 TOP 3 · 潜力';

                    return (
                      <div
                        key={item.account.id}
                        onClick={() => setActiveAccount(item.account)}
                        data-account-podium={idx + 1}
                        className={`p-5 rounded-2xl border shadow-xs transition-all hover:shadow-md cursor-pointer relative overflow-hidden ${medalBg}`}
                      >
                        <div className="flex flex-wrap items-center justify-between gap-2 mb-3">
                          <span className="whitespace-nowrap text-xs font-black px-2.5 py-1 rounded-full bg-white/90 shadow-2xs font-mono">
                            {medalBadge}
                          </span>
                          <span className="ml-auto inline-flex"><AccountRatingBadge account={item.account} compact /></span>
                        </div>

                        <div className="flex items-center gap-3 mb-4">
                          <AccountAvatar name={item.account.name} url={item.account.avatarUrl} className="w-11 h-11" />
                          <div className="min-w-0">
                            <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
                              <h4 className="max-w-full truncate font-extrabold text-sm text-slate-900">{item.account.name}</h4>
                              <span className="whitespace-nowrap text-[11px] font-bold px-2 py-0.5 rounded bg-white/80 border border-slate-200/60 text-slate-700">{item.account.theaterName}</span>
                            </div>
                            <AccountProfileTotals account={item.account} />
                          </div>
                        </div>

                        <div className="grid grid-cols-3 gap-2 p-3 bg-white/90 rounded-xl border border-slate-200/60 text-center font-mono">
                          <div>
                            <div className="text-[10px] text-slate-400 font-sans">创收金额</div>
                            <div className="font-black text-emerald-600 text-sm">{item.hasPeriodRevenue ? `¥${item.revenue.toLocaleString()}` : item.monthlyRevenue !== null ? '仅月累计' : '—'}</div>
                          </div>
                          <div>
                            <div className="text-[10px] text-slate-400 font-sans">区间播放</div>
                            <div className="font-black text-indigo-600 text-sm">{item.hasPeriodTraffic ? `${(item.views / 10000).toFixed(1)}w` : '—'}</div>
                          </div>
                          <div>
                            <div className="text-[10px] text-slate-400 font-sans">万播RPM</div>
                            <div className="font-black text-purple-600 text-sm">
                              {item.hasPeriodRevenue && item.hasPeriodTraffic && item.views > 0 ? `¥${item.rpm}` : '—'}
                            </div>
                          </div>
                        </div>
                      </div>
                    );
                  })}
                </div>
              )}

              {/* 账号全量排行榜表格/卡片清单 (清晰紧凑的视觉节奏) */}
              <div className="border border-slate-200/80 rounded-xl overflow-hidden">
                <div className="bg-slate-50/80 px-4 py-3 border-b border-slate-200 flex items-center justify-between text-xs font-semibold text-slate-500">
                  <span>全量账号排行 (共 {accountRankings.length} 个账号，点击查看详情)</span>
                  <span>涵盖 {enabledTheaterCount} 个剧场</span>
                </div>

                <div className="overflow-x-auto">
                  <table className="w-full text-left text-xs">
                    <thead>
                      <tr className="bg-white border-b border-slate-100 text-slate-400 font-medium">
                        <th className="py-3 px-4 w-12 text-center">排名</th>
                        <th className="py-3 px-4">账号名称</th>
                        <th className="py-3 px-4">绑定剧场</th>
                        <th className="py-3 px-4">账号标签</th>
                        <th className="py-3 px-4 text-right">创收金额 (元)</th>
                        <th className="py-3 px-4 text-right">区间播放</th>
                        <th className="py-3 px-4 text-right">净增关注</th>
                        <th className="py-3 px-4 text-right">万播RPM</th>
                        <th className="py-3 px-4 text-center">发片数</th>
                        <th className="py-3 px-4 text-center">优化率</th>
                        <th className="py-3 px-4 text-center">操作</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-100 text-slate-700">
                      {accountRankings.map((item, idx) => {
                        const rankNum = idx + 1;
                        return (
                          <tr
                            key={item.account.id}
                            onClick={() => setActiveAccount(item.account)}
                            className="hover:bg-slate-50/80 transition-colors cursor-pointer"
                          >
                            <td className="py-3 px-4 text-center font-mono font-bold text-slate-400">
                              {rankNum <= 3 ? (
                                <span className={`inline-block w-5 h-5 rounded-full text-white text-[10px] leading-5 font-bold ${
                                  rankNum === 1 ? 'bg-amber-500' : rankNum === 2 ? 'bg-slate-400' : 'bg-amber-700'
                                }`}>
                                  {rankNum}
                                </span>
                              ) : (
                                rankNum
                              )}
                            </td>

                            <td className="py-3 px-4 font-bold text-slate-900 flex items-center gap-2.5">
                              <AccountAvatar name={item.account.name} url={item.account.avatarUrl} className="w-7 h-7" />
                              <span className="hover:text-indigo-600 transition-colors">{item.account.name}</span>
                            </td>

                            <td className="py-3 px-4">
                              <span className="px-2 py-0.5 rounded-md bg-indigo-50 text-indigo-700 font-semibold border border-indigo-100">
                                {item.account.theaterName}
                              </span>
                            </td>

                            <td className="py-3 px-4">
                              <AccountRatingBadge account={item.account} compact />
                            </td>

                            <td className="py-3 px-4 text-right font-mono font-black text-emerald-600">
                              {item.hasPeriodRevenue ? `¥${item.revenue.toLocaleString()}` : item.monthlyRevenue !== null ? '仅月累计' : '—'}
                            </td>

                            <td className="py-3 px-4 text-right font-mono font-black text-slate-900">
                              {item.hasPeriodTraffic ? `${(item.views / 10000).toFixed(1)}w` : '—'}
                            </td>

                            <td className="py-3 px-4 text-right font-mono font-bold text-indigo-600">
                              {item.hasPeriodTraffic ? `${item.follows >= 0 ? '+' : ''}${item.follows.toLocaleString()}` : '—'}
                            </td>

                            <td className="py-3 px-4 text-right font-mono font-extrabold text-purple-600">
                              {item.hasPeriodRevenue && item.hasPeriodTraffic && item.views > 0 ? `¥${item.rpm}` : '—'}
                            </td>

                            <td className="py-3 px-4 text-center font-mono font-medium">
                              {item.hasWorkData ? item.videoCount : '—'}
                            </td>

                            <td className="py-3 px-4 text-center">
                              <span className={`px-2 py-0.5 rounded-md font-mono font-bold text-[10px] ${
                                getOptimizationHealth(item.optimizationRate)==='critical'
                                  ? 'bg-red-100 text-red-700'
                                  : getOptimizationHealth(item.optimizationRate)==='warning'
                                  ? 'bg-amber-100 text-amber-700'
                                  : 'bg-emerald-100 text-emerald-700'
                              }`}>
                                {formatOptimizationRate(item.optimizationRate)} ({item.optimizedCount}条)
                              </span>
                            </td>

                            <td className="py-3 px-4 text-center">
                              <button
                                onClick={(e) => {
                                  e.stopPropagation();
                                  setActiveAccount(item.account);
                                }}
                                className="px-2 py-1 rounded-md border border-slate-200 text-indigo-600 hover:bg-indigo-50 font-semibold text-[11px]"
                              >
                                档案
                              </button>
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              </div>
            </div>

            {/* 4. 平台优化诊断原因分布预览 */}
            <div className="bg-white rounded-2xl p-6 border border-slate-200/80 shadow-xs">
              <div className="flex items-center justify-between mb-4">
                <div className="flex items-center gap-2">
                  <span className="p-2 bg-rose-50 text-rose-600 rounded-xl">
                    <ShieldAlert className="w-4 h-4" />
                  </span>
                  <div>
                    <h3 className="text-sm font-bold text-slate-800">作品分析标签分布</h3>
                    <p className="text-[11px] text-slate-400">按作品分析标签归类，未识别的保留待归类</p>
                  </div>
                </div>

                <button
                  onClick={() => setActiveTab('accountOptimization')}
                  className="text-xs font-semibold text-rose-600 hover:text-rose-700 flex items-center gap-1 cursor-pointer"
                >
                  <span>进入账号优化</span>
                  <ChevronRight className="w-4 h-4" />
                </button>
              </div>

              <OptimizationReasonBarChart 
                reasons={reasonDistribution}
                onSelectReason={(r) => {
                  setSelectedReasonFilter(prev => prev === r ? null : (r as SimplifiedOptimizationReason));
                  setActiveTab('accountOptimization');
                }}
                selectedReason={selectedReasonFilter}
              />
            </div>
          </div>
        )}

        {/* ========================================================= */}
        {/* TAB 2: 矩阵账号运营概览 (每个卡片必须显示流量数据) */}
        {/* ========================================================= */}
        {activeTab === 'matrix' && (
          <div className="space-y-6">
            {/* 顶部统计卡片 */}
            <div className="bg-white rounded-2xl p-6 border border-slate-200/80 shadow-xs flex flex-wrap items-center justify-between gap-4">
              <div>
                <h3 className="text-lg font-bold text-slate-900">矩阵账号运营概览 ({matrixAccounts.length}个账号)</h3>
                <p className="text-xs text-slate-500 mt-1">
                周期创收与播放量、昨日四项数据、历史总创收及优化率
                </p>
              </div>
              <div role="group" aria-label="账号矩阵排序" className="order-3 flex w-full flex-wrap items-center gap-1.5 xl:order-none xl:w-auto">
                {MATRIX_SORT_OPTIONS.map(option => {
                  const active = matrixSort.key === option.key;
                  return <button key={option.key} type="button" aria-pressed={active}
                    aria-label={`${option.label}${active ? matrixSort.order === 'desc' ? '，从高到低' : '，从低到高' : ''}`}
                    title={active ? '再次点击反转顺序，缺失数据始终在最后' : `按${option.label}排序`}
                    onClick={() => setMatrixSort(current => ({ key: option.key,
                      order: current.key === option.key ? current.order === 'desc' ? 'asc' : 'desc' : defaultMatrixSortOrder(option.key) }))}
                    className={`inline-flex items-center gap-1 whitespace-nowrap rounded-lg border px-2.5 py-1.5 text-xs font-semibold transition-colors ${active ? 'border-indigo-200 bg-indigo-50 text-indigo-700' : 'border-transparent text-slate-500 hover:bg-slate-50 hover:text-slate-800'}`}>
                    {option.label}<span aria-hidden="true" className={active ? 'text-indigo-500' : 'text-slate-300'}>{active ? matrixSort.order === 'desc' ? '↓' : '↑' : '↕'}</span>
                  </button>;
                })}
              </div>
              <div className="ml-auto flex flex-wrap items-center gap-2">
                <span className="text-xs text-slate-400">剧场数: <strong className="text-slate-800 font-mono">{enabledTheaterCount}</strong> 个</span>
                <span className="text-slate-200">•</span>
                <span className="text-xs text-slate-400">可用账号数: <strong className="text-slate-800 font-mono">{availableAccountCount}</strong> 个</span>
              </div>
            </div>

            {/* 账号卡片网格 (34个账号，完整包含流量与收益) */}
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
              {matrixAccounts.map(item => {
                return (
                  <div
                    key={item.account.id}
                    data-matrix-account={item.account.id}
                    onClick={() => setActiveAccount(item.account)}
                    className="bg-white rounded-2xl p-5 border border-slate-200/80 hover:border-indigo-400 hover:shadow-md transition-all cursor-pointer flex flex-col justify-between"
                  >
                    <div>
                      {/* 顶部标签 */}
                      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
                        <span className="text-[11px] font-bold px-2 py-0.5 rounded-md bg-indigo-50 text-indigo-700 border border-indigo-100">
                          {item.account.theaterName}
                        </span>
                        <AccountRatingBadge account={item.account} size="md" />
                      </div>

                      {/* 账号主体 */}
                      <div className="flex items-center gap-3 mb-3">
                        <span className="relative inline-flex h-10 w-10 flex-none">
                          <AccountAvatar name={item.account.name} url={item.account.avatarUrl} className="w-10 h-10" />
                          <AccountLoginBadge account={item.account} />
                        </span>
                        <div className="min-w-0">
                          <div className="flex flex-wrap items-center gap-1.5"><h4 className="max-w-full truncate font-extrabold text-sm text-slate-900">
                            {item.account.name}
                          </h4><BusinessAccountStatusBadge status={item.account.businessStatus} /></div>
                          <AccountProfileTotals account={item.account} />
                        </div>
                      </div>

                    </div>

                    {/* 流量数据矩阵 (核心要求：每个卡片必须显示流量数据) */}
                    <div className="pt-3 border-t border-slate-100 space-y-2.5">
                      {/* 收益与播放量 */}
                      <div className="grid grid-cols-2 gap-2 text-xs font-mono">
                        <div className="p-2 bg-emerald-50/60 rounded-xl border border-emerald-100">
                          <span className="text-[10px] text-emerald-700 font-sans block">创收金额</span>
                          <span className="font-black text-emerald-700 text-sm">{item.hasPeriodRevenue ? `¥${item.revenue.toLocaleString()}` : item.monthlyRevenue !== null ? '仅月累计' : '—'}</span>
                        </div>
                        <div className="p-2 bg-indigo-50/60 rounded-xl border border-indigo-100">
                          <span className="text-[10px] text-indigo-700 font-sans block">区间播放</span>
                          <span className="font-black text-indigo-700 text-sm">{item.hasPeriodTraffic ? `${(item.views / 10000).toFixed(1)}w` : '—'}</span>
                        </div>
                      </div>

                      <AccountYesterdayMetrics data={item.dailySummary} />

                      {/* 历史累计收益不跟随周期筛选，优化率仍按所选区间 */}
                      <div className="flex flex-wrap items-center justify-between gap-x-2 gap-y-2 pt-1 text-[10px]">
                        <span data-account-historical-revenue className="whitespace-nowrap text-slate-500">
                          历史总创收 <strong className="ml-1 font-mono text-[11px] font-semibold tabular-nums text-slate-700">{item.account.rating?.recordedTotal == null ? '—' : `¥${item.account.rating.recordedTotal.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`}</strong>
                        </span>
                        <span className={`px-2 py-0.5 rounded font-mono font-bold text-[10px] ${
                          getOptimizationHealth(item.optimizationRate)==='critical'
                            ? 'bg-rose-100 text-rose-700'
                            : getOptimizationHealth(item.optimizationRate)==='warning'
                            ? 'bg-amber-100 text-amber-700'
                            : 'bg-emerald-100 text-emerald-700'
                        }`}>
                          优化率: {formatOptimizationRate(item.optimizationRate)} ({item.optimizedCount}条)
                        </span>
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        )}

        {/* ========================================================= */}
        {/* TAB 3: 账号发视频优化分析 (以账号为单位核算优化情况) */}
        {/* ========================================================= */}
        {activeTab === 'accountOptimization' && (
          <AccountOptimizationView 
            onSettingsSaved={onRefresh}
            optimizationStats={accountOptimizationStats}
            allVideos={accountOptimizationVideos}
            theaters={ENABLED_THEATERS}
            accounts={ACCOUNTS}
            reasonFilter={selectedReasonFilter}
            onReasonFilterChange={setSelectedReasonFilter}
            dateRange={dateRange}
            onDateRangeChange={(r) => setDateRange(r)}
            onOpenVideoDrawer={(v) => setActiveVideo(v)}
            onOpenAccountDrawer={(a) => setActiveAccount(a)}
          />
        )}

        {/* ========================================================= */}
        {/* TAB 4: 视频流量明细库 (重点以账号发布的视频为核心) */}
        {/* ========================================================= */}
        {activeTab === 'videos' && (
          <div className="space-y-4">
            {/* 顶部控制与账号筛选栏 */}
            <div ref={videoListStart} className="scroll-mt-48 bg-white rounded-2xl p-5 border border-slate-200/80 shadow-xs space-y-4">
              <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 pb-3 border-b border-slate-100">
                <div>
                  <h3 className="text-base font-bold text-slate-900">
                  账号发布视频流量明细 ({tagFilteredVideos.length} 条)
                  </h3>
                  <p className="text-xs text-slate-500 mt-0.5">
                    文件名严格统一规范为「剧名-n」，按账号聚合追踪发布时分、播放量、完播率与平台优化标识
                  </p>
                </div>

                {/* 视图模式切换 */}
                <div className="flex items-center gap-2">
                  <div className="inline-flex p-0.5 bg-slate-100 rounded-lg text-xs">
                    <button
                      onClick={() => setVideoViewMode('card')}
                      className={`px-3 py-1 rounded-md font-medium transition-all ${
                        videoViewMode === 'card' ? 'bg-white font-bold text-indigo-600 shadow-xs' : 'text-slate-600'
                      }`}
                    >
                      卡片视图
                    </button>
                    <button
                      onClick={() => setVideoViewMode('grouped')}
                      className={`px-3 py-1 rounded-md font-medium transition-all ${
                        videoViewMode === 'grouped' ? 'bg-white font-bold text-indigo-600 shadow-xs' : 'text-slate-600'
                      }`}
                    >
                      表格视图
                    </button>
                  </div>
                </div>
              </div>

              {/* 排序与控制 */}
              <div role="group" aria-label="视频排序与标签" className="flex flex-wrap items-center justify-between gap-x-4 gap-y-3 text-xs">
                <div role="group" aria-label="视频排序" className="flex w-max max-w-full flex-none flex-wrap items-center gap-3">
                  <span className="text-slate-400 font-medium">排序维度:</span>
                  <div className="inline-flex p-0.5 bg-slate-100 rounded-lg">
                    <button
                      onClick={() => setVideoSortBy('views')}
                      className={`px-2.5 py-1 rounded-md font-medium cursor-pointer ${
                        videoSortBy === 'views' ? 'bg-white text-indigo-600 font-bold shadow-xs' : 'text-slate-600'
                      }`}
                    >
                      播放量
                    </button>
                    <button
                      onClick={() => setVideoSortBy('completionRate')}
                      className={`px-2.5 py-1 rounded-md font-medium cursor-pointer ${
                        videoSortBy === 'completionRate' ? 'bg-white text-indigo-600 font-bold shadow-xs' : 'text-slate-600'
                      }`}
                    >
                      完播率
                    </button>
                    <button
                      onClick={() => setVideoSortBy('publishTime')}
                      className={`px-2.5 py-1 rounded-md font-medium cursor-pointer ${
                        videoSortBy === 'publishTime' ? 'bg-white text-indigo-600 font-bold shadow-xs' : 'text-slate-600'
                      }`}
                    >
                      发布时间
                    </button>
                    <button
                      onClick={() => setVideoSortBy('hearts')}
                      className={`px-2.5 py-1 rounded-md font-medium cursor-pointer ${
                        videoSortBy === 'hearts' ? 'bg-white text-indigo-600 font-bold shadow-xs' : 'text-slate-600'
                      }`}
                    >
                      爱心数
                    </button>
                  </div>

                  <button
                    onClick={() => setSortOrder(o => o === 'desc' ? 'asc' : 'desc')}
                    className="p-1.5 rounded-lg border border-slate-200 bg-white text-slate-600 hover:bg-slate-50 text-xs font-medium flex items-center gap-1 cursor-pointer"
                  >
                    <ArrowUpDown className="w-3.5 h-3.5" />
                    <span>{sortOrder === 'desc' ? '从高到低' : '从低到高'}</span>
                  </button>
                </div>

                <VideoTrafficFilter value={selectedVideoTag} onChange={setSelectedVideoTag} counts={videoTagStats.counts} total={currentVideos.length} />
              </div>
              <div className="border-t border-slate-100 pt-3">{renderVideoPagination('top')}</div>
            </div>

            {/* Both view modes share the tag filter and empty result. */}
            {tagFilteredVideos.length===0?(
              <div className="rounded-2xl border border-slate-200/80 bg-white px-6 py-14 text-center">
                <p className="text-sm font-semibold text-slate-700">暂无符合当前条件的视频</p>
                <p className="mt-1 text-xs text-slate-400">可调整日期、账号、搜索或视频标签后查看</p>
                {selectedVideoTag!=='ALL'&&<button type="button" onClick={()=>setSelectedVideoTag('ALL')} className="mt-4 rounded-lg bg-indigo-50 px-4 py-2 text-xs font-semibold text-indigo-600 hover:bg-indigo-100">查看全部标签</button>}
              </div>
            ):videoViewMode === 'card' ? (
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                {pagedVideos.map(v => {

                  return (
                    <div
                      key={v.id}
                      onClick={() => setActiveVideo(v)}
                      className="bg-white rounded-2xl p-5 border border-slate-200/80 hover:border-indigo-400 hover:shadow-md transition-all cursor-pointer flex flex-col justify-between"
                    >
                      <div className="flex items-start gap-3">
                        <WorkVideoCover key={`${v.accountId}:${v.id}`} video={v} size="lg" />
                        <div className="min-w-0 flex-1">
                          <div className="mb-2 flex flex-wrap items-center justify-between gap-x-2 gap-y-1.5">
                            <span className="shrink-0 text-[11px] font-bold text-indigo-700 bg-indigo-50 border border-indigo-100 px-2 py-0.5 rounded">{v.theater}</span>
                            <VideoTrafficTags video={v}/>
                          </div>
                          <h4 className="text-base font-extrabold text-slate-900 font-mono tracking-tight">{v.fileName}</h4>
                          <div className="mt-1.5 flex flex-wrap items-center gap-x-2 gap-y-1 text-[11px] text-slate-500">
                            <span className="inline-flex max-w-full items-center gap-1.5"><AccountAvatar name={v.accountName} url={v.avatarUrl} className="w-5 h-5"/><span className="truncate font-bold text-slate-700">{v.accountName}</span></span>
                            <span className="whitespace-nowrap font-mono text-[10px] text-slate-400">{v.publishTime}</span>
                          </div>
                        </div>
                      </div>

                      {/* 流量数据网格 */}
                      <div className="mt-4 pt-3 border-t border-slate-100">
                        <div data-video-card-metrics className="grid grid-cols-6 gap-1.5 text-center font-mono">
                          {[
                            { label: '播放', value: v.views >= 100_000 ? interactionCount(v.views) : `${(v.views / 10000).toFixed(1)}w`, full: v.views.toLocaleString('zh-CN'), color: 'text-slate-900' },
                            { label: '完播率', value: `${v.completionRate}%`, full: `${v.completionRate}%`, color: v.completionRate >= 22 ? 'text-emerald-600' : 'text-slate-800' },
                            { label: '爱心', value: interactionCount(v.hearts), full: v.hearts.toLocaleString('zh-CN'), color: 'text-slate-800' },
                            { label: '评论', value: interactionCount(v.comments), full: v.comments.toLocaleString('zh-CN'), color: 'text-slate-800' },
                            { label: '转发', value: interactionCount(v.shares), full: v.shares.toLocaleString('zh-CN'), color: 'text-slate-800' },
                            { label: '点赞', value: interactionCount(v.thumbsUp), full: v.thumbsUp.toLocaleString('zh-CN'), color: 'text-slate-800' },
                          ].map(metric => <div key={metric.label} className="min-w-0 whitespace-nowrap" title={`${metric.label}：${metric.full}`}>
                            <div className={`text-xs font-black lg:text-[11px] xl:text-xs ${metric.color}`}>{metric.value}</div>
                            <div className="text-[10px] text-slate-400 font-sans">{metric.label}</div>
                          </div>)}
                        </div>
                      </div>
                    </div>
                  );
                })}
              </div>
            ) : (
              /* 表格模式 */
              <div className="bg-white rounded-2xl border border-slate-200/80 shadow-xs overflow-hidden">
                <div data-video-table-scroll role="region" aria-label="视频明细表格，可横向滚动" tabIndex={0} className="overflow-x-auto overscroll-x-contain">
                  <table className="w-full min-w-[1200px] whitespace-nowrap text-left text-xs [&_td]:px-3 [&_th]:px-3">
                    <thead>
                      <tr className="bg-slate-50 text-slate-500 font-semibold border-b border-slate-200">
                        <th className="py-3 px-4">视频文件名 (剧名-n)</th>
                        <th className="py-3 px-4">所属账号</th>
                        <th className="py-3 px-4">剧场</th>
                        <th className="py-3 px-4">发布时间</th>
                        <th className="py-3 px-4 text-right">播放量</th>
                        <th className="py-3 px-4 text-right">完播率</th>
                        <th className="py-3 px-4 text-right">爱心</th>
                        <th className="py-3 px-4 text-right">评论</th>
                        <th className="py-3 px-4 text-right">转发</th>
                        <th className="py-3 px-4 text-right">点赞</th>
                        <th className="py-3 px-4 text-center">视频标签</th>
                        <th className="py-3 px-4 text-center">操作</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-100 text-slate-700">
                      {pagedVideos.map(v => (
                        <tr
                          key={v.id}
                          onClick={() => setActiveVideo(v)}
                          className="hover:bg-slate-50 transition-colors cursor-pointer"
                        >
                          <td className="w-[232px] max-w-[232px] py-3 px-4 font-mono font-bold text-slate-900">
                            <span className="block max-w-[200px] truncate" title={v.fileName}>{v.fileName}</span>
                          </td>
                          <td className="py-3 px-4 font-medium text-slate-800">
                            {v.accountName}
                          </td>
                          <td className="py-3 px-4">
                            <span className="inline-flex w-max whitespace-nowrap px-2 py-0.5 rounded bg-indigo-50 text-indigo-700 font-medium">
                              {v.theater}
                            </span>
                          </td>
                          <td className="py-3 px-4 font-mono text-slate-500">
                            <span className="block">{v.publishTime.slice(0, 10)}</span>
                            <span className="mt-0.5 block text-[11px] text-slate-400">{v.publishTime.slice(11)}</span>
                          </td>
                          <td className="py-3 px-4 text-right font-mono font-bold text-slate-900">
                            {v.views.toLocaleString()}
                          </td>
                          <td className="py-3 px-4 text-right font-mono font-bold text-slate-800">
                            {v.completionRate}%
                          </td>
                          <td className="py-3 px-4 text-right font-mono text-slate-700">
                            {v.hearts.toLocaleString()}
                          </td>
                          <td className="py-3 px-4 text-right font-mono text-slate-700">
                            {v.comments.toLocaleString()}
                          </td>
                          <td className="py-3 px-4 text-right font-mono text-slate-700">
                            {v.shares.toLocaleString()}
                          </td>
                          <td className="py-3 px-4 text-right font-mono text-slate-700">
                            {v.thumbsUp.toLocaleString()}
                          </td>
                          <td className="py-3 px-4 text-center">
                            <VideoTrafficTags video={v} stacked/>
                          </td>
                          <td className="py-3 px-4 text-center">
                            <button
                              onClick={(e) => {
                                e.stopPropagation();
                                setActiveVideo(v);
                              }}
                              className="text-indigo-600 hover:text-indigo-800 font-semibold"
                            >
                              详情
                            </button>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            )}
            {tagFilteredVideos.length>0&&<div className="rounded-xl border border-slate-200/80 bg-white p-3.5">{renderVideoPagination('bottom')}</div>}
          </div>
        )}

        {/* ========================================================= */}
        {/* TAB 5: 数据透视与导出 */}
        {/* ========================================================= */}
        {activeTab === 'pivot' && (
          <DataPivotView 
            revenueList={currentRevenueList}
            trafficList={filterTrafficDetails(selectedTheater, selectedAccountId, dateRange)}
            videoList={currentVideos}
            showToast={showToast}
          />
        )}
      </main>

      {/* 账号综合档案抽屉 */}
      <AccountDetailDrawer 
        account={ACCOUNTS.find(a => a.id === activeAccount?.id) || null}
        onUpdateData={() => {if (activeAccount) {setCollectionAccountIds([activeAccount.id]); setCollectionOpen(true);}}}
        dateRange={dateRange}
        onClose={() => setActiveAccount(null)}
        onSelectVideo={(v) => setActiveVideo(v)}
      />

      {/* 视频切片详情抽屉 */}
      <VideoDetailDrawer 
        video={activeVideo}
        onClose={() => setActiveVideo(null)}
        showToast={showToast}
      />
      <DataCollectionModal isOpen={collectionOpen} onClose={() => setCollectionOpen(false)} accounts={allAccounts} theaters={model.THEATERS} defaultSelectedTheater={selectedTheater} defaultSelectedAccountId={collectionAccountIds.length === 1 ? collectionAccountIds[0] : 'ALL'} initialAccountIds={collectionAccountIds} onDataSaved={onRefresh} onJobStateChange={setCollectionSummary} showToast={showToast} />
    </div>
  );
};
