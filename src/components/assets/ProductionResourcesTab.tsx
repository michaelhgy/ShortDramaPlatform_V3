import { SceneryWorkbench } from './SceneryWorkbench';
import React, { useEffect, useMemo, useState } from 'react';
import type { ProductionResourceItem, ResourceCategory, ResourceInventoryMetrics } from '../../assetsTypes';
import { FolderOpen, Image as ImageIcon, Play, Search, Video } from 'lucide-react';
import { openProductionResourceFolder } from '../../services/assetsCenterService';
import { ResourcePreviewModal, type PreviewResourceData } from './modals/ResourcePreviewModal';
import { formatElapsedSeconds } from '../../utils/duration';

interface Props {
  sceneryOpenRequest?: number;
  resources: ProductionResourceItem[];
  metrics: ResourceInventoryMetrics;
  onOpenFolder: (path: string) => void;
  onAddResource: (resource: Omit<ProductionResourceItem, 'id' | 'addedAt'>) => void;
  onShowToast: (msg: string) => void;
}

const categories = [
  { id: 'scenery_video', name: '风景视频', folderLabel: '打开风景目录', Icon: Video, color: 'text-indigo-600' },
  { id: 'real_image', name: '真人图片', folderLabel: '打开图片目录', Icon: ImageIcon, color: 'text-emerald-600' },
  { id: 'lead_video', name: '引流视频', folderLabel: '打开引流目录', Icon: Video, color: 'text-rose-600' },
] as const;

