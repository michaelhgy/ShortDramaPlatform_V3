import React, { useState, useMemo, useRef } from 'react';
import { TimeRangeFilter } from '../../analyticsTypes';
import { Sparkles, TrendingUp, Calendar, AlertCircle } from 'lucide-react';
import { svgPointAnchor, ViewportFloatingLayer } from './common/ViewportFloatingLayer';

export interface AccountTrendPoint {
  date: string;
  dayLabel: string;
  revenue: number;
  videoViews?: number;
  isYesterday?: boolean;
}

interface AccountTrendChartProps {
  trendPoints: AccountTrendPoint[];
  timeRange: TimeRangeFilter;
  accountName: string;
  hasVideoViews?: boolean;
}

export const AccountTrendChart: React.FC<AccountTrendChartProps> = ({
  trendPoints,
  timeRange,
  accountName,
  hasVideoViews = false,
}) => {
  const [hoverIndex, setHoverIndex] = useState<number | null>(null);
  const svgRef = useRef<SVGSVGElement>(null);

  // SVG Geometry Constants (Carefully bounded to prevent overflow)
  const svgWidth = 720;
  const svgHeight = 180;
  const padding = { top: 24, right: 28, bottom: 28, left: 44 };
  const chartWidth = svgWidth - padding.left - padding.right;
  const chartHeight = svgHeight - padding.top - padding.bottom;

  // Determine whether to show 7-day Moving Average (近30日 / 本月) vs. No Moving Average (近7日 / 昨日 / 自定义短周期)
  const isMultiWeekPeriod = timeRange === '30days' || timeRange === 'this_month' || (timeRange === 'custom' && trendPoints.length >= 14);
  const showMovingAverage = isMultiWeekPeriod && trendPoints.length >= 7;
  const isYesterdayMode = timeRange === 'yesterday';

  // 1. Calculate 7-Day Moving Average series if applicable
  const processedPoints = useMemo(() => {
    return trendPoints.map((pt, idx, arr) => {
      let ma7: number | null = null;
      if (showMovingAverage) {
        // Calculate backward 7-day window average
        const windowStart = Math.max(0, idx - 6);
        const windowSlice = arr.slice(windowStart, idx + 1);
        const sum = windowSlice.reduce((acc, curr) => acc + curr.revenue, 0);
        ma7 = Math.round((sum / windowSlice.length) * 10) / 10;
      }
      return {
        ...pt,
        ma7,
      };
    });
  }, [trendPoints, showMovingAverage]);

  // 2. Compute Max Value for dynamic scaling with comfortable headroom
  const { maxVal, minVal, peakPoint, valleyPoint, peakIdx, valleyIdx } = useMemo(() => {
    if (processedPoints.length === 0) {
      return { maxVal: 500, minVal: 0, peakPoint: null, valleyPoint: null, peakIdx: 0, valleyIdx: 0 };
    }

    let max = -Infinity;
    let min = Infinity;
    let pIdx = 0;
    let vIdx = 0;

    processedPoints.forEach((p, idx) => {
      if (p.revenue > max) {
        max = p.revenue;
        pIdx = idx;
      }
      if (p.revenue < min) {
        min = p.revenue;
        vIdx = idx;
      }
      if (p.ma7 !== null && p.ma7 > max) {
        max = p.ma7;
      }
    });

    if (max <= 0) max = 100;
    // Add 18% buffer to keep all dots and labels inside container safely
    const paddedMax = Math.ceil((max * 1.18) / 50) * 50;

    return {
      maxVal: Math.max(paddedMax, 200),
      minVal: 0,
      peakPoint: processedPoints[pIdx],
      valleyPoint: processedPoints[vIdx],
      peakIdx: pIdx,
      valleyIdx: vIdx,
    };
  }, [processedPoints]);

  // Coordinate Conversion Helpers
  const getX = (index: number, totalCount: number) => {
    if (totalCount <= 1) return padding.left + chartWidth / 2;
    return padding.left + (index / (totalCount - 1)) * chartWidth;
  };

  const getY = (val: number) => {
    const ratio = Math.max(0, Math.min(1, (val - minVal) / (maxVal - minVal || 1)));
    return padding.top + chartHeight - ratio * chartHeight;
  };

  // Smooth Cardinal Spline builder for primary trend
  const buildSmoothCurve = (pts: { x: number; y: number }[]) => {
    if (pts.length === 0) return '';
    if (pts.length === 1) return `M ${pts[0].x} ${pts[0].y}`;
    if (pts.length === 2) return `M ${pts[0].x} ${pts[0].y} L ${pts[1].x} ${pts[1].y}`;

    let path = `M ${pts[0].x} ${pts[0].y}`;
    for (let i = 0; i < pts.length - 1; i++) {
      const p0 = i > 0 ? pts[i - 1] : pts[i];
      const p1 = pts[i];
      const p2 = pts[i + 1];
      const p3 = i < pts.length - 2 ? pts[i + 2] : p2;

      const cp1x = p1.x + (p2.x - p0.x) / 5.5;
      const cp1y = p1.y + (p2.y - p0.y) / 5.5;
      const cp2x = p2.x - (p3.x - p1.x) / 5.5;
      const cp2y = p2.y - (p3.y - p1.y) / 5.5;

      path += ` C ${cp1x.toFixed(1)} ${cp1y.toFixed(1)}, ${cp2x.toFixed(1)} ${cp2y.toFixed(1)}, ${p2.x.toFixed(1)} ${p2.y.toFixed(1)}`;
    }
    return path;
  };

  // 3. Map geometric coordinates
  const coords = useMemo(() => {
    return processedPoints.map((p, idx) => ({
      x: getX(idx, processedPoints.length),
      y: getY(p.revenue),
      maY: p.ma7 !== null ? getY(p.ma7) : null,
      data: p,
      index: idx,
    }));
  }, [processedPoints, maxVal, minVal]);

  // Main continuous line paths
  const mainLinePath = useMemo(() => {
    return buildSmoothCurve(coords.map((c) => ({ x: c.x, y: c.y })));
  }, [coords]);

  const mainAreaPath = useMemo(() => {
    if (coords.length < 2) return '';
    const firstX = coords[0].x;
    const lastX = coords[coords.length - 1].x;
    const bottomY = padding.top + chartHeight;
    return `${mainLinePath} L ${lastX} ${bottomY} L ${firstX} ${bottomY} Z`;
  }, [mainLinePath, coords, chartHeight]);

  // Moving average line path
  const maLinePath = useMemo(() => {
    if (!showMovingAverage) return '';
    const maCoords = coords
      .filter((c) => c.maY !== null)
      .map((c) => ({ x: c.x, y: c.maY as number }));
    return buildSmoothCurve(maCoords);
  }, [coords, showMovingAverage]);

  // 4. Subtle Y-Axis Grid Marks (3 lightweight reference horizontal lines)
  const yAxisTicks = useMemo(() => {
    const step = maxVal / 3;
    return [
      { val: 0, y: getY(0) },
      { val: Math.round(step), y: getY(step) },
      { val: Math.round(step * 2), y: getY(step * 2) },
      { val: Math.round(maxVal), y: getY(maxVal) },
    ];
  }, [maxVal]);

  // 5. Sparse X-Axis Date Labels to avoid visual crowding
  const xLabels = useMemo(() => {
    const count = processedPoints.length;
    if (count <= 1) return coords;
    if (count <= 7) return coords; // In 7-day mode, every day is clean

    // In 30-day / this month mode, sample ~5-6 representative ticks
    const step = Math.ceil(count / 5);
    return coords.filter((_, idx) => idx === 0 || idx === count - 1 || idx % step === 0);
  }, [coords, processedPoints.length]);

  // Precise SVG Mouse Move Handler with CTM inverse transformation
  const handleMouseMove = (e: React.MouseEvent<SVGSVGElement>) => {
    const svg = e.currentTarget;
    if (!svg || processedPoints.length === 0) return;

    let relX: number;
    const ctm = svg.getScreenCTM();
    if (ctm) {
      const pt = svg.createSVGPoint();
      pt.x = e.clientX;
      pt.y = e.clientY;
      const transformed = pt.matrixTransform(ctm.inverse());
      relX = transformed.x;
    } else {
      const rect = svg.getBoundingClientRect();
      relX = ((e.clientX - rect.left) / rect.width) * svgWidth;
    }

    const total = processedPoints.length;
    if (total <= 1) {
      setHoverIndex(0);
      return;
    }

    const step = chartWidth / (total - 1);
    let selectedIdx = Math.round((relX - padding.left) / step);
    selectedIdx = Math.max(0, Math.min(total - 1, selectedIdx));

    setHoverIndex(selectedIdx);
  };

  const activePoint = hoverIndex !== null ? coords[hoverIndex] : null;

  return (
    <div className="space-y-3">
      {/* Header Info & Sub-Legends */}
      <div className="flex flex-wrap items-center justify-between gap-2 text-xs">
        <div className="flex items-center gap-2">
          <span className="font-bold text-[#1A1D2E]">
            {isYesterdayMode ? '近期走势 · 昨日结算高亮' : '账号收益多维走势'}
          </span>
          <span className="text-[11px] text-[#64748B]">
            {isYesterdayMode
              ? '(近7日流水走势背景，高亮展示昨日结算入账)'
              : showMovingAverage
              ? '(实线：真实单日流水 · 橙线：7日移动均线)'
              : '(实线：真实单日流水)'}
          </span>
        </div>

        {/* Dynamic Legend Tags */}
        <div className="flex items-center gap-3 text-[11px]">
          {/* Daily Actual Line Legend */}
          <div className="flex items-center gap-1.5 text-[#1A1D2E] font-medium">
            <span className="w-3 h-0.5 bg-[#1A1D2E] rounded-full inline-block" />
            <span>真实单日收益</span>
          </div>

          {/* 7-Day Moving Average Legend (Only shown in 30-day / this month) */}
          {showMovingAverage && (
            <div className="flex items-center gap-1.5 text-amber-700 font-medium bg-amber-50 px-2 py-0.5 rounded-md border border-amber-200/60">
              <span className="w-3 h-0.5 bg-amber-500 rounded-full inline-block border-t border-dashed border-amber-600" />
              <span>7日移动平均</span>
            </div>
          )}

          {/* Yesterday Highlight Legend */}
          {isYesterdayMode && (
            <div className="flex items-center gap-1.5 text-emerald-800 font-medium bg-emerald-50 px-2 py-0.5 rounded-md border border-emerald-200/60">
              <span className="w-2 h-2 rounded-full bg-[#1A1D2E] ring-2 ring-[#DDFD00] inline-block" />
              <span>昨日结算点</span>
            </div>
          )}
        </div>
      </div>

      {/* SVG Chart Container */}
      <div className="relative w-full bg-slate-50/80 rounded-xl p-2 sm:p-3 border border-black/[0.04] select-none overflow-hidden">
        <svg
          ref={svgRef}
          viewBox={`0 0 ${svgWidth} ${svgHeight}`}
          className="w-full h-auto overflow-hidden block cursor-crosshair"
          style={{ maxHeight: '190px' }}
          onMouseMove={handleMouseMove}
          onMouseLeave={() => setHoverIndex(null)}
        >
          <defs>
            {/* Primary Area Gradient */}
            <linearGradient id={`acc-area-grad-${accountName}`} x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="#1A1D2E" stopOpacity="0.16" />
              <stop offset="70%" stopColor="#1A1D2E" stopOpacity="0.03" />
              <stop offset="100%" stopColor="#1A1D2E" stopOpacity="0.0" />
            </linearGradient>

            {/* Subtle glow filter */}
            <filter id="softGlow" x="-20%" y="-20%" width="140%" height="140%">
              <feGaussianBlur stdDeviation="2" result="blur" />
              <feComposite in="SourceGraphic" in2="blur" operator="over" />
            </filter>
          </defs>

          {/* 1. Subtle Minimalist Y-Axis Grid Lines */}
          {yAxisTicks.map((tick, idx) => (
            <g key={idx} className="transition-opacity duration-300">
              <line
                x1={padding.left}
                y1={tick.y}
                x2={svgWidth - padding.right}
                y2={tick.y}
                stroke="#E2E8F0"
                strokeWidth={idx === 0 ? "1.2" : "0.75"}
                strokeDasharray={idx === 0 ? "none" : "3 4"}
              />
              <text
                x={padding.left - 8}
                y={tick.y + 3.5}
                textAnchor="end"
                className="text-[9px] font-mono fill-slate-400"
              >
                ¥{tick.val}
              </text>
            </g>
          ))}

          {/* 2. Shaded Area Under Primary Line */}
          {mainAreaPath && (
            <path
              d={mainAreaPath}
              fill={`url(#acc-area-grad-${accountName})`}
              className="transition-all duration-300 pointer-events-none"
            />
          )}

          {/* 3. 7-Day Moving Average Line (Smooth Golden Line) */}
          {showMovingAverage && maLinePath && (
            <path
              d={maLinePath}
              fill="none"
              stroke="#D97706"
              strokeWidth="1.8"
              strokeDasharray="4 3"
              strokeLinecap="round"
              strokeLinejoin="round"
              className="transition-all duration-300 pointer-events-none opacity-90"
            />
          )}

          {/* 4. Real Daily Revenue Main Line (High contrast crisp dark line) */}
          {mainLinePath && (
            <path
              d={mainLinePath}
              fill="none"
              stroke="#1A1D2E"
              strokeWidth="2.2"
              strokeLinecap="round"
              strokeLinejoin="round"
              className="transition-all duration-300 pointer-events-none"
            />
          )}

          {/* 5. Minimalist X-Axis Date Labels */}
          {xLabels.map((lbl, idx) => (
            <text
              key={idx}
              x={lbl.x}
              y={svgHeight - 8}
              textAnchor="middle"
              className={`text-[9px] font-mono transition-colors ${
                lbl.data.isYesterday && isYesterdayMode
                  ? 'fill-[#1A1D2E] font-black'
                  : 'fill-slate-400'
              }`}
            >
              {lbl.data.dayLabel}
            </text>
          ))}

          {/* 6. Static Data Points & Yesterday Highlight Indicator */}
          {coords.map((c) => {
            const isYest = isYesterdayMode && c.data.isYesterday;
            const isPeak = c.index === peakIdx && processedPoints.length > 3;

            return (
              <g key={c.data.date} className="pointer-events-none">
                {/* Yesterday Highlight Accent Marker */}
                {isYest && (
                  <g>
                    {/* Pulsing Outer Ring */}
                    <circle
                      cx={c.x}
                      cy={c.y}
                      r="9"
                      fill="#DDFD00"
                      fillOpacity="0.4"
                      className="animate-pulse"
                    />
                    <circle
                      cx={c.x}
                      cy={c.y}
                      r="5.5"
                      fill="#1A1D2E"
                      stroke="#DDFD00"
                      strokeWidth="2.5"
                    />
                    {/* Yesterday Tag Pill above the dot */}
                    <g transform={`translate(${c.x}, ${Math.max(14, c.y - 12)})`}>
                      <rect
                        x="-24"
                        y="-12"
                        width="48"
                        height="14"
                        rx="4"
                        fill="#1A1D2E"
                        stroke="#DDFD00"
                        strokeWidth="1"
                      />
                      <text
                        x="0"
                        y="-3"
                        textAnchor="middle"
                        className="text-[8px] font-bold fill-[#DDFD00] font-mono"
                      >
                        昨日结算
                      </text>
                    </g>
                  </g>
                )}

                {/* Normal Discrete Point Dots (rendered cleanly on 7-day or hover) */}
                {!isYest && (coords.length <= 14 || hoverIndex === c.index) && (
                  <circle
                    cx={c.x}
                    cy={c.y}
                    r={hoverIndex === c.index ? 4.5 : 2.5}
                    fill={hoverIndex === c.index ? '#1A1D2E' : '#475569'}
                    stroke="#FFFFFF"
                    strokeWidth="1.5"
                    className="transition-all duration-150"
                  />
                )}

                {/* Moving Average point dot on hover */}
                {showMovingAverage && c.maY !== null && hoverIndex === c.index && (
                  <circle
                    cx={c.x}
                    cy={c.maY}
                    r="4"
                    fill="#D97706"
                    stroke="#FFFFFF"
                    strokeWidth="1.5"
                  />
                )}
              </g>
            );
          })}

          {/* 7. Active Column Indicator Band */}
          {activePoint && coords.length > 1 && (
            <rect
              x={
                hoverIndex === 0
                  ? padding.left - 8
                  : activePoint.x - (chartWidth / (coords.length - 1)) / 2
              }
              y={padding.top}
              width={
                hoverIndex === 0 || hoverIndex === coords.length - 1
                  ? (chartWidth / (coords.length - 1)) / 2 + 8
                  : chartWidth / (coords.length - 1)
              }
              height={chartHeight}
              fill="#1A1D2E"
              fillOpacity="0.04"
              rx="4"
              className="pointer-events-none"
            />
          )}

          {/* 8. Hover Guide Vertical Cursor Line */}
          {activePoint && (
            <g className="pointer-events-none">
              <line
                x1={activePoint.x}
                y1={padding.top}
                x2={activePoint.x}
                y2={padding.top + chartHeight}
                stroke="#1A1D2E"
                strokeWidth="1"
                strokeDasharray="2 2"
                opacity="0.6"
              />
              {/* Highlight Dot */}
              <circle
                cx={activePoint.x}
                cy={activePoint.y}
                r="5"
                fill="#1A1D2E"
                stroke="#FFFFFF"
                strokeWidth="2"
              />
            </g>
          )}
        </svg>

        {/* 9. Viewport-level tooltip, free of chart-container clipping */}
        {activePoint && (
          <ViewportFloatingLayer
            getAnchorRect={() => svgPointAnchor(svgRef.current, activePoint.x, activePoint.y, svgWidth, svgHeight)}
          >
            <div className="bg-[#1A1D2E] text-white p-2 rounded-lg shadow-xl text-xs space-y-1 transition-all duration-75 border border-white/10">
              {/* Header: Date + IsYesterday */}
              <div className="flex items-center justify-between gap-3 text-[10px] pb-1 border-b border-white/10 font-mono">
              <span className="text-slate-300">{activePoint.data.date}</span>
              {activePoint.data.isYesterday && (
                <span className="px-1.5 py-0.2 rounded bg-[#DDFD00] text-[#1A1D2E] font-bold text-[9px]">
                  昨日
                </span>
              )}
            </div>

            {/* Metric 1: Real Daily Revenue */}
            <div className="flex items-center justify-between gap-4">
              <span className="text-slate-300 text-[11px]">单日真实流水:</span>
              <span className="font-mono font-bold text-[#DDFD00] text-xs">
                ¥{activePoint.data.revenue.toLocaleString('zh-CN', { minimumFractionDigits: 2 })}
              </span>
            </div>

            {/* Metric 2: 7-Day Moving Average (if applicable) */}
            {showMovingAverage && activePoint.data.ma7 !== null && (
              <div className="flex items-center justify-between gap-4">
                <span className="text-amber-300 text-[11px]">7日均线 (MA7):</span>
                <span className="font-mono font-semibold text-amber-300 text-xs">
                  ¥{activePoint.data.ma7.toFixed(2)}
                </span>
              </div>
            )}

            {/* Metric 3: Video Views (Qingning accounts) */}
            {activePoint.data.videoViews !== undefined && (
              <div className="flex items-center justify-between gap-4 pt-0.5 text-[10px] text-slate-300 border-t border-white/10">
                <span>推广播放量:</span>
                <span className="font-mono text-emerald-300">
                  {activePoint.data.videoViews.toLocaleString()} 次
                </span>
              </div>
            )}
            </div>
          </ViewportFloatingLayer>
        )}
      </div>
    </div>
  );
};
