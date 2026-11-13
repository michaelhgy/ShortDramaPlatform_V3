import { AccountAvatar } from '../AccountAvatar';
import { fetchAssetsCenterSeedForDataHub } from '../../services/assetsCenterService';
import { ProductionProgress } from './ProductionProgress';
import { liveVideo } from '../taskcenter/ffmpegTaskModel';
import { createFinalBatch, regenerateFinals, moveProductionTask, setAutomaticComposition } from '../../api/finalComposition';
import { compareProductionUnits, movedTaskOrder, applyTaskOrder } from './productionOrder';
import { compositionStatusLabel, matchesProductionStage, productionStageCounts, type ProductionStageFilter } from './productionStatus';
import { useLongPressReorder } from './useLongPressReorder';
import { formatPlannedDate } from '../../utils/plannedDate';
import { refreshArea } from '../../services/dataHub';
import { TemplateProductionModal } from '../templates/TemplateProductionModal';
import React, { useState, useMemo, useRef, useEffect } from 'react';
import { 
  ProductionUnit, 
  ProductionVideoItem,
  ScannedMaterialClip,
  CleanupPreviewData,
} from '../../productionTypes';
import { listV2ProductionTasks, listV2ProductionTaskSummaries, getV2ProductionTaskDetails, scanV2ProductionTask, previewV2Cleanup, executeV2Cleanup, updateV2TaskInsertionStrategy, updateV2MaterialInsertionStrategy } from '../../api/v2Production';
import { FinalRegenerationModal } from './FinalRegenerationModal';
import { MaterialManagerModal } from './MaterialManagerModal';
import { MaterialDeleteDialog } from './MaterialDeleteDialog';
import { InsertionSettingsModal, overrideSummary, materialInsertionSummary } from './InsertionSettingsModal';
import { openV2File, openV2Folder } from '../../api/v2Catalog';
import { toProductionUnit } from '../../adapters/production';
import { formatElapsedSeconds } from '../../utils/duration';
import { TemplateLibraryRegion } from './TemplateLibraryRegion';
import { DramaTaskCover } from './DramaTaskCover';
import { PublishingWorkbench } from './PublishingWorkbench';
import { useProductionPublishing, useProductionPublishIndex, ProductionPublishCardProgress, ProductionPublishLocation, ProductionPublishMount, ProductionPublishTotal, ProductionPublishVideo } from './ProductionPublishing';
import { publicationCard, publicationCardStatus } from './productionPublishingModel';
import { getCachedProductionSummary, loadProductionSummary } from '../../services/productionService';
import { loadSharedTaskCenter } from '../../services/taskCenterService';
import { useDataArea } from '../../hooks/useDataArea';
import { reuseUnchanged, reuseUnchangedRecord } from '../../utils/reuseUnchanged';
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
  Sparkles, 
  Clock, 
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
  Filter,
  Settings2,
  MoreVertical
  ,Volume2
  ,VolumeX
  ,GripVertical
  ,Power
  ,LoaderCircle
} from 'lucide-react';

let cachedProductionUnits: ProductionUnit[] | null = null;
// 页面切换会销毁组件，但已读取的剧集详情仍可复用，避免返回生产中心时重新读取全部明细。
let cachedProductionDetails: Record<string, ProductionUnit> = {};
let cachedSelectedProductionTaskId = '';
const PRODUCTION_SUMMARY_CACHE_KEY = 'v2-production-task-summaries-v1';

function readCachedProductionUnits(): ProductionUnit[] | null {
  try {
    const raw = localStorage.getItem(PRODUCTION_SUMMARY_CACHE_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw);
    return Array.isArray(parsed) ? parsed as ProductionUnit[] : null;
  } catch {
    return null;
  }
}

function saveCachedProductionUnits(units: ProductionUnit[]): void {
  try {
    localStorage.setItem(PRODUCTION_SUMMARY_CACHE_KEY, JSON.stringify(units));
    localStorage.setItem(`${PRODUCTION_SUMMARY_CACHE_KEY}:updated-at`, new Date().toISOString());
  } catch {
    // 缓存只用于加速，空间不足时不影响正常业务。
  }
}

interface ProductionCenterProps {
  onParameters?: () => void;
  onMakeTemplate?: () => void;
  onBackToWorkbench?: () => void;
  showToast: (msg: string) => void;
}

function getTaskCardStatus(unit: ProductionUnit): { label: string; className: string } {
  const canonical: Record<string, { label: string; className: string }> = {
    released: { label: '发布完成', className: 'bg-emerald-100 text-emerald-800' },
    action_required: { label: '待处理异常', className: 'bg-rose-100 text-rose-800' },
    final_processing: { label: '成片处理中', className: 'bg-blue-100 text-blue-800' },
    awaiting_release: { label: '待发布准备', className: 'bg-orange-50 text-orange-700' },
    awaiting_final_generation: { label: '待生成成片', className: 'bg-amber-100 text-amber-800' },
    awaiting_template: { label: '待选模板', className: 'bg-purple-100 text-purple-800' },
    awaiting_scan: { label: '待扫描素材', className: 'bg-sky-100 text-sky-800' },
    awaiting_material: { label: '待导入素材', className: 'bg-slate-200 text-slate-700' },
  };
  if (unit.taskDisplayStatus && canonical[unit.taskDisplayStatus]) return canonical[unit.taskDisplayStatus];
  return { label: '状态同步中', className: 'bg-slate-200 text-slate-700' };
}

