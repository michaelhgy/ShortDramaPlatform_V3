import type {
  ChangeSignalItem, ContributionItem, DailyRevenueDataPoint, DramaAttributionSummary,
  RevenueCollectionLog, RevenueQualityTier, RevenueSummaryMetrics, TheaterFilter, TimeRangeFilter, TrendGhostPoint,
} from '../analyticsTypes';
import type { V1CatalogAccount, V1CatalogTheater, V1DailyRevenue, V1RevenueCollectionResponse } from '../types/revenue';
import type { CalculatedAccountItem } from '../utils/accountEngine';
import type { AggregatedPlatformVideo, DailyVideoRecord, VideoAnalysisResult } from '../utils/videoEngine';
import type { CalculatedDramaItem } from '../utils/dramaEngine';
import type { CalculatedCombinationCell, CombinationMatrixResult } from '../utils/combinationEngine';
import type { V2DailyAccountRevenueSummary, V2RevenueVideoDetail } from '../api/v2Revenue';

export type V2RevenuePayload = {
  summary: RevenueSummaryMetrics;
  trendPoints: DailyRevenueDataPoint[];
  ghostPoints: TrendGhostPoint[];
  hasGhostData: boolean;
  ghostUnavailableReason?: string;
  theaterContributions: ContributionItem[];
  accountContributions: ContributionItem[];
  dramaContributions: ContributionItem[];
  dramaAttributionSummary: DramaAttributionSummary;
  changeSignals: ChangeSignalItem[];
  dataCompleteness: { totalAccounts: number; updatedAccounts: number; pendingAccounts: number; completenessRatio: number; isFullyComplete: boolean; statusText: string; };
  isEmpty?: boolean;
  availableTheaters?: { key: Exclude<TheaterFilter, 'all'>; label: string }[];
};

type CanonicalTheater = Exclude<TheaterFilter, 'all'> | 'other';
const QUALITY_RANK: Record<RevenueQualityTier, number> = { estimated: 1, derived: 2, direct: 3 };

function iso(date: Date): string {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, '0');
  const day = String(date.getDate()).padStart(2, '0');
  return `${year}-${month}-${day}`;
}
function addDays(value: string, offset: number): string { const date = new Date(`${value}T12:00:00`); date.setDate(date.getDate() + offset); return iso(date); }
function enumerate(start: string, end: string): string[] { const dates: string[] = []; for (let item = start; item <= end; item = addDays(item, 1)) dates.push(item); return dates; }
function canonicalTheater(name: string): CanonicalTheater {
  if (name.includes('青柠')) return 'qingning';
  if (name.includes('九州')) return 'jiuzhou';
  if (name.includes('点众')) return 'dianzhong';
  if (name.includes('番茄')) return 'fanqie';
  if (name.includes('花生')) return 'huasheng';
  return 'other';
}
function maxQuality(current: RevenueQualityTier, next: RevenueQualityTier): RevenueQualityTier { return QUALITY_RANK[next] > QUALITY_RANK[current] ? next : current; }
function round(value: number): number { return Math.round(value * 100) / 100; }

function percentile(values: number[], ratio = 0.75): number {
  if (!values.length) return 0;
  const sorted = [...values].sort((left, right) => left - right);
  const point = (sorted.length - 1) * ratio;
  const lower = Math.floor(point); const upper = Math.ceil(point);
  return round(sorted[lower] + ((sorted[upper] ?? sorted[lower]) - sorted[lower]) * (point - lower));
}

/**
 * Convert the persisted Qingning daily facts into the existing video-analysis
 * view model.  It deliberately does not claim that a platform video has been
 * linked to an internal finished clip: that mapping is a separate workflow.
 */
