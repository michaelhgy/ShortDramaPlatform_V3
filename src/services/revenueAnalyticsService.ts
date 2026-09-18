import { resolveV1RevenueRange, toQingningDramaAnalytics, toQingningDramaContributions, toQingningVideoAnalysis, toRevenueAccountAnalytics, toRevenueAnalytics, type V2RevenuePayload } from '../adapters/revenue';
import type { CalculatedAccountItem } from '../utils/accountEngine';
import type { VideoAnalysisResult } from '../utils/videoEngine';
import type { CalculatedDramaItem } from '../utils/dramaEngine';
import type { RevenueCollectionLog, TheaterFilter, TimeRangeFilter } from '../analyticsTypes';
import { collectV2QingningRevenue, loadV2DailyAccountRevenueSummary, loadV2RevenueCollectionLogs, loadV2RevenueCollectionRun, loadV2RevenueSourceData, loadV2RevenueVideoDetails, type V2RevenueCollectionLog, type V2RevenueCollectionRun } from '../api/v2Revenue';

export interface RevenuePageData {
  source: 'v2';
  analytics: V2RevenuePayload;
  collectionLogs: RevenueCollectionLog[];
  accounts: CalculatedAccountItem[];
  videoAnalysis: VideoAnalysisResult;
  videoDetailsTruncated: boolean;
  dramas: CalculatedDramaItem[];
}

const revenuePageCache = new Map<string, RevenuePageData>();
// ⚠️ 必须**按筛选条件分开**，不能只留一个"当前请求"。
// 旧写法是单个变量：A 时间段的请求还在飞时切到 B 时间段，B 会**直接复用 A 的结果** ——
// 于是"筛选项写着 30 天、眼睛看到的却是 7 天的数字"（用户报的毛病）。
const revenuePageRequests = new Map<string, Promise<RevenuePageData>>();
const revenueOverviewRequests = new Map<string, Promise<RevenuePageData>>();
const REVENUE_CACHE_KEY = 'v2-revenue-page-cache-v1';

function revenueCacheKey(input: { timeRange: TimeRangeFilter; theaterFilter: TheaterFilter; customStart?: string; customEnd?: string }): string {
  return JSON.stringify(input);
}

function persistentCacheKey(input: { timeRange: TimeRangeFilter; theaterFilter: TheaterFilter; customStart?: string; customEnd?: string }): string {
  return `${REVENUE_CACHE_KEY}:${revenueCacheKey(input)}`;
}

export function getCachedRevenuePageData(input: { timeRange: TimeRangeFilter; theaterFilter: TheaterFilter; customStart?: string; customEnd?: string }): RevenuePageData | null {
  const key = revenueCacheKey(input);
  const memory = revenuePageCache.get(key);
  if (memory) return memory;
  try {
    const raw = localStorage.getItem(persistentCacheKey(input));
    if (!raw) return null;
    const parsed = JSON.parse(raw) as RevenuePageData;
    if (!parsed || parsed.source !== 'v2' || !parsed.analytics) return null;
    revenuePageCache.set(key, parsed);
    return parsed;
  } catch { return null; }
}

function persistRevenuePageData(input: { timeRange: TimeRangeFilter; theaterFilter: TheaterFilter; customStart?: string; customEnd?: string }, data: RevenuePageData): void {
  try {
    // Video rows are deliberately omitted from persistent storage. They are
    // large and are refreshed from the backend when the page is opened.
    const lightweight: RevenuePageData = {
      ...data,
      videoAnalysis: { ...data.videoAnalysis, videos: [] },
    };
    localStorage.setItem(persistentCacheKey(input), JSON.stringify(lightweight));
  } catch { /* cache is optional and must never block the real request */ }
}

export function loadRevenueOverviewData(input: { timeRange: TimeRangeFilter; theaterFilter: TheaterFilter; customStart?: string; customEnd?: string }, force = false): Promise<RevenuePageData> {
  const key = revenueCacheKey(input);
  const cached = getCachedRevenuePageData(input);
  if (cached && !force) return Promise.resolve(cached);
  const overviewInFlight = revenueOverviewRequests.get(key);
  if (overviewInFlight) return overviewInFlight;
  const yesterday = resolveV1RevenueRange('yesterday').currentEnd;
  const overviewRequest = Promise.all([loadV2RevenueSourceData(), loadV2RevenueCollectionLogs(), loadV2DailyAccountRevenueSummary(yesterday)]).then(([source, logs, collectionSummary]) => {
    const analytics = toRevenueAnalytics(source.rows, source.accounts, source.theaters, input.timeRange, input.theaterFilter, input.customStart, input.customEnd, collectionSummary);
    return {
      source: 'v2' as const,
      analytics,
      collectionLogs: logs.items.map(toLog),
      accounts: toRevenueAccountAnalytics(source.rows, source.accounts, source.theaters, input.timeRange, input.theaterFilter, input.customStart, input.customEnd),
      videoAnalysis: { hasVideoLevelData: false, unsupportedReason: '视频明细正在后台读取', totalPlatformVideosCount: 0, totalDailyRecordsCount: 0, videos: [], p75Views: 0, p75Revenue: 0, isLowSampleCount: true, maxViews: 10000, maxRevenue: 100 },
      videoDetailsTruncated: false,
      dramas: [],
    };
  }).then((data) => {
    revenuePageCache.set(key, data);
    return data;
  }).finally(() => { revenueOverviewRequests.delete(key); });
  revenueOverviewRequests.set(key, overviewRequest);
  return overviewRequest;
}