const FinalProduction: React.FC<ProductionCenterProps> = ({
  showToast, onMakeTemplate,
}) => {
  const [units, setUnits] = useState<ProductionUnit[]>(() => cachedProductionUnits || getCachedProductionSummary() || readCachedProductionUnits() || []);
  const [lastRefreshAt, setLastRefreshAt] = useState<Date | null>(() => {
    try { const value = localStorage.getItem('v2-production-task-summaries-v1:updated-at'); return value ? new Date(value) : null; } catch { return null; }
  });
  const [detailUnits, setDetailUnits] = useState<Record<string, ProductionUnit>>(cachedProductionDetails);
  const [detailsLoading, setDetailsLoading] = useState(false);
  const detailRequests = useRef<Record<string, Promise<void>>>({});
  const [selectedUnitId, setSelectedUnitId] = useState<string>(cachedSelectedProductionTaskId);
  const [stageFilter, setStageFilter] = useState<ProductionStageFilter>('all');
  
  // Dynamic Account & Drama Filter State
  const [selectedAccount, setSelectedAccount] = useState<string>('all');
  const [selectedDrama, setSelectedDrama] = useState<string>('all');
  const [isFilterExpanded, setIsFilterExpanded] = useState<boolean>(false);

  const [isScanning, setIsScanning] = useState(false);
  const [isComposing, setIsComposing] = useState(false);
  const [regenerationTask, setRegenerationTask] = useState<ProductionUnit | null>(null);
  const [regeneratingId, setRegeneratingId] = useState<string | null>(null);
  const regenerationBusy = useRef(false);
  const [autoChanging,setAutoChanging]=useState(false),[orderSaving,setOrderSaving]=useState(false);
  const [automaticEnabled,setAutomaticEnabled]=useState(false);
  const taskListRef=useRef<HTMLDivElement>(null),pendingOrder=useRef<string[]|null>(null);

  // Material Track Wheel-Scroll Ref
  const materialTrackRef = useRef<HTMLDivElement>(null);

  // Modals & Drawers
  const [isFinalVideoPreviewOpen, setIsFinalVideoPreviewOpen] = useState(false);
  const [previewMaterialClip, setPreviewMaterialClip] = useState<ScannedMaterialClip | null>(null);
  const [materialManager, setMaterialManager] = useState<{taskId: string; materialId?: string} | null>(null);
  const [deletingMaterialId, setDeletingMaterialId] = useState<string | null>(null);
  const materialPreviewPlayer = useRef<HTMLVideoElement>(null);
  const [isMaterialPreviewMuted, setIsMaterialPreviewMuted] = useState(() => localStorage.getItem('v2-material-preview-muted') !== 'false');
  const [selectedMaterialClipId, setSelectedMaterialClipId] = useState<string | null>(null);
  const [insertionTask, setInsertionTask] = useState<ProductionUnit | null>(null);
  const [materialInsertionClip, setMaterialInsertionClip] = useState<ScannedMaterialClip | null>(null);
  const [materialInsertionTask, setMaterialInsertionTask] = useState<ProductionUnit | null>(null);
  
  // Danger Actions Modal State (completed publication cleanup vs failed/unpublished task deletion)
  const [isCleanupModalOpen, setIsCleanupModalOpen] = useState(false);
  const [cleanupActionState, setCleanupActionState] = useState<'idle' | 'executing' | 'done'>('idle');
  const [cleanupPreview, setCleanupPreview] = useState<CleanupPreviewData | null>(null);
  const [isCleanupListExpanded, setIsCleanupListExpanded] = useState(false);

  const [publishingTaskId, setPublishingTaskId] = useState('');
  const publishingProgress = useProductionPublishing(selectedUnitId, !!publishingTaskId);
  const publicationIndex = useProductionPublishIndex();

  const applyFullTaskList = (items: Awaited<ReturnType<typeof listV2ProductionTasks>>['items']) => {
    const nextUnits = items.map(toProductionUnit);
    const nextDetails = { ...cachedProductionDetails };
    nextUnits.forEach((unit) => { nextDetails[unit.id] = unit; });
    cachedProductionDetails = nextDetails;
    saveCachedProductionUnits(nextUnits);
    setDetailUnits(nextDetails);
    setUnits(nextUnits);
  };

  // ── 统一数据层接入（刷新大修 · 第 1b 步）──────────────────────────────
  // 「什么时候刷」交给 dataHub（每 3 秒）；「数据怎么合并」仍是下面原来的逻辑，一个字没改。
  // 旧实现是"60 秒兜底 + 变更事件"，而事件还带 2.5 秒抑制窗口、会吞掉真实变更。
  const accountCatalog = useDataArea<Awaited<ReturnType<typeof fetchAssetsCenterSeedForDataHub>>>('catalog', fetchAssetsCenterSeedForDataHub);
  const summaryArea = useDataArea<ProductionUnit[]>('production', () => loadProductionSummary(true));
  // ⚠️ 顶栏、任务中心、生产中心订阅的是**同一个区域**，所以必须用**同一个取数方法**，
  // 否则谁最后注册谁生效、三处拿到的就不是同一份快照（数字会对不上）。
  const taskCenterArea = useDataArea<Awaited<ReturnType<typeof loadSharedTaskCenter>>>(
    'taskCenter',
    () => loadSharedTaskCenter(true),
  );

  // 首次挂载复用生产任务缓存；公共模板由独立区域读取。
  useEffect(() => {
    let active = true;
    if (cachedProductionUnits) setUnits(cachedProductionUnits);
    else {
      const persistedUnits = readCachedProductionUnits();
      if (persistedUnits) {
        cachedProductionUnits = persistedUnits;
        setUnits(persistedUnits);
      }
    }
    return () => { active = false; };
  }, []);

  // 摘要数据回来后执行合并（原逻辑原样搬过来）
  useEffect(() => {
    if (!summaryArea.data) return;
    const realUnits = pendingOrder.current?applyTaskOrder(summaryArea.data,pendingOrder.current):summaryArea.data;
    // 摘要接口只包含统计与模板/导出状态，素材和成片明细有意留空。
    // 已打开任务若继续直接优先使用旧详情缓存，就会永远看不到导出完成。
    // 因此把摘要的新状态合并进去；若本轮退回到完整接口，则以完整详情整体替换。
    const isSummaryResponse = true;
    cachedProductionUnits = realUnits;
    saveCachedProductionUnits(realUnits);
    // 用 dataHub 的 updatedAt：它**只在成功时前进**，所以这个时间不会骗人。
    // （旧实现无论成功失败都写 new Date()，这正是"更新于 HH:mm 不可信"的来源。）
    setLastRefreshAt(summaryArea.updatedAt ? new Date(summaryArea.updatedAt) : null);
    // 让"内容没变的条目"沿用旧引用：没变化时整块列表不重画（用户要求"不卡、不闪"）。
    // 详见 src/utils/reuseUnchanged.ts 顶部说明。
    setUnits((previous) => reuseUnchanged(previous, realUnits));
    setDetailUnits((previous) => {
      const next: Record<string, ProductionUnit> = {};
      realUnits.forEach((unit) => {
        const previousDetail = previous[unit.id];
        if (previousDetail && isSummaryResponse) {
          // 摘要接口故意不做文件探测，因此没有正式模板视频名、大小、
          // 时长和阶段耗时。不能用这些空字段覆盖已加载详情，否则页面会
          // 在“草稿名/无耗时”和“正式视频/真实耗时”之间来回跳。
          const sameTemplateVersion = previousDetail.templateDraftName === unit.templateDraftName;
          next[unit.id] = {
            ...unit,
            scannedMaterials: previousDetail.scannedMaterials,
            videos: previousDetail.videos,
            ...(sameTemplateVersion ? {
              templateVideoUrl: unit.templateVideoUrl || previousDetail.templateVideoUrl,
              templateVideoName: unit.templateVideoName || previousDetail.templateVideoName,
              templateDurationSec: unit.templateDurationSec ?? previousDetail.templateDurationSec,
              templateDurationText: unit.templateDurationText || previousDetail.templateDurationText,
              templateFileSizeText: unit.templateFileSizeText || previousDetail.templateFileSizeText,
              templateDraftDuration: unit.templateDraftDuration || previousDetail.templateDraftDuration,
              templateDraftDurationSeconds: unit.templateDraftDurationSeconds ?? previousDetail.templateDraftDurationSeconds,
              templateExportDuration: unit.templateExportDuration || previousDetail.templateExportDuration,
              templateExportDurationSeconds: unit.templateExportDurationSeconds ?? previousDetail.templateExportDurationSeconds,
              templateTotalDuration: unit.templateTotalDuration || previousDetail.templateTotalDuration,
            } : {}),
          };
        } else if (!isSummaryResponse) {
          next[unit.id] = unit;
        }
      });
      // 同理：详情字典里没变的条目也沿用旧引用，避免右侧详情区被无谓重画
      const merged = reuseUnchangedRecord(previous, next);
      cachedProductionDetails = merged;
      return merged;
    });
    setSelectedUnitId((current) => {
      const visible = realUnits.filter(unit => matchesProductionStage(unit, stageFilter)
        && (selectedAccount === 'all' || unit.accountName === selectedAccount)
        && (selectedDrama === 'all' || unit.dramaName === selectedDrama));
      const next = current && visible.some(unit => unit.id === current) ? current : visible[0]?.id || '';
      cachedSelectedProductionTaskId = next;
      return next;
    });
    setPublishingTaskId(current => current && realUnits.some(unit => unit.id === current) ? current : '');
    if (selectedUnitId && !realUnits.some(unit => unit.id === selectedUnitId)) {
      setIsFinalVideoPreviewOpen(false);
      setPreviewMaterialClip(null);
      setIsCleanupModalOpen(false);
    }
  }, [summaryArea.data, summaryArea.updatedAt]);

  const loadProductionDetails = (taskId: string, force = false) => {
    if (!taskId || (!force && cachedProductionDetails[taskId]) || detailRequests.current[taskId]) return;
    const request = getV2ProductionTaskDetails(taskId).then((task) => {
      setDetailUnits((previous) => {
        const next = { ...previous, [taskId]: toProductionUnit(task) };
        cachedProductionDetails = next;
        return next;
      });
    }).catch(() => undefined).finally(() => { delete detailRequests.current[taskId]; });
    detailRequests.current[taskId] = request;
  };

  useEffect(() => {
    if (!selectedUnitId || detailUnits[selectedUnitId]) return;
    let active = true;
    setDetailsLoading(true);
    loadProductionDetails(selectedUnitId);
    const timer = window.setInterval(() => {
      if (cachedProductionDetails[selectedUnitId]) {
        window.clearInterval(timer);
        if (active) setDetailsLoading(false);
      }
    }, 50);
    const timeout = window.setTimeout(() => { window.clearInterval(timer); if (active) setDetailsLoading(false); }, 12000);
    return () => { active = false; window.clearInterval(timer); window.clearTimeout(timeout); };
  }, [selectedUnitId, detailUnits]);

  // 已打开的详情先用缓存秒开，再只静默校验当前剧集，避免详情长期停留在旧状态。
  useEffect(() => {
    if (!selectedUnitId) return;
    let active = true;
    const refreshCurrentDetail = () => {
      if (!active || document.hidden) return;
      loadProductionDetails(selectedUnitId, true);
    };
    refreshCurrentDetail();
    const timer = window.setInterval(refreshCurrentDetail, 5000);
    const onVisibilityChange = () => { if (!document.hidden) refreshCurrentDetail(); };
    document.addEventListener('visibilitychange', onVisibilityChange);
    return () => {
      active = false;
      window.clearInterval(timer);
      document.removeEventListener('visibilitychange', onVisibilityChange);
    };
  }, [selectedUnitId]);

  useEffect(() => {
    cachedSelectedProductionTaskId = selectedUnitId;
  }, [selectedUnitId]);

  // Extract unique accounts & dramas from current units
  const availableAccounts = useMemo(() => {
    const map = new Map<string, string>();
    units.forEach(u => map.set(u.accountId || u.accountName, u.accountName));
    return Array.from(map.entries()).map(([id, name]) => ({ id, name }));
  }, [units]);

  const availableDramas = useMemo(() => {
    const map = new Map<string, string>();
    units.forEach(u => map.set(u.dramaId, u.dramaName));
    return Array.from(map.entries()).map(([id, name]) => ({ id, name }));
  }, [units]);

  const stageCounts = useMemo(() => productionStageCounts(units), [units]);

  // Joint Filter Verification: 
  // 1. Check if an account tag is enabled given current stageFilter and selectedDrama
  const isAccountOptionEnabled = (accName: string) => {
    return units.some(u => {
      if (!matchesProductionStage(u, stageFilter)) return false;
      if (selectedDrama !== 'all' && u.dramaName !== selectedDrama) return false;
      return u.accountName === accName;
    });
  };

  // 2. Check if a drama tag is enabled given current stageFilter and selectedAccount
  const isDramaOptionEnabled = (drmName: string) => {
    return units.some(u => {
      if (!matchesProductionStage(u, stageFilter)) return false;
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
    return [...units].sort(compareProductionUnits);
  }, [units]);

  // Multi-dimensional Filtering: Stage + Account + Drama
  const filteredUnits = useMemo(() => {
    return sortedUnits.filter(u => {
      // 1. Stage filter
      if (!matchesProductionStage(u, stageFilter)) return false;

      // 2. Account filter
      if (selectedAccount !== 'all' && u.accountName !== selectedAccount) return false;

      // 3. Drama filter
      if (selectedDrama !== 'all' && u.dramaName !== selectedDrama) return false;

      return true;
    });
  }, [sortedUnits, stageFilter, selectedAccount, selectedDrama]);

  const reorderCards=async(source:string,target:string,placement:'before'|'after')=>{
    if(orderSaving)return;
    const previous=new Map(units.map(u=>[u.id,u.manualOrder]));
    pendingOrder.current=movedTaskOrder(units,source,target,placement);setUnits(current=>applyTaskOrder(current,pendingOrder.current!));setOrderSaving(true);
    try{
      const result=await moveProductionTask(source,target,placement);
      setUnits(current=>{const next=applyTaskOrder(current,result.order);cachedProductionUnits=next;saveCachedProductionUnits(next);return next;});
      showToast('制作顺序已更新，后续成片按卡片顺序合成');
    }catch(error){setUnits(current=>current.map(u=>({...u,manualOrder:previous.get(u.id)})));showToast(error instanceof Error?error.message:'排序保存失败');}
    finally{pendingOrder.current=null;setOrderSaving(false);void refreshArea('production');void refreshArea('taskCenter');}
  };
  const cardDrag=useLongPressReorder(taskListRef,reorderCards,orderSaving);
  useEffect(()=>setAutomaticEnabled(!!taskCenterArea.data?.finalComposition?.auto_enabled),[taskCenterArea.data?.finalComposition?.auto_enabled]);
  const toggleAutomatic=async()=>{
    if(autoChanging)return;setAutoChanging(true);
    try{const result=await setAutomaticComposition(!automaticEnabled);setAutomaticEnabled(!!result.auto_enabled);showToast(result.auto_enabled?'自动合成已开启，按卡片顺序处理已就绪任务':'自动合成已关闭，当前一条完成后停下自动任务');void refreshArea('taskCenter');}
    catch(error){showToast(error instanceof Error?error.message:'自动合成设置失败');}
    finally{setAutoChanging(false);}
  };

  useEffect(() => {
    if (filteredUnits.some(unit => unit.id === selectedUnitId)) return;
    const next = filteredUnits[0]?.id || '';
    setSelectedUnitId(next);
    cachedSelectedProductionTaskId = next;
  }, [filteredUnits, selectedUnitId]);

  const selectedUnit = useMemo(() => {
    const summary = filteredUnits.find(u => u.id === selectedUnitId) || filteredUnits[0];
    return summary ? (detailUnits[summary.id] || summary) : undefined;
  }, [units, selectedUnitId, filteredUnits, detailUnits]);

  const materialManagerUnit = materialManager ? (detailUnits[materialManager.taskId] || units.find(unit => unit.id === materialManager.taskId)) : undefined;

  const cleanupItems = cleanupPreview?.itemsToDelete ?? [];
  const visibleCleanupItems = isCleanupListExpanded ? cleanupItems : cleanupItems.slice(0, 10);
  const hiddenCleanupItemCount = Math.max(0, cleanupItems.length - visibleCleanupItems.length);

  const productionDurations = useMemo(() => {
    if (!selectedUnit) return { generation: '—' };
    const jobs = (taskCenterArea.data?.finalComposition?.jobs || []).filter(j => j.task_id === selectedUnit.id);
    const times = (selectedUnit.videos ?? []).map(video => liveVideo(video, jobs).generationDurationSeconds).filter((v): v is number => v != null);
    return { generation: times.length ? formatElapsedSeconds(times.reduce((a,b)=>a+b,0),'—') : '—' };
  }, [selectedUnit, taskCenterArea.data?.finalComposition]);

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
      // 列表摘要只含数量；右侧会优先使用已加载的详情缓存。扫描完成后必须
      // 更新同一份详情，否则摘要已变而素材缩略图区仍显示扫描前的旧数据。
      const refreshedUnit = toProductionUnit(await getV2ProductionTaskDetails(selectedUnit.id));
      cachedProductionDetails = { ...cachedProductionDetails, [refreshedUnit.id]: refreshedUnit };
      setDetailUnits(cachedProductionDetails);
      setUnits((previous) => {
        const next = previous.map((unit) => unit.id === refreshedUnit.id ? refreshedUnit : unit);
        cachedProductionUnits = next;
        saveCachedProductionUnits(next);
        return next;
      });
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

  const handleBatchGenerateVideos = async () => {
    if (!selectedUnit || isComposing || regenerationBusy.current) return;
    setIsComposing(true);
    try {
      const result = await createFinalBatch(selectedUnit.id);
      showToast(result.created_count ? `已加入FFmpeg合成队列：${result.created_count}条，已完成或排队${result.skipped_count}条已跳过。` : '素材已完成或已在合成队列中。');
      loadProductionDetails(selectedUnit.id, true);
      await Promise.all([refreshArea('taskCenter'), refreshArea('production')]);
    } catch (error) { showToast(error instanceof Error ? error.message : '合成提交失败'); }
    finally { setIsComposing(false); }
  };
  const handleRegenerate = async (taskId: string, videoId?: string) => {
    if (regenerationBusy.current || isComposing) return;
    regenerationBusy.current = true;
    setRegeneratingId(videoId || 'batch');
    try {
      const result = await regenerateFinals(taskId, videoId);
      setRegenerationTask(null);
      showToast(`已按当前中插、尾插设置重新加入合成队列：${result.regenerated_count}条。旧成品已删除，新成品沿用原文件名；队列暂停状态不变。`);
      loadProductionDetails(taskId, true);
      await Promise.all([refreshArea('taskCenter'), refreshArea('production')]);
    } catch (error) { showToast(error instanceof Error ? error.message : '重新生成提交失败'); }
    finally { regenerationBusy.current = false; setRegeneratingId(null); }
  };
  const completedFinalVideos = useMemo(
    () => (selectedUnit?.videos || []).filter((video) => video.status === 'exported' && Boolean(video.videoUrl)),
    [selectedUnit],
  );
  const handlePlayVideo = (_video: ProductionVideoItem) => setIsFinalVideoPreviewOpen(true);

  const applyInsertionDetails = (task: Awaited<ReturnType<typeof getV2ProductionTaskDetails>>) => {
    const refreshed = toProductionUnit(task);
    cachedProductionDetails = { ...cachedProductionDetails, [refreshed.id]: refreshed };
    setDetailUnits(cachedProductionDetails);
    setUnits(previous => {
      const next = previous.map(unit => unit.id === refreshed.id ? refreshed : unit);
      cachedProductionUnits = next; saveCachedProductionUnits(next); return next;
    });
    void refreshArea('production');
  };

  const openMaterialInsertionSettings = (clip: ScannedMaterialClip) => {
    setMaterialInsertionTask(selectedUnit || null);
    setMaterialInsertionClip(clip);
  };

  // Danger Actions:
  // Only an automatically verified official publication enters the cleanup lifecycle; other tasks are deletions.
  const handleOpenDangerModal = async () => {
    if (!selectedUnit) return;
    try {
      setCleanupPreview(await previewV2Cleanup(selectedUnit.id));
      setIsCleanupListExpanded(false);
      setCleanupActionState('idle');
      setIsCleanupModalOpen(true);
    }
    catch (error) { showToast(error instanceof Error ? error.message : '无法读取清理预览。'); }
  };
  const handleExecuteCleanup = async () => {
    if (!selectedUnit) return;
    // Keep the action target stable while the task list is refreshed. When the
    // last task is deleted, the refresh makes selectedUnit undefined before
    // the async handler finishes; using the captured target avoids reading
    // from a disappearing card and lets the empty state render normally.
    const targetUnit = selectedUnit;
    setCleanupActionState('executing');
    try {
      const result = await executeV2Cleanup(targetUnit.id);
      if (result.errors.length) { showToast(`清理部分完成：${result.errors.join('；')}`); setCleanupActionState('idle'); return; }
      // Close the modal before replacing the selected task list. This avoids
      // one intermediate render where the modal still expects selectedUnit
      // while the final card has already been removed.
      setIsCleanupModalOpen(false);
      const tasks = await listV2ProductionTasks(); applyFullTaskList(tasks.items);
      await Promise.all([refreshArea('taskCenter'), refreshArea('production')]);
      setCleanupActionState('done'); showToast(targetUnit.releaseStatus === 'registered' ? '立即清理已完成。' : '剧集已删除。');
    } catch (error) { setCleanupActionState('idle'); showToast(error instanceof Error ? error.message : '清理失败，请稍后重试。'); }
  };

  return (
    <div 
      className="space-y-4 animate-in fade-in duration-200 max-w-[1840px] mx-auto w-full"
    >
      <style>{'@keyframes cover-hold{from{transform:scaleX(0)}to{transform:scaleX(1)}}'}</style>
      {cardDrag.drag&&<div data-testid="production-drag-preview" style={{left:cardDrag.drag.x+14,top:cardDrag.drag.y+12}} className="pointer-events-none fixed z-[150] max-w-[290px] rounded-xl border border-lime-300 bg-white/95 px-4 py-3 text-xs shadow-2xl backdrop-blur"><div className="mb-1 flex items-center gap-1 text-[10px] font-bold text-lime-700"><GripVertical size={12}/>调整合成顺序 · ESC取消</div><strong className="block truncate text-[#1A1D2E]">{units.find(u=>u.id===cardDrag.drag!.id)?.accountName} · {units.find(u=>u.id===cardDrag.drag!.id)?.dramaName}</strong></div>}
      {/* Top Banner / Operational Metric Bar (Retained without extra business logic) */}
      <div className="bg-white rounded-2xl p-4 border border-black/[0.06] shadow-xs flex flex-wrap items-center justify-between gap-4">
        <div className="flex items-center gap-3.5">
          <div className="w-10 h-10 rounded-xl bg-[#1A1D2E] text-[#DDFD00] flex items-center justify-center font-bold shadow-xs">
            <Layers className="w-5 h-5" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <div className="flex items-center gap-2"><h2 className="text-lg font-black text-[#1A1D2E] tracking-tight">生产中心 (Production Center)</h2>{lastRefreshAt && <span className="text-[10px] font-normal text-slate-400">更新于 {lastRefreshAt.toLocaleTimeString('zh-CN', { timeZone: 'Asia/Shanghai' })}</span>}</div>
              <span className="px-2.5 py-0.5 rounded-full text-[11px] font-extrabold bg-[#DDFD00] text-[#1A1D2E]">
                独立制作单元：账号 × 剧集
              </span>
            </div>
            <p className="text-xs text-[#64748B] mt-0.5">
              桌面工作区：素材同步 ➔ 模板选用 ➔ 成片合成 ➔ 发布准备
            </p>
          </div>
        </div>

        {/* Global Pipeline Summary Badges */}
        <div className="flex items-center gap-2.5 text-xs">
          <button type="button" data-testid="automatic-composition" role="switch" aria-checked={automaticEnabled} disabled={autoChanging} onClick={()=>void toggleAutomatic()} title="记住上次开关状态；开启后按卡片顺序合成已有素材且已选模板的任务。关闭不打断当前一条。" className={`flex items-center gap-2 rounded-xl border px-3 py-1.5 text-xs font-bold transition-all disabled:opacity-50 ${automaticEnabled?'border-lime-300 bg-[#DDFD00] text-[#1A1D2E] shadow-sm':'border-slate-200 bg-slate-50 text-slate-500 hover:border-slate-400'}`}>
            {autoChanging?<LoaderCircle className="h-3.5 w-3.5 animate-spin"/>:<Power className="h-3.5 w-3.5"/>}<span>自动合成</span><span className={`text-[10px] ${automaticEnabled?'text-lime-900':'text-slate-400'}`}>{automaticEnabled?'已开启':'已关闭'}</span>
          </button>
          {automaticEnabled&&taskCenterArea.data?.finalComposition?.auto_error&&<span className="max-w-[120px] truncate text-[10px] text-amber-700" title={taskCenterArea.data.finalComposition.auto_error}>有任务需处理</span>}
          {automaticEnabled&&taskCenterArea.data?.finalComposition?.paused&&<span className="text-[10px] text-amber-700">合成队列已暂停</span>}
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
            <span className="text-[#64748B]">已完成发布:</span>
            <span className="font-bold text-[#1A1D2E]">
              {units.filter(u => u.releaseStatus === 'registered').length} 个
            </span>
          </div>
        </div>
      </div>

      {/* Main 2-Column Desktop Workspace (Height constrained to prevent whole-page scrolling) */}
      <div className="grid grid-cols-1 xl:grid-cols-[320px_minmax(0,1fr)] gap-5 items-start">
        
        {/* Task list keeps a compact width so the production workspace has more room. */}
        <div className="min-w-0 bg-white rounded-3xl p-4 border border-black/[0.06] shadow-xs flex flex-col h-[calc(100vh-185px)] min-h-[640px]">
          
          {/* 1. Stage Filter Bar */}
          <div className="flex items-center gap-2 text-xs shrink-0 mb-2.5" data-testid="production-stage-filters">
          <div role="group" aria-label="进行中的剧集筛选" className="flex min-w-0 flex-1 items-center gap-1 p-1 bg-black/[0.03] rounded-xl border border-black/[0.03]">
            <button
              onClick={() => setStageFilter('all')}
              className={`flex-1 py-1.5 rounded-lg font-bold transition-all text-center cursor-pointer ${
                stageFilter === 'all' ? 'bg-white text-[#1A1D2E] shadow-xs' : 'text-[#64748B] hover:text-[#1A1D2E]'
              }`}
            >
              全部 ({stageCounts.all})
            </button>
            <button
              onClick={() => setStageFilter('in_progress')}
              className={`flex-1 py-1.5 rounded-lg font-semibold transition-all text-center cursor-pointer ${
                stageFilter === 'in_progress' ? 'bg-white text-[#1A1D2E] shadow-xs' : 'text-[#64748B] hover:text-[#1A1D2E]'
              }`}
            >
              未完成 ({stageCounts.in_progress})
            </button>
            <button
              onClick={() => setStageFilter('overdue')}
              className={`flex-1 py-1.5 rounded-lg font-semibold transition-all text-center cursor-pointer ${
                stageFilter === 'overdue' ? 'bg-white text-rose-700 shadow-xs font-bold' : 'text-[#64748B] hover:text-rose-600'
              }`}
            >
              逾期 ({stageCounts.overdue})
            </button>
          </div>
          <div role="group" aria-label="已完成剧集筛选" className="flex shrink-0 p-1 bg-black/[0.03] rounded-xl border border-black/[0.03]">
            <button
              onClick={() => setStageFilter('completed')}
              className={`px-2 py-1.5 rounded-lg font-semibold transition-all text-center cursor-pointer ${
                stageFilter === 'completed' ? 'bg-white text-slate-700 shadow-xs' : 'text-[#64748B] hover:text-slate-900'
              }`}
            >
              已完成 ({stageCounts.completed})
            </button>
          </div>
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
          <div ref={taskListRef} data-testid="production-card-list" className="flex-1 overflow-y-auto space-y-2.5 pr-1 no-scrollbar">
            {filteredUnits.length === 0 ? (
              <div className="py-12 text-center text-xs text-[#64748B] space-y-1">
                <p className="font-bold">暂无符合筛选条件的制作任务</p>
                <p className="text-[11px]">可尝试切换筛选条件或点击「重置筛选」</p>
              </div>
            ) : (
              filteredUnits.map((unit) => {
                const displayUnit = detailUnits[unit.id] || unit;
                const isSelected = unit.id === selectedUnit?.id;
                const cardPublication = unit.id === selectedUnitId && publishingProgress.data ? publicationCard(publishingProgress.videos) : publicationIndex[unit.id];
                const taskCardStatus = unit.isCompleted ? { label: cardPublication?.scheduled && !cardPublication.draft_only ? '官方已定时' : '发布完成', className: 'border border-emerald-100 bg-emerald-50 text-emerald-700' } : cardPublication ? { label: publicationCardStatus(cardPublication), className: 'border border-violet-100 bg-violet-50 text-violet-700' } : getTaskCardStatus(displayUnit);
                const accountRecord = accountCatalog.data?.accounts.find(a => a.id === unit.accountId);
                const avatarUrl = accountRecord?.avatarUrl;

                return (
                  <div
                    key={unit.id}
                    data-production-task={unit.id} data-reorderable={!unit.isCompleted} data-testid="production-task-card"
                    title={unit.isCompleted?'已交付官方，等待清理':'长按1秒拖动，调整成片合成顺序'}
                    onPointerDown={cardDrag.pointerDown(unit.id,!unit.isCompleted)} onClickCapture={cardDrag.clickCapture}
                    onMouseEnter={() => loadProductionDetails(unit.id)}
                    onClick={() => { setSelectedUnitId(unit.id); loadProductionDetails(unit.id); }}
                    className={`p-3 rounded-2xl border transition-all cursor-pointer select-none relative ${cardDrag.drag?.id===unit.id?'opacity-40 scale-[.98] ring-2 ring-lime-400':''} ${
                      unit.isCompleted
                        ? isSelected
                          ? 'bg-slate-100/90 border-slate-400 shadow-sm opacity-85'
                          : 'bg-slate-50/60 hover:bg-slate-100/70 border-slate-200 text-slate-500 opacity-65'
                        : isSelected
                        ? 'bg-white border-[#1A1D2E] shadow-md ring-2 ring-[#1A1D2E]/10'
                        : 'bg-white hover:bg-slate-50 border-black/[0.06] shadow-xs'
                    }`}
                  >
                    {cardDrag.pressing===unit.id&&<span className="absolute bottom-0 left-3 right-3 h-0.5 origin-left animate-[cover-hold_1s_linear] rounded-full bg-lime-500"/>}
                    {cardDrag.drag?.target===unit.id&&<span data-testid="production-drop-marker" className={`pointer-events-none absolute -left-1 -right-1 z-10 h-1 rounded-full bg-lime-400 shadow-[0_0_0_2px_white] ${cardDrag.drag.placement==='before'?'-top-1.5':'-bottom-1.5'}`}><span className="absolute right-0 -top-4 rounded bg-[#1A1D2E] px-1.5 text-[9px] text-lime-300">放到这里</span></span>}
                    {/* Layer 1: Account Identifier (Avatar + Account Name) & Status Badges */}
                    <div className="flex items-center justify-between gap-2 mb-1.5">
                      <div className="flex items-center gap-2 min-w-0">
                        <span data-testid="production-account-avatar"><AccountAvatar name={accountRecord?.nickname || unit.accountName} url={avatarUrl} className="w-10 h-10 shadow-2xs" /></span>
                        <div className="min-w-0 flex flex-col gap-0.5">
                          <span className={`font-black text-sm leading-5 tracking-tight truncate ${unit.isCompleted ? 'text-slate-600 font-semibold' : 'text-[#1A1D2E]'}`}>
                            {unit.accountName}
                          </span>
                          {accountRecord?.theaterName && <span data-testid="production-account-theater" className="truncate text-[10px] leading-3.5 font-medium text-slate-500" title={accountRecord.theaterName}>{accountRecord.theaterName}</span>}
                        </div>
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
                      <div
                        data-testid="production-drama-name"
                        title="右键复制剧名"
                        onContextMenu={async event => {
                          event.preventDefault();
                          event.stopPropagation();
                          const name = unit.dramaName.replace(/[《》]/g, '').trim();
                          if (!name) return showToast('剧名为空，无法复制。');
                          try {
                            if (navigator.clipboard?.writeText) await navigator.clipboard.writeText(name);
                            else {
                              const input = document.createElement('textarea');
                              input.value = name;
                              input.style.position = 'fixed';
                              input.style.opacity = '0';
                              document.body.appendChild(input);
                              try {
                                input.select();
                                if (!document.execCommand('copy')) throw new Error('复制失败');
                              } finally { input.remove(); }
                            }
                            showToast(`已复制剧名：${name}`);
                          } catch { showToast('复制失败，请重试。'); }
                        }}
                        className="flex items-center gap-1 font-extrabold text-[#1A1D2E] truncate max-w-[185px]"
                      >
                        <Film className="w-3.5 h-3.5 text-slate-400 shrink-0" />
                        <span className="truncate">《{unit.dramaName}》</span>
                      </div>

                      <div className="flex items-center gap-1 text-[11px] text-[#64748B] shrink-0">
                        <Clock className="w-3 h-3 text-slate-400" />
                        <span className={unit.isOverdue && !unit.isCompleted ? 'text-rose-700 font-bold' : ''}>
                          {formatPlannedDate(unit.scheduledDate)}
                        </span>
                      </div>
                    </div>

                    <div className="mt-2.5 pt-2 border-t border-black/[0.04]">
                      {cardPublication ? <ProductionPublishCardProgress value={cardPublication} /> : <ProductionProgress unit={displayUnit} jobs={taskCenterArea.data?.finalComposition?.jobs} compact />}
                    </div>
                  </div>
                );
              })
            )}
          </div>
        </div>

        {/* Current Account × Drama Production Workspace */}
        {!selectedUnit && <div className="flex min-h-64 flex-col items-center justify-center gap-3 rounded-3xl border border-black/[0.06] bg-white p-8 text-sm text-slate-500"><p>选择制作任务查看成片；也可以先制作公共模板。</p><button type="button" onClick={onMakeTemplate} className="rounded-xl bg-[#1A1D2E] px-4 py-2 text-xs font-black text-[#DDFD00]">制作模板</button></div>}
        {selectedUnit && (
          <div className="min-w-0 bg-white rounded-3xl p-5 border border-black/[0.06] shadow-xs flex flex-col h-[calc(100vh-185px)] min-h-[640px] space-y-4 [@media(max-height:1100px)]:overflow-y-auto">
            
            {/* Header Area (Fixed at top) */}
            <div data-testid="production-task-header" className="pb-3.5 border-b border-black/[0.06] shrink-0 space-y-3">
              <div className="flex flex-nowrap items-start justify-between gap-3">
                <DramaTaskCover key={selectedUnit.id} taskId={selectedUnit.id} name={selectedUnit.dramaName} showToast={showToast} />
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2">
                    <span className="px-2.5 py-0.5 rounded-lg bg-[#1A1D2E] text-[#DDFD00] font-black text-xs">
                      制作任务
                    </span>
                    <h3 className="min-w-0 truncate text-xl font-black text-[#1A1D2E] tracking-tight" title={`${selectedUnit.accountName} × 《${selectedUnit.dramaName}》`}>
                      {selectedUnit.accountName} × 《{selectedUnit.dramaName}》
                    </h3>
                    {selectedUnit.mountSource && <span className="shrink-0 rounded-lg bg-slate-100 px-2 py-1 text-[10px] font-bold text-slate-500">{{ mini_drama: '小程序挂载', channels_drama: '视频号挂载', plugin: '插件挂载' }[selectedUnit.mountSource]}</span>}
                  </div>
              <div className="flex flex-col items-start gap-1 text-xs text-[#64748B] mt-1.5">
                <span className="flex items-center gap-1">
                  <Clock className="w-3.5 h-3.5" /> 计划发布日期：
                  <strong className={`text-[#1A1D2E] ${selectedUnit.isOverdue && !selectedUnit.isCompleted ? 'text-rose-700 font-black' : ''}`}>
                    {formatPlannedDate(selectedUnit.scheduledDate)}
                  </strong>
                  {selectedUnit.isOverdue && !selectedUnit.isCompleted && (
                    <span className="text-[10px] px-1.5 py-0.2 bg-rose-100 text-rose-800 rounded font-bold ml-1">
                      逾期未完成
                    </span>
                  )}
                </span>
                <span data-testid="task-generation-duration" className="flex items-center gap-1">
                  <span>生成耗时：<strong className="text-[#1A1D2E]">{productionDurations.generation}</strong></span>
                </span>
                <ProductionPublishLocation videos={publishingProgress.videos} />
              </div>
                </div>

                {/* Right Top Operations: 发布完成后清理，异常任务直接删除 */}
                <div className="flex shrink-0 items-center gap-2.5">


                  {/* 发布完成后进入清理周期；未完成或异常发布只能删除剧集 */}
                  {selectedUnit.releaseStatus === 'registered' ? (
                    <button
                      onClick={handleOpenDangerModal}
                      className="flex items-center gap-1.5 px-3 py-1.5 rounded-xl bg-slate-100 hover:bg-slate-200 text-xs font-bold text-[#1A1D2E] transition-all cursor-pointer"
                      title="已成功交付官方后台：执行过程文件清理"
                    >
                      <Brush className="w-3.5 h-3.5 text-slate-600" />
                      <span>立即清理</span>
                    </button>
                  ) : (
                    <button
                      onClick={handleOpenDangerModal}
                      className="flex items-center gap-1.5 px-3 py-1.5 rounded-xl bg-rose-50 hover:bg-rose-100 border border-rose-200 text-xs font-bold text-rose-700 transition-all cursor-pointer"
                      title="发布未完成或未匹配官方作品：删除当前制作任务及关联生产数据"
                    >
                      <Trash2 className="w-3.5 h-3.5 text-rose-600" />
                      <span>删除剧集</span>
                    </button>
                  )}
                  <button type="button" onClick={() => setPublishingTaskId(selectedUnit.id)} className="flex items-center gap-1.5 rounded-xl bg-[#1A1D2E] px-3.5 py-1.5 text-xs font-black text-[#DDFD00] hover:bg-black">
                    <ExternalLink className="h-3.5 w-3.5" />自动发布
                  </button>
                </div>
              </div>


            </div>

            <div className="grid min-w-0 shrink-0 grid-cols-1 gap-x-4 gap-y-2.5 xl:grid-cols-[minmax(0,0.8fr)_minmax(0,1.2fr)] xl:grid-rows-[auto_auto]" data-testid="production-input-regions">
              {/* SECTION 1: Materials and templates share one row on desktop. */}
              <div className="grid min-w-0 grid-rows-[auto_auto] gap-2.5 p-3.5 rounded-2xl bg-[#F8FAFC] border border-black/[0.06] xl:row-span-2 xl:grid-rows-subgrid" data-testid="material-region">
                <div className="flex flex-wrap items-center justify-between gap-2.5 self-start">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="w-5 h-5 rounded-full bg-[#1A1D2E] text-[#DDFD00] flex items-center justify-center text-[11px] font-black">
                      1
                    </span>
                    <button type="button" onClick={() => setMaterialManager({taskId: selectedUnit.id})} className="rounded-md font-black text-sm text-[#1A1D2E] underline-offset-4 hover:underline focus-visible:outline-2 focus-visible:outline-offset-4" title="打开素材管理：预览、插片设置和删除">素材区域</button>
                    <span className="text-xs font-bold text-slate-700 bg-white px-2 py-0.5 rounded-lg border border-black/[0.05]">
                      有效素材 <strong className="inline-flex min-w-5 items-center justify-center rounded-md bg-[#1A1D2E] px-1.5 text-[#DDFD00] tabular-nums">{selectedUnit.scannedMaterials?.length || 0}</strong> 条
                    </span>
                  </div>

                  <div className="flex shrink-0 items-center gap-2">
                    <button
                      type="button"
                      onClick={() => setInsertionTask(selectedUnit)}
                      disabled={selectedUnit.isCompleted}
                      className={`flex items-center gap-1 px-2.5 py-1.2 rounded-xl border text-xs font-semibold cursor-pointer ${selectedUnit.insertionStrategy ? 'bg-amber-50 border-amber-200 text-amber-800' : 'bg-white border-black/[0.08] text-[#1A1D2E]'}`}
                      title="设置当前账号×剧集下所有素材的默认插片规则"
                    >
                      <Settings2 className="w-3.5 h-3.5" />
                      <span>{overrideSummary(selectedUnit.insertionStrategy)}</span>
                    </button>
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
                      title="保留已有编号；新增素材从最大序号续接，优先衔接最后一条的类型"
                    >
                      <Scan className={`w-3.5 h-3.5 ${isScanning ? 'animate-spin' : ''}`} />
                      <span>{isScanning ? '正在扫描...' : '扫描素材'}</span>
                    </button>
                  </div>
                </div>

                {/* Material horizontal scroll track with compact previews and file details */}
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
                          className={`w-32 bg-white rounded-xl overflow-hidden p-2 flex flex-col justify-between group transition-all shrink-0 select-none cursor-pointer ${
                            isSelected
                              ? 'border border-black/[0.06] shadow-xs'
                              : 'border border-black/[0.06] hover:border-black/20 hover:shadow-xs'
                          }`}
                        >
                          {/* Portrait preview preserves the entire video image. */}
                          <div className="aspect-[9/20] w-full rounded-lg bg-slate-900 overflow-hidden relative mb-1.5" data-testid="material-thumbnail">
                            <button
                              type="button"
                              onClick={(event) => { event.stopPropagation(); openMaterialInsertionSettings(clip); }}
                              disabled={selectedUnit.isCompleted}
                              aria-label={`${clip.title}插片设置`}
                              className="absolute top-1 left-1 z-10 w-6 h-6 rounded-lg bg-white/90 text-[#1A1D2E] flex items-center justify-center opacity-70 group-hover:opacity-100 focus-visible:opacity-100 transition-opacity shadow-sm cursor-pointer"
                              title="设置本素材插片规则"
                            >
                              <MoreVertical className="w-3.5 h-3.5" />
                            </button>
                            {clip.thumbnailUrl || selectedUnit.coverUrl ? (
                              <img
                                src={clip.thumbnailUrl || selectedUnit.coverUrl}
                                alt={clip.title}
                                className="w-full h-full object-contain"
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

                          {/* Show the actual material filename, including the sheep marker. */}
                          <div className="space-y-0.5">
                            <div className="text-xs font-bold text-[#1A1D2E] min-w-0 truncate" title={clip.title}>
                              {clip.title}
                            </div>
                            <p className="text-[10px] text-[#64748B] truncate">
                              {clip.durationText} · {clip.fileSizeText}
                            </p>
                            <p className={`text-[10px] truncate font-bold ${clip.insertionStrategy?.midroll?.enabled === false || clip.insertionStrategy?.endroll?.enabled === false ? 'text-amber-700' : 'text-slate-400'}`}>
                              {materialInsertionSummary(clip.insertionStrategy)}
                            </p>
                          </div>
                        </div>
                      );
                    })}
                  </div>
                </div>
              </div>

              <TemplateLibraryRegion
                onMakeTemplate={onMakeTemplate}
                key={selectedUnit.id}
                taskId={selectedUnit.id}
                accountName={selectedUnit.accountName}
                dramaName={selectedUnit.dramaName}
                materialCount={selectedUnit.materialsCount}
                showToast={showToast}
              />
            </div>

            {/* SECTION 3: 成片区域 (Material-Driven Final Videos - 3-Stage Progress Rail + Independent Vertical Scroll, No Scrollbars) */}
            <div className="p-4 rounded-2xl bg-[#F8FAFC] border border-black/[0.06] flex-1 flex flex-col min-h-0 space-y-2.5 [@media(max-height:1100px)]:flex-none [@media(max-height:1100px)]:min-h-[420px]" data-testid="final-video-region">
              
              {/* Header: Title & Action Button */}
              <div className="flex items-center justify-between gap-2.5 shrink-0">
                <div className="flex min-w-0 flex-wrap items-center gap-x-3 gap-y-1">
                  <span className="w-5 h-5 rounded-full bg-[#1A1D2E] text-[#DDFD00] flex items-center justify-center text-[11px] font-black">
                    3
                  </span>
                  <span className="font-black text-sm text-[#1A1D2E]">成片区域</span>
                  <ProductionPublishTotal videos={publishingProgress.videos} refreshing={publishingProgress.refreshing} error={publishingProgress.error} onRefresh={publishingProgress.refresh} />
                </div>

                {/* Main Action: 成片生成 */}
                <div className="flex items-center gap-2">
                  <button
                    onClick={() => setIsFinalVideoPreviewOpen(true)}
                    disabled={completedFinalVideos.length === 0}
                    title={completedFinalVideos.length ? '预览已导出的成片' : '当前没有已导出的成片'}
                    className="p-2 rounded-xl border border-black/[0.06] bg-white hover:bg-slate-50 text-slate-600 hover:text-[#1A1D2E] transition-all cursor-pointer disabled:opacity-40 disabled:cursor-not-allowed"
                  >
                    <Film className="w-4 h-4" />
                  </button>
                  <button
                    type="button"
                    onClick={() => setRegenerationTask(selectedUnit)}
                    disabled={isComposing || regeneratingId !== null || selectedUnit.isCompleted || !(selectedUnit.videos || []).some(video => video.engine === 'ffmpeg')}
                    title="按当前中插、尾插设置重新生成本剧集全部成品，提交前需确认"
                    className="flex items-center gap-1.5 px-3.5 py-1.5 rounded-xl border border-black/[0.08] bg-white hover:bg-slate-50 text-[#1A1D2E] text-xs font-bold transition-all cursor-pointer disabled:opacity-40 disabled:cursor-not-allowed"
                  >
                    <RotateCcw className="w-3.5 h-3.5" />
                    <span>全部成品重新生成</span>
                  </button>
                  <button
                    onClick={handleBatchGenerateVideos}
                    disabled={isComposing || regeneratingId !== null || !selectedUnit.scannedMaterials?.length || selectedUnit.isCompleted}
                    title="使用所选模板的分层缓存合成素材，保留原声"
                    className="flex items-center gap-1.5 px-3.5 py-1.5 rounded-xl bg-[#1A1D2E] text-[#DDFD00] hover:bg-black text-xs font-black transition-all shadow-xs cursor-pointer disabled:opacity-40 disabled:cursor-not-allowed"
                  >
                    <Sparkles className="w-3.5 h-3.5 fill-[#DDFD00]" />
                    <span>{isComposing ? '提交中…' : '批量合成'}</span>
                  </button>
                </div>
              </div>

              <ProductionProgress unit={selectedUnit} jobs={taskCenterArea.data?.finalComposition?.jobs} />

              {/* Final Videos Independent Vertical Scroll Container for 20-30 items (Scrollbar visually hidden) */}
              <div className="flex-1 overflow-y-auto pr-1 space-y-2 no-scrollbar">
                {(selectedUnit.videos || []).map((item) => {
                  const vid = liveVideo(item, (taskCenterArea.data?.finalComposition?.jobs || []).filter(j => j.task_id === selectedUnit.id));
                  return (
                    <div
                      key={vid.id}
                      className="p-2.5 bg-white rounded-xl border border-black/[0.04] flex flex-wrap items-center justify-between gap-3 text-xs hover:border-black/[0.12] transition-colors"
                    >
                      {/* Left: Title & Duration & Status */}
                      <div className="flex min-w-0 flex-1 basis-72 items-center gap-2.5">
                        <span className="h-5 w-5 shrink-0 rounded-lg bg-slate-100 text-slate-700 font-extrabold flex items-center justify-center text-[11px]">
                          {vid.sequenceNumber}
                        </span>
                        <div className="min-w-0">
                          <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
                            <div className="font-extrabold text-[#1A1D2E] text-xs break-all" title={vid.title}>
                              {vid.title}
                            </div>
                            {vid.insertionResultText?.split(' · ').map(label => (
                              <span key={label} className={`inline-flex items-center rounded px-1.5 py-0.5 text-[10px] font-semibold ${label === '中插' ? 'bg-amber-50 text-amber-700' : 'bg-violet-50 text-violet-700'}`}>
                                {label}
                              </span>
                            ))}
                            <ProductionPublishMount value={publishingProgress.videos[vid.id]} />
                          </div>
                          <div className="mt-1 flex flex-wrap items-center gap-x-2 gap-y-0.5 text-[11px] text-[#64748B]">
                            <span>时长：{formatElapsedSeconds(vid.durationSec, '—')}</span>
                            <span>· 大小：{vid.fileSizeText}</span>
                            <span>· 生成耗时：<strong className="text-slate-800">{vid.generationDurationSeconds != null ? formatElapsedSeconds(vid.generationDurationSeconds, '—') : vid.generationDuration || '—'}</strong></span>
                          </div>
                        </div>
                      </div>

                      <ProductionPublishVideo value={publishingProgress.videos[vid.id]} onOpen={() => setPublishingTaskId(selectedUnit.id)} />

                      {/* Right: Status Badge & 3 Fixed Operations */}
                      <div className="flex shrink-0 items-center gap-2.5">
                        <span title={vid.generationStage || vid.errorMessage} className={`whitespace-nowrap px-2 py-0.5 rounded-lg text-[10px] font-bold ${
                          vid.status === 'exported'
                            ? 'bg-emerald-100 text-emerald-800'
                            : vid.status === 'exporting'
                            ? 'bg-indigo-50 text-indigo-700'
                            : vid.status === 'draft_ready'
                            ? 'bg-indigo-100 text-indigo-800'
                            : vid.status === 'draft_queued'
                            ? 'bg-sky-100 text-sky-800'
                            : vid.status === 'pending_export'
                            ? 'bg-sky-100 text-sky-800'
                            : vid.status === 'draft_generating'
                            ? 'bg-amber-100 text-amber-800'
                            : vid.status === 'draft_error' || vid.status === 'video_error'
                            ? 'bg-rose-100 text-rose-800'
                            : 'bg-slate-100 text-slate-600'
                        }`}>
                          {compositionStatusLabel(vid)}
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

                          <button type="button" onClick={() => void openV2Folder(selectedUnit.outputFolder || '').catch(e=>showToast(e.message))} title="打开成片目录" className="p-1 rounded-lg hover:bg-slate-100 text-slate-600"><FolderOpen className="w-3.5 h-3.5"/></button>
                          {vid.engine === 'ffmpeg' && !selectedUnit.isCompleted && ['exported','video_error','cancelled'].includes(vid.status) && <button type="button" onClick={() => void handleRegenerate(selectedUnit.id, vid.id)} disabled={isComposing || regeneratingId !== null} aria-label={`${vid.title}重新生成`} title="重新生成（立即删除旧成品，读取当前中插、尾插设置）" className="p-1 rounded-lg hover:bg-slate-100 text-slate-600 cursor-pointer disabled:opacity-40 disabled:cursor-not-allowed"><RotateCcw className={`w-3.5 h-3.5 ${regeneratingId === vid.id ? 'animate-spin' : ''}`}/></button>}
                        </div>
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>


          </div>
        )}
      </div>

      {regenerationTask && <FinalRegenerationModal
        task={regenerationTask}
        busy={regeneratingId !== null}
        onClose={() => { if (!regenerationBusy.current) setRegenerationTask(null); }}
        onConfirm={() => void handleRegenerate(regenerationTask.id)}
      />}

      {/* ================= DIALOG 2: 清理或删除预览 ================= */}
      {isCleanupModalOpen && selectedUnit && (
        <div className="fixed inset-0 z-50 bg-black/60 backdrop-blur-xs flex items-center justify-center p-4">
          <div className="bg-white rounded-3xl max-w-xl w-full max-h-[calc(100vh-2rem)] overflow-y-auto p-6 shadow-2xl border border-black/[0.08] space-y-5 animate-in fade-in zoom-in-95">
            
            {/* Header */}
            <div className="flex items-start justify-between border-b border-black/[0.06] pb-3.5">
              <div>
                <h3 className="font-black text-lg text-[#1A1D2E] flex items-center gap-2">
                  {selectedUnit.releaseStatus === 'registered' ? (
                    <>
                      <Brush className="w-5 h-5 text-slate-700" />
                      <span>立即清理（发布完成后）</span>
                    </>
                  ) : (
                    <>
                      <Trash2 className="w-5 h-5 text-rose-600" />
                      <span>删除剧集（发布未完成或异常）</span>
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
                  当前剧集<strong>已成功交付官方后台</strong>。将清理FFmpeg成片、过程缓存和任务专属临时文件；原素材按设置保留，发布记录和数据分析关联继续保留。
                </span>
              ) : (
                <span>
                  当前剧集<strong>发布未完成或无法匹配官方作品</strong>。将删除这条生产任务及其专属素材、成片、缓存和队列记录；公共模板、公共资源和数据分析历史不受影响。
                </span>
              )}
            </div>

            {cleanupPreview?.blockingReason && <p role="alert" className="rounded-xl bg-amber-50 p-3 text-xs text-amber-800">{cleanupPreview.blockingReason}</p>}

            {/* Deletion List Preview (Name on left, Size on right) */}
            <div className="space-y-2">
              <h4 className="text-xs font-bold text-[#1A1D2E] flex items-center justify-between">
                <span>{selectedUnit.releaseStatus === 'registered' ? '将清理的生产文件' : '将删除的生产数据'}</span>
                <span className="text-[11px] text-[#64748B] font-normal">后端预览预估</span>
              </h4>

              <div className="bg-slate-50 rounded-2xl border border-black/[0.04] p-3 space-y-2 text-xs">
                {visibleCleanupItems.map((item) => <div key={item.name} className="flex items-center justify-between gap-3 text-slate-700"><span className="min-w-0 truncate" title={item.name}>{item.name}</span><strong className="shrink-0 font-mono text-slate-900">{item.sizeText}</strong></div>)}
                {hiddenCleanupItemCount > 0 && (
                  <button
                    type="button"
                    onClick={() => setIsCleanupListExpanded(true)}
                    className="w-full pt-1 text-left text-[11px] font-bold text-slate-500 hover:text-[#1A1D2E] cursor-pointer"
                  >
                    已省略 {hiddenCleanupItemCount} 项，点击查看全部
                  </button>
                )}
                {isCleanupListExpanded && cleanupItems.length > 10 && (
                  <button
                    type="button"
                    onClick={() => setIsCleanupListExpanded(false)}
                    className="w-full pt-1 text-left text-[11px] font-bold text-slate-500 hover:text-[#1A1D2E] cursor-pointer"
                  >
                    收起明细，仅显示前 10 项
                  </button>
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
                {cleanupPreview?.estimatedSpaceText || '读取中'}
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
                  onClick={handleExecuteCleanup}
                  disabled={cleanupActionState === 'executing' || !cleanupPreview?.canExecute}
                  className="px-4 py-2 rounded-xl bg-[#1A1D2E] hover:bg-black text-[#DDFD00] text-xs font-black transition-all cursor-pointer shadow-xs flex items-center gap-1.5"
                >
                  <Brush className="w-3.5 h-3.5" />
                  <span>{cleanupActionState === 'executing' ? '正在执行一键清理...' : '执行一键清理'}</span>
                </button>
              ) : (
                <button
                  onClick={handleExecuteCleanup}
                  disabled={cleanupActionState === 'executing' || !cleanupPreview?.canExecute}
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

      {/* Completed final-video preview: only real, successfully exported MP4 files. */}
      {isFinalVideoPreviewOpen && selectedUnit && (
        <div className="fixed inset-0 z-50 bg-black/70 backdrop-blur-xs flex items-center justify-center p-4" onClick={() => setIsFinalVideoPreviewOpen(false)}>
          <div role="dialog" aria-modal="true" aria-label="成片预览" className="bg-white rounded-3xl max-w-5xl w-full max-h-[calc(100vh-2rem)] p-5 shadow-2xl border border-black/[0.08] space-y-4 animate-in fade-in zoom-in-95 overflow-y-auto" onClick={(event) => event.stopPropagation()}>
            <div className="flex items-center justify-between border-b border-black/[0.06] pb-3">
              <div>
                <h3 className="font-black text-base text-[#1A1D2E]">成片预览</h3>
                <p className="text-xs text-[#64748B] mt-0.5">{selectedUnit.accountName} · {selectedUnit.dramaName}</p>
              </div>
              <button onClick={() => setIsFinalVideoPreviewOpen(false)} className="p-1 rounded-lg hover:bg-slate-100 text-slate-500 cursor-pointer" title="关闭">
                <X className="w-4 h-4" />
              </button>
            </div>
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
              {completedFinalVideos.map((video) => (
                <div key={video.id} className="border border-black/[0.06] rounded-xl p-3 space-y-2.5">
                  <video
                    src={video.videoUrl}
                    poster={video.thumbnailUrl}
                    controls
                    preload="none"
                    playsInline
                    muted
                    className="final-preview-video w-full aspect-[9/20] object-contain bg-black rounded-lg cursor-pointer"
                    title="单击播放或暂停"
                    onPlay={(event) => {
                      document.querySelectorAll<HTMLVideoElement>('.final-preview-video').forEach((other) => {
                        if (other !== event.currentTarget) other.pause();
                      });
                    }}
                    onClick={(event) => {
                      event.preventDefault();
                      event.stopPropagation();
                      const element = event.currentTarget;
                      if (element.paused) {
                        void element.play().catch(() => undefined);
                      } else {
                        element.pause();
                      }
                    }}
                  />
                  <div>
                    <p className="font-black text-xs text-[#1A1D2E] break-all" title={video.title}>{video.title}</p>
                    <p className="text-[11px] text-[#64748B] mt-0.5 truncate" title={video.materialName}>{video.materialName || '—'}</p>
                    <p className="text-[11px] text-[#64748B] mt-1">{formatElapsedSeconds(video.durationSec, '—')} · {video.fileSizeText}</p>
                  </div>
                  <button type="button" onClick={() => void openV2Folder(selectedUnit.outputFolder || '').catch(e=>showToast(e.message))} className="flex w-full items-center justify-center gap-1 rounded-xl border border-black/[0.06] px-2 py-2 text-xs font-bold"><FolderOpen className="h-3.5 w-3.5"/>打开成片目录</button>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}

      {publishingTaskId && <PublishingWorkbench
        key={publishingTaskId}
        taskId={publishingTaskId}
        onClose={() => setPublishingTaskId('')}
        showToast={showToast}
      />}

      {materialManager && materialManagerUnit && <MaterialManagerModal
        key={materialManager.taskId} task={materialManagerUnit} initialMaterialId={materialManager.materialId}
        onClose={() => setMaterialManager(null)} showToast={showToast}
        onTaskChanged={async task => { applyInsertionDetails(task); await refreshArea('taskCenter'); }} />}
      {deletingMaterialId && <MaterialDeleteDialog materialId={deletingMaterialId}
        onClose={() => setDeletingMaterialId(null)}
        onBeforeDelete={() => { const player = materialPreviewPlayer.current; if (player) { player.pause(); player.removeAttribute('src'); player.load(); } }}
        onFailure={() => { const player = materialPreviewPlayer.current; if (player && previewMaterialClip?.videoUrl) { player.src = previewMaterialClip.videoUrl; player.load(); } }}
        onDeleted={async task => { applyInsertionDetails(task); setPreviewMaterialClip(null); setSelectedMaterialClipId(null); await refreshArea('taskCenter'); showToast('已删除原素材、对应成片和合成任务'); }} />}

      {insertionTask && <InsertionSettingsModal
        key={`task-insertion-${insertionTask.id}`} title="本剧集插片设置"
        subtitle={`${insertionTask.accountName} × 《${insertionTask.dramaName}》`} initial={insertionTask.insertionStrategy}
        onClose={() => setInsertionTask(null)} onSave={async (strategy) => {
          applyInsertionDetails(await updateV2TaskInsertionStrategy(insertionTask.id, strategy));
          showToast(strategy ? '本剧集插片设置已保存' : '本剧集已恢复跟随全局');
        }} />}
      {materialInsertionClip && materialInsertionTask && <InsertionSettingsModal
        key={`material-insertion-${materialInsertionClip.id}`} title="本素材插片设置" material
        subtitle={`${materialInsertionClip.title} · ${materialInsertionClip.durationText}`}
        initial={materialInsertionClip.insertionStrategy} taskOverride={materialInsertionTask.insertionStrategy}
        onClose={() => { setMaterialInsertionClip(null); setMaterialInsertionTask(null); }} onSave={async (strategy) => {
          applyInsertionDetails(await updateV2MaterialInsertionStrategy(materialInsertionClip.id, strategy));
          showToast(strategy ? '本素材插片设置已保存' : '本素材已恢复跟随剧集');
        }} />}

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
                  时长：{previewMaterialClip.durationText} · 大小: {previewMaterialClip.fileSizeText} · 分辨率: {previewMaterialClip.resolution || '读取中'}
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
                ref={materialPreviewPlayer}
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
                <button type="button" disabled={selectedUnit?.isCompleted} onClick={() => setDeletingMaterialId(previewMaterialClip.id)} className="flex items-center gap-1 px-3 py-1.5 rounded-xl border border-rose-200 bg-rose-50 hover:bg-rose-100 text-rose-700 font-bold cursor-pointer disabled:opacity-40">
                  <Trash2 className="w-3.5 h-3.5" />删除素材
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


export const ProductionCenter: React.FC<ProductionCenterProps> = props => {
  const [templateOpen, setTemplateOpen] = useState(false);
  return <div className="max-w-[1840px] mx-auto">
    <FinalProduction {...props} onMakeTemplate={() => setTemplateOpen(true)} />
    {templateOpen && <TemplateProductionModal showToast={props.showToast} onClose={() => setTemplateOpen(false)} onParameters={() => { setTemplateOpen(false); props.onParameters?.(); }} />}
  </div>;
};
