import React, { useEffect, useRef, useState } from 'react';
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
import { getCachedAssetsCenterSeed, loadAssetsCenterSeed, refreshCachedAssetsItem } from '../../services/assetsCenterService';
import { BusinessDataTab } from './BusinessDataTab';
import { DramaLibraryTab } from './DramaLibraryTab';
import { ProductionResourcesTab } from './ProductionResourcesTab';
import { ViralAssetsTab } from './ViralAssetsTab';
import { openV2Folder } from '../../api/v2Catalog';
import { getV2ProductionResources } from '../../api/v2Catalog';
import { subscribeV2DataRefresh } from '../../services/dataRefreshCoordinator';
import {
  Building2,
  Film,
  Cpu,
  Sparkles,
  CheckCircle2,
  FolderOpen,
  X,
  Layers,
  ArrowRight,
} from 'lucide-react';

interface AssetsCenterViewProps {
  showToast?: (msg: string) => void;
}

export const AssetsCenterView: React.FC<AssetsCenterViewProps> = ({ showToast: externalShowToast }) => {
  const [activeTab, setActiveTab] = useState<AssetsCenterTab>('business_data');

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

  // Toast notification state
  const [toastMessage, setToastMessage] = useState<string | null>(null);
  // Newer requests own the screen. A late full-seed response must never
  // overwrite a targeted update that arrived after it was started.
  const refreshGeneration = useRef(0);

  useEffect(() => {
    let active = true;
    const applySeed = (seed: Awaited<ReturnType<typeof loadAssetsCenterSeed>>, generation: number) => {
      if (!active || generation !== refreshGeneration.current) return;
      setAccounts(seed.accounts);
      setTheaters(seed.theaters);
      setSubTheaters(seed.subTheaters);
      setDramas(seed.dramas);
      setProfiles(seed.profiles);
      setProductionResources(seed.productionResources);
      setViralAssets(seed.viralAssets);
      setLastRefreshAt(new Date());
    };
    const refresh = () => {
      const generation = ++refreshGeneration.current;
      return loadAssetsCenterSeed(true).then((seed) => applySeed(seed, generation)).catch(() => {
      if (active) setToastMessage('资料数据更新失败，已保留上次数据。');
      });
    };
    void refresh();
    const refreshForChange = async (detail?: import('../../services/dataChangeEvents').V2DataChangeDetail) => {
      if (!detail) { await refresh(); return; }
      if (detail.accountId || detail.dramaId || ['theater_changed', 'sub_theater_changed', 'profile_changed'].includes(detail.changeType || '')) {
        const generation = ++refreshGeneration.current;
        await refreshCachedAssetsItem(detail).then((changed) => {
          if (!active || generation !== refreshGeneration.current || !changed) return;
          if (changed.accounts) setAccounts(changed.accounts);
          if (changed.theaters) setTheaters(changed.theaters);
          if (changed.subTheaters) setSubTheaters(changed.subTheaters);
          if (changed.dramas) setDramas(changed.dramas);
          if (changed.profiles) setProfiles(changed.profiles);
          setLastRefreshAt(new Date());
        });
      } else if (detail.changeType === 'resource_changed') {
        await getV2ProductionResources().then((response) => {
          if (!active) return;
          setProductionResources(response.items); setLastRefreshAt(new Date());
        });
      } else { await refresh(); }
    };
    const unsubscribe = subscribeV2DataRefresh('assets', ({ detail }) => refreshForChange(detail).catch(() => undefined));
    return () => { active = false; unsubscribe(); };
  }, []);

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
                  <h1 className="text-base font-black text-[#1A1D2E] tracking-tight">资料中心</h1>{lastRefreshAt && <span className="text-[10px] font-normal text-slate-400">更新于 {lastRefreshAt.toLocaleTimeString('zh-CN')}</span>}
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
            <div className="flex items-center gap-1.5 p-1 bg-slate-100/90 rounded-2xl border border-black/[0.04]">
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
                  支持 {resourceMetrics.supportableDramas} 剧
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
            onShowToast={showToast}
          />
        )}

        {activeTab === 'drama_library' && (
          <DramaLibraryTab
            profiles={profiles}
            dramas={dramas}
            viralAssets={viralAssets}
            selectedDramaId={targetDramaIdForLibrary}
            onSelectDrama={setTargetDramaIdForLibrary}
            onUpdateProfiles={setProfiles}
            onOpenFolder={handleOpenFolder}
            onShowToast={showToast}
          />
        )}

        {activeTab === 'production_resources' && (
          <ProductionResourcesTab
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