export function toQingningVideoAnalysis(details: V2RevenueVideoDetail[], selectedTheater: TheaterFilter): VideoAnalysisResult {
  if (selectedTheater !== 'all' && selectedTheater !== 'qingning') {
    return { hasVideoLevelData: false, unsupportedReason: '当前剧场未提供平台视频级数据', totalPlatformVideosCount: 0, totalDailyRecordsCount: 0, videos: [], p75Views: 0, p75Revenue: 0, isLowSampleCount: true, maxViews: 10000, maxRevenue: 100 };
  }
  const grouped = new Map<string, V2RevenueVideoDetail[]>();
  details.forEach((detail) => {
    const key = `${detail.account_id}:${detail.source_video_id}`;
    const rows = grouped.get(key) || [];
    rows.push(detail); grouped.set(key, rows);
  });
  const videos: AggregatedPlatformVideo[] = [...grouped.values()].map<AggregatedPlatformVideo>((rows) => {
    const first = rows[0];
    const records: DailyVideoRecord[] = [...rows]
      .sort((left, right) => left.revenue_date.localeCompare(right.revenue_date))
      .map((row) => ({ date: row.revenue_date, dayLabel: row.revenue_date.slice(5), videoViews: Number(row.video_views) || 0, dramaViews: Number(row.drama_views) || 0, revenue: Number(row.gross_revenue) || 0 }));
    const videoViews = records.reduce((sum, row) => sum + row.videoViews, 0);
    const dramaViews = records.reduce((sum, row) => sum + row.dramaViews, 0);
    const revenue = round(records.reduce((sum, row) => sum + row.revenue, 0));
    const firstObservedDate = first.first_observed_date || records[0]?.date || first.revenue_date;
    return {
      id: first.source_video_id, theaterKey: 'qingning', theaterName: first.theater_name,
      accountId: first.account_id, accountName: first.account_name,
      dramaId: first.matched_drama_id || `source:${first.source_drama_name}`,
      dramaName: first.matched_drama_name || first.source_drama_name || '待匹配剧集',
      firstObservedDate, firstObservedShort: firstObservedDate.slice(5), candidateBatch: '平台采集明细',
      // Drama-name matching is not a material link. Only a saved manual link
      // from the separate confirmation workflow can set this to true.
      isLinked: Boolean(first.linked_video_task_id), linkedClipName: first.linked_material_name || first.linked_material_id || undefined,
      sourceMaterialId: first.linked_material_id || undefined, sourceMaterialName: first.linked_material_name || undefined,
      candidateClips: [], periodVideoViews: videoViews,
      periodDramaViews: dramaViews, periodRevenue: revenue,
      receptionStrength: videoViews ? round(dramaViews / videoViews) : 0,
      rpm: videoViews ? round((revenue / videoViews) * 1000) : 0,
      periodDailyRecords: records, quadrant: 'long_tail', linkedTaskId: first.linked_task_id || first.inferred_task_id || undefined,
      linkedActualReleaseTime: first.linked_actual_release_time || first.inferred_actual_release_time || undefined,
      linkedReleaseAddress: [first.linked_release_province || first.inferred_release_province, first.linked_release_city || first.inferred_release_city, first.linked_release_district || first.inferred_release_district, first.linked_release_detail_address || first.inferred_release_detail_address].filter(Boolean).join('') || undefined,
    };
  }).filter((video) => video.periodVideoViews > 0 || video.periodRevenue !== 0);
  const p75Views = percentile(videos.map((video) => video.periodVideoViews));
  const p75Revenue = percentile(videos.map((video) => video.periodRevenue));
  videos.forEach((video) => {
    video.quadrant = video.periodVideoViews >= p75Views && video.periodRevenue >= p75Revenue ? 'breakout'
      : video.periodVideoViews >= p75Views ? 'hook'
        : video.periodRevenue >= p75Revenue ? 'high_ticket' : 'long_tail';
  });
  return {
    hasVideoLevelData: true, totalPlatformVideosCount: videos.length,
    totalDailyRecordsCount: details.length, videos, p75Views, p75Revenue,
    isLowSampleCount: videos.length < 20,
    maxViews: Math.max(10000, ...videos.map((video) => video.periodVideoViews)),
    maxRevenue: Math.max(100, ...videos.map((video) => video.periodRevenue)),
  };
}

