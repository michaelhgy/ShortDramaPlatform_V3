import React, { useState, useMemo } from 'react';
import { 
  CombinationDimension, 
  CombinationMetric, 
  TimeRangeFilter, 
  TheaterFilter,
  AnalyticsTopTab
} from '../../analyticsTypes';
import { 
  calculateCombinationMatrix, 
  CalculatedCombinationCell 
} from '../../utils/combinationEngine';
import { 
  Grid3X3, 
  X, 
  PlusCircle, 
  Film, 
  User, 
  MapPin, 
  Calendar, 
  Layers, 
  Info,
  ChevronRight
} from 'lucide-react';
import { StatusBadge } from './common/StatusBadge';
import { HelpTooltip, ModuleInfoPopover } from './common/HelpTooltip';

interface CombinationModuleProps {
  timeRange: TimeRangeFilter;
  selectedTheater: TheaterFilter;
  customStartDate?: string;
  customEndDate?: string;
  onNavigateToTab?: (tab: AnalyticsTopTab, entityId?: string) => void;
  onScheduleToday?: (dramaId?: string, accountId?: string) => void;
}

export const CombinationModule: React.FC<CombinationModuleProps> = ({
  timeRange,
  selectedTheater,
  customStartDate,
  customEndDate,
  onNavigateToTab,
  onScheduleToday,
}) => {
  // 1. Core State: Default metric is 'total_revenue' (总收益)
  const [dimension, setDimension] = useState<CombinationDimension>('account_x_drama');
  const [metric, setMetric] = useState<CombinationMetric>('total_revenue');
  const [selectedCell, setSelectedCell] = useState<CalculatedCombinationCell | null>(null);

  // 2. Compute dynamic combination matrix based on Global Filters (timeRange & selectedTheater)
  const matrixData = useMemo(() => {
    return calculateCombinationMatrix(
      dimension, 
      metric, 
      timeRange, 
      selectedTheater,
      customStartDate,
      customEndDate
    );
  }, [dimension, metric, timeRange, selectedTheater, customStartDate, customEndDate]);

  const { rowHeaders, colHeaders, cellMap, percentiles } = matrixData;

  const dimensionLabels: Record<CombinationDimension, string> = {
    account_x_drama: '账号 × 剧集',
    account_x_location: '账号 × 虚拟定位',
    drama_x_location: '剧集 × 虚拟定位',
  };

  const metricLabels: Record<CombinationMetric, string> = {
    total_revenue: '总收益 (¥)',
    avg_revenue: '平均单条收益 (¥)',
    publish_count: '发布次数 (条)',
    video_views: '视频播放量',
    drama_views: '剧集播放量',
  };

  const timeRangeLabels: Record<TimeRangeFilter, string> = {
    yesterday: '昨日 (2026-08-23)',
    '7days': '近7日 (2026-08-17 ~ 2026-08-23)',
    '30days': '近30日 (2026-07-25 ~ 2026-08-23)',
    this_month: '本月 (2026-08-01 ~ 2026-08-23)',
    custom: `自定义 (${customStartDate || '2026-08-10'} ~ ${customEndDate || '2026-08-23'})`,
  };

  // Helper function to get heatmap background based on percentile distribution
  const getCellHeatStyle = (cell: CalculatedCombinationCell) => {
    if (cell.isInapplicable) {
      return 'bg-slate-100/60 text-slate-300 cursor-not-allowed select-none';
    }

    if (!cell.hasRecords) {
      return 'bg-white hover:bg-slate-50/70 text-slate-300';
    }

    let val = 0;
    let isAvailable = true;

    if (metric === 'total_revenue') {
      if (!cell.isAttributable) isAvailable = false;
      else val = cell.totalRevenue;
    } else if (metric === 'avg_revenue') {
      if (!cell.isAttributable) isAvailable = false;
      else val = cell.avgRevenue;
    } else if (metric === 'publish_count') {
      val = cell.sampleCount;
    } else if (metric === 'video_views') {
      if (cell.videoViews === undefined) isAvailable = false;
      else val = cell.videoViews;
    } else if (metric === 'drama_views') {
      if (cell.dramaViews === undefined) isAvailable = false;
      else val = cell.dramaViews;
    }

    if (!isAvailable || val <= 0) {
      return 'bg-emerald-50/30 hover:bg-emerald-50 text-slate-400';
    }

    const { p25, p50, p75, p90 } = percentiles;

    if (val >= p90) {
      return 'bg-emerald-600 hover:bg-emerald-700 text-white font-bold shadow-xs';
    }
    if (val >= p75) {
      return 'bg-emerald-400 hover:bg-emerald-500 text-emerald-950 font-bold';
    }
    if (val >= p50) {
      return 'bg-emerald-200 hover:bg-emerald-300 text-emerald-950 font-semibold';
    }
    if (val >= p25) {
      return 'bg-emerald-100/90 hover:bg-emerald-200 text-emerald-900 font-medium';
    }
    return 'bg-emerald-50/80 hover:bg-emerald-100 text-emerald-800 font-medium';
  };

  // Helper for sub-label color based on cell heat
  const getSubLabelColor = (cell: CalculatedCombinationCell) => {
    if (cell.isInapplicable || !cell.hasRecords) return 'text-slate-300';

    let val = 0;
    if (metric === 'total_revenue' && cell.isAttributable) val = cell.totalRevenue;
    else if (metric === 'avg_revenue' && cell.isAttributable) val = cell.avgRevenue;
    else if (metric === 'publish_count') val = cell.sampleCount;
    else if (metric === 'video_views' && cell.videoViews) val = cell.videoViews;
    else if (metric === 'drama_views' && cell.dramaViews) val = cell.dramaViews;

    if (val >= percentiles.p90) return 'text-emerald-100';
    if (val >= percentiles.p75) return 'text-emerald-900';
    if (val >= percentiles.p50) return 'text-emerald-800';
    return 'text-[#64748B]';
  };

  return (
    <div className="space-y-4">
      {/* 1. CONTROL TOOLBAR: Dimensions & Metric Selectors */}
      <div className="bg-white rounded-2xl p-4 border border-black/[0.06] shadow-xs space-y-3">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <div className="flex items-center gap-2">
              <Grid3X3 className="w-4 h-4 text-emerald-600" />
              <h3 className="text-sm font-bold text-[#1A1D2E]">
                多维真实表现矩阵 (Combination Matrix)
              </h3>
              <span className="text-[11px] px-2 py-0.5 rounded-full bg-slate-100 text-slate-600 font-mono">
                {timeRangeLabels[timeRange]} · {selectedTheater === 'all' ? '全部剧场' : selectedTheater}
              </span>
              <ModuleInfoPopover
                title="组合矩阵说明"
                content={
                  <>
                    <p>• <strong>矩阵维度</strong>：支持账号×剧集、账号×虚拟定位、剧集×虚拟定位三种交织分析。</p>
                    <p>• <strong>默认指标</strong>：严格默认「总收益」，避免均值受极值误导。</p>
                    <p>• <strong>样本规模</strong>：发布次数标记样本丰富度，辅助判断组合真实置信度。</p>
                    <p>• <strong>业务边界</strong>：严格遵守「一部剧归属单一剧场」，跨剧场组合直接标明「不适用」。</p>
                  </>
                }
              />
            </div>
            <p className="text-xs text-[#64748B] mt-0.5">
              严守「一部剧归属单一剧场」业务边界，真实沉淀各组合历史归因证据与样本规模。
            </p>
          </div>

          {/* Dimension Selector */}
          <div className="flex items-center gap-1 bg-slate-100 p-0.5 rounded-xl border border-black/[0.04] text-xs">
            {(['account_x_drama', 'account_x_location', 'drama_x_location'] as CombinationDimension[]).map((d) => (
              <button
                key={d}
                onClick={() => {
                  setDimension(d);
                  setSelectedCell(null);
                }}
                className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-all cursor-pointer ${
                  dimension === d
                    ? 'bg-[#1A1D2E] text-white font-semibold shadow-xs'
                    : 'text-[#64748B] hover:text-[#1A1D2E]'
                }`}
              >
                {dimensionLabels[d]}
              </button>
            ))}
          </div>
        </div>

        {/* Metric Selector Bar */}
        <div className="flex flex-wrap items-center justify-between gap-3 pt-2 border-t border-black/[0.04] text-xs">
          <div className="flex items-center gap-2">
            <span className="text-[11px] text-[#64748B] font-medium">默认/切换指标:</span>
            <div className="flex items-center gap-1 bg-slate-50 p-0.5 rounded-lg border border-black/[0.04]">
              {(['total_revenue', 'avg_revenue', 'publish_count', 'video_views', 'drama_views'] as CombinationMetric[]).map((m) => (
                <button
                  key={m}
                  onClick={() => setMetric(m)}
                  className={`px-2.5 py-1 rounded-md text-[11px] font-medium transition-all cursor-pointer ${
                    metric === m
                      ? 'bg-white text-[#1A1D2E] font-bold shadow-2xs'
                      : 'text-[#64748B] hover:text-[#1A1D2E]'
                  }`}
                >
                  {metricLabels[m]}
                  {m === 'total_revenue' && <span className="ml-1 text-[9px] text-emerald-600 font-bold">(默认)</span>}
                </button>
              ))}
            </div>
          </div>

          {/* Visual Legend */}
          <div className="flex items-center gap-3 text-[11px] text-[#64748B]">
            <div className="flex items-center gap-1.5">
              <span className="w-5 h-3.5 rounded-xs bg-slate-100/70 border border-slate-200/60 text-center text-[8px] text-slate-400 flex items-center justify-center">
                不适用
              </span>
              <span className="text-[10px] text-slate-500">跨剧场不适用</span>
            </div>

            <div className="flex items-center gap-1.5">
              <span className="w-4 h-3.5 rounded-xs bg-white border border-black/[0.08] text-center text-[9px] text-slate-400 flex items-center justify-center">
                —
              </span>
              <span className="text-[10px] text-slate-500">无记录</span>
            </div>

            <div className="flex items-center gap-1 ml-2">
              <span className="text-[10px] text-slate-400 mr-0.5">热力分层:</span>
              <span className="w-3.5 h-3 rounded-xs bg-emerald-50 border border-emerald-100" title="P25以下" />
              <span className="w-3.5 h-3 rounded-xs bg-emerald-100" title="P25~P50" />
              <span className="w-3.5 h-3 rounded-xs bg-emerald-200" title="P50~P75" />
              <span className="w-3.5 h-3 rounded-xs bg-emerald-400" title="P75~P90" />
              <span className="w-3.5 h-3 rounded-xs bg-emerald-600" title="P90+" />
              <span className="text-[10px] text-emerald-800 font-bold ml-0.5">高产出</span>
            </div>
          </div>
        </div>
      </div>

      {/* 2. THE MATRIX HEATMAP GRID (Preserve exact horizontal/vertical scroll & sticky behaviors) */}
      <div className="bg-white rounded-2xl p-4 border border-black/[0.06] shadow-xs overflow-hidden">
        {rowHeaders.length === 0 || colHeaders.length === 0 ? (
          <div className="py-12 text-center text-slate-400 text-xs">
            当前剧场筛选下暂无可展示的行列组合
          </div>
        ) : (
          <div className="overflow-x-auto max-h-[580px] overflow-y-auto">
            <table className="w-full border-collapse text-xs">
              <thead>
                <tr>
                  {/* Top-Left Corner Header */}
                  <th className="sticky top-0 left-0 z-20 bg-slate-100 p-2.5 text-left font-bold text-[#1A1D2E] border-b border-r border-black/[0.08] min-w-[150px] shadow-2xs">
                    {dimension === 'drama_x_location' ? '剧集 \\ 虚拟定位' : dimension === 'account_x_location' ? '账号 \\ 虚拟定位' : '账号 \\ 剧集'}
                  </th>

                  {/* Column Headers */}
                  {colHeaders.map((col) => (
                    <th
                      key={col.key}
                      className="sticky top-0 z-10 bg-slate-50 p-2.5 text-center font-bold text-[#1A1D2E] border-b border-r border-black/[0.06] min-w-[120px] max-w-[170px] truncate shadow-2xs"
                      title={col.label}
                    >
                      <div className="truncate">{col.label}</div>
                      {col.theaterName && (
                        <div className="text-[9px] font-normal text-[#64748B] truncate">
                          {col.theaterName}
                        </div>
                      )}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {rowHeaders.map((row) => (
                  <tr key={row.key} className="border-b border-black/[0.04]">
                    {/* Sticky Row Header */}
                    <th className="sticky left-0 z-10 bg-slate-50/95 p-2.5 text-left font-bold text-[#1A1D2E] border-r border-black/[0.08] whitespace-nowrap shadow-2xs">
                      <div className="flex items-center gap-1.5">
                        <span className="truncate">{row.label}</span>
                      </div>
                      {row.theaterName && (
                        <div className="text-[9px] font-normal text-[#64748B]">
                          {row.theaterName}
                        </div>
                      )}
                    </th>

                    {/* Cell Values */}
                    {colHeaders.map((col) => {
                      const mapKey = `${row.key}:::${col.key}`;
                      const cell = cellMap.get(mapKey);

                      // Safety fallback
                      if (!cell) {
                        return (
                          <td
                            key={col.key}
                            className="p-2.5 text-center border-r border-black/[0.04] bg-white text-slate-300 font-mono text-xs select-none"
                          >
                            —
                          </td>
                        );
                      }

                      // 1. 不适用状态 (Inapplicable - cross-theater)
                      if (cell.isInapplicable) {
                        return (
                          <td
                            key={col.key}
                            className="p-2.5 text-center border-r border-black/[0.04] bg-slate-100/50 text-slate-300 text-[10px] select-none cursor-not-allowed"
                            title="业务规则：该剧不属于此剧场，不适用该组合"
                          >
                            <span className="text-[9px] text-slate-400">不适用</span>
                          </td>
                        );
                      }

                      // 2. 无历史记录 (No Records)
                      if (!cell.hasRecords) {
                        return (
                          <td
                            key={col.key}
                            onClick={() => setSelectedCell(cell)}
                            className="p-2.5 text-center border-r border-black/[0.04] bg-white hover:bg-slate-50 text-slate-300 text-xs cursor-pointer select-none transition-colors"
                            title="点击查看详情（当前周期内暂无发布记录）"
                          >
                            —
                          </td>
                        );
                      }

                      // 3. 正常数据单元格 (Valid Data Cell with Heatmap Style)
                      const heatClass = getCellHeatStyle(cell);
                      const subLabelColor = getSubLabelColor(cell);

                      return (
                        <td
                          key={col.key}
                          onClick={() => setSelectedCell(cell)}
                          className={`p-2 text-center border-r border-black/[0.04] cursor-pointer transition-all duration-150 relative ${heatClass}`}
                          title={`点击查看真实发布证据明细 (${cell.sampleCount}条记录)`}
                        >
                          <div className="flex flex-col items-center justify-center leading-tight">
                            {/* Primary Metric Value */}
                            <span className="font-mono text-xs font-bold">
                              {metric === 'total_revenue' && (
                                cell.isAttributable ? `¥${cell.totalRevenue.toFixed(0)}` : '—'
                              )}
                              {metric === 'avg_revenue' && (
                                cell.isAttributable ? `¥${cell.avgRevenue.toFixed(1)}` : '—'
                              )}
                              {metric === 'publish_count' && `${cell.sampleCount}条`}
                              {metric === 'video_views' && (
                                cell.videoViews ? `${(cell.videoViews / 10000).toFixed(1)}w` : '—'
                              )}
                              {metric === 'drama_views' && (
                                cell.dramaViews ? `${(cell.dramaViews / 10000).toFixed(1)}w` : '—'
                              )}
                            </span>

                            {/* Secondary Sample Counter Pill */}
                            <span className={`text-[9px] font-mono mt-0.5 ${subLabelColor}`}>
                              {cell.sampleCount}次
                              {cell.zeroRevenueCount > 0 && metric === 'total_revenue' && (
                                <span className="opacity-80"> (0收{cell.zeroRevenueCount})</span>
                              )}
                            </span>
                          </div>
                        </td>
                      );
                    })}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* 3. CELL DETAIL SIDE DRAWER (Shows Objective Historical Evidence) */}
      {selectedCell && (
        <div className="fixed inset-0 z-50 overflow-hidden bg-black/40 backdrop-blur-xs flex justify-end animate-in fade-in duration-150">
          <div className="w-full max-w-2xl bg-white h-full shadow-2xl flex flex-col border-l border-black/10 animate-in slide-in-from-right duration-200">
            {/* Drawer Header */}
            <div className="p-5 border-b border-black/[0.06] bg-slate-50 flex items-center justify-between shrink-0">
              <div className="space-y-1">
                <div className="flex items-center gap-2">
                  <span className="px-2 py-0.5 rounded-md bg-[#1A1D2E] text-[#DDFD00] text-xs font-bold font-mono">
                    组合详情证据
                  </span>
                  <span className="text-xs text-[#64748B]">
                    {dimensionLabels[dimension]}
                  </span>
                </div>
                <h3 className="text-base font-black text-[#1A1D2E]">
                  {selectedCell.rowName} × {selectedCell.colName}
                </h3>
              </div>

              <div className="flex items-center gap-2">
                {onScheduleToday && selectedCell.dramaId && (
                  <button
                    onClick={() => onScheduleToday(selectedCell.dramaId, selectedCell.accountId)}
                    className="flex items-center gap-1.5 px-3 py-1.5 rounded-xl bg-[#1A1D2E] text-[#DDFD00] text-xs font-semibold hover:bg-black/90 active:scale-95 transition-all shadow-xs cursor-pointer"
                  >
                    <PlusCircle className="w-3.5 h-3.5" />
                    <span>安排此组合排期</span>
                  </button>
                )}
                <button
                  onClick={() => setSelectedCell(null)}
                  className="p-1.5 rounded-xl hover:bg-slate-200 text-slate-500 hover:text-[#1A1D2E] transition-colors cursor-pointer"
                >
                  <X className="w-5 h-5" />
                </button>
              </div>
            </div>

            {/* Drawer Body */}
            <div className="flex-1 overflow-y-auto p-5 space-y-5">
              {/* 1. Core Summary Stats Grid */}
              <div className="space-y-2">
                <div className="flex items-center justify-between text-xs text-[#64748B]">
                  <span className="font-bold text-[#1A1D2E]">该组合在当前统计周期内的整体表现</span>
                  <span className="font-mono">{timeRangeLabels[timeRange]}</span>
                </div>

                <div className="grid grid-cols-2 sm:grid-cols-3 gap-2.5">
                  {/* 总收益 (Default Core Metric) */}
                  <div className="p-3 rounded-xl bg-emerald-50/70 border border-emerald-200/60">
                    <div className="text-[11px] text-emerald-900 font-bold flex items-center justify-between">
                      <span>总收益 (默认指标)</span>
                    </div>
                    <div className="font-mono text-xl font-black text-emerald-900 mt-0.5">
                      {selectedCell.isAttributable 
                        ? `¥${selectedCell.totalRevenue.toLocaleString('zh-CN', { minimumFractionDigits: 2 })}` 
                        : '—'}
                    </div>
                    <div className="text-[10px] text-slate-400 mt-0.5">
                      {selectedCell.isAttributable ? '所选周期精确归因总和' : '渠道未提供单视频归因'}
                    </div>
                  </div>

                  {/* 发布次数 */}
                  <div className="p-3 rounded-xl bg-slate-50 border border-black/[0.04]">
                    <div className="text-[11px] text-[#64748B]">发布次数</div>
                    <div className="font-mono text-base font-black text-[#1A1D2E] mt-0.5">
                      {selectedCell.sampleCount} <span className="text-xs font-normal text-slate-500">条</span>
                    </div>
                    <div className="text-[10px] text-slate-400 mt-0.5">
                      周期内平台推广视频样本量
                    </div>
                  </div>

                  {/* 0收益视频数量 */}
                  <div className="p-3 rounded-xl bg-amber-50/60 border border-amber-200/60">
                    <div className="text-[11px] text-amber-900 font-medium">0收益视频数</div>
                    <div className="font-mono text-base font-black text-amber-900 mt-0.5">
                      {selectedCell.zeroRevenueCount} / {selectedCell.sampleCount}
                    </div>
                    <div className="text-[10px] text-amber-700/80 mt-0.5">
                      {selectedCell.sampleCount > 0 
                        ? `${selectedCell.sampleCount} 条中有 ${selectedCell.zeroRevenueCount} 条周期收益为 0`
                        : '暂无数据'}
                    </div>
                  </div>

                  {/* 平均单条收益 */}
                  <div className="p-3 rounded-xl bg-slate-50 border border-black/[0.04]">
                    <div className="text-[11px] text-[#64748B]">平均单条收益 (辅助)</div>
                    <div className="font-mono text-base font-bold text-slate-800 mt-0.5">
                      {selectedCell.isAttributable ? `¥${selectedCell.avgRevenue.toFixed(2)}` : '—'}
                    </div>
                    <div className="text-[10px] text-slate-400 mt-0.5">
                      可归因收益 ÷ 可归因发布数
                    </div>
                  </div>

                  {/* 中位单条收益 */}
                  <div className="p-3 rounded-xl bg-slate-50 border border-black/[0.04]">
                    <div className="text-[11px] text-[#64748B]">中位单条收益</div>
                    <div className="font-mono text-base font-bold text-slate-800 mt-0.5">
                      {selectedCell.isAttributable ? `¥${selectedCell.medianRevenue.toFixed(2)}` : '—'}
                    </div>
                    <div className="text-[10px] text-slate-400 mt-0.5">
                      有效避免极端爆款拉高均值
                    </div>
                  </div>

                  {/* 最高单条收益 */}
                  <div className="p-3 rounded-xl bg-emerald-50/60 border border-emerald-200/60">
                    <div className="text-[11px] text-emerald-900 font-medium">最高单条收益</div>
                    <div className="font-mono text-base font-black text-emerald-900 mt-0.5">
                      {selectedCell.isAttributable ? `¥${selectedCell.bestRevenue.toFixed(2)}` : '—'}
                    </div>
                    <div className="text-[10px] text-emerald-700/80 mt-0.5">
                      单条视频产出峰值
                    </div>
                  </div>

                  {/* 视频播放量 */}
                  <div className="p-3 rounded-xl bg-slate-50 border border-black/[0.04]">
                    <div className="text-[11px] text-[#64748B]">视频播放量</div>
                    <div className="font-mono text-base font-bold text-slate-800 mt-0.5">
                      {selectedCell.videoViews ? selectedCell.videoViews.toLocaleString() : '—'}
                    </div>
                    <div className="text-[10px] text-slate-400 mt-0.5">
                      {selectedCell.videoViews ? '青柠视频号生态播放' : '非青柠渠道未回传'}
                    </div>
                  </div>

                  {/* 剧集播放量 */}
                  <div className="p-3 rounded-xl bg-slate-50 border border-black/[0.04]">
                    <div className="text-[11px] text-[#64748B]">剧集播放量</div>
                    <div className="font-mono text-base font-bold text-slate-800 mt-0.5">
                      {selectedCell.dramaViews ? selectedCell.dramaViews.toLocaleString() : '—'}
                    </div>
                    <div className="text-[10px] text-slate-400 mt-0.5">
                      {selectedCell.dramaViews ? '完播与承接剧集播放' : '非青柠渠道未回传'}
                    </div>
                  </div>
                </div>
              </div>

              {/* 2. Real Historical Published Video Evidence Table */}
              <div className="space-y-2.5">
                <div className="flex items-center justify-between">
                  <h4 className="text-xs font-bold text-[#1A1D2E] uppercase tracking-wider flex items-center gap-1.5">
                    <Film className="w-3.5 h-3.5 text-indigo-600" />
                    <span>真实发布明细记录 ({selectedCell.publishRecords.length} 条)</span>
                  </h4>
                  <span className="text-[11px] text-[#64748B]">
                    按发布业务日期倒序排列
                  </span>
                </div>

                {selectedCell.publishRecords.length === 0 ? (
                  <div className="p-6 text-center text-slate-400 text-xs bg-slate-50 rounded-xl">
                    当前统计周期内无明细记录
                  </div>
                ) : (
                  <div className="border border-black/[0.06] rounded-xl overflow-hidden shadow-2xs">
                    <div className="overflow-x-auto max-h-80 overflow-y-auto">
                      <table className="w-full text-left text-xs border-collapse">
                        <thead className="sticky top-0 bg-slate-100 z-10">
                          <tr className="border-b border-black/[0.06] text-[#64748B] font-medium text-[11px]">
                            <th className="py-2.5 px-3 whitespace-nowrap">业务日期</th>
                            <th className="py-2.5 px-3 min-w-[140px]">成片/视频名称</th>
                            <th className="py-2.5 px-3 whitespace-nowrap">账号</th>
                            <th className="py-2.5 px-3 whitespace-nowrap">剧集</th>
                            <th className="py-2.5 px-3 min-w-[130px]">虚拟定位</th>
                            <th className="py-2.5 px-3 text-right whitespace-nowrap">收益 (¥)</th>
                            <th className="py-2.5 px-3 text-right whitespace-nowrap">视频播放</th>
                            <th className="py-2.5 px-3 text-right whitespace-nowrap">剧集播放</th>
                          </tr>
                        </thead>
                        <tbody className="divide-y divide-black/[0.04]">
                          {selectedCell.publishRecords.map((rec) => (
                            <tr key={rec.id} className="hover:bg-slate-50/80 transition-colors">
                              <td className="py-2 px-3 font-mono text-slate-500 whitespace-nowrap">
                                {rec.date}
                              </td>
                              <td className="py-2 px-3 font-semibold text-[#1A1D2E]">
                                {rec.videoName}
                              </td>
                              <td className="py-2 px-3 text-slate-600 whitespace-nowrap">
                                {onNavigateToTab && rec.accountId ? (
                                  <button
                                    type="button"
                                    onClick={() => {
                                      setSelectedCell(null);
                                      onNavigateToTab('accounts', rec.accountId);
                                    }}
                                    className="text-left hover:text-indigo-600 transition-colors"
                                  >
                                    {rec.accountName}
                                  </button>
                                ) : (
                                  rec.accountName
                                )}
                              </td>
                              <td className="py-2 px-3 text-slate-600 whitespace-nowrap">
                                {onNavigateToTab && rec.dramaId ? (
                                  <button
                                    type="button"
                                    onClick={() => {
                                      setSelectedCell(null);
                                      onNavigateToTab('dramas', rec.dramaId);
                                    }}
                                    className="text-left hover:text-indigo-600 transition-colors"
                                  >
                                    {rec.dramaName}
                                  </button>
                                ) : (
                                  rec.dramaName
                                )}
                              </td>
                              <td className="py-2 px-3 text-[#64748B] text-[11px] max-w-[160px] truncate" title={rec.locationText}>
                                {rec.locationText}
                              </td>
                              <td className="py-2 px-3 text-right font-mono font-bold whitespace-nowrap">
                                {rec.isAttributable ? (
                                  rec.revenue === 0 ? (
                                    <span className="text-slate-400 font-normal">¥0.00</span>
                                  ) : (
                                    <span className="text-emerald-700">¥{rec.revenue.toFixed(2)}</span>
                                  )
                                ) : (
                                  <span className="text-slate-300 font-normal">—</span>
                                )}
                              </td>
                              <td className="py-2 px-3 text-right font-mono text-slate-600 whitespace-nowrap">
                                {rec.videoViews !== undefined ? rec.videoViews.toLocaleString() : '—'}
                              </td>
                              <td className="py-2 px-3 text-right font-mono text-slate-600 whitespace-nowrap">
                                {rec.dramaViews !== undefined ? rec.dramaViews.toLocaleString() : '—'}
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </div>
                )}
              </div>
            </div>

            {/* Drawer Footer */}
            <div className="p-4 border-t border-black/[0.06] bg-slate-50/50 flex items-center justify-between text-xs text-[#64748B]">
              <div className="flex items-center gap-1.5">
                <Info className="w-3.5 h-3.5 text-slate-400" />
                <span>展示全部真实历史发布证据，不含任何算法估算或伪造评分</span>
              </div>
              <button
                onClick={() => setSelectedCell(null)}
                className="px-4 py-1.5 rounded-xl bg-slate-200 text-[#1A1D2E] font-bold hover:bg-slate-300 transition-colors cursor-pointer"
              >
                关闭详情
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
