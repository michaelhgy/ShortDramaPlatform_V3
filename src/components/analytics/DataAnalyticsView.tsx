import React, { useState, useEffect } from 'react';
import { 
  AnalyticsTopTab, 
  TimeRangeFilter, 
  TheaterFilter
} from '../../analyticsTypes';
import { getCachedRevenuePageData, loadRevenueOverviewData, loadRevenuePageData, requestRevenueCollection, type RevenueCollectionProgress } from '../../services/revenueAnalyticsService';
import type { V2RevenuePayload } from '../../adapters/revenue';
import type { RevenueCollectionLog } from '../../analyticsTypes';
import type { CalculatedAccountItem } from '../../utils/accountEngine';

import { AnalyticsHeader } from './AnalyticsHeader';
import { RevenueModule } from './RevenueModule';
import { AccountModule } from './AccountModule';
import { VideoModule } from './VideoModule';
import { DramaModule } from './DramaModule';
import { CombinationModule } from './CombinationModule';
import { RevenueCollectionDrawer } from './RevenueCollectionDrawer';
import { changeAffects, eventDetail } from '../../services/dataChangeEvents';

interface DataAnalyticsViewProps {
  onScheduleToday: (dramaId?: string, accountId?: string) => void;
  showToast: (msg: string) => void;
}

const localDateOffset = (days: number) => {
  const value = new Date();
  value.setHours(12, 0, 0, 0);
  value.setDate(value.getDate() + days);
  return `${value.getFullYear()}-${String(value.getMonth() + 1).padStart(2, '0')}-${String(value.getDate()).padStart(2, '0')}`;
};

