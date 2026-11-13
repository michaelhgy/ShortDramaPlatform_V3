import { getOptimizationAppearance, type OptimizationSeverity } from '../../types/optimizationNotices';
import React, { useState, useMemo, useId } from 'react';
import { buildDualTrendLayout, mergeDualTrendData, type ChartDateBounds } from './dualTrendLayout';

// ==========================================
// 1. 折线 / 面积趋势图 (Area Trend Chart)
// ==========================================
export interface TrendPoint {
  date: string;
  label: string;
  value: number;
  subValue?: number;
  subLabel?: string;
}

interface AreaTrendChartProps {
  data: TrendPoint[];
  metricName: string;
  unit?: string;
  color?: string; // hex or tailwind stroke
  fillGradientId?: string;
  height?: number;
  onPointClick?: (point: TrendPoint) => void;
  selectedDate?: string;
}

export const AreaTrendChart: React.FC<AreaTrendChartProps> = ({
  data,
  metricName,
  unit = '',
  color = '#6366F1', // Indigo / Purple
  fillGradientId = 'purpleGrad',
  height = 240,
  onPointClick,
  selectedDate,
}) => {
  const [hoveredIndex, setHoveredIndex] = useState<number | null>(null);

  if (!data || data.length === 0) {
    return <div className="h-48 flex items-center justify-center text-slate-400 text-xs">暂无趋势数据</div>;
  }

  const values = data.map(d => d.value);
  const minVal = Math.min(...values) * 0.95;
  const maxVal = Math.max(...values) * 1.05;
  const range = maxVal - minVal || 1;

  const paddingLeft = 60;
  const paddingRight = 30;
  const paddingTop = 25;
  const paddingBottom = 40;
  const svgWidth = 720;
  const svgHeight = height;

  const chartWidth = svgWidth - paddingLeft - paddingRight;
  const chartHeight = svgHeight - paddingTop - paddingBottom;

  const points = data.map((d, i) => {
    const x = paddingLeft + (i / (data.length - 1 || 1)) * chartWidth;
    const y = paddingTop + chartHeight - ((d.value - minVal) / range) * chartHeight;
    return { x, y, data: d, index: i };
  });

  // Path generator
  const pathD = points.reduce((acc, p, i) => {
    return i === 0 ? `M ${p.x} ${p.y}` : `${acc} L ${p.x} ${p.y}`;
  }, '');

  const areaD = `${pathD} L ${points[points.length - 1].x} ${paddingTop + chartHeight} L ${points[0].x} ${paddingTop + chartHeight} Z`;

  // Y-axis ticks
  const yTicks = [0, 0.33, 0.66, 1].map(ratio => {
    const val = minVal + ratio * range;
    const y = paddingTop + chartHeight - ratio * chartHeight;
    return { val, y };
  });

  const activePoint = hoveredIndex !== null ? points[hoveredIndex] : null;

  return (
    <div className="relative w-full select-none">
      <svg
        viewBox={`0 0 ${svgWidth} ${svgHeight}`}
        className="w-full h-auto overflow-visible"
        onMouseLeave={() => setHoveredIndex(null)}
      >
        <defs>
          <linearGradient id={fillGradientId} x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor={color} stopOpacity="0.22" />
            <stop offset="100%" stopColor={color} stopOpacity="0.01" />
          </linearGradient>
        </defs>

        {/* Horizontal Grid lines */}
        {yTicks.map((t, idx) => (
          <g key={`area-tick-${idx}`}>
            <line
              x1={paddingLeft}
              y1={t.y}
              x2={svgWidth - paddingRight}
              y2={t.y}
              stroke="#E2E8F0"
              strokeDasharray="4 4"
              strokeWidth="1"
            />
            <text
              x={paddingLeft - 8}
              y={t.y + 4}
              textAnchor="end"
              className="text-[10px] fill-slate-400 font-mono tabular-nums"
            >
              {t.val >= 10000 ? `${(t.val / 10000).toFixed(1)}w` : Math.round(t.val).toLocaleString()}
            </text>
          </g>
        ))}

        {/* Area fill */}
        <path d={areaD} fill={`url(#${fillGradientId})`} />

        {/* Line stroke */}
        <path
          d={pathD}
          fill="none"
          stroke={color}
          strokeWidth="2.5"
          strokeLinecap="round"
          strokeLinejoin="round"
        />

        {/* Data points */}
        {points.map((p, i) => {
          const isSelected = selectedDate === p.data.date;
          const isHovered = hoveredIndex === i;
          return (
            <g
              key={`area-pt-${p.data.date}-${i}`}
              className="cursor-pointer"
              onMouseEnter={() => setHoveredIndex(i)}
              onClick={() => onPointClick && onPointClick(p.data)}
            >
              {/* Invisible larger hover target */}
              <circle cx={p.x} cy={p.y} r="14" fill="transparent" />

              {/* Highlight halo when selected or hovered */}
              {(isSelected || isHovered) && (
                <circle
                  cx={p.x}
                  cy={p.y}
                  r="7"
                  fill={color}
                  fillOpacity="0.2"
                  className="animate-ping"
                />
              )}

              {/* Point dot */}
              <circle
                cx={p.x}
                cy={p.y}
                r={isSelected || isHovered ? '5' : '3.5'}
                fill="#FFFFFF"
                stroke={color}
                strokeWidth={isSelected || isHovered ? '2.5' : '2'}
              />

              {/* X Axis Labels */}
              <text
                x={p.x}
                y={paddingTop + chartHeight + 20}
                textAnchor="middle"
                className={`text-[11px] font-medium transition-colors ${
                  isSelected || isHovered ? 'fill-indigo-900 font-bold' : 'fill-slate-400'
                }`}
              >
                {p.data.label}
              </text>
            </g>
          );
        })}

        {/* Vertical pointer line on hover */}
        {activePoint && (
          <line
            x1={activePoint.x}
            y1={paddingTop}
            x2={activePoint.x}
            y2={paddingTop + chartHeight}
            stroke={color}
            strokeWidth="1.2"
            strokeDasharray="2 2"
          />
        )}
      </svg>

      {/* Floating Tooltip */}
      {activePoint && (
        <div
          className="pointer-events-none absolute z-20 px-3 py-2 rounded-xl bg-slate-900/95 text-white shadow-xl backdrop-blur-sm text-xs -translate-x-1/2 -translate-y-full border border-white/10"
          style={{
            left: `${(activePoint.x / svgWidth) * 100}%`,
            top: `${(activePoint.y / svgHeight) * 100 - 12}%`,
          }}
        >
          <div className="flex items-center gap-1.5 font-semibold text-slate-300 text-[11px]">
            <span>{activePoint.data.date}</span>
            <span className="text-slate-500">·</span>
            <span className="text-indigo-300">点击下钻</span>
          </div>
          <div className="mt-1 flex items-baseline gap-1">
            <span className="text-slate-400 text-[11px]">{metricName}:</span>
            <span className="text-white font-bold font-mono text-sm tabular-nums">
              {activePoint.data.value.toLocaleString()}
            </span>
            {unit && <span className="text-slate-400 text-[10px]">{unit}</span>}
          </div>
          {activePoint.data.subLabel && (
            <div className="text-[10px] text-slate-400 mt-0.5">
              {activePoint.data.subLabel}: {activePoint.data.subValue?.toLocaleString()}
            </div>
          )}
        </div>
      )}
    </div>
  );
};

