import React, { useState, useMemo, useRef, useEffect } from 'react';
import { TimeRangeFilter, TheaterFilter, AnalyticsTopTab } from '../../analyticsTypes';
import { 
  calculatePlatformVideosAnalytics, 
  AggregatedPlatformVideo, 
  VideoAnalysisResult 
} from '../../utils/videoEngine';
import { VideoDrawer } from './VideoDrawer';
import { VideoLinkModal } from './VideoLinkModal';
import { 
  Search, 
  ArrowUpDown, 
  CheckCircle2, 
  Clock, 
  ChevronRight, 
  ChevronLeft, 
  AlertCircle, 
  Film 
} from 'lucide-react';
import { StatusBadge } from './common/StatusBadge';
import { HelpTooltip, ModuleInfoPopover } from './common/HelpTooltip';
import { confirmV2RevenueVideoLink, loadV2RevenueVideoCandidates, type V2RevenueVideoCandidate } from '../../api/v2Revenue';

interface VideoModuleProps {
  timeRange: TimeRangeFilter;
  selectedTheater: TheaterFilter;
  customStartDate?: string;
  customEndDate?: string;
  initialVideoId?: string;
  autoOpenDrawerForVideoId?: string;
  onNavigateToTab?: (tab: AnalyticsTopTab, entityId?: string) => void;
  onLinkVideo?: (videoId: string, materialId: string, clipName: string) => void;
  analysisOverride?: VideoAnalysisResult;
}

type SortField = 'revenue' | 'videoViews' | 'dramaViews' | 'rpm' | 'receptionStrength' | 'date';

const PAGE_SIZE = 20;

