import { DramaItem, DramaProductionStatus, ManualAccountStatus, ScheduleTask } from './types';

export type InsightType = 'opportunity' | 'warning' | 'trend' | 'action_ready';

export interface DailyInsight {
  id: string;
  type: InsightType;
  title: string;
  badge: string;
  badgeColor: 'lime' | 'purple' | 'amber' | 'blue' | 'rose';
  desc: string;
  highlightValue?: string;
  actionText?: string;
  actionType?: 'schedule_drama' | 'fill_unassigned' | 'adjust_time' | 'batch_render';
  actionData?: {
    dramaId?: string;
    accountId?: string;
    targetTime?: string;
  };
}

export interface ExploreDrama extends DramaItem {
  heatScore: number; // e.g. 98.4
  heatTrend: 'up' | 'fire' | 'stable';
  marketRank: number;
  hookType: string; // e.g. "开局逆袭打脸 / 身份反转"
  hookScore: number; // e.g. 95
  completionRateEstimate: string; // e.g. "93.8% 预估完播"
  estimatedRevenueRange: string; // e.g. "¥650 - ¥980"
  targetAudience: string; // e.g. "30-55岁 · 下沉男性爽文"
  bestFitAccountId?: string;
  bestFitAccountName?: string;
  assetStatus: 'ready' | 'optimizing' | 'new';
  isHeroOpportunity?: boolean;
  recommendedTime: string;
  reasons: string[];
}

export interface ExploreAccount {
  avatarUrl?: string;
  id: string;
  name: string;
  platform: string;
  manualStatus: ManualAccountStatus;
  healthTag: '爆发主攻' | '流量爬坡' | '未排期预警' | '防限流观察' | '稳定长尾';
  yesterdayRevenue: number;
  revenueChangePercent: number; // e.g. +34.2
  revenueTrend: number[]; // 7-day sparkline values
  monthRevenue: number;
  fanCount: string;
  recommendedDramaId: string;
  recommendedDramaName: string;
  matchScore: number; // e.g. 96
  todayTaskCount: number;
  riskNote?: string;
}

export interface ProductionFunnelMetrics {
  totalScheduled: number;
  renderingCount: number;
  readyForPushCount: number;
  scheduledTimeWindowCount: {
    noon: number; // 12:00-13:30
    eveningPrime: number; // 18:30-21:00
    lateNight: number; // 21:30-23:30
  };
}
