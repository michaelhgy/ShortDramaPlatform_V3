import React, { useState, useMemo, useRef } from 'react';
import { DramaContentProfile, DramaBusinessItem, ViralAssetItem } from '../../assetsTypes';
import {
  Film,
  FolderOpen,
  Image as ImageIcon,
  Video,
  FileText,
  Sparkles,
  Search,
  CheckCircle2,
  AlertCircle,
  Copy,
  Check,
  Play,
  Layers,
  ChevronRight,
  ExternalLink,
  Plus,
  RefreshCw,
  Clock,
  HardDrive,
  Tag,
  Upload,
  X,
  Edit2,
  Save,
  Filter,
  ChevronLeft,
} from 'lucide-react';
import { ResourcePreviewModal, PreviewResourceData } from './modals/ResourcePreviewModal';
import { createV2DramaProfile, uploadV2DramaCover } from '../../api/v2Catalog';

interface DramaLibraryTabProps {
  profiles: DramaContentProfile[];
  dramas: DramaBusinessItem[];
  viralAssets: ViralAssetItem[];
  selectedDramaId?: string;
  onSelectDrama?: (dramaId: string) => void;
  onUpdateProfiles?: (profiles: DramaContentProfile[]) => void;
  onOpenFolder: (path: string) => void;
  onShowToast: (msg: string) => void;
}

