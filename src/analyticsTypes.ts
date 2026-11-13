// Comprehensive Data Analytics Types for Production Desktop Workspace

export type AnalyticsTopTab = 'overview' | 'revenue' | 'accounts' | 'dramas' | 'videos' | 'account_data';

export type TimeRangeFilter = 'yesterday' | '7days' | '14days' | '30days' | 'this_month' | 'custom';

export type TheaterFilter = 'all' | 'qingning' | 'jiuzhou' | 'dianzhong' | 'fanqie' | 'huasheng';

export type RevenueQualityTier = 'direct' | 'derived' | 'estimated';

// Data Coverage Indicator
export interface DataCoverageInfo {
  revenueTheatersCount: number;
  totalTheatersCount: number;
  videoDataTheaters: string[];
  coverageDescription: string;
}

// 1. REVENUE MODULE TYPES
export interface RevenueSummaryMetrics {
  isYesterday: boolean;
  
  // Multi-day fields:
  currentPeriodRevenue: number;
  dailyAverageRevenue: number;
  prevPeriodRevenue: number | null;
  changePct: number | null; // null if insufficient data
  changeInsufficientReason?: string;
  
  // Yesterday fields:
  yesterdayRevenue: number;
  recentAverageRevenue: number;
  recentAveragePeriodDays: number;
  changeVsAveragePct: number | null;
  yesterdayContextLabel?: string;
  
  // Completeness metrics:
  completenessRatio: number;
  totalAccounts: number;
  updatedAccounts: number;
  pendingAccounts: number;
  completenessText: string;
  isFullyComplete: boolean;

  // Legacy compatibility fields if referenced:
  last7DaysRevenue?: number;
  thisMonthRevenue?: number;
  prev7DaysRevenue?: number;
  last7DaysChangePct?: number;
}

export interface DailyRevenueDataPoint {
  date: string; // YYYY-MM-DD
  dayLabel: string; // e.g. 08-23
  totalRevenue: number;
  qingningRevenue: number;
  jiuzhouRevenue: number;
  dianzhongRevenue: number;
  fanqieRevenue: number;
  huashengRevenue: number;
  videoViews?: number; // Qingning only
  dramaViews?: number; // Qingning only
}

export interface TrendGhostPoint {
  date: string;
  dayLabel: string;
  revenue: number;
}

export interface DramaAttributionSummary {
  attributableRevenue: number;
  totalPeriodRevenue: number;
  attributableRatioPct: number;
  unattributableRevenue: number;
}

export interface ContributionItem {
  id: string;
  name: string;
  category?: string;
  theater?: string;
  revenue: number;
  sharePct: number;
  changePct: number | null; // null if previous period data insufficient
  changeInsufficientReason?: string;
  isAttributable: boolean; // false if data cannot be reliably attributed
  qualityTier: RevenueQualityTier;
  hasData?: boolean;
  isNew?: boolean;
}

export interface ChangeSignalItem {
  id: string;
  type: 'positive' | 'negative' | 'neutral' | 'warning';
  title: string;
  description: string;
  metric: string;
  date: string;
  targetType?: 'account' | 'drama' | 'collection' | 'theater';
  targetId?: string;
  targetName?: string;
}

// 2. ACCOUNT MODULE TYPES
export interface AccountVirtualLocation {
  province: string;
  city: string;
  district: string;
  detail: string;
  fullAddress: string;
  usedCount: number;
  lastUsedDate: string;
}

export interface AccountDramaPerformance {
  dramaId: string;
  dramaName: string;
  publishCount: number;
  totalRevenue: number;
  avgRevenuePerVideo: number;
  videoViews?: number; // undefined if not Qingning
  dramaViews?: number; // undefined if not Qingning
}

export interface AccountLocationPerformance {
  locationId: string;
  fullAddress: string;
  usedCount: number;
  totalRevenue: number;
  videoViews?: number;
  dramaViews?: number;
  lastUsedDate: string;
}