/** Real Qingning drama aggregation for the existing drama-analysis interface. */
export function toQingningDramaAnalytics(analysis: VideoAnalysisResult): CalculatedDramaItem[] {
  const groups = new Map<string, AggregatedPlatformVideo[]>();
  analysis.videos.forEach((video) => { const list = groups.get(video.dramaId) || []; list.push(video); groups.set(video.dramaId, list); });
  return [...groups.entries()].map(([id, videos]) => {
    const revenue = round(videos.reduce((sum, video) => sum + video.periodRevenue, 0));
    const videoViews = videos.reduce((sum, video) => sum + video.periodVideoViews, 0);
    const dramaViews = videos.reduce((sum, video) => sum + video.periodDramaViews, 0);
    const accounts = new Map<string, AggregatedPlatformVideo[]>();
    videos.forEach((video) => { const list = accounts.get(video.accountId) || []; list.push(video); accounts.set(video.accountId, list); });
    const sorted = [...videos].sort((left, right) => right.periodRevenue - left.periodRevenue);
    const best = sorted[0]; const values = sorted.map((video) => video.periodRevenue);
    const locations = new Map<string, AggregatedPlatformVideo[]>();
    videos.forEach((video) => { if (video.linkedReleaseAddress) { const list = locations.get(video.linkedReleaseAddress) || []; list.push(video); locations.set(video.linkedReleaseAddress, list); } });
    const median = values.length ? values.sort((left, right) => left - right)[Math.floor(values.length / 2)] : 0;
    return {
      id, name: videos[0].dramaName, theaterKey: 'qingning' as const, theaterName: videos[0].theaterName,
      hasQingningVideoData: true, isAttributable: !id.startsWith('source:'),
      historicalTotalAccounts: accounts.size, historicalTotalRevenue: revenue,
      periodRevenue: revenue, periodAccountsCount: accounts.size, periodVideoViews: videoViews, periodDramaViews: dramaViews,
      videoVariance: { publishedVideoCount: videos.length, bestSingleVideoRevenue: best?.periodRevenue || 0, avgSingleVideoRevenue: videos.length ? round(revenue / videos.length) : 0, medianSingleVideoRevenue: median, zeroRevenueCount: videos.filter((video) => video.periodRevenue === 0).length, bestVideoDisplay: { isLinked: Boolean(best?.isLinked), displayName: best?.id || '暂无', videoId: best?.id || '', firstObservedDate: best?.firstObservedDate || '', accountName: best?.accountName || '' }, hasVideoLevelData: true },
      accountDifferences: [...accounts.entries()].map(([, list]) => ({ accountId: list[0].accountId, accountName: list[0].accountName, publishCount: list.length, totalRevenue: round(list.reduce((sum, video) => sum + video.periodRevenue, 0)), avgRevenuePerVideo: round(list.reduce((sum, video) => sum + video.periodRevenue, 0) / list.length), videoViews: list.reduce((sum, video) => sum + video.periodVideoViews, 0), dramaViews: list.reduce((sum, video) => sum + video.periodDramaViews, 0) })).sort((left, right) => right.totalRevenue - left.totalRevenue),
      locationPerformances: [...locations.entries()].map(([fullAddress, list]) => ({ locationId: fullAddress, fullAddress, usedCount: list.length, totalRevenue: round(list.reduce((sum, video) => sum + video.periodRevenue, 0)), videoViews: list.reduce((sum, video) => sum + video.periodVideoViews, 0), dramaViews: list.reduce((sum, video) => sum + video.periodDramaViews, 0), lastUsedDate: list.map((video) => video.firstObservedDate).sort().at(-1) || '' })),
    };
  }).sort((left, right) => right.periodRevenue - left.periodRevenue);
}

/**
 * The Qingning detail feed includes the platform-reported drama name.  This
 * is drama-level attribution only; it must not be presented as a confirmed
 * material/finished-video link, which remains a separate manual action.
 */
export function toQingningDramaContributions(analysis: VideoAnalysisResult): {
  items: ContributionItem[];
  attributableRevenue: number;
  totalVideoRevenue: number;
} {
  const totalVideoRevenue = round(analysis.videos.reduce((sum, video) => sum + video.periodRevenue, 0));
  const groups = new Map<string, AggregatedPlatformVideo[]>();
  analysis.videos.forEach((video) => {
    if (video.dramaId.startsWith('source:')) return;
    const rows = groups.get(video.dramaId) || [];
    rows.push(video);
    groups.set(video.dramaId, rows);
  });
  const attributableRevenue = round([...groups.values()].reduce(
    (sum, rows) => sum + rows.reduce((rowSum, video) => rowSum + video.periodRevenue, 0), 0,
  ));
  const items = [...groups.entries()].map(([id, videos]) => {
    const revenue = round(videos.reduce((sum, video) => sum + video.periodRevenue, 0));
    return {
      id,
      name: videos[0].dramaName,
      category: '短剧',
      theater: videos[0].theaterName,
      revenue,
      sharePct: attributableRevenue ? round((revenue / attributableRevenue) * 100) : 0,
      changePct: null,
      changeInsufficientReason: '平台视频级明细当前只汇总所选周期，未计算上一周期逐剧变化。',
      isAttributable: true,
      qualityTier: 'direct' as const,
      hasData: true,
    } satisfies ContributionItem;
  }).sort((left, right) => right.revenue - left.revenue);
  return { items, attributableRevenue, totalVideoRevenue };
}

