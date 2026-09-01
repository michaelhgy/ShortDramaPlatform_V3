import React, { useState, useMemo, useEffect } from 'react';
import { 
  TimeRangeFilter, 
  TheaterFilter,
  AnalyticsTopTab
} from '../../analyticsTypes';
import { 
  calculateAccountsAnalytics, 
  CalculatedAccountItem 
} from '../../utils/accountEngine';
import { AccountTrendChart } from './AccountTrendChart';
import { 
  Users, 
  Search, 
  MapPin, 
  Tv2, 
  PlusCircle,
  HelpCircle,
  TrendingUp,
  AlertCircle,
  Sparkles,
  Info,
  ChevronRight
} from 'lucide-react';
import { StatusBadge } from './common/StatusBadge';
import { HelpTooltip, ModuleInfoPopover } from './common/HelpTooltip';

interface AccountModuleProps {
  timeRange: TimeRangeFilter;
  selectedTheater: TheaterFilter;
  customStartDate?: string;
  customEndDate?: string;
  initialAccountId?: string;
  onNavigateToTab?: (tab: AnalyticsTopTab, entityId?: string) => void;
  onScheduleToday?: (dramaId?: string, accountId?: string) => void;
  accounts?: CalculatedAccountItem[];
}

export const AccountModule: React.FC<AccountModuleProps> = ({
  timeRange,
  selectedTheater,
  customStartDate,
  customEndDate,
  initialAccountId,
  onNavigateToTab,
  onScheduleToday,
  accounts: realAccounts,
}) => {
  // 1. Dynamic calculation based on global filters (timeRange & selectedTheater)
  const { accounts: calculatedAccounts, theaterFilterName } = useMemo(() => {
    if (realAccounts) return { accounts: realAccounts, theaterFilterName: selectedTheater === 'all' ? '全部剧场' : '青柠剧场' };
    return calculateAccountsAnalytics(timeRange, selectedTheater, customStartDate, customEndDate);
  }, [timeRange, selectedTheater, customStartDate, customEndDate, realAccounts]);

  const [selectedAccountId, setSelectedAccountId] = useState<string>(
    initialAccountId || calculatedAccounts[0]?.id || 'acc-1'
  );
  const [searchQuery, setSearchQuery] = useState('');
  const [sortBy, setSortBy] = useState<'revenue_desc' | 'views_desc' | 'name'>('revenue_desc');

  // Respond if initialAccountId changes from drill-down
  useEffect(() => {
    if (initialAccountId && calculatedAccounts.some((a) => a.id === initialAccountId)) {
      setSelectedAccountId(initialAccountId);
    }
  }, [initialAccountId, calculatedAccounts]);

  // Auto-switch selected account if current selected account is filtered out by theater
  useEffect(() => {
    const isSelectedInList = calculatedAccounts.some((a) => a.id === selectedAccountId);
    if (!isSelectedInList && calculatedAccounts.length > 0) {
      setSelectedAccountId(calculatedAccounts[0].id);
    }
  }, [calculatedAccounts, selectedAccountId]);

  // 2. Filter & Sort accounts
  const filteredAccounts = useMemo(() => {
    return calculatedAccounts
      .filter((acc) => {
        const query = searchQuery.toLowerCase().trim();
        if (!query) return true;
        return (
          acc.name.toLowerCase().includes(query) ||
          acc.recentMainDrama.toLowerCase().includes(query) ||
          acc.defaultLocation.fullAddress.toLowerCase().includes(query) ||
          acc.theater.toLowerCase().includes(query)
        );
      })
      .sort((a, b) => {
        if (sortBy === 'revenue_desc') {
          return b.periodRevenue - a.periodRevenue;
        }
        if (sortBy === 'views_desc') {
          return (b.periodVideoViews || 0) - (a.periodVideoViews || 0);
        }
        return a.name.localeCompare(b.name, 'zh-CN');
      });
  }, [calculatedAccounts, searchQuery, sortBy]);

  const selectedAccount: CalculatedAccountItem | undefined =
    calculatedAccounts.find((a) => a.id === selectedAccountId) || filteredAccounts[0];

  // Dynamic labels based on timeRange
  const periodRevenueLabel = useMemo(() => {
    switch (timeRange) {
      case 'yesterday': return '昨日收益';
      case '7days': return '近7日收益';
      case '14days': return '近14日收益';
      case '30days': return '近30日收益';
      case 'this_month': return '本月收益';
      case 'custom': return '周期收益';
      default: return '周期收益';
    }
  }, [timeRange]);

  const sortRevenueOptionLabel = useMemo(() => {
    switch (timeRange) {
      case 'yesterday': return '昨日收益降序';
      case '7days': return '7日收益降序';
      case '14days': return '14日收益降序';
      case '30days': return '30日收益降序';
      case 'this_month': return '本月收益降序';
      case 'custom': return '周期收益降序';
      default: return '周期收益降序';
    }
  }, [timeRange]);

  const summaryRevenueCardTitle = useMemo(() => {
    switch (timeRange) {
      case 'yesterday': return '昨日结算收益';
      case '7days': return '近7日累计收益';
      case '14days': return '近14日累计收益';
      case '30days': return '近30日累计收益';
      case 'this_month': return '本月累计收益';
      case 'custom': return '周期累计收益';
      default: return '当前周期收益';
    }
  }, [timeRange]);

  const summaryAverageCardTitle = useMemo(() => {
    return timeRange === 'yesterday' ? '近期参考日均 (近7日)' : '周期日均收益';
  }, [timeRange]);

  const summaryViewsCardTitle = useMemo(() => {
    switch (timeRange) {
      case 'yesterday': return '昨日视频播放量';
      case '7days': return '近7日视频播放量';
      case '14days': return '近14日视频播放量';
      case '30days': return '近30日视频播放量';
      case 'this_month': return '本月视频播放量';
      case 'custom': return '周期视频播放量';
      default: return '周期视频播放量';
    }
  }, [timeRange]);

  const dramaSectionTitle = useMemo(() => {
    switch (timeRange) {
      case 'yesterday': return '昨日剧集表现';
      case '7days': return '近7日剧集表现';
      case '14days': return '近14日剧集表现';
      case '30days': return '近30日剧集表现';
      case 'this_month': return '本月剧集表现';
      case 'custom': return '周期内剧集表现';
      default: return '剧集表现';
    }
  }, [timeRange]);

  return (
    <div className="grid grid-cols-1 lg:grid-cols-12 gap-4 items-start">
      {/* LEFT COLUMN: Account Navigation List & Quick Search (4 cols) */}
      <div className="lg:col-span-4 bg-white rounded-2xl p-4 border border-black/[0.06] shadow-xs space-y-3">
        {/* Header & Scope info */}
        <div className="flex items-center justify-between">
          <div>
            <h3 className="text-sm font-bold text-[#1A1D2E] flex items-center gap-2">
              <span>账号列表</span>
              <span className="text-xs px-2 py-0.5 rounded-full bg-slate-100 font-mono text-[#64748B]">
                {filteredAccounts.length} / {calculatedAccounts.length}
              </span>
            </h3>
            <p className="text-[11px] text-[#64748B] mt-0.5">
              {theaterFilterName} · {periodRevenueLabel}
            </p>
          </div>
        </div>

        {/* Search & Sort Controls */}
        <div className="space-y-2">
          <div className="relative">
            <Search className="w-3.5 h-3.5 absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
            <input
              type="text"
              placeholder="搜索账号 / 主推剧 / 发布地址..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="w-full pl-8 pr-3 py-1.5 bg-slate-50 border border-black/[0.06] rounded-xl text-xs placeholder:text-slate-400 focus:bg-white focus:outline-hidden focus:border-[#1A1D2E] transition-all"
            />
          </div>

          <div className="flex items-center justify-between text-xs text-[#64748B] px-1">
            <span>排序方式:</span>
            <select
              value={sortBy}
              onChange={(e) => setSortBy(e.target.value as any)}
              className="bg-slate-50 border border-black/[0.06] rounded-lg px-2 py-1 text-xs text-[#1A1D2E] font-medium cursor-pointer"
            >
              <option value="revenue_desc">{sortRevenueOptionLabel}</option>
              <option value="views_desc">播放量降序 (青柠)</option>
              <option value="name">按账号名称排序</option>
            </select>
          </div>
        </div>

        {/* Account Master List */}
        <div className="space-y-1.5 max-h-[640px] overflow-y-auto pr-1">
          {filteredAccounts.map((acc) => {
            const isSelected = acc.id === selectedAccountId;
            return (
              <div
                key={acc.id}
                onClick={() => setSelectedAccountId(acc.id)}
                className={`p-3 rounded-xl cursor-pointer transition-all border text-left ${
                  isSelected
                    ? 'bg-[#1A1D2E] text-white border-[#1A1D2E] shadow-sm'
                    : 'bg-slate-50/70 text-[#1A1D2E] hover:bg-slate-100/90 border-black/[0.04]'
                }`}
              >
                <div className="flex items-center justify-between gap-1">
                  <div className="flex items-center gap-1.5 min-w-0">
                    <span className="font-semibold text-xs truncate">
                      {acc.name}
                    </span>
                    <span
                      className={`text-[10px] px-1.5 py-0.2 rounded-md shrink-0 font-medium ${
                        isSelected
                          ? 'bg-white/10 text-slate-200'
                          : 'bg-black/[0.04] text-[#64748B]'
                      }`}
                    >
                      {acc.theater}
                    </span>
                  </div>

                  {/* Revenue in Period */}
                  <div className="text-right shrink-0">
                    <span
                      className={`font-mono text-xs font-bold ${
                        isSelected ? 'text-[#DDFD00]' : 'text-[#1A1D2E]'
                      }`}
                    >
                      ¥{acc.periodRevenue.toLocaleString('zh-CN', { minimumFractionDigits: 2 })}
                    </span>
                  </div>
                </div>

                {/* Sub-info: Recent Main Drama & Location Preview */}
                <div
                  className={`flex items-center justify-between text-[11px] mt-1.5 ${
                    isSelected ? 'text-slate-300' : 'text-[#64748B]'
                  }`}
                >
                  <div className="flex items-center gap-1 truncate max-w-[170px]">
                    <Tv2 className="w-3 h-3 shrink-0 opacity-70" />
                    <span className="truncate">{acc.recentMainDrama}</span>
                  </div>

                  {acc.hasQingningVideoData && acc.periodVideoViews !== undefined ? (
                    <div className="font-mono text-[10px] shrink-0">
                      {(acc.periodVideoViews / 10000).toFixed(1)}万播放
                    </div>
                  ) : (
                    <div className="text-[10px] shrink-0 opacity-60">
                      {acc.locationPerformances.length} 个地址
                    </div>
                  )}
                </div>
              </div>
            );
          })}

          {filteredAccounts.length === 0 && (
            <div className="p-8 text-center text-xs text-slate-400 space-y-1">
              <Users className="w-6 h-6 mx-auto opacity-40 text-slate-400 mb-2" />
              <div>未找到匹配账号</div>
              <div className="text-[11px] text-slate-400">请尝试清除搜索词或切换剧场筛选</div>
            </div>
          )}
        </div>
      </div>

      {/* RIGHT COLUMN: Account Detail Multi-Dimensional View (8 cols) */}
      {selectedAccount ? (
        <div className="lg:col-span-8 space-y-4">
          {/* 1. Account Profile Header & Key Period Metrics */}
          <div className="bg-white rounded-2xl p-5 border border-black/[0.06] shadow-xs space-y-4">
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div>
                <div className="flex items-center gap-2">
                  <h2 className="text-base font-bold text-[#1A1D2E]">
                    {selectedAccount.name}
                  </h2>
                  <span className="text-xs px-2 py-0.5 rounded-md bg-slate-100 font-medium text-[#64748B]">
                    {selectedAccount.theater}
                  </span>
                  
                  {selectedAccount.hasQingningVideoData ? (
                    <StatusBadge variant="direct" text="具备视频播放数据" />
                  ) : selectedAccount.theaterKey === 'huasheng' ? (
                    <StatusBadge variant="estimated" text="按规则推测收益" />
                  ) : (
                    <span className="text-xs px-2 py-0.5 rounded-md bg-slate-100 text-slate-700 font-medium border border-slate-200">
                      直接收益采集
                    </span>
                  )}
                </div>
                
                {/* Default Virtual Location Card (Full address + Usage count) */}
                <div className="flex flex-wrap items-center gap-2 text-xs text-[#64748B] mt-2">
                  <div className="flex items-center gap-1">
                    <MapPin className="w-3.5 h-3.5 text-rose-500 shrink-0" />
                    <span className="font-semibold text-[#1A1D2E]">当前默认发布地址:</span>
                    <span className="text-[#1A1D2E]">{selectedAccount.defaultLocation.fullAddress}</span>
                  </div>
                  <div className="flex items-center gap-1">
                    <span className="text-[10px] px-1.5 py-0.2 rounded-md bg-slate-100 text-slate-500 font-mono">
                      已沿用 {selectedAccount.defaultLocation.usedCount} 次
                    </span>
                    <StatusBadge variant="historical" text="历史累计" tooltip="该账号默认定位的使用次数基于历史全量发布统计" />
                  </div>
                </div>
              </div>

              {/* Action Button: 安排今日排期 */}
              {onScheduleToday && (
                <button
                  onClick={() => onScheduleToday(selectedAccount.dramaPerformancesInPeriod[0]?.dramaId, selectedAccount.id)}
                  className="flex items-center gap-1.5 px-3.5 py-1.5 rounded-xl bg-[#1A1D2E] text-[#DDFD00] text-xs font-semibold hover:bg-black/90 active:scale-[0.98] transition-all shadow-xs cursor-pointer"
                >
                  <PlusCircle className="w-3.5 h-3.5" />
                  <span>安排今日排期</span>
                </button>
              )}
            </div>

            {/* Account Quick Metrics Trio (Strictly 3 positions, responsive to timeRange) */}
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 pt-2 border-t border-black/[0.04]">
              {/* Position 1: 当前周期收益 */}
              <div className="p-3 rounded-xl bg-slate-50 border border-black/[0.04] space-y-1">
                <div className="text-[11px] font-medium text-[#64748B]">
                  {summaryRevenueCardTitle}
                </div>
                <div className="font-mono text-xl font-black text-[#1A1D2E]">
                  ¥{selectedAccount.periodRevenue.toLocaleString('zh-CN', { minimumFractionDigits: 2 })}
                </div>
                <div className="text-[10px] text-slate-500 truncate">
                  {timeRange === 'yesterday' ? '已核对真实入账收益' : '周期累计结算收益'}
                </div>
              </div>

              {/* Position 2: 当前周期日均收益 (或昨日参考均值) */}
              <div className="p-3 rounded-xl bg-slate-50 border border-black/[0.04] space-y-1">
                <div className="text-[11px] font-medium text-[#64748B]">
                  {summaryAverageCardTitle}
                </div>
                <div className="font-mono text-xl font-black text-[#1A1D2E]">
                  {timeRange === 'yesterday' ? (
                    selectedAccount.recent7DayAvgRevenue > 0 ? (
                      `¥${selectedAccount.recent7DayAvgRevenue.toLocaleString('zh-CN', { minimumFractionDigits: 2 })}`
                    ) : (
                      <span className="text-slate-400 text-sm font-normal">数据不足</span>
                    )
                  ) : (
                    `¥${selectedAccount.dailyAverageRevenue.toLocaleString('zh-CN', { minimumFractionDigits: 2 })}`
                  )}
                </div>
                <div className="text-[10px] text-slate-500 truncate">
                  {timeRange === 'yesterday' ? (
                    selectedAccount.changeVsRecentAvgPct !== null ? (
                      <span className={selectedAccount.changeVsRecentAvgPct >= 0 ? 'text-emerald-600 font-medium' : 'text-rose-600 font-medium'}>
                        较近期日均 {selectedAccount.changeVsRecentAvgPct >= 0 ? '+' : ''}{selectedAccount.changeVsRecentAvgPct}%
                      </span>
                    ) : '基准参考 08-17 ~ 08-23'
                  ) : (
                    `按周期实际天数平摊`
                  )}
                </div>
              </div>

              {/* Position 3: 当前周期视频播放 (Qingning vs Non-Qingning graceful fallback) */}
              <div className="p-3 rounded-xl bg-slate-50 border border-black/[0.04] space-y-1">
                <div className="text-[11px] font-medium text-[#64748B]">
                  {summaryViewsCardTitle}
                </div>
                <div className="font-mono text-xl font-black text-[#1A1D2E]">
                  {selectedAccount.hasQingningVideoData && selectedAccount.periodVideoViews !== undefined ? (
                    `${(selectedAccount.periodVideoViews / 10000).toFixed(1)} 万次`
                  ) : (
                    '—'
                  )}
                </div>
                <div className="text-[10px] text-slate-500 truncate">
                  {selectedAccount.hasQingningVideoData ? '视频号生态推广播放' : '当前数据源未提供'}
                </div>
              </div>
            </div>
          </div>

          {/* 2. Account Revenue Trend Visualizer (High-contrast real daily line + MA7 trendline) */}
          <div className="bg-white rounded-2xl p-5 border border-black/[0.06] shadow-xs">
            <AccountTrendChart
              trendPoints={selectedAccount.dailyTrendPoints}
              timeRange={timeRange}
              accountName={selectedAccount.name}
              hasVideoViews={selectedAccount.hasQingningVideoData}
            />
          </div>

          {/* 3. 剧集表现 (Drama Performances in Period) */}
          <div className="bg-white rounded-2xl p-5 border border-black/[0.06] shadow-xs space-y-3">
            <div className="flex items-center justify-between">
              <div>
                <h3 className="text-xs font-bold text-[#1A1D2E] flex items-center gap-1.5">
                  <span>{dramaSectionTitle}</span>
                  <span className="text-[10px] px-1.5 py-0.2 rounded-md bg-slate-100 font-normal text-[#64748B]">
                    {periodRevenueLabel}统计
                  </span>
                </h3>
                <p className="text-[11px] text-[#64748B] mt-0.5">
                  该账号在所选周期内各剧目的登记发布数、收益与播放表现
                </p>
              </div>
            </div>

            <div className="overflow-x-auto">
              <table className="w-full text-left text-xs border-collapse">
                <thead>
                  <tr className="border-b border-black/[0.06] text-[#64748B] font-medium">
                    <th className="py-2.5 px-2">剧集名称</th>
                    <th className="py-2.5 px-2 text-center">
                      <div className="inline-flex items-center gap-1">
                        <span>发布视频数</span>
                        <HelpTooltip text="所选周期内，该账号针对该剧登记发布的平台推广视频数量。" />
                      </div>
                    </th>
                    <th className="py-2.5 px-2 text-right">总收益</th>
                    <th className="py-2.5 px-2 text-right">
                      <div className="inline-flex items-center gap-1 justify-end">
                        <span>平均单条收益</span>
                        <HelpTooltip text="当前账号针对该剧的总收益 ÷ 发布视频数，受少数极值影响，仅供参考。" />
                      </div>
                    </th>
                    <th className="py-2.5 px-2 text-right">视频播放</th>
                    <th className="py-2.5 px-2 text-right">剧集播放</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-black/[0.04]">
                  {selectedAccount.dramaPerformancesInPeriod.map((dp) => (
                    <tr key={dp.dramaId} className="hover:bg-slate-50/70 transition-colors">
                      <td className="py-2.5 px-2 font-semibold text-[#1A1D2E]">
                        {onNavigateToTab ? (
                          <button
                            type="button"
                            onClick={() => onNavigateToTab('dramas', dp.dramaId)}
                            className="text-left font-semibold text-[#1A1D2E] hover:text-indigo-600 transition-colors flex items-center gap-1 group"
                          >
                            <span>{dp.dramaName}</span>
                            <ChevronRight className="w-3 h-3 text-slate-400 group-hover:text-indigo-600 transition-colors" />
                          </button>
                        ) : (
                          dp.dramaName
                        )}
                      </td>
                      <td className="py-2.5 px-2 text-center font-mono font-medium">
                        {dp.publishCount} 条
                      </td>
                      <td className="py-2.5 px-2 text-right font-mono font-bold text-[#1A1D2E]">
                        {dp.isAttributable && dp.totalRevenue !== undefined
                          ? `¥${dp.totalRevenue.toFixed(2)}`
                          : '—'}
                      </td>
                      <td className="py-2.5 px-2 text-right font-mono text-[#64748B]">
                        {dp.isAttributable && dp.avgRevenuePerVideo !== undefined
                          ? `¥${dp.avgRevenuePerVideo.toFixed(1)}`
                          : '—'}
                      </td>
                      <td className="py-2.5 px-2 text-right font-mono text-[#64748B]">
                        {dp.videoViews !== undefined ? `${(dp.videoViews / 10000).toFixed(1)}万` : '—'}
                      </td>
                      <td className="py-2.5 px-2 text-right font-mono text-[#64748B]">
                        {dp.dramaViews !== undefined ? `${(dp.dramaViews / 10000).toFixed(1)}万` : '—'}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>

          {/* 4. 发布地址历史表现（历史累计） */}
          <div className="bg-white rounded-2xl p-5 border border-black/[0.06] shadow-xs space-y-3">
            <div className="flex items-center justify-between">
              <div>
                <h3 className="text-xs font-bold text-[#1A1D2E] flex items-center gap-2">
                  <span>发布地址历史表现</span>
                  <StatusBadge 
                    variant="historical" 
                    text="历史累计" 
                    tooltip="按该账号发布登记时实际记录的发布地址快照聚合，展示全历史真实数据（不随顶部周期变动）"
                  />
                </h3>
                <p className="text-[11px] text-[#64748B] mt-0.5">
                  仅统计已人工核对关联的平台视频，按该账号发布登记时实际记录的地址聚合。
                </p>
              </div>
            </div>

            <div className="overflow-x-auto">
              <table className="w-full text-left text-xs border-collapse">
                <thead>
                  <tr className="border-b border-black/[0.06] text-[#64748B] font-medium">
                    <th className="py-2.5 px-2">省市区 + 详细地址</th>
                    <th className="py-2.5 px-2 text-center">使用次数</th>
                    <th className="py-2.5 px-2 text-right">总收益</th>
                    <th className="py-2.5 px-2 text-right">视频播放</th>
                    <th className="py-2.5 px-2 text-right">剧集播放</th>
                    <th className="py-2.5 px-2 text-center">最后使用</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-black/[0.04]">
                  {selectedAccount.locationPerformances.map((lp) => (
                    <tr key={lp.locationId} className="hover:bg-slate-50/70 transition-colors">
                      <td className="py-2.5 px-2 font-medium text-[#1A1D2E] max-w-[280px]">
                        <div className="flex items-center gap-1 truncate" title={lp.fullAddress}>
                          <MapPin className="w-3.5 h-3.5 text-slate-400 shrink-0" />
                          <span className="truncate">{lp.fullAddress}</span>
                        </div>
                      </td>
                      <td className="py-2.5 px-2 text-center font-mono font-medium">
                        {lp.usedCount} 次
                      </td>
                      <td className="py-2.5 px-2 text-right font-mono font-bold text-[#1A1D2E]">
                        ¥{lp.totalRevenue.toFixed(2)}
                      </td>
                      <td className="py-2.5 px-2 text-right font-mono text-[#64748B]">
                        {lp.videoViews !== undefined ? `${(lp.videoViews / 10000).toFixed(1)}万` : '—'}
                      </td>
                      <td className="py-2.5 px-2 text-right font-mono text-[#64748B]">
                        {lp.dramaViews !== undefined ? `${(lp.dramaViews / 10000).toFixed(1)}万` : '—'}
                      </td>
                      <td className="py-2.5 px-2 text-center font-mono text-[11px] text-slate-500">
                        {lp.lastUsedDate}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      ) : (
        <div className="lg:col-span-8 bg-white rounded-2xl p-12 border border-black/[0.06] shadow-xs flex flex-col items-center justify-center text-center space-y-3">
          <AlertCircle className="w-10 h-10 text-slate-300" />
          <h3 className="text-sm font-bold text-[#1A1D2E]">未选中账号</h3>
          <p className="text-xs text-slate-400">请在左侧列表中选择一个账号以查看完整多维数据</p>
        </div>
      )}
    </div>
  );
};
