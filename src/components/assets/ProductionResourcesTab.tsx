import React, { useState, useMemo } from 'react';
import { ProductionResourceItem, ResourceCapacityMetrics } from '../../assetsTypes';
import {
  Video,
  Image as ImageIcon,
  Music,
  FolderOpen,
  Plus,
  Play,
  Pause,
  Volume2,
  CheckCircle2,
  AlertCircle,
  TrendingUp,
  Cpu,
  Layers,
  Sparkles,
  Search,
  Filter,
  ArrowUpRight,
  Info,
} from 'lucide-react';
import { ResourcePreviewModal, PreviewResourceData } from './modals/ResourcePreviewModal';
import { formatElapsedSeconds } from '../../utils/duration';

interface ProductionResourcesTabProps {
  resources: ProductionResourceItem[];
  metrics: ResourceCapacityMetrics;
  onOpenFolder: (path: string) => void;
  onAddResource: (resource: Omit<ProductionResourceItem, 'id' | 'addedAt'>) => void;
  onShowToast: (msg: string) => void;
}

type ResourceCategoryFilter = 'ALL' | 'real_video' | 'real_image' | 'bgm' | 'lead_video';

function formatDuration(seconds?: number): string {
  return formatElapsedSeconds(seconds, '—');
}

export const ProductionResourcesTab: React.FC<ProductionResourcesTabProps> = ({
  resources,
  metrics,
  onOpenFolder,
  onAddResource,
  onShowToast,
}) => {
  const [selectedCategory, setSelectedCategory] = useState<ResourceCategoryFilter>('ALL');
  const [searchTerm, setSearchTerm] = useState('');
  const [selectedTag, setSelectedTag] = useState<string>('ALL');
  const [previewResource, setPreviewResource] = useState<PreviewResourceData | null>(null);
  const [playingBgmId, setPlayingBgmId] = useState<string | null>(null);

  // All distinct tags
  const allTags = useMemo(() => {
    const set = new Set<string>();
    resources.forEach(r => r.tags?.forEach(t => set.add(t)));
    return Array.from(set);
  }, [resources]);

  // Filtered resources
  const filteredResources = useMemo(() => {
    return resources.filter(r => {
      const matchCat = selectedCategory === 'ALL' || r.category === selectedCategory;
      const matchSearch =
        !searchTerm ||
        r.name.toLowerCase().includes(searchTerm.toLowerCase()) ||
        r.tags?.some(t => t.toLowerCase().includes(searchTerm.toLowerCase()));
      const matchTag = selectedTag === 'ALL' || r.tags?.includes(selectedTag);
      return matchCat && matchSearch && matchTag;
    });
  }, [resources, selectedCategory, searchTerm, selectedTag]);

  const handleOpenCategoryFolder = (cat: 'video' | 'image' | 'bgm' | 'lead_video') => {
    const category = cat === 'video' ? 'real_video' : cat === 'image' ? 'real_image' : cat;
    const resource = resources.find((item) => item.category === category);
    if (!resource) { onShowToast('该资源目录暂无文件，请先放入资源后重试。'); return; }
    const separator = resource.filePath.includes('\\') ? '\\' : '/';
    onOpenFolder(resource.filePath.slice(0, resource.filePath.lastIndexOf(separator)));
  };

  const handleOpenResourceFolder = (filePath: string) => {
    const separator = filePath.includes('\\') ? '\\' : '/';
    onOpenFolder(filePath.slice(0, filePath.lastIndexOf(separator)));
  };

  return (
    <div className="space-y-6">
      {/* 1. CAPACITY METRICS DASHBOARD (产能计算中心) */}
      <div className="bg-white rounded-2xl border border-black/[0.06] shadow-xs p-6 relative overflow-hidden">
        <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-6">
          {/* Main Capacity Hero */}
          <div className="space-y-2 lg:max-w-md">
            <div className="flex items-center gap-2">
              <span className="w-2.5 h-2.5 rounded-full bg-[#1A1D2E] animate-pulse" />
              <h2 className="text-xs font-bold uppercase tracking-wider text-[#64748B]">
                生产物料总产能计算
              </h2>
            </div>
            <div className="flex items-baseline gap-2">
              <span className="text-3xl sm:text-4xl font-black text-[#1A1D2E] tracking-tight font-mono">
                {metrics.supportableDramas}
              </span>
              <span className="text-base font-bold text-[#1A1D2E]">部剧集生产支持</span>
            </div>
            <p className="text-xs text-[#64748B] leading-relaxed">
              基于当前有效储备物料自动核算。消耗配比：每部短剧需消耗 <strong className="text-slate-800 font-bold">3 个真人视频</strong> 与 <strong className="text-slate-800 font-bold">6 张真人图片</strong>。
            </p>
          </div>

          {/* 3 Metric Breakdown Cards */}
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 flex-1">
            {/* Real Video Card */}
            <div className={`p-4 rounded-xl border transition-all ${
              metrics.bottleneckType === 'video'
                ? 'bg-amber-50/70 border-amber-200/80 shadow-2xs'
                : 'bg-slate-50/70 border-black/[0.05]'
            }`}>
              <div className="flex items-center justify-between mb-2">
                <span className="font-bold text-xs text-[#1A1D2E] flex items-center gap-1.5">
                  <Video className="w-3.5 h-3.5 text-indigo-600" />
                  真人视频
                </span>
                <span className="text-[10px] font-mono text-slate-400">消耗 3个/剧</span>
              </div>
              <div className="flex items-baseline justify-between">
                <span className="text-xl font-bold font-mono text-[#1A1D2E]">
                  <span className="text-xs font-normal text-slate-500">剩余 </span>{metrics.videoCount} <span className="text-xs font-normal text-slate-500">个</span>
                </span>
                <span className="text-xs font-semibold text-indigo-700 bg-indigo-50 px-2 py-0.5 rounded-md font-mono">
                  可供 {metrics.videoSupportableDramas} 部
                </span>
              </div>
            </div>

            {/* Real Image Card */}
            <div className={`p-4 rounded-xl border transition-all ${
              metrics.bottleneckType === 'image'
                ? 'bg-amber-50/70 border-amber-200/80 shadow-2xs'
                : 'bg-slate-50/70 border-black/[0.05]'
            }`}>
              <div className="flex items-center justify-between mb-2">
                <span className="font-bold text-xs text-[#1A1D2E] flex items-center gap-1.5">
                  <ImageIcon className="w-3.5 h-3.5 text-emerald-600" />
                  真人图片
                </span>
                <span className="text-[10px] font-mono text-slate-400">消耗 6张/剧</span>
              </div>
              <div className="flex items-baseline justify-between">
                <span className="text-xl font-bold font-mono text-[#1A1D2E]">
                  <span className="text-xs font-normal text-slate-500">剩余 </span>{metrics.imageCount} <span className="text-xs font-normal text-slate-500">张</span>
                </span>
                <span className="text-xs font-semibold text-emerald-700 bg-emerald-50 px-2 py-0.5 rounded-md font-mono">
                  可供 {metrics.imageSupportableDramas} 部
                </span>
              </div>
            </div>

            {/* BGM Card */}
            <div className="p-4 rounded-xl border bg-slate-50/70 border-black/[0.05]">
              <div className="flex items-center justify-between mb-2">
                <span className="font-bold text-xs text-[#1A1D2E] flex items-center gap-1.5">
                  <Music className="w-3.5 h-3.5 text-purple-600" />
                  BGM 音频
                </span>
                <span className="text-[10px] text-slate-400">公共复用</span>
              </div>
              <div className="flex items-baseline justify-between">
                <span className="text-xl font-bold font-mono text-[#1A1D2E]">
                  {metrics.bgmCount} <span className="text-xs font-normal text-slate-500">首</span>
                </span>
                <span className="text-xs font-semibold text-purple-700 bg-purple-50 px-2 py-0.5 rounded-md">
                  全剧可复用
                </span>
              </div>
            </div>
          </div>
        </div>

        {/* Bottleneck Guidance Banner */}
        <div className="mt-4 pt-3 border-t border-black/[0.06] flex items-center justify-between">
          <div className="flex items-center gap-2 text-xs">
            <Info className="w-4 h-4 text-slate-400 shrink-0" />
            <span className="text-[#64748B]">
              <strong>产能调度建议：</strong> {metrics.shortageTip}
            </span>
          </div>

          <div className="flex items-center gap-2">
            <button
              onClick={() => handleOpenCategoryFolder('video')}
              className="text-[11px] font-bold text-slate-700 hover:text-indigo-600 flex items-center gap-1 cursor-pointer"
            >
              <FolderOpen className="w-3 h-3" />
              <span>补充视频</span>
            </button>
            <span className="text-slate-300">·</span>
            <button
              onClick={() => handleOpenCategoryFolder('image')}
              className="text-[11px] font-bold text-slate-700 hover:text-emerald-600 flex items-center gap-1 cursor-pointer"
            >
              <FolderOpen className="w-3 h-3" />
              <span>补充图片</span>
            </button>
          </div>
        </div>
      </div>

      {/* 2. CATEGORY SWITCHER & WINDOWS FOLDER QUICK OPEN BAR */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
        {/* Category Pills */}
        <div className="flex items-center gap-1.5 p-1 bg-slate-100/90 rounded-2xl border border-black/[0.04] w-fit">
          <button
            onClick={() => setSelectedCategory('ALL')}
            className={`px-3.5 py-1.5 rounded-xl text-xs font-bold transition-all cursor-pointer ${
              selectedCategory === 'ALL'
                ? 'bg-white text-[#1A1D2E] shadow-sm'
                : 'text-[#64748B] hover:text-[#1A1D2E]'
            }`}
          >
            全部资源 ({resources.length})
          </button>
          <button
            onClick={() => setSelectedCategory('lead_video')}
            className={`flex items-center gap-1.5 px-3.5 py-1.5 rounded-xl text-xs font-bold transition-all cursor-pointer ${selectedCategory === 'lead_video' ? 'bg-white text-[#1A1D2E] shadow-sm' : 'text-[#64748B] hover:text-[#1A1D2E]'}`}
          >
            <Video className="w-3.5 h-3.5 text-rose-600" />
            <span>引流视频 ({resources.filter((item) => item.category === 'lead_video').length})</span>
          </button>
          <button
            onClick={() => setSelectedCategory('real_video')}
            className={`flex items-center gap-1.5 px-3.5 py-1.5 rounded-xl text-xs font-bold transition-all cursor-pointer ${
              selectedCategory === 'real_video'
                ? 'bg-white text-[#1A1D2E] shadow-sm'
                : 'text-[#64748B] hover:text-[#1A1D2E]'
            }`}
          >
            <Video className="w-3.5 h-3.5 text-indigo-600" />
            <span>真人视频 ({metrics.totalVideoCount})</span>
          </button>
          <button
            onClick={() => setSelectedCategory('real_image')}
            className={`flex items-center gap-1.5 px-3.5 py-1.5 rounded-xl text-xs font-bold transition-all cursor-pointer ${
              selectedCategory === 'real_image'
                ? 'bg-white text-[#1A1D2E] shadow-sm'
                : 'text-[#64748B] hover:text-[#1A1D2E]'
            }`}
          >
            <ImageIcon className="w-3.5 h-3.5 text-emerald-600" />
            <span>真人图片 ({metrics.totalImageCount})</span>
          </button>
          <button
            onClick={() => setSelectedCategory('bgm')}
            className={`flex items-center gap-1.5 px-3.5 py-1.5 rounded-xl text-xs font-bold transition-all cursor-pointer ${
              selectedCategory === 'bgm'
                ? 'bg-white text-[#1A1D2E] shadow-sm'
                : 'text-[#64748B] hover:text-[#1A1D2E]'
            }`}
          >
            <Music className="w-3.5 h-3.5 text-purple-600" />
            <span>BGM ({metrics.bgmCount})</span>
          </button>
        </div>

        {/* Windows Folder Quick Open Actions */}
        <div className="flex items-center gap-2">
          <button
            onClick={() => handleOpenCategoryFolder('lead_video')}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-xl bg-white border border-black/[0.08] hover:bg-slate-50 text-[#1A1D2E] text-xs font-semibold shadow-2xs transition-all cursor-pointer"
          >
            <FolderOpen className="w-3.5 h-3.5 text-rose-600" />
            <span>打开引流目录</span>
          </button>
          <button
            onClick={() => handleOpenCategoryFolder('video')}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-xl bg-white border border-black/[0.08] hover:bg-slate-50 text-[#1A1D2E] text-xs font-semibold shadow-2xs transition-all cursor-pointer"
          >
            <FolderOpen className="w-3.5 h-3.5 text-indigo-600" />
            <span>打开视频目录</span>
          </button>
          <button
            onClick={() => handleOpenCategoryFolder('image')}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-xl bg-white border border-black/[0.08] hover:bg-slate-50 text-[#1A1D2E] text-xs font-semibold shadow-2xs transition-all cursor-pointer"
          >
            <FolderOpen className="w-3.5 h-3.5 text-emerald-600" />
            <span>打开图片目录</span>
          </button>
          <button
            onClick={() => handleOpenCategoryFolder('bgm')}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-xl bg-white border border-black/[0.08] hover:bg-slate-50 text-[#1A1D2E] text-xs font-semibold shadow-2xs transition-all cursor-pointer"
          >
            <FolderOpen className="w-3.5 h-3.5 text-purple-600" />
            <span>打开 BGM 目录</span>
          </button>
        </div>
      </div>

      {/* 3. SEARCH & TAG FILTER BAR */}
      <div className="bg-white p-3.5 rounded-2xl border border-black/[0.06] shadow-xs flex flex-col sm:flex-row items-center justify-between gap-3">
        <div className="relative w-full sm:w-80">
          <Search className="w-3.5 h-3.5 text-slate-400 absolute left-3 top-2.5" />
          <input
            type="text"
            placeholder="搜索物料文件名、特征标签..."
            value={searchTerm}
            onChange={e => setSearchTerm(e.target.value)}
            className="w-full pl-8 pr-3 py-1.5 rounded-xl border border-black/[0.08] bg-slate-50 text-xs font-medium text-[#1A1D2E] focus:bg-white focus:outline-none"
          />
        </div>

        {/* Tags filter chips */}
        <div className="flex items-center gap-1.5 overflow-x-auto w-full sm:w-auto pb-1 sm:pb-0 text-xs">
          <span className="text-slate-400 font-medium shrink-0 text-[11px]">标签:</span>
          <button
            onClick={() => setSelectedTag('ALL')}
            className={`px-2 py-0.5 rounded-md font-semibold text-[11px] shrink-0 cursor-pointer ${
              selectedTag === 'ALL'
                ? 'bg-[#1A1D2E] text-white'
                : 'bg-slate-100 text-slate-600 hover:bg-slate-200'
            }`}
          >
            全部
          </button>
          {allTags.map(t => (
            <button
              key={t}
              onClick={() => setSelectedTag(t)}
              className={`px-2 py-0.5 rounded-md font-semibold text-[11px] shrink-0 cursor-pointer ${
                selectedTag === t
                  ? 'bg-[#1A1D2E] text-[#DDFD00]'
                  : 'bg-slate-100 text-slate-600 hover:bg-slate-200'
              }`}
            >
              #{t}
            </button>
          ))}
        </div>
      </div>

      {/* 4. RESOURCE GRID */}
      <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 xl:grid-cols-5 2xl:grid-cols-6 gap-3">
        {filteredResources.map(res => {
          const isBgm = res.category === 'bgm';
          const isPlayingThis = playingBgmId === res.id;

          return (
            <div
              key={res.id}
              className="bg-white rounded-xl border border-black/[0.06] shadow-xs p-2.5 hover:shadow-md transition-all flex flex-col justify-between group min-w-0"
            >
              <div className="space-y-2">
                {/* Visual Thumbnail or Audio Card Header */}
                {res.category === 'real_video' || res.category === 'lead_video' ? (
                  <button
                    type="button"
                    onClick={() => setPreviewResource({
                      title: res.name, categoryName: res.categoryName, type: 'video', filePath: res.filePath,
                      fileSizeMb: res.fileSizeMb, resolution: res.resolution, durationText: formatDuration(res.durationSeconds),
                      tags: res.tags, thumbnailUrl: res.thumbnailUrl, mediaUrl: res.mediaUrl,
                    })}
                    className="relative rounded-lg overflow-hidden bg-slate-900 w-[108px] max-w-full aspect-[9/16] mx-auto flex items-center justify-center border border-black/[0.06] cursor-pointer"
                    title="预览详情"
                  >
                    {res.thumbnailUrl && <img src={res.thumbnailUrl} alt={res.name} className="absolute inset-0 w-full h-full object-cover opacity-80" />}
                    <div className="w-10 h-10 rounded-full bg-white/20 backdrop-blur-xs flex items-center justify-center text-white group-hover:scale-110 transition-transform">
                      <Play className="w-4 h-4 ml-0.5" />
                    </div>
                    <span className="absolute bottom-2 right-2 px-1.5 py-0.5 rounded bg-black/60 text-white font-mono text-[10px] backdrop-blur-xs">
                      {formatDuration(res.durationSeconds)}
                    </span>
                    <span className="absolute top-2 left-2 px-1.5 py-0.5 rounded bg-indigo-600/90 text-white font-bold text-[10px]">
                      {res.categoryName}
                    </span>
                  </button>
                ) : res.category === 'real_image' ? (
                  <button
                    type="button"
                    onClick={() => setPreviewResource({
                      title: res.name, categoryName: res.categoryName, type: 'image', filePath: res.filePath,
                      fileSizeMb: res.fileSizeMb, resolution: res.resolution, durationText: formatDuration(res.durationSeconds),
                      tags: res.tags, thumbnailUrl: res.thumbnailUrl, mediaUrl: res.mediaUrl,
                    })}
                    className="relative rounded-lg overflow-hidden bg-slate-950 w-[108px] max-w-full aspect-[9/16] mx-auto flex items-center justify-center border border-black/[0.06] cursor-pointer"
                    title="预览详情"
                  >
                    <img
                      src={res.thumbnailUrl || res.mediaUrl}
                      alt={res.name}
                      className="w-full h-full object-cover group-hover:scale-105 transition-transform duration-300"
                    />
                    <span className="absolute top-2 left-2 px-1.5 py-0.5 rounded bg-emerald-600/90 text-white font-bold text-[10px]">
                      真人图片
                    </span>
                  </button>
                ) : (
                  <div className="relative rounded-lg overflow-hidden bg-purple-950 p-3 w-[108px] max-w-full aspect-[9/16] mx-auto flex flex-col justify-between text-white">
                    <div className="flex items-center justify-between">
                      <span className="px-1.5 py-0.5 rounded bg-purple-500/30 text-purple-200 font-bold text-[10px]">
                        BGM 音频
                      </span>
                      <Volume2 className="w-3.5 h-3.5 text-purple-300" />
                    </div>
                    <div className="flex items-center justify-between">
                      <button
                        onClick={() => setPlayingBgmId(isPlayingThis ? null : res.id)}
                        className="w-9 h-9 rounded-full bg-[#DDFD00] text-[#1A1D2E] flex items-center justify-center font-bold hover:scale-105 transition-transform cursor-pointer"
                      >
                        {isPlayingThis ? <Pause className="w-4 h-4" /> : <Play className="w-4 h-4 ml-0.5" />}
                      </button>
                      <span className="font-mono text-[11px] text-purple-200">
                        {formatDuration(res.durationSeconds)}
                      </span>
                    </div>
                  </div>
                )}

                {/* Title and Specs */}
                <div>
                  <h4 className="font-bold text-xs text-[#1A1D2E] line-clamp-2 min-h-8 group-hover:text-indigo-600 transition-colors" title={res.name}>
                    {res.name}
                  </h4>
                  <p className="text-[11px] text-slate-500 font-mono mt-0.5">
                    {res.fileSizeMb} MB {res.resolution ? `· ${res.resolution}` : ''}
                  </p>
                  {res.probeStatus === 'pending' && (
                    <p className="text-[11px] text-indigo-600 mt-0.5">正在识别视频信息…</p>
                  )}
                  {res.probeStatus === 'failed' && (
                    <p className="text-[11px] text-amber-700 mt-0.5" title={res.probeError}>视频信息识别失败，不影响其他资料。</p>
                  )}
                </div>

                {/* Tags */}
                {res.tags && res.tags.length > 0 && (
                  <div className="flex flex-wrap gap-1">
                    {res.tags.slice(0, 2).map(t => (
                      <span key={t} className="px-1.5 py-0.2 rounded bg-slate-100 text-slate-600 text-[10px] font-medium">
                        #{t}
                      </span>
                    ))}
                  </div>
                )}
              </div>

            </div>
          );
        })}
      </div>

      {filteredResources.length === 0 && (
        <div className="py-16 text-center text-slate-400 text-xs bg-white rounded-2xl border border-black/[0.06]">
          没有找到符合筛选条件的生产物料
        </div>
      )}

      {/* Light Media Preview Modal */}
      <ResourcePreviewModal
        isOpen={!!previewResource}
        onClose={() => setPreviewResource(null)}
        resource={previewResource}
        onOpenFolder={onOpenFolder}
      />
    </div>
  );
};