export async function loadRevenuePageData(input: { timeRange: TimeRangeFilter; theaterFilter: TheaterFilter; customStart?: string; customEnd?: string }, force = false): Promise<RevenuePageData> {
  const key = revenueCacheKey(input);
  const cached = getCachedRevenuePageData(input);
  if (cached && !force) return cached;
  const pageInFlight = revenuePageRequests.get(key);
  if (pageInFlight) return pageInFlight;
  const range = resolveV1RevenueRange(input.timeRange, input.customStart, input.customEnd);
  const yesterday = resolveV1RevenueRange('yesterday').currentEnd;
  const pageRequest = Promise.all([loadV2RevenueSourceData(), loadV2RevenueCollectionLogs(), loadV2RevenueVideoDetails(range.currentStart, range.currentEnd), loadV2DailyAccountRevenueSummary(yesterday)]).then(([source, logs, videoDetails, collectionSummary]) => {
    const videoAnalysis = toQingningVideoAnalysis(videoDetails.items, input.theaterFilter);
    const directDrama = toQingningDramaContributions(videoAnalysis);
    const baseAnalytics = toRevenueAnalytics(source.rows, source.accounts, source.theaters, input.timeRange, input.theaterFilter, input.customStart, input.customEnd, collectionSummary);
    return {
      source: 'v2' as const,
      // The overview still uses account-day income for its headline.  The
      // drama tab receives only the separately verified Qingning video feed.
      analytics: {
        ...baseAnalytics,
        dramaContributions: directDrama.items,
        dramaAttributionSummary: {
          attributableRevenue: directDrama.attributableRevenue,
          totalPeriodRevenue: directDrama.totalVideoRevenue,
          attributableRatioPct: directDrama.totalVideoRevenue
            ? Math.round((directDrama.attributableRevenue / directDrama.totalVideoRevenue) * 10000) / 100
            : 0,
          unattributableRevenue: Math.round((directDrama.totalVideoRevenue - directDrama.attributableRevenue) * 100) / 100,
        },
      },
      collectionLogs: logs.items.map(toLog),
      accounts: toRevenueAccountAnalytics(source.rows, source.accounts, source.theaters, input.timeRange, input.theaterFilter, input.customStart, input.customEnd, videoDetails.items),
      videoAnalysis,
      videoDetailsTruncated: videoDetails.truncated,
      dramas: toQingningDramaAnalytics(videoAnalysis),
    };
  });
  revenuePageRequests.set(key, pageRequest);
  try {
    const data = await pageRequest;
    revenuePageCache.set(key, data);
    persistRevenuePageData(input, data);
    return data;
  } finally { revenuePageRequests.delete(key); }
}

/**
 * 「收益数据变了没有」的轻量信号：最新一条采集日志的 id。
 *
 * 页面拿它当"该重新拉数据了"的提示 —— **替代旧的"采集完成广播"**。
 * 这正是统一数据层里的 `revenue` 区域（间隔 0：不自动刷，只按需）。
 */
export async function loadRevenueSignal(): Promise<string> {
  const logs = await loadV2RevenueCollectionLogs();
  return logs.items[0]?.id ?? '';
}

export type RevenueCollectionProgress = Pick<V2RevenueCollectionRun, 'status' | 'total_units' | 'completed_units' | 'success_units' | 'no_data_units' | 'failed_units' | 'current_theater' | 'current_account' | 'error_message'>;

export async function requestRevenueCollection(scopeName: string, mode: 'immediate' | 'backfill', startDate: string, endDate: string, targets?: { theaters?: string[]; accountIds?: string[] }, onProgress?: (progress: RevenueCollectionProgress) => void): Promise<void> {
  if (!['all', 'theater', 'account', 'qingning'].includes(scopeName)) throw new Error('请选择已接入收益采集的剧场范围');
  const started = await collectV2QingningRevenue(startDate, endDate, targets?.theaters, targets?.accountIds);
  while (true) {
    const progress = await loadV2RevenueCollectionRun(started.run_id);
    onProgress?.(progress);
    if (progress.status === 'completed') return;
    if (progress.status === 'failed') throw new Error(progress.error_message || '收益采集任务失败');
    await new Promise((resolve) => window.setTimeout(resolve, 700));
  }
}

function toLog(item: V2RevenueCollectionLog): RevenueCollectionLog {
  return {
    id: item.id, theaterName: item.theater_name, accountName: item.account_name,
    period: item.revenue_date, status: item.collection_status,
    collectedAmount: item.amount == null ? undefined : Number(item.amount), qualityTier: 'direct',
    updatedAt: String(item.collected_at || new Date().toISOString()).replace('T', ' '), note: item.error_message || (item.collection_status === 'no_data' ? '来源正常返回：该日没有收益记录' : '已读取并校验收益数据'),
  };
}