export const VideoModule: React.FC<VideoModuleProps> = ({
  timeRange,
  selectedTheater,
  customStartDate,
  customEndDate,
  initialVideoId,
  autoOpenDrawerForVideoId,
  onNavigateToTab,
  onLinkVideo,
  analysisOverride,
}) => {
  // Session link overrides state
  const [linkOverrides, setLinkOverrides] = useState<
    Record<string, { isLinked: boolean; clipName: string; materialId: string; materialName: string }>
  >({});

  // Active filters inside Video tab
  const [searchQuery, setSearchQuery] = useState<string>('');
  const [accountFilter, setAccountFilter] = useState<string>('all');
  const [dramaFilter, setDramaFilter] = useState<string>('all');
  const [associationFilter, setAssociationFilter] = useState<'all' | 'linked' | 'unlinked'>('all');
  const [sortField, setSortField] = useState<SortField>('revenue');
  const [sortAsc, setSortAsc] = useState<boolean>(false);

  // Pagination state
  const [currentPage, setCurrentPage] = useState<number>(1);

  // Interaction states
  const [hoveredVideo, setHoveredVideo] = useState<AggregatedPlatformVideo | null>(null);
  const [selectedVideo, setSelectedVideo] = useState<AggregatedPlatformVideo | null>(null);
  const [isDrawerOpen, setIsDrawerOpen] = useState<boolean>(false);
  const [linkingVideo, setLinkingVideo] = useState<AggregatedPlatformVideo | null>(null);
  const [isLinkModalOpen, setIsLinkModalOpen] = useState<boolean>(false);
  const [linkCandidates, setLinkCandidates] = useState<V2RevenueVideoCandidate[]>([]);
  const [loadingCandidates, setLoadingCandidates] = useState(false);
  const [linkError, setLinkError] = useState('');

  const tableRef = useRef<HTMLDivElement>(null);

  // 1. Calculate aggregated dataset based on global filters
  const analysisResult: VideoAnalysisResult = useMemo(() => {
    if (analysisOverride) return analysisOverride;
    return calculatePlatformVideosAnalytics(timeRange, selectedTheater, linkOverrides, customStartDate, customEndDate);
  }, [timeRange, selectedTheater, linkOverrides, customStartDate, customEndDate, analysisOverride]);

  // Handle auto open drawer / navigate from external tabs
  useEffect(() => {
    const targetId = autoOpenDrawerForVideoId || initialVideoId;
    if (targetId && analysisResult.videos.length > 0) {
      const found = analysisResult.videos.find((v) => v.id === targetId);
      if (found) {
        setSelectedVideo(found);
        if (autoOpenDrawerForVideoId) {
          setIsDrawerOpen(true);
        }
      }
    }
  }, [autoOpenDrawerForVideoId, initialVideoId, analysisResult.videos]);

  // Reset page to 1 whenever filters or sorting change
  useEffect(() => {
    setCurrentPage(1);
  }, [searchQuery, accountFilter, dramaFilter, associationFilter, sortField, sortAsc]);

  // 2. Filter options lists
  const availableAccounts = useMemo(() => {
    const map = new Map<string, string>();
    analysisResult.videos.forEach((v) => map.set(v.accountId, v.accountName));
    return Array.from(map.entries()).map(([id, name]) => ({ id, name }));
  }, [analysisResult.videos]);

  const availableDramas = useMemo(() => {
    const map = new Map<string, string>();
    analysisResult.videos.forEach((v) => map.set(v.dramaId, v.dramaName));
    return Array.from(map.entries()).map(([id, name]) => ({ id, name }));
  }, [analysisResult.videos]);

  // 3. Filtered videos for UI
  const filteredVideos = useMemo(() => {
    return analysisResult.videos.filter((v) => {
      // Search query
      if (searchQuery.trim()) {
        const q = searchQuery.toLowerCase().trim();
        const matchId = v.id.toLowerCase().includes(q);
        const matchAcc = v.accountName.toLowerCase().includes(q);
        const matchDrama = v.dramaName.toLowerCase().includes(q);
        const matchClip = v.linkedClipName ? v.linkedClipName.toLowerCase().includes(q) : false;
        const matchBatch = v.candidateBatch.toLowerCase().includes(q);
        if (!matchId && !matchAcc && !matchDrama && !matchClip && !matchBatch) return false;
      }

      // Account filter
      if (accountFilter !== 'all' && v.accountId !== accountFilter) return false;

      // Drama filter
      if (dramaFilter !== 'all' && v.dramaId !== dramaFilter) return false;

      // Association status filter
      if (associationFilter === 'linked' && !v.isLinked) return false;
      if (associationFilter === 'unlinked' && v.isLinked) return false;

      return true;
    });
  }, [analysisResult.videos, searchQuery, accountFilter, dramaFilter, associationFilter]);

  // 4. Sorted videos for Table
  const sortedVideos = useMemo(() => {
    return [...filteredVideos].sort((a, b) => {
      let comparison = 0;
      if (sortField === 'revenue') comparison = a.periodRevenue - b.periodRevenue;
      else if (sortField === 'videoViews') comparison = a.periodVideoViews - b.periodVideoViews;
      else if (sortField === 'dramaViews') comparison = a.periodDramaViews - b.periodDramaViews;
      else if (sortField === 'rpm') comparison = a.rpm - b.rpm;
      else if (sortField === 'receptionStrength') comparison = a.receptionStrength - b.receptionStrength;
      else if (sortField === 'date') comparison = a.firstObservedDate.localeCompare(b.firstObservedDate);
      return sortAsc ? comparison : -comparison;
    });
  }, [filteredVideos, sortField, sortAsc]);

  // 5. Paginated videos
  const totalPages = Math.max(1, Math.ceil(sortedVideos.length / PAGE_SIZE));
  const paginatedVideos = useMemo(() => {
    const start = (currentPage - 1) * PAGE_SIZE;
    return sortedVideos.slice(start, start + PAGE_SIZE);
  }, [sortedVideos, currentPage]);

  // Handle select video (from scatter bubble or table row)
  const handleSelectVideo = (video: AggregatedPlatformVideo) => {
    setSelectedVideo(video);
    setIsDrawerOpen(true);

    // Locate the video in sortedVideos, navigate table to the corresponding page
    const videoIndex = sortedVideos.findIndex((v) => v.id === video.id);
    if (videoIndex !== -1) {
      const targetPage = Math.floor(videoIndex / PAGE_SIZE) + 1;
      if (targetPage !== currentPage) {
        setCurrentPage(targetPage);
      }
    }
  };

  // Handle open link modal
  const handleOpenLinkModal = (video: AggregatedPlatformVideo) => {
    setLinkingVideo(video);
    setIsLinkModalOpen(true);
    setLoadingCandidates(true); setLinkError(''); setLinkCandidates([]);
    void loadV2RevenueVideoCandidates(video.accountId, video.id)
      .then((result) => setLinkCandidates(result.candidates))
      .catch((error: unknown) => setLinkError(error instanceof Error ? error.message : '读取候选原素材失败'))
      .finally(() => setLoadingCandidates(false));
  };

  // Handle confirmed link
  const handleConfirmLink = (candidate: V2RevenueVideoCandidate, note: string) => {
    if (!linkingVideo) return;
    void confirmV2RevenueVideoLink({ account_id: linkingVideo.accountId, video_id: linkingVideo.id,
      production_task_id: candidate.production_task_id, production_video_task_id: candidate.production_video_task_id,
      source_material_id: candidate.source_material_id, note })
      .then(() => {
    setLinkOverrides((prev) => ({
      ...prev,
      [linkingVideo.id]: {
        isLinked: true,
        clipName: candidate.file_name || candidate.original_name,
        materialId: candidate.source_material_id,
        materialName: candidate.original_name || candidate.file_name,
      },
    }));
    if (onLinkVideo) {
      onLinkVideo(linkingVideo.id, candidate.source_material_id, candidate.file_name || candidate.original_name);
    }
      setIsLinkModalOpen(false);
    })
      .catch((error: unknown) => setLinkError(error instanceof Error ? error.message : '保存人工确认关联失败'));
  };

  const handleSort = (field: SortField) => {
    if (sortField === field) {
      setSortAsc(!sortAsc);
    } else {
      setSortField(field);
      setSortAsc(false);
    }
  };

  // Counts for status pills
  const totalCount = analysisResult.videos.length;
  const linkedCount = analysisResult.videos.filter((v) => v.isLinked).length;
  const unlinkedCount = analysisResult.videos.filter((v) => !v.isLinked).length;

  // Scatter plot coordinate math
  const maxPlotViews = Math.max(analysisResult.maxViews, 10000);
  const maxPlotRevenue = Math.max(analysisResult.maxRevenue, 100);

  const plotP75X = (analysisResult.p75Views / maxPlotViews) * 100;
  const plotP75Y = (analysisResult.p75Revenue / maxPlotRevenue) * 100;

  // Page index range text
  const startItemIndex = sortedVideos.length === 0 ? 0 : (currentPage - 1) * PAGE_SIZE + 1;
  const endItemIndex = Math.min(currentPage * PAGE_SIZE, sortedVideos.length);

  // If theater doesn't have video level data, render empty state
  if (!analysisResult.hasVideoLevelData) {
    return (
      <div
        id="video-module-unsupported-state"
        className="p-12 rounded-3xl bg-white border border-black/10 text-center space-y-4 shadow-xs"
      >
        <div className="w-14 h-14 rounded-2xl bg-amber-50 text-amber-700 mx-auto flex items-center justify-center border border-amber-200">
          <AlertCircle className="w-7 h-7" />
        </div>
        <div className="max-w-md mx-auto space-y-1.5">
          <h3 className="text-base font-bold text-[#1A1D2E]">
            {analysisResult.unsupportedReason || '当前剧场未提供平台视频级数据'}
          </h3>
          <p className="text-xs text-[#64748B] leading-relaxed">
            当前仅青柠剧场支持推广视频 ID 级别的日结算明细回传与归因。所选剧场暂未开放平台视频级数据接口，请在顶部切换至「全部剧场」或「青柠剧场」查看。
          </p>
        </div>
      </div>
    );
  }

  return (
    <div id="video-analytics-page" className="space-y-6 animate-in fade-in duration-200">
      
      {/* 1. TOP SCATTER PLOT (四象限分布) */}
      <div 
        id="video-scatter-plot-card"
        className="bg-white rounded-3xl p-6 border border-black/10 shadow-xs space-y-4"
      >
        {/* Scatter Header */}
        <div className="flex flex-wrap items-center justify-between gap-4">
          <div className="space-y-1">
            <div className="flex items-center gap-2">
              <Film className="w-5 h-5 text-indigo-600 shrink-0" />
              <h3 className="text-sm font-bold text-[#1A1D2E] tracking-tight">
                青柠平台推广视频表现分布图 (Scatter Plot)
              </h3>
              <span className="text-[11px] px-2.5 py-0.5 rounded-full bg-slate-100 text-[#64748B] font-mono font-medium">
                {analysisResult.totalPlatformVideosCount} 条样本
              </span>
              <ModuleInfoPopover
                title="散点分布图说明"
                content={
                  <>
                    <p>• <strong>横轴</strong>：所选周期内各平台推广视频的总播放量。</p>
                    <p>• <strong>纵轴</strong>：所选周期内各平台推广视频产生的总收益。</p>
                    <p>• <strong>气泡大小</strong>：正比于剧集承接播放量（比率）。</p>
                    <p>• <strong>虚线参考线</strong>：P75 分位数，划分四象限特征。</p>
                  </>
                }
              />
            </div>
            <p className="text-xs text-[#64748B]">
              横轴：视频播放量 · 纵轴：{timeRange === 'yesterday' ? '当日收益' : '周期收益'} · 气泡大小：剧集承接播放量 · 快速定位高转化与高播放特征视频
            </p>
          </div>

          {/* Top Right Legend Items */}
          <div className="flex items-center gap-4 text-xs text-[#64748B]">
            <div className="flex items-center gap-1.5">
              <span className="w-2.5 h-2.5 rounded-full bg-[#10B981]"></span>
              <span>爆款转化</span>
            </div>
            <div className="flex items-center gap-1.5">
              <span className="w-2.5 h-2.5 rounded-full bg-[#3B82F6]"></span>
              <span>高曝光转化</span>
            </div>
            <div className="flex items-center gap-1.5">
              <span className="w-2.5 h-2.5 rounded-full bg-[#64748B]"></span>
              <span>常规视频</span>
            </div>
          </div>
        </div>

        {/* Scatter Canvas Stage */}
        <div className="relative w-full h-[360px] bg-slate-50/60 rounded-2xl border border-black/[0.06] p-6 overflow-hidden select-none">
          
          {/* Axis Grid Background Lines */}
          <div className="absolute inset-0 pointer-events-none">
            {/* Horizontal Grid */}
            <div className="w-full h-1/4 border-b border-black/[0.03]" />
            <div className="w-full h-1/4 border-b border-black/[0.03]" />
            <div className="w-full h-1/4 border-b border-black/[0.03]" />
          </div>

          {/* Quadrant P75 Reference Lines */}
          {plotP75X > 5 && plotP75X < 95 && (
            <div 
              className="absolute top-0 bottom-6 border-l border-dashed border-slate-300 pointer-events-none"
              style={{ left: `${Math.min(90, Math.max(10, plotP75X))}%` }}
            >
              <span className="absolute top-2 left-1.5 text-[9px] font-mono text-slate-400 bg-white/80 px-1 rounded">
                播放 P75 ({(analysisResult.p75Views / 10000).toFixed(1)}w)
              </span>
            </div>
          )}

          {plotP75Y > 5 && plotP75Y < 95 && (
            <div 
              className="absolute left-10 right-0 border-t border-dashed border-slate-300 pointer-events-none"
              style={{ bottom: `${Math.min(90, Math.max(10, plotP75Y))}%` }}
            >
              <span className="absolute right-3 -top-4 text-[9px] font-mono text-slate-400 bg-white/80 px-1 rounded">
                收益 P75 (¥{analysisResult.p75Revenue.toFixed(0)})
              </span>
            </div>
          )}

          {/* Scatter Bubbles Layer */}
          <div className="absolute inset-x-10 top-6 bottom-8">
            {analysisResult.videos.map((v) => {
              // Coordinate math in %
              const posX = (v.periodVideoViews / maxPlotViews) * 100;
              const posY = (v.periodRevenue / maxPlotRevenue) * 100;

              // Size mapping: 12px to 32px based on drama views
              const size = Math.max(12, Math.min(32, 12 + (v.periodDramaViews / (maxPlotViews * 1.2 || 1)) * 20));

              // Bubble color category
              const isTopRevenue = v.periodRevenue >= analysisResult.p75Revenue;
              const isTopViews = v.periodVideoViews >= analysisResult.p75Views;
              
              let bubbleBg = 'bg-slate-400/70 border-slate-500';
              if (isTopRevenue && isTopViews) bubbleBg = 'bg-emerald-500/80 border-emerald-600 shadow-sm';
              else if (isTopRevenue) bubbleBg = 'bg-indigo-500/80 border-indigo-600';
              else if (isTopViews) bubbleBg = 'bg-blue-500/80 border-blue-600';

              const isHovered = hoveredVideo?.id === v.id;
              const isSelected = selectedVideo?.id === v.id;

              return (
                <div
                  key={v.id}
                  id={`scatter-bubble-${v.id}`}
                  onClick={() => handleSelectVideo(v)}
                  onMouseEnter={() => setHoveredVideo(v)}
                  onMouseLeave={() => setHoveredVideo(null)}
                  style={{
                    left: `${Math.min(98, Math.max(2, posX))}%`,
                    bottom: `${Math.min(98, Math.max(2, posY))}%`,
                    width: `${size}px`,
                    height: `${size}px`,
                  }}
                  className={`absolute -translate-x-1/2 translate-y-1/2 rounded-full border cursor-pointer transition-all duration-150 flex items-center justify-center ${bubbleBg} ${
                    isHovered || isSelected 
                      ? 'scale-150 z-30 ring-4 ring-[#DDFD00]/80 shadow-lg' 
                      : 'hover:scale-125 z-10'
                  }`}
                >
                  {isTopRevenue && (
                    <span className="text-[8px] font-bold text-white font-mono leading-none">
                      ¥
                    </span>
                  )}
                </div>
              );
            })}
          </div>

          {/* Y Axis Label */}
          <div className="absolute left-2 top-4 bottom-8 flex flex-col justify-between text-[10px] font-mono text-slate-400 pointer-events-none">
            <span>¥{Math.round(maxPlotRevenue)}</span>
            <span>¥{Math.round(maxPlotRevenue / 2)}</span>
            <span>¥0</span>
          </div>

          {/* X Axis Label */}
          <div className="absolute bottom-1 inset-x-10 flex justify-between text-[10px] font-mono text-slate-400 pointer-events-none">
            <span>0</span>
            <span>{(maxPlotViews / 20000).toFixed(1)} 万播放</span>
            <span>{(maxPlotViews / 10000).toFixed(1)} 万播放</span>
          </div>

          {/* Hover Floating Details Card on Scatter Canvas */}
          {hoveredVideo && (
            <div 
              className="absolute top-4 right-4 z-40 p-3.5 bg-[#1A1D2E]/95 text-white rounded-2xl shadow-xl border border-white/10 w-72 space-y-2 pointer-events-none backdrop-blur-md animate-in fade-in zoom-in-95 duration-100"
            >
              <div className="flex items-center justify-between border-b border-white/10 pb-1.5">
                <span className="font-mono text-[10px] text-[#DDFD00] font-bold">
                  {hoveredVideo.id}
                </span>
                <span className="text-[10px] text-slate-300">
                  {hoveredVideo.firstObservedShort} 首次观测
                </span>
              </div>

              <div className="space-y-0.5 text-[11px]">
                <div className="font-bold text-white text-xs truncate">
                  {hoveredVideo.dramaName}
                </div>
                <div className="text-slate-300 flex items-center justify-between">
                  <span>账号: {hoveredVideo.accountName}</span>
                  <span>批次: {hoveredVideo.candidateBatch.slice(0, 5)}</span>
                </div>
              </div>

              <div className="grid grid-cols-2 gap-2 pt-1.5 border-t border-white/10 text-[11px]">
                <div>
                  <span className="text-slate-400 block text-[10px]">周期收益</span>
                  <strong className="text-emerald-400 font-mono font-bold">
                    ¥{hoveredVideo.periodRevenue.toFixed(2)}
                  </strong>
                </div>
                <div>
                  <span className="text-slate-400 block text-[10px]">视频播放</span>
                  <span className="text-slate-200 font-mono">
                    {hoveredVideo.periodVideoViews.toLocaleString()}
                  </span>
                </div>
                <div>
                  <span className="text-slate-400 block text-[10px]">承接强度</span>
                  <span className="text-indigo-300 font-mono font-medium">
                    {hoveredVideo.receptionStrength.toFixed(2)}
                  </span>
                </div>
                <div>
                  <span className="text-slate-400 block text-[10px]">千次播放收益</span>
                  <span className="text-amber-300 font-mono font-medium">
                    ¥{hoveredVideo.rpm.toFixed(2)}
                  </span>
                </div>
              </div>

              <div className="pt-1.5 border-t border-white/10 text-[10px] flex items-center justify-between">
                <span className="text-slate-400">成片关联:</span>
                {hoveredVideo.isLinked ? (
                  <span className="text-emerald-400 font-medium">
                    已关联 · {hoveredVideo.linkedClipName}
                  </span>
                ) : (
                  <span className="text-amber-400 font-medium">
                    待核对 ({hoveredVideo.candidateBatch})
                  </span>
                )}
              </div>
            </div>
          )}

        </div>
      </div>

      {/* 2. BOTTOM TABLE: Platform Video Inventory (视频列表与分页) */}
      <div 
        ref={tableRef}
        id="video-table-card"
        className="bg-white rounded-3xl p-6 border border-black/10 shadow-xs space-y-4"
      >
        {/* Table Filters Header */}
        <div className="flex flex-wrap items-center justify-between gap-3 pb-3 border-b border-black/[0.06]">
          <div className="flex items-center gap-3 flex-wrap">
            {/* Search Input */}
            <div className="relative">
              <Search className="w-4 h-4 text-slate-400 absolute left-3 top-1/2 -translate-y-1/2" />
              <input
                type="text"
                placeholder="搜索视频 ID / 剧集 / 账号 / 成片..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="pl-9 pr-3 py-1.5 bg-slate-50 border border-black/[0.08] rounded-xl text-xs text-[#1A1D2E] outline-none w-64 focus:bg-white focus:border-black/20 transition-all"
              />
            </div>

            {/* Account Filter */}
            <select
              value={accountFilter}
              onChange={(e) => setAccountFilter(e.target.value)}
              className="px-3 py-1.5 bg-slate-50 border border-black/[0.08] rounded-xl text-xs text-[#1A1D2E] outline-none cursor-pointer"
            >
              <option value="all">全部账号 ({availableAccounts.length})</option>
              {availableAccounts.map((acc) => (
                <option key={acc.id} value={acc.id}>
                  {acc.name}
                </option>
              ))}
            </select>

            {/* Drama Filter */}
            <select
              value={dramaFilter}
              onChange={(e) => setDramaFilter(e.target.value)}
              className="px-3 py-1.5 bg-slate-50 border border-black/[0.08] rounded-xl text-xs text-[#1A1D2E] outline-none cursor-pointer"
            >
              <option value="all">全部剧集 ({availableDramas.length})</option>
              {availableDramas.map((d) => (
                <option key={d.id} value={d.id}>
                  {d.name}
                </option>
              ))}
            </select>
          </div>

          {/* Association Status Pills */}
          <div className="flex items-center gap-1.5 p-1 bg-slate-50 border border-black/[0.06] rounded-2xl text-xs">
            <button
              onClick={() => setAssociationFilter('all')}
              className={`px-3 py-1 rounded-xl font-medium transition-all cursor-pointer ${
                associationFilter === 'all'
                  ? 'bg-[#1A1D2E] text-white shadow-xs'
                  : 'text-[#64748B] hover:text-[#1A1D2E]'
              }`}
            >
              全部 ({totalCount})
            </button>
            <button
              onClick={() => setAssociationFilter('linked')}
              className={`px-3 py-1 rounded-xl font-medium transition-all cursor-pointer ${
                associationFilter === 'linked'
                  ? 'bg-emerald-700 text-white shadow-xs'
                  : 'text-emerald-700 hover:bg-emerald-50'
              }`}
            >
              已关联 ({linkedCount})
            </button>
            <button
              onClick={() => setAssociationFilter('unlinked')}
              className={`px-3 py-1 rounded-xl font-medium transition-all cursor-pointer ${
                associationFilter === 'unlinked'
                  ? 'bg-amber-700 text-white shadow-xs'
                  : 'text-amber-700 hover:bg-amber-50'
              }`}
            >
              待核对 ({unlinkedCount})
            </button>
          </div>
        </div>

        {/* Video Table */}
        <div className="overflow-x-auto border border-black/[0.06] rounded-2xl">
          <table className="w-full text-left border-collapse text-xs">
            <thead>
              <tr className="bg-slate-50/80 text-[11px] font-bold text-[#64748B] border-b border-black/[0.06]">
                <th 
                  onClick={() => handleSort('date')}
                  className="py-3 px-3.5 font-medium cursor-pointer hover:text-[#1A1D2E] select-none"
                >
                  <div className="flex items-center gap-1">
                    <span>首次观测</span>
                    <ArrowUpDown className="w-3 h-3 text-slate-400" />
                  </div>
                </th>
                <th className="py-3 px-3.5 font-medium">账号</th>
                <th className="py-3 px-3.5 font-medium">剧集</th>
                <th className="py-3 px-3.5 font-medium">平台视频 ID</th>
                <th 
                  onClick={() => handleSort('videoViews')}
                  className="py-3 px-3.5 font-medium text-right cursor-pointer hover:text-[#1A1D2E] select-none"
                >
                  <div className="flex items-center justify-end gap-1">
                    <span>视频播放</span>
                    <ArrowUpDown className="w-3 h-3 text-slate-400" />
                  </div>
                </th>
                <th 
                  onClick={() => handleSort('dramaViews')}
                  className="py-3 px-3.5 font-medium text-right cursor-pointer hover:text-[#1A1D2E] select-none"
                >
                  <div className="flex items-center justify-end gap-1">
                    <span>剧集播放</span>
                    <ArrowUpDown className="w-3 h-3 text-slate-400" />
                  </div>
                </th>
                <th 
                  onClick={() => handleSort('revenue')}
                  className="py-3 px-3.5 font-medium text-right cursor-pointer hover:text-[#1A1D2E] select-none"
                >
                  <div className="flex items-center justify-end gap-1">
                    <span>周期收益</span>
                    <ArrowUpDown className="w-3 h-3 text-slate-400" />
                  </div>
                </th>
                <th 
                  onClick={() => handleSort('receptionStrength')}
                  className="py-3 px-3.5 font-medium text-right cursor-pointer hover:text-[#1A1D2E] select-none"
                >
                  <div className="flex items-center justify-end gap-1">
                    <span>承接强度</span>
                    <HelpTooltip text="剧集播放 ÷ 视频播放" />
                    <ArrowUpDown className="w-3 h-3 text-slate-400 ml-1" />
                  </div>
                </th>
                <th 
                  onClick={() => handleSort('rpm')}
                  className="py-3 px-3.5 font-medium text-right cursor-pointer hover:text-[#1A1D2E] select-none"
                >
                  <div className="flex items-center justify-end gap-1">
                    <span>千次播放收益</span>
                    <HelpTooltip text="每千次视频播放产生的收益（RPM）" />
                    <ArrowUpDown className="w-3 h-3 text-slate-400 ml-1" />
                  </div>
                </th>
                <th className="py-3 px-3.5 font-medium">成片关联</th>
                <th className="py-3 px-3.5 font-medium text-right">操作</th>
              </tr>
            </thead>

            <tbody className="divide-y divide-black/[0.04]">
              {paginatedVideos.length === 0 ? (
                <tr>
                  <td colSpan={11} className="py-8 text-center text-slate-400 text-xs">
                    未找到符合当前筛选条件的平台视频
                  </td>
                </tr>
              ) : (
                paginatedVideos.map((v) => {
                  const isHovered = hoveredVideo?.id === v.id;
                  const isSelected = selectedVideo?.id === v.id;

                  return (
                    <tr
                      key={v.id}
                      id={`video-row-${v.id}`}
                      onMouseEnter={() => setHoveredVideo(v)}
                      onMouseLeave={() => setHoveredVideo(null)}
                      onClick={() => handleSelectVideo(v)}
                      className={`cursor-pointer transition-colors ${
                        isSelected
                          ? 'bg-slate-100/90'
                          : isHovered
                          ? 'bg-slate-50/80'
                          : 'hover:bg-slate-50/50'
                      }`}
                    >
                      {/* 1. 首次观测 */}
                      <td className="py-3 px-3.5 font-mono text-[#64748B] whitespace-nowrap">
                        {v.firstObservedShort}
                      </td>

                      {/* 2. 账号 */}
                      <td className="py-3 px-3.5 font-medium text-[#1A1D2E] whitespace-nowrap">
                        {v.accountName}
                      </td>

                      {/* 3. 剧集 */}
                      <td className="py-3 px-3.5 text-[#1A1D2E] font-medium max-w-[200px] truncate">
                        <span className="truncate">{v.dramaName}</span>
                      </td>

                      {/* 4. 平台视频 ID */}
                      <td className="py-3 px-3.5 max-w-[220px]">
                        <span className="block truncate font-mono text-[10px] text-slate-500 bg-slate-100 px-1.5 py-1 rounded" title={v.id}>
                          {v.id}
                        </span>
                      </td>

                      {/* 5. 视频播放 */}
                      <td className="py-3 px-3.5 text-right font-mono text-slate-700 whitespace-nowrap">
                        {v.periodVideoViews.toLocaleString()}
                      </td>

                      {/* 5. 剧集播放 */}
                      <td className="py-3 px-3.5 text-right font-mono text-slate-700 whitespace-nowrap">
                        {v.periodDramaViews.toLocaleString()}
                      </td>

                      {/* 6. 周期收益 */}
                      <td className="py-3 px-3.5 text-right font-mono font-bold text-emerald-700 whitespace-nowrap">
                        ¥{v.periodRevenue.toFixed(2)}
                      </td>

                      {/* 7. 承接强度 */}
                      <td className="py-3 px-3.5 text-right font-mono text-indigo-700 font-medium whitespace-nowrap">
                        {v.receptionStrength.toFixed(2)}
                      </td>

                      {/* 8. 千次播放收益 */}
                      <td className="py-3 px-3.5 text-right font-mono text-amber-800 font-medium whitespace-nowrap">
                        ¥{v.rpm.toFixed(2)}
                      </td>

                      {/* 9. 成片关联 */}
                      <td className="py-3 px-3.5 whitespace-nowrap" onClick={(e) => e.stopPropagation()}>
                        {v.isLinked ? (
                          <StatusBadge variant="linked" text={v.linkedClipName} />
                        ) : (
                          <StatusBadge variant="unlinked" text={`${v.candidateBatch} (待核对)`} />
                        )}
                      </td>

                      {/* 10. 操作 */}
                      <td className="py-3 px-3.5 text-right whitespace-nowrap" onClick={(e) => e.stopPropagation()}>
                        <div className="flex items-center justify-end gap-1.5">
                          <button
                            onClick={() => handleOpenLinkModal(v)}
                            className="px-2.5 py-1 rounded-xl text-[11px] font-medium text-slate-700 hover:text-[#1A1D2E] hover:bg-slate-200/70 transition-colors cursor-pointer"
                          >
                            {v.isLinked ? '修改关联' : '核对关联'}
                          </button>
                          <button
                            onClick={() => handleSelectVideo(v)}
                            className="p-1 rounded-lg text-slate-400 hover:text-[#1A1D2E] hover:bg-slate-200/70 transition-colors cursor-pointer"
                          >
                            <ChevronRight className="w-4 h-4" />
                          </button>
                        </div>
                      </td>
                    </tr>
                  );
                })
              )}
            </tbody>
          </table>
        </div>

        {/* Table Footer with Pagination */}
        <div className="flex flex-wrap items-center justify-between gap-3 text-xs text-[#64748B] pt-2">
          <div>
            显示 <strong className="font-mono text-[#1A1D2E]">{startItemIndex}–{endItemIndex}</strong> / {sortedVideos.length} 条平台视频
          </div>

          {/* Pagination Controls */}
          {totalPages > 1 && (
            <div className="flex items-center gap-1.5">
              <button
                disabled={currentPage <= 1}
                onClick={() => setCurrentPage((p) => Math.max(1, p - 1))}
                className={`p-1.5 rounded-xl border flex items-center justify-center transition-all ${
                  currentPage <= 1
                    ? 'border-black/[0.04] text-slate-300 cursor-not-allowed'
                    : 'border-black/[0.08] text-slate-700 hover:bg-slate-100 active:scale-95 cursor-pointer'
                }`}
              >
                <ChevronLeft className="w-4 h-4" />
              </button>

              {/* Page buttons */}
              {Array.from({ length: totalPages }, (_, i) => i + 1).map((pageNum) => {
                if (
                  totalPages > 7 &&
                  pageNum !== 1 &&
                  pageNum !== totalPages &&
                  Math.abs(pageNum - currentPage) > 1
                ) {
                  if (pageNum === 2 || pageNum === totalPages - 1) {
                    return (
                      <span key={`ellipsis-${pageNum}`} className="px-1 text-slate-400 font-mono">
                        ...
                      </span>
                    );
                  }
                  return null;
                }

                const isActive = pageNum === currentPage;
                return (
                  <button
                    key={pageNum}
                    onClick={() => setCurrentPage(pageNum)}
                    className={`w-7 h-7 rounded-xl font-mono text-xs font-medium transition-all cursor-pointer ${
                      isActive
                        ? 'bg-[#1A1D2E] text-white shadow-xs'
                        : 'text-slate-600 hover:bg-slate-100 border border-transparent'
                    }`}
                  >
                    {pageNum}
                  </button>
                );
              })}

              <button
                disabled={currentPage >= totalPages}
                onClick={() => setCurrentPage((p) => Math.min(totalPages, p + 1))}
                className={`p-1.5 rounded-xl border flex items-center justify-center transition-all ${
                  currentPage >= totalPages
                    ? 'border-black/[0.04] text-slate-300 cursor-not-allowed'
                    : 'border-black/[0.08] text-slate-700 hover:bg-slate-100 active:scale-95 cursor-pointer'
                }`}
              >
                <ChevronRight className="w-4 h-4" />
              </button>
            </div>
          )}
        </div>
      </div>

      {/* 3. SIDE DRAWER FOR VIDEO DETAILS */}
      <VideoDrawer
        video={selectedVideo}
        isOpen={isDrawerOpen}
        onClose={() => setIsDrawerOpen(false)}
        timeRange={timeRange}
        onOpenLinkModal={handleOpenLinkModal}
        onNavigateToTab={onNavigateToTab}
      />

      {/* 4. MODAL FOR VIDEO LINKING */}
      <VideoLinkModal
        video={linkingVideo}
        isOpen={isLinkModalOpen}
        onClose={() => setIsLinkModalOpen(false)}
        candidates={linkCandidates}
        isLoadingCandidates={loadingCandidates}
        errorMessage={linkError}
        onConfirmLink={handleConfirmLink}
      />

    </div>
  );
};