export function toQingningCombinationMatrix(analysis: VideoAnalysisResult, dimension: import('../analyticsTypes').CombinationDimension, metric: import('../analyticsTypes').CombinationMetric, timeRange: TimeRangeFilter, selectedTheater: TheaterFilter): CombinationMatrixResult {
  const rowMap = new Map<string, string>(); const colMap = new Map<string, string>(); const groups = new Map<string, AggregatedPlatformVideo[]>();
  const usableVideos = dimension === 'account_x_drama' ? analysis.videos : analysis.videos.filter((video) => Boolean(video.linkedReleaseAddress));
  const keysFor = (video: AggregatedPlatformVideo) => dimension === 'account_x_drama'
    ? { rowKey: video.accountId, rowLabel: video.accountName, colKey: video.dramaId, colLabel: video.dramaName }
    : dimension === 'account_x_location'
      ? { rowKey: video.accountId, rowLabel: video.accountName, colKey: video.linkedReleaseAddress || '', colLabel: video.linkedReleaseAddress || '' }
      : { rowKey: video.dramaId, rowLabel: video.dramaName, colKey: video.linkedReleaseAddress || '', colLabel: video.linkedReleaseAddress || '' };
  // Keep the same key separator as the existing matrix renderer and legacy
  // calculator.  A previous two-colon key made every real cell look absent.
  usableVideos.forEach((video) => { const keys = keysFor(video); rowMap.set(keys.rowKey, keys.rowLabel); colMap.set(keys.colKey, keys.colLabel); const key = `${keys.rowKey}:::${keys.colKey}`; const list = groups.get(key) || []; list.push(video); groups.set(key, list); });
  const cells = new Map<string, CalculatedCombinationCell>(); const values: number[] = [];
  groups.forEach((videos, key) => { const first = videos[0]; const keys = keysFor(first); const revenues = videos.map((video) => video.periodRevenue); const totalRevenue = round(revenues.reduce((sum, value) => sum + value, 0)); const sorted = [...revenues].sort((a, b) => a - b); const record = (video: AggregatedPlatformVideo) => ({ id: video.id, date: video.firstObservedDate, videoName: video.id, accountId: video.accountId, accountName: video.accountName, dramaId: video.dramaId, dramaName: video.dramaName, theaterName: video.theaterName, theaterKey: 'qingning' as const, locationId: video.linkedTaskId || '', locationText: video.linkedReleaseAddress || '未人工确认关联', revenue: video.periodRevenue, videoViews: video.periodVideoViews, dramaViews: video.periodDramaViews, isAttributable: !video.dramaId.startsWith('source:') }); const cell: CalculatedCombinationCell = { id: key, dimension, rowKey: keys.rowKey, rowLabel: keys.rowLabel, colKey: keys.colKey, colLabel: keys.colLabel, theaterName: first.theaterName, isInapplicable: false, hasRecords: true, isAttributable: !first.dramaId.startsWith('source:'), sampleCount: videos.length, attributableCount: videos.length, zeroRevenueCount: videos.filter((video) => video.periodRevenue === 0).length, totalRevenue, avgRevenue: round(totalRevenue / videos.length), medianRevenue: sorted[Math.floor(sorted.length / 2)] || 0, bestRevenue: Math.max(...revenues), worstRevenue: Math.min(...revenues), videoViews: videos.reduce((sum, video) => sum + video.periodVideoViews, 0), dramaViews: videos.reduce((sum, video) => sum + video.periodDramaViews, 0), publishRecords: videos.map(record) }; cells.set(key, cell); values.push(metric === 'total_revenue' ? cell.totalRevenue : metric === 'avg_revenue' ? cell.avgRevenue : metric === 'publish_count' ? cell.sampleCount : metric === 'video_views' ? cell.videoViews || 0 : cell.dramaViews || 0); });
  const sortedValues = [...values].sort((a, b) => a - b); const at = (ratio: number) => sortedValues.length ? sortedValues[Math.floor((sortedValues.length - 1) * ratio)] : 0;
  return { dimension, metric, timeRange, selectedTheater, rowHeaders: [...rowMap].map(([key, label]) => ({ key, label })), colHeaders: [...colMap].map(([key, label]) => ({ key, label })), cellMap: cells, percentiles: { p25: at(.25), p50: at(.5), p75: at(.75), p90: at(.9), maxVal: sortedValues.at(-1) || 0, count: values.length } };
}