export const ProductionResourcesTab: React.FC<Props> = ({ resources, metrics, onOpenFolder, onShowToast, sceneryOpenRequest = 0 }) => {
  const [selectedCategory, setSelectedCategory] = useState<ResourceCategory | 'ALL'>(sceneryOpenRequest ? 'scenery_video' : 'ALL');
  const [searchTerm, setSearchTerm] = useState('');
  const [selectedTag, setSelectedTag] = useState('ALL');
  const [previewResource, setPreviewResource] = useState<PreviewResourceData | null>(null);
  useEffect(() => {
    if (!sceneryOpenRequest) return;
    setSelectedCategory('scenery_video'); setSearchTerm(''); setSelectedTag('ALL'); setPreviewResource(null);
  }, [sceneryOpenRequest]);
  const allTags = useMemo(() => [...new Set(resources.flatMap(item => item.tags || []))], [resources]);
  const filteredResources = useMemo(() => resources.filter(item =>
    (selectedCategory === 'ALL' || item.category === selectedCategory)
    && (!searchTerm || item.name.toLowerCase().includes(searchTerm.toLowerCase()) || item.tags?.some(tag => tag.toLowerCase().includes(searchTerm.toLowerCase())))
    && (selectedTag === 'ALL' || item.tags?.includes(selectedTag))), [resources, selectedCategory, searchTerm, selectedTag]);

  const openCategory = async (category: ResourceCategory) => {
    try { await openProductionResourceFolder(category); }
    catch (error) { onShowToast(error instanceof Error ? error.message : '目录打开失败。'); }
  };
  const preview = (item: ProductionResourceItem) => setPreviewResource({
    title: item.name, categoryName: item.categoryName, type: item.category === 'real_image' ? 'image' : 'video',
    filePath: item.filePath, fileSizeMb: item.fileSizeMb, resolution: item.resolution,
    durationText: formatElapsedSeconds(item.durationSeconds, '—'), tags: item.tags,
    thumbnailUrl: item.thumbnailUrl, mediaUrl: item.mediaUrl,
  });

  return <div className="space-y-6" data-testid="production-resources">
    <div className="rounded-2xl border border-black/[0.06] bg-white p-6 shadow-xs">
      <div className="mb-4 flex flex-wrap items-center justify-between gap-2">
        <div><h2 className="text-sm font-black text-[#1A1D2E]">生产资源储备</h2><p className="mt-1 text-xs text-[#64748B]">处理后的风景用于制作模板，点击“风景视频”管理原片裁切与可用素材。</p></div>
        <span className="text-xs text-[#64748B]">共 <strong className="font-mono text-lg text-[#1A1D2E]">{metrics.totalResourceCount}</strong> 项资源</span>
      </div>
      <div className="grid gap-3 sm:grid-cols-3">
        {categories.map(({ id, name, Icon, color }) => <div key={id} className="rounded-xl border border-black/[0.05] bg-slate-50/70 p-4">
          <div className="mb-2 flex items-center gap-1.5 text-xs font-bold text-[#1A1D2E]"><Icon className={`h-3.5 w-3.5 ${color}`} />{name}</div>
          <div className="flex items-baseline justify-between gap-2"><span className="font-mono text-xl font-bold text-[#1A1D2E]">{id === 'scenery_video' ? metrics.videoCount : id === 'real_image' ? metrics.imageCount : metrics.leadVideoCount}<span className="ml-1 text-xs font-normal text-[#64748B]">{id === 'real_image' ? '张可用' : '条可用'}</span></span><span className="text-[11px] text-[#64748B]">共 {id === 'scenery_video' ? metrics.totalVideoCount : id === 'real_image' ? metrics.totalImageCount : metrics.leadVideoCount} {id === 'real_image' ? '张' : '条'}</span></div>
        </div>)}
      </div>
    </div>

    <div className="flex flex-wrap items-center justify-between gap-3">
      <div className="flex flex-wrap items-center gap-1.5 rounded-2xl border border-black/[0.04] bg-slate-100/90 p-1" aria-label="资源分类">
        <button type="button" onClick={() => setSelectedCategory('ALL')} aria-pressed={selectedCategory === 'ALL'} className={`rounded-xl px-3.5 py-1.5 text-xs font-bold ${selectedCategory === 'ALL' ? 'bg-white text-[#1A1D2E] shadow-sm' : 'text-[#64748B] hover:text-[#1A1D2E]'}`}>全部资源 ({resources.length})</button>
        {categories.map(({ id, name, Icon, color }) => <button key={id} type="button" onClick={() => setSelectedCategory(id)} aria-pressed={selectedCategory === id} className={`flex items-center gap-1.5 rounded-xl px-3.5 py-1.5 text-xs font-bold ${selectedCategory === id ? 'bg-white text-[#1A1D2E] shadow-sm' : 'text-[#64748B] hover:text-[#1A1D2E]'}`}><Icon className={`h-3.5 w-3.5 ${color}`} />{name} ({resources.filter(item => item.category === id).length})</button>)}
      </div>
      <div className="flex flex-wrap items-center gap-2">
        {categories.map(({ id, folderLabel, color }) => <button key={id} type="button" onClick={() => void openCategory(id)} className="flex items-center gap-1.5 rounded-xl border border-black/[0.08] bg-white px-3 py-1.5 text-xs font-semibold text-[#1A1D2E] shadow-2xs hover:bg-slate-50"><FolderOpen className={`h-3.5 w-3.5 ${color}`} />{folderLabel}</button>)}
      </div>
    </div>

    <div className="flex flex-col items-center justify-between gap-3 rounded-2xl border border-black/[0.06] bg-white p-3.5 shadow-xs sm:flex-row">
      <div className="relative w-full sm:w-80"><Search className="absolute left-3 top-2.5 h-3.5 w-3.5 text-slate-400" /><input type="text" aria-label="搜索生产资源" placeholder="搜索物料文件名、特征标签..." value={searchTerm} onChange={event => setSearchTerm(event.target.value)} className="w-full rounded-xl border border-black/[0.08] bg-slate-50 py-1.5 pl-8 pr-3 text-xs font-medium text-[#1A1D2E] focus:bg-white focus:outline-none" /></div>
      <div className="flex w-full items-center gap-1.5 overflow-x-auto text-xs sm:w-auto"><span className="shrink-0 text-[11px] text-slate-400">标签:</span>{['ALL', ...allTags].map(tag => <button key={tag} type="button" onClick={() => setSelectedTag(tag)} className={`shrink-0 rounded-md px-2 py-0.5 text-[11px] font-semibold ${selectedTag === tag ? 'bg-[#1A1D2E] text-[#DDFD00]' : 'bg-slate-100 text-slate-600 hover:bg-slate-200'}`}>{tag === 'ALL' ? '全部' : `#${tag}`}</button>)}</div>
    </div>

    {selectedCategory === 'scenery_video' ? <SceneryWorkbench showToast={onShowToast} openReadyRequest={sceneryOpenRequest}/> : <><div className="grid grid-cols-2 gap-3 sm:grid-cols-3 md:grid-cols-4 xl:grid-cols-5 2xl:grid-cols-6">
      {filteredResources.map(item => <article key={item.id} data-resource-id={item.id} className="group flex min-w-0 flex-col rounded-xl border border-black/[0.06] bg-white p-2.5 shadow-xs transition-all hover:shadow-md">
        <button type="button" onClick={() => preview(item)} aria-label={`预览 ${item.name}`} className="relative mx-auto flex aspect-[9/16] w-[108px] max-w-full items-center justify-center overflow-hidden rounded-lg border border-black/[0.06] bg-slate-900">
          {(item.thumbnailUrl || item.category === 'real_image' && item.mediaUrl) && <img src={item.thumbnailUrl || item.mediaUrl} alt="" className="absolute inset-0 h-full w-full object-contain" />}
          {item.category !== 'real_image' && <span className="flex h-9 w-9 items-center justify-center rounded-full bg-white/30 text-white backdrop-blur-xs"><Play className="ml-0.5 h-4 w-4" /></span>}
          {item.category !== 'real_image' && <span className="absolute bottom-2 right-2 rounded bg-black/60 px-1.5 py-0.5 font-mono text-[10px] text-white">{formatElapsedSeconds(item.durationSeconds, '—')}</span>}
          <span className="absolute left-2 top-2 rounded bg-[#1A1D2E]/85 px-1.5 py-0.5 text-[10px] font-bold text-white">{item.categoryName}</span>
        </button>
        <h4 title={item.name} className="mt-2 line-clamp-2 min-h-8 break-all text-xs font-bold text-[#1A1D2E]">{item.name}</h4>
        <p className="mt-0.5 text-[11px] text-slate-500">{item.fileSizeMb} MB {item.resolution ? `· ${item.resolution}` : ''}</p>
        {(item.category === 'scenery_video' || item.category === 'real_image' && typeof item.usageLimit === 'number') && <p className="text-[11px] text-slate-600 mt-1">已用 {item.usageCount || 0}/{item.usageLimit || 5} · 占用 {item.reservedCount || 0} · 剩余 {item.remainingCount || 0}</p>}
        {item.cleanupError && <p role="alert" className="mt-1 text-[11px] text-amber-700">自动清理未完成：{item.cleanupError}</p>}
        {item.probeStatus === 'pending' && <p className="mt-0.5 text-[11px] text-indigo-600">正在识别视频信息…</p>}
        {item.probeStatus === 'failed' && <p title={item.probeError} className="mt-0.5 text-[11px] text-amber-700">视频信息识别失败，不影响其他资料。</p>}
        {item.tags?.length ? <div className="mt-2 flex flex-wrap gap-1">{item.tags.slice(0, 2).map(tag => <span key={tag} className="rounded bg-slate-100 px-1.5 text-[10px] text-slate-600">#{tag}</span>)}</div> : null}
      </article>)}
    </div>
    {!filteredResources.length && <div className="rounded-2xl border border-black/[0.06] bg-white py-16 text-center text-xs text-slate-400">没有找到符合筛选条件的生产物料</div>}
    </>}
    <ResourcePreviewModal isOpen={!!previewResource} onClose={() => setPreviewResource(null)} resource={previewResource} onOpenFolder={onOpenFolder} />
  </div>;
};
