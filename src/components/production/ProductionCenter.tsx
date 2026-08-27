import React, { useState, useMemo, useRef, useEffect } from 'react';
import { 
  ProductionUnit, 
  ProductionVideoItem,
  ScannedMaterialClip,
  CleanupPreviewData
} from '../../productionTypes';
import { listV2ProductionTasks, queueV2Template, scanV2ProductionTask } from '../../api/v2Production';
import { openV2File, openV2Folder } from '../../api/v2Catalog';
import { toProductionUnit } from '../../adapters/production';
import { 
  Layers, 
  Scan, 
  FolderOpen, 
  Film, 
  ExternalLink, 
  RotateCcw, 
  Play, 
  AlertCircle, 
  Eye, 
  Check, 
  Sparkles, 
  Clock, 
  MoreVertical, 
  Trash2, 
  Video, 
  Brush, 
  X, 
  ShieldCheck,
  Undo2,
  HardDrive,
  User,
  ChevronDown,
  ChevronUp,
  Filter
  ,Volume2
  ,VolumeX
} from 'lucide-react';

interface ProductionCenterProps {
  onBackToWorkbench?: () => void;
  showToast: (msg: string) => void;
}

// Generate deterministic avatar color for accounts
function getAccountColor(name: string) {
  const colors = [
    { bg: 'bg-amber-100', text: 'text-amber-800', border: 'border-amber-200' },
    { bg: 'bg-blue-100', text: 'text-blue-800', border: 'border-blue-200' },
    { bg: 'bg-purple-100', text: 'text-purple-800', border: 'border-purple-200' },
    { bg: 'bg-emerald-100', text: 'text-emerald-800', border: 'border-emerald-200' },
    { bg: 'bg-rose-100', text: 'text-rose-800', border: 'border-rose-200' },
    { bg: 'bg-indigo-100', text: 'text-indigo-800', border: 'border-indigo-200' },
  ];
  let hash = 0;
  for (let i = 0; i < name.length; i++) {
    hash = name.charCodeAt(i) + ((hash << 5) - hash);
  }
  return colors[Math.abs(hash) % colors.length];
}

function getTaskCardStatus(unit: ProductionUnit): { label: string; className: string } {
  const videos = unit.videos ?? [];
  const exportedCount = videos.filter((video) => video.status === 'exported').length;
  const hasException = unit.templateStatus === 'error' || videos.some((video) => video.status === 'error');
  const isVideoRunning = videos.some((video) => video.status === 'draft_generating' || video.status === 'exporting');

  if (unit.releaseStatus === 'registered') return { label: '发布已登记', className: 'bg-emerald-100 text-emerald-800' };
  if (hasException) return { label: '异常', className: 'bg-rose-100 text-rose-800' };
  if (videos.length > 0 && exportedCount === videos.length) return { label: '待登记发布', className: 'bg-orange-50 text-orange-700' };
  if (isVideoRunning) return { label: '成片生成中', className: 'bg-blue-100 text-blue-800' };
  if (unit.templateStatus === 'generated') return { label: '待生成成片', className: 'bg-amber-100 text-amber-800' };
  if (unit.templateStatus === 'draft_ready' || unit.templateStatus === 'exporting') return { label: '模板制作中', className: 'bg-indigo-100 text-indigo-800' };
  if (unit.scannedMaterials.length === 0) {
    return (unit.pendingMaterialCount ?? 0) > 0
      ? { label: '待扫描素材', className: 'bg-sky-100 text-sky-800' }
      : { label: '待导入素材', className: 'bg-slate-200 text-slate-700' };
  }
  return { label: '待制作模板', className: 'bg-purple-100 text-purple-800' };
}

