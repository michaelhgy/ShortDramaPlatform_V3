import React, { useState } from 'react';
import { AggregatedPlatformVideo, DailyVideoRecord } from '../../utils/videoEngine';
import { TimeRangeFilter, AnalyticsTopTab } from '../../analyticsTypes';
import { 
  X, 
  Link2, 
  CheckCircle2, 
  Clock, 
  BarChart3,
  TrendingUp,
  Info,
  ChevronRight
} from 'lucide-react';
import { StatusBadge } from './common/StatusBadge';
import { HelpTooltip } from './common/HelpTooltip';

interface VideoDrawerProps {
  video: AggregatedPlatformVideo | null;
  isOpen: boolean;
  onClose: () => void;
  timeRange: TimeRangeFilter;
  onOpenLinkModal: (video: AggregatedPlatformVideo) => void;
  onNavigateToTab?: (tab: AnalyticsTopTab, entityId?: string) => void;
}

export const VideoDrawer: React.FC<VideoDrawerProps> = ({
  video,
  isOpen,
  onClose,
  timeRange,
  onOpenLinkModal,
  onNavigateToTab,
}) => {
  const [hoveredIndex, setHoveredIndex] = useState<number | null>(null);

  if (!isOpen || !video) return null;

  const timeRangeLabelMap: Record<TimeRangeFilter, string> = {
    yesterday: '昨日 (08-23)',
    '7days': '近7日 (08-17 ~ 08-23)',
    '30days': '近30日 (07-25 ~ 08-23)',
    this_month: '本月 (08-01 ~ 08-23)',
    custom: '自定义周期',
  };

  const periodLabel = timeRangeLabelMap[timeRange] || '当前周期';
  const records = video.periodDailyRecords || [];

  // SVG Chart Dimensions & Math
  const chartWidth = 500;
  const chartHeight = 140;
  const padLeft = 36;
  const padRight = 20;
  const padTop = 16;
  const padBottom = 26;

  const plotWidth = chartWidth - padLeft - padRight;
  const plotHeight = chartHeight - padTop - padBottom;

  const revenues = records.map((r) => r.revenue);
  const maxRevenue = Math.max(...revenues, 10);

  const points = records.map((r, i) => {
    const x = records.length > 1 
      ? padLeft + (i / (records.length - 1)) * plotWidth
      : padLeft + plotWidth / 2;
    const y = padTop + plotHeight - (r.revenue / maxRevenue) * plotHeight;
    return { x, y, record: r, index: i };
  });

  // Generate SVG path for line
  const linePathD = points.length > 1
    ? points.reduce((acc, p, idx) => {
        if (idx === 0) return `M ${p.x} ${p.y}`;
        return `${acc} L ${p.x} ${p.y}`;
      }, '')
    : '';

  // Generate SVG path for area fill
  const areaPathD = points.length > 1
    ? `${linePathD} L ${points[points.length - 1].x} ${padTop + plotHeight} L ${points[0].x} ${padTop + plotHeight} Z`
    : '';

  const activeHoverPoint = hoveredIndex !== null && points[hoveredIndex] ? points[hoveredIndex] : null;

  return (
    <div 
      id="video-drawer-backdrop"
      className="fixed inset-0 z-50 overflow-hidden bg-black/40 backdrop-blur-xs animate-in fade-in duration-200"
    >
      <div className="absolute inset-0" onClick={onClose} />

      <div 
        id="video-drawer-panel"
        className="absolute inset-y-0 right-0 max-w-full flex pl-10"
      >
        <div className="w-screen max-w-xl bg-white shadow-2xl border-l border-black/10 flex flex-col animate-in slide-in-from-right duration-200">
          
          {/* Drawer Header */}
          <div className="p-5 bg-[#1A1D2E] text-white flex items-center justify-between shrink-0">
            <div className="space-y-1">
              <div className="flex items-center gap-2">
                <span className="font-mono text-xs px-2 py-0.5 rounded bg-white/10 text-[#DDFD00] font-bold">
                  {video.id}
                </span>
                <span className="text-xs text-slate-300">
                  {video.theaterName} · 平台视频详情
                </span>
              </div>
              <h2 className="text-base font-bold text-white tracking-tight flex items-center gap-2">
                {video.dramaName}
              </h2>
            </div>
            <button
              onClick={onClose}
              className="p-1.5 rounded-xl text-slate-300 hover:text-white hover:bg-white/10 transition-colors cursor-pointer"
            >
              <X className="w-5 h-5" />
            </button>
          </div>

          {/* Drawer Scrollable Body */}
          <div className="flex-1 overflow-y-auto p-6 space-y-6 text-xs text-[#1A1D2E]">
            
            {/* 1. Basic Metadata Card */}
            <div className="p-4 rounded-2xl bg-slate-50 border border-black/[0.06] space-y-3">
              <div className="flex items-center justify-between text-xs pb-2 border-b border-black/[0.06]">
                <span className="font-bold text-[#1A1D2E]">基础观测信息</span>
                <span className="text-[11px] text-slate-500 bg-white px-2 py-0.5 rounded-full border border-black/[0.06]">
                  统计周期: {periodLabel}
                </span>
              </div>
              <div className="grid grid-cols-2 gap-3 text-[11px]">
                <div className="flex flex-col gap-0.5">
                  <span className="text-[#64748B]">所属账号:</span>
                  {onNavigateToTab ? (
                    <button
                      type="button"
                      onClick={() => {
                        onClose();
                        onNavigateToTab('accounts', video.accountId);
                      }}
                      className="text-left font-bold text-[#1A1D2E] hover:text-indigo-600 transition-colors flex items-center gap-1 group"
                    >
                      <span>{video.accountName}</span>
                      <ChevronRight className="w-3 h-3 text-slate-400 group-hover:text-indigo-600 transition-colors" />
                    </button>
                  ) : (
                    <span className="font-bold text-[#1A1D2E]">{video.accountName}</span>
                  )}
                </div>
                <div className="flex flex-col gap-0.5">
                  <span className="text-[#64748B]">所属剧集:</span>
                  {onNavigateToTab ? (
                    <button
                      type="button"
                      onClick={() => {
                        onClose();
                        onNavigateToTab('dramas', video.dramaId);
                      }}
                      className="text-left font-bold text-[#1A1D2E] hover:text-indigo-600 transition-colors flex items-center gap-1 group"
                    >
                      <span>{video.dramaName}</span>
                      <ChevronRight className="w-3 h-3 text-slate-400 group-hover:text-indigo-600 transition-colors" />
                    </button>
                  ) : (
                    <span className="font-bold text-[#1A1D2E]">{video.dramaName}</span>
                  )}
                </div>
                <div className="flex flex-col gap-0.5">
                  <span className="text-[#64748B]">首次观测日期:</span>
                  <span className="font-mono font-medium text-[#1A1D2E]">{video.firstObservedDate}</span>
                </div>
                <div className="flex flex-col gap-0.5">
                  <span className="text-[#64748B]">推断发布批次:</span>
                  <span className="font-mono text-slate-800">{video.candidateBatch}</span>
                </div>
              </div>
            </div>

            {/* 2. Core Period Metrics Grid */}
            <div className="space-y-2">
              <div className="flex items-center justify-between">
                <h4 className="font-bold text-[#1A1D2E] text-xs">周期表现指标</h4>
                <span className="text-[10px] text-slate-400">基于所选全局筛选范围</span>
              </div>

              <div className="grid grid-cols-2 gap-3">
                {/* 周期收益 */}
                <div className="p-3.5 rounded-2xl bg-emerald-50/70 border border-emerald-200/60 space-y-1">
                  <div className="text-[11px] text-emerald-800 font-medium flex items-center justify-between">
                    <span>周期收益</span>
                    <span className="text-[10px] text-emerald-700 bg-emerald-100/60 px-1.5 py-0.5 rounded font-mono">¥</span>
                  </div>
                  <div className="text-xl font-mono font-bold text-emerald-700">
                    ¥{video.periodRevenue.toFixed(2)}
                  </div>
                  <div className="text-[10px] text-emerald-700/80">
                    当前周期内该平台视频每日收益累计之和
                  </div>
                </div>

                {/* 周期视频播放量 */}
                <div className="p-3.5 rounded-2xl bg-blue-50/70 border border-blue-200/60 space-y-1">
                  <div className="text-[11px] text-blue-800 font-medium flex items-center justify-between">
                    <span>周期视频播放</span>
                    <span className="text-[10px] text-blue-700 bg-blue-100/60 px-1.5 py-0.5 rounded font-mono">次</span>
                  </div>
                  <div className="text-xl font-mono font-bold text-blue-800">
                    {video.periodVideoViews.toLocaleString()}
                  </div>
                  <div className="text-[10px] text-blue-700/80">
                    推广视频在青柠平台的曝光播放总量
                  </div>
                </div>

                {/* 承接强度 */}
                <div className="p-3.5 rounded-2xl bg-indigo-50/70 border border-indigo-200/60 space-y-1">
                  <div className="text-[11px] text-indigo-900 font-medium flex items-center justify-between">
                    <span>承接强度</span>
                    <HelpTooltip text="剧集播放量 ÷ 视频播放量。用于衡量观众被视频吸引后进入剧场继续观看正片的意愿强度。" />
                  </div>
                  <div className="text-xl font-mono font-bold text-indigo-800">
                    {video.receptionStrength.toFixed(2)}
                  </div>
                  <div className="text-[10px] text-indigo-700/80">
                    剧集播放 ÷ 视频播放 (比率指标)
                  </div>
                </div>

                {/* 千次视频播放收益 */}
                <div className="p-3.5 rounded-2xl bg-amber-50/70 border border-amber-200/60 space-y-1">
                  <div className="text-[11px] text-amber-900 font-medium flex items-center justify-between">
                    <span>千次视频播放收益 (RPM)</span>
                    <HelpTooltip text="周期收益 ÷ 视频播放量 × 1000。衡量每千次视频播放产生的商业变现能力。" />
                  </div>
                  <div className="text-xl font-mono font-bold text-amber-800">
                    ¥{video.rpm.toFixed(2)}
                  </div>
                  <div className="text-[10px] text-amber-700/80">
                    每千次视频播放所产生的周期收益
                  </div>
                </div>
              </div>
            </div>

            {/* 3. Internal Clip & Material Association */}
            <div className="p-4 rounded-2xl bg-slate-50 border border-black/[0.06] space-y-3">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <Link2 className="w-4 h-4 text-[#1A1D2E]" />
                  <h4 className="font-bold text-[#1A1D2E] text-xs">成片与素材归因</h4>
                </div>
                <button
                  onClick={() => onOpenLinkModal(video)}
                  className="px-2.5 py-1 rounded-xl bg-[#1A1D2E] text-[#DDFD00] text-[11px] font-bold hover:bg-black/90 active:scale-95 transition-all shadow-xs cursor-pointer"
                >
                  {video.isLinked ? '修改关联' : '核对关联'}
                </button>
              </div>

              {video.isLinked ? (
                <div className="p-3 rounded-xl bg-emerald-50/80 border border-emerald-200/70 space-y-2">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-1.5">
                      <CheckCircle2 className="w-4 h-4 text-emerald-600" />
                      <span className="font-bold text-emerald-950 text-xs">已关联内部成片</span>
                    </div>
                    <StatusBadge variant="linked" text="已精准关联" />
                  </div>
                  <div className="grid grid-cols-2 gap-2 text-[11px] text-emerald-900 pt-1">
                    <div>
                      关联成片: <strong className="text-[#1A1D2E]">{video.linkedClipName}</strong>
                    </div>
                    <div>
                      源素材编号: <strong className="text-[#1A1D2E]">{video.sourceMaterialId}</strong>
                    </div>
                    <div className="col-span-2 text-[10px] text-emerald-800/80">
                      源素材名称: {video.sourceMaterialName || `${video.dramaName}-${video.sourceMaterialId}`}
                    </div>
                  </div>
                </div>
              ) : (
                <div className="p-3 rounded-xl bg-amber-50/80 border border-amber-200/70 space-y-2">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-1.5">
                      <Clock className="w-4 h-4 text-amber-600" />
                      <span className="font-bold text-amber-950 text-xs">待核对关联成片</span>
                    </div>
                    <StatusBadge variant="unlinked" text="待关联" />
                  </div>
                  <p className="text-[11px] text-amber-900 leading-relaxed">
                    根据首次观测日期与账号批次已锁定范围：<strong className="text-[#1A1D2E]">{video.candidateBatch}</strong>。请点击右上角核对具体成片片段。
                  </p>
                </div>
              )}
            </div>

            {/* 4. Daily Revenue Trend (Line + Area Chart) */}
            <div className="space-y-3">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <TrendingUp className="w-4 h-4 text-[#1A1D2E]" />
                  <h4 className="font-bold text-[#1A1D2E] text-xs">每日收益趋势</h4>
                </div>
                <span className="text-[10px] text-slate-400">
                  共 {records.length} 天观测数据
                </span>
              </div>

              {/* Chart Card */}
              <div className="p-4 rounded-2xl bg-slate-50 border border-black/[0.06] space-y-2 relative overflow-hidden">
                {records.length >= 2 ? (
                  <div className="space-y-2">
                    {/* Header info / Hover value display */}
                    <div className="flex items-center justify-between text-[11px]">
                      <span className="text-slate-500">
                        {activeHoverPoint 
                          ? `${activeHoverPoint.record.date} (${activeHoverPoint.record.dayLabel})` 
                          : '每日收益走势 (折线 + 渐变面积)'}
                      </span>
                      <span className="font-mono font-bold text-emerald-700">
                        {activeHoverPoint 
                          ? `¥${activeHoverPoint.record.revenue.toFixed(2)}` 
                          : `最高单日: ¥${maxRevenue.toFixed(2)}`}
                      </span>
                    </div>

                    {/* SVG Line + Area Chart */}
                    <div className="relative w-full h-[140px]">
                      <svg 
                        viewBox={`0 0 ${chartWidth} ${chartHeight}`} 
                        className="w-full h-full overflow-visible"
                      >
                        <defs>
                          <linearGradient id="videoRevAreaGradient" x1="0" y1="0" x2="0" y2="1">
                            <stop offset="0%" stopColor="#10B981" stopOpacity="0.25" />
                            <stop offset="100%" stopColor="#10B981" stopOpacity="0.00" />
                          </linearGradient>
                        </defs>

                        {/* Horizontal Faint Guide Lines */}
                        <line 
                          x1={padLeft} 
                          y1={padTop} 
                          x2={chartWidth - padRight} 
                          y2={padTop} 
                          stroke="#E2E8F0" 
                          strokeDasharray="3 3" 
                          strokeWidth="1" 
                        />
                        <line 
                          x1={padLeft} 
                          y1={padTop + plotHeight / 2} 
                          x2={chartWidth - padRight} 
                          y2={padTop + plotHeight / 2} 
                          stroke="#E2E8F0" 
                          strokeDasharray="3 3" 
                          strokeWidth="1" 
                        />
                        <line 
                          x1={padLeft} 
                          y1={padTop + plotHeight} 
                          x2={chartWidth - padRight} 
                          y2={padTop + plotHeight} 
                          stroke="#CBD5E1" 
                          strokeWidth="1" 
                        />

                        {/* Y-axis Labels */}
                        <text 
                          x={padLeft - 6} 
                          y={padTop + 3} 
                          textAnchor="end" 
                          className="text-[9px] font-mono fill-slate-400"
                        >
                          ¥{Math.round(maxRevenue)}
                        </text>
                        <text 
                          x={padLeft - 6} 
                          y={padTop + plotHeight / 2 + 3} 
                          textAnchor="end" 
                          className="text-[9px] font-mono fill-slate-400"
                        >
                          ¥{Math.round(maxRevenue / 2)}
                        </text>
                        <text 
                          x={padLeft - 6} 
                          y={padTop + plotHeight + 3} 
                          textAnchor="end" 
                          className="text-[9px] font-mono fill-slate-400"
                        >
                          ¥0
                        </text>

                        {/* Area Fill */}
                        <path 
                          d={areaPathD} 
                          fill="url(#videoRevAreaGradient)" 
                        />

                        {/* Line Curve */}
                        <path 
                          d={linePathD} 
                          fill="none" 
                          stroke="#059669" 
                          strokeWidth="2.2" 
                          strokeLinecap="round" 
                          strokeLinejoin="round" 
                        />

                        {/* Active Hover Guide Line and Point */}
                        {activeHoverPoint && (
                          <>
                            <line 
                              x1={activeHoverPoint.x} 
                              y1={padTop} 
                              x2={activeHoverPoint.x} 
                              y2={padTop + plotHeight} 
                              stroke="#059669" 
                              strokeDasharray="2 2" 
                              strokeWidth="1.5" 
                            />
                            <circle 
                              cx={activeHoverPoint.x} 
                              cy={activeHoverPoint.y} 
                              r="4.5" 
                              fill="#059669" 
                              stroke="#FFFFFF" 
                              strokeWidth="2" 
                            />
                          </>
                        )}

                        {/* X-axis Date Labels */}
                        {points.map((p, idx) => {
                          const showLabel = 
                            points.length <= 8 || 
                            idx === 0 || 
                            idx === points.length - 1 || 
                            idx % Math.ceil(points.length / 5) === 0;

                          if (!showLabel) return null;
                          return (
                            <text 
                              key={p.record.date} 
                              x={p.x} 
                              y={chartHeight - 4} 
                              textAnchor="middle" 
                              className="text-[9px] font-mono fill-slate-400"
                            >
                              {p.record.dayLabel}
                            </text>
                          );
                        })}

                        {/* Interactive Transparent Hover Bars */}
                        {points.map((p, idx) => {
                          const barWidth = plotWidth / points.length;
                          return (
                            <rect 
                              key={`hover-zone-${idx}`}
                              x={p.x - barWidth / 2}
                              y={padTop}
                              width={barWidth}
                              height={plotHeight}
                              fill="transparent"
                              className="cursor-pointer"
                              onMouseEnter={() => setHoveredIndex(idx)}
                              onMouseLeave={() => setHoveredIndex(null)}
                            />
                          );
                        })}
                      </svg>
                    </div>
                  </div>
                ) : records.length === 1 ? (
                  <div className="py-6 text-center space-y-1.5">
                    <div className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full bg-emerald-100/70 text-emerald-800 font-mono font-bold text-xs">
                      <span>单日观测收益: ¥{records[0].revenue.toFixed(2)}</span>
                    </div>
                    <p className="text-[11px] text-slate-400">
                      仅 1 天观测数据（{records[0].date}），暂无走势曲线
                    </p>
                  </div>
                ) : (
                  <div className="py-6 text-center text-slate-400 text-xs">
                    暂无每日表现数据
                  </div>
                )}
              </div>
            </div>

            {/* 5. Daily Performance Breakdown (Table) */}
            <div className="space-y-3">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <BarChart3 className="w-4 h-4 text-[#1A1D2E]" />
                  <h4 className="font-bold text-[#1A1D2E] text-xs">每日表现明细</h4>
                </div>
                <span className="text-[10px] text-slate-400">
                  明细记录
                </span>
              </div>

              {/* Daily Records Table */}
              <div className="border border-black/[0.06] rounded-xl overflow-hidden bg-white">
                <table className="w-full text-left border-collapse">
                  <thead>
                    <tr className="bg-slate-50/80 text-[11px] font-bold text-[#64748B] border-b border-black/[0.06]">
                      <th className="py-2 px-3 font-medium">日期</th>
                      <th className="py-2 px-3 text-right font-medium">视频播放</th>
                      <th className="py-2 px-3 text-right font-medium">剧集播放</th>
                      <th className="py-2 px-3 text-right font-medium">当日收益</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-black/[0.04] text-[11px] font-mono">
                    {records.map((rec, i) => (
                      <tr 
                        key={rec.date} 
                        onMouseEnter={() => setHoveredIndex(i)}
                        onMouseLeave={() => setHoveredIndex(null)}
                        className={`transition-colors ${
                          hoveredIndex === i ? 'bg-emerald-50/60' : 'hover:bg-slate-50/50'
                        }`}
                      >
                        <td className="py-2 px-3 font-medium text-[#1A1D2E]">
                          {rec.date} ({rec.dayLabel})
                        </td>
                        <td className="py-2 px-3 text-right text-slate-700">
                          {rec.videoViews.toLocaleString()}
                        </td>
                        <td className="py-2 px-3 text-right text-slate-700">
                          {rec.dramaViews.toLocaleString()}
                        </td>
                        <td className="py-2 px-3 text-right font-bold text-emerald-700">
                          ¥{rec.revenue.toFixed(2)}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>

          </div>

          {/* Drawer Footer */}
          <div className="p-4 bg-slate-50 border-t border-black/[0.06] flex items-center justify-between text-xs text-slate-500">
            <span>平台视频 ID: <strong className="font-mono text-[#1A1D2E]">{video.id}</strong></span>
            <button
              onClick={onClose}
              className="px-4 py-1.5 rounded-xl bg-white border border-black/10 text-[#1A1D2E] font-medium hover:bg-slate-100 transition-colors shadow-xs cursor-pointer"
            >
              关闭
            </button>
          </div>

        </div>
      </div>
    </div>
  );
};
