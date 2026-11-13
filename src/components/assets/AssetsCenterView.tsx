import React, { useEffect, useState } from 'react';
import {
  AssetsCenterTab,
  AccountBusinessItem,
  TheaterBusinessItem,
  SubTheaterBusinessItem,
  DramaBusinessItem,
  DramaContentProfile,
  ProductionResourceItem,
  ViralAssetItem,
} from '../../assetsTypes';
import { calculateResourceMetrics } from '../../utils/resourceMetrics';
import { fetchAssetsCenterSeedForDataHub, getCachedAssetsCenterSeed, loadAssetsCenterSeed, loadProductionResources } from '../../services/assetsCenterService';
import { BusinessDataTab } from './BusinessDataTab';
import { QueryManagementTab } from './QueryManagementTab';
import { DramaLibraryTab } from './DramaLibraryTab';
import { ProductionResourcesTab } from './ProductionResourcesTab';
import { ViralAssetsTab } from './ViralAssetsTab';
import { DramaDownloadModal } from './modals/DramaDownloadModal';
import { getDramaDownloadReadTask, getV2Settings, openV2Folder, startDramaDownloadPipeline, stopDramaDownloadPipeline, type DramaDownloadReadTaskState } from '../../api/v2Catalog';
import { useDataArea } from '../../hooks/useDataArea';
import { refreshArea } from '../../services/dataHub';
import {
  Building2,
  Film,
  Cpu,
  Sparkles,
  CheckCircle2,
  FolderOpen,
  X,
  Layers,
  Link2,
  ArrowRight,
} from 'lucide-react';

interface AssetsCenterViewProps {
  sceneryOpenRequest?: number;
  showToast?: (msg: string) => void;
}