export function resolveV1RevenueRange(timeRange: TimeRangeFilter, customStart?: string, customEnd?: string) {
  const today = iso(new Date());
  const yesterday = addDays(today, -1);
  if (timeRange === 'yesterday') return { currentStart: yesterday, currentEnd: yesterday, previousStart: addDays(yesterday, -1), previousEnd: addDays(yesterday, -1), trendDates: enumerate(addDays(yesterday, -6), yesterday) };
  if (timeRange === '7days') return { currentStart: addDays(yesterday, -6), currentEnd: yesterday, previousStart: addDays(yesterday, -13), previousEnd: addDays(yesterday, -7), trendDates: enumerate(addDays(yesterday, -6), yesterday) };
  if (timeRange === '14days') return { currentStart: addDays(yesterday, -13), currentEnd: yesterday, previousStart: addDays(yesterday, -27), previousEnd: addDays(yesterday, -14), trendDates: enumerate(addDays(yesterday, -13), yesterday) };
  if (timeRange === '30days') return { currentStart: addDays(yesterday, -29), currentEnd: yesterday, previousStart: addDays(yesterday, -59), previousEnd: addDays(yesterday, -30), trendDates: enumerate(addDays(yesterday, -29), yesterday) };
  if (timeRange === 'this_month') {
    const currentStart = `${yesterday.slice(0, 8)}01`;
    const length = enumerate(currentStart, yesterday).length;
    return { currentStart, currentEnd: yesterday, previousStart: addDays(currentStart, -length), previousEnd: addDays(currentStart, -1), trendDates: enumerate(currentStart, yesterday) };
  }
  const currentStart = customStart || addDays(yesterday, -6);
  const currentEnd = customEnd && customEnd < today ? customEnd : yesterday;
  const length = Math.max(1, enumerate(currentStart, currentEnd).length);
  return { currentStart, currentEnd, previousStart: addDays(currentStart, -length), previousEnd: addDays(currentStart, -1), trendDates: enumerate(currentStart, currentEnd) };
}

