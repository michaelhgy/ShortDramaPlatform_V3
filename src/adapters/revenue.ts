import type {
  ChangeSignalItem, ContributionItem, DailyRevenueDataPoint, DramaAttributionSummary,
  RevenueCollectionLog, RevenueQualityTier, RevenueSummaryMetrics, TheaterFilter, TimeRangeFilter, TrendGhostPoint,
} from '../analyticsTypes';
import type { V1CatalogAccount, V1CatalogTheater, V1DailyRevenue, V1RevenueCollectionResponse } from '../types/revenue';

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

export function resolveV1RevenueRange(timeRange: TimeRangeFilter, customStart?: string, customEnd?: string) {
  const today = iso(new Date());
  const yesterday = addDays(today, -1);
  if (timeRange === 'yesterday') return { currentStart: yesterday, currentEnd: yesterday, previousStart: addDays(yesterday, -1), previousEnd: addDays(yesterday, -1), trendDates: enumerate(addDays(yesterday, -6), yesterday) };
  if (timeRange === '7days') return { currentStart: addDays(yesterday, -6), currentEnd: yesterday, previousStart: addDays(yesterday, -13), previousEnd: addDays(yesterday, -7), trendDates: enumerate(addDays(yesterday, -6), yesterday) };
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
  const activeTheaterIds = new Set(theaters.filter((theater) => theater.status !== 'disabled').map((theater) => theater.id));
  const eligibleAccounts = accounts.filter((account) => account.status !== 'disabled' && account.theater_id !== null && activeTheaterIds.has(account.theater_id) && (theaterFilter === 'all' || canonicalTheater(theaters.find((theater) => theater.id === account.theater_id)?.name || '') === theaterFilter));
  const updatedAccounts = new Set(latestRows.map((row) => row.account_id)).size;
  const totalAccounts = eligibleAccounts.length;
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
    completenessText: `${updatedAccounts}/${totalAccounts} 账号已有日收益记录${pendingAccounts ? ` · ${pendingAccounts} 未记录` : ''}`,
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
  const theaterContributions = [...theaterMap.values()].sort((left, right) => right.revenue - left.revenue);
  const accountContributions = [...accountMap.values()].sort((left, right) => right.revenue - left.revenue);
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
