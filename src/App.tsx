import React, { useEffect, useState } from 'react';
import { 
  NavTab, 
  ScheduleTask, 
  AccountItem, 
  DramaPrediction,
  DramaItem, 
} from './types';
import { 
  INITIAL_ACCOUNTS, 
  DRAMA_LIBRARY, 
  RECENT_DRAMA_PREDICTIONS, 
  INITIAL_SCHEDULE_TASKS,
  INITIAL_TASK_CENTER_QUEUE
} from './mockData';
import { Header } from './components/Header';
import { TodayScheduleSection } from './components/TodayScheduleSection';
import { YesterdayAccountsSection } from './components/YesterdayAccountsSection';
import { RecentDramasSection } from './components/RecentDramasSection';
import { WorkbenchExplore } from './components/explore/WorkbenchExplore';
import { ProductionCenter } from './components/production/ProductionCenter';
import { DataAnalyticsView } from './components/analytics/DataAnalyticsView';
import { AssetsCenterView } from './components/assets/AssetsCenterView';
import { ParameterCenterView } from './components/parameters/ParameterCenterView';
import { SettingsView } from './components/settings/SettingsView';
import { TaskCenterModal } from './components/taskcenter/TaskCenterModal';
import { ScheduleModal } from './components/ScheduleModal';
import { EditTimePopover } from './components/EditTimePopover';
import { CheckCircle2 } from 'lucide-react';
import { createV2ProductionTask } from './api/v2Production';
import { createBusinessDrama, loadAssetsCenterSeed } from './services/assetsCenterService';
import { getV2Accounts, getV2Settings, type V2AccountRecord } from './api/v2Catalog';
import { loadV2DailyAccountRevenueSummary, type V2DailyAccountRevenueSummary } from './api/v2Revenue';
import { eventDetail } from './services/dataChangeEvents';

function yesterdayDateValue(): string {
  const value = new Date();
  value.setDate(value.getDate() - 1);
  const offset = value.getTimezoneOffset() * 60_000;
  return new Date(value.getTime() - offset).toISOString().slice(0, 10);
}