export function toRevenueAnalytics(
  rows: V1DailyRevenue[], accounts: V1CatalogAccount[], theaters: V1CatalogTheater[],
  timeRange: TimeRangeFilter, theaterFilter: TheaterFilter, customStart?: string, customEnd?: string,
  dailyCollectionSummary?: V2DailyAccountRevenueSummary,
): V2RevenuePayload {
  const range = resolveV1RevenueRange(timeRange, customStart, customEnd);
  const currentDates = enumerate(range.currentStart, range.currentEnd);
  const previousDates = enumerate(range.previousStart, range.previousEnd);
  const matchesScope = (row: V1DailyRevenue) => theaterFilter === 'all' || canonicalTheater(row.theater_name) === theaterFilter;
  const current = rows.filter((row) => currentDates.includes(row.revenue_date) && matchesScope(row));
  const previous = rows.filter((row) => previousDates.includes(row.revenue_date) && matchesScope(row));
  const amount = (row: V1DailyRevenue) => Number.parseFloat(row.amount);
  const total = (items: V1DailyRevenue[]) => items.reduce((sum, row) => sum + (Number.isFinite(amount(row)) ? amount(row) : 0), 0);
  const currentTotal = total(current);
  const previousTotal = total(previous);
  const changePct = previousTotal > 0 ? round(((currentTotal - previousTotal) / previousTotal) * 100) : null;
  const recentDates = enumerate(addDays(range.currentEnd, -6), range.currentEnd);
  const recentTotal = total(rows.filter((row) => recentDates.includes(row.revenue_date) && matchesScope(row)));
  const recentAverage = recentTotal / recentDates.length;
  const latestRows = current.filter((row) => row.revenue_date === range.currentEnd);
  const activeTheaterIds = new Set(theaters.filter((theater) => theater.status !== 'disabled' && theater.status !== '停用').map((theater) => String(theater.id)));
  const eligibleAccounts = accounts.filter((account) => account.status !== '停用' && account.status !== 'disabled' && account.theater_id !== null && activeTheaterIds.has(String(account.theater_id)) && (theaterFilter === 'all' || canonicalTheater(theaters.find((theater) => String(theater.id) === String(account.theater_id))?.name || '') === theaterFilter));
  // The collection badge is a yesterday-read completion indicator, not a
  // count of non-zero revenue rows.  A normal "no data" response is complete;
  // failures and absent reads remain pending.  Both analytics and the global
  // header consume this same backend summary.
  const completedStatuses = new Set(['success', 'no_data']);
  const updatedAccounts = dailyCollectionSummary
    ? dailyCollectionSummary.items.filter((item) => completedStatuses.has(item.collection_status)).length
    : new Set(latestRows.map((row) => row.account_id)).size;
  const totalAccounts = dailyCollectionSummary ? dailyCollectionSummary.items.length : eligibleAccounts.length;
  const pendingAccounts = Math.max(0, totalAccounts - updatedAccounts);
  const isFullyComplete = totalAccounts > 0 && pendingAccounts === 0;

  const summary: RevenueSummaryMetrics = {
    isYesterday: timeRange === 'yesterday', currentPeriodRevenue: round(currentTotal), dailyAverageRevenue: round(currentTotal / Math.max(1, currentDates.length)),
    prevPeriodRevenue: previous.length ? round(previousTotal) : null, changePct,
    changeInsufficientReason: previous.length ? undefined : '上一周期没有可用日收益记录，暂不计算变化。',
    yesterdayRevenue: round(currentTotal), recentAverageRevenue: round(recentAverage), recentAveragePeriodDays: recentDates.length,
    changeVsAveragePct: recentAverage > 0 ? round(((currentTotal - recentAverage) / recentAverage) * 100) : null,
    yesterdayContextLabel: undefined, completenessRatio: totalAccounts ? updatedAccounts / totalAccounts : 0,
    totalAccounts, updatedAccounts, pendingAccounts,
    completenessText: `${updatedAccounts}/${totalAccounts} 账号已完成收益采集${pendingAccounts ? ` · ${pendingAccounts} 未采集` : ''}`,
    isFullyComplete, last7DaysRevenue: round(recentTotal), thisMonthRevenue: round(total(rows.filter((row) => row.revenue_date.startsWith(range.currentEnd.slice(0, 8)) && matchesScope(row)))),
    prev7DaysRevenue: previous.length ? round(previousTotal) : undefined, last7DaysChangePct: changePct ?? undefined,
  };

  const trendPoints = range.trendDates.map((date) => {
    const day = rows.filter((row) => row.revenue_date === date && matchesScope(row));
    const byKey = (key: CanonicalTheater) => total(day.filter((row) => canonicalTheater(row.theater_name) === key));
    return { date, dayLabel: date.slice(5), totalRevenue: round(total(day)), qingningRevenue: round(byKey('qingning')), jiuzhouRevenue: round(byKey('jiuzhou')), dianzhongRevenue: round(byKey('dianzhong')), fanqieRevenue: round(byKey('fanqie')), huashengRevenue: round(byKey('huasheng')), hasRecordedData: day.length > 0 };
  });
  const ghostPoints = previousDates.map((date) => ({ date, dayLabel: date.slice(5), revenue: round(total(previous.filter((row) => row.revenue_date === date))) }));

  const contribution = (items: V1DailyRevenue[], group: (row: V1DailyRevenue) => { id: string; name: string; theater?: string }) => {
    const values = new Map<string, ContributionItem>();
    items.forEach((row) => {
      const key = group(row); const value = Number.isFinite(amount(row)) ? amount(row) : 0;
      const existing = values.get(key.id);
      if (existing) { existing.revenue += value; existing.qualityTier = maxQuality(existing.qualityTier, row.quality); }
      else values.set(key.id, { ...key, revenue: value, sharePct: 0, changePct: null, isAttributable: true, qualityTier: row.quality, hasData: true });
    });
    return values;
  };
  const theaterMap = contribution(current, (row) => ({ id: `theater-${row.theater_id}`, name: row.theater_name }));
  const accountMap = contribution(current, (row) => ({ id: String(row.account_id), name: row.account_nickname, theater: row.theater_name }));
  const applyComparison = (map: Map<string, ContributionItem>, prior: V1DailyRevenue[], key: (row: V1DailyRevenue) => string) => {
    const priorTotal = new Map<string, number>(); prior.forEach((row) => priorTotal.set(key(row), (priorTotal.get(key(row)) || 0) + (Number.isFinite(amount(row)) ? amount(row) : 0)));
    map.forEach((item, id) => { const before = priorTotal.get(id) || 0; item.sharePct = currentTotal > 0 ? round((item.revenue / currentTotal) * 100) : 0; item.changePct = before > 0 ? round(((item.revenue - before) / before) * 100) : null; item.isNew = before === 0 && item.revenue > 0 && previous.length > 0; item.changeInsufficientReason = previous.length ? undefined : '上一周期没有可用日收益记录'; item.revenue = round(item.revenue); });
  };
  applyComparison(theaterMap, previous, (row) => `theater-${row.theater_id}`);
  applyComparison(accountMap, previous, (row) => String(row.account_id));
  // 总收益仍包含当前范围内的全部历史记录；排行榜只是不把 0 收益
  // 项目堆给用户看。账号当前是否停用不参与这里的历史收益判断。
  const theaterContributions = [...theaterMap.values()]
    .filter((item) => item.revenue !== 0)
    .sort((left, right) => right.revenue - left.revenue);
  const accountContributions = [...accountMap.values()]
    .filter((item) => item.revenue !== 0)
    .sort((left, right) => right.revenue - left.revenue);
  const dramaAttributionSummary: DramaAttributionSummary = { attributableRevenue: 0, totalPeriodRevenue: round(currentTotal), attributableRatioPct: 0, unattributableRevenue: round(currentTotal) };
  const changeSignals: ChangeSignalItem[] = pendingAccounts ? [{ id: `missing-${range.currentEnd}`, type: 'warning', title: `${pendingAccounts} 个账号尚无日收益记录`, description: '这表示当前日期缺少规范化日收益记录，不应按零收益解释。', metric: '待核对', date: range.currentEnd, targetType: 'collection' }] : [];
  return {
    summary, trendPoints, ghostPoints, hasGhostData: previous.length > 0,
    ghostUnavailableReason: previous.length ? undefined : '上一周期没有可用日收益记录',
    theaterContributions, accountContributions, dramaContributions: [], dramaAttributionSummary, changeSignals,
    dataCompleteness: { totalAccounts, updatedAccounts, pendingAccounts, completenessRatio: summary.completenessRatio, isFullyComplete, statusText: summary.completenessText },
    isEmpty: current.length === 0,
    availableTheaters: theaters.flatMap((theater) => {
      const key = canonicalTheater(theater.name);
      return key === 'other' || theater.status === 'disabled' ? [] : [{ key, label: theater.name }];
    }),
  };
}