export const ProductionCenter: React.FC<ProductionCenterProps> = ({
  showToast,
}) => {
  const [units, setUnits] = useState<ProductionUnit[]>([]);
  const [selectedUnitId, setSelectedUnitId] = useState<string>('');
  const [stageFilter, setStageFilter] = useState<'all' | 'in_progress' | 'overdue' | 'completed'>('all');
  
  // Dynamic Account & Drama Filter State
  const [selectedAccount, setSelectedAccount] = useState<string>('all');
  const [selectedDrama, setSelectedDrama] = useState<string>('all');
  const [isFilterExpanded, setIsFilterExpanded] = useState<boolean>(false);

  const [isScanning, setIsScanning] = useState(false);
  const [isGeneratingVideos, setIsGeneratingVideos] = useState(false);

  // Material Track Wheel-Scroll Ref
  const materialTrackRef = useRef<HTMLDivElement>(null);

  // Modals & Drawers
  const [previewVideo, setPreviewVideo] = useState<ProductionVideoItem | null>(null);
  const [previewMaterialClip, setPreviewMaterialClip] = useState<ScannedMaterialClip | null>(null);
  const [isMaterialPreviewMuted, setIsMaterialPreviewMuted] = useState(() => localStorage.getItem('v2-material-preview-muted') !== 'false');
  const [selectedMaterialClipId, setSelectedMaterialClipId] = useState<string | null>(null);
  const [activeTemplateMenuOpen, setActiveTemplateMenuOpen] = useState<boolean>(false);
  
  // Danger Actions Modal State (Situation A: Registered Release Cleanup vs Situation B: Delete Drama Task)
  const [isCleanupModalOpen, setIsCleanupModalOpen] = useState(false);
  const [cleanupActionState, setCleanupActionState] = useState<'idle' | 'executing' | 'done'>('idle');

  // Release Registration Dialog State
  const [isReleaseDialogOpen, setIsReleaseDialogOpen] = useState(false);
  const [actualReleaseTimeInput, setActualReleaseTimeInput] = useState('');

  useEffect(() => {
    listV2ProductionTasks()
      .then((response) => {
        const realUnits = response.items.map(toProductionUnit);
        setUnits(realUnits);
        setSelectedUnitId((current) => current && realUnits.some((unit) => unit.id === current) ? current : realUnits[0]?.id || '');
      })
      .catch((error: unknown) => showToast(error instanceof Error ? error.message : '生产任务读取失败，请稍后重试。'));
  }, []);

  // Extract unique accounts & dramas from current units
  const availableAccounts = useMemo(() => {
    const map = new Map<string, string>();
    units.forEach(u => map.set(u.accountId, u.accountName));
    return Array.from(map.entries()).map(([id, name]) => ({ id, name }));
  }, [units]);

  const availableDramas = useMemo(() => {
    const map = new Map<string, string>();
    units.forEach(u => map.set(u.dramaId, u.dramaName));
    return Array.from(map.entries()).map(([id, name]) => ({ id, name }));
  }, [units]);

  // Joint Filter Verification: 
  // 1. Check if an account tag is enabled given current stageFilter and selectedDrama
  const isAccountOptionEnabled = (accName: string) => {
    return units.some(u => {
      if (stageFilter === 'in_progress' && u.isCompleted) return false;
      if (stageFilter === 'overdue' && (u.isCompleted || !u.isOverdue)) return false;
      if (stageFilter === 'completed' && !u.isCompleted) return false;
      if (selectedDrama !== 'all' && u.dramaName !== selectedDrama) return false;
      return u.accountName === accName;
    });
  };

  // 2. Check if a drama tag is enabled given current stageFilter and selectedAccount
  const isDramaOptionEnabled = (drmName: string) => {
    return units.some(u => {
      if (stageFilter === 'in_progress' && u.isCompleted) return false;
      if (stageFilter === 'overdue' && (u.isCompleted || !u.isOverdue)) return false;
      if (stageFilter === 'completed' && !u.isCompleted) return false;
      if (selectedAccount !== 'all' && u.accountName !== selectedAccount) return false;
      return u.dramaName === drmName;
    });
  };

  // Material Horizontal Mouse Wheel scroll binding (Wheel deltaY -> scrollLeft)
  useEffect(() => {
    const el = materialTrackRef.current;
    if (!el) return;

    const onWheel = (e: WheelEvent) => {
      if (e.deltaY !== 0) {
        const isAtLeft = el.scrollLeft <= 0;
        const isAtRight = el.scrollLeft + el.clientWidth >= el.scrollWidth - 1;

        // When able to scroll horizontally, prevent vertical scroll and translate to scrollLeft
        if ((e.deltaY < 0 && !isAtLeft) || (e.deltaY > 0 && !isAtRight)) {
          e.preventDefault();
          el.scrollLeft += e.deltaY;
        }
      }
    };

    el.addEventListener('wheel', onWheel, { passive: false });
    return () => el.removeEventListener('wheel', onWheel);
  }, [selectedUnitId]);

  // Multi-tier Sorting: 
  // 1. Incomplete tasks first (isCompleted === false), Registered/Completed tasks last
  // 2. Earliest scheduled publish time first (sortTimestamp ascending) -> Overdue tasks naturally stay top
  const sortedUnits = useMemo(() => {
    return [...units].sort((a, b) => {
      if (a.isCompleted !== b.isCompleted) {
        return a.isCompleted ? 1 : -1;
      }
      return a.sortTimestamp - b.sortTimestamp;
    });
  }, [units]);

  // Multi-dimensional Filtering: Stage + Account + Drama
  const filteredUnits = useMemo(() => {
    return sortedUnits.filter(u => {
      // 1. Stage filter
      if (stageFilter === 'in_progress' && u.isCompleted) return false;
      if (stageFilter === 'overdue' && (u.isCompleted || !u.isOverdue)) return false;
      if (stageFilter === 'completed' && !u.isCompleted) return false;

      // 2. Account filter
      if (selectedAccount !== 'all' && u.accountName !== selectedAccount) return false;

      // 3. Drama filter
      if (selectedDrama !== 'all' && u.dramaName !== selectedDrama) return false;

      return true;
    });
  }, [sortedUnits, stageFilter, selectedAccount, selectedDrama]);

  const selectedUnit = useMemo(() => {
    return units.find(u => u.id === selectedUnitId) || filteredUnits[0] || units[0];
  }, [units, selectedUnitId, filteredUnits]);

  // Dynamic statistics & 3-stage progress rail calculation for Final Videos area
  const videoStats = useMemo(() => {
    if (!selectedUnit) return { materials: 0, drafts: 0, exported: 0, errors: 0, exportedPercent: 0, draftRemainingPercent: 0 };
    const materials = selectedUnit.scannedMaterials?.length || selectedUnit.materialsCount || 0;
    const drafts = (selectedUnit.videos || []).filter(v => v.status === 'draft_ready' || v.status === 'pending_export' || v.status === 'exporting' || v.status === 'exported').length;
    const exported = (selectedUnit.videos || []).filter(v => v.status === 'exported').length;
    const errors = (selectedUnit.videos || []).filter(v => v.status === 'error').length;
    
    const exportedPercent = materials > 0 ? (exported / materials) * 100 : 0;
    const draftRemainingCount = Math.max(0, drafts - exported);
    const draftRemainingPercent = materials > 0 ? (draftRemainingCount / materials) * 100 : 0;

    return { materials, drafts, exported, errors, exportedPercent, draftRemainingPercent };
  }, [selectedUnit]);

  // ================= ACTION HANDLERS =================

  // Material Scan & Sync Rule:
  // Synchronizes local material directory with valid records.
  // Next new material gets next un-recycled sequence number (剧名-n),
  // and immediately material-drives a corresponding un-generated video clip!
  const handleSyncScanMaterials = async () => {
    if (!selectedUnit) return;
    setIsScanning(true);
    try {
      const result = await scanV2ProductionTask(selectedUnit.id);
      const tasks = await listV2ProductionTasks();
      const refreshedUnit = tasks.items.map(toProductionUnit).find((unit) => unit.id === selectedUnit.id);
      if (refreshedUnit) {
        setUnits((previous) => previous.map((unit) => unit.id === refreshedUnit.id ? refreshedUnit : unit));
      }
      showToast(`素材扫描完成：发现 ${result.discovered} 条有效素材。`);
    } catch (error) {
      showToast(error instanceof Error ? error.message : '素材扫描失败，请稍后重试。');
    } finally {
      setIsScanning(false);
    }
  };

  const handleOpenMaterialFolder = async () => {
    if (!selectedUnit) return;
    try {
      await openV2Folder(selectedUnit.materialFolder);
    } catch (error) {
      showToast(error instanceof Error ? error.message : '打开素材目录失败，请稍后重试。');
    }
  };

  const showUnavailable = () => {
    showToast('该功能将在后续生产中心阶段接入，当前不会执行任何操作。');
  };

  const handleGenerateTemplate = async () => {
    if (!selectedUnit) return;
    try {
      const result = await queueV2Template(selectedUnit.id);
      const tasks = await listV2ProductionTasks();
      setUnits(tasks.items.map(toProductionUnit));
      showToast(`模板任务已进入队列：${result.draft_name}`);
    } catch (error) {
      showToast(error instanceof Error ? error.message : '模板任务创建失败，请稍后重试。');
    }
  };
  const handleExportTemplateFromDraft = showUnavailable;
  const handlePlayTemplateVideo = showUnavailable;
  const handleOpenTemplateDraft = showUnavailable;
  const handleReExportTemplate = showUnavailable;
  const handleRegenerateTemplate = async () => {
    setActiveTemplateMenuOpen(false);
    if (!selectedUnit) return;
    try {
      const result = await queueV2Template(selectedUnit.id, true);
      const tasks = await listV2ProductionTasks();
      setUnits(tasks.items.map(toProductionUnit));
      showToast(`模板已重新排入队列：${result.draft_name}`);
    } catch (error) {
      showToast(error instanceof Error ? error.message : '模板重新生成失败，请稍后重试。');
    }
  };
  const handleBatchGenerateVideos = showUnavailable;

  // Single Final Video Actions
  const handlePlayVideo = (video: ProductionVideoItem) => {
    setPreviewVideo(video);
  };

  const handleOpenVideoDraft = (_video: ProductionVideoItem) => showUnavailable();
  const handleReExportVideo = (_video: ProductionVideoItem) => showUnavailable();
  const handleToggleExportInspection = showUnavailable;
  const handleOpenReleaseDialog = showUnavailable;
  const handleConfirmRegisterRelease = showUnavailable;
  const handleRevokeRelease = showUnavailable;

  // Danger Actions:
  // If registered release -> "立即清理" (Cleanup Lifecycle)
  // If unregistered release -> "删除剧集" (Delete Drama Task)
  const handleOpenDangerModal = showUnavailable;
  const handleExecuteRegisteredCleanup = showUnavailable;
  const handleExecuteDeleteDramaTask = showUnavailable;

  return (
    <div 
      className="space-y-4 animate-in fade-in duration-200 max-w-[1360px] mx-auto w-full" 
      onClick={() => {
        setActiveTemplateMenuOpen(false);
      }}
    >
      {/* Top Banner / Operational Metric Bar (Retained without extra business logic) */}
      <div className="bg-white rounded-2xl p-4 border border-black/[0.06] shadow-xs flex flex-wrap items-center justify-between gap-4">
        <div className="flex items-center gap-3.5">
          <div className="w-10 h-10 rounded-xl bg-[#1A1D2E] text-[#DDFD00] flex items-center justify-center font-bold shadow-xs">
            <Layers className="w-5 h-5" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h2 className="text-lg font-black text-[#1A1D2E] tracking-tight">生产中心 (Production Center)</h2>
              <span className="px-2.5 py-0.5 rounded-full text-[11px] font-extrabold bg-[#DDFD00] text-[#1A1D2E]">
                独立制作单元：账号 × 剧集
              </span>
            </div>
            <p className="text-xs text-[#64748B] mt-0.5">
              桌面工作区：素材同步 ➔ 专属模板 ➔ 成片生成 ➔ 发布登记
            </p>
          </div>
        </div>

        {/* Global Pipeline Summary Badges */}
        <div className="flex items-center gap-2.5 text-xs">
          <div className="px-3 py-1.5 rounded-xl bg-[#F8FAFC] border border-black/[0.04] flex items-center gap-2">
            <span className="w-2 h-2 rounded-full bg-amber-500" />
            <span className="text-[#64748B]">制作中:</span>
            <span className="font-bold text-[#1A1D2E]">
              {units.filter(u => !u.isCompleted).length} 个任务
            </span>
          </div>

          <div className="px-3 py-1.5 rounded-xl bg-[#F8FAFC] border border-black/[0.04] flex items-center gap-2">
            <span className="w-2 h-2 rounded-full bg-rose-500" />
            <span className="text-[#64748B]">逾期未完成:</span>
            <span className="font-bold text-rose-700">
              {units.filter(u => !u.isCompleted && u.isOverdue).length} 个
            </span>
          </div>

          <div className="px-3 py-1.5 rounded-xl bg-[#F8FAFC] border border-black/[0.04] flex items-center gap-2">
            <span className="w-2 h-2 rounded-full bg-emerald-500" />
            <span className="text-[#64748B]">已登记发布:</span>
            <span className="font-bold text-[#1A1D2E]">
              {units.filter(u => u.releaseStatus === 'registered').length} 个
            </span>
          </div>
        </div>
      </div>

      {/* Main 2-Column Desktop Workspace (Height constrained to prevent whole-page scrolling) */}
      <div className="grid grid-cols-1 xl:grid-cols-12 gap-5 items-start">
        
        {/* Left Column (4 cols): Independent Vertical Scroll Task List */}
        <div className="xl:col-span-4 bg-white rounded-3xl p-4 border border-black/[0.06] shadow-xs flex flex-col h-[calc(100vh-185px)] min-h-[640px]">
          
          {/* 1. Stage Filter Bar */}
          <div className="flex items-center gap-1 p-1 bg-black/[0.03] rounded-xl border border-black/[0.03] text-xs shrink-0 mb-2.5">
            <button
              onClick={() => setStageFilter('all')}
              className={`flex-1 py-1.5 rounded-lg font-bold transition-all text-center cursor-pointer ${
                stageFilter === 'all' ? 'bg-white text-[#1A1D2E] shadow-xs' : 'text-[#64748B] hover:text-[#1A1D2E]'
              }`}
            >
              全部 ({units.length})
            </button>
            <button
              onClick={() => setStageFilter('in_progress')}
              className={`flex-1 py-1.5 rounded-lg font-semibold transition-all text-center cursor-pointer ${
                stageFilter === 'in_progress' ? 'bg-white text-[#1A1D2E] shadow-xs' : 'text-[#64748B] hover:text-[#1A1D2E]'
              }`}
            >
              未完成 ({units.filter(u => !u.isCompleted).length})
            </button>
            <button
              onClick={() => setStageFilter('overdue')}
              className={`flex-1 py-1.5 rounded-lg font-semibold transition-all text-center cursor-pointer ${
                stageFilter === 'overdue' ? 'bg-white text-rose-700 shadow-xs font-bold' : 'text-[#64748B] hover:text-rose-600'
              }`}
            >
              逾期 ({units.filter(u => !u.isCompleted && u.isOverdue).length})
            </button>
            <button
              onClick={() => setStageFilter('completed')}
              className={`flex-1 py-1.5 rounded-lg font-semibold transition-all text-center cursor-pointer ${
                stageFilter === 'completed' ? 'bg-white text-slate-700 shadow-xs' : 'text-[#64748B] hover:text-slate-900'
              }`}
            >
              已完成 ({units.filter(u => u.isCompleted).length})
            </button>
          </div>

          {/* 2. Dynamic Account & Drama Filter Chips */}
          <div className="shrink-0 mb-3 space-y-2 bg-[#F8FAFC] rounded-2xl p-2.5 border border-black/[0.04]">
            {/* Account Filter Chips */}
            <div className="space-y-1">
              <div className="flex items-center justify-between text-[11px] text-[#64748B] px-0.5">
                <span className="flex items-center gap-1 font-bold text-[#1A1D2E]">
                  <User className="w-3 h-3 text-slate-500" />
                  账号筛选:
                </span>
                {(selectedAccount !== 'all' || selectedDrama !== 'all') && (
                  <button 
                    onClick={() => { setSelectedAccount('all'); setSelectedDrama('all'); }}
                    className="text-[10px] text-slate-500 hover:text-rose-600 font-semibold cursor-pointer underline"
                  >
                    重置筛选
                  </button>
                )}
              </div>
              <div className="flex flex-wrap items-center gap-1">
                <button
                  onClick={() => setSelectedAccount('all')}
                  className={`px-2 py-0.8 rounded-lg text-[11px] font-bold transition-all cursor-pointer whitespace-nowrap ${
                    selectedAccount === 'all'
                      ? 'bg-[#1A1D2E] text-[#DDFD00] shadow-xs'
                      : 'bg-white text-slate-600 hover:bg-slate-200/70 border border-black/[0.04]'
                  }`}
                >
                  全部账号
                </button>
                {availableAccounts.map(acc => {
                  const isSelected = selectedAccount === acc.name;
                  const isEnabled = isAccountOptionEnabled(acc.name);

                  return (
                    <button
                      key={acc.id}
                      disabled={!isEnabled}
                      onClick={() => {
                        if (!isEnabled) return;
                        setSelectedAccount(isSelected ? 'all' : acc.name);
                      }}
                      className={`px-2 py-0.8 rounded-lg text-[11px] font-semibold transition-all whitespace-nowrap ${
                        !isEnabled
                          ? 'opacity-35 bg-slate-100/70 text-slate-400 border border-slate-200/60 cursor-not-allowed select-none'
                          : isSelected
                          ? 'bg-[#1A1D2E] text-[#DDFD00] font-bold shadow-xs cursor-pointer'
                          : 'bg-white text-slate-700 hover:bg-slate-200/70 border border-black/[0.04] cursor-pointer'
                      }`}
                      title={!isEnabled ? '当前筛选条件下无关联任务' : acc.name}
                    >
                      {acc.name}
                    </button>
                  );
                })}
              </div>
            </div>

            {/* Drama Filter Chips (Collapsible / Multi-select with Joint Filter Dependency) */}
            <div className="space-y-1 pt-1 border-t border-black/[0.04]">
              <div className="flex items-center justify-between text-[11px] text-[#64748B] px-0.5">
                <span className="flex items-center gap-1 font-bold text-[#1A1D2E]">
                  <Film className="w-3 h-3 text-slate-500" />
                  剧集筛选:
                </span>
                <button
                  onClick={() => setIsFilterExpanded(!isFilterExpanded)}
                  className="text-[10px] text-slate-500 hover:text-slate-900 flex items-center gap-0.5 cursor-pointer"
                >
                  <span>{isFilterExpanded ? '收起' : `更多 (${availableDramas.length})`}</span>
                  {isFilterExpanded ? <ChevronUp className="w-3 h-3" /> : <ChevronDown className="w-3 h-3" />}
                </button>
              </div>

              <div className="flex flex-wrap items-center gap-1">
                <button
                  onClick={() => setSelectedDrama('all')}
                  className={`px-2 py-0.8 rounded-lg text-[11px] font-bold transition-all cursor-pointer whitespace-nowrap ${
                    selectedDrama === 'all'
                      ? 'bg-[#1A1D2E] text-[#DDFD00] shadow-xs'
                      : 'bg-white text-slate-600 hover:bg-slate-200/70 border border-black/[0.04]'
                  }`}
                >
                  全部剧集
                </button>
                {(isFilterExpanded ? availableDramas : availableDramas.slice(0, 3)).map(d => {
                  const isSelected = selectedDrama === d.name;
                  const isEnabled = isDramaOptionEnabled(d.name);

                  return (
                    <button
                      key={d.id}
                      disabled={!isEnabled}
                      onClick={() => {
                        if (!isEnabled) return;
                        setSelectedDrama(isSelected ? 'all' : d.name);
                      }}
                      className={`px-2 py-0.8 rounded-lg text-[11px] font-semibold transition-all max-w-[130px] truncate ${
                        !isEnabled
                          ? 'opacity-35 bg-slate-100/70 text-slate-400 border border-slate-200/60 cursor-not-allowed select-none'
                          : isSelected
                          ? 'bg-[#1A1D2E] text-[#DDFD00] font-bold shadow-xs cursor-pointer'
                          : 'bg-white text-slate-700 hover:bg-slate-200/70 border border-black/[0.04] cursor-pointer'
                      }`}
                      title={!isEnabled ? '当前筛选条件下无关联任务' : d.name}
                    >
                      {d.name}
                    </button>
                  );
                })}
              </div>
            </div>
          </div>

          {/* Continuous Task List with Independent Vertical Scrolling (Scrollbars visually hidden) */}
          <div className="flex-1 overflow-y-auto space-y-2.5 pr-1 no-scrollbar">
            {filteredUnits.length === 0 ? (
              <div className="py-12 text-center text-xs text-[#64748B] space-y-1">
                <p className="font-bold">暂无符合筛选条件的制作任务</p>
                <p className="text-[11px]">可尝试切换筛选条件或点击「重置筛选」</p>
              </div>
            ) : (
              filteredUnits.map((unit) => {
                const isSelected = unit.id === selectedUnit?.id;
                const exportedCount = unit.videos.filter(v => v.status === 'exported').length;
                const totalVideos = unit.videos.length;
                const taskCardStatus = getTaskCardStatus(unit);
                const avatarColor = getAccountColor(unit.accountName);
                const avatarChar = unit.accountName.charAt(0) || '账';

                return (
                  <div
                    key={unit.id}
                    onClick={() => setSelectedUnitId(unit.id)}
                    className={`p-3 rounded-2xl border transition-all cursor-pointer select-none relative ${
                      unit.isCompleted
                        ? isSelected
                          ? 'bg-slate-100/90 border-slate-400 shadow-sm opacity-85'
                          : 'bg-slate-50/60 hover:bg-slate-100/70 border-slate-200 text-slate-500 opacity-65'
                        : isSelected
                        ? 'bg-white border-[#1A1D2E] shadow-md ring-2 ring-[#1A1D2E]/10'
                        : 'bg-white hover:bg-slate-50 border-black/[0.06] shadow-xs'
                    }`}
                  >
                    {/* Layer 1: Account Identifier (Avatar + Account Name) & Status Badges */}
                    <div className="flex items-start justify-between gap-2 mb-1.5">
                      <div className="flex items-center gap-2 min-w-0">
                        {/* Account Character Avatar for instant visual recognition */}
                        <div className={`w-6 h-6 rounded-lg ${avatarColor.bg} ${avatarColor.text} ${avatarColor.border} border font-black text-xs flex items-center justify-center shrink-0 shadow-2xs`}>
                          {avatarChar}
                        </div>
                        <span className={`font-black text-sm tracking-tight truncate ${unit.isCompleted ? 'text-slate-600 font-semibold' : 'text-[#1A1D2E]'}`}>
                          {unit.accountName}
                        </span>
                      </div>

                      <div className="flex items-center justify-end gap-1 shrink-0">
                        {/* Overdue Badge (逾期未完成) */}
                        {unit.isOverdue && !unit.isCompleted && (
                          <span className="text-[10px] px-2 py-0.5 rounded-full font-black bg-rose-100 text-rose-700 border border-rose-200">
                            逾期
                          </span>
                        )}

                        {(unit.pendingMaterialCount ?? 0) > 0 && (
                          <span className="inline-flex items-start gap-0.5 rounded-md bg-emerald-50 px-1.5 py-0.5 font-bold whitespace-nowrap">
                            <span className="text-[9px] leading-[10px] text-emerald-700">新素材</span>
                            <span className="text-[8px] leading-[10px] text-emerald-600">+{unit.pendingMaterialCount ?? 0}</span>
                          </span>
                        )}

                        <span className={`text-[10px] px-2 py-0.5 rounded-full font-bold ${taskCardStatus.className}`}>
                          {taskCardStatus.label}
                        </span>
                      </div>
                    </div>

                    {/* Layer 2: Drama Name & Scheduled Publish Time */}
                    <div className="flex items-center justify-between text-xs pt-0.5">
                      <div className="flex items-center gap-1 font-extrabold text-[#1A1D2E] truncate max-w-[185px]">
                        <Film className="w-3.5 h-3.5 text-slate-400 shrink-0" />
                        <span className="truncate">《{unit.dramaName}》</span>
                      </div>

                      <div className="flex items-center gap-1 text-[11px] text-[#64748B] shrink-0">
                        <Clock className="w-3 h-3 text-slate-400" />
                        <span className={unit.isOverdue && !unit.isCompleted ? 'text-rose-700 font-bold' : ''}>
                          {unit.scheduledTime}
                        </span>
                      </div>
                    </div>

                    {/* Layer 3: Quantities (素材数量 · 成片/导出概况) */}
                    <div className="mt-2.5 pt-2 border-t border-black/[0.04] flex items-center justify-between text-[11px] text-[#64748B]">
                      <div className="flex items-center gap-1 min-w-0">
                        <span>素材:</span>
                        <strong className="text-[#1A1D2E] font-extrabold">{unit.scannedMaterials?.length || 0} 条</strong>
                      </div>
                      <div className="flex items-center gap-1">
                        <span>成片 / 导出:</span>
                        <strong className={exportedCount === totalVideos && totalVideos > 0 ? 'text-emerald-700 font-extrabold' : 'text-[#1A1D2E] font-extrabold'}>
                          {exportedCount} / {totalVideos} 条
                        </strong>
                      </div>
                    </div>
                  </div>
                );
              })
            )}
          </div>
        </div>

        {/* Right Column (8 cols): Current Account × Drama Production Workspace */}
        {selectedUnit && (
          <div className="xl:col-span-8 bg-white rounded-3xl p-5 border border-black/[0.06] shadow-xs flex flex-col h-[calc(100vh-185px)] min-h-[640px] space-y-4">
            
            {/* Header Area (Fixed at top) */}
            <div className="pb-3.5 border-b border-black/[0.06] shrink-0 space-y-3">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div>
                  <div className="flex items-center gap-2">
                    <span className="px-2.5 py-0.5 rounded-lg bg-[#1A1D2E] text-[#DDFD00] font-black text-xs">
                      制作任务
                    </span>
                    <h3 className="text-xl font-black text-[#1A1D2E] tracking-tight">
                      {selectedUnit.accountName} × 《{selectedUnit.dramaName}》
                    </h3>
                  </div>

                  <div className="flex flex-wrap items-center gap-4 text-xs text-[#64748B] mt-1.5">
                    <span className="flex items-center gap-1">
                      <Clock className="w-3.5 h-3.5" /> 计划发布时间：
                      <strong className={`text-[#1A1D2E] ${selectedUnit.isOverdue && !selectedUnit.isCompleted ? 'text-rose-700 font-black' : ''}`}>
                        {selectedUnit.scheduledTime}
                      </strong>
                      {selectedUnit.isOverdue && !selectedUnit.isCompleted && (
                        <span className="text-[10px] px-1.5 py-0.2 bg-rose-100 text-rose-800 rounded font-bold ml-1">
                          逾期未完成
                        </span>
                      )}
                    </span>
                    <span className="flex items-center gap-1" title={selectedUnit.outputFolder}>
                      <FolderOpen className="w-3.5 h-3.5" /> 输出目录：
                      <code className="text-[11px] bg-slate-100 px-1.5 py-0.5 rounded text-slate-700 truncate max-w-[220px]">
                        {selectedUnit.outputFolder}
                      </code>
                    </span>
                  </div>
                </div>

                {/* Right Top Operations: 成片导出检查 & Danger Button (删除剧集 / 立即清理 depending on releaseStatus) */}
                <div className="flex items-center gap-2.5">
                  <button
                    onClick={handleToggleExportInspection}
                    className={`flex items-center gap-1.5 px-3 py-1.5 rounded-xl text-xs font-bold transition-all border cursor-pointer ${
                      selectedUnit.exportInspectionMode 
                        ? 'bg-amber-500/10 text-amber-900 border-amber-500/30 ring-1 ring-amber-500/20' 
                        : 'bg-white text-[#64748B] border-black/[0.08] hover:text-[#1A1D2E]'
                    }`}
                    title="开启后：打开成片草稿 ➔ 等待用户人工核对 ➔ 确认继续 ➔ 自动导出 ➔ 进入下一条"
                  >
                    <Eye className="w-3.5 h-3.5" />
                    <span>成片导出检查: {selectedUnit.exportInspectionMode ? '开启' : '关闭'}</span>
                  </button>

                  {/* Danger Action Switch: Unregistered -> "删除剧集"; Registered -> "立即清理" */}
                  {selectedUnit.releaseStatus === 'registered' ? (
                    <button
                      onClick={handleOpenDangerModal}
                      className="flex items-center gap-1.5 px-3 py-1.5 rounded-xl bg-slate-100 hover:bg-slate-200 text-xs font-bold text-[#1A1D2E] transition-all cursor-pointer"
                      title="当前任务已登记发布：执行发布后安全清理"
                    >
                      <Brush className="w-3.5 h-3.5 text-slate-600" />
                      <span>立即清理</span>
                    </button>
                  ) : (
                    <button
                      onClick={handleOpenDangerModal}
                      className="flex items-center gap-1.5 px-3 py-1.5 rounded-xl bg-rose-50 hover:bg-rose-100 border border-rose-200 text-xs font-bold text-rose-700 transition-all cursor-pointer"
                      title="当前任务尚未登记发布：删除当前制作任务中的该剧及关联生产数据"
                    >
                      <Trash2 className="w-3.5 h-3.5 text-rose-600" />
                      <span>删除剧集</span>
                    </button>
                  )}
                </div>
              </div>

              {/* Silent Export Listening Banner (Manual Interruption / Waiting) */}
              {selectedUnit.isListeningExport && (
                <div className="p-3 rounded-2xl bg-amber-50/90 border border-amber-200 text-xs flex items-start justify-between gap-3 animate-in fade-in">
                  <div className="flex items-start gap-2.5">
                    <div className="p-1.5 rounded-lg bg-amber-500 text-white mt-0.5">
                      <AlertCircle className="w-3.5 h-3.5" />
                    </div>
                    <div>
                      <h4 className="font-bold text-amber-950">剪映导出后台监听中</h4>
                      <p className="text-amber-900 mt-0.5 leading-relaxed">
                        {selectedUnit.listeningMessage || '系统正在持续监听目标输出文件。若您在剪映中手动调整草稿并再次点击导出，系统检测到有效文件后将自动继续完成；或随时点击「重新导出」。'}
                      </p>
                    </div>
                  </div>

                  <div className="flex items-center gap-2 shrink-0">
                    <button
                      onClick={() => handleBatchGenerateVideos()}
                      className="px-3 py-1.5 rounded-xl bg-amber-600 hover:bg-amber-700 text-white font-bold cursor-pointer shadow-xs"
                    >
                      重新导出
                    </button>
                  </div>
                </div>
              )}
            </div>

            {/* SECTION 1: 素材区域 (Material Scan - Wheel Scroll + 9:20 Video Ratio + No Scrollbars) */}
            <div className="p-4 rounded-2xl bg-[#F8FAFC] border border-black/[0.06] shrink-0 space-y-2.5">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <span className="w-5 h-5 rounded-full bg-[#1A1D2E] text-[#DDFD00] flex items-center justify-center text-[11px] font-black">
                    1
                  </span>
                  <span className="font-black text-sm text-[#1A1D2E]">素材区域</span>
                  <span className="text-xs font-bold text-slate-700 bg-white px-2 py-0.5 rounded-lg border border-black/[0.05]">
                    有效素材 <strong className="text-[#1A1D2E]">{selectedUnit.scannedMaterials?.length || 0}</strong> 条
                  </span>
                </div>

                <div className="flex items-center gap-2">
                  <button
                    onClick={handleOpenMaterialFolder}
                    className="flex items-center gap-1 px-2.5 py-1.2 rounded-xl bg-white border border-black/[0.08] hover:bg-slate-50 text-xs font-semibold text-[#1A1D2E] cursor-pointer"
                  >
                    <FolderOpen className="w-3.5 h-3.5" />
                    <span>素材目录</span>
                  </button>

                  <button
                    onClick={handleSyncScanMaterials}
                    disabled={isScanning}
                    className="flex items-center gap-1.5 px-3 py-1.2 rounded-xl bg-[#1A1D2E] text-[#DDFD00] hover:bg-black text-xs font-extrabold transition-all shadow-xs cursor-pointer"
                    title="同步本地素材目录与有效素材记录（序号不重复复用）"
                  >
                    <Scan className={`w-3.5 h-3.5 ${isScanning ? 'animate-spin' : ''}`} />
                    <span>{isScanning ? '正在扫描...' : '扫描素材'}</span>
                  </button>
                </div>
              </div>

              {/* Material Thumbnail Horizontal Scroll Track (Wheel-enabled, 9:20 ratio, clean titles, file size, Click to select, Double-click to preview) */}
              <div 
                ref={materialTrackRef}
                className="overflow-x-auto pb-1.5 pt-1 no-scrollbar cursor-grab active:cursor-grabbing"
              >
                <div className="flex items-center gap-3 w-max">
                  {(selectedUnit.scannedMaterials || []).map((clip) => {
                    const isSelected = selectedMaterialClipId === clip.id;
                    return (
                      <div 
                        key={clip.id} 
                        onClick={() => setSelectedMaterialClipId(clip.id)}
                        onDoubleClick={() => setPreviewMaterialClip(clip)}
                        className={`w-28 bg-white rounded-xl overflow-hidden p-2 flex flex-col justify-between group transition-all shrink-0 select-none cursor-pointer ${
                          isSelected
                            ? 'border border-black/[0.06] shadow-xs'
                            : 'border border-black/[0.06] hover:border-black/20 hover:shadow-xs'
                        }`}
                      >
                        {/* Thumbnail: 9:20 Vertical Short-Drama Aspect Ratio + Double-Click Preview Hint Overlay */}
                        <div className="aspect-[9/20] rounded-lg bg-slate-900 overflow-hidden relative mb-1.5">
                          {clip.thumbnailUrl || selectedUnit.coverUrl ? (
                            <img 
                              src={clip.thumbnailUrl || selectedUnit.coverUrl} 
                              alt={clip.title}
                              className="w-full h-full object-cover group-hover:scale-105 transition-transform duration-300"
                            />
                          ) : (
                            <Film className="w-5 h-5 text-slate-500 absolute inset-0 m-auto" aria-label="暂无预览图" />
                          )}
                          
                          {/* Hover Play & Preview Hint Overlay */}
                          <div 
                            onClick={(e) => {
                              e.stopPropagation();
                              setPreviewMaterialClip(clip);
                            }}
                            className="absolute inset-0 bg-black/40 opacity-0 group-hover:opacity-100 transition-opacity flex flex-col items-center justify-center gap-1 cursor-pointer"
                          >
                            <span className="w-7 h-7 rounded-full bg-white/90 text-[#1A1D2E] flex items-center justify-center shadow-md">
                              <Play className="w-3.5 h-3.5 fill-[#1A1D2E] ml-0.5" />
                            </span>
                          </div>

                          <span className="absolute bottom-1 right-1 px-1 py-0.2 rounded bg-black/75 backdrop-blur-xs text-[9px] font-mono text-white">
                            {clip.durationText}
                          </span>
                        </div>

                        {/* Title (No angle brackets, middle truncation, -n always visible) & File Size */}
                        <div className="space-y-0.5">
                          <div className="flex items-center text-xs font-bold text-[#1A1D2E] min-w-0">
                            <span className="truncate">{clip.dramaPrefix}</span>
                            <span className="shrink-0">-{clip.sequenceNumber}</span>
                          </div>
                          <p className="text-[10px] text-[#64748B] truncate">
                            {clip.durationText} · {clip.fileSizeText}
                          </p>
                        </div>
                      </div>
                    );
                  })}
                </div>
              </div>
            </div>

            {/* SECTION 2: 独立专属模板区域 (Account × Drama = 独立模板 + File Size & Duration + 5 Distinct Statuses) */}
            <div className="p-3.5 rounded-2xl bg-[#F8FAFC] border border-black/[0.06] shrink-0 space-y-2.5">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <span className="w-5 h-5 rounded-full bg-[#1A1D2E] text-[#DDFD00] flex items-center justify-center text-[11px] font-black">
                    2
                  </span>
                  <span className="font-black text-sm text-[#1A1D2E]">专属模板制作 (Master Draft)</span>
                  <span className={`text-[11px] px-2 py-0.5 rounded-lg font-bold border ${
                    selectedUnit.templateStatus === 'generated'
                      ? 'bg-emerald-100 text-emerald-800 border-emerald-200'
                      : selectedUnit.templateStatus === 'draft_ready'
                      ? 'bg-amber-100 text-amber-900 border-amber-300'
                      : selectedUnit.templateStatus === 'generating' || selectedUnit.templateStatus === 'exporting'
                      ? 'bg-amber-100 text-amber-800 border-amber-200 animate-pulse'
                      : selectedUnit.templateStatus === 'error'
                      ? 'bg-rose-100 text-rose-800 border-rose-200'
                      : 'bg-slate-200 text-slate-700 border-slate-300'
                  }`}>
                    {selectedUnit.templateStatus === 'generated' ? '专属模板已就绪' :
                     selectedUnit.templateStatus === 'draft_ready' ? '草稿已生成 · 待导出' :
                     selectedUnit.templateStatus === 'exporting' ? '模板视频导出中...' :
                     selectedUnit.templateStatus === 'generating' ? '模板生成中...' :
                     selectedUnit.templateStatus === 'error' ? '模板异常' : '未生成'}
                  </span>
                </div>

                {selectedUnit.templateStatus === 'error' && selectedUnit.templateErrorMessage && (
                  <div className="mt-2 rounded-xl border border-rose-200 bg-rose-50 px-3 py-2 text-[11px] text-rose-800">
                    <span className="font-bold">生成失败：</span>{selectedUnit.templateErrorMessage}
                  </div>
                )}

                {/* Template Operations according to Status */}
                <div className="flex items-center gap-2">
                  {selectedUnit.templateStatus === 'not_generated' ? (
                    <button
                      onClick={handleGenerateTemplate}
                      className="flex items-center gap-1.5 px-3 py-1.2 rounded-xl bg-[#1A1D2E] text-[#DDFD00] hover:bg-black text-xs font-extrabold transition-all shadow-xs cursor-pointer"
                    >
                      <Sparkles className="w-3.5 h-3.5 fill-[#DDFD00]" />
                      <span>自动生成专属模板</span>
                    </button>
                  ) : selectedUnit.templateStatus === 'draft_ready' ? (
                    <>
                      {/* 1. 播放视频: 置灰禁用 (尚未导出视频) */}
                      <button
                        disabled
                        className="flex items-center gap-1 px-2.5 py-1.2 rounded-xl bg-slate-100 border border-slate-200 text-xs font-semibold text-slate-400 opacity-60 cursor-not-allowed"
                        title="视频尚未导出，暂无法播放"
                      >
                        <Play className="w-3 h-3 text-slate-400" />
                        <span>播放视频</span>
                      </button>

                      {/* 2. 打开草稿: 可用 */}
                      <button
                        onClick={handleOpenTemplateDraft}
                        className="flex items-center gap-1 px-2.5 py-1.2 rounded-xl bg-white border border-black/[0.08] hover:bg-slate-50 text-xs font-semibold text-[#1A1D2E] cursor-pointer"
                        title="打开当前剧专属模板剪映草稿"
                      >
                        <ExternalLink className="w-3 h-3 text-slate-700" />
                        <span>打开草稿</span>
                      </button>

                      {/* 3. 开始导出: 主动作按钮，可用 */}
                      <button
                        onClick={handleExportTemplateFromDraft}
                        className="flex items-center gap-1.5 px-3.5 py-1.2 rounded-xl bg-[#1A1D2E] text-[#DDFD00] hover:bg-black text-xs font-black transition-all shadow-xs cursor-pointer"
                        title="草稿已生成，开始导出成片视频"
                      >
                        <Sparkles className="w-3.5 h-3.5 fill-[#DDFD00]" />
                        <span>开始导出</span>
                      </button>

                      {/* More Menu */}
                      <div className="relative" onClick={(e) => e.stopPropagation()}>
                        <button
                          onClick={() => setActiveTemplateMenuOpen(!activeTemplateMenuOpen)}
                          className="p-1.5 rounded-xl bg-white border border-black/[0.08] hover:bg-slate-50 text-slate-600 cursor-pointer"
                          title="更多模板操作"
                        >
                          <MoreVertical className="w-3.5 h-3.5" />
                        </button>

                        {activeTemplateMenuOpen && (
                          <div className="absolute right-0 top-8 z-30 w-48 bg-white rounded-xl shadow-xl border border-black/[0.08] p-1 text-xs animate-in fade-in zoom-in-95">
                            <button
                              onClick={handleRegenerateTemplate}
                              className="w-full text-left px-2.5 py-2 rounded-lg hover:bg-rose-50 font-bold text-rose-700 flex items-center gap-2 cursor-pointer"
                            >
                              <RotateCcw className="w-3.5 h-3.5 text-rose-600" />
                              <span>重新生成 (重做草稿)</span>
                            </button>
                          </div>
                        )}
                      </div>
                    </>
                  ) : (
                    <>
                      <button
                        onClick={handlePlayTemplateVideo}
                        className="flex items-center gap-1 px-2.5 py-1.2 rounded-xl bg-white border border-black/[0.08] hover:bg-slate-50 text-xs font-semibold text-[#1A1D2E] cursor-pointer"
                        title="查看已导出的模板视频"
                      >
                        <Play className="w-3 h-3 text-slate-700" />
                        <span>播放视频</span>
                      </button>

                      <button
                        onClick={handleOpenTemplateDraft}
                        className="flex items-center gap-1 px-2.5 py-1.2 rounded-xl bg-white border border-black/[0.08] hover:bg-slate-50 text-xs font-semibold text-[#1A1D2E] cursor-pointer"
                        title="打开当前剧自己的模板剪映草稿"
                      >
                        <ExternalLink className="w-3 h-3 text-slate-700" />
                        <span>打开草稿</span>
                      </button>

                      <button
                        onClick={handleReExportTemplate}
                        className="flex items-center gap-1 px-2.5 py-1.2 rounded-xl bg-white border border-black/[0.08] hover:bg-slate-50 text-xs font-semibold text-[#1A1D2E] cursor-pointer"
                        title="保留现有模板草稿，只重新执行导出"
                      >
                        <RotateCcw className="w-3 h-3 text-slate-700" />
                        <span>重新导出</span>
                      </button>

                      {/* More Menu: Re-generate Template */}
                      <div className="relative" onClick={(e) => e.stopPropagation()}>
                        <button
                          onClick={() => setActiveTemplateMenuOpen(!activeTemplateMenuOpen)}
                          className="p-1.5 rounded-xl bg-white border border-black/[0.08] hover:bg-slate-50 text-slate-600 cursor-pointer"
                          title="更多模板操作"
                        >
                          <MoreVertical className="w-3.5 h-3.5" />
                        </button>

                        {activeTemplateMenuOpen && (
                          <div className="absolute right-0 top-8 z-30 w-48 bg-white rounded-xl shadow-xl border border-black/[0.08] p-1 text-xs animate-in fade-in zoom-in-95">
                            <button
                              onClick={handleRegenerateTemplate}
                              className="w-full text-left px-2.5 py-2 rounded-lg hover:bg-rose-50 font-bold text-rose-700 flex items-center gap-2 cursor-pointer"
                            >
                              <RotateCcw className="w-3.5 h-3.5 text-rose-600" />
                              <span>重新生成 (重做草稿)</span>
                            </button>
                          </div>
                        )}
                      </div>
                    </>
                  )}
                </div>
              </div>

              {selectedUnit.templateDraftName && (
                <div className="px-3 py-2 bg-white rounded-xl border border-black/[0.04] flex flex-wrap items-center justify-between gap-2 text-xs">
                  <div className="flex items-center gap-2">
                    <Film className="w-3.5 h-3.5 text-slate-500" />
                    <span className="font-bold text-[#1A1D2E]">{selectedUnit.templateDraftName}</span>
                    <span className="text-[11px] text-[#64748B]">
                      ({selectedUnit.templateDurationText || '—'} · {selectedUnit.templateFileSizeText || '—'})
                    </span>
                  </div>
                  <div className="flex items-center gap-4 text-[#64748B]">
                    <span>草稿耗时: <strong className="text-[#1A1D2E]">{selectedUnit.templateDraftDuration || '—'}</strong></span>
                    <span>导出耗时: <strong className="text-[#1A1D2E]">{selectedUnit.templateExportDuration || '—'}</strong></span>
                    <span>更新于: {selectedUnit.templateUpdatedAt || '—'}</span>
                  </div>
                </div>
              )}
            </div>

            {/* SECTION 3: 成片区域 (Material-Driven Final Videos - 3-Stage Progress Rail + Independent Vertical Scroll, No Scrollbars) */}
            <div className="p-4 rounded-2xl bg-[#F8FAFC] border border-black/[0.06] flex-1 flex flex-col min-h-0 space-y-2.5">
              
              {/* Header: Title & Action Button */}
              <div className="flex items-center justify-between gap-2.5 shrink-0">
                <div className="flex items-center gap-2">
                  <span className="w-5 h-5 rounded-full bg-[#1A1D2E] text-[#DDFD00] flex items-center justify-center text-[11px] font-black">
                    3
                  </span>
                  <span className="font-black text-sm text-[#1A1D2E]">成片区域</span>
                </div>

                {/* Main Action: 成片生成 */}
                <div className="flex items-center gap-2">
                  <button
                    onClick={handleBatchGenerateVideos}
                    disabled={isGeneratingVideos}
                    className="flex items-center gap-1.5 px-3.5 py-1.5 rounded-xl bg-[#1A1D2E] text-[#DDFD00] hover:bg-black text-xs font-black transition-all shadow-xs cursor-pointer"
                  >
                    <Sparkles className={`w-3.5 h-3.5 fill-[#DDFD00] ${isGeneratingVideos ? 'animate-spin' : ''}`} />
                    <span>{isGeneratingVideos ? '成片生成中...' : '成片生成'}</span>
                  </button>
                </div>
              </div>

              {/* 三阶段生产进度轨 (以“素材”为总长度，依次叠加“草稿”和“视频”；固定显示 视频 / 草稿 / 素材 与数量，异常独立显示) */}
              <div className="p-2.5 bg-white rounded-xl border border-black/[0.04] shrink-0 space-y-2 shadow-2xs">
                <div className="flex flex-wrap items-center justify-between gap-2 text-xs">
                  {/* 固定显示 视频 / 草稿 / 素材 三个名称和对应数量 */}
                  <div className="flex items-center gap-4">
                    <div className="flex items-center gap-1.5">
                      <span className="w-2 h-2 rounded-full bg-emerald-500 shrink-0" />
                      <span className="font-bold text-[#64748B]">视频</span>
                      <span className="font-mono font-black text-emerald-800 text-[13px]">{videoStats.exported}</span>
                    </div>

                    <div className="flex items-center gap-1.5">
                      <span className="w-2 h-2 rounded-full bg-indigo-500 shrink-0" />
                      <span className="font-bold text-[#64748B]">草稿</span>
                      <span className="font-mono font-black text-indigo-800 text-[13px]">{videoStats.drafts}</span>
                    </div>

                    <div className="flex items-center gap-1.5">
                      <span className="w-2 h-2 rounded-full bg-slate-500 shrink-0" />
                      <span className="font-bold text-[#64748B]">素材</span>
                      <span className="font-mono font-black text-[#1A1D2E] text-[13px]">{videoStats.materials}</span>
                    </div>
                  </div>

                  {/* 异常独立显示 */}
                  <div className="flex items-center gap-1.5 px-2 py-0.5 rounded-lg bg-slate-50 border border-black/[0.04] text-xs">
                    <span className={`w-1.5 h-1.5 rounded-full shrink-0 ${videoStats.errors > 0 ? 'bg-rose-500 animate-pulse' : 'bg-slate-400'}`} />
                    <span className="font-bold text-[#64748B]">异常</span>
                    <span className={`font-mono font-black ${videoStats.errors > 0 ? 'text-rose-600' : 'text-slate-500'}`}>
                      {videoStats.errors}
                    </span>
                  </div>
                </div>

                {/* 单条三阶段叠加进度轨 (底轨为素材总量，左起依次为视频导出绿轨与草稿就绪蓝轨) */}
                <div 
                  className="h-2.5 w-full bg-slate-200/70 rounded-full overflow-hidden flex border border-black/[0.03] relative"
                  title={`视频: ${videoStats.exported} | 草稿: ${videoStats.drafts} | 素材: ${videoStats.materials}`}
                >
                  {videoStats.exportedPercent > 0 && (
                    <div 
                      className="h-full bg-emerald-500 transition-all duration-500"
                      style={{ width: `${Math.min(100, videoStats.exportedPercent)}%` }}
                    />
                  )}
                  {videoStats.draftRemainingPercent > 0 && (
                    <div 
                      className="h-full bg-indigo-500 transition-all duration-500"
                      style={{ width: `${Math.min(100 - videoStats.exportedPercent, videoStats.draftRemainingPercent)}%` }}
                    />
                  )}
                </div>
              </div>

              {/* Final Videos Independent Vertical Scroll Container for 20-30 items (Scrollbar visually hidden) */}
              <div className="flex-1 overflow-y-auto pr-1 space-y-2 no-scrollbar">
                {(selectedUnit.videos || []).map((vid) => {
                  return (
                    <div
                      key={vid.id}
                      className="p-2.5 bg-white rounded-xl border border-black/[0.04] flex flex-wrap items-center justify-between gap-3 text-xs hover:border-black/[0.12] transition-colors"
                    >
                      {/* Left: Title & Duration & Status */}
                      <div className="flex items-center gap-2.5">
                        <span className="w-5 h-5 rounded-lg bg-slate-100 text-slate-700 font-extrabold flex items-center justify-center text-[11px]">
                          {vid.sequenceNumber}
                        </span>
                        <div>
                          <div className="flex items-center gap-2">
                            <div className="flex items-center font-extrabold text-[#1A1D2E] text-xs">
                              <span>{vid.dramaPrefix}</span>
                              <span>-{vid.sequenceNumber}</span>
                            </div>
                            <span className="text-[11px] text-[#64748B]">
                              时长：{vid.durationSec} 秒 · 大小: {vid.fileSizeText}
                            </span>
                          </div>
                          <div className="flex items-center gap-3 text-[11px] text-[#64748B]">
                            <span>草稿耗时: <strong className="text-slate-800">{vid.draftDuration}</strong></span>
                            <span>导出耗时: <strong className="text-slate-800">{vid.exportDuration}</strong></span>
                          </div>
                        </div>
                      </div>

                      {/* Right: Status Badge & 3 Fixed Operations */}
                      <div className="flex items-center gap-2.5">
                        <span className={`px-2 py-0.5 rounded-lg text-[10px] font-bold ${
                          vid.status === 'exported'
                            ? 'bg-emerald-100 text-emerald-800'
                            : vid.status === 'exporting'
                            ? 'bg-amber-100 text-amber-800 animate-pulse'
                            : vid.status === 'draft_ready'
                            ? 'bg-indigo-100 text-indigo-800'
                            : vid.status === 'draft_generating'
                            ? 'bg-amber-100 text-amber-800'
                            : vid.status === 'error'
                            ? 'bg-rose-100 text-rose-800'
                            : 'bg-slate-100 text-slate-600'
                        }`}>
                          {vid.status === 'exported' ? '已导出' :
                           vid.status === 'exporting' ? `导出中 (${vid.exportProgress || 0}%)` :
                           vid.status === 'draft_ready' ? '草稿已生成' :
                           vid.status === 'draft_generating' ? '草稿生成中' :
                           vid.status === 'pending_export' ? '待导出' :
                           vid.status === 'error' ? '异常' : '待生成'}
                        </span>

                        {/* 3 Fixed Small Icon Operations */}
                        <div className="flex items-center gap-0.5">
                          {/* 1. 预览视频 */}
                          <button
                            onClick={() => handlePlayVideo(vid)}
                            className="p-1 rounded-lg hover:bg-slate-100 text-slate-600 hover:text-[#1A1D2E] transition-colors cursor-pointer"
                            title="预览视频"
                          >
                            <Video className="w-3.5 h-3.5" />
                          </button>

                          {/* 2. 打开草稿 */}
                          <button
                            onClick={() => handleOpenVideoDraft(vid)}
                            className="p-1 rounded-lg hover:bg-slate-100 text-slate-600 hover:text-[#1A1D2E] transition-colors cursor-pointer"
                            title="在剪映中打开该集成片草稿"
                          >
                            <ExternalLink className="w-3.5 h-3.5" />
                          </button>

                          {/* 3. 重新导出 */}
                          <button
                            onClick={() => handleReExportVideo(vid)}
                            className="p-1 rounded-lg hover:bg-slate-100 text-slate-600 hover:text-[#1A1D2E] transition-colors cursor-pointer"
                            title="重新导出（保留草稿）"
                          >
                            <RotateCcw className="w-3.5 h-3.5" />
                          </button>
                        </div>
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>

            {/* SECTION 4: 发布登记 (Release Registration) */}
            <div className="p-3.5 rounded-2xl bg-[#F8FAFC] border border-black/[0.06] shrink-0 flex flex-wrap items-center justify-between gap-3">
              <div>
                <div className="flex items-center gap-2">
                  <span className="w-5 h-5 rounded-full bg-[#1A1D2E] text-[#DDFD00] flex items-center justify-center text-[11px] font-black">
                    4
                  </span>
                  <span className="font-black text-sm text-[#1A1D2E]">发布登记</span>
                  <span className={`text-[11px] px-2 py-0.5 rounded-lg font-bold ${
                    selectedUnit.releaseStatus === 'registered'
                      ? 'bg-emerald-100 text-emerald-800'
                      : 'bg-slate-200 text-slate-700'
                  }`}>
                    {selectedUnit.releaseStatus === 'registered' ? '已登记发布' : '未登记发布'}
                  </span>
                </div>
                <p className="text-xs text-[#64748B] mt-0.5">
                  {selectedUnit.releaseStatus === 'registered'
                    ? `已于 ${selectedUnit.actualReleaseTime || selectedUnit.scheduledTime} 登记发布`
                    : '成片导出完成后，登记发布时间以驱动后续安全清理与归档'}
                </p>
              </div>

              <div className="flex items-center gap-2">
                {selectedUnit.releaseStatus === 'registered' ? (
                  <button
                    onClick={handleRevokeRelease}
                    className="flex items-center gap-1.5 px-3 py-1.5 rounded-xl bg-white border border-black/[0.08] hover:bg-slate-100 text-xs font-bold text-[#1A1D2E] cursor-pointer"
                  >
                    <Undo2 className="w-3.5 h-3.5" />
                    <span>撤销发布</span>
                  </button>
                ) : (
                  <button
                    onClick={handleOpenReleaseDialog}
                    className="flex items-center gap-1.5 px-3.5 py-1.5 rounded-xl bg-[#1A1D2E] text-[#DDFD00] hover:bg-black text-xs font-black transition-all shadow-xs cursor-pointer"
                  >
                    <Check className="w-3.5 h-3.5" />
                    <span>登记发布</span>
                  </button>
                )}
              </div>
            </div>

          </div>
        )}
      </div>

      {/* ================= DIALOG 1: 登记发布时间弹窗 (Release Time Dialog) ================= */}
      {isReleaseDialogOpen && (
        <div className="fixed inset-0 z-50 bg-black/60 backdrop-blur-xs flex items-center justify-center p-4">
          <div className="bg-white rounded-3xl max-w-md w-full p-6 shadow-2xl border border-black/[0.08] space-y-5 animate-in fade-in zoom-in-95">
            <div className="flex items-center justify-between border-b border-black/[0.06] pb-3">
              <h3 className="font-black text-base text-[#1A1D2E] flex items-center gap-2">
                <Check className="w-4 h-4 text-emerald-600" />
                <span>登记实际发布时间</span>
              </h3>
              <button 
                onClick={() => setIsReleaseDialogOpen(false)}
                className="p-1 rounded-lg hover:bg-slate-100 text-slate-500 cursor-pointer"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            <div className="space-y-3.5 text-xs">
              {/* 当前任务 */}
              <div className="p-3 bg-slate-50 rounded-xl border border-black/[0.04] space-y-1">
                <span className="text-[#64748B] block">当前制作任务</span>
                <p className="font-extrabold text-sm text-[#1A1D2E]">
                  {selectedUnit.accountName} × 《{selectedUnit.dramaName}》
                </p>
              </div>

              {/* 计划发布时间 */}
              <div className="flex items-center justify-between px-1">
                <span className="text-[#64748B]">计划发布时间:</span>
                <span className="font-bold text-[#1A1D2E]">{selectedUnit.scheduledTime}</span>
              </div>

              {/* 登记发布时间 Input (Default populated with scheduled time) */}
              <div className="space-y-1.5 pt-1">
                <label className="font-bold text-[#1A1D2E] block">
                  实际发布时间:
                </label>
                <input 
                  type="text"
                  value={actualReleaseTimeInput}
                  onChange={(e) => setActualReleaseTimeInput(e.target.value)}
                  placeholder="例如：今天 18:30 或 今天 19:10"
                  className="w-full px-3.5 py-2 rounded-xl bg-slate-50 border border-black/[0.08] focus:border-[#1A1D2E] focus:bg-white outline-hidden text-xs font-bold text-[#1A1D2E]"
                />
                <span className="text-[11px] text-[#64748B]">
                  默认已引用计划发布时间，可根据实际发布时刻直接修改。
                </span>
              </div>
            </div>

            <div className="flex items-center justify-end gap-2.5 pt-2 border-t border-black/[0.06]">
              <button
                onClick={() => setIsReleaseDialogOpen(false)}
                className="px-4 py-2 rounded-xl border border-black/[0.08] hover:bg-slate-50 text-xs font-semibold text-[#64748B] cursor-pointer"
              >
                取消
              </button>
              <button
                onClick={handleConfirmRegisterRelease}
                className="px-4 py-2 rounded-xl bg-[#1A1D2E] text-[#DDFD00] hover:bg-black text-xs font-black transition-all cursor-pointer shadow-xs"
              >
                确认登记
              </button>
            </div>
          </div>
        </div>
      )}

      {/* ================= DIALOG 2: 危险操作统一 Preview 弹窗 (Situation A: 立即清理 vs Situation B: 删除剧集) ================= */}
      {isCleanupModalOpen && (
        <div className="fixed inset-0 z-50 bg-black/60 backdrop-blur-xs flex items-center justify-center p-4">
          <div className="bg-white rounded-3xl max-w-xl w-full p-6 shadow-2xl border border-black/[0.08] space-y-5 animate-in fade-in zoom-in-95">
            
            {/* Header */}
            <div className="flex items-start justify-between border-b border-black/[0.06] pb-3.5">
              <div>
                <h3 className="font-black text-lg text-[#1A1D2E] flex items-center gap-2">
                  {selectedUnit.releaseStatus === 'registered' ? (
                    <>
                      <Brush className="w-5 h-5 text-slate-700" />
                      <span>立即清理 (发布后安全清理)</span>
                    </>
                  ) : (
                    <>
                      <Trash2 className="w-5 h-5 text-rose-600" />
                      <span>删除剧集 (未发布制作任务)</span>
                    </>
                  )}
                </h3>
                <p className="text-xs text-[#64748B] mt-1 font-bold">
                  {selectedUnit.accountName} × 《{selectedUnit.dramaName}》
                </p>
              </div>
              <button 
                onClick={() => setIsCleanupModalOpen(false)}
                className="p-1.5 rounded-lg hover:bg-slate-100 text-slate-500 cursor-pointer"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            {/* Brief Description */}
            <div className="p-3.5 bg-slate-50 rounded-2xl border border-black/[0.04] text-xs text-[#64748B] leading-relaxed">
              {selectedUnit.releaseStatus === 'registered' ? (
                <span>
                  当前剧集<strong>已完成发布登记</strong>。执行一键清理将安全移除剪映本地临时工程分镜与中间导出缓存，历史成片将保留并归档，随后将该任务从生产中心移出。
                </span>
              ) : (
                <span>
                  当前剧集<strong>尚未登记发布</strong>。本次操作将删除当前账号下这部剧的制作任务、专属模板及剪映草稿过程数据。<strong className="text-slate-900">这不是删除资料中心里的剧集主档</strong>。
                </span>
              )}
            </div>

            {/* Deletion List Preview (Name on left, Size on right) */}
            <div className="space-y-2">
              <h4 className="text-xs font-bold text-[#1A1D2E] flex items-center justify-between">
                <span>{selectedUnit.releaseStatus === 'registered' ? '清理内容清单' : '将删除的生产数据'}</span>
                <span className="text-[11px] text-[#64748B] font-normal">后端预览预估</span>
              </h4>

              <div className="bg-slate-50 rounded-2xl border border-black/[0.04] p-3 space-y-2 text-xs">
                {selectedUnit.releaseStatus === 'registered' ? (
                  <>
                    <div className="flex items-center justify-between text-slate-700">
                      <span>剪映本地专属模板草稿缓存</span>
                      <strong className="font-mono text-slate-900">1.1 GB</strong>
                    </div>
                    <div className="flex items-center justify-between text-slate-700">
                      <span>成片分集工程草稿与临时分镜</span>
                      <strong className="font-mono text-slate-900">2.3 GB</strong>
                    </div>
                    <div className="flex items-center justify-between text-slate-700">
                      <span>渲染中间缓存与临时技术文件</span>
                      <strong className="font-mono text-slate-900">0.4 GB</strong>
                    </div>
                  </>
                ) : (
                  <>
                    <div className="flex items-center justify-between text-slate-700">
                      <span>当前剧制作任务及生产排期关系</span>
                      <strong className="font-mono text-slate-900">0.2 GB</strong>
                    </div>
                    <div className="flex items-center justify-between text-slate-700">
                      <span>素材扫描关系及解析缓存</span>
                      <strong className="font-mono text-slate-900">0.7 GB</strong>
                    </div>
                    <div className="flex items-center justify-between text-slate-700">
                      <span>当前账号 × 剧专属模板草稿</span>
                      <strong className="font-mono text-slate-900">1.1 GB</strong>
                    </div>
                    <div className="flex items-center justify-between text-slate-700">
                      <span>成片草稿及相关生成过程数据</span>
                      <strong className="font-mono text-slate-900">2.3 GB</strong>
                    </div>
                    <div className="flex items-center justify-between text-slate-700">
                      <span>临时缓存与中间文件</span>
                      <strong className="font-mono text-slate-900">0.4 GB</strong>
                    </div>
                  </>
                )}
              </div>
            </div>

            {/* Estimated Disk Space Release */}
            <div className="flex items-center justify-between p-3.5 bg-[#DDFD00]/15 rounded-2xl border border-[#DDFD00]/40">
              <div className="flex items-center gap-2">
                <HardDrive className="w-4 h-4 text-[#1A1D2E]" />
                <span className="font-extrabold text-xs text-[#1A1D2E]">预计释放磁盘空间</span>
              </div>
              <span className="font-black text-base text-[#1A1D2E] font-mono">
                {selectedUnit.releaseStatus === 'registered' ? '3.8 GB' : '4.7 GB'}
              </span>
            </div>

            {/* Safe Protection Scope */}
            <div className="p-3 bg-emerald-50/70 rounded-2xl border border-emerald-200/60 text-xs text-emerald-900 space-y-1">
              <div className="flex items-center gap-1.5 font-bold">
                <ShieldCheck className="w-3.5 h-3.5 text-emerald-700" />
                <span>安全保护范围（不受任何影响）</span>
              </div>
              <p className="text-[11px] text-emerald-800 leading-relaxed">
                • 账号主档档案　• 资料中心剧集母本档　• 其他账号制作的同部剧集　• 其他独立制作任务
              </p>
            </div>

            {/* Final Danger Action Button */}
            <div className="flex items-center justify-end gap-2.5 pt-2 border-t border-black/[0.06]">
              <button
                onClick={() => setIsCleanupModalOpen(false)}
                disabled={cleanupActionState === 'executing'}
                className="px-4 py-2 rounded-xl border border-black/[0.08] hover:bg-slate-50 text-xs font-semibold text-[#64748B] cursor-pointer"
              >
                取消
              </button>

              {selectedUnit.releaseStatus === 'registered' ? (
                <button
                  onClick={handleExecuteRegisteredCleanup}
                  disabled={cleanupActionState === 'executing'}
                  className="px-4 py-2 rounded-xl bg-[#1A1D2E] hover:bg-black text-[#DDFD00] text-xs font-black transition-all cursor-pointer shadow-xs flex items-center gap-1.5"
                >
                  <Brush className="w-3.5 h-3.5" />
                  <span>{cleanupActionState === 'executing' ? '正在执行一键清理...' : '执行一键清理'}</span>
                </button>
              ) : (
                <button
                  onClick={handleExecuteDeleteDramaTask}
                  disabled={cleanupActionState === 'executing'}
                  className="px-4 py-2 rounded-xl bg-rose-600 hover:bg-rose-700 text-white text-xs font-black transition-all cursor-pointer shadow-xs flex items-center gap-1.5"
                >
                  <Trash2 className="w-3.5 h-3.5" />
                  <span>{cleanupActionState === 'executing' ? '正在删除剧集...' : '删除剧集'}</span>
                </button>
              )}
            </div>

          </div>
        </div>
      )}

      {/* Final Video Preview Modal */}
      {previewVideo && (
        <div className="fixed inset-0 z-50 bg-black/70 backdrop-blur-xs flex items-center justify-center p-4">
          <div className="bg-white rounded-3xl max-w-lg w-full p-6 shadow-2xl border border-black/[0.08] space-y-4 animate-in fade-in zoom-in-95">
            <div className="flex items-center justify-between border-b border-black/[0.06] pb-3">
              <div>
                <h3 className="font-black text-base text-[#1A1D2E]">{previewVideo.title}</h3>
                <p className="text-xs text-[#64748B]">视频时长：{previewVideo.durationSec} 秒 · 草稿工程：{previewVideo.capcutDraftName}</p>
              </div>
              <button 
                onClick={() => setPreviewVideo(null)}
                className="p-1 rounded-lg hover:bg-slate-100 text-slate-500 cursor-pointer"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            <div className="aspect-[9/16] max-h-[380px] mx-auto rounded-2xl bg-black overflow-hidden relative flex items-center justify-center">
              {selectedUnit.coverUrl && <img 
                src={selectedUnit.coverUrl} 
                alt="Video Preview"
                className="w-full h-full object-cover opacity-85"
              />}
              <div className="absolute inset-0 bg-gradient-to-t from-black/80 via-transparent to-transparent flex flex-col justify-end p-4">
                <div className="flex items-center gap-2 text-white">
                  <span className="w-8 h-8 rounded-full bg-white/20 backdrop-blur-xs flex items-center justify-center">
                    <Play className="w-4 h-4 fill-white" />
                  </span>
                  <div>
                    <p className="text-xs font-bold">{previewVideo.title}</p>
                    <p className="text-[10px] text-white/70">剪映已渲染成片 (1080×1920)</p>
                  </div>
                </div>
              </div>
            </div>

            <div className="flex items-center justify-between pt-2 border-t border-black/[0.06] text-xs">
              <span className="text-[#64748B]">
                草稿耗时: {previewVideo.draftDuration} · 导出耗时: {previewVideo.exportDuration}
              </span>
              <button
                onClick={() => {
                  showToast(`🖥️ 已在剪映中打开草稿「${previewVideo.capcutDraftName}」`);
                  setPreviewVideo(null);
                }}
                className="flex items-center gap-1 px-3 py-1.5 rounded-xl bg-[#1A1D2E] text-white font-bold cursor-pointer"
              >
                <ExternalLink className="w-3.5 h-3.5" />
                <span>打开草稿</span>
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Material Clip Preview Modal (Triggered by double-clicking material thumbnail) */}
      {previewMaterialClip && (
        <div
          className="fixed inset-0 z-50 bg-black/75 backdrop-blur-xs flex items-center justify-center p-4"
          onClick={() => setPreviewMaterialClip(null)}
        >
          <div
            className="bg-white rounded-3xl max-w-3xl w-full p-6 shadow-2xl border border-black/[0.08] space-y-4 animate-in fade-in zoom-in-95"
            onClick={(event) => event.stopPropagation()}
          >
            <div className="flex items-center justify-between border-b border-black/[0.06] pb-3">
              <div>
                <div className="flex items-center gap-2">
                  <span className="px-2 py-0.5 rounded-md bg-[#1A1D2E] text-[#DDFD00] text-[10px] font-black">
                    原始素材
                  </span>
                  <h3 className="font-black text-base text-[#1A1D2E]">{previewMaterialClip.title}</h3>
                </div>
                <p className="text-xs text-[#64748B] mt-0.5">
                  时长：{previewMaterialClip.durationText} · 大小: {previewMaterialClip.fileSizeText} · 分辨率: 1080×2400 (9:20)
                </p>
              </div>
              <button 
                onClick={() => setPreviewMaterialClip(null)}
                className="p-1 rounded-lg hover:bg-slate-100 text-slate-500 cursor-pointer"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            {/* Video Player Simulation (9:20 vertical short-drama display) */}
            <div className="aspect-[9/18] max-h-[680px] mx-auto rounded-2xl bg-black overflow-hidden relative flex items-center justify-center">
              {previewMaterialClip.videoUrl ? <video
                src={previewMaterialClip.videoUrl}
                poster={previewMaterialClip.thumbnailUrl || selectedUnit.coverUrl}
                controls
                autoPlay
                muted={isMaterialPreviewMuted}
                playsInline
                preload="metadata"
                className="w-full h-full object-contain"
              /> : (previewMaterialClip.thumbnailUrl || selectedUnit.coverUrl) && <img
                src={previewMaterialClip.thumbnailUrl || selectedUnit.coverUrl}
                alt={previewMaterialClip.title}
                className="w-full h-full object-cover opacity-90"
              />}
            </div>

            {/* Bottom Info & Action */}
            <div className="flex items-center justify-between pt-2 border-t border-black/[0.06] text-xs">
              <span className="text-[#64748B] truncate max-w-[280px]" title={previewMaterialClip.filePath}>
                路径: {previewMaterialClip.filePath || selectedUnit.materialFolder}
              </span>
              <div className="flex items-center gap-2">
                <button
                  type="button"
                  onClick={() => setIsMaterialPreviewMuted((muted) => {
                    const next = !muted;
                    localStorage.setItem('v2-material-preview-muted', String(next));
                    return next;
                  })}
                  className="flex items-center gap-1 px-3 py-1.5 rounded-xl bg-slate-100 hover:bg-slate-200 text-[#1A1D2E] font-bold cursor-pointer"
                  title={isMaterialPreviewMuted ? '开启视频声音' : '关闭视频声音'}
                >
                  {isMaterialPreviewMuted ? <VolumeX className="w-3.5 h-3.5" /> : <Volume2 className="w-3.5 h-3.5" />}
                  <span>{isMaterialPreviewMuted ? '开启声音' : '静音'}</span>
                </button>
                <button
                  onClick={() => {
                    const filePath = previewMaterialClip.filePath;
                    if (!filePath) {
                      showToast('当前素材没有可打开的文件路径。');
                      return;
                    }
                    openV2File(filePath).then(() => {
                      showToast(`已打开素材文件：${previewMaterialClip.title}`);
                      setPreviewMaterialClip(null);
                    }).catch((error: unknown) => {
                      showToast(error instanceof Error ? error.message : '打开素材文件失败，请稍后重试。');
                    });
                  }}
                  className="flex items-center gap-1 px-3 py-1.5 rounded-xl bg-slate-100 hover:bg-slate-200 text-[#1A1D2E] font-bold cursor-pointer"
                >
                  <FolderOpen className="w-3.5 h-3.5" />
                  <span>打开播放器</span>
                </button>
                <button
                  onClick={() => setPreviewMaterialClip(null)}
                  className="px-3.5 py-1.5 rounded-xl bg-[#1A1D2E] text-white font-bold cursor-pointer"
                >
                  关闭
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

    </div>
  );
};