export const DramaLibraryTab: React.FC<DramaLibraryTabProps> = ({
  profiles,
  dramas,
  viralAssets,
  selectedDramaId,
  onSelectDrama,
  onUpdateProfiles,
  onOpenFolder,
  onShowToast,
}) => {
  const [currentDramaId, setCurrentDramaId] = useState<string>(
    selectedDramaId || profiles[0]?.dramaId || dramas[0]?.id || 'drama-01'
  );
  const [searchTerm, setSearchTerm] = useState('');
  const [selectedTheaterFilter, setSelectedTheaterFilter] = useState('ALL');
  const [activeSubTab, setActiveSubTab] = useState<'master_video' | 'covers' | 'plot_aa' | 'viral_clips'>('master_video');
  const [previewResource, setPreviewResource] = useState<PreviewResourceData | null>(null);
  const [copiedPath, setCopiedPath] = useState(false);

  // Drama list pagination
  const [dramaListPage, setDramaListPage] = useState(1);
  const DRAMAS_PER_PAGE = 7;

  // New tag input
  const [newTagInput, setNewTagInput] = useState('');
  const [isAddingTag, setIsAddingTag] = useState(false);

  // Inline synopsis & character edit mode
  const [isEditingPlot, setIsEditingPlot] = useState(false);
  const [plotSynopsis, setPlotSynopsis] = useState('');
  const [plotCharacterNotes, setPlotCharacterNotes] = useState('');

  // Hidden file input for cover replacement
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [coverTarget, setCoverTarget] = useState<'main' | 'horizontal'>('main');

  // Sync selectedDramaId if passed from outside
  React.useEffect(() => {
    if (selectedDramaId) {
      setCurrentDramaId(selectedDramaId);
    }
  }, [selectedDramaId]);

  // Current active drama profile
  const currentProfile = useMemo(() => {
    return profiles.find(p => p.dramaId === currentDramaId);
  }, [profiles, currentDramaId]);

  // Reset plot states when currentProfile changes
  React.useEffect(() => {
    if (currentProfile?.plotKnowledgeBase) {
      setPlotSynopsis(currentProfile.plotKnowledgeBase.synopsis || '');
      setPlotCharacterNotes(currentProfile.plotKnowledgeBase.characterNotes || '');
    }
    setIsEditingPlot(false);
    setIsAddingTag(false);
  }, [currentProfile]);

  // Current active drama business item
  const currentDramaBusiness = useMemo(() => {
    return dramas.find(d => d.id === currentDramaId);
  }, [dramas, currentDramaId]);

  // Associated viral assets
  const associatedVirals = useMemo(() => {
    return viralAssets.filter(v => v.sourceDramaId === currentDramaId);
  }, [viralAssets, currentDramaId]);

  // Distinct theaters from dramas
  const theaterOptions = useMemo(() => {
    const set = new Set<string>();
    dramas.forEach(d => set.add(d.theaterName));
    return Array.from(set);
  }, [dramas]);

  // Filtered drama list for left selector
  const filteredDramas = useMemo(() => {
    return dramas.filter(d => {
      const matchSearch =
        !searchTerm ||
        d.currentName.toLowerCase().includes(searchTerm.toLowerCase()) ||
        d.historyNames.some(h => h.toLowerCase().includes(searchTerm.toLowerCase())) ||
        d.theaterName.toLowerCase().includes(searchTerm.toLowerCase());
      const matchTheater = selectedTheaterFilter === 'ALL' || d.theaterName === selectedTheaterFilter;
      return matchSearch && matchTheater;
    }).sort((a, b) => Number(Boolean(b.hasContentProfile || profiles.some((profile) => profile.dramaId === b.id))) - Number(Boolean(a.hasContentProfile || profiles.some((profile) => profile.dramaId === a.id))) || a.currentName.localeCompare(b.currentName, 'zh-CN'));
  }, [dramas, profiles, searchTerm, selectedTheaterFilter]);

  // Paginated dramas
  const totalPages = Math.max(1, Math.ceil(filteredDramas.length / DRAMAS_PER_PAGE));
  const paginatedDramas = useMemo(() => {
    const start = (dramaListPage - 1) * DRAMAS_PER_PAGE;
    return filteredDramas.slice(start, start + DRAMAS_PER_PAGE);
  }, [filteredDramas, dramaListPage]);

  const handleCopyFolder = (path: string) => {
    navigator.clipboard.writeText(path);
    setCopiedPath(true);
    onShowToast('已复制 Windows 文件夹路径');
    setTimeout(() => setCopiedPath(false), 2000);
  };

  // Cover image replacement handler
  const triggerCoverPicker = (target: 'main' | 'horizontal') => {
    setCoverTarget(target);
    fileInputRef.current?.click();
  };

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file || !currentProfile || !currentDramaBusiness) return;

    const objectUrl = URL.createObjectURL(file);
    const reader = new FileReader();
    reader.onload = () => {
      const contentBase64 = String(reader.result || '');
      uploadV2DramaCover(currentDramaBusiness.id, { filename: file.name, content_base64: contentBase64 })
        .then((saved) => {
          const updatedProfiles = profiles.map(p => p.dramaId === currentProfile.dramaId ? {
            ...p,
            cover: { ...p.cover, ...(coverTarget === 'main' ? { mainCoverUrl: objectUrl } : { horizontalPosterUrl: objectUrl }), filePath: saved.file_path, updateTime: new Date().toISOString().slice(0, 16).replace('T', ' ') },
          } : p);
          if (onUpdateProfiles) onUpdateProfiles(updatedProfiles);
          onShowToast(`已保存《${currentProfile.dramaCurrentName}》封面`);
        })
        .catch((error: unknown) => onShowToast(error instanceof Error ? error.message : '封面保存失败。'));
    };
    reader.readAsDataURL(file);

    e.target.value = '';
  };

  // Tag Management
  const handleAddTag = () => {
    if (!newTagInput.trim() || !currentProfile) return;
    const tag = newTagInput.trim();
    const existingTags = currentProfile.tags || [];
    if (!existingTags.includes(tag)) {
      const updatedProfiles = profiles.map(p => {
        if (p.dramaId === currentProfile.dramaId) {
          return { ...p, tags: [...existingTags, tag] };
        }
        return p;
      });
      if (onUpdateProfiles) onUpdateProfiles(updatedProfiles);
      onShowToast(`已添加标签「${tag}」`);
    }
    setNewTagInput('');
    setIsAddingTag(false);
  };

  const handleRemoveTag = (tagToRemove: string) => {
    if (!currentProfile) return;
    const updatedProfiles = profiles.map(p => {
      if (p.dramaId === currentProfile.dramaId) {
        return { ...p, tags: (p.tags || []).filter(t => t !== tagToRemove) };
      }
      return p;
    });
    if (onUpdateProfiles) onUpdateProfiles(updatedProfiles);
    onShowToast(`已移除标签「${tagToRemove}」`);
  };

  // Save Plot knowledge
  const handleSavePlot = () => {
    if (!currentProfile) return;
    const updatedProfiles = profiles.map(p => {
      if (p.dramaId === currentProfile.dramaId) {
        return {
          ...p,
          plotKnowledgeBase: {
            ...p.plotKnowledgeBase,
            synopsis: plotSynopsis,
            characterNotes: plotCharacterNotes,
          },
        };
      }
      return p;
    });
    if (onUpdateProfiles) onUpdateProfiles(updatedProfiles);
    setIsEditingPlot(false);
    onShowToast('已保存剧情知识库与人物小传');
  };

  return (
    <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 items-start">
      {/* Hidden file input for cover replacement */}
      <input
        ref={fileInputRef}
        type="file"
        accept="image/*"
        className="hidden"
        onChange={handleFileChange}
      />

      {/* LEFT COLUMN: Drama Selector List with Theater Filter & Pagination */}
      <div className="lg:col-span-4 space-y-4">
        <div className="bg-white rounded-2xl border border-black/[0.06] shadow-xs p-4 space-y-3">
          <div className="flex items-center justify-between">
            <h3 className="font-bold text-sm text-[#1A1D2E] flex items-center gap-2">
              <Film className="w-4 h-4 text-slate-600" />
              <span>选择剧集资料库</span>
            </h3>
            <span className="text-xs font-mono text-[#64748B] font-bold">
              共 {filteredDramas.length} 部
            </span>
          </div>

          {/* Search Box */}
          <div className="relative">
            <Search className="w-3.5 h-3.5 text-slate-400 absolute left-3 top-2.5" />
            <input
              type="text"
              placeholder="搜索剧名、历史别名..."
              value={searchTerm}
              onChange={e => {
                setSearchTerm(e.target.value);
                setDramaListPage(1);
              }}
              className="w-full pl-8 pr-3 py-1.5 rounded-xl border border-black/[0.08] bg-slate-50 text-xs font-medium text-[#1A1D2E] focus:bg-white focus:outline-none"
            />
          </div>

          {/* Theater Filter */}
          <div className="flex items-center gap-1.5 text-xs text-[#64748B]">
            <span className="text-[11px] font-semibold text-slate-400">剧场:</span>
            <select
              value={selectedTheaterFilter}
              onChange={e => {
                setSelectedTheaterFilter(e.target.value);
                setDramaListPage(1);
              }}
              className="flex-1 px-2.5 py-1 rounded-xl border border-black/[0.08] bg-slate-50 text-xs font-semibold text-[#1A1D2E] focus:outline-none"
            >
              <option value="ALL">全部剧场</option>
              {theaterOptions.map(t => (
                <option key={t} value={t}>
                  {t}
                </option>
              ))}
            </select>
          </div>

          {/* Drama Cards List */}
          <div className="space-y-1.5 min-h-[360px]">
            {paginatedDramas.length > 0 ? (
              paginatedDramas.map(drama => {
                const isSelected = drama.id === currentDramaId;
                const hasProfile = profiles.some(p => p.dramaId === drama.id);

                return (
                  <button
                    key={drama.id}
                    onClick={() => {
                      setCurrentDramaId(drama.id);
                      if (onSelectDrama) onSelectDrama(drama.id);
                    }}
                    className={`w-full text-left p-3 rounded-xl border transition-all cursor-pointer flex items-center justify-between group ${
                      isSelected
                        ? 'bg-[#1A1D2E] text-white border-[#1A1D2E] shadow-sm'
                        : 'bg-slate-50/70 hover:bg-slate-100/80 text-slate-800 border-black/[0.04]'
                    }`}
                  >
                    <div className="space-y-1 min-w-0 pr-2">
                      <div className="flex items-center gap-1.5">
                        <span className={`font-bold text-xs truncate ${isSelected ? 'text-white' : 'text-[#1A1D2E]'}`}>
                          {drama.currentName}
                        </span>
                      </div>

                      <div className="flex items-center gap-2 text-[11px]">
                        <span className={isSelected ? 'text-slate-300' : 'text-[#64748B]'}>
                          {drama.theaterName}
                        </span>
                        <span className={isSelected ? 'text-slate-500' : 'text-slate-300'}>·</span>
                        {hasProfile ? (
                          <span className={`font-medium ${isSelected ? 'text-[#DDFD00]' : 'text-emerald-700 font-semibold'}`}>
                            资料就绪
                          </span>
                        ) : (
                          <span className={isSelected ? 'text-slate-400' : 'text-slate-400'}>
                            待建档
                          </span>
                        )}
                      </div>
                    </div>

                    <ChevronRight
                      className={`w-4 h-4 shrink-0 transition-transform ${
                        isSelected ? 'text-[#DDFD00] translate-x-0.5' : 'text-slate-400 group-hover:translate-x-0.5'
                      }`}
                    />
                  </button>
                );
              })
            ) : (
              <div className="py-8 text-center text-slate-400 text-xs">
                未找到匹配剧集
              </div>
            )}
          </div>

          {/* Left List Pagination */}
          {totalPages > 1 && (
            <div className="pt-2 border-t border-black/[0.06] flex items-center justify-between text-xs text-[#64748B]">
              <span>第 {dramaListPage} / {totalPages} 页</span>
              <div className="flex items-center gap-1">
                <button
                  onClick={() => setDramaListPage(prev => Math.max(1, prev - 1))}
                  disabled={dramaListPage === 1}
                  className="p-1 rounded bg-slate-100 hover:bg-slate-200 disabled:opacity-40 cursor-pointer"
                >
                  <ChevronLeft className="w-3.5 h-3.5" />
                </button>
                <button
                  onClick={() => setDramaListPage(prev => Math.min(totalPages, prev + 1))}
                  disabled={dramaListPage === totalPages}
                  className="p-1 rounded bg-slate-100 hover:bg-slate-200 disabled:opacity-40 cursor-pointer"
                >
                  <ChevronRight className="w-3.5 h-3.5" />
                </button>
              </div>
            </div>
          )}
        </div>
      </div>

      {/* RIGHT COLUMN: Drama Detail Profile */}
      <div className="lg:col-span-8 space-y-5">
        {currentProfile ? (
          <>
            {/* Header Hero Card for Current Drama */}
            <div className="bg-white rounded-2xl border border-black/[0.06] shadow-xs p-5 relative overflow-hidden space-y-4">
              <div className="flex flex-col sm:flex-row sm:items-start justify-between gap-4">
                <div className="flex items-start gap-4">
                  {/* Poster Thumbnail with replace trigger */}
                  <div
                    onClick={() => triggerCoverPicker('main')}
                    className="w-16 h-22 rounded-xl overflow-hidden shadow-sm bg-slate-900 border border-black/10 shrink-0 relative group cursor-pointer"
                    title="点击更换竖版封面"
                  >
                    <img
                      src={currentProfile.cover?.mainCoverUrl || 'https://images.unsplash.com/photo-1578632767115-351597cf2477?w=300&auto=format&fit=crop&q=80'}
                      alt={currentProfile.dramaCurrentName}
                      className="w-full h-full object-cover"
                    />
                    <div className="absolute inset-0 bg-black/50 opacity-0 group-hover:opacity-100 flex flex-col items-center justify-center transition-opacity text-white">
                      <Upload className="w-3.5 h-3.5 mb-0.5" />
                      <span className="text-[9px] font-semibold">换封面</span>
                    </div>
                  </div>

                  <div className="space-y-1.5">
                    <div className="flex flex-wrap items-center gap-2">
                      <h2 className="text-base font-black text-[#1A1D2E]">
                        {currentProfile.dramaCurrentName}
                      </h2>
                      <span className="px-2 py-0.5 rounded-full bg-slate-100 text-slate-700 text-[11px] font-semibold">
                        {currentProfile.theaterName}
                      </span>
                      {currentProfile.category && (
                        <span className="px-2 py-0.5 rounded-full bg-indigo-50 text-indigo-700 text-[11px] font-semibold">
                          {currentProfile.category}
                        </span>
                      )}
                    </div>

                    {/* Historical aliases display */}
                    {currentDramaBusiness && currentDramaBusiness.historyNames.length > 0 && (
                      <div className="flex items-center gap-1.5 text-[11px] text-[#64748B]">
                        <span>历史剧名:</span>
                        <div className="flex flex-wrap gap-1">
                          {currentDramaBusiness.historyNames.map((h, i) => (
                            <span key={i} className="px-1.5 py-0.2 rounded bg-slate-100 text-slate-600 font-mono">
                              {h}
                            </span>
                          ))}
                        </div>
                      </div>
                    )}

                    <div className="flex items-center gap-4 text-xs text-[#64748B] pt-0.5">
                      <span className="flex items-center gap-1">
                        <Film className="w-3.5 h-3.5 text-slate-400" />
                        <span>共 {currentProfile.totalEpisodes || currentProfile.masterVideoPackage.totalFiles} 集原片</span>
                      </span>
                      <span className="flex items-center gap-1">
                        <HardDrive className="w-3.5 h-3.5 text-slate-400" />
                        <span>{currentProfile.masterVideoPackage.totalSizeGb} GB</span>
                      </span>
                      <span className="flex items-center gap-1">
                        <Clock className="w-3.5 h-3.5 text-slate-400" />
                        <span>更新于 {currentProfile.updatedAt}</span>
                      </span>
                    </div>
                  </div>
                </div>

                {/* Primary Action: Open Windows Folder */}
                <div className="flex items-center gap-2 shrink-0">
                  <button
                    onClick={() => onOpenFolder(currentProfile.masterVideoPackage.folderPath)}
                    className="flex items-center gap-1.5 px-3.5 py-2 rounded-xl bg-[#1A1D2E] text-[#DDFD00] hover:bg-black/90 active:scale-[0.98] text-xs font-bold shadow-xs transition-all cursor-pointer"
                  >
                    <FolderOpen className="w-3.5 h-3.5" />
                    <span>打开 Windows 原片目录</span>
                  </button>
                </div>
              </div>

              {/* Tags Strip (Add / Delete Tags) */}
              <div className="pt-2 border-t border-black/[0.04] flex flex-wrap items-center gap-1.5 text-xs">
                <span className="text-[11px] font-semibold text-slate-400 flex items-center gap-1">
                  <Tag className="w-3 h-3" />
                  <span>题材标签:</span>
                </span>

                {(currentProfile.tags || ['战神归来', '极道爽剧', '打脸逆袭']).map(t => (
                  <span
                    key={t}
                    className="inline-flex items-center gap-1 px-2 py-0.5 rounded-lg bg-slate-100 text-slate-700 text-[11px] font-medium group"
                  >
                    <span>#{t}</span>
                    <button
                      onClick={() => handleRemoveTag(t)}
                      className="text-slate-400 hover:text-rose-600 transition-colors cursor-pointer"
                      title="删除标签"
                    >
                      <X className="w-3 h-3" />
                    </button>
                  </span>
                ))}

                {isAddingTag ? (
                  <div className="inline-flex items-center gap-1">
                    <input
                      type="text"
                      placeholder="标签名..."
                      value={newTagInput}
                      onChange={e => setNewTagInput(e.target.value)}
                      onKeyDown={e => {
                        if (e.key === 'Enter') handleAddTag();
                      }}
                      className="px-2 py-0.5 rounded-lg border border-black/[0.1] bg-white text-[11px] w-20 focus:outline-none"
                      autoFocus
                    />
                    <button
                      onClick={handleAddTag}
                      className="px-2 py-0.5 rounded-lg bg-[#1A1D2E] text-white text-[10px] font-bold cursor-pointer"
                    >
                      添加
                    </button>
                    <button
                      onClick={() => setIsAddingTag(false)}
                      className="p-0.5 text-slate-400 hover:text-slate-600 cursor-pointer"
                    >
                      <X className="w-3 h-3" />
                    </button>
                  </div>
                ) : (
                  <button
                    onClick={() => setIsAddingTag(true)}
                    className="inline-flex items-center gap-0.5 px-2 py-0.5 rounded-lg border border-dashed border-black/20 text-slate-500 hover:text-slate-800 hover:border-black/40 text-[11px] font-semibold transition-colors cursor-pointer"
                  >
                    <Plus className="w-3 h-3" />
                    <span>加标签</span>
                  </button>
                )}
              </div>

              {/* Sub Navigation Bar for Drama Profile */}
              <div className="pt-2 border-t border-black/[0.06] flex flex-wrap items-center gap-2">
                <button
                  onClick={() => setActiveSubTab('master_video')}
                  className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-bold transition-all cursor-pointer ${
                    activeSubTab === 'master_video'
                      ? 'bg-[#1A1D2E] text-white shadow-2xs'
                      : 'text-slate-600 hover:bg-slate-100'
                  }`}
                >
                  <Video className="w-3.5 h-3.5" />
                  <span>原片视频库 ({currentProfile.masterVideoPackage.totalFiles} 集)</span>
                </button>

                <button
                  onClick={() => setActiveSubTab('covers')}
                  className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-bold transition-all cursor-pointer ${
                    activeSubTab === 'covers'
                      ? 'bg-[#1A1D2E] text-white shadow-2xs'
                      : 'text-slate-600 hover:bg-slate-100'
                  }`}
                >
                  <ImageIcon className="w-3.5 h-3.5" />
                  <span>剧集封面物料</span>
                </button>

                <button
                  onClick={() => setActiveSubTab('plot_aa')}
                  className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-bold transition-all cursor-pointer ${
                    activeSubTab === 'plot_aa'
                      ? 'bg-[#1A1D2E] text-white shadow-2xs'
                      : 'text-slate-600 hover:bg-slate-100'
                  }`}
                >
                  <FileText className="w-3.5 h-3.5" />
                  <span>剧情概要 · A+A 知识库</span>
                </button>

                <button
                  onClick={() => setActiveSubTab('viral_clips')}
                  className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-bold transition-all cursor-pointer ${
                    activeSubTab === 'viral_clips'
                      ? 'bg-[#1A1D2E] text-white shadow-2xs'
                      : 'text-slate-600 hover:bg-slate-100'
                  }`}
                >
                  <Sparkles className="w-3.5 h-3.5 text-amber-500" />
                  <span>关联爆款资产 ({associatedVirals.length})</span>
                </button>
              </div>
            </div>

            {/* TAB CONTENT 1: MASTER VIDEO PACKAGE */}
            {activeSubTab === 'master_video' && (
              <div className="bg-white rounded-2xl border border-black/[0.06] shadow-xs p-5 space-y-4">
                {/* Folder Path Bar */}
                <div className="p-3.5 rounded-xl bg-slate-50 border border-black/[0.06] flex flex-col sm:flex-row sm:items-center justify-between gap-2.5 text-xs">
                  <div className="flex items-center gap-2">
                    <FolderOpen className="w-4 h-4 text-slate-500 shrink-0" />
                    <div>
                      <span className="font-semibold text-[#1A1D2E] mr-2">原片存储位置:</span>
                      <code className="font-mono text-slate-600 bg-white px-2 py-0.5 rounded border border-black/[0.06] select-all">
                        {currentProfile.masterVideoPackage.folderPath}
                      </code>
                    </div>
                  </div>
                  <div className="flex items-center gap-2 shrink-0">
                    <button
                      onClick={() => handleCopyFolder(currentProfile.masterVideoPackage.folderPath)}
                      className="flex items-center gap-1 px-2.5 py-1 rounded-lg bg-white border border-black/[0.08] hover:bg-slate-100 text-slate-700 font-medium transition-colors cursor-pointer text-[11px]"
                    >
                      {copiedPath ? <Check className="w-3 h-3 text-emerald-600" /> : <Copy className="w-3 h-3" />}
                      <span>{copiedPath ? '已复制' : '复制路径'}</span>
                    </button>
                    <button
                      onClick={() => onOpenFolder(currentProfile.masterVideoPackage.folderPath)}
                      className="flex items-center gap-1 px-2.5 py-1 rounded-lg bg-[#1A1D2E] text-[#DDFD00] font-bold hover:bg-black transition-colors cursor-pointer text-[11px]"
                    >
                      <FolderOpen className="w-3 h-3" />
                      <span>打开本地目录</span>
                    </button>
                  </div>
                </div>

                {/* Episodes Grid */}
                <div>
                  <div className="flex items-center justify-between mb-3">
                    <span className="font-bold text-xs text-[#1A1D2E]">
                      分集原片文件列表 ({currentProfile.masterVideoPackage.files.length} 集)
                    </span>
                    <span className="text-[11px] text-slate-400 font-mono">
                      格式规格: {currentProfile.masterVideoPackage.resolution}
                    </span>
                  </div>

                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-2.5">
                    {currentProfile.masterVideoPackage.files.map(ep => (
                      <div
                        key={ep.episode}
                        className="p-3 rounded-xl border border-black/[0.06] bg-slate-50/50 hover:bg-slate-100/80 transition-all flex items-center justify-between group"
                      >
                        <div className="flex items-center gap-3 min-w-0">
                          <div className="w-8 h-8 rounded-lg bg-[#1A1D2E] text-[#DDFD00] font-mono font-bold text-xs flex items-center justify-center shrink-0">
                            {ep.episode < 10 ? `0${ep.episode}` : ep.episode}
                          </div>
                          <div className="min-w-0">
                            <p className="font-semibold text-xs text-[#1A1D2E] truncate" title={ep.filename}>
                              {ep.filename}
                            </p>
                            <p className="text-[11px] text-slate-500 font-mono flex items-center gap-2 mt-0.5">
                              <span>{ep.durationText}</span>
                              <span>·</span>
                              <span>{ep.fileSizeMb} MB</span>
                              <span>·</span>
                              <span>{ep.resolution}</span>
                            </p>
                          </div>
                        </div>

                        <div className="flex items-center gap-1.5 shrink-0 opacity-80 group-hover:opacity-100">
                          <button
                            onClick={() => {
                              setPreviewResource({
                                title: `${currentProfile.dramaCurrentName} - 第${ep.episode}集`,
                                categoryName: '剧集分集原片',
                                type: 'video',
                                filePath: ep.path,
                                fileSizeMb: ep.fileSizeMb,
                                durationText: ep.durationText,
                                resolution: ep.resolution,
                                sourceDramaName: currentProfile.dramaCurrentName,
                              });
                            }}
                            className="p-1.5 rounded-lg bg-white border border-black/[0.08] hover:bg-slate-100 text-slate-700 transition-colors cursor-pointer"
                            title="轻量预览"
                          >
                            <Play className="w-3 h-3" />
                          </button>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              </div>
            )}

            {/* TAB CONTENT 2: COVERS & POSTERS (With Replace Triggers) */}
            {activeSubTab === 'covers' && (
              <div className="bg-white rounded-2xl border border-black/[0.06] shadow-xs p-5 space-y-4">
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                  {/* Main Cover */}
                  <div className="p-4 rounded-xl border border-black/[0.06] bg-slate-50/50 space-y-2.5">
                    <div className="flex items-center justify-between">
                      <span className="font-bold text-xs text-[#1A1D2E]">竖版主封面 (1080x1920)</span>
                      <span className="px-2 py-0.5 rounded bg-emerald-50 text-emerald-700 text-[10px] font-bold">
                        当前主推
                      </span>
                    </div>
                    <div className="w-full h-64 rounded-xl overflow-hidden bg-slate-900 flex items-center justify-center relative group">
                      <img
                        src={currentProfile.cover?.mainCoverUrl}
                        alt="竖版封面"
                        className="h-full object-cover"
                      />
                      <div
                        onClick={() => triggerCoverPicker('main')}
                        className="absolute inset-0 bg-black/50 opacity-0 group-hover:opacity-100 flex flex-col items-center justify-center transition-opacity text-white cursor-pointer"
                      >
                        <Upload className="w-5 h-5 mb-1" />
                        <span className="text-xs font-bold">点击选择本地图片替换</span>
                      </div>
                    </div>
                    <div className="flex items-center justify-between text-[11px] text-slate-500">
                      <span>用于各平台短剧挂载与播放器封面</span>
                      <button
                        onClick={() => triggerCoverPicker('main')}
                        className="text-indigo-600 font-semibold hover:underline cursor-pointer flex items-center gap-1"
                      >
                        <Upload className="w-3 h-3" />
                        <span>替换封面</span>
                      </button>
                    </div>
                  </div>

                  {/* Horizontal Poster */}
                  <div className="p-4 rounded-xl border border-black/[0.06] bg-slate-50/50 space-y-2.5">
                    <div className="flex items-center justify-between">
                      <span className="font-bold text-xs text-[#1A1D2E]">横版宣传海报 (1920x1080)</span>
                      <span className="px-2 py-0.5 rounded bg-slate-100 text-slate-600 text-[10px] font-medium">
                        宣发备用
                      </span>
                    </div>
                    <div className="w-full h-64 rounded-xl overflow-hidden bg-slate-900 flex items-center justify-center relative group">
                      <img
                        src={currentProfile.cover?.horizontalPosterUrl || 'https://images.unsplash.com/photo-1486406146926-c627a92ad1ab?w=800&auto=format&fit=crop&q=80'}
                        alt="横版海报"
                        className="w-full h-full object-cover"
                      />
                      <div
                        onClick={() => triggerCoverPicker('horizontal')}
                        className="absolute inset-0 bg-black/50 opacity-0 group-hover:opacity-100 flex flex-col items-center justify-center transition-opacity text-white cursor-pointer"
                      >
                        <Upload className="w-5 h-5 mb-1" />
                        <span className="text-xs font-bold">点击选择本地图片替换</span>
                      </div>
                    </div>
                    <div className="flex items-center justify-between text-[11px] text-slate-500">
                      <span>用于横幅轮播与多媒体分发</span>
                      <button
                        onClick={() => triggerCoverPicker('horizontal')}
                        className="text-indigo-600 font-semibold hover:underline cursor-pointer flex items-center gap-1"
                      >
                        <Upload className="w-3 h-3" />
                        <span>上传新海报</span>
                      </button>
                    </div>
                  </div>
                </div>
              </div>
            )}

            {/* TAB CONTENT 3: PLOT KNOWLEDGE BASE (A+A EXTENSION READY & EDITABLE) */}
            {activeSubTab === 'plot_aa' && (
              <div className="bg-white rounded-2xl border border-black/[0.06] shadow-xs p-5 space-y-4">
                <div className="p-3 rounded-xl bg-indigo-50/80 border border-indigo-200/80 flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <Sparkles className="w-4 h-4 text-indigo-700" />
                    <div>
                      <span className="font-bold text-indigo-950 text-xs">剧情知识库与 A+A 生产资料预留</span>
                      <p className="text-[11px] text-indigo-800">
                        结构化沉淀主线故事、核心人物设定与爆款钩子点，无缝赋能未来 A+A 自动化内容生产。
                      </p>
                    </div>
                  </div>
                  <div className="flex items-center gap-2">
                    {isEditingPlot ? (
                      <button
                        onClick={handleSavePlot}
                        className="flex items-center gap-1 px-3 py-1.5 rounded-lg bg-indigo-600 text-white font-bold text-xs hover:bg-indigo-700 cursor-pointer"
                      >
                        <Save className="w-3.5 h-3.5" />
                        <span>保存知识库</span>
                      </button>
                    ) : (
                      <button
                        onClick={() => setIsEditingPlot(true)}
                        className="flex items-center gap-1 px-3 py-1.5 rounded-lg bg-white border border-indigo-200 text-indigo-700 font-bold text-xs hover:bg-indigo-50 cursor-pointer"
                      >
                        <Edit2 className="w-3.5 h-3.5" />
                        <span>编辑资料</span>
                      </button>
                    )}
                  </div>
                </div>

                {/* Synopsis */}
                <div className="p-4 rounded-xl border border-black/[0.06] bg-slate-50/50 space-y-2">
                  <span className="font-bold text-xs text-[#1A1D2E]">主线故事梗概 (Synopsis)</span>
                  {isEditingPlot ? (
                    <textarea
                      rows={3}
                      value={plotSynopsis}
                      onChange={e => setPlotSynopsis(e.target.value)}
                      className="w-full px-3 py-2 rounded-xl border border-black/[0.1] bg-white text-xs text-[#1A1D2E] focus:outline-none"
                    />
                  ) : (
                    <p className="text-xs text-slate-700 leading-relaxed">
                      {plotSynopsis || currentProfile.plotKnowledgeBase?.synopsis || '男主重生回到八零年代，运用商业认知反转逆袭，建立实业帝国。'}
                    </p>
                  )}
                </div>

                {/* Character Notes */}
                <div className="p-4 rounded-xl border border-black/[0.06] bg-slate-50/50 space-y-2">
                  <span className="font-bold text-xs text-[#1A1D2E]">核心人物小传与角色关系</span>
                  {isEditingPlot ? (
                    <textarea
                      rows={3}
                      value={plotCharacterNotes}
                      onChange={e => setPlotCharacterNotes(e.target.value)}
                      className="w-full px-3 py-2 rounded-xl border border-black/[0.1] bg-white text-xs text-[#1A1D2E] focus:outline-none"
                    />
                  ) : (
                    <p className="text-xs text-slate-700 leading-relaxed">
                      {plotCharacterNotes || currentProfile.plotKnowledgeBase?.characterNotes || '主角、女主与关键反派冲突关系设定。'}
                    </p>
                  )}
                </div>

                {/* Script Folder Location */}
                {currentProfile.plotKnowledgeBase?.scriptFolderPath && (
                  <div className="p-3.5 rounded-xl bg-slate-50 border border-black/[0.06] flex items-center justify-between text-xs">
                    <div className="flex items-center gap-2">
                      <FileText className="w-4 h-4 text-slate-500 shrink-0" />
                      <div>
                        <span className="font-semibold text-[#1A1D2E] mr-1.5">分镜剧本文档目录:</span>
                        <code className="font-mono text-slate-600 bg-white px-2 py-0.5 rounded border border-black/[0.06]">
                          {currentProfile.plotKnowledgeBase.scriptFolderPath}
                        </code>
                      </div>
                    </div>
                    <button
                      onClick={() => onOpenFolder(currentProfile.plotKnowledgeBase!.scriptFolderPath!)}
                      className="flex items-center gap-1 px-2.5 py-1 rounded-lg bg-[#1A1D2E] text-[#DDFD00] font-bold text-[11px] cursor-pointer"
                    >
                      <FolderOpen className="w-3 h-3" />
                      <span>打开剧本目录</span>
                    </button>
                  </div>
                )}
              </div>
            )}

            {/* TAB CONTENT 4: ASSOCIATED VIRAL CLIPS */}
            {activeSubTab === 'viral_clips' && (
              <div className="bg-white rounded-2xl border border-black/[0.06] shadow-xs p-5 space-y-4">
                <div className="flex items-center justify-between">
                  <div>
                    <h3 className="font-bold text-xs text-[#1A1D2E]">
                      本剧沉淀的爆款资产 ({associatedVirals.length})
                    </h3>
                    <p className="text-[11px] text-slate-400">
                      来源于当前剧集在各账号分发测试中跑出的高 ROI 钩子与成片切片
                    </p>
                  </div>
                </div>

                {associatedVirals.length > 0 ? (
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                    {associatedVirals.map(v => (
                      <div
                        key={v.id}
                        className="p-3.5 rounded-xl border border-black/[0.06] bg-slate-50/60 hover:bg-slate-100/80 transition-all space-y-2.5 group"
                      >
                        <div className="flex items-start justify-between gap-2">
                          <span className="font-bold text-xs text-[#1A1D2E] group-hover:text-indigo-600 transition-colors truncate" title={v.materialName}>
                            {v.materialName}
                          </span>
                          <span className="px-2 py-0.5 rounded bg-indigo-50 text-indigo-700 font-bold text-[10px] shrink-0 border border-indigo-200/50">
                            爆款 {v.viralCount || v.records?.length || 1} 次
                          </span>
                        </div>

                        <div className="flex items-center justify-between text-xs font-mono">
                          <span className="text-slate-600 font-semibold">
                            {v.totalVideoPlaysText || (v.totalVideoPlays ? `${(v.totalVideoPlays / 10000).toFixed(1)}万播放` : '已记录播放')}
                          </span>
                          {v.hasRevenueData && v.totalRevenue ? (
                            <span className="px-2 py-0.5 rounded bg-emerald-600 text-white font-bold text-[11px]">
                              收益 ¥{v.totalRevenue.toLocaleString()}
                            </span>
                          ) : (
                            <span className="text-slate-400 text-[11px]">
                              首爆: {v.firstViralDate}
                            </span>
                          )}
                        </div>

                        <div className="pt-2 border-t border-black/[0.04] flex items-center justify-between text-[11px]">
                          <span className="text-slate-400 font-mono">
                            时长 {v.durationSeconds}s · {v.fileSizeMb}MB
                          </span>
                          <button
                            onClick={() => {
                              setPreviewResource({
                                title: v.materialName,
                                categoryName: `爆款源素材 · 《${v.sourceDramaName}》`,
                                type: 'video',
                                filePath: v.filePath,
                                fileSizeMb: v.fileSizeMb,
                                durationText: `00:${v.durationSeconds < 10 ? '0' : ''}${v.durationSeconds}`,
                                metrics: {
                                  playCountText: v.totalVideoPlaysText,
                                  revenue: v.totalRevenue,
                                },
                                sourceDramaName: v.sourceDramaName,
                                sourceAccountName: v.sourceAccountName,
                              });
                            }}
                            className="flex items-center gap-1 px-2.5 py-1 rounded-lg bg-[#1A1D2E] text-[#DDFD00] font-bold cursor-pointer"
                          >
                            <Play className="w-3 h-3" />
                            <span>轻量预览</span>
                          </button>
                        </div>
                      </div>
                    ))}
                  </div>
                ) : (
                  <div className="py-12 text-center text-slate-400 text-xs">
                    本剧暂无沉淀的爆款切片资产
                  </div>
                )}
              </div>
            )}
          </>
        ) : (
          /* Empty state for dramas without content profile yet */
          <div className="bg-white rounded-2xl border border-black/[0.06] shadow-xs p-12 text-center space-y-4">
            <div className="w-12 h-12 rounded-2xl bg-slate-100 text-slate-400 flex items-center justify-center mx-auto">
              <Film className="w-6 h-6" />
            </div>
            <div>
              <h3 className="font-bold text-sm text-[#1A1D2E]">
                《{currentDramaBusiness?.currentName}》暂未建立资料库档案
              </h3>
              <p className="text-xs text-[#64748B] mt-1 max-w-md mx-auto">
                已在业务资料建立该剧档案，点击下方按钮一键初始化原片目录与物料档案。
              </p>
            </div>
            <button
              onClick={() => {
                if (!currentDramaBusiness) return;
                createV2DramaProfile(currentDramaBusiness.id)
                  .then((paths) => {
                    const profile: DramaContentProfile = {
                      id: `profile-${currentDramaBusiness.id}`,
                      dramaId: currentDramaBusiness.id,
                      dramaCurrentName: currentDramaBusiness.currentName,
                      theaterName: currentDramaBusiness.theaterName,
                      category: '',
                      tags: [],
                      totalEpisodes: 0,
                      cover: { filePath: '', updateTime: '' },
                      masterVideoPackage: {
                        folderPath: paths.master_folder_path,
                        totalFiles: 0,
                        totalSizeGb: 0,
                        resolution: '',
                        status: '待导入',
                        files: [],
                      },
                      associatedViralAssetsCount: 0,
                      updatedAt: new Date().toISOString().slice(0, 16).replace('T', ' '),
                    };
                    onUpdateProfiles?.([...profiles.filter((item) => item.dramaId !== profile.dramaId), profile]);
                    onShowToast(`已为《${currentDramaBusiness.currentName}》创建剧集档案`);
                  })
                  .catch((error: unknown) => onShowToast(error instanceof Error ? error.message : '剧集档案创建失败。'));
              }}
              className="inline-flex items-center gap-1.5 px-4 py-2 rounded-xl bg-[#1A1D2E] text-[#DDFD00] text-xs font-bold hover:bg-black shadow-xs transition-all cursor-pointer"
            >
              <Plus className="w-3.5 h-3.5" />
              <span>一键建立剧集档案</span>
            </button>
          </div>
        )}
      </div>

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