function toScheduleAccount(account: V2AccountRecord, daily?: V2DailyAccountRevenueSummary['items'][number]): AccountItem {
  return {
    id: account.id,
    name: account.nickname,
    avatarSeed: account.nickname,
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
  const [activeTab, setActiveTab] = useState<NavTab>('workbench');
  const [workbenchMode, setWorkbenchMode] = useState<'standard' | 'explore'>('explore'); // Default to Explore version
  // 刷新大修 · 第 6 步：记住"已经打开过的页签"。
  // 第一次切到某个页签才挂载它，之后**只藏起来、不拆掉** —— 这样筛选、选中的剧都还在。
  // （以前是切走就销毁、切回来重建，靠"重建"顺带刷新；现在刷新由统一数据层负责，不再需要。
  //   不能一上来就把所有页面都挂载 —— 那样开软件要等半天，所以用懒挂载。）
  const [mountedTabs, setMountedTabs] = useState<Set<NavTab>>(() => new Set<NavTab>(['workbench']));
  useEffect(() => {
    setMountedTabs((previous) => (previous.has(activeTab) ? previous : new Set(previous).add(activeTab)));
  }, [activeTab]);
  const [tasks, setTasks] = useState<ScheduleTask[]>(INITIAL_SCHEDULE_TASKS);
  const [accounts, setAccounts] = useState<AccountItem[]>([]);
  const [dramas, setDramas] = useState<DramaItem[]>([]);
  const [predictions] = useState<DramaPrediction[]>(RECENT_DRAMA_PREDICTIONS);
  const [taskQueue, setTaskQueue] = useState(INITIAL_TASK_CENTER_QUEUE);
  const [publishTimePresets, setPublishTimePresets] = useState<string[]>(['12:00', '18:30', '19:45', '21:00']);
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
  const [editingTimeTask, setEditingTimeTask] = useState<ScheduleTask | null>(null);
  const [toastMessage, setToastMessage] = useState<string | null>(null);

  useEffect(() => {
    void refreshScheduleAccounts().catch(() => showToast('安排今日的昨日收益读取失败。'));
    loadAssetsCenterSeed().then((seed) => {
      setDramas(seed.dramas.map((drama) => ({
        id: drama.id,
        name: drama.currentName,
        theaterId: drama.theaterId,
        theaterName: drama.theaterName,
        coverUrl: seed.profiles.find((profile) => profile.dramaId === drama.id)?.cover.mainCoverUrl,
        productionCount: drama.productionCount || 0,
        lastScheduledAt: drama.lastScheduledAt || '',
        activeProductionCount: drama.activeProductionCount || 0,
      })));
      setScheduleTheaters(seed.theaters.filter((theater) => theater.status === '启用').map((theater) => ({ id: theater.id, name: theater.name })));
    }).catch(() => showToast('安排今日的真实账号和剧集加载失败。'));
  }, []);

  // “安排今日”只需要当前可安排的正常账号。账号状态变化时更新这份
  // 小型名单和昨日收益，不重读资料中心的其余数据。
  useEffect(() => {
    const onDataChanged = (event: Event) => {
      const detail = eventDetail(event);
      if (detail.changeType !== 'account_changed' || !detail.accountId) return;
      void refreshScheduleAccounts().catch(() => undefined);
    };
    window.addEventListener('v2-data-changed', onDataChanged);
    return () => window.removeEventListener('v2-data-changed', onDataChanged);
  }, []);

  useEffect(() => {
    getV2Settings().then((settings) => {
      setPublishTimePresets(settings.publish_presets);
      setPublishDateOffsetDays(settings.publish_date_offset_days);
    }).catch(() => undefined);
  }, []);

  const showToast = (msg: string) => {
    setToastMessage(msg);
    setTimeout(() => {
      setToastMessage(null);
    }, 2800);
  };

  const openSchedule = () => {
    Promise.all([getV2Settings().catch(() => null), refreshScheduleAccounts().catch(() => undefined)])
      .then(([settings]) => {
        if (!settings) return;
        setPublishTimePresets(settings.publish_presets);
        setPublishDateOffsetDays(settings.publish_date_offset_days);
      })
      .finally(() => setIsScheduleModalOpen(true));
  };

  // Derived state
  const arrangedAccountIds = Array.from(new Set(tasks.map(t => t.accountId)));
  // Actions
  const handleOpenGlobalSchedule = () => {
    setModalAccountId(undefined);
    setModalDramaId(undefined);
    openSchedule();
  };

  const handleScheduleFromAccount = (account: AccountItem) => {
    setModalAccountId(account.id);
    setModalDramaId(undefined);
    openSchedule();
  };

  const handleScheduleFromDrama = (drama: DramaPrediction) => {
    setModalAccountId(undefined);
    setModalDramaId(drama.dramaId);
    openSchedule();
  };

  const handleScheduleFromDramaModal = (dramaId: string, accountId?: string) => {
    setModalDramaId(dramaId);
    setModalAccountId(accountId);
    openSchedule();
  };

  const handleAddDramaToAccount = (accountId: string, _accountName: string) => {
    setModalAccountId(accountId);
    setModalDramaId(undefined);
    openSchedule();
  };

  const handleSaveNewSchedule = async (newTasksData: Omit<ScheduleTask, 'id'>[]) => {
    try {
      await Promise.all(newTasksData.map((task) => createV2ProductionTask({
        source_id: `schedule-${task.accountId}-${task.dramaId}-${task.plannedPublishAt || task.publishTime}`,
        account_name: task.accountName,
        drama_name: task.dramaName,
        planned_publish_at: task.plannedPublishAt || task.publishTime,
      })));
    } catch (error) {
      showToast(error instanceof Error ? error.message : '生产任务创建失败，请稍后重试。');
      return;
    }
    const createdTasks: ScheduleTask[] = newTasksData.map((task, idx) => ({
      ...task,
      id: `task-new-${Date.now()}-${idx}`,
    }));

    setTasks(prev => [...prev, ...createdTasks]);
    
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
  };

  const handleDeleteTask = (taskId: string) => {
    setTasks(prev => prev.filter(t => t.id !== taskId));
    showToast('已移除该项制作安排');
  };

  const handleUpdateTime = (taskId: string, newTime: string) => {
    setTasks(prev => prev.map(t => t.id === taskId ? { ...t, publishTime: newTime } : t));
    showToast(`发布时间已更新为：${newTime}`);
  };

  return (
    <div className="min-h-screen bg-[#EEF2F6] flex flex-col selection:bg-[#DDFD00] selection:text-[#1A1D2E]">
      {/* Top Header Bar with lightweight integrated status & Workbench Mode Switcher */}
      <Header
        activeTab={activeTab}
        onTabChange={setActiveTab}
        taskQueue={taskQueue}
        onOpenSettings={() => setActiveTab('settings')}
        onQuickSchedule={handleOpenGlobalSchedule}
        workbenchMode={workbenchMode}
        onWorkbenchModeChange={setWorkbenchMode}
        onOpenTaskCenterModal={() => setIsTaskCenterModalOpen(true)}
        showToast={showToast}
      />

      {/* Main View Area */}
      <main className="flex-1 px-6 sm:px-8 py-6 max-w-[1780px] w-full mx-auto">
        {mountedTabs.has('production') && (
          <div style={{ display: activeTab === 'production' ? undefined : 'none' }}>
            <ProductionCenter
              onBackToWorkbench={() => setActiveTab('workbench')}
              showToast={showToast}
            />
          </div>
        )}

        {mountedTabs.has('analytics') && (
          <div style={{ display: activeTab === 'analytics' ? undefined : 'none' }}>
            <DataAnalyticsView
              onScheduleToday={(dramaId, accountId) => {
                if (dramaId || accountId) {
                  handleScheduleFromDramaModal(dramaId || 'drama-1', accountId);
                } else {
                  handleOpenGlobalSchedule();
                }
              }}
              showToast={showToast}
            />
          </div>
        )}

        {mountedTabs.has('assets') && (
          <div style={{ display: activeTab === 'assets' ? undefined : 'none' }}>
            <AssetsCenterView
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

        {mountedTabs.has('workbench') && (
          <div style={{ display: activeTab === 'workbench' ? undefined : 'none' }}>
            {/* 工作台内部的"探索版 / 标准版"切换仍保持互斥挂载（工作台是未完成的模块，不投入）。 */}
            {workbenchMode === 'explore' ? (
              <WorkbenchExplore
                tasks={tasks}
                accounts={accounts}
                dramas={dramas}
                onAddDramaToAccount={handleAddDramaToAccount}
                onAddNewAccountSchedule={handleOpenGlobalSchedule}
                onEditTime={(task) => setEditingTimeTask(task)}
                onDeleteTask={handleDeleteTask}
                onOpenProduction={() => setActiveTab('production')}
                onSaveNewSchedule={handleSaveNewSchedule}
                showToast={showToast}
                onScheduleFromDramaModal={handleScheduleFromDramaModal}
              />
            ) : (
              <div className="grid grid-cols-1 lg:grid-cols-12 gap-8 items-start">
                <div className="lg:col-span-7 xl:col-span-7">
                  <TodayScheduleSection
                    tasks={tasks}
                    onAddDramaToAccount={handleAddDramaToAccount}
                    onAddNewAccountSchedule={handleOpenGlobalSchedule}
                    onEditTime={(task) => setEditingTimeTask(task)}
                    onDeleteTask={handleDeleteTask}
                    onOpenProduction={() => setActiveTab('production')}
                  />
                </div>

                <div className="lg:col-span-5 xl:col-span-5 flex flex-col gap-6">
                  <YesterdayAccountsSection
                    accounts={accounts}
                    arrangedAccountIds={arrangedAccountIds}
                    onScheduleAccount={handleScheduleFromAccount}
                  />

                  <RecentDramasSection
                    predictions={predictions}
                    onScheduleDrama={handleScheduleFromDrama}
                  />
                </div>
              </div>
            )}
          </div>
        )}
      </main>

      {/* Global Task Center Modal */}
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
        publishTimePresets={publishTimePresets}
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

      {/* Popover: 修改发布时间 */}
      <EditTimePopover
        isOpen={!!editingTimeTask}
        task={editingTimeTask}
        onClose={() => setEditingTimeTask(null)}
        onUpdateTime={handleUpdateTime}
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