// ==========================================
// 2. 账号流量 / 收益占比环形图 (Donut Distribution Chart)
// ==========================================
export interface SliceItem {
  id?: string;
  name?: string;
  label?: string;
  value: number;
  color: string;
  tag?: string;
}

interface DonutDistributionChartProps {
  slices?: SliceItem[];
  title?: string;
  totalLabel?: string;
  centerLabel?: string;
  centerValue?: string;
  isCurrency?: boolean;
  onSliceClick?: (slice: SliceItem) => void;
  selectedId?: string;
}

export const DonutDistributionChart: React.FC<DonutDistributionChartProps> = ({
  slices = [],
  title,
  totalLabel,
  centerLabel = '总计',
  centerValue,
  isCurrency = false,
  onSliceClick,
  selectedId,
}) => {
  const [hoveredId, setHoveredId] = useState<string | null>(null);

  const validSlices = slices || [];
  const total = validSlices.reduce((sum, s) => sum + (s.value || 0), 0) || 1;
  const radius = 64;
  const strokeWidth = 22;
  const circumference = 2 * Math.PI * radius;

  let currentAngle = -90; // Start at top

  const paths = validSlices.map((slice, idx) => {
    const id = slice.id || slice.name || slice.label || `slice-${idx}`;
    const label = slice.label || slice.name || slice.id || `类别 ${idx + 1}`;
    const pct = (slice.value || 0) / total;
    const strokeDashoffset = circumference * (1 - pct);
    const rotation = currentAngle;
    currentAngle += pct * 360;

    return {
      slice,
      id,
      label,
      pct,
      strokeDashoffset,
      rotation,
    };
  });

  return (
    <div className="w-full">
      {/* 标题栏 */}
      {title && (
        <div className="flex items-center justify-between mb-4 pb-2 border-b border-slate-100">
          <h4 className="text-xs font-bold text-slate-800">{title}</h4>
          {totalLabel && (
            <span className="text-[11px] text-slate-400 font-mono font-medium">
              {totalLabel}
            </span>
          )}
        </div>
      )}

      <div className="flex flex-col sm:flex-row items-center gap-6">
        {/* SVG Donut Circle */}
        <div className="relative w-44 h-44 shrink-0 flex items-center justify-center">
          <svg viewBox="0 0 160 160" className="w-full h-full -rotate-90">
            {/* Background circle track */}
            <circle
              cx="80"
              cy="80"
              r={radius}
              fill="transparent"
              stroke="#F1F5F9"
              strokeWidth={strokeWidth}
            />
            {paths.map(({ slice, id, strokeDashoffset, rotation }, idx) => {
              const isHovered = hoveredId === id;
              const isSelected = selectedId === id;
              return (
                <circle
                  key={`donut-circle-${id}-${idx}`}
                  cx="80"
                  cy="80"
                  r={radius}
                  fill="transparent"
                  stroke={slice.color}
                  strokeWidth={isHovered || isSelected ? strokeWidth + 4 : strokeWidth}
                  strokeDasharray={circumference}
                  strokeDashoffset={strokeDashoffset}
                  transform={`rotate(${rotation} 80 80)`}
                  className="transition-all duration-200 cursor-pointer"
                  onMouseEnter={() => setHoveredId(id)}
                  onMouseLeave={() => setHoveredId(null)}
                  onClick={() => onSliceClick && onSliceClick(slice)}
                />
              );
            })}
          </svg>

          {/* Center content */}
          <div className="absolute inset-0 flex flex-col items-center justify-center pointer-events-none text-center px-2">
            <span className="text-[11px] text-slate-400 font-medium truncate max-w-[90px]">
              {centerLabel}
            </span>
            <span className="text-base font-extrabold text-[#1E1644] font-mono tabular-nums leading-tight">
              {centerValue || (
                isCurrency
                  ? (total >= 10000 ? `¥${(total / 10000).toFixed(1)}w` : `¥${Math.round(total).toLocaleString()}`)
                  : (total >= 10000 ? `${(total / 10000).toFixed(1)}w` : total.toLocaleString())
              )}
            </span>
          </div>
        </div>

        {/* Legend list */}
        <div className="flex-1 grid grid-cols-2 gap-x-4 gap-y-2 w-full text-xs">
          {paths.map(({ slice, id, label }, idx) => {
            const pct = (((slice.value || 0) / total) * 100).toFixed(1);
            const isSelected = selectedId === id;
            const isHovered = hoveredId === id;
            return (
              <div
                key={`donut-legend-${id}-${idx}`}
                onClick={() => onSliceClick && onSliceClick(slice)}
                onMouseEnter={() => setHoveredId(id)}
                onMouseLeave={() => setHoveredId(null)}
                className={`flex items-center justify-between p-1.5 rounded-lg cursor-pointer transition-all ${
                  isSelected || isHovered ? 'bg-indigo-50/80 font-bold' : 'hover:bg-slate-50'
                }`}
              >
                <div className="flex items-center gap-2 truncate">
                  <span
                    className="w-2.5 h-2.5 rounded-full shrink-0"
                    style={{ backgroundColor: slice.color }}
                  />
                  <span className="text-slate-700 truncate">{label}</span>
                </div>
                <div className="flex items-center gap-1 shrink-0 font-mono text-slate-500 tabular-nums">
                  <span className="font-semibold text-slate-800">{pct}%</span>
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
};

// ==========================================
// 3. 剧场收益柱状对比 (Mini Bar Chart)
// ==========================================
export interface BarItem {
  label: string;
  value: number;
  displayValue?: string;
  active?: boolean;
}

interface MiniBarChartProps {
  data: BarItem[];
  color?: string; // Emerald / Teal
  height?: number;
  unit?: string;
  onBarClick?: (item: BarItem) => void;
}

export const MiniBarChart: React.FC<MiniBarChartProps> = ({
  data = [],
  color = '#10B981',
  height = 90,
  unit = '¥',
  onBarClick,
}) => {
  const safeData = data || [];
  if (safeData.length === 0) {
    return <div className="h-20 flex items-center justify-center text-slate-400 text-xs">暂无数据</div>;
  }
  const maxVal = Math.max(...safeData.map(d => d.value), 1);

  return (
    <div className="flex items-end justify-between gap-2 w-full" style={{ height }}>
      {safeData.map((item, idx) => {
        const heightPct = Math.max((item.value / maxVal) * 100, 8);
        return (
          <div
            key={`bar-item-${idx}`}
            onClick={() => onBarClick && onBarClick(item)}
            className="flex-1 flex flex-col items-center gap-1.5 group cursor-pointer h-full justify-end"
          >
            {/* Tooltip value */}
            <span className="text-[10px] text-slate-400 group-hover:text-emerald-700 font-mono tabular-nums opacity-0 group-hover:opacity-100 transition-opacity">
              {unit}{item.value.toFixed(1)}
            </span>

            {/* Bar */}
            <div className="w-full bg-slate-100 rounded-t-md overflow-hidden flex items-end h-full max-h-[60px]">
              <div
                className="w-full rounded-t-md transition-all duration-300 group-hover:brightness-90"
                style={{
                  height: `${heightPct}%`,
                  backgroundColor: color,
                }}
              />
            </div>

            {/* X label */}
            <span className="text-[10px] text-slate-400 font-medium group-hover:text-slate-800 transition-colors">
              {item.label}
            </span>
          </div>
        );
      })}
    </div>
  );
};

// ==========================================
// 4. 优化原因分布进度条图 (Optimization Reasons Bar Chart)
// ==========================================
export interface OptimizationReasonItem {
  reason: string;
  count: number;
  percentage?: number;
  severity?: OptimizationSeverity;
  color?: string;
}

interface OptimizationReasonBarChartProps {
  data?: OptimizationReasonItem[];
  reasons?: OptimizationReasonItem[];
  selectedReason?: string | null;
  onSelectReason?: (reason: string | null) => void;
}

export const OptimizationReasonBarChart: React.FC<OptimizationReasonBarChartProps> = ({
  data,
  reasons,
  selectedReason,
  onSelectReason,
}) => {
  const list = data || reasons || [];

  if (list.length === 0) {
    return (
      <div className="h-44 flex flex-col items-center justify-center text-slate-400 text-xs">
        <span className="text-slate-300 font-medium">当前无优化异常记录</span>
      </div>
    );
  }

  const maxCount = Math.max(...list.map(d => d.count), 1);
  const totalCount = list.reduce((sum, d) => sum + d.count, 0) || 1;

  const getReasonColor = (reason: string) => getOptimizationAppearance(reason).color;


  return (
    <div role="group" aria-label="作品分析标签分布" className="w-full">
      <div className="flex items-center justify-between mb-4 pb-2 border-b border-slate-100">
        <div className="flex items-center gap-2">
          <h4 className="text-xs font-bold text-slate-800">作品分析标签分布</h4>
          <span className="text-[10px] px-1.5 py-0.2 rounded-full bg-rose-100 text-rose-700 font-bold">
            共 {totalCount} 条
          </span>
        </div>
        <span className="text-[11px] text-slate-400">点击单项快速筛选</span>
      </div>

      <div className="space-y-2.5 w-full">
        {list.map((item, idx) => {
          const isSelected = selectedReason === item.reason;
          const color = item.color || getReasonColor(item.reason);
          const severity = item.severity;
          const barWidth = Math.max((item.count / maxCount) * 100, 3);
          const percentage = item.percentage !== undefined ? item.percentage : Math.round((item.count / totalCount) * 100);

          return (
            <div
              key={`opt-reason-${item.reason || idx}`}
              onClick={() => onSelectReason && onSelectReason(isSelected ? null : item.reason)}
              className={`p-2.5 rounded-xl transition-all cursor-pointer border ${
                isSelected 
                  ? 'bg-rose-50/90 border-rose-300 shadow-xs ring-2 ring-rose-500/20' 
                  : 'bg-white hover:bg-slate-50/80 border-slate-100'
              }`}
            >
              <div className="flex items-center justify-between gap-2 mb-1.5 text-xs">
                <div className="flex items-center gap-2 truncate">
                  <span 
                    className="w-2.5 h-2.5 rounded-full shrink-0" 
                    style={{ backgroundColor: color }}
                  />
                  <span className="font-semibold text-slate-800 truncate">
                    {item.reason}
                  </span>
                  {severity && severity !== '未判定' && <span className={`text-[10px] px-1.5 py-0.2 rounded font-medium ${
                    severity === '严重' ? 'bg-red-100 text-red-700' :
                    severity === '中度' ? 'bg-amber-100 text-amber-700' :
                    'bg-slate-100 text-slate-600'
                  }`}>
                    {severity}
                  </span>}
                </div>
                <div className="flex items-center gap-2 font-mono tabular-nums shrink-0">
                  <span className="font-bold text-slate-900">{item.count} 条</span>
                  <span className="text-slate-400 text-[11px]">({percentage}%)</span>
                </div>
              </div>

              {/* Visual Bar */}
              <div className="w-full bg-slate-100 h-2 rounded-full overflow-hidden">
                <div
                  className="h-full rounded-full transition-all duration-500"
                  style={{
                    width: `${barWidth}%`,
                    backgroundColor: color,
                  }}
                />
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
};

// ==========================================
// 5. 播放量与收益联动双轴图 (Dual Trend Chart)
// ==========================================
export interface DualTrendPoint {
  date: string;
  label: string;
  views: number;
  revenue: number;
}

interface DualTrendChartProps {
  data?: DualTrendPoint[];
  revenueData?: Array<{ date: string; amount: number; theater?: string }>;
  trafficData?: Array<{ date: string; views: number; theater?: string }>;
  height?: number;
  onPointClick?: (point: DualTrendPoint) => void;
  selectedDate?: string;
  dateBounds?: ChartDateBounds;
  showHeader?: boolean;
}

export function DualTrendLegend() {
  return <div role="group" aria-label="走势指标图例" className="flex flex-wrap items-center gap-x-4 gap-y-2 text-xs">
    <div className="flex items-center gap-1.5 whitespace-nowrap">
      <span className="h-1 w-3 rounded-full bg-indigo-500" />
      <span className="font-medium text-slate-600">总播放量 (左轴)</span>
    </div>
    <div className="flex items-center gap-1.5 whitespace-nowrap">
      <span className="h-1 w-3 rounded-full bg-emerald-500" />
      <span className="font-medium text-slate-600">收益金额 (右轴)</span>
    </div>
  </div>;
}

export const DualTrendChart: React.FC<DualTrendChartProps> = ({
  data,
  revenueData,
  trafficData,
  height = 260,
  onPointClick,
  selectedDate,
  dateBounds,
  showHeader = true,
}) => {
  const [hoveredIndex, setHoveredIndex] = useState<number | null>(null);

  // 聚合收益与流量数据或直接使用 data
  const chartPoints: DualTrendPoint[] = useMemo(() => {
    if (data && data.length > 0) return data;
    if (!revenueData && !trafficData) return [];

    return mergeDualTrendData(trafficData||[],revenueData||[]);
  }, [data, revenueData, trafficData]);

  const layout = useMemo(() => buildDualTrendLayout(chartPoints,dateBounds,height),
    [chartPoints,dateBounds?.start,dateBounds?.end,height]);
  const gradientId = useId();

  if (!chartPoints || chartPoints.length === 0) {
    return <div className="h-48 flex items-center justify-center text-slate-400 text-xs">暂无走势数据</div>;
  }

  const {points,labels,maxViews,maxRevenue,paddingLeft,paddingRight,paddingTop,svgWidth,svgHeight,chartHeight} = layout;

  const hasViews=points.some(p=>Number.isFinite(p.data.views));
  const hasRevenue=points.some(p=>Number.isFinite(p.data.revenue));
  const seriesPath=(key:'yViews'|'yRev')=>points.reduce((path,p,i)=>Number.isFinite(p[key])
    ? `${path} ${i>0&&Number.isFinite(points[i-1][key])?'L':'M'} ${p.x} ${p[key]}`:path,'').trim();
  const viewsPath=seriesPath('yViews'),revPath=seriesPath('yRev');

  const viewsArea = `${viewsPath} L ${points[points.length - 1].x} ${paddingTop + chartHeight} L ${points[0].x} ${paddingTop + chartHeight} Z`;

  const activePoint = hoveredIndex !== null ? points[hoveredIndex] : null;

  return (
    <div className="w-full" data-missing-revenue={!hasRevenue || undefined}>
      {/* 顶部标题与双指标图例 */}
      {showHeader && <div className="flex flex-wrap items-center justify-between gap-3 mb-4 pb-3 border-b border-slate-100">
        <div>
          <h3 className="text-sm font-bold text-slate-800">
            矩阵全链路走势复盘 (播放量 vs 变现金额)
          </h3>
          <p className="text-[11px] text-slate-400">
            日维度播放量与直接推广收益联动曲线，支持悬停查看单日万播RPM转化效率
          </p>
        </div>

        <DualTrendLegend />
      </div>}

      <div className="relative w-full select-none">
        <svg
          viewBox={`0 0 ${svgWidth} ${svgHeight}`}
          className="w-full h-auto overflow-visible"
          onMouseLeave={() => setHoveredIndex(null)}
        >
          <defs>
            <linearGradient id={gradientId} x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="#6366F1" stopOpacity="0.18" />
              <stop offset="100%" stopColor="#6366F1" stopOpacity="0.01" />
            </linearGradient>
          </defs>

          {/* Horizontal Grid lines */}
          {[0, 0.25, 0.5, 0.75, 1].map((ratio, idx) => {
            const y = paddingTop + chartHeight - ratio * chartHeight;
            const leftVal = ratio * maxViews;
            const rightVal = ratio * maxRevenue;

            return (
              <g key={`dual-grid-${idx}`}>
                <line
                  x1={paddingLeft}
                  y1={y}
                  x2={svgWidth - paddingRight}
                  y2={y}
                  stroke="#F1F5F9"
                  strokeDasharray="4 4"
                  strokeWidth="1"
                />
                {/* Left axis (Views) */}
                <text
                  x={paddingLeft - 8}
                  y={y + 4}
                  textAnchor="end"
                  className="text-[10px] fill-indigo-500 font-mono tabular-nums font-semibold"
                >
                  {!hasViews ? '—' : leftVal >= 10000 ? `${(leftVal / 10000).toFixed(0)}w` : Math.round(leftVal)}
                </text>
                {/* Right axis (Revenue) */}
                <text
                  x={svgWidth - paddingRight + 8}
                  y={y + 4}
                  textAnchor="start"
                  className="text-[10px] fill-emerald-600 font-mono tabular-nums font-semibold"
                >
                  {!hasRevenue ? '—' : rightVal >= 10000 ? `¥${(rightVal/10000).toFixed(1)}w` : `¥${Math.round(rightVal)}`}
                </text>
              </g>
            );
          })}

          {/* Views Area Fill */}
          {points.length>1 && points.every(p=>Number.isFinite(p.yViews)) && <path d={viewsArea} fill={`url(#${gradientId})`} />}

          {/* Views Line (Indigo) */}
          {points.length>1 && <path
            d={viewsPath}
            fill="none"
            stroke="#6366F1"
            strokeWidth="2.5"
            strokeLinecap="round"
            strokeLinejoin="round"
          />}

          {/* Revenue Line (Emerald) */}
          {points.length>1 && <path
            d={revPath}
            fill="none"
            stroke="#10B981"
            strokeWidth="2.5"
            strokeLinecap="round"
            strokeLinejoin="round"
          />}

          {/* Values moved away from their dots retain a light guide to the original coordinate. */}
          {labels.filter(label=>Math.abs(label.x-label.pointX)>8 || Math.abs(label.y-label.pointY)>22).map(label=>(
            <line key={`guide-${label.index}-${label.metric}`} x1={label.pointX} y1={label.pointY}
              x2={label.x} y2={label.y+(label.y<label.pointY?7:-7)} stroke="#CBD5E1" strokeWidth="0.6" pointerEvents="none" />
          ))}

          {activePoint && <line x1={activePoint.x} y1={paddingTop} x2={activePoint.x} y2={paddingTop+chartHeight}
            stroke="#94A3B8" strokeWidth="1.2" strokeDasharray="3 3" pointerEvents="none" />}

          {/* Interactive Points */}
          {points.map((p, i) => {
            const isSelected = selectedDate === p.data.date;
            const isHovered = hoveredIndex === i;

            return (
              <g
                key={`dual-pt-${p.data.date}-${i}`}
                className="cursor-pointer"
                tabIndex={0}
                aria-label={`${p.data.date}，播放量${Number.isFinite(p.data.views)?p.data.views:'暂无数据'}，收益${Number.isFinite(p.data.revenue)?p.data.revenue.toFixed(2):'暂无数据'}`}
                onMouseEnter={() => setHoveredIndex(i)}
                onFocus={() => setHoveredIndex(i)}
                onBlur={() => setHoveredIndex(null)}
                onClick={() => onPointClick && onPointClick(p.data)}
              >
                <rect x={p.x-Math.min(20,610/points.length/2)} y={paddingTop}
                  width={Math.min(40,610/points.length)} height={chartHeight+22} fill="transparent" />

                {/* Views Point Dot */}
                {Number.isFinite(p.yViews) && <circle
                  cx={p.x}
                  cy={p.yViews}
                  r={p.overlapping ? (isSelected || isHovered ? 6.5 : 5.2) : (isSelected || isHovered ? 4.5 : 3)}
                  fill="#FFFFFF"
                  stroke="#6366F1"
                  strokeWidth="2"
                />}

                {/* Revenue Point Dot */}
                {Number.isFinite(p.yRev) && <circle
                  cx={p.x}
                  cy={p.yRev}
                  r={p.overlapping ? (isSelected || isHovered ? 3.5 : 2.5) : (isSelected || isHovered ? 4.5 : 3)}
                  fill="#FFFFFF"
                  stroke="#10B981"
                  strokeWidth={p.overlapping ? 1.7 : 2}
                />}

                {/* X Axis Label */}
                {(i%layout.dateLabelStep===0 || i===points.length-1) && <text
                  x={p.x}
                  y={layout.dateLabelY}
                  textAnchor="middle"
                  className={`text-[10px] font-medium transition-colors ${
                    isSelected || isHovered ? 'fill-slate-900 font-bold' : 'fill-slate-400'
                  }`}
                >
                  {p.data.label}
                </text>}
              </g>
            );
          })}

          {labels.map(label=><text key={`value-${label.index}-${label.metric}`} x={label.x} y={label.y}
            textAnchor="middle" dominantBaseline="central" fontSize="9" fontWeight="600"
            fontFamily="ui-monospace, SFMono-Regular, Consolas, monospace"
            fill={label.metric==='views'?'#6366F1':'#059669'} stroke="white" strokeWidth="3.5" strokeLinejoin="round"
            paintOrder="stroke" pointerEvents="none" style={{fontVariantNumeric:'tabular-nums'}}>{label.text}</text>)}
        </svg>

        {/* Floating Dual Tooltip */}
        {activePoint && (
          <div
            className="pointer-events-none absolute z-20 px-3.5 py-2.5 rounded-xl bg-slate-900/95 text-white shadow-xl backdrop-blur-sm text-xs -translate-x-1/2 -translate-y-full border border-white/10"
            style={{
              left: `${(activePoint.x / svgWidth) * 100}%`,
              top: `${(Math.min(...[activePoint.yViews, activePoint.yRev].filter(Number.isFinite)) / svgHeight) * 100 - 12}%`,
            }}
          >
            <div className="font-semibold text-slate-300 text-[11px] mb-1.5 border-b border-slate-700/60 pb-1 flex items-center justify-between gap-4">
              <span>{activePoint.data.date} (运营日记)</span>
              <span className="text-emerald-400 font-mono">
                RPM: {Number.isFinite(activePoint.data.revenue)&&activePoint.data.views>0 ? `¥${((activePoint.data.revenue/activePoint.data.views)*10000).toFixed(1)}` : '暂无数据'}
              </span>
            </div>
            <div className="flex items-center gap-2 mb-1">
              <span className="w-2 h-2 rounded-full bg-indigo-400" />
              <span className="text-slate-400 text-[11px]">总播放量:</span>
              <span className="text-indigo-300 font-bold font-mono text-xs tabular-nums">
                {Number.isFinite(activePoint.data.views)?`${activePoint.data.views.toLocaleString()} 次`:'暂无数据'}
              </span>
            </div>
            <div className="flex items-center gap-2">
              <span className="w-2 h-2 rounded-full bg-emerald-400" />
              <span className="text-slate-400 text-[11px]">当日创收:</span>
              <span className="text-emerald-300 font-bold font-mono text-xs tabular-nums">
                {Number.isFinite(activePoint.data.revenue)?`¥${activePoint.data.revenue.toLocaleString('zh-CN',{minimumFractionDigits:2,maximumFractionDigits:2})}`:'暂无数据'}
              </span>
            </div>
          </div>
        )}
      </div>
    </div>
  );
};
