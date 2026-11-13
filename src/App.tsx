import { RevenueVerificationModal } from './components/RevenueVerificationModal';
import { plannedDate, formatPlannedDate, planningDayOffset, planningToday } from './utils/plannedDate';
import React, { useEffect, useState } from 'react';
import { 
  NavTab, 
  ScheduleTask, 
  AccountItem, 
  DramaItem, 
} from './types';
import { 
  INITIAL_TASK_CENTER_QUEUE
} from './mockData';
import { Header } from './components/Header';
import { CockpitView } from './components/cockpit/CockpitView';
import { ProductionCenter } from './components/production/ProductionCenter';
import { ContentProductionView } from './components/content/ContentProductionView';
import { AnalyticsDashboard } from './components/analytics/AnalyticsDashboard';
import { AssetsCenterView } from './components/assets/AssetsCenterView';
import { ParameterCenterView } from './components/parameters/ParameterCenterView';
import { SettingsView } from './components/settings/SettingsView';
import { TaskCenterModal } from './components/taskcenter/TaskCenterModal';
import { ScheduleModal } from './components/ScheduleModal';
import { CheckCircle2 } from 'lucide-react';
import { createV2ProductionTask } from './api/v2Production';
import { createBusinessDrama, fetchAssetsCenterSeedForDataHub, loadAssetsCenterSeed } from './services/assetsCenterService';
import { getV2Accounts, getV2Settings, type V2AccountRecord } from './api/v2Catalog';
import { loadV2DailyAccountRevenueSummary, type V2DailyAccountRevenueSummary } from './api/v2Revenue';
import { eventDetail } from './services/dataChangeEvents';
import { useDataArea } from './hooks/useDataArea';
import { refreshArea } from './services/dataHub';

function yesterdayDateValue(): string {
  return planningDayOffset(-1);
}

function toScheduleAccount(account: V2AccountRecord, daily?: V2DailyAccountRevenueSummary['items'][number]): AccountItem {
  return {
    id: account.id,
    name: account.nickname,
    avatarSeed: account.nickname,
    avatarUrl: account.avatar_url,
    yesterdayRevenue: Number(daily?.amount || 0),
    yesterdayRevenueState: daily?.collection_status || 'uncollected',
    monthRevenue: 0,
    manualStatus: '正常',
    platform: '微信视频号',
    theaterId: account.theater_id,
    theaterName: account.theater_name,
  };
}

