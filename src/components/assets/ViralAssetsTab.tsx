import React, { useState, useMemo } from 'react';
import {
  ViralAssetItem,
  ViralRecordItem,
  AccountBusinessItem,
  DramaBusinessItem,
  ProductionBatchCandidateMaterial,
} from '../../assetsTypes';
import {
  Sparkles,
  Play,
  FolderOpen,
  Search,
  Filter,
  Film,
  Copy,
  Check,
  Plus,
  History,
  Layers,
  Calendar,
  Send,
  Building2,
  Tv,
  CheckCircle2,
  FileVideo,
  ChevronRight,
  Database,
  Info,
} from 'lucide-react';
import { ResourcePreviewModal, PreviewResourceData } from './modals/ResourcePreviewModal';
import { MarkViralModal } from './modals/MarkViralModal';
import { ViralRecordsDrawer } from './modals/ViralRecordsDrawer';

interface ViralAssetsTabProps {
  viralAssets: ViralAssetItem[];
  accounts: AccountBusinessItem[];
  dramas: DramaBusinessItem[];
  onOpenFolder: (path: string) => void;
  onUpdateViralAssets: (assets: ViralAssetItem[]) => void;
  onShowToast: (msg: string) => void;
  onApplyToProduction?: (asset: ViralAssetItem) => void;
}

type TimeRangeFilter = 'ALL' | '7d' | '30d' | '90d';