/** V2 phase 1: account revenue is direct account-day data; no drama/video attribution is invented. */
export function toRevenueAccountAnalytics(
  rows: V1DailyRevenue[], accounts: V1CatalogAccount[], theaters: V1CatalogTheater[],
  timeRange: TimeRangeFilter, theaterFilter: TheaterFilter, customStart?: string, customEnd?: string,
  videoDetails: V2RevenueVideoDetail[] = [],
): CalculatedAccountItem[] {
  const range = resolveV1RevenueRange(timeRange, customStart, customEnd);
  const days = enumerate(range.currentStart, range.currentEnd);
  const recentDays = enumerate(addDays(range.currentEnd, -6), range.currentEnd);
  const theaterById = new Map(theaters.map((item) => [String(item.id), item]));
  // 这里是收益展示名单，不是采集名单：已经停用的账号只要在当前
  // 时间范围内有历史收益，就必须正常参与统计和显示。
  const displayAccounts = accounts.filter((account) => {
    const theater = theaterById.get(String(account.theater_id));
    return Boolean(theater) && (theaterFilter === 'all' || canonicalTheater(theater?.name || '') === theaterFilter);
  });
  return displayAccounts.map((account) => {
    const accountRows = rows.filter((row) => String(row.account_id) === String(account.id));
    const amountFor = (date: string) => accountRows.filter((row) => row.revenue_date === date).reduce((sum, row) => sum + (Number.parseFloat(row.amount) || 0), 0);
    const periodRevenue = round(days.reduce((sum, item) => sum + amountFor(item), 0));
    const yesterdayRevenue = round(amountFor(range.currentEnd));
    const theater = theaterById.get(String(account.theater_id));
    const accountDetails = videoDetails.filter((detail) => String(detail.account_id) === String(account.id));
    const viewsFor = (date: string) => accountDetails.filter((detail) => detail.revenue_date === date).reduce((sum, detail) => sum + (Number(detail.video_views) || 0), 0);
    const periodVideoViews = accountDetails.reduce((sum, detail) => sum + (Number(detail.video_views) || 0), 0);
    const periodDramaViews = accountDetails.reduce((sum, detail) => sum + (Number(detail.drama_views) || 0), 0);
    const dramaMap = new Map<string, { dramaId: string; dramaName: string; videos: Set<string>; revenue: number; videoViews: number; dramaViews: number }>();
    accountDetails.forEach((detail) => {
      const dramaId = detail.matched_drama_id || `source:${detail.source_drama_name}`;
      const item = dramaMap.get(dramaId) || { dramaId, dramaName: detail.matched_drama_name || detail.source_drama_name || '待匹配剧集', videos: new Set<string>(), revenue: 0, videoViews: 0, dramaViews: 0 };
      item.videos.add(detail.source_video_id); item.revenue += Number(detail.gross_revenue) || 0;
      item.videoViews += Number(detail.video_views) || 0; item.dramaViews += Number(detail.drama_views) || 0;
      dramaMap.set(dramaId, item);
    });
    const dramaPerformancesInPeriod = [...dramaMap.values()]
      .map((item) => ({ dramaId: item.dramaId, dramaName: item.dramaName, publishCount: item.videos.size, totalRevenue: round(item.revenue), avgRevenuePerVideo: item.videos.size ? round(item.revenue / item.videos.size) : 0, videoViews: item.videoViews, dramaViews: item.dramaViews, isAttributable: Boolean(!item.dramaId.startsWith('source:')) }))
      .sort((left, right) => (right.totalRevenue || 0) - (left.totalRevenue || 0));
    const recentMainDrama = dramaPerformancesInPeriod[0]?.dramaName || '本周期暂无视频明细';
    const locationMap = new Map<string, { videos: Set<string>; revenue: number; videoViews: number; dramaViews: number; lastUsedDate: string }>();
    accountDetails.forEach((detail) => {
      const address = [detail.linked_release_province || detail.inferred_release_province, detail.linked_release_city || detail.inferred_release_city, detail.linked_release_district || detail.inferred_release_district, detail.linked_release_detail_address || detail.inferred_release_detail_address].filter(Boolean).join('');
      if (!(detail.linked_task_id || detail.inferred_task_id) || !address) return;
      const item = locationMap.get(address) || { videos: new Set<string>(), revenue: 0, videoViews: 0, dramaViews: 0, lastUsedDate: '' };
      item.videos.add(detail.source_video_id); item.revenue += Number(detail.gross_revenue) || 0;
      item.videoViews += Number(detail.video_views) || 0; item.dramaViews += Number(detail.drama_views) || 0;
      item.lastUsedDate = item.lastUsedDate > detail.revenue_date ? item.lastUsedDate : detail.revenue_date; locationMap.set(address, item);
    });
    const locationPerformances = [...locationMap.entries()].map(([fullAddress, item]) => ({ locationId: fullAddress, fullAddress, usedCount: item.videos.size, totalRevenue: round(item.revenue), videoViews: item.videoViews, dramaViews: item.dramaViews, lastUsedDate: item.lastUsedDate })).sort((left, right) => right.totalRevenue - left.totalRevenue);
    const dailyTrendPoints = days.map((item) => ({ date: item, dayLabel: item.slice(5), revenue: round(amountFor(item)), isYesterday: item === range.currentEnd }));
    const recentTotal = recentDays.reduce((sum, item) => sum + amountFor(item), 0);
    return {
      id: String(account.id), name: account.nickname, theater: theater?.name || '青柠剧场', theaterKey: 'qingning', hasQingningVideoData: true,
      periodRevenue, dailyAverageRevenue: round(periodRevenue / Math.max(1, days.length)), recent7DayAvgRevenue: round(recentTotal / recentDays.length),
      yesterdayRevenue, changeVsRecentAvgPct: null, sevenDaysRevenue: round(recentTotal), sevenDaysRevenueTrend: recentDays.map(amountFor),
      thirtyDaysRevenue: round(accountRows.filter((row) => row.revenue_date >= addDays(range.currentEnd, -29) && row.revenue_date <= range.currentEnd).reduce((sum, row) => sum + (Number.parseFloat(row.amount) || 0), 0)),
      recentMainDrama, periodVideoViews, periodDramaViews, yesterdayVideoViews: viewsFor(range.currentEnd),
      defaultLocation: { province: '', city: '', district: '', detail: '', fullAddress: '尚未登记发布地址', usedCount: 0, lastUsedDate: '' },
      dailyTrend: dailyTrendPoints.map((item) => ({ ...item, videoViews: viewsFor(item.date) })),
      dailyTrendPoints: dailyTrendPoints.map((item) => ({ ...item, videoViews: viewsFor(item.date) })),
      dramaPerformances: dramaPerformancesInPeriod.map((item) => ({ dramaId: item.dramaId, dramaName: item.dramaName, publishCount: item.publishCount, totalRevenue: item.totalRevenue || 0, avgRevenuePerVideo: item.avgRevenuePerVideo || 0, videoViews: item.videoViews, dramaViews: item.dramaViews })),
      dramaPerformancesInPeriod, locationPerformances, historicalLocations: locationPerformances,
    } as CalculatedAccountItem;
  }).filter((account) => account.periodRevenue !== 0);
}

export function toCollectionLogs(response: V1RevenueCollectionResponse): RevenueCollectionLog[] {
  return response.items.map((item) => {
    const amounts = (item.attempts || []).map((attempt) => Number.parseFloat(attempt.amount || '')).filter(Number.isFinite);
    const attempts = item.attempts || [];
    const period = attempts.length ? `${attempts[0].date} ~ ${attempts[attempts.length - 1].date}` : '本次请求';
    const note = item.message || attempts.find((attempt) => attempt.message)?.message || `请求 ${response.request_id}`;
    const status = item.status === 'unsupported' || item.status === 'skipped' ? 'indeterminate' : item.status;
    return { id: `v1-${response.request_id}-${item.account_id}`, theaterName: item.theater, accountName: String(item.account_id), period, status, collectedAmount: amounts.length ? round(amounts.reduce((sum, value) => sum + value, 0)) : undefined, qualityTier: undefined, updatedAt: new Date().toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit', second: '2-digit' }), note };
  });
}