export default function App() {
  const [activeTab, setActiveTab] = useState<NavTab>('dashboard');
  const [sceneryOpenRequest, setSceneryOpenRequest] = useState(0);
  const openScenery = () => {
    setSceneryOpenRequest(value => value + 1);
    setActiveTab('assets');
    window.scrollTo({ top: 0 });
  };
  // 刷新大修 · 第 6 步：记住"已经打开过的页签"。
  // 第一次切到某个页签才挂载它，之后**只藏起来、不拆掉** —— 这样筛选、选中的剧都还在。
  // （以前是切走就销毁、切回来重建，靠"重建"顺带刷新；现在刷新由统一数据层负责，不再需要。
  //   不能一上来就把所有页面都挂载 —— 那样开软件要等半天，所以用懒挂载。）
  const [mountedTabs, setMountedTabs] = useState<Set<NavTab>>(() => new Set<NavTab>(['dashboard']));
  useEffect(() => {
    setMountedTabs((previous) => (previous.has(activeTab) ? previous : new Set(previous).add(activeTab)));
  }, [activeTab]);
  const [accounts, setAccounts] = useState<AccountItem[]>([]);
  const [dramas, setDramas] = useState<DramaItem[]>([]);
  const [taskQueue, setTaskQueue] = useState(INITIAL_TASK_CENTER_QUEUE);
  const [publishDateOffsetDays, setPublishDateOffsetDays] = useState(0);
  const [scheduleTheaters, setScheduleTheaters] = useState<{ id: string; name: string }[]>([]);

  const refreshScheduleAccounts = async (): Promise<void> => {
    const [response, revenue] = await Promise.all([getV2Accounts(), loadV2DailyAccountRevenueSummary(yesterdayDateValue())]);
    const byAccountId = new Map(revenue.items.map((item) => [item.account_id, item]));
    setAccounts(response.items.filter((account) => account.status === '正常').map((account) => toScheduleAccount(account, byAccountId.get(account.id))));
  };

  // 旧的「每 1.5 秒轮询变更表」和「每 60 秒把所有页面全量重刷」已删除
  //（刷新大修 · 第 5b 步）：两者的作用已由 src/services/dataHub.ts 的统一数据层接管。
  // 写操作后的即时通知（publishV2DataChange）**保留** —— 它不轮询，开销为零。

  // Modal / Interaction states
  const [isScheduleModalOpen, setIsScheduleModalOpen] = useState(false);
  const [isTaskCenterModalOpen, setIsTaskCenterModalOpen] = useState(false);
  const [modalAccountId, setModalAccountId] = useState<string | undefined>();
  const [modalDramaId, setModalDramaId] = useState<string | undefined>();
  const [toastMessage, setToastMessage] = useState<string | null>(null);

  // 刷新大修 · 第 8 步：剧集/剧场名单原来只在挂载时读一次 —— 在资料中心改了剧名或新增剧集，
  // "安排今天"弹窗里还是旧的，必须刷新整个页面才对。现在与资料中心**共用 catalog 区域**（同一份数据），
  // 那边一改，这边自动跟上。
  const catalogArea = useDataArea<Awaited<ReturnType<typeof loadAssetsCenterSeed>>>(
    'catalog',
    () => fetchAssetsCenterSeedForDataHub(),
  );

  useEffect(() => {
    void refreshScheduleAccounts().catch(() => showToast('安排今日的昨日收益读取失败。'));
  }, []);

  useEffect(() => {
    const seed = catalogArea.data;
    if (!seed) {
      if (catalogArea.error) showToast('安排今日的真实账号和剧集加载失败。');
      return;
    }
    const profilesById = new Map(seed.profiles.map(profile => [profile.dramaId,profile]));
    setDramas(seed.dramas.map((drama) => ({
      id: drama.id,
      name: drama.currentName,
      totalEpisodes: drama.officialTotalEpisodes,
      theaterId: drama.theaterId,
      theaterName: drama.theaterName,
      coverUrl: profilesById.get(drama.id)?.cover.mainCoverUrl,
      productionCount: drama.productionCount || 0,
      lastScheduledAt: drama.lastScheduledAt || '',
      activeProductionCount: drama.activeProductionCount || 0,
    })));
    setScheduleTheaters(seed.theaters.filter((theater) => theater.status === '启用').map((theater) => ({ id: theater.id, name: theater.name })));
  }, [catalogArea.data, catalogArea.error]);

  // “安排今日”只需要当前可安排的正常账号。账号状态变化时更新这份
  // 小型名单和昨日收益，不重读资料中心的其余数据。
  useEffect(() => {
    const onDataChanged = (event: Event) => {
      const detail = eventDetail(event);
      if (detail.changeType !== 'account_changed' || !detail.accountId) return;
      void refreshScheduleAccounts().catch(() => undefined);
      void refreshArea('production');
      void refreshArea('taskCenter');
      void refreshArea('revenue');
    };
    window.addEventListener('v2-data-changed', onDataChanged);
    return () => window.removeEventListener('v2-data-changed', onDataChanged);
  }, []);

  useEffect(() => {
    getV2Settings().then((settings) => {
      setPublishDateOffsetDays(settings.publish_date_offset_days);
    }).catch(() => undefined);
  }, []);

  const showToast = (msg: string) => {
    setToastMessage(msg);
    setTimeout(() => {
      setToastMessage(null);
    }, 2800);
  };

  // 刷新大修 · 第 8 步：原来要等两个请求都结束才打开弹窗，本地服务慢时点了"安排今天"
  // 会有几秒钟毫无反应（按钮不转圈、面板也不出来）。现在**先打开**，数据到了再填。
  const openSchedule = () => {
    setIsScheduleModalOpen(true);
    void Promise.all([getV2Settings().catch(() => null), refreshScheduleAccounts().catch(() => undefined)])
      .then(([settings]) => {
        if (!settings) return;
          setPublishDateOffsetDays(settings.publish_date_offset_days);
      });
  };

  // 首页现在只保留新驾驶舱；“安排今天”仍从 V3 的全局入口打开原有弹窗。
  const handleOpenGlobalSchedule = () => {
    setModalAccountId(undefined);
    setModalDramaId(undefined);
    openSchedule();
  };

  const handleSaveNewSchedule = async (newTasksData: Omit<ScheduleTask, 'id'>[]) => {
    try {
      await Promise.all(newTasksData.map((task) => createV2ProductionTask({
        source_id: `schedule-${task.accountId}-${task.dramaId}-${plannedDate(task.plannedPublishAt) || planningToday()}`,
        account_name: task.accountName,
        drama_name: task.dramaName,
        planned_publish_at: plannedDate(task.plannedPublishAt),
        mount_source: task.mountSource,
        mount_external_id: task.mountExternalId,
      })));
    } catch (error) {
      showToast(error instanceof Error ? error.message : '生产任务创建失败，请稍后重试。');
      return false;
    }
    const createdTasks: ScheduleTask[] = newTasksData.map((task, idx) => ({
      ...task,
      plannedPublishAt: plannedDate(task.plannedPublishAt),
      publishTime: formatPlannedDate(task.plannedPublishAt),
      id: `task-new-${Date.now()}-${idx}`,
    }));

    // Also add to background task queue
    createdTasks.forEach(task => {
      setTaskQueue(prev => [
        {
          id: `tc-${Date.now()}-${task.id}`,
          title: `《${task.dramaName}》- ${task.accountName}`,
          accountName: task.accountName,
          stage: '后台生成',
          status: 'waiting',
          time: '排队等待中',
        },
        ...prev,
      ]);
    });

    showToast(`已成功创建 ${createdTasks.length} 项制作安排`);
    return true;
  };

  return (
    <div className="min-h-screen bg-[#EEF2F6] flex flex-col selection:bg-[#DDFD00] selection:text-[#1A1D2E]">
      {/* Top Header Bar with lightweight integrated status & Workbench Mode Switcher */}
      <Header
        activeTab={activeTab}
        onTabChange={setActiveTab}
        onOpenScenery={openScenery}
        taskQueue={taskQueue}
        onOpenSettings={() => setActiveTab('settings')}
        onQuickSchedule={handleOpenGlobalSchedule}
        onOpenTaskCenterModal={() => setIsTaskCenterModalOpen(true)}
        showToast={showToast}
      />

      {/* Main View Area */}
      <main className={`flex-1 px-6 sm:px-8 py-6 w-full mx-auto ${activeTab === 'production' ? 'max-w-[1904px]' : 'max-w-[1780px]'}`}>
        {mountedTabs.has('production') && (
          <div style={{ display: activeTab === 'production' ? undefined : 'none' }}>
            <ProductionCenter
              onBackToWorkbench={() => setActiveTab('dashboard')}
              onParameters={() => setActiveTab('parameters')}
              showToast={showToast}
            />
          </div>
        )}

        {mountedTabs.has('content') && (
          <div style={{ display: activeTab === 'content' ? undefined : 'none' }}>
            <ContentProductionView showToast={showToast} />
          </div>
        )}

        {mountedTabs.has('dashboard') && (
          <div style={{ display: activeTab === 'dashboard' ? undefined : 'none' }}>
            <CockpitView showToast={showToast} />
          </div>
        )}

        {mountedTabs.has('analytics') && (
          <div style={{ display: activeTab === 'analytics' ? undefined : 'none' }}>
            <AnalyticsDashboard showToast={showToast} />
          </div>
        )}

        {mountedTabs.has('assets') && (
          <div style={{ display: activeTab === 'assets' ? undefined : 'none' }}>
            <AssetsCenterView
              sceneryOpenRequest={sceneryOpenRequest}
              showToast={showToast}
            />
          </div>
        )}

        {mountedTabs.has('parameters') && (
          <div style={{ display: activeTab === 'parameters' ? undefined : 'none' }}>
            <ParameterCenterView
              showToast={showToast}
            />
          </div>
        )}

        {mountedTabs.has('settings') && (
          <div style={{ display: activeTab === 'settings' ? undefined : 'none' }}>
            <SettingsView
              showToast={showToast}
            />
          </div>
        )}

      </main>

      {/* Global Task Center Modal */}
      <RevenueVerificationModal />
      <TaskCenterModal
        isOpen={isTaskCenterModalOpen}
        onClose={() => setIsTaskCenterModalOpen(false)}
        showToast={showToast}
      />

      {/* Side Panel: 安排今天 */}
      <ScheduleModal
        isOpen={isScheduleModalOpen}
        onClose={() => setIsScheduleModalOpen(false)}
        accounts={accounts}
        dramas={dramas}
        initialAccountId={modalAccountId}
        initialDramaId={modalDramaId}
        publishDateOffsetDays={publishDateOffsetDays}
        theaters={scheduleTheaters}
        onCreateDrama={async (data) => {
          const created = await createBusinessDrama({ ...data, isUsedInBusiness: false });
          const item: DramaItem = { id: created.id, name: created.currentName, theaterId: created.theaterId, theaterName: created.theaterName };
          setDramas((items) => [item, ...items]);
          return item;
        }}
        onSaveSchedule={handleSaveNewSchedule}
      />

      {/* Floating Toast Notification */}
      {toastMessage && (
        <div className="fixed bottom-6 right-6 z-50 flex items-center gap-2 px-4 py-2.5 rounded-2xl bg-[#1A1D2E] text-white text-xs font-bold shadow-2xl border border-white/10 animate-in fade-in slide-in-from-bottom-2 duration-150">
          <div className="w-4 h-4 rounded-full bg-[#DDFD00] text-[#1A1D2E] flex items-center justify-center font-bold">
            <CheckCircle2 className="w-3 h-3" />
          </div>
          <span>{toastMessage}</span>
        </div>
      )}
    </div>
  );
}