export const ViralAssetsTab: React.FC<ViralAssetsTabProps> = ({
  viralAssets,
  accounts,
  dramas,
  onOpenFolder,
  onUpdateViralAssets,
  onShowToast,
  onApplyToProduction,
}) => {
  // Filter states
  const [selectedTheaterFilter, setSelectedTheaterFilter] = useState<string>('ALL');
  const [selectedDramaFilter, setSelectedDramaFilter] = useState<string>('ALL');
  const [timeRangeFilter, setTimeRangeFilter] = useState<TimeRangeFilter>('ALL');
  const [searchTerm, setSearchTerm] = useState<string>('');

  // Modals & Drawer states
  const [previewResource, setPreviewResource] = useState<PreviewResourceData | null>(null);
  const [selectedAssetForDrawer, setSelectedAssetForDrawer] = useState<ViralAssetItem | null>(null);
  const [isMarkViralOpen, setIsMarkViralOpen] = useState<boolean>(false);
  const [copiedId, setCopiedId] = useState<string | null>(null);

  // Distinct Theaters from dramas and viral assets
  const theaterList = useMemo(() => {
    const set = new Set<string>();
    viralAssets.forEach(v => {
      if (v.sourceTheaterName) set.add(v.sourceTheaterName);
    });
    dramas.forEach(d => {
      if (d.theaterName) set.add(d.theaterName);
    });
    return Array.from(set);
  }, [viralAssets, dramas]);

  // Distinct source dramas from viral assets
  const sourceDramaList = useMemo(() => {
    const set = new Set<string>();
    viralAssets.forEach(v => {
      if (v.sourceDramaName) set.add(v.sourceDramaName);
    });
    return Array.from(set);
  }, [viralAssets]);

  // Top Statistics
  // 1. 爆款素材 = 实际保存的唯一源素材数量
  const uniqueMaterialsCount = viralAssets.length;
  // 2. 爆款记录 = 所有素材产生过的爆款次数总和
  const totalRecordsCount = useMemo(() => {
    return viralAssets.reduce((acc, v) => acc + (v.records?.length || v.viralCount || 1), 0);
  }, [viralAssets]);
  // 3. 多次爆款素材 = 爆款次数 ≥ 2 的素材数量
  const multipleViralCount = useMemo(() => {
    return viralAssets.filter(v => (v.viralCount || v.records?.length || 1) >= 2).length;
  }, [viralAssets]);

  // Filtered Assets logic
  const filteredVirals = useMemo(() => {
    const now = new Date();

    return viralAssets.filter(asset => {
      // 1. Theater filter
      if (selectedTheaterFilter !== 'ALL') {
        const matchTheater =
          asset.sourceTheaterName === selectedTheaterFilter ||
          dramas.some(
            d => d.currentName === asset.sourceDramaName && d.theaterName === selectedTheaterFilter
          );
        if (!matchTheater) return false;
      }

      // 2. Source Drama filter
      if (selectedDramaFilter !== 'ALL') {
        if (asset.sourceDramaName !== selectedDramaFilter) return false;
      }

      // 3. Time range filter (based on latestViralDate or firstViralDate)
      if (timeRangeFilter !== 'ALL') {
        const assetDate = new Date(asset.latestViralDate || asset.firstViralDate);
        const diffDays = (now.getTime() - assetDate.getTime()) / (1000 * 3600 * 24);
        if (timeRangeFilter === '7d' && diffDays > 7) return false;
        if (timeRangeFilter === '30d' && diffDays > 30) return false;
        if (timeRangeFilter === '90d' && diffDays > 90) return false;
      }

      // 4. Search term (Material filename, current drama, history drama names, accounts, MD5)
      if (searchTerm) {
        const q = searchTerm.toLowerCase().trim();
        const matchMaterial = asset.materialName.toLowerCase().includes(q);
        const matchDrama = asset.sourceDramaName.toLowerCase().includes(q);
        const matchMD5 = asset.md5?.toLowerCase().includes(q);
        const matchRecords = asset.records?.some(
          r =>
            r.accountName.toLowerCase().includes(q) ||
            r.dramaName.toLowerCase().includes(q) ||
            r.notes?.toLowerCase().includes(q)
        );

        // Also check if matches drama history names in drama catalog
        const matchingDramaBiz = dramas.find(d => d.currentName === asset.sourceDramaName);
        const matchHistoryNames = matchingDramaBiz?.historyNames?.some(h =>
          h.toLowerCase().includes(q)
        );

        if (!matchMaterial && !matchDrama && !matchMD5 && !matchRecords && !matchHistoryNames) {
          return false;
        }
      }

      return true;
    });
  }, [viralAssets, selectedTheaterFilter, selectedDramaFilter, timeRangeFilter, searchTerm, dramas]);

  const handleCopyPath = (id: string, path: string) => {
    navigator.clipboard.writeText(path);
    setCopiedId(id);
    onShowToast('已复制本地源视频文件路径');
    setTimeout(() => setCopiedId(null), 2000);
  };

  // Handle Mark Viral Confirmation
  const handleConfirmMarkViral = (
    candidate: ProductionBatchCandidateMaterial,
    recordData: {
      date: string;
      publishTime: string;
      videoPlayCountText: string;
      dramaPlayCountText?: string;
      revenue?: number;
      dataSource: '青柠平台数据' | '人工录入';
      notes?: string;
    },
    isExistingAsset: boolean
  ) => {
    // Parse play count numbers if possible
    let parsedVideoPlays: number | undefined = undefined;
    if (recordData.videoPlayCountText.includes('万') || recordData.videoPlayCountText.includes('w')) {
      const num = parseFloat(recordData.videoPlayCountText.replace(/[^\d.]/g, ''));
      if (!isNaN(num)) parsedVideoPlays = Math.round(num * 10000);
    } else {
      const num = parseInt(recordData.videoPlayCountText.replace(/[^\d]/g, ''), 10);
      if (!isNaN(num)) parsedVideoPlays = num;
    }

    let parsedDramaPlays: number | undefined = undefined;
    if (recordData.dramaPlayCountText) {
      if (recordData.dramaPlayCountText.includes('万') || recordData.dramaPlayCountText.includes('w')) {
        const num = parseFloat(recordData.dramaPlayCountText.replace(/[^\d.]/g, ''));
        if (!isNaN(num)) parsedDramaPlays = Math.round(num * 10000);
      } else {
        const num = parseInt(recordData.dramaPlayCountText.replace(/[^\d]/g, ''), 10);
        if (!isNaN(num)) parsedDramaPlays = num;
      }
    }

    const newRecord: ViralRecordItem = {
      id: `rec-${Date.now().toString().slice(-4)}`,
      date: recordData.date,
      viralDate: recordData.date,
      accountName: candidate.accountName,
      dramaName: candidate.dramaName,
      publishTime: recordData.publishTime,
      publishInfo: recordData.publishTime ? `${recordData.publishTime}` : undefined,
      videoPlayCount: parsedVideoPlays,
      videoPlayCountText: recordData.videoPlayCountText,
      playCountText: `${recordData.videoPlayCountText}播放`,
      dramaPlayCount: parsedDramaPlays,
      dramaPlayCountText: recordData.dramaPlayCountText,
      revenue: recordData.revenue,
      conversionRevenue: recordData.revenue,
      dataSource: recordData.dataSource,
      notes: recordData.notes,
    };

    const existingIndex = viralAssets.findIndex(v => v.md5 === candidate.md5);

    if (existingIndex >= 0) {
      // Append record to existing asset without duplicating physical files
      const existing = viralAssets[existingIndex];
      const updatedRecords = [newRecord, ...(existing.records || [])];
      
      // Calculate totals
      let totalVideo = 0;
      let totalDrama = 0;
      let hasDrama = false;
      let partialDrama = false;
      let totalRev = 0;
      let hasRev = false;

      updatedRecords.forEach(r => {
        if (r.videoPlayCount) totalVideo += r.videoPlayCount;
        if (r.dramaPlayCount) {
          totalDrama += r.dramaPlayCount;
          hasDrama = true;
        } else {
          partialDrama = true;
        }
        if (r.revenue) {
          totalRev += r.revenue;
          hasRev = true;
        }
      });

      const updatedAsset: ViralAssetItem = {
        ...existing,
        latestViralDate: recordData.date,
        lastViralDate: recordData.date,
        viralCount: updatedRecords.length,
        records: updatedRecords,
        totalVideoPlays: totalVideo || undefined,
        totalVideoPlaysText: totalVideo ? `${(totalVideo / 10000).toFixed(1)}万` : existing.totalVideoPlaysText,
        totalDramaPlays: hasDrama ? totalDrama : undefined,
        totalDramaPlaysText: hasDrama ? `${(totalDrama / 10000).toFixed(1)}万` : undefined,
        hasDramaPlayData: hasDrama,
        isPartialDramaPlays: hasDrama && partialDrama,
        totalRevenue: hasRev ? totalRev : undefined,
        hasRevenueData: hasRev,
      };

      const updatedList = [...viralAssets];
      updatedList[existingIndex] = updatedAsset;
      onUpdateViralAssets(updatedList);
      onShowToast(`已为源素材追加第 ${updatedRecords.length} 条爆款投放记录（无需重复保存文件）`);
    } else {
      // Create new Viral Asset
      const newAsset: ViralAssetItem = {
        id: `va-${Date.now().toString().slice(-4)}`,
        materialName: candidate.filename || candidate.name,
        title: (candidate.filename || candidate.name).replace('.mp4', ''),
        sourceDramaName: candidate.dramaName,
        sourceTheaterName: candidate.theaterName || '点众剧场',
        sourceAccountName: candidate.accountName,
        md5: candidate.md5,
        filePath: candidate.filePath,
        fileSizeMb: candidate.fileSizeMb,
        durationSeconds: candidate.durationSeconds,
        thumbnailUrl: candidate.thumbnailUrl,
        firstViralDate: recordData.date,
        latestViralDate: recordData.date,
        lastViralDate: recordData.date,
        viralCount: 1,
        totalVideoPlays: parsedVideoPlays,
        totalVideoPlaysText: recordData.videoPlayCountText,
        totalDramaPlays: parsedDramaPlays,
        totalDramaPlaysText: recordData.dramaPlayCountText,
        hasDramaPlayData: !!parsedDramaPlays,
        isPartialDramaPlays: false,
        totalRevenue: recordData.revenue,
        hasRevenueData: !!recordData.revenue,
        records: [newRecord],
        createdAt: recordData.date,
      };

      onUpdateViralAssets([newAsset, ...viralAssets]);
      onShowToast(`已成功沉淀新爆款源素材「${newAsset.materialName}」`);
    }
  };

  const handleOpenPreview = (asset: ViralAssetItem) => {
    setPreviewResource({
      title: asset.materialName,
      categoryName: `爆款源素材 · 《${asset.sourceDramaName}》`,
      type: 'video',
      filePath: asset.filePath,
      fileSizeMb: asset.fileSizeMb,
      durationText: `00:${asset.durationSeconds < 10 ? '0' : ''}${asset.durationSeconds}`,
      metrics: {
        playCountText: asset.totalVideoPlaysText,
        revenue: asset.hasRevenueData ? asset.totalRevenue : undefined,
      },
      sourceDramaName: asset.sourceDramaName,
      sourceAccountName: asset.sourceAccountName,
    });
  };

  const handleApplyProduction = (asset: ViralAssetItem) => {
    if (onApplyToProduction) {
      onApplyToProduction(asset);
    } else {
      onShowToast(`已将源素材「${asset.materialName}」加入当前生产管线候选池`);
    }
  };

  return (
    <div className="space-y-6">
      {/* 1. Header Banner & Universal Stats */}
      <div className="bg-white rounded-2xl border border-black/[0.06] shadow-xs p-6 flex flex-col lg:flex-row lg:items-center justify-between gap-5">
        <div className="space-y-1.5 max-w-2xl">
          <div className="flex items-center gap-2">
            <span className="p-1.5 rounded-xl bg-[#1A1D2E] text-[#DDFD00]">
              <Sparkles className="w-4 h-4" />
            </span>
            <h2 className="text-base font-bold text-[#1A1D2E]">
              爆款源素材资产库 (源素材管理中心)
            </h2>
          </div>
          <p className="text-xs text-[#64748B] leading-relaxed">
            长效沉淀产生爆款结果的原始视频素材（单物理文件），归集各账号与剧集的多次爆款投放记录。
            系统通过 MD5 唯一指纹精准去重，同一素材多次爆款仅新增记录，不重复保存文件。
          </p>
        </div>

        {/* Universal Stats Badges & Mark Viral Action */}
        <div className="flex items-center gap-3 flex-wrap sm:flex-nowrap">
          {/* Stat 1: 爆款素材 */}
          <div className="px-4 py-2.5 rounded-2xl bg-slate-50 border border-black/[0.04] text-right min-w-[100px]">
            <span className="text-[11px] text-slate-400 block font-medium">爆款素材</span>
            <span className="text-lg font-black text-[#1A1D2E] font-mono">
              {uniqueMaterialsCount} <span className="text-xs font-normal text-slate-500">个</span>
            </span>
          </div>

          {/* Stat 2: 爆款记录 */}
          <div className="px-4 py-2.5 rounded-2xl bg-slate-50 border border-black/[0.04] text-right min-w-[100px]">
            <span className="text-[11px] text-slate-400 block font-medium">爆款记录</span>
            <span className="text-lg font-black text-[#1A1D2E] font-mono">
              {totalRecordsCount} <span className="text-xs font-normal text-slate-500">次</span>
            </span>
          </div>

          {/* Stat 3: 多次爆款素材 */}
          <div className="px-4 py-2.5 rounded-2xl bg-indigo-50/80 border border-indigo-200 text-right min-w-[115px]">
            <span className="text-[11px] text-indigo-700 block font-medium">多次爆款素材</span>
            <span className="text-lg font-black text-indigo-950 font-mono">
              {multipleViralCount} <span className="text-xs font-normal text-indigo-600">个</span>
            </span>
          </div>

          {/* Button: + 标记 / 录入爆款 */}
          <button
            onClick={() => setIsMarkViralOpen(true)}
            className="flex items-center gap-1.5 px-4 py-3 rounded-2xl bg-[#1A1D2E] text-[#DDFD00] hover:bg-black/90 active:scale-[0.98] text-xs font-bold shadow-xs transition-all cursor-pointer shrink-0 ml-1"
          >
            <Plus className="w-4 h-4" />
            <span>标记 / 录入爆款</span>
          </button>
        </div>
      </div>

      {/* 2. Structured Filter & Search Controls */}
      <div className="bg-white rounded-2xl border border-black/[0.06] shadow-xs p-4 space-y-3">
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-12 gap-3 items-center text-xs">
          {/* 来源剧场 Select */}
          <div className="lg:col-span-3">
            <div className="flex items-center gap-2 px-3 py-2 rounded-xl bg-slate-50 border border-black/[0.06]">
              <Building2 className="w-3.5 h-3.5 text-slate-400 shrink-0" />
              <span className="text-slate-400 shrink-0 text-[11px]">剧场:</span>
              <select
                value={selectedTheaterFilter}
                onChange={e => setSelectedTheaterFilter(e.target.value)}
                className="w-full bg-transparent font-semibold text-[#1A1D2E] focus:outline-none cursor-pointer"
              >
                <option value="ALL">全部剧场 ({theaterList.length})</option>
                {theaterList.map(th => (
                  <option key={th} value={th}>
                    {th}
                  </option>
                ))}
              </select>
            </div>
          </div>

          {/* 来源剧集 Select */}
          <div className="lg:col-span-3">
            <div className="flex items-center gap-2 px-3 py-2 rounded-xl bg-slate-50 border border-black/[0.06]">
              <Film className="w-3.5 h-3.5 text-slate-400 shrink-0" />
              <span className="text-slate-400 shrink-0 text-[11px]">原始剧集:</span>
              <select
                value={selectedDramaFilter}
                onChange={e => setSelectedDramaFilter(e.target.value)}
                className="w-full bg-transparent font-semibold text-[#1A1D2E] focus:outline-none cursor-pointer truncate"
              >
                <option value="ALL">全部来源剧集 ({sourceDramaList.length})</option>
                {sourceDramaList.map(name => (
                  <option key={name} value={name}>
                    {name}
                  </option>
                ))}
              </select>
            </div>
          </div>

          {/* 时间范围 Filter */}
          <div className="lg:col-span-2">
            <div className="flex items-center gap-2 px-3 py-2 rounded-xl bg-slate-50 border border-black/[0.06]">
              <Calendar className="w-3.5 h-3.5 text-slate-400 shrink-0" />
              <span className="text-slate-400 shrink-0 text-[11px]">时间:</span>
              <select
                value={timeRangeFilter}
                onChange={e => setTimeRangeFilter(e.target.value as TimeRangeFilter)}
                className="w-full bg-transparent font-semibold text-[#1A1D2E] focus:outline-none cursor-pointer"
              >
                <option value="ALL">全部时间</option>
                <option value="7d">最近 7 天</option>
                <option value="30d">最近 30 天</option>
                <option value="90d">最近 90 天</option>
              </select>
            </div>
          </div>

          {/* 综合搜索框 (素材名称/当前剧名/历史剧名/账号/MD5) */}
          <div className="lg:col-span-4">
            <div className="relative">
              <Search className="w-3.5 h-3.5 text-slate-400 absolute left-3 top-2.5" />
              <input
                type="text"
                placeholder="搜索素材名称、剧名、历史别名、账号、MD5..."
                value={searchTerm}
                onChange={e => setSearchTerm(e.target.value)}
                className="w-full pl-8 pr-8 py-2 rounded-xl border border-black/[0.08] bg-slate-50/60 text-xs font-medium text-[#1A1D2E] placeholder:text-slate-400 focus:outline-none focus:bg-white focus:ring-2 focus:ring-[#1A1D2E]/20 transition-all"
              />
              {searchTerm && (
                <button
                  type="button"
                  onClick={() => setSearchTerm('')}
                  className="absolute right-2.5 top-2.5 text-slate-400 hover:text-slate-600 cursor-pointer"
                >
                  ×
                </button>
              )}
            </div>
          </div>
        </div>

        {/* Active Filter Indicators if any */}
        {(selectedTheaterFilter !== 'ALL' ||
          selectedDramaFilter !== 'ALL' ||
          timeRangeFilter !== 'ALL' ||
          searchTerm) && (
          <div className="flex items-center gap-2 pt-2 border-t border-black/[0.04] text-[11px] text-slate-500">
            <span className="text-slate-400">已生效筛选:</span>
            {selectedTheaterFilter !== 'ALL' && (
              <span className="px-2 py-0.5 rounded-md bg-slate-100 text-slate-700 font-medium flex items-center gap-1">
                剧场: {selectedTheaterFilter}
                <button
                  onClick={() => setSelectedTheaterFilter('ALL')}
                  className="hover:text-black cursor-pointer"
                >
                  ×
                </button>
              </span>
            )}
            {selectedDramaFilter !== 'ALL' && (
              <span className="px-2 py-0.5 rounded-md bg-slate-100 text-slate-700 font-medium flex items-center gap-1">
                剧集: {selectedDramaFilter}
                <button
                  onClick={() => setSelectedDramaFilter('ALL')}
                  className="hover:text-black cursor-pointer"
                >
                  ×
                </button>
              </span>
            )}
            {timeRangeFilter !== 'ALL' && (
              <span className="px-2 py-0.5 rounded-md bg-slate-100 text-slate-700 font-medium flex items-center gap-1">
                时间: {timeRangeFilter === '7d' ? '近7天' : timeRangeFilter === '30d' ? '近30天' : '近90天'}
                <button
                  onClick={() => setTimeRangeFilter('ALL')}
                  className="hover:text-black cursor-pointer"
                >
                  ×
                </button>
              </span>
            )}
            {searchTerm && (
              <span className="px-2 py-0.5 rounded-md bg-slate-100 text-slate-700 font-medium flex items-center gap-1">
                关键词: "{searchTerm}"
                <button
                  onClick={() => setSearchTerm('')}
                  className="hover:text-black cursor-pointer"
                >
                  ×
                </button>
              </span>
            )}
            <button
              onClick={() => {
                setSelectedTheaterFilter('ALL');
                setSelectedDramaFilter('ALL');
                setTimeRangeFilter('ALL');
                setSearchTerm('');
              }}
              className="text-indigo-600 hover:text-indigo-800 font-semibold ml-auto cursor-pointer"
            >
              清空全部筛选
            </button>
          </div>
        )}
      </div>

      {/* 3. Viral Raw Material Asset Cards Grid */}
      {filteredVirals.length > 0 ? (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {filteredVirals.map(asset => {
            const recordsCount = asset.records?.length || asset.viralCount || 1;
            const isMultipleViral = recordsCount >= 2;
            const latestRecord = asset.records?.[0];

            return (
              <div
                key={asset.id}
                className="bg-white rounded-2xl border border-black/[0.06] shadow-xs p-5 hover:border-black/20 hover:shadow-sm transition-all flex flex-col justify-between space-y-4 group"
              >
                <div className="space-y-3.5">
                  {/* Card Header Top Row */}
                  <div className="flex items-start gap-3.5">
                    {/* Video Thumbnail with Hover Play Button */}
                    <div
                      onClick={() => handleOpenPreview(asset)}
                      className="relative w-28 h-20 rounded-xl overflow-hidden bg-slate-900 shrink-0 cursor-pointer group/thumb border border-black/[0.06]"
                    >
                      {asset.thumbnailUrl ? (
                        <img
                          src={asset.thumbnailUrl}
                          alt={asset.materialName}
                          className="w-full h-full object-cover group-hover/thumb:scale-105 transition-transform duration-300 opacity-90"
                          referrerPolicy="no-referrer"
                        />
                      ) : (
                        <div className="w-full h-full flex items-center justify-center text-slate-600">
                          <FileVideo className="w-6 h-6" />
                        </div>
                      )}

                      {/* Play Overlay */}
                      <div className="absolute inset-0 bg-black/30 group-hover/thumb:bg-black/50 transition-colors flex items-center justify-center">
                        <div className="w-7 h-7 rounded-full bg-white/90 text-[#1A1D2E] flex items-center justify-center shadow-md group-hover/thumb:scale-110 transition-transform">
                          <Play className="w-3.5 h-3.5 fill-current ml-0.5" />
                        </div>
                      </div>

                      {/* Duration & Size Pills */}
                      <div className="absolute bottom-1 right-1 px-1.5 py-0.2 rounded bg-black/75 text-white font-mono text-[9px] font-semibold">
                        00:{asset.durationSeconds < 10 ? '0' : ''}{asset.durationSeconds}
                      </div>
                    </div>

                    {/* Metadata & Filename */}
                    <div className="space-y-1 min-w-0 flex-1">
                      <div className="flex items-center gap-1.5 flex-wrap">
                        <span className="px-2 py-0.5 rounded-md bg-slate-100 text-[#1A1D2E] text-[10px] font-bold">
                          《{asset.sourceDramaName}》
                        </span>
                        {asset.sourceTheaterName && (
                          <span className="px-1.5 py-0.5 rounded-md bg-slate-50 text-slate-500 text-[10px] border border-black/[0.04]">
                            {asset.sourceTheaterName}
                          </span>
                        )}
                        <span
                          className={`px-2 py-0.5 rounded-md text-[10px] font-bold border ${
                            isMultipleViral
                              ? 'bg-indigo-50 text-indigo-700 border-indigo-200'
                              : 'bg-slate-100 text-slate-700 border-slate-200'
                          }`}
                        >
                          爆款 {recordsCount} 次
                        </span>
                      </div>

                      <h3
                        className="font-bold text-xs sm:text-sm text-[#1A1D2E] leading-snug line-clamp-2 pt-0.5"
                        title={asset.materialName}
                      >
                        {asset.materialName}
                      </h3>

                      <div className="flex items-center gap-3 text-[10px] text-slate-500 font-mono pt-0.5">
                        <span>首爆: {asset.firstViralDate}</span>
                        <span>·</span>
                        <span>最近: {asset.latestViralDate}</span>
                      </div>
                    </div>
                  </div>

                  {/* Performance Data Metrics Strip (Strictly Neutral & Rigorous) */}
                  <div className="p-3 rounded-xl bg-slate-50 border border-black/[0.04] grid grid-cols-2 sm:grid-cols-3 gap-2.5 text-xs">
                    {/* 1. 视频播放 */}
                    <div>
                      <span className="text-[10px] text-[#64748B] block font-medium">视频播放</span>
                      <span className="font-mono font-black text-[#1A1D2E] text-xs">
                        {asset.totalVideoPlaysText ||
                          (asset.totalVideoPlays
                            ? `${(asset.totalVideoPlays / 10000).toFixed(1)}万`
                            : '已记录')}
                      </span>
                    </div>

                    {/* 2. 剧集播放 */}
                    <div>
                      <span className="text-[10px] text-[#64748B] block font-medium">剧集播放</span>
                      {asset.hasDramaPlayData && asset.totalDramaPlaysText ? (
                        <div className="flex items-center gap-1">
                          <span className="font-mono font-bold text-[#1A1D2E] text-xs">
                            {asset.totalDramaPlaysText}
                          </span>
                          {asset.isPartialDramaPlays && (
                            <span
                              className="text-[9px] text-slate-400 font-normal"
                              title="仅部分记录具备剧集播放接口数据"
                            >
                              (部分累计)
                            </span>
                          )}
                        </div>
                      ) : (
                        <span className="text-slate-400 font-mono text-xs">—</span>
                      )}
                    </div>

                    {/* 3. 已记录收益 (Only rendered if real revenue exists; NEVER show ¥0) */}
                    {asset.hasRevenueData && asset.totalRevenue ? (
                      <div>
                        <span className="text-[10px] text-emerald-800 block font-medium">已记录收益</span>
                        <span className="font-mono font-black text-emerald-900 text-xs">
                          ¥{asset.totalRevenue.toLocaleString()}
                        </span>
                      </div>
                    ) : (
                      <div>
                        <span className="text-[10px] text-[#64748B] block font-medium">收益记录</span>
                        <span className="text-slate-400 font-mono text-[11px]">未记录/无接口</span>
                      </div>
                    )}
                  </div>

                  {/* Latest Record Quick Peek Strip */}
                  {latestRecord && (
                    <div className="px-3 py-2 rounded-xl bg-slate-100/70 border border-black/[0.04] text-[11px] flex items-center justify-between gap-2">
                      <div className="flex items-center gap-1.5 truncate text-slate-600">
                        <History className="w-3 h-3 text-slate-400 shrink-0" />
                        <span className="text-slate-400 shrink-0">最近投放:</span>
                        <span className="font-semibold text-[#1A1D2E] truncate">
                          {latestRecord.accountName} · 《{latestRecord.dramaName}》
                        </span>
                        {latestRecord.dramaName !== asset.sourceDramaName && (
                          <span className="px-1 py-0.1 rounded bg-purple-100 text-purple-800 text-[9px] font-bold shrink-0">
                            复用
                          </span>
                        )}
                      </div>
                      <span className="font-mono text-slate-500 text-[10px] shrink-0">
                        {latestRecord.videoPlayCountText || latestRecord.playCountText} · {latestRecord.dataSource}
                      </span>
                    </div>
                  )}
                </div>

                {/* Bottom Actions Row */}
                <div className="pt-3 border-t border-black/[0.06] flex items-center justify-between gap-2 text-xs">
                  {/* View Viral Records Drawer Trigger */}
                  <button
                    type="button"
                    onClick={() => setSelectedAssetForDrawer(asset)}
                    className="flex items-center gap-1 text-slate-700 hover:text-[#1A1D2E] font-bold text-xs py-1 px-1.5 rounded-lg hover:bg-slate-100 transition-colors cursor-pointer"
                  >
                    <Layers className="w-3.5 h-3.5 text-indigo-600" />
                    <span>查看爆款记录 ({recordsCount})</span>
                    <ChevronRight className="w-3 h-3 text-slate-400" />
                  </button>

                  <div className="flex items-center gap-1.5">
                    {/* Copy Path */}
                    <button
                      type="button"
                      onClick={() => handleCopyPath(asset.id, asset.filePath)}
                      className="p-1.5 rounded-lg text-slate-500 hover:text-slate-800 hover:bg-slate-100 transition-colors cursor-pointer"
                      title={copiedId === asset.id ? '已复制路径' : '复制本地源文件路径'}
                    >
                      {copiedId === asset.id ? (
                        <Check className="w-3.5 h-3.5 text-emerald-600" />
                      ) : (
                        <Copy className="w-3.5 h-3.5" />
                      )}
                    </button>

                    {/* Open in Windows Explorer */}
                    <button
                      type="button"
                      onClick={() => onOpenFolder(asset.filePath)}
                      className="p-1.5 rounded-lg text-slate-500 hover:text-slate-800 hover:bg-slate-100 transition-colors cursor-pointer"
                      title="在 Windows 资源管理器中打开"
                    >
                      <FolderOpen className="w-3.5 h-3.5" />
                    </button>

                    {/* Lightweight Preview */}
                    <button
                      type="button"
                      onClick={() => handleOpenPreview(asset)}
                      className="flex items-center gap-1 px-2.5 py-1.5 rounded-xl bg-slate-100 hover:bg-slate-200 text-slate-800 font-bold transition-all cursor-pointer shadow-2xs"
                    >
                      <Play className="w-3 h-3" />
                      <span>预览</span>
                    </button>

                    {/* Apply to Production */}
                    <button
                      type="button"
                      onClick={() => handleApplyProduction(asset)}
                      className="flex items-center gap-1 px-3 py-1.5 rounded-xl bg-[#1A1D2E] text-[#DDFD00] hover:bg-black/90 active:scale-[0.98] font-bold shadow-xs transition-all cursor-pointer"
                    >
                      <Send className="w-3 h-3" />
                      <span>用于生产</span>
                    </button>
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      ) : (
        /* Empty State */
        <div className="bg-white rounded-2xl border border-black/[0.06] shadow-xs p-12 text-center space-y-4">
          <div className="w-12 h-12 rounded-2xl bg-slate-100 text-slate-400 flex items-center justify-center mx-auto">
            <Film className="w-6 h-6" />
          </div>
          <div>
            <h3 className="font-bold text-sm text-[#1A1D2E]">未找到符合条件的爆款源素材</h3>
            <p className="text-xs text-[#64748B] mt-1 max-w-sm mx-auto">
              当前筛选条件下无匹配的素材。您可以调整剧场、剧集、时间筛选或关键词搜索。
            </p>
          </div>
          <button
            onClick={() => {
              setSelectedTheaterFilter('ALL');
              setSelectedDramaFilter('ALL');
              setTimeRangeFilter('ALL');
              setSearchTerm('');
            }}
            className="px-4 py-2 rounded-xl bg-slate-100 hover:bg-slate-200 text-slate-700 font-bold text-xs transition-colors cursor-pointer"
          >
            重置全部筛选
          </button>
        </div>
      )}

      {/* 4. Drawers & Modals */}
      {/* Detail Records Drawer */}
      <ViralRecordsDrawer
        isOpen={!!selectedAssetForDrawer}
        onClose={() => setSelectedAssetForDrawer(null)}
        asset={selectedAssetForDrawer}
        onOpenFolder={onOpenFolder}
        onPreview={handleOpenPreview}
        onApplyToProduction={handleApplyProduction}
        onShowToast={onShowToast}
      />

      {/* Lightweight Media Preview Modal */}
      <ResourcePreviewModal
        isOpen={!!previewResource}
        onClose={() => setPreviewResource(null)}
        resource={previewResource}
        onOpenFolder={onOpenFolder}
      />

      {/* Mark / Log Viral Modal */}
      <MarkViralModal
        isOpen={isMarkViralOpen}
        onClose={() => setIsMarkViralOpen(false)}
        accounts={accounts}
        dramas={dramas}
        viralAssets={viralAssets}
        onConfirmMarkViral={handleConfirmMarkViral}
      />
    </div>
  );
};