export const AssetsCenterView: React.FC<AssetsCenterViewProps> = ({ showToast: externalShowToast, sceneryOpenRequest = 0 }) => {
  const [activeTab, setActiveTab] = useState<AssetsCenterTab>(sceneryOpenRequest ? 'production_resources' : 'business_data');
  useEffect(() => { if (sceneryOpenRequest) setActiveTab('production_resources'); }, [sceneryOpenRequest]);

  // State collections
  const cachedSeed = getCachedAssetsCenterSeed();
  const [accounts, setAccounts] = useState<AccountBusinessItem[]>(cachedSeed?.accounts || []);
  const [theaters, setTheaters] = useState<TheaterBusinessItem[]>(cachedSeed?.theaters || []);
  const [subTheaters, setSubTheaters] = useState<SubTheaterBusinessItem[]>(cachedSeed?.subTheaters || []);
  const [dramas, setDramas] = useState<DramaBusinessItem[]>(cachedSeed?.dramas || []);
  const [profiles, setProfiles] = useState<DramaContentProfile[]>(cachedSeed?.profiles || []);
  const [productionResources, setProductionResources] = useState<ProductionResourceItem[]>(cachedSeed?.productionResources || []);
  const [viralAssets, setViralAssets] = useState<ViralAssetItem[]>(cachedSeed?.viralAssets || []);
  const [lastRefreshAt, setLastRefreshAt] = useState<Date | null>(() => {
    try { const value = localStorage.getItem('v2-assets-center-seed-v1:updated-at'); return value ? new Date(value) : null; } catch { return null; }
  });

  // Selected drama for library tab navigation
  const [targetDramaIdForLibrary, setTargetDramaIdForLibrary] = useState<string | undefined>(undefined);
  const [dramaDownloadRoot, setDramaDownloadRoot] = useState('Z:\\04短剧原片');
  const [isDramaDownloadOpen, setIsDramaDownloadOpen] = useState(false);
  const [readTaskState, setReadTaskState] = useState<DramaDownloadReadTaskState>({ status: 'idle', phase: 'read-task' });

  // Toast notification state
  const [toastMessage, setToastMessage] = useState<string | null>(null);

  // ── 统一数据层接入（刷新大修 · 第 3a 步）────────────────────────────
  // 资料中心的数据分两种，**新鲜度要求正好相反**，所以用两个区域分开处理：
  //   ① catalog（你手填的资料）：几天才改一次 → 间隔 0，**打开读一次 + 改完立刻刷**
  //   ② resourceIndex（磁盘上的素材）：会变，但**读一次要遍历整个素材盘**
  //      → 30 秒一次（用户 2026-09-18 选定）。绝不能跟着 3 秒跑。
  const catalogArea = useDataArea<Awaited<ReturnType<typeof loadAssetsCenterSeed>>>(
    'catalog',
    () => fetchAssetsCenterSeedForDataHub(),
  );
  const resourceArea = useDataArea<ProductionResourceItem[]>(
    'resourceIndex',
    loadProductionResources,
  );

  useEffect(() => {
    const seed = catalogArea.data;
    if (!seed) return;
    setAccounts(seed.accounts);
    setTheaters(seed.theaters);
    setSubTheaters(seed.subTheaters);
    setDramas(seed.dramas);
    setProfiles(seed.profiles);
    setViralAssets(seed.viralAssets);
    setLastRefreshAt(catalogArea.updatedAt ? new Date(catalogArea.updatedAt) : null);
    if (seed.warnings.length) {
      setToastMessage(`部分资料暂未更新：${seed.warnings.join('、')}。其他资料仍可正常使用。`);
    }
    if (catalogArea.error) setToastMessage('资料数据更新失败，已保留上次数据。');
  }, [catalogArea.data, catalogArea.updatedAt, catalogArea.error]);

  useEffect(() => {
    if (!resourceArea.data) return;
    setProductionResources(resourceArea.data);
    setLastRefreshAt(resourceArea.updatedAt ? new Date(resourceArea.updatedAt) : null);
  }, [resourceArea.data, resourceArea.updatedAt]);

  useEffect(() => {
    if (!isDramaDownloadOpen) return;
    getV2Settings().then((settings) => setDramaDownloadRoot(settings.drama_download_root || 'Z:\\04短剧原片')).catch(() => undefined);
  }, [isDramaDownloadOpen]);

  useEffect(() => {
    if (!isDramaDownloadOpen) return undefined;
    let cancelled = false;
    const refresh = () => getDramaDownloadReadTask().then((value) => { if (!cancelled) setReadTaskState(value); }).catch(() => undefined);
    refresh();
    const timer = window.setInterval(refresh, 1000);
    return () => { cancelled = true; window.clearInterval(timer); };
  }, [isDramaDownloadOpen]);

  const showToast = (msg: string) => {
    if (externalShowToast) {
      externalShowToast(msg);
    } else {
      setToastMessage(msg);
      setTimeout(() => {
        setToastMessage(null);
      }, 3500);
    }
  };

  // Open Windows Folder handler
  const handleOpenFolder = (folderPath: string) => {
    openV2Folder(folderPath).then(() => showToast('已打开本地目录')).catch((error: unknown) => showToast(error instanceof Error ? error.message : '目录打开失败。'));
  };

  const downloadRefreshKey = React.useRef('');
  useEffect(() => {
    const finished = (readTaskState.status === 'succeeded' && readTaskState.phase === 'completed') || readTaskState.status === 'failed' || readTaskState.status === 'stopped';
    const key = `${readTaskState.created_at || ''}:${readTaskState.completed_task_count || 0}:${finished ? readTaskState.status : ''}`;
    if ((finished || readTaskState.completed_task_count) && key !== downloadRefreshKey.current) {
      downloadRefreshKey.current = key;
      void refreshArea('catalog');
    }
  }, [readTaskState.created_at, readTaskState.completed_task_count, readTaskState.status, readTaskState.phase]);

  const handleStartDramaDownload = () => {
    startDramaDownloadPipeline()
      .then((value) => setReadTaskState(value))
      .catch((error: unknown) => showToast(error instanceof Error ? error.message : '启动短剧原片下载失败。'));
  };

  const handleStopDramaDownload = () => {
    stopDramaDownloadPipeline()
      .then((value) => setReadTaskState(value))
      .catch((error: unknown) => showToast(error instanceof Error ? error.message : '停止短剧原片下载失败。'));
  };

  // Capacity calculation
  const resourceMetrics = calculateResourceMetrics(productionResources);

  // Navigation from drama business row to drama content library
  const handleNavigateToDramaProfile = (dramaId: string) => {
    setTargetDramaIdForLibrary(dramaId);
    setActiveTab('drama_library');
  };

  return (
    <div className="min-h-screen bg-[#F8F9FA] pb-20 text-[#1A1D2E]">
      {/* 1. TOP HEADER & NAVIGATION BAR */}
      <div className="bg-white border-b border-black/[0.06] sticky top-0 z-30 shadow-2xs">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-3.5">
          <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
            {/* Title & Badge */}
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 rounded-2xl bg-[#1A1D2E] text-[#DDFD00] flex items-center justify-center shadow-xs">
                <Layers className="w-5 h-5" />
              </div>
              <div>
                <div className="flex items-center gap-2">
                  <h1 className="text-base font-black text-[#1A1D2E] tracking-tight">资料中心</h1>{lastRefreshAt && <span className="text-[10px] font-normal text-slate-400">更新于 {lastRefreshAt.toLocaleTimeString('zh-CN', { timeZone: 'Asia/Shanghai' })}</span>}
                  <span className="px-2 py-0.5 rounded-full bg-slate-100 text-slate-700 text-[10px] font-bold">
                    资产与生产资源总库
                  </span>
                </div>
                <p className="text-xs text-[#64748B] mt-0.5">
                  统一管理公司业务基础档案、剧集原片物料、生产消耗资源与高转化爆款资产
                </p>
              </div>
            </div>

            {/* 4 Core Area Tab Buttons */}
            <div className="flex flex-wrap items-center gap-1.5 p-1 bg-slate-100/90 rounded-2xl border border-black/[0.04]">
              {/* Tab 1: 业务资料 */}
              <button
                onClick={() => setActiveTab('business_data')}
                className={`flex items-center gap-2 px-3.5 py-2 rounded-xl text-xs font-bold transition-all cursor-pointer ${
                  activeTab === 'business_data'
                    ? 'bg-[#1A1D2E] text-white shadow-xs'
                    : 'text-[#64748B] hover:text-[#1A1D2E] hover:bg-slate-200/50'
                }`}
              >
                <Building2 className={`w-3.5 h-3.5 ${activeTab === 'business_data' ? 'text-[#DDFD00]' : ''}`} />
                <span>业务资料</span>
              </button>

              <button
                onClick={() => setActiveTab('query_management')}
                className={`flex items-center gap-2 px-3.5 py-2 rounded-xl text-xs font-bold transition-all cursor-pointer ${activeTab === 'query_management' ? 'bg-[#1A1D2E] text-white shadow-xs' : 'text-[#64748B] hover:text-[#1A1D2E] hover:bg-slate-200/50'}`}
              >
                <Link2 className={`w-3.5 h-3.5 ${activeTab === 'query_management' ? 'text-[#DDFD00]' : ''}`} />
                <span>查单管理</span>
              </button>

              {/* Tab 2: 剧集资料库 */}
              <button
                onClick={() => setActiveTab('drama_library')}
                className={`flex items-center gap-2 px-3.5 py-2 rounded-xl text-xs font-bold transition-all cursor-pointer ${
                  activeTab === 'drama_library'
                    ? 'bg-[#1A1D2E] text-white shadow-xs'
                    : 'text-[#64748B] hover:text-[#1A1D2E] hover:bg-slate-200/50'
                }`}
              >
                <Film className={`w-3.5 h-3.5 ${activeTab === 'drama_library' ? 'text-[#DDFD00]' : ''}`} />
                <span>剧集资料库</span>
              </button>

              {/* Tab 3: 生产资源 (with Live Capacity Badge) */}
              <button
                onClick={() => setActiveTab('production_resources')}
                className={`flex items-center gap-2 px-3.5 py-2 rounded-xl text-xs font-bold transition-all cursor-pointer ${
                  activeTab === 'production_resources'
                    ? 'bg-[#1A1D2E] text-white shadow-xs'
                    : 'text-[#64748B] hover:text-[#1A1D2E] hover:bg-slate-200/50'
                }`}
              >
                <Cpu className={`w-3.5 h-3.5 ${activeTab === 'production_resources' ? 'text-[#DDFD00]' : ''}`} />
                <span>生产资源</span>
                <span className={`px-1.5 py-0.2 rounded-full font-mono text-[10px] font-bold ${
                  activeTab === 'production_resources'
                    ? 'bg-[#DDFD00] text-[#1A1D2E]'
                    : 'bg-slate-200 text-slate-700'
                }`}>
                  {resourceMetrics.totalResourceCount} 项
                </span>
              </button>

              {/* Tab 4: 爆款资产 */}
              <button
                onClick={() => setActiveTab('viral_assets')}
                className={`flex items-center gap-2 px-3.5 py-2 rounded-xl text-xs font-bold transition-all cursor-pointer ${
                  activeTab === 'viral_assets'
                    ? 'bg-[#1A1D2E] text-white shadow-xs'
                    : 'text-[#64748B] hover:text-[#1A1D2E] hover:bg-slate-200/50'
                }`}
              >
                <Sparkles className={`w-3.5 h-3.5 ${activeTab === 'viral_assets' ? 'text-amber-400' : ''}`} />
                <span>爆款资产</span>
              </button>
            </div>
          </div>
        </div>
      </div>

      {/* 2. MAIN WORKSPACE CONTAINER */}
      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 pt-6">
        {activeTab === 'business_data' && (
          <BusinessDataTab
            accounts={accounts}
            theaters={theaters}
            subTheaters={subTheaters}
            dramas={dramas}
            onUpdateAccounts={setAccounts}
            onUpdateTheaters={setTheaters}
            onUpdateSubTheaters={setSubTheaters}
            onUpdateDramas={setDramas}
            onNavigateToDramaProfile={handleNavigateToDramaProfile}
            onManageQueryLinks={() => setActiveTab('query_management')}
            onShowToast={showToast}
          />
        )}

        {activeTab === 'query_management' && <QueryManagementTab onShowToast={showToast} />}

        {activeTab === 'drama_library' && (
          <DramaLibraryTab
            profiles={profiles}
            dramas={dramas}
            viralAssets={viralAssets}
            selectedDramaId={targetDramaIdForLibrary}
            onSelectDrama={setTargetDramaIdForLibrary}
            onUpdateProfiles={setProfiles}
            onOpenFolder={handleOpenFolder}
            onOpenDramaDownload={() => setIsDramaDownloadOpen(true)}
            onShowToast={showToast}
          />
        )}

        {activeTab === 'production_resources' && (
          <ProductionResourcesTab
            sceneryOpenRequest={sceneryOpenRequest}
            resources={productionResources}
            metrics={resourceMetrics}
            onOpenFolder={handleOpenFolder}
            onAddResource={newRes => {
              const item: ProductionResourceItem = {
                ...newRes,
                id: `res-${Date.now().toString().slice(-4)}`,
                addedAt: new Date().toISOString().slice(0, 10),
              };
              setProductionResources([item, ...productionResources]);
              showToast(`已成功录入生产资源: ${item.name}`);
            }}
            onShowToast={showToast}
          />
        )}

        {activeTab === 'viral_assets' && (
          <ViralAssetsTab
            viralAssets={viralAssets}
            accounts={accounts}
            dramas={dramas}
            onOpenFolder={handleOpenFolder}
            onUpdateViralAssets={setViralAssets}
            onShowToast={showToast}
          />
        )}
      </main>

      <DramaDownloadModal
        isOpen={isDramaDownloadOpen}
        downloadRoot={dramaDownloadRoot}
        readTaskState={readTaskState}
        onClose={() => setIsDramaDownloadOpen(false)}
        onOpenFolder={handleOpenFolder}
        onStartPipeline={handleStartDramaDownload}
        onStopPipeline={handleStopDramaDownload}
        onShowToast={showToast}
      />

      {/* 3. FLOATING SYSTEM TOAST FEEDBACK */}
      {toastMessage && (
        <div className="fixed bottom-6 right-6 z-50 animate-in fade-in slide-in-from-bottom-3 duration-200">
          <div className="bg-[#1A1D2E] text-white px-4 py-3 rounded-2xl shadow-2xl border border-white/10 flex items-center gap-3 text-xs max-w-md">
            <CheckCircle2 className="w-4 h-4 text-[#DDFD00] shrink-0" />
            <span className="font-medium">{toastMessage}</span>
            <button
              onClick={() => setToastMessage(null)}
              className="text-slate-400 hover:text-white p-1 ml-auto cursor-pointer"
            >
              <X className="w-3.5 h-3.5" />
            </button>
          </div>
        </div>
      )}
    </div>
  );
};
