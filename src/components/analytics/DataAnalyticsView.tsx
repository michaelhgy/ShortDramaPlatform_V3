import React, { useState, useMemo } from 'react';
import { 
  AnalyticsTopTab, 
  TimeRangeFilter, 
  TheaterFilter, 
  PlatformVideoItem 
} from '../../analyticsTypes';
import {
  MOCK_ACCOUNTS_ANALYTICS,
  MOCK_DRAMAS_ANALYTICS,
  MOCK_PLATFORM_VIDEOS,
  MOCK_COLLECTION_LOGS,
} from '../../analyticsMockData';
import { calculateRevenueAnalytics } from '../../utils/revenueEngine';
import { calculateAccountsAnalytics } from '../../utils/accountEngine';
import { calculateDramasAnalytics } from '../../utils/dramaEngine';

import { AnalyticsHeader } from './AnalyticsHeader';
import { RevenueModule } from './RevenueModule';
import { AccountModule } from './AccountModule';
import { DramaModule } from './DramaModule';
import { VideoModule } from './VideoModule';
import { CombinationModule } from './CombinationModule';
import { RevenueCollectionDrawer } from './RevenueCollectionDrawer';

interface DataAnalyticsViewProps {
  onScheduleToday: (dramaId?: string, accountId?: string) => void;
  showToast: (msg: string) => void;
}

export const DataAnalyticsView: React.FC<DataAnalyticsViewProps> = ({
  onScheduleToday,
  showToast,
}) => {
  const [activeTab, setActiveTab] = useState<AnalyticsTopTab>('revenue');
  const [timeRange, setTimeRange] = useState<TimeRangeFilter>('7days');
  const [customStartDate, setCustomStartDate] = useState<string>('2026-08-03');
  const [customEndDate, setCustomEndDate] = useState<string>('2026-08-17');
  const [selectedTheater, setSelectedTheater] = useState<TheaterFilter>('all');
  const [isCollectionDrawerOpen, setIsCollectionDrawerOpen] = useState<boolean>(false);

  // Cross-module targeted navigation state
  const [targetAccountId, setTargetAccountId] = useState<string | undefined>(undefined);
  const [targetDramaId, setTargetDramaId] = useState<string | undefined>(undefined);
  const [targetVideoId, setTargetVideoId] = useState<string | undefined>(undefined);
  const [autoOpenVideoDrawerId, setAutoOpenVideoDrawerId] = useState<string | undefined>(undefined);

  // Dynamic Revenue Engine recalculation when timeRange, custom dates or selectedTheater changes
  const revenueCalculated = useMemo(() => {
    return calculateRevenueAnalytics(timeRange, selectedTheater, customStartDate, customEndDate);
  }, [timeRange, selectedTheater, customStartDate, customEndDate]);

  // Counts for header badges
  const calculatedAccounts = useMemo(() => {
    return calculateAccountsAnalytics(timeRange, selectedTheater, customStartDate, customEndDate);
  }, [timeRange, selectedTheater, customStartDate, customEndDate]);

  const calculatedDramas = useMemo(() => {
    return calculateDramasAnalytics(timeRange, selectedTheater, customStartDate, customEndDate);
  }, [timeRange, selectedTheater, customStartDate, customEndDate]);

  // Video Link update handler
  const handleLinkVideo = (videoId: string, materialId: string, clipName: string) => {
    showToast(`已成功为平台视频 ${videoId} 关联内部素材 ${materialId}`);
  };

  const handleTriggerCollect = (scope: string, mode: string, startDate: string, endDate: string) => {
    showToast(`收益采集任务已完成：${scope} · ${startDate} ~ ${endDate}`);
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
    } else if (tab === 'dramas' && entityId) {
      setTargetDramaId(entityId);
      showToast(`已定位至剧集：${entityId}`);
    } else if (tab === 'videos' && entityId) {
      setTargetVideoId(entityId);
      setAutoOpenVideoDrawerId(entityId);
      showToast(`已定位至视频：${entityId}`);
    }
  };

  const handleSelectVideoAndOpenDrawer = (videoId: string) => {
    setActiveTab('videos');
    setTargetVideoId(videoId);
    setAutoOpenVideoDrawerId(videoId);
    showToast(`已打开平台视频：${videoId}`);
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
        activeAccountsCount={calculatedAccounts.accounts.length}
        activeDramasCount={calculatedDramas.length}
        collectionStatusText={revenueCalculated.dataCompleteness.statusText}
        isFullyComplete={revenueCalculated.dataCompleteness.isFullyComplete}
      />

      {/* 2. Main Content Module based on Top Tab */}
      {activeTab === 'revenue' && (
        <RevenueModule
          summary={revenueCalculated.summary}
          trendPoints={revenueCalculated.trendPoints}
          ghostPoints={revenueCalculated.ghostPoints}
          hasGhostData={revenueCalculated.hasGhostData}
          ghostUnavailableReason={revenueCalculated.ghostUnavailableReason}
          theaterContributions={revenueCalculated.theaterContributions}
          accountContributions={revenueCalculated.accountContributions}
          dramaContributions={revenueCalculated.dramaContributions}
          dramaAttributionSummary={revenueCalculated.dramaAttributionSummary}
          changeSignals={revenueCalculated.changeSignals}
          timeRange={timeRange}
          selectedTheater={selectedTheater}
          onNavigateToTab={handleNavigateToTab}
          onOpenCollectionDrawer={() => setIsCollectionDrawerOpen(true)}
        />
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
        />
      )}

      {activeTab === 'dramas' && (
        <DramaModule
          timeRange={timeRange}
          selectedTheater={selectedTheater}
          customStartDate={customStartDate}
          customEndDate={customEndDate}
          initialDramaId={targetDramaId}
          onNavigateToTab={handleNavigateToTab}
          onSelectVideoAndOpenDrawer={handleSelectVideoAndOpenDrawer}
          onScheduleToday={onScheduleToday}
        />
      )}

      {activeTab === 'videos' && (
        <VideoModule
          timeRange={timeRange}
          selectedTheater={selectedTheater}
          customStartDate={customStartDate}
          customEndDate={customEndDate}
          initialVideoId={targetVideoId}
          autoOpenDrawerForVideoId={autoOpenVideoDrawerId}
          onNavigateToTab={handleNavigateToTab}
          onLinkVideo={handleLinkVideo}
        />
      )}

      {activeTab === 'combinations' && (
        <CombinationModule
          timeRange={timeRange}
          selectedTheater={selectedTheater}
          customStartDate={customStartDate}
          customEndDate={customEndDate}
          onNavigateToTab={handleNavigateToTab}
          onScheduleToday={onScheduleToday}
        />
      )}

      {/* 3. Global Revenue Collection Drawer */}
      <RevenueCollectionDrawer
        isOpen={isCollectionDrawerOpen}
        onClose={() => setIsCollectionDrawerOpen(false)}
        logs={MOCK_COLLECTION_LOGS}
        onTriggerCollect={handleTriggerCollect}
      />
    </div>
  );
};