export interface AccountAnalyticsItem {
  id: string;
  name: string;
  theater: string;
  hasQingningVideoData: boolean;
  sevenDaysRevenue: number;
  sevenDaysRevenueTrend: number[]; // 7 points
  thirtyDaysRevenue: number;
  recentMainDrama: string;
  defaultLocation: AccountVirtualLocation;
  sevenDaysVideoViews?: number;
  sevenDaysDramaViews?: number;
  dailyTrend: { date: string; revenue: number; videoViews?: number }[];
  dramaPerformances: AccountDramaPerformance[];
  locationPerformances: AccountLocationPerformance[];
}

// 3. DRAMA MODULE TYPES
export interface DramaAccountDifference {
  accountId: string;
  accountName: string;
  publishCount: number;
  totalRevenue: number;
  avgRevenuePerVideo: number;
  videoViews?: number;
  dramaViews?: number;
}

export interface DramaVideoVarianceStats {
  publishedVideoCount: number;
  bestSingleVideoRevenue: number;
  avgSingleVideoRevenue: number;
  medianSingleVideoRevenue: number;
  worstSingleVideoRevenue: number;
  bestVideoName?: string;
}

export interface DramaLocationPerformance {
  locationId: string;
  fullAddress: string;
  usedCount: number;
  totalRevenue: number;
  videoViews?: number;
  dramaViews?: number;
}

export interface DramaAnalyticsItem {
  id: string;
  name: string;
  category: string;
  activeAccountsCount: number;
  sevenDaysRevenue: number;
  sevenDaysRevenueTrend: number[];
  thirtyDaysRevenue: number;
  hasQingningData: boolean;
  sevenDaysVideoViews?: number;
  sevenDaysDramaViews?: number;
  dailyTrend: { date: string; revenue: number; videoViews?: number }[];
  accountDifferences: DramaAccountDifference[];
  videoVariance: DramaVideoVarianceStats;
  locationPerformances: DramaLocationPerformance[];
}

// 4. PLATFORM VIDEO MODULE TYPES
export interface PlatformVideoItem {
  id: string; // Platform Video ID
  date: string; // YYYY-MM-DD
  accountName: string;
  accountId: string;
  dramaName: string;
  dramaId: string;
  theater: string; // e.g. 青柠剧场
  videoViews: number; // 当日视频播放量
  dramaViews: number; // 当日剧集播放量
  revenue: number; // 当日收益
  receptionStrength: number; // 承接强度 = 剧集播放 / 视频播放
  rpm: number; // 千次播放收益 = 收益 / 视频播放 * 1000
  associationStatus: 'linked' | 'unlinked';
  linkedMaterialId?: string; // e.g. "素材-04"
  linkedInternalClipName?: string;
  linkedAt?: string;
  isOutlier?: boolean;
}

// 5. COMBINATIONS MODULE TYPES
export type CombinationDimension = 'account_x_drama' | 'account_x_location' | 'drama_x_location';

export type CombinationMetric = 'total_revenue' | 'avg_revenue' | 'publish_count' | 'video_views' | 'drama_views';

export interface CombinationRecord {
  id: string;
  rowKey: string;
  rowLabel: string;
  colKey: string;
  colLabel: string;
  dimension: CombinationDimension;
  sampleCount: number;
  totalRevenue: number;
  avgRevenue: number;
  medianRevenue: number;
  bestRevenue: number;
  worstRevenue: number;
  videoViews?: number;
  dramaViews?: number;
  recentTrend: number[]; // 5-7 points
  recentPublishRecords: {
    id: string;
    date: string;
    videoName: string;
    revenue: number;
    videoViews?: number;
    locationText: string;
  }[];
}

// 6. REVENUE COLLECTION LOGS
export interface RevenueCollectionLog {
  id: string;
  theaterName: string;
  accountName: string;
  period: string;
  status: 'success' | 'no_data' | 'failed' | 'indeterminate';
  collectedAmount: number;
  qualityTier: RevenueQualityTier;
  updatedAt: string;
  note?: string;
}
