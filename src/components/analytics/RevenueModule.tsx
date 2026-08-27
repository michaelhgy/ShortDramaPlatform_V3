import React, { useState } from 'react';
import { 
  RevenueSummaryMetrics, 
  DailyRevenueDataPoint, 
  TrendGhostPoint,
  ContributionItem, 
  ChangeSignalItem, 
  TimeRangeFilter,
  TheaterFilter,
  DramaAttributionSummary,
  AnalyticsTopTab
} from '../../analyticsTypes';
import { 
  TrendingUp, 
  TrendingDown, 
  ArrowUpRight, 
  ArrowDownRight, 
  Layers, 
  Users, 
  Tv2, 
  AlertCircle, 
  Sparkles,
  Calendar,
  CheckCircle2,
  Info,
  ExternalLink,
  ChevronRight
} from 'lucide-react';
import { AdvancedRevenueTrendChart } from './AdvancedRevenueTrendChart';
import { StatusBadge } from './common/StatusBadge';
import { HelpTooltip, ModuleInfoPopover } from './common/HelpTooltip';

interface RevenueModuleProps {
  summary: RevenueSummaryMetrics;
  trendPoints: DailyRevenueDataPoint[];
  ghostPoints?: TrendGhostPoint[];
  hasGhostData: boolean;
  ghostUnavailableReason?: string;
  theaterContributions: ContributionItem[];
  accountContributions: ContributionItem[];
  dramaContributions: ContributionItem[];
  dramaAttributionSummary: DramaAttributionSummary;
  changeSignals: ChangeSignalItem[];
  timeRange: TimeRangeFilter;
  selectedTheater: TheaterFilter;
  onNavigateToTab?: (tab: AnalyticsTopTab, entityId?: string) => void;
  onOpenCollectionDrawer?: () => void;
}