export const DataAnalyticsView: React.FC<DataAnalyticsViewProps> = ({
  onScheduleToday,
  showToast,
}) => {
  const [activeTab, setActiveTab] = useState<AnalyticsTopTab>('revenue');
  const [timeRange, setTimeRange] = useState<TimeRangeFilter>('7days');
  const [customStartDate, setCustomStartDate] = useState<string>(() => localDateOffset(-7));
  const [customEndDate, setCustomEndDate] = useState<string>(() => localDateOffset(-1));
  const [selectedTheater, setSelectedTheater] = useState<TheaterFilter>('qingning');
  const [isCollectionDrawerOpen, setIsCollectionDrawerOpen] = useState<boolean>(false);
  const [revenueData, setRevenueData] = useState<V2RevenuePayload | null>(null);
  const [collectionLogs, setCollectionLogs] = useState<RevenueCollectionLog[]>([]);
  const [revenueAccounts, setRevenueAccounts] = useState<CalculatedAccountItem[]>([]);
  const [videoAnalysis, setVideoAnalysis] = useState<import('../../utils/videoEngine').VideoAnalysisResult | null>(null);
  const [videoDetailsTruncated, setVideoDetailsTruncated] = useState(false);
  const [revenueDramas, setRevenueDramas] = useState<import('../../utils/dramaEngine').CalculatedDramaItem[]>([]);
  const [revenueError, setRevenueError] = useState('');
  const [isRevenueRefreshing, setIsRevenueRefreshing] = useState(false);

  const applyRevenuePageData = (data: Awaited<ReturnType<typeof loadRevenuePageData>>) => {
    setRevenueData(data.analytics); setCollectionLogs(data.collectionLogs); setRevenueAccounts(data.accounts);
    setVideoAnalysis(data.videoAnalysis); setVideoDetailsTruncated(data.videoDetailsTruncated); setRevenueDramas(data.dramas);
  };

  // Cross-module targeted navigation state
  const [targetAccountId, setTargetAccountId] = useState<string | undefined>(undefined);

  useEffect(() => {
    let active = true;
    const input = { timeRange, theaterFilter: selectedTheater, customStart: customStartDate, customEnd: customEndDate };
    const needsDetailedData = activeTab === 'accounts' || activeTab === 'videos' || activeTab === 'dramas' || activeTab === 'combinations';
    const refresh = (force = false) => {
      if (active) setIsRevenueRefreshing(true);
      return loadRevenuePageData(input, force)
        .then((data) => { if (active) { applyRevenuePageData(data); setRevenueError(''); } })
        .catch((error: unknown) => { if (active) setRevenueError(error instanceof Error ? error.message : '收益数据加载失败'); })
        .finally(() => { if (active) setIsRevenueRefreshing(false); });
    };
    const refreshVisibleData = () => {
      if (needsDetailedData) void refresh(true);
      else {
        setIsRevenueRefreshing(true);
        void loadRevenueOverviewData(input, true).then((data) => { if (active) applyRevenuePageData(data); }).finally(() => { if (active) setIsRevenueRefreshing(false); });
      }
    };
    const cached = getCachedRevenuePageData(input);
    if (cached) applyRevenuePageData(cached);
    if (needsDetailedData) {
      // Do not first apply the lightweight overview here. Its deliberately
      // empty video/drama fields used to overwrite a loaded detailed tab,
      // making "剧集" flash empty and "组合" look like it had no data.
      void refresh(true);
    } else {
      if (active) setIsRevenueRefreshing(true);
      void loadRevenueOverviewData(input, true)
        .then((data) => { if (active) applyRevenuePageData(data); })
        .catch(() => { if (active) setRevenueError('收益数据加载失败'); })
        .finally(() => { if (active) setIsRevenueRefreshing(false); });
    }
    const onDataChanged = (event: Event) => { if (changeAffects(eventDetail(event), 'analytics')) refreshVisibleData(); };
    const onVisibilityChange = () => { if (!document.hidden) refreshVisibleData(); };
    // Collection changes arrive through the common event feed; this remains a
    // slow reconciliation check rather than a repeated full-data poll.
    const timer = window.setInterval(() => { if (!document.hidden) refreshVisibleData(); }, 60000);
    window.addEventListener('v2-data-changed', onDataChanged);
    document.addEventListener('visibilitychange', onVisibilityChange);
    return () => { active = false; window.clearInterval(timer); document.removeEventListener('visibilitychange', onVisibilityChange); window.removeEventListener('v2-data-changed', onDataChanged); };
  }, [activeTab, timeRange, selectedTheater, customStartDate, customEndDate]);

  const handleTriggerCollect = async (scope: string, mode: 'immediate' | 'backfill', startDate: string, endDate: string, targets?: { theaters?: string[]; accountIds?: string[] }, onProgress?: (progress: RevenueCollectionProgress) => void) => {
    await requestRevenueCollection(scope, mode, startDate, endDate, targets, onProgress);
    const data = await loadRevenuePageData({ timeRange, theaterFilter: selectedTheater, customStart: customStartDate, customEnd: customEndDate }, true);
    applyRevenuePageData(data);
    showToast(`青柠收益采集已完成：${startDate} ~ ${endDate}`);
  };

  const handleCustomDateChange = (start: string, end: string) => {
    setCustomStartDate(start);
    setCustomEndDate(end);
    setTimeRange('custom');
    showToast(`已应用自定义时间范围：${start} ~ ${end}`);
  };

  const handleNavigateToTab = (tab: AnalyticsTopTab, entityId?: string) => {
    setActiveTab(tab);
    if (tab === 'accounts' && entityId) {
      setTargetAccountId(entityId);
      showToast(`已定位至账号：${entityId}`);
    }
  };

  return (
    <div className="max-w-7xl mx-auto space-y-4 pb-12">
      {/* 1. Universal Clean Analytics Header */}
      <AnalyticsHeader
        activeTab={activeTab}
        onTabChange={setActiveTab}
        timeRange={timeRange}
        onTimeRangeChange={setTimeRange}
        customStartDate={customStartDate}
        customEndDate={customEndDate}
        onCustomDateChange={handleCustomDateChange}
        selectedTheater={selectedTheater}
        onTheaterChange={setSelectedTheater}
        onOpenCollectionDrawer={() => setIsCollectionDrawerOpen(true)}
        activeAccountsCount={revenueData ? revenueAccounts.length : 0}
        activeDramasCount={revenueData ? revenueDramas.length : 0}
        collectionStatusText={isRevenueRefreshing ? '正在后台更新收益数据…' : (revenueData?.dataCompleteness.statusText || (revenueError ? '收益数据加载失败' : '正在读取 V2 收益数据…'))}
        isFullyComplete={revenueData?.dataCompleteness.isFullyComplete || false}
      />

      {/* 2. Main Content Module based on Top Tab */}
      {activeTab === 'revenue' && revenueData && (
        <RevenueModule
          summary={revenueData.summary}
          trendPoints={revenueData.trendPoints}
          ghostPoints={revenueData.ghostPoints}
          hasGhostData={revenueData.hasGhostData}
          ghostUnavailableReason={revenueData.ghostUnavailableReason}
          theaterContributions={revenueData.theaterContributions}
          accountContributions={revenueData.accountContributions}
          dramaContributions={revenueData.dramaContributions}
          dramaAttributionSummary={revenueData.dramaAttributionSummary}
          changeSignals={revenueData.changeSignals}
          timeRange={timeRange}
          selectedTheater={selectedTheater}
          onNavigateToTab={handleNavigateToTab}
          onOpenCollectionDrawer={() => setIsCollectionDrawerOpen(true)}
        />
      )}
      {activeTab === 'revenue' && !revenueData && (
        <div className="rounded-2xl border border-black/[0.06] bg-white px-5 py-10 text-sm text-slate-500">{revenueError || '正在读取 V2 收益数据…'}</div>
      )}

      {activeTab === 'accounts' && (
        <AccountModule
          timeRange={timeRange}
          selectedTheater={selectedTheater}
          customStartDate={customStartDate}
          customEndDate={customEndDate}
          initialAccountId={targetAccountId}
          onNavigateToTab={handleNavigateToTab}
          onScheduleToday={onScheduleToday}
          accounts={revenueAccounts}
        />
      )}

      {activeTab === 'videos' && !videoAnalysis && (
        <div className="rounded-2xl border border-black/[0.06] bg-white px-5 py-10 text-sm text-slate-500">正在读取当前日期范围的视频明细…</div>
      )}
      {activeTab === 'videos' && videoAnalysis && (
        <>
          {videoDetailsTruncated && (
            <div className="rounded-2xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-800">当前日期范围的青柠视频明细超过安全读取上限，已只显示前 12,000 条。请缩小日期或按账号筛选后查看。</div>
          )}
          <VideoModule
            timeRange={timeRange}
            selectedTheater={selectedTheater}
            customStartDate={customStartDate}
            customEndDate={customEndDate}
            onNavigateToTab={handleNavigateToTab}
            analysisOverride={videoAnalysis}
          />
        </>
      )}

      {activeTab === 'dramas' && (
        <DramaModule
          timeRange={timeRange}
          selectedTheater={selectedTheater}
          customStartDate={customStartDate}
          customEndDate={customEndDate}
          onNavigateToTab={handleNavigateToTab}
          onScheduleToday={onScheduleToday}
          dramas={revenueDramas}
        />
      )}

      {activeTab === 'combinations' && !videoAnalysis && (
        <div className="rounded-2xl border border-black/[0.06] bg-white px-5 py-10 text-sm text-slate-500">正在读取当前日期范围的组合数据…</div>
      )}
      {activeTab === 'combinations' && videoAnalysis && (
        <CombinationModule timeRange={timeRange} selectedTheater={selectedTheater} customStartDate={customStartDate} customEndDate={customEndDate} onNavigateToTab={handleNavigateToTab} onScheduleToday={onScheduleToday} videoAnalysis={videoAnalysis || undefined} />
      )}


      {/* 3. Global Revenue Collection Drawer */}
      <RevenueCollectionDrawer
        isOpen={isCollectionDrawerOpen}
        onClose={() => setIsCollectionDrawerOpen(false)}
        logs={collectionLogs}
        onTriggerCollect={handleTriggerCollect}
      />
    </div>
  );
};
