import React, { useState, useMemo, useRef } from 'react';
import { 
  DailyRevenueDataPoint, 
  TrendGhostPoint, 
  TheaterFilter 
} from '../../analyticsTypes';
import { 
  TrendingUp, 
  TrendingDown, 
  Info, 
  Layers, 
  Film, 
  Sparkles, 
  CheckCircle2, 
  AlertCircle 
} from 'lucide-react';
import { svgPointAnchor, ViewportFloatingLayer } from './common/ViewportFloatingLayer';

interface AdvancedRevenueTrendChartProps {
  trendPoints: DailyRevenueDataPoint[];
  ghostPoints?: TrendGhostPoint[];
  hasGhostData: boolean;
  ghostUnavailableReason?: string;
  isYesterday: boolean;
  yesterdayContextLabel?: string;
  theaterFilter: TheaterFilter;
}

export const AdvancedRevenueTrendChart: React.FC<AdvancedRevenueTrendChartProps> = ({
  trendPoints,
  ghostPoints = [],
  hasGhostData,
  ghostUnavailableReason,
  isYesterday,
  yesterdayContextLabel,
  theaterFilter,
}) => {
  const [viewMode, setTrendViewMode] = useState<'total' | 'theaters' | 'views'>('total');
  const [hoverIndex, setHoverIndex] = useState<number | null>(null);
  const svgRef = useRef<SVGSVGElement>(null);

  // SVG Chart Geometry Constants
  const svgWidth = 800;
  const svgHeight = 220;
  const padding = { top: 28, right: 36, bottom: 32, left: 56 };
  const chartWidth = svgWidth - padding.left - padding.right;
  const chartHeight = svgHeight - padding.top - padding.bottom;

  // Compute Peak & Valley
  const { maxVal, minVal, peakIndex, valleyIndex } = useMemo(() => {
    if (trendPoints.length === 0) return { maxVal: 1000, minVal: 0, peakIndex: 0, valleyIndex: 0 };
    
    let max = -Infinity;
    let min = Infinity;
    let pIdx = 0;
    let vIdx = 0;

    trendPoints.forEach((p, idx) => {
      if (p.totalRevenue > max) {
        max = p.totalRevenue;
        pIdx = idx;
      }
      if (p.totalRevenue < min) {
        min = p.totalRevenue;
        vIdx = idx;
      }
    });

    // Also factor in ghost points if visible
    if (hasGhostData && viewMode === 'total') {
      ghostPoints.forEach(gp => {
        if (gp.revenue > max) max = gp.revenue;
      });
    }

    // Add 15% top buffer for smooth aesthetics and peak markers
    const paddedMax = Math.ceil((max * 1.15) / 100) * 100;
    const paddedMin = 0;

    return {
      maxVal: Math.max(paddedMax, 500),
      minVal: paddedMin,
      peakIndex: pIdx,
      valleyIndex: vIdx,
    };
  }, [trendPoints, ghostPoints, hasGhostData, viewMode]);

  // Max video views for dual axis
  const maxVideoViews = useMemo(() => {
    let max = 10000;
    trendPoints.forEach(p => {
      if (p.videoViews && p.videoViews > max) max = p.videoViews;
    });
    return Math.ceil((max * 1.15) / 10000) * 10000;
  }, [trendPoints]);

  // Coordinate conversion helpers
  const getX = (index: number, totalCount: number) => {
    if (totalCount <= 1) return padding.left + chartWidth / 2;
    return padding.left + (index / (totalCount - 1)) * chartWidth;
  };

  const getY = (val: number) => {
    const ratio = Math.max(0, Math.min(1, (val - minVal) / (maxVal - minVal || 1)));
    return padding.top + chartHeight - ratio * chartHeight;
  };

  const getViewY = (val: number) => {
    const ratio = Math.max(0, Math.min(1, val / (maxVideoViews || 1)));
    return padding.top + chartHeight - ratio * chartHeight;
  };

  // Build Smooth Cubic Bezier Curves (Cardinal Spline)
  const buildSmoothPath = (points: { x: number; y: number }[]) => {
    if (points.length === 0) return '';
    if (points.length === 1) return `M ${points[0].x} ${points[0].y}`;
    if (points.length === 2) return `M ${points[0].x} ${points[0].y} L ${points[1].x} ${points[1].y}`;

    let path = `M ${points[0].x} ${points[0].y}`;
    for (let i = 0; i < points.length - 1; i++) {
      const p0 = i > 0 ? points[i - 1] : points[i];
      const p1 = points[i];
      const p2 = points[i + 1];
      const p3 = i < points.length - 2 ? points[i + 2] : p2;

      const cp1x = p1.x + (p2.x - p0.x) / 6;
      const cp1y = p1.y + (p2.y - p0.y) / 6;
      const cp2x = p2.x - (p3.x - p1.x) / 6;
      const cp2y = p2.y - (p3.y - p1.y) / 6;

      path += ` C ${cp1x.toFixed(1)} ${cp1y.toFixed(1)}, ${cp2x.toFixed(1)} ${cp2y.toFixed(1)}, ${p2.x.toFixed(1)} ${p2.y.toFixed(1)}`;
    }
    return path;
  };

  // Main points coordinates
  const mainPointsCoords = useMemo(() => {
    return trendPoints.map((p, idx) => ({
      x: getX(idx, trendPoints.length),
      y: getY(p.totalRevenue),
      data: p,
    }));
  }, [trendPoints, maxVal, minVal]);

  // Main smooth line path
  const mainLinePath = useMemo(() => {
    return buildSmoothPath(mainPointsCoords);
  }, [mainPointsCoords]);

  // Main area fill path (closed to bottom)
  const mainAreaPath = useMemo(() => {
    if (mainPointsCoords.length < 2) return '';
    const firstX = mainPointsCoords[0].x;
    const lastX = mainPointsCoords[mainPointsCoords.length - 1].x;
    const bottomY = padding.top + chartHeight;
    return `${mainLinePath} L ${lastX} ${bottomY} L ${firstX} ${bottomY} Z`;
  }, [mainLinePath, mainPointsCoords, chartHeight]);

  // Ghost Line coordinates
  const ghostPointsCoords = useMemo(() => {
    if (!hasGhostData || ghostPoints.length === 0) return [];
    return ghostPoints.map((gp, idx) => ({
      x: getX(idx, ghostPoints.length),
      y: getY(gp.revenue),
      data: gp,
    }));
  }, [ghostPoints, hasGhostData, maxVal, minVal]);

  const ghostLinePath = useMemo(() => {
    return buildSmoothPath(ghostPointsCoords);
  }, [ghostPointsCoords]);

  // Theater layer curves if viewMode === 'theaters'
  const theaterCurves = useMemo(() => {
    if (viewMode !== 'theaters') return [];
    const keys: { key: keyof DailyRevenueDataPoint; label: string; color: string }[] = [
      { key: 'qingningRevenue', label: '青柠剧场', color: '#1A1D2E' },
      { key: 'jiuzhouRevenue', label: '九州剧场', color: '#059669' },
      { key: 'dianzhongRevenue', label: '点众微剧', color: '#6366F1' },
      { key: 'fanqieRevenue', label: '番茄剧场', color: '#F59E0B' },
      { key: 'huashengRevenue', label: '花生剧场', color: '#EC4899' },
    ];

    return keys.map(k => {
      const pts = trendPoints.map((p, idx) => ({
        x: getX(idx, trendPoints.length),
        y: getY((p[k.key] as number) || 0),
      }));
      return {
        ...k,
        path: buildSmoothPath(pts),
        points: pts,
      };
    });
  }, [viewMode, trendPoints, maxVal, minVal]);

  // Video Views Curve if viewMode === 'views'
  const viewsPointsCoords = useMemo(() => {
    if (viewMode !== 'views') return [];
    return trendPoints.map((p, idx) => ({
      x: getX(idx, trendPoints.length),
      y: getViewY(p.videoViews || 0),
      views: p.videoViews || 0,
    }));
  }, [viewMode, trendPoints, maxVideoViews]);

  const viewsLinePath = useMemo(() => {
    return buildSmoothPath(viewsPointsCoords);
  }, [viewsPointsCoords]);

  // Mouse Move Event Handler for SVG with exact CTM inverse transformation
  const handleMouseMove = (e: React.MouseEvent<SVGSVGElement>) => {
    const svg = e.currentTarget;
    if (!svg || trendPoints.length === 0) return;

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

    const total = trendPoints.length;
    if (total <= 1) {
      setHoverIndex(0);
      return;
    }

    // Step distance between points
    const step = chartWidth / (total - 1);
    let selectedIdx = Math.round((relX - padding.left) / step);
    selectedIdx = Math.max(0, Math.min(total - 1, selectedIdx));

    setHoverIndex(selectedIdx);
  };

  // Hovered item details
  const activeHoverPoint = hoverIndex !== null && hoverIndex >= 0 && hoverIndex < trendPoints.length 
    ? trendPoints[hoverIndex] 
    : null;
  const activeHoverGhost = hoverIndex !== null && hasGhostData && hoverIndex < ghostPoints.length 
    ? ghostPoints[hoverIndex] 
    : null;

  // Grid Ticks (4 levels)
  const gridTicks = [0, 0.33, 0.66, 1].map(r => {
    const val = minVal + r * (maxVal - minVal);
    return {
      val: Math.round(val),
      y: getY(val),
    };
  });

  return (
    <div className="bg-white rounded-2xl p-5 border border-black/[0.06] shadow-xs space-y-4">
      {/* 1. CHART HEADER & CONTEXT CONTROLS */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <div className="flex items-center gap-2">
            <h3 className="text-sm font-bold text-[#1A1D2E] flex items-center gap-2">
              <span>{isYesterday ? '近期收益走势 · 昨日高亮' : '高级收益趋势'}</span>
            </h3>
            {isYesterday ? (
              <span className="text-[11px] px-2 py-0.5 rounded-md bg-[#1A1D2E] text-[#DDFD00] font-medium">
                昨日上下文对比模式
              </span>
            ) : hasGhostData ? (
              <span className="text-[10px] px-2 py-0.5 rounded-md bg-slate-100 text-[#64748B] flex items-center gap-1 font-medium">
                <span className="w-2 h-0.5 bg-slate-400 border-b border-dashed inline-block" />
                <span>含上一周期参考虚线</span>
              </span>
            ) : (
              <span 
                className="text-[10px] px-2 py-0.5 rounded-md bg-amber-50 text-amber-800 border border-amber-200/60 flex items-center gap-1 font-medium"
                title={ghostUnavailableReason || '前一比较周期数据不完整'}
              >
                <AlertCircle className="w-3 h-3 text-amber-600 shrink-0" />
                <span>上一周期数据不足</span>
              </span>
            )}
          </div>
          <p className="text-xs text-[#64748B] mt-0.5">
            {isYesterday
              ? `展示昨日及前 6 日收益分布（昨日入账 ¥${trendPoints[trendPoints.length - 1]?.totalRevenue.toLocaleString('zh-CN', { minimumFractionDigits: 2 })}，${yesterdayContextLabel || '处于近期稳定位'}）`
              : '按自然日真实结算流水绘制平滑趋势，第一眼感知趋势走势，第二眼读取精准数值'}
          </p>
        </div>

        {/* View Mode Toggle */}
        <div className="flex items-center gap-1 bg-slate-100 p-0.5 rounded-xl border border-black/[0.04] text-xs">
          <button
            onClick={() => setTrendViewMode('total')}
            className={`px-3 py-1 rounded-lg text-xs font-medium transition-all ${
              viewMode === 'total'
                ? 'bg-[#1A1D2E] text-white font-semibold shadow-2xs'
                : 'text-[#64748B] hover:text-[#1A1D2E]'
            }`}
          >
            {theaterFilter === 'all' ? '总收益走势' : '剧场专属走势'}
          </button>

          {theaterFilter === 'all' && (
            <button
              onClick={() => setTrendViewMode('theaters')}
              className={`px-3 py-1 rounded-lg text-xs font-medium transition-all ${
                viewMode === 'theaters'
                  ? 'bg-[#1A1D2E] text-white font-semibold shadow-2xs'
                  : 'text-[#64748B] hover:text-[#1A1D2E]'
              }`}
            >
              五大剧场分层
            </button>
          )}

          <button
            onClick={() => setTrendViewMode('views')}
            className={`px-3 py-1 rounded-lg text-xs font-medium transition-all ${
              viewMode === 'views'
                ? 'bg-[#1A1D2E] text-white font-semibold shadow-2xs'
                : 'text-[#64748B] hover:text-[#1A1D2E]'
            }`}
          >
            叠加青柠播放量
          </button>
        </div>
      </div>

      {/* 2. THE SVG TREND CANVAS CONTAINER */}
      <div className="relative w-full overflow-hidden select-none bg-radial from-slate-50/60 to-white rounded-xl border border-black/[0.04]">
        <svg
          ref={svgRef}
          viewBox={`0 0 ${svgWidth} ${svgHeight}`}
          className="w-full h-auto max-h-[260px] cursor-crosshair overflow-visible"
          onMouseMove={handleMouseMove}
          onMouseLeave={() => setHoverIndex(null)}
        >
          <defs>
            {/* Area gradient for main curve */}
            <linearGradient id="mainAreaGrad" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="#1A1D2E" stopOpacity="0.16" />
              <stop offset="60%" stopColor="#1A1D2E" stopOpacity="0.04" />
              <stop offset="100%" stopColor="#1A1D2E" stopOpacity="0.0" />
            </linearGradient>

            {/* Video views green area gradient */}
            <linearGradient id="viewsAreaGrad" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="#059669" stopOpacity="0.12" />
              <stop offset="100%" stopColor="#059669" stopOpacity="0.0" />
            </linearGradient>
          </defs>

          {/* Background Grid Lines & Left Currency Ticks */}
          {gridTicks.map((tick, i) => (
            <g key={i}>
              <line
                x1={padding.left}
                y1={tick.y}
                x2={svgWidth - padding.right}
                y2={tick.y}
                stroke="#E2E8F0"
                strokeWidth="1"
                strokeDasharray={i === 0 ? 'none' : '3 3'}
              />
              <text
                x={padding.left - 8}
                y={tick.y + 3}
                textAnchor="end"
                fontSize="10"
                fill="#94A3B8"
                fontFamily="monospace"
              >
                ¥{tick.val >= 1000 ? `${(tick.val / 1000).toFixed(1)}k` : tick.val}
              </text>
            </g>
          ))}

          {/* Secondary Y-axis for Video Views if mode === 'views' */}
          {viewMode === 'views' && (
            <g>
              <text
                x={svgWidth - padding.right + 6}
                y={padding.top + 3}
                textAnchor="start"
                fontSize="9"
                fill="#059669"
                fontFamily="monospace"
                fontWeight="bold"
              >
                {(maxVideoViews / 10000).toFixed(0)}万次
              </text>
              <text
                x={svgWidth - padding.right + 6}
                y={padding.top + chartHeight + 3}
                textAnchor="start"
                fontSize="9"
                fill="#94A3B8"
                fontFamily="monospace"
              >
                0次
              </text>
            </g>
          )}

          {/* Area Fill Gradient (Main Line) */}
          {viewMode === 'total' && mainAreaPath && (
            <path
              d={mainAreaPath}
              fill="url(#mainAreaGrad)"
              className="transition-all duration-300 pointer-events-none"
            />
          )}

          {/* Video Views Line & Area if mode === 'views' */}
          {viewMode === 'views' && viewsLinePath && (
            <g className="pointer-events-none">
              <path
                d={viewsLinePath}
                fill="none"
                stroke="#059669"
                strokeWidth="2"
                strokeDasharray="4 2"
                opacity="0.85"
              />
            </g>
          )}

          {/* Ghost Reference Line (Previous Period) */}
          {viewMode === 'total' && hasGhostData && ghostLinePath && (
            <g className="pointer-events-none">
              <path
                d={ghostLinePath}
                fill="none"
                stroke="#94A3B8"
                strokeWidth="1.75"
                strokeDasharray="4 4"
                opacity="0.65"
              />
            </g>
          )}

          {/* Theater Layer Curves if mode === 'theaters' */}
          {viewMode === 'theaters' && (
            <g className="pointer-events-none">
              {theaterCurves.map(tc => (
                <path
                  key={tc.key}
                  d={tc.path}
                  fill="none"
                  stroke={tc.color}
                  strokeWidth={tc.key === 'qingningRevenue' ? '2.5' : '1.75'}
                  opacity={tc.key === 'qingningRevenue' ? '1' : '0.8'}
                />
              ))}
            </g>
          )}

          {/* Main Active Line (Smooth Curve) */}
          {viewMode !== 'theaters' && mainLinePath && (
            <path
              d={mainLinePath}
              fill="none"
              stroke="#1A1D2E"
              strokeWidth="2.5"
              strokeLinecap="round"
              strokeLinejoin="round"
              opacity={isYesterday ? '0.75' : '1'}
              className="transition-all duration-200 pointer-events-none"
            />
          )}

          {/* Peak & Valley Markers (Restrained subtle badges) */}
          {viewMode === 'total' && !isYesterday && trendPoints.length > 3 && (
            <g className="pointer-events-none">
              {/* Peak */}
              {mainPointsCoords[peakIndex] && (
                <g transform={`translate(${mainPointsCoords[peakIndex].x}, ${mainPointsCoords[peakIndex].y - 8})`}>
                  <circle r="3.5" fill="#1A1D2E" />
                  <rect
                    x="-24"
                    y="-18"
                    width="48"
                    height="15"
                    rx="4"
                    fill="#1A1D2E"
                    opacity="0.9"
                  />
                  <text
                    x="0"
                    y="-8"
                    textAnchor="middle"
                    fill="#DDFD00"
                    fontSize="9"
                    fontWeight="bold"
                    fontFamily="monospace"
                  >
                    ¥{trendPoints[peakIndex].totalRevenue.toFixed(0)} 峰
                  </text>
                </g>
              )}
            </g>
          )}

          {/* Yesterday Special Highlight on the Last Node */}
          {isYesterday && mainPointsCoords.length > 0 && (
            <g 
              transform={`translate(${mainPointsCoords[mainPointsCoords.length - 1].x}, ${mainPointsCoords[mainPointsCoords.length - 1].y})`}
              className="pointer-events-none"
            >
              <circle r="9" fill="#1A1D2E" opacity="0.15" />
              <circle r="6" fill="#1A1D2E" stroke="#DDFD00" strokeWidth="2.5" />
              <rect
                x="-38"
                y="-30"
                width="76"
                height="20"
                rx="6"
                fill="#1A1D2E"
                stroke="#DDFD00"
                strokeWidth="1"
              />
              <text
                x="0"
                y="-16"
                textAnchor="middle"
                fill="#DDFD00"
                fontSize="10"
                fontWeight="bold"
                fontFamily="monospace"
              >
                昨日 ¥{trendPoints[trendPoints.length - 1].totalRevenue.toFixed(0)}
              </text>
            </g>
          )}

          {/* Interactive Active Column Indicator Band */}
          {hoverIndex !== null && mainPointsCoords[hoverIndex] && trendPoints.length > 1 && (
            <rect
              x={
                hoverIndex === 0
                  ? padding.left - 12
                  : mainPointsCoords[hoverIndex].x - (chartWidth / (trendPoints.length - 1)) / 2
              }
              y={padding.top}
              width={
                hoverIndex === 0 || hoverIndex === trendPoints.length - 1
                  ? (chartWidth / (trendPoints.length - 1)) / 2 + 12
                  : chartWidth / (trendPoints.length - 1)
              }
              height={chartHeight}
              fill="#1A1D2E"
              fillOpacity="0.04"
              rx="6"
              className="pointer-events-none"
            />
          )}

          {/* Interactive Hover Guide Crosshair & Dot */}
          {hoverIndex !== null && mainPointsCoords[hoverIndex] && (
            <g className="pointer-events-none">
              {/* Vertical Guide Line */}
              <line
                x1={mainPointsCoords[hoverIndex].x}
                y1={padding.top}
                x2={mainPointsCoords[hoverIndex].x}
                y2={padding.top + chartHeight}
                stroke="#1A1D2E"
                strokeWidth="1.2"
                strokeDasharray="3 3"
                opacity="0.6"
              />

              {/* Ghost Point Marker on crosshair */}
              {hasGhostData && ghostPointsCoords[hoverIndex] && (
                <circle
                  cx={ghostPointsCoords[hoverIndex].x}
                  cy={ghostPointsCoords[hoverIndex].y}
                  r="3.5"
                  fill="#94A3B8"
                  stroke="#FFFFFF"
                  strokeWidth="1.5"
                />
              )}

              {/* Main Point Marker on crosshair */}
              <circle
                cx={mainPointsCoords[hoverIndex].x}
                cy={mainPointsCoords[hoverIndex].y}
                r="5"
                fill="#DDFD00"
                stroke="#1A1D2E"
                strokeWidth="2.5"
              />
            </g>
          )}

          {/* X-Axis Date Labels (Only key readable dates, avoid crowding) */}
          {mainPointsCoords.map((pt, idx) => {
            const total = trendPoints.length;
            // Filter labels on dense datasets
            const shouldShow = total <= 8 
              || idx === 0 
              || idx === total - 1 
              || (total <= 16 && idx % 2 === 0) 
              || (total > 16 && idx % 4 === 0);

            if (!shouldShow) return null;

            const isLast = idx === total - 1;
            const isHovered = hoverIndex === idx;

            return (
              <text
                key={pt.data.date}
                x={pt.x}
                y={padding.top + chartHeight + 18}
                textAnchor="middle"
                fontSize={isHovered || (isYesterday && isLast) ? '11' : '10'}
                fontWeight={isHovered || (isYesterday && isLast) ? 'bold' : 'normal'}
                fill={isHovered || (isYesterday && isLast) ? '#1A1D2E' : '#64748B'}
                fontFamily="monospace"
              >
                {isYesterday && isLast ? '昨日' : pt.data.dayLabel}
              </text>
            );
          })}
        </svg>

        {/* 3. Viewport-level tooltip, free of chart-container clipping */}
        {activeHoverPoint && hoverIndex !== null && mainPointsCoords[hoverIndex] && (
          <ViewportFloatingLayer
            getAnchorRect={() => svgPointAnchor(svgRef.current, mainPointsCoords[hoverIndex].x, mainPointsCoords[hoverIndex].y, svgWidth, svgHeight)}
          >
            <div className="bg-[#1A1D2E]/95 backdrop-blur-xs text-white p-3 rounded-xl shadow-xl text-xs space-y-1.5 border border-white/10 transition-all duration-75 min-w-[210px] max-w-[calc(100vw-1rem)]">
              <div className="flex items-center justify-between border-b border-white/10 pb-1 text-[#DDFD00]">
              <span className="font-mono font-bold">📅 {activeHoverPoint.date}</span>
              <span className="font-mono text-sm font-black">
                ¥{activeHoverPoint.totalRevenue.toLocaleString('zh-CN', { minimumFractionDigits: 2 })}
              </span>
            </div>

            {/* Ghost Comparison if active */}
            {activeHoverGhost && (
              <div className="flex items-center justify-between text-[10px] text-slate-300 bg-white/5 px-1.5 py-0.5 rounded-md">
                <span>上一周期同日 ({activeHoverGhost.date}):</span>
                <span className="font-mono text-slate-200">
                  ¥{activeHoverGhost.revenue.toFixed(2)} 
                  <strong className={`ml-1 ${activeHoverPoint.totalRevenue >= activeHoverGhost.revenue ? 'text-emerald-400' : 'text-rose-400'}`}>
                    ({activeHoverPoint.totalRevenue >= activeHoverGhost.revenue ? '+' : ''}
                    {(((activeHoverPoint.totalRevenue - activeHoverGhost.revenue) / (activeHoverGhost.revenue || 1)) * 100).toFixed(1)}%)
                  </strong>
                </span>
              </div>
            )}

            {/* Theater Distribution Breakdown */}
            <div className="space-y-0.5 text-[10px] text-slate-300 pt-0.5">
              <div className="flex justify-between items-center">
                <span className="flex items-center gap-1">
                  <span className="w-2 h-2 rounded-xs bg-[#DDFD00]" />
                  <span>青柠剧场:</span>
                </span>
                <span className="font-mono text-white">¥{activeHoverPoint.qingningRevenue.toFixed(2)}</span>
              </div>
              <div className="flex justify-between items-center">
                <span className="flex items-center gap-1">
                  <span className="w-2 h-2 rounded-xs bg-emerald-400" />
                  <span>九州剧场:</span>
                </span>
                <span className="font-mono text-white">¥{activeHoverPoint.jiuzhouRevenue.toFixed(2)}</span>
              </div>
              <div className="flex justify-between items-center">
                <span className="flex items-center gap-1">
                  <span className="w-2 h-2 rounded-xs bg-indigo-400" />
                  <span>点众微剧:</span>
                </span>
                <span className="font-mono text-white">¥{activeHoverPoint.dianzhongRevenue.toFixed(2)}</span>
              </div>
              <div className="flex justify-between items-center">
                <span className="flex items-center gap-1">
                  <span className="w-2 h-2 rounded-xs bg-amber-400" />
                  <span>番茄 / 花生:</span>
                </span>
                <span className="font-mono text-white">
                  ¥{(activeHoverPoint.fanqieRevenue + activeHoverPoint.huashengRevenue).toFixed(2)}
                </span>
              </div>

              {activeHoverPoint.videoViews && (
                <div className="flex justify-between items-center pt-1 border-t border-white/10 text-emerald-300 font-medium">
                  <span>青柠播放量:</span>
                  <span className="font-mono">{(activeHoverPoint.videoViews / 10000).toFixed(1)}万次</span>
                </div>
              )}
            </div>
            </div>
          </ViewportFloatingLayer>
        )}
      </div>

      {/* 4. REFINED LEGEND & ANNOTATIONS */}
      <div className="flex flex-wrap items-center justify-between gap-3 text-xs text-[#64748B] pt-1">
        <div className="flex flex-wrap items-center gap-4 text-[11px]">
          {viewMode === 'total' && (
            <>
              <span className="flex items-center gap-1.5 font-medium text-[#1A1D2E]">
                <span className="w-3 h-1 rounded-full bg-[#1A1D2E]" />
                <span>当前周期主走势</span>
              </span>
              {hasGhostData ? (
                <span className="flex items-center gap-1.5 font-medium text-slate-500">
                  <span className="w-3 h-0.5 border-b border-dashed border-slate-400" />
                  <span>上一周期对比参考</span>
                </span>
              ) : (
                <span className="text-slate-400 italic">
                  * 上一周期历史数据不足，已克制隐藏假参考线
                </span>
              )}
            </>
          )}

          {viewMode === 'theaters' && (
            <>
              <span className="flex items-center gap-1.5">
                <span className="w-2.5 h-2.5 rounded-xs bg-[#1A1D2E]" />
                <span>青柠</span>
              </span>
              <span className="flex items-center gap-1.5">
                <span className="w-2.5 h-2.5 rounded-xs bg-[#059669]" />
                <span>九州</span>
              </span>
              <span className="flex items-center gap-1.5">
                <span className="w-2.5 h-2.5 rounded-xs bg-[#6366F1]" />
                <span>点众</span>
              </span>
              <span className="flex items-center gap-1.5">
                <span className="w-2.5 h-2.5 rounded-xs bg-[#F59E0B]" />
                <span>番茄</span>
              </span>
              <span className="flex items-center gap-1.5">
                <span className="w-2.5 h-2.5 rounded-xs bg-[#EC4899]" />
                <span>花生(推测)</span>
              </span>
            </>
          )}

          {viewMode === 'views' && (
            <>
              <span className="flex items-center gap-1.5 font-medium text-[#1A1D2E]">
                <span className="w-3 h-1 rounded-full bg-[#1A1D2E]" />
                <span>结算流水 (¥)</span>
              </span>
              <span className="flex items-center gap-1.5 font-medium text-emerald-700">
                <span className="w-3 h-0.5 border-b border-dashed border-emerald-600" />
                <span>青柠视频播放量 (万次)</span>
              </span>
            </>
          )}
        </div>

        <div className="text-[11px] text-slate-400 font-mono">
          最高 ¥{maxVal.toLocaleString()} · 极低噪点贝塞尔平滑
        </div>
      </div>
    </div>
  );
};