export const RevenueModule: React.FC<RevenueModuleProps> = ({
  summary,
  trendPoints,
  ghostPoints = [],
  hasGhostData,
  ghostUnavailableReason,
  theaterContributions,
  accountContributions,
  dramaContributions,
  dramaAttributionSummary,
  changeSignals,
  timeRange,
  selectedTheater,
  onNavigateToTab,
  onOpenCollectionDrawer,
}) => {
  const [contributionTab, setContributionTab] = useState<'theaters' | 'accounts' | 'dramas'>('theaters');

  const activeContributions = contributionTab === 'theaters' 
    ? theaterContributions 
    : contributionTab === 'accounts' 
    ? accountContributions 
    : dramaContributions;

  // Handle Jump from Signal
  const handleSignalClick = (signal: ChangeSignalItem) => {
    if (signal.targetType === 'account' && onNavigateToTab) {
      onNavigateToTab('accounts', signal.targetId);
    } else if (signal.targetType === 'drama' && onNavigateToTab) {
      onNavigateToTab('dramas', signal.targetId);
    } else if (signal.targetType === 'collection' && onOpenCollectionDrawer) {
      onOpenCollectionDrawer();
    }
  };

  // Handle table row click for navigation
  const handleRowClick = (item: ContributionItem) => {
    if (!onNavigateToTab) return;
    if (contributionTab === 'accounts') {
      onNavigateToTab('accounts', item.id);
    } else if (contributionTab === 'dramas') {
      onNavigateToTab('dramas', item.id);
    }
  };

  return (
    <div className="space-y-4">
      {/* 1. DYNAMIC SUMMARY CARDS (Adaptive to Yesterday vs. Multi-day periods) */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 bg-white p-3.5 rounded-2xl border border-black/[0.06] shadow-xs">
        {summary.isYesterday ? (
          // YESTERDAY MODE (昨日专属摘要)
          <>
            {/* Card 1: 昨日收益 */}
            <div className="p-3 rounded-xl bg-slate-50/90 border border-black/[0.04] space-y-1">
              <div className="text-[11px] font-medium text-[#64748B] flex items-center justify-between">
                <span>昨日结算收益</span>
                <span className="w-1.5 h-1.5 rounded-full bg-emerald-500" />
              </div>
              <div className="flex items-baseline gap-1">
                <span className="font-mono text-2xl font-black text-[#1A1D2E]">
                  ¥{summary.yesterdayRevenue.toLocaleString('zh-CN', { minimumFractionDigits: 2 })}
                </span>
              </div>
              <div className="text-[10px] text-slate-500">
                已核对真实入账收益
              </div>
            </div>

            {/* Card 2: 近7日参考均值 */}
            <div className="p-3 rounded-xl bg-slate-50/90 border border-black/[0.04] space-y-1">
              <div className="text-[11px] font-medium text-[#64748B] flex items-center justify-between">
                <span>近期参考日均 (近7日)</span>
                <HelpTooltip text="近7日每日结算收益的算术平均值，作为昨日表现的基准线。" />
              </div>
              <div className="flex items-baseline gap-1">
                <span className="font-mono text-2xl font-black text-[#1A1D2E]">
                  ¥{summary.recentAverageRevenue.toLocaleString('zh-CN', { minimumFractionDigits: 2 })}
                </span>
              </div>
              <div className="text-[10px] text-slate-500">
                基准参考区间 08-17 ~ 08-23
              </div>
            </div>

            {/* Card 3: 较近期均值 */}
            <div className="p-3 rounded-xl bg-slate-50/90 border border-black/[0.04] space-y-1">
              <div className="text-[11px] font-medium text-[#64748B]">较近期参考均值</div>
              <div className="flex items-baseline gap-1.5">
                {summary.changeVsAveragePct !== null ? (
                  <span className={`font-mono text-2xl font-black flex items-center gap-0.5 ${
                    summary.changeVsAveragePct >= 0 ? 'text-emerald-600' : 'text-rose-600'
                  }`}>
                    {summary.changeVsAveragePct >= 0 ? '+' : ''}{summary.changeVsAveragePct}%
                  </span>
                ) : (
                  <StatusBadge variant="insufficient" text="数据不足" />
                )}
              </div>
              <div className="text-[10px] text-[#64748B]">
                {summary.yesterdayContextLabel || '处于近期稳定区间'}
              </div>
            </div>

            {/* Card 4: 昨日数据完整度 */}
            <div className="p-3 rounded-xl bg-[#1A1D2E] text-white space-y-1">
              <div className="text-[11px] font-medium text-slate-300 flex items-center justify-between">
                <span>昨日数据完整度</span>
                <span className={`w-2 h-2 rounded-full ${summary.isFullyComplete ? 'bg-emerald-400' : 'bg-amber-400 animate-pulse'}`} />
              </div>
              <div className="flex items-baseline gap-1.5">
                <span className="font-mono text-2xl font-black text-[#DDFD00]">
                  {summary.updatedAccounts} <span className="text-sm font-normal text-slate-300">/ {summary.totalAccounts}</span>
                </span>
              </div>
              <div className="text-[10px] text-slate-300 truncate">
                {summary.isFullyComplete ? '全部账号已结算入账' : `${summary.pendingAccounts} 个账号待补采`}
              </div>
            </div>
          </>
        ) : (
          // MULTI-DAY MODE (多日周期摘要)
          <>
            {/* Card 1: 当前周期收益 */}
            <div className="p-3 rounded-xl bg-slate-50/90 border border-black/[0.04] space-y-1">
              <div className="text-[11px] font-medium text-[#64748B] flex items-center justify-between">
                <span>当前周期累计收益</span>
                <span className="w-1.5 h-1.5 rounded-full bg-emerald-500" />
              </div>
              <div className="flex items-baseline gap-1">
                <span className="font-mono text-2xl font-black text-[#1A1D2E]">
                  ¥{summary.currentPeriodRevenue.toLocaleString('zh-CN', { minimumFractionDigits: 2 })}
                </span>
              </div>
              <div className="text-[10px] text-slate-500">
                {timeRange === '7days' ? '近7日结算 (08-17 ~ 08-23)' : timeRange === '30days' ? '近30日结算' : timeRange === 'this_month' ? '本月累计 (08-01 ~ 08-23)' : '自定义区间'}
              </div>
            </div>

            {/* Card 2: 日均收益 */}
            <div className="p-3 rounded-xl bg-slate-50/90 border border-black/[0.04] space-y-1">
              <div className="text-[11px] font-medium text-[#64748B]">周期日均收益</div>
              <div className="flex items-baseline gap-1">
                <span className="font-mono text-2xl font-black text-[#1A1D2E]">
                  ¥{summary.dailyAverageRevenue.toLocaleString('zh-CN', { minimumFractionDigits: 2 })}
                </span>
              </div>
              <div className="text-[10px] text-slate-500">
                按周期实际天数平摊
              </div>
            </div>

            {/* Card 3: 较上一周期 (严谨处理数据不足) */}
            <div className="p-3 rounded-xl bg-slate-50/90 border border-black/[0.04] space-y-1 relative group">
              <div className="text-[11px] font-medium text-[#64748B] flex items-center gap-1">
                <span>较上一周期</span>
                {summary.changePct === null && (
                  <HelpTooltip text={summary.changeInsufficientReason || '前一比较周期数据不完整'} />
                )}
              </div>
              <div className="flex items-baseline gap-1.5">
                {summary.changePct !== null ? (
                  <span className={`font-mono text-2xl font-black flex items-center gap-0.5 ${
                    summary.changePct >= 0 ? 'text-emerald-600' : 'text-rose-600'
                  }`}>
                    {summary.changePct >= 0 ? '+' : ''}{summary.changePct}%
                  </span>
                ) : (
                  <StatusBadge variant="insufficient" text="数据不足" />
                )}
              </div>
              <div className="text-[10px] text-slate-500 truncate">
                {summary.changePct !== null
                  ? `前一周期 ¥${summary.prevPeriodRevenue?.toFixed(0)}`
                  : (summary.changeInsufficientReason || '前一比较周期数据不完整')}
              </div>
            </div>

            {/* Card 4: 数据完整度 */}
            <div className="p-3 rounded-xl bg-[#1A1D2E] text-white space-y-1">
              <div className="text-[11px] font-medium text-slate-300 flex items-center justify-between">
                <span>数据完整度</span>
                <span className={`w-2 h-2 rounded-full ${summary.isFullyComplete ? 'bg-emerald-400' : 'bg-amber-400'}`} />
              </div>
              <div className="flex items-baseline gap-1.5">
                <span className="font-mono text-2xl font-black text-[#DDFD00]">
                  {Math.round(summary.completenessRatio * 100)}%
                </span>
              </div>
              <div className="text-[10px] text-slate-300 truncate">
                {summary.completenessText}
              </div>
            </div>
          </>
        )}
      </div>

      {/* 2. ADVANCED REVENUE TREND CHART (主视觉平滑贝塞尔曲线 + 虚线对比 + 昨日高亮) */}
      <AdvancedRevenueTrendChart
        trendPoints={trendPoints}
        ghostPoints={ghostPoints}
        hasGhostData={hasGhostData}
        ghostUnavailableReason={ghostUnavailableReason}
        isYesterday={summary.isYesterday}
        yesterdayContextLabel={summary.yesterdayContextLabel}
        theaterFilter={selectedTheater}
      />

      {/* 3. LOWER SECTION: 收益贡献 (8 cols) & 变化信号 (4 cols) */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-4 items-start">
        {/* Left 8 cols: 收益贡献维度 */}
        <div className="lg:col-span-8 bg-white rounded-2xl p-5 border border-black/[0.06] shadow-xs space-y-4">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div>
              <div className="flex items-center gap-2">
                <h3 className="text-sm font-bold text-[#1A1D2E] flex items-center gap-2">
                  <span>收益贡献</span>
                  <span className="text-[11px] px-2 py-0.5 rounded-md bg-slate-100 font-normal text-[#64748B]">
                    {summary.isYesterday ? '昨日分布' : '周期分布'}
                  </span>
                </h3>
                <ModuleInfoPopover
                  title="收益贡献说明"
                  content={
                    <>
                      <p>• <strong>按剧场</strong>：汇总各剧场结算渠道的收益贡献结构。</p>
                      <p>• <strong>按账号</strong>：查看各推流账号的收益分布与较上一周期变化。</p>
                      <p>• <strong>按剧集</strong>：以当前「可归因收益」为分母展示各剧集份额，未归因流水单独标出。</p>
                    </>
                  }
                />
              </div>
              <p className="text-xs text-[#64748B] mt-0.5">
                下钻查看各剧场、账号与可归因剧集的收入贡献结构与周期变化
              </p>
            </div>

            {/* Sub-tabs */}
            <div className="flex items-center gap-1 bg-slate-100 p-0.5 rounded-xl border border-black/[0.04] text-xs">
              <button
                onClick={() => setContributionTab('theaters')}
                className={`px-3 py-1 rounded-lg text-xs font-medium transition-all cursor-pointer ${
                  contributionTab === 'theaters'
                    ? 'bg-[#1A1D2E] text-white font-semibold shadow-2xs'
                    : 'text-[#64748B] hover:text-[#1A1D2E]'
                }`}
              >
                按剧场 ({theaterContributions.length})
              </button>
              <button
                onClick={() => setContributionTab('accounts')}
                className={`px-3 py-1 rounded-lg text-xs font-medium transition-all cursor-pointer ${
                  contributionTab === 'accounts'
                    ? 'bg-[#1A1D2E] text-white font-semibold shadow-2xs'
                    : 'text-[#64748B] hover:text-[#1A1D2E]'
                }`}
              >
                按账号 ({accountContributions.length})
              </button>
              <button
                onClick={() => setContributionTab('dramas')}
                className={`px-3 py-1 rounded-lg text-xs font-medium transition-all cursor-pointer ${
                  contributionTab === 'dramas'
                    ? 'bg-[#1A1D2E] text-white font-semibold shadow-2xs'
                    : 'text-[#64748B] hover:text-[#1A1D2E]'
                }`}
              >
                按剧集 ({dramaContributions.length})
              </button>
            </div>
          </div>

          {/* Special Banner when "按剧集" (Dramas) is active: Attributable Revenue Header */}
          {contributionTab === 'dramas' && (
            <div className="flex flex-wrap items-center justify-between gap-2 p-3 rounded-xl bg-slate-50 border border-black/[0.06] text-xs">
              <div className="flex items-center gap-2">
                <span className="font-bold text-[#1A1D2E]">当前可归因收益:</span>
                <span className="font-mono font-black text-emerald-700 text-sm">
                  ¥{dramaAttributionSummary.attributableRevenue.toLocaleString('zh-CN', { minimumFractionDigits: 2 })}
                </span>
                <span className="text-[#64748B] text-[11px]">
                  (占当前周期总收益 {dramaAttributionSummary.attributableRatioPct}%)
                </span>
              </div>
              <div className="text-[11px] text-[#64748B] flex items-center gap-1">
                <Info className="w-3.5 h-3.5 text-slate-400 shrink-0" />
                <span>仅计入具备明确剧集ID的平台流水，未归因收益不计入分母</span>
              </div>
            </div>
          )}

          {/* Contribution Data Table */}
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs border-collapse">
              <thead>
                <tr className="border-b border-black/[0.06] text-[#64748B] font-medium">
                  <th className="py-2.5 px-2">名称</th>
                  {contributionTab === 'dramas' && <th className="py-2.5 px-2">题材</th>}
                  {contributionTab === 'accounts' && <th className="py-2.5 px-2">所属剧场</th>}
                  <th className="py-2.5 px-2 text-right">
                    {summary.isYesterday ? '昨日收益' : '周期收益'}
                  </th>
                  <th className="py-2.5 px-3">
                    <div className="flex items-center gap-1">
                      <span>贡献占比</span>
                      <HelpTooltip text="当前对象收益占当前可归因收益的比例，不代表收益率。" />
                    </div>
                  </th>
                  <th className="py-2.5 px-2 text-right">
                    {summary.isYesterday ? '较前日' : '较上一周期'}
                  </th>
                  <th className="py-2.5 px-2 text-center">数据属性</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-black/[0.04]">
                {activeContributions.map((item) => {
                  const isClickable = (contributionTab === 'accounts' || contributionTab === 'dramas') && onNavigateToTab;

                  return (
                    <tr 
                      key={item.id} 
                      onClick={() => handleRowClick(item)}
                      className={`transition-colors ${
                        isClickable ? 'cursor-pointer hover:bg-slate-50/80 group' : 'hover:bg-slate-50/70'
                      }`}
                    >
                      {/* Name */}
                      <td className="py-2.5 px-2 font-semibold text-[#1A1D2E]">
                        <div className="flex items-center gap-1.5">
                          <span className={isClickable ? 'group-hover:text-indigo-600 transition-colors' : ''}>
                            {item.name}
                          </span>
                          {isClickable && (
                            <ChevronRight className="w-3 h-3 text-slate-400 group-hover:text-indigo-600 opacity-0 group-hover:opacity-100 transition-all shrink-0" />
                          )}
                        </div>
                      </td>

                      {/* Optional Drama Category */}
                      {contributionTab === 'dramas' && (
                        <td className="py-2.5 px-2 text-[#64748B]">
                          <span className="px-1.5 py-0.5 rounded-md bg-slate-100 text-[10px]">
                            {item.category || '短剧'}
                          </span>
                        </td>
                      )}

                      {/* Optional Account Theater */}
                      {contributionTab === 'accounts' && (
                        <td className="py-2.5 px-2 text-[#64748B]">
                          <span className="text-[11px]">{item.theater || '全渠道'}</span>
                        </td>
                      )}

                      {/* Revenue */}
                      <td className="py-2.5 px-2 text-right font-mono font-bold text-[#1A1D2E]">
                        {item.hasData !== false ? `¥${item.revenue.toLocaleString('zh-CN', { minimumFractionDigits: 2 })}` : '—'}
                      </td>

                      {/* Share % */}
                      <td className="py-2.5 px-3">
                        <div className="flex items-center gap-2">
                          <div className="w-20 h-1.5 bg-slate-100 rounded-full overflow-hidden">
                            <div 
                              className="h-full bg-[#1A1D2E] rounded-full"
                              style={{ width: `${Math.min(100, Math.max(0, item.sharePct))}%` }}
                            />
                          </div>
                          <span className="font-mono text-[11px] text-[#64748B] w-10">
                            {item.sharePct.toFixed(1)}%
                          </span>
                        </div>
                      </td>

                      {/* Change % (or Insufficient Data Pill) */}
                      <td className="py-2.5 px-2 text-right">
                        {item.changePct !== null ? (
                          <span className={`inline-flex items-center gap-0.5 font-mono text-[11px] font-semibold ${
                            item.changePct > 0 
                              ? 'text-emerald-600' 
                              : item.changePct < 0 
                              ? 'text-rose-600' 
                              : 'text-slate-500'
                          }`}>
                            {item.changePct > 0 ? (
                              <ArrowUpRight className="w-3 h-3" />
                            ) : item.changePct < 0 ? (
                              <ArrowDownRight className="w-3 h-3" />
                            ) : null}
                            {item.changePct > 0 ? `+${item.changePct}%` : `${item.changePct}%`}
                          </span>
                        ) : item.isNew ? (
                          <span className="text-[10px] px-1.5 py-0.5 rounded-md bg-blue-50 text-blue-700 font-medium">
                            新增
                          </span>
                        ) : (
                          <StatusBadge 
                            variant="insufficient" 
                            text="数据不足" 
                            tooltip={item.changeInsufficientReason || '上一周期历史数据不足，暂不计算变化'} 
                          />
                        )}
                      </td>

                      {/* Quality Tier (推测 vs 直接收益) */}
                      <td className="py-2.5 px-2 text-center">
                        {item.qualityTier === 'estimated' ? (
                          <StatusBadge variant="estimated" text="推测" tooltip="该金额由规则估算，并非数据来源直接返回的日收益。" />
                        ) : (
                          <StatusBadge variant="direct" text="直接收益" />
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>

        {/* Right 4 cols: 变化信号 (Deterministic Rule-Engine Signals) */}
        <div className="lg:col-span-4 bg-white rounded-2xl p-5 border border-black/[0.06] shadow-xs space-y-3.5">
          <div className="flex items-center justify-between">
            <h3 className="text-sm font-bold text-[#1A1D2E] flex items-center gap-2">
              <Sparkles className="w-4 h-4 text-[#1A1D2E]" />
              <span>变化信号</span>
            </h3>
            <span className="text-[10px] px-2 py-0.5 rounded-md bg-slate-100 text-[#64748B]">
              规则引擎实时判定
            </span>
          </div>
          <p className="text-xs text-[#64748B]">
            监测周期内异动、连续增长或异常未结算，点击卡片可快速穿透至对应分析
          </p>

          <div className="space-y-2.5">
            {changeSignals.map((signal) => (
              <div 
                key={signal.id}
                onClick={() => handleSignalClick(signal)}
                className="p-3 rounded-xl bg-slate-50/80 border border-black/[0.04] space-y-1.5 hover:border-black/15 hover:bg-slate-50 transition-all cursor-pointer group"
              >
                <div className="flex items-start justify-between gap-2">
                  <div className="font-bold text-xs text-[#1A1D2E] flex items-center gap-1.5">
                    <span className={`w-1.5 h-1.5 rounded-full shrink-0 ${
                      signal.type === 'positive' 
                        ? 'bg-emerald-500' 
                        : signal.type === 'negative' 
                        ? 'bg-rose-500' 
                        : signal.type === 'warning'
                        ? 'bg-amber-500'
                        : 'bg-indigo-500'
                    }`} />
                    <span className="group-hover:text-[#1A1D2E]">{signal.title}</span>
                  </div>
                  <span className={`text-[10px] font-mono font-bold px-1.5 py-0.2 rounded-md shrink-0 ${
                    signal.type === 'positive' 
                      ? 'bg-emerald-100 text-emerald-800' 
                      : signal.type === 'negative' 
                      ? 'bg-rose-100 text-rose-800' 
                      : signal.type === 'warning'
                      ? 'bg-amber-100 text-amber-800'
                      : 'bg-indigo-100 text-indigo-800'
                  }`}>
                    {signal.metric}
                  </span>
                </div>
                <p className="text-[11px] text-[#64748B] leading-relaxed">
                  {signal.description}
                </p>
                <div className="flex items-center justify-between text-[10px] text-slate-400 pt-0.5 border-t border-black/[0.03]">
                  <span>{signal.date}</span>
                  <span className="text-[#1A1D2E] font-medium flex items-center gap-0.5 opacity-0 group-hover:opacity-100 transition-opacity">
                    <span>{signal.targetType === 'collection' ? '前往采集' : signal.targetType === 'account' ? '查看账号' : '查看剧集'}</span>
                    <ChevronRight className="w-3 h-3" />
                  </span>
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
};
