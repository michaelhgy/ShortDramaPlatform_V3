import React, { useState, useMemo, useEffect } from 'react';
import { 
  TimeRangeFilter, 
  TheaterFilter,
  AnalyticsTopTab
} from '../../analyticsTypes';
import { 
  calculateDramasAnalytics, 
  CalculatedDramaItem 
} from '../../utils/dramaEngine';
import { 
  Tv2, 
  Search, 
  Users, 
  MapPin, 
  PlusCircle, 
  Award, 
  HelpCircle, 
  CheckCircle2, 
  Clock, 
  AlertCircle,
  Building2,
  Sparkles,
  Info,
  ChevronRight,
  ExternalLink
} from 'lucide-react';
import { StatusBadge } from './common/StatusBadge';
import { HelpTooltip, ModuleInfoPopover } from './common/HelpTooltip';

interface DramaModuleProps {
  timeRange: TimeRangeFilter;
  selectedTheater: TheaterFilter;
  customStartDate?: string;
  customEndDate?: string;
  initialDramaId?: string;
  onNavigateToTab?: (tab: AnalyticsTopTab, entityId?: string) => void;
  onSelectVideoAndOpenDrawer?: (videoId: string) => void;
  onScheduleToday?: (dramaId?: string, accountId?: string) => void;
}

export const DramaModule: React.FC<DramaModuleProps> = ({
  timeRange,
  selectedTheater,
  customStartDate,
  customEndDate,
  initialDramaId,
  onNavigateToTab,
  onSelectVideoAndOpenDrawer,
  onScheduleToday,
}) => {
  // 1. Calculate dynamic drama analytics according to Global Filter (timeRange + selectedTheater)
  const calculatedDramas = useMemo(() => {
    return calculateDramasAnalytics(timeRange, selectedTheater, customStartDate, customEndDate);
  }, [timeRange, selectedTheater, customStartDate, customEndDate]);

  const [selectedDramaId, setSelectedDramaId] = useState<string>(
    initialDramaId || calculatedDramas[0]?.id || 'd-1'
  );
  const [searchQuery, setSearchQuery] = useState('');
  const [sortBy, setSortBy] = useState<'revenue_desc' | 'accounts_desc' | 'name'>('revenue_desc');
  const [hoveredVideoDetail, setHoveredVideoDetail] = useState<boolean>(false);

  // Respond if initialDramaId changes from drill-down
  useEffect(() => {
    if (initialDramaId && calculatedDramas.some((d) => d.id === initialDramaId)) {
      setSelectedDramaId(initialDramaId);
    }
  }, [initialDramaId, calculatedDramas]);

  // Auto-switch selected drama if current selected drama is filtered out by theater
  useEffect(() => {
    if (calculatedDramas.length > 0) {
      const exists = calculatedDramas.some((d) => d.id === selectedDramaId);
      if (!exists) {
        setSelectedDramaId(calculatedDramas[0].id);
      }
    }
  }, [calculatedDramas, selectedDramaId]);

  // 2. Filter & Sort dramas (Strictly by drama name, NO genre/category)
  const filteredDramas = useMemo(() => {
    return calculatedDramas
      .filter((d) => {
        const query = searchQuery.trim().toLowerCase();
        if (!query) return true;
        return d.name.toLowerCase().includes(query);
      })
      .sort((a, b) => {
        if (sortBy === 'revenue_desc') return b.periodRevenue - a.periodRevenue;
        if (sortBy === 'accounts_desc') return b.periodAccountsCount - a.periodAccountsCount;
        return a.name.localeCompare(b.name, 'zh-CN');
      });
  }, [calculatedDramas, searchQuery, sortBy]);

  const selectedDrama: CalculatedDramaItem | undefined = 
    filteredDramas.find((d) => d.id === selectedDramaId) || filteredDramas[0];

  // Dynamic Text Helpers according to Global Filter
  const periodLabel = useMemo(() => {
    switch (timeRange) {
      case 'yesterday': return '昨日';
      case '7days': return '近7日';
      case '30days': return '近30日';
      case 'this_month': return '本月';
      case 'custom': return '周期';
      default: return '周期';
    }
  }, [timeRange]);

  const revenueLabel = useMemo(() => {
    switch (timeRange) {
      case 'yesterday': return '昨日收益';
      case '7days': return '近7日收益';
      case '30days': return '近30日收益';
      case 'this_month': return '本月收益';
      case 'custom': return '周期收益';
      default: return '收益';
    }
  }, [timeRange]);

  const sortRevenueLabel = useMemo(() => {
    switch (timeRange) {
      case 'yesterday': return '昨日收益降序';
      case '7days': return '7日收益降序';
      case '30days': return '30日收益降序';
      case 'this_month': return '本月收益降序';
      case 'custom': return '周期收益降序';
      default: return '收益降序';
    }
  }, [timeRange]);

  const handleBestVideoClick = () => {
    if (!selectedDrama || !selectedDrama.videoVariance.bestVideoDisplay.videoId) return;
    const vId = selectedDrama.videoVariance.bestVideoDisplay.videoId;
    if (vId === '—') return;
    if (onSelectVideoAndOpenDrawer) {
      onSelectVideoAndOpenDrawer(vId);
    } else if (onNavigateToTab) {
      onNavigateToTab('videos', vId);
    }
  };

  return (
    <div className="grid grid-cols-1 lg:grid-cols-12 gap-4 items-start">
      {/* LEFT 4 COLS: 剧集列表 */}
      <div className="lg:col-span-4 bg-white rounded-2xl p-4 border border-black/[0.06] shadow-xs flex flex-col h-[780px]">
        {/* Header & Search */}
        <div className="space-y-2.5 pb-3 border-b border-black/[0.04] shrink-0">
          <div className="flex items-center justify-between">
            <h3 className="text-sm font-bold text-[#1A1D2E] flex items-center gap-2">
              <Tv2 className="w-4 h-4 text-emerald-600" />
              <span>剧集收益榜</span>
              <span className="text-xs font-mono font-semibold px-2 py-0.5 rounded-full bg-slate-100 text-[#64748B]">
                {filteredDramas.length}
              </span>
            </h3>

            {/* Quick Sort */}
            <select
              value={sortBy}
              onChange={(e) => setSortBy(e.target.value as any)}
              className="text-[11px] bg-slate-50 border border-black/[0.06] rounded-lg px-2 py-1 text-[#1A1D2E] font-medium outline-none cursor-pointer"
            >
              <option value="revenue_desc">{sortRevenueLabel}</option>
              <option value="accounts_desc">发布账号数</option>
              <option value="name">剧名排序</option>
            </select>
          </div>

          {/* Search Input */}
          <div className="relative">
            <Search className="w-3.5 h-3.5 absolute left-3 top-1/2 -translate-y-1/2 text-[#64748B]" />
            <input
              type="text"
              placeholder="搜索剧集名称..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="w-full pl-8 pr-3 py-1.5 bg-slate-50 border border-black/[0.06] rounded-xl text-xs text-[#1A1D2E] placeholder:text-slate-400 outline-none focus:border-black/30 transition-all"
            />
          </div>
        </div>

        {/* Scrollable Drama Cards */}
        <div className="flex-1 overflow-y-auto space-y-2 pt-3 pr-1">
          {filteredDramas.length === 0 ? (
            <div className="h-48 flex flex-col items-center justify-center text-center p-4 text-[#64748B]">
              <AlertCircle className="w-8 h-8 text-slate-300 mb-2" />
              <p className="text-xs font-semibold text-[#1A1D2E]">未找到符合条件的剧集</p>
              <p className="text-[11px] text-[#64748B] mt-1">
                {selectedTheater !== 'all' ? `当前剧场下暂无匹配结果` : '请尝试调整剧名搜索词'}
              </p>
            </div>
          ) : (
            filteredDramas.map((drama) => {
              const isSelected = drama.id === selectedDrama?.id;
              return (
                <div
                  key={drama.id}
                  onClick={() => setSelectedDramaId(drama.id)}
                  className={`p-3 rounded-xl border transition-all cursor-pointer space-y-2 ${
                    isSelected
                      ? 'bg-[#1A1D2E] text-white border-[#1A1D2E] shadow-sm'
                      : 'bg-slate-50/70 border-black/[0.04] hover:bg-white hover:border-black/[0.1] text-[#1A1D2E]'
                  }`}
                >
                  {/* Top Row: Drama Name & Period Revenue */}
                  <div className="flex items-start justify-between gap-2">
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-1.5 flex-wrap">
                        <span className="font-bold text-xs truncate max-w-[200px]" title={drama.name}>
                          {drama.name}
                        </span>
                        <span className={`text-[9px] px-1.5 py-0.2 rounded-md font-medium ${
                          isSelected ? 'bg-white/20 text-[#DDFD00]' : 'bg-slate-200/80 text-[#1A1D2E]'
                        }`}>
                          {drama.theaterName}
                        </span>
                      </div>
                      <div className={`text-[11px] flex items-center gap-2 mt-0.5 ${
                        isSelected ? 'text-slate-300' : 'text-[#64748B]'
                      }`}>
                        <span className="flex items-center gap-1">
                          <Users className="w-3 h-3" />
                          {drama.periodAccountsCount} 个账号承接
                        </span>
                      </div>
                    </div>

                    <div className="text-right shrink-0">
                      <div className={`font-mono font-bold text-xs ${
                        isSelected ? 'text-[#DDFD00]' : 'text-emerald-700'
                      }`}>
                        {drama.isAttributable 
                          ? `¥${drama.periodRevenue.toFixed(1)}`
                          : '—'}
                      </div>
                      <div className={`text-[10px] ${isSelected ? 'text-slate-400' : 'text-slate-400'}`}>
                        {revenueLabel}
                      </div>
                    </div>
                  </div>

                  {/* Bottom Row */}
                  <div className="flex items-center justify-between pt-1 border-t border-black/[0.04] text-[10px]">
                    {drama.hasQingningVideoData && drama.periodVideoViews ? (
                      <span className={`font-mono ${isSelected ? 'text-emerald-300' : 'text-emerald-700 font-medium'}`}>
                        青柠播放: {(drama.periodVideoViews / 10000).toFixed(1)} 万次
                      </span>
                    ) : (
                      <span className={isSelected ? 'text-slate-400' : 'text-slate-400'}>
                        {drama.isAttributable ? '多账号推广收益' : '非确切归因剧场'}
                      </span>
                    )}

                    <span className={`font-mono ${isSelected ? 'text-slate-300' : 'text-[#64748B]'}`}>
                      {drama.isAttributable ? `历史 ¥${drama.historicalTotalRevenue.toFixed(0)}` : '历史未单列'}
                    </span>
                  </div>
                </div>
              );
            })
          )}
        </div>
      </div>

      {/* RIGHT 8 COLS: 剧集详情 */}
      {selectedDrama ? (
        <div className="lg:col-span-8 space-y-4">
          {/* 1. Drama Header Banner */}
          <div className="bg-white rounded-2xl p-5 border border-black/[0.06] shadow-xs space-y-3">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div>
                <div className="flex items-center gap-2 flex-wrap">
                  <h2 className="text-base font-black text-[#1A1D2E]">
                    {selectedDrama.name}
                  </h2>
                  <span className="text-xs px-2 py-0.5 rounded-md bg-slate-100 text-[#1A1D2E] font-semibold border border-black/[0.04]">
                    {selectedDrama.theaterName}
                  </span>
                  {selectedDrama.hasQingningVideoData && (
                    <StatusBadge variant="direct" text="青柠视频级数据" />
                  )}
                </div>

                {/* Historical Background Banner (Strictly Labeled as 历史累计) */}
                <div className="text-xs text-[#64748B] mt-2 flex flex-wrap items-center gap-2">
                  <div className="flex items-center gap-1">
                    <span className="font-semibold text-[#1A1D2E]">历史累计：</span>
                    <span>{selectedDrama.historicalTotalAccounts} 个账号发布</span>
                    <span>·</span>
                    <span>
                      可归因收益 {selectedDrama.isAttributable 
                        ? `¥${selectedDrama.historicalTotalRevenue.toLocaleString('zh-CN', { minimumFractionDigits: 2 })}` 
                        : '—'}
                    </span>
                  </div>
                  <StatusBadge 
                    variant="historical" 
                    text="历史累计" 
                    tooltip="展示该剧自上线以来的全量历史数据，不受顶部时间筛选影响" 
                  />
                </div>
              </div>

              {/* Action Button: 以此剧安排排期 */}
              {onScheduleToday && (
                <button
                  onClick={() => onScheduleToday(selectedDrama.id)}
                  className="flex items-center gap-1.5 px-3.5 py-1.5 rounded-xl bg-[#1A1D2E] text-[#DDFD00] text-xs font-semibold hover:bg-black/90 active:scale-[0.98] transition-all shadow-xs"
                >
                  <PlusCircle className="w-3.5 h-3.5" />
                  <span>以此剧安排排期</span>
                </button>
              )}
            </div>

            {/* Quick Metrics: Current Period Data */}
            <div className="grid grid-cols-3 gap-3 pt-2 border-t border-black/[0.04]">
              {/* Metric 1: 当前周期可归因收益 */}
              <div className="p-2.5 rounded-xl bg-slate-50 border border-black/[0.04]">
                <div className="text-[11px] text-[#64748B] flex items-center justify-between">
                  <span>{periodLabel}可归因收益</span>
                  <HelpTooltip text="当前周期内平台明细中明确归属于该剧的收益总和。" />
                </div>
                <div className="font-mono text-base font-black text-[#1A1D2E] mt-0.5">
                  {selectedDrama.isAttributable 
                    ? `¥${selectedDrama.periodRevenue.toLocaleString('zh-CN', { minimumFractionDigits: 2 })}`
                    : '—'}
                </div>
                <div className="text-[10px] text-[#64748B] mt-0.5 truncate">
                  {selectedDrama.isAttributable ? '周期内各账号确切归因收益' : '当前剧场暂无单剧确切归因'}
                </div>
              </div>

              {/* Metric 2: 当前周期发布账号数 */}
              <div className="p-2.5 rounded-xl bg-slate-50 border border-black/[0.04]">
                <div className="text-[11px] text-[#64748B] flex items-center justify-between">
                  <span>{periodLabel}发布账号</span>
                  <HelpTooltip text="所选周期内实际登记发布该剧的去重账号数量。" />
                </div>
                <div className="font-mono text-base font-black text-[#1A1D2E] mt-0.5">
                  {selectedDrama.periodAccountsCount} 个
                </div>
                <div className="text-[10px] text-[#64748B] mt-0.5 truncate">
                  周期内实际登记发布去重账号
                </div>
              </div>

              {/* Metric 3: 当前周期视频播放 */}
              <div className="p-2.5 rounded-xl bg-slate-50 border border-black/[0.04]">
                <div className="text-[11px] text-[#64748B] flex items-center justify-between">
                  <span>{periodLabel}视频播放</span>
                  <HelpTooltip text="所选周期内该剧推广视频产生的总播放量（仅青柠支持）。" />
                </div>
                <div className="font-mono text-base font-black text-[#1A1D2E] mt-0.5">
                  {selectedDrama.hasQingningVideoData && selectedDrama.periodVideoViews
                    ? `${(selectedDrama.periodVideoViews / 10000).toFixed(1)} 万次`
                    : '—'}
                </div>
                <div className="text-[10px] text-[#64748B] mt-0.5 truncate">
                  {selectedDrama.hasQingningVideoData ? '推广视频总播放量' : '当前剧场未提供视频级数据'}
                </div>
              </div>
            </div>
          </div>

          {/* 2. 平台视频表现差异 */}
          <div className="bg-white rounded-2xl p-5 border border-black/[0.06] shadow-xs space-y-3">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <div className="flex items-center gap-2">
                <h3 className="text-xs font-bold text-[#1A1D2E] flex items-center gap-1.5">
                  <Award className="w-4 h-4 text-amber-500" />
                  <span>平台视频表现差异</span>
                </h3>
                <ModuleInfoPopover
                  title="平台视频表现差异说明"
                  content={
                    <>
                      <p>比较该剧在所选周期内各平台推广视频的收益表现（按平台视频ID聚合统计）。</p>
                      <p>• <strong>最佳单条收益</strong>：当前周期收益最高的平台视频。</p>
                      <p>• <strong>平均单条收益</strong>：总收益 ÷ 观测视频数，易受爆款拉高。</p>
                      <p>• <strong>中位单条收益</strong>：视频收益中位数，更能代表典型视频表现。</p>
                      <p>• <strong>0收益视频</strong>：明确为0收益的视频数，反映转化漏斗。</p>
                    </>
                  }
                />
              </div>

              <div className="text-[11px] text-slate-400">
                统计样本：{selectedDrama.videoVariance.publishedVideoCount} 条平台视频
              </div>
            </div>

            {/* 4 Statistical Metrics Cards */}
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
              {/* Card 1: 最佳单条收益 */}
              <div 
                onClick={handleBestVideoClick}
                className="p-3 rounded-xl bg-emerald-50/70 border border-emerald-200/60 relative cursor-pointer hover:bg-emerald-100/60 transition-colors group"
                title="点击可直接下钻至视频分析并查看该视频详情"
              >
                <div className="text-[11px] text-emerald-800 font-medium flex items-center justify-between">
                  <span>最佳单条收益</span>
                  <ExternalLink className="w-3 h-3 text-emerald-600 opacity-0 group-hover:opacity-100 transition-opacity" />
                </div>
                <div className="font-mono text-base font-black text-emerald-900 mt-0.5">
                  {selectedDrama.videoVariance.publishedVideoCount > 0 
                    ? `¥${selectedDrama.videoVariance.bestSingleVideoRevenue.toFixed(2)}`
                    : '—'}
                </div>

                {/* Best Video Display with Status */}
                <div className="text-[10px] text-emerald-800/90 mt-1 flex items-center gap-1 truncate">
                  <span className="truncate font-medium max-w-[100px]" title={selectedDrama.videoVariance.bestVideoDisplay.displayName}>
                    {selectedDrama.videoVariance.bestVideoDisplay.displayName}
                  </span>
                  {selectedDrama.videoVariance.bestVideoDisplay.isLinked ? (
                    <StatusBadge variant="linked" text="已关联" />
                  ) : (
                    <StatusBadge variant="unlinked" text="未关联" />
                  )}
                </div>
              </div>

              {/* Card 2: 平均单条收益 */}
              <div className="p-3 rounded-xl bg-slate-50 border border-black/[0.04]">
                <div className="text-[11px] text-[#64748B] font-medium flex items-center justify-between">
                  <span>平均单条收益</span>
                  <HelpTooltip text="当前周期该剧可归因总收益 ÷ 发布视频数。易受少数爆款拉高。" />
                </div>
                <div className="font-mono text-base font-black text-[#1A1D2E] mt-0.5">
                  {selectedDrama.videoVariance.publishedVideoCount > 0 
                    ? `¥${selectedDrama.videoVariance.avgSingleVideoRevenue.toFixed(2)}`
                    : '—'}
                </div>
                <div className="text-[10px] text-slate-500 mt-1 truncate">
                  {selectedDrama.videoVariance.publishedVideoCount} 条平台视频均值
                </div>
              </div>

              {/* Card 3: 中位单条收益 */}
              <div className="p-3 rounded-xl bg-slate-50 border border-black/[0.04]">
                <div className="text-[11px] text-[#64748B] font-medium flex items-center justify-between">
                  <span>中位单条收益</span>
                  <HelpTooltip text="当前周期该剧所有平台视频收益的中位数，更能代表典型视频表现。" />
                </div>
                <div className="font-mono text-base font-black text-[#1A1D2E] mt-0.5">
                  {selectedDrama.videoVariance.publishedVideoCount > 0 
                    ? `¥${selectedDrama.videoVariance.medianSingleVideoRevenue.toFixed(2)}`
                    : '—'}
                </div>
                <div className="text-[10px] text-slate-500 mt-1 truncate">
                  消除爆款极值后的基准
                </div>
              </div>

              {/* Card 4: 0收益视频 */}
              <div className="p-3 rounded-xl bg-amber-50/70 border border-amber-200/60">
                <div className="text-[11px] text-amber-800 font-medium flex items-center justify-between">
                  <span>0收益视频</span>
                  <HelpTooltip text="当前周期收益为 0 的视频数量与占比，属于有效数据统计。" />
                </div>
                <div className="font-mono text-base font-black text-amber-900 mt-0.5">
                  {selectedDrama.videoVariance.publishedVideoCount > 0 
                    ? `${selectedDrama.videoVariance.zeroRevenueCount} / ${selectedDrama.videoVariance.publishedVideoCount}`
                    : '—'}
                </div>
                <div className="text-[10px] text-amber-700/80 mt-1 truncate">
                  客观统计周期内无转化数
                </div>
              </div>
            </div>
          </div>

          {/* 3. 不同账号表现 */}
          <div className="bg-white rounded-2xl p-5 border border-black/[0.06] shadow-xs space-y-3">
            <div>
              <h3 className="text-xs font-bold text-[#1A1D2E]">
                不同账号表现差异
              </h3>
              <p className="text-[11px] text-[#64748B]">
                同一部剧在不同账号的承接效果存在显著分化（当前口径：{periodLabel}）
              </p>
            </div>

            <div className="overflow-x-auto">
              <table className="w-full text-left text-xs border-collapse">
                <thead>
                  <tr className="border-b border-black/[0.06] text-[#64748B] font-medium">
                    <th className="py-2.5 px-2">账号名称</th>
                    <th className="py-2.5 px-2 text-center">发布视频数</th>
                    <th className="py-2.5 px-2 text-right">总收益</th>
                    <th className="py-2.5 px-2 text-right">
                      <div className="inline-flex items-center gap-1 justify-end">
                        <span>平均单条收益</span>
                        <HelpTooltip text="该账号发布此剧的总收益 ÷ 发布视频数" />
                      </div>
                    </th>
                    <th className="py-2.5 px-2 text-right">视频播放</th>
                    <th className="py-2.5 px-2 text-right">剧集播放</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-black/[0.04]">
                  {selectedDrama.accountDifferences.length === 0 ? (
                    <tr>
                      <td colSpan={6} className="py-6 text-center text-slate-400 text-xs">
                        {periodLabel}暂无已登记发布数据
                      </td>
                    </tr>
                  ) : (
                    selectedDrama.accountDifferences.map((ad) => (
                      <tr key={ad.accountId} className="hover:bg-slate-50/70 transition-colors">
                        <td className="py-2.5 px-2 font-semibold text-[#1A1D2E]">
                          {onNavigateToTab ? (
                            <button
                              type="button"
                              onClick={() => onNavigateToTab('accounts', ad.accountId)}
                              className="text-left font-semibold text-[#1A1D2E] hover:text-indigo-600 transition-colors flex items-center gap-1 group"
                            >
                              <span>{ad.accountName}</span>
                              <ChevronRight className="w-3 h-3 text-slate-400 group-hover:text-indigo-600 transition-colors" />
                            </button>
                          ) : (
                            ad.accountName
                          )}
                        </td>
                        <td className="py-2.5 px-2 text-center font-mono font-medium">
                          {ad.publishCount} 条
                        </td>
                        <td className="py-2.5 px-2 text-right font-mono font-bold text-[#1A1D2E]">
                          ¥{ad.totalRevenue.toFixed(2)}
                        </td>
                        <td className="py-2.5 px-2 text-right font-mono font-medium text-emerald-700">
                          ¥{ad.avgRevenuePerVideo.toFixed(1)}
                        </td>
                        <td className="py-2.5 px-2 text-right font-mono text-[#64748B]">
                          {ad.videoViews !== undefined ? `${(ad.videoViews / 10000).toFixed(1)}万` : '—'}
                        </td>
                        <td className="py-2.5 px-2 text-right font-mono text-[#64748B]">
                          {ad.dramaViews !== undefined ? `${(ad.dramaViews / 10000).toFixed(1)}万` : '—'}
                        </td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>
            {!selectedDrama.hasQingningVideoData && (
              <div className="text-[10px] text-slate-400 pt-1 border-t border-black/[0.04]">
                * 说明：当前剧场未提供视频级播放数据，对应字段显示为「—」。
              </div>
            )}
          </div>

          {/* 4. 虚拟定位历史表现 · 历史累计 */}
          <div className="bg-white rounded-2xl p-5 border border-black/[0.06] shadow-xs space-y-3">
            <div className="flex items-center justify-between">
              <div>
                <h3 className="text-xs font-bold text-[#1A1D2E] flex items-center gap-2">
                  <span>虚拟定位历史表现</span>
                  <StatusBadge 
                    variant="historical" 
                    text="历史累计" 
                    tooltip="按实际登记发布该剧时所采用的虚拟地址快照聚合，展示全历史真实数据（不随顶部周期变动）" 
                  />
                </h3>
                <p className="text-[11px] text-[#64748B] mt-0.5">
                  按实际登记发布该剧时所采用的虚拟地址快照聚合，展示全历史真实数据（不随顶部周期变动）
                </p>
              </div>
            </div>

            <div className="overflow-x-auto">
              <table className="w-full text-left text-xs border-collapse">
                <thead>
                  <tr className="border-b border-black/[0.06] text-[#64748B] font-medium">
                    <th className="py-2.5 px-2">虚拟定位地址</th>
                    <th className="py-2.5 px-2 text-center">发布次数</th>
                    <th className="py-2.5 px-2 text-right">总收益</th>
                    <th className="py-2.5 px-2 text-right">视频播放</th>
                    <th className="py-2.5 px-2 text-right">剧集播放</th>
                    <th className="py-2.5 px-2 text-right">最后使用</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-black/[0.04]">
                  {selectedDrama.locationPerformances.map((lp) => (
                    <tr key={lp.locationId} className="hover:bg-slate-50/70 transition-colors">
                      <td className="py-2.5 px-2 font-medium text-[#1A1D2E] max-w-[260px]">
                        <div className="flex items-center gap-1.5 truncate" title={lp.fullAddress}>
                          <MapPin className="w-3.5 h-3.5 text-slate-400 shrink-0" />
                          <span className="truncate">{lp.fullAddress}</span>
                        </div>
                      </td>
                      <td className="py-2.5 px-2 text-center font-mono font-medium">
                        {lp.usedCount} 次
                      </td>
                      <td className="py-2.5 px-2 text-right font-mono font-bold text-[#1A1D2E]">
                        {lp.totalRevenue > 0 ? `¥${lp.totalRevenue.toFixed(2)}` : '—'}
                      </td>
                      <td className="py-2.5 px-2 text-right font-mono text-[#64748B]">
                        {lp.videoViews !== undefined ? `${(lp.videoViews / 10000).toFixed(1)}万` : '—'}
                      </td>
                      <td className="py-2.5 px-2 text-right font-mono text-[#64748B]">
                        {lp.dramaViews !== undefined ? `${(lp.dramaViews / 10000).toFixed(1)}万` : '—'}
                      </td>
                      <td className="py-2.5 px-2 text-right font-mono text-[#64748B] whitespace-nowrap">
                        {lp.lastUsedDate}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      ) : null}
    </div>
  );
};
