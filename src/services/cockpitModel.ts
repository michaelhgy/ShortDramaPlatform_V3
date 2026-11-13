import { createOptimizationReasonCounts, matchOptimizationAnalysis, buildOptimizationDefinitions } from '../types/optimizationNotices.ts';
import { isAvailableAccountStatus, visibleOperationsData, type AccountDisplayScope } from './accountVisibility.ts';
import { accountDailySummary, type AccountDailySummary } from './accountDailySummary.ts';
import { 
  type TheaterInfo,
  type AccountInfo,
  type RevenueRecord,
  type AccountDailyTraffic,
  type AccountDailyTrafficDetail,
  type VideoTrafficItem,
  type OptimizationRecord,
  type SimplifiedOptimizationReason,
  OFFICIAL_OPTIMIZATION_DEFINITIONS,
  type AccountOptimizationStat
} from '../types/shortDramaOps.ts';

import type { OperationsDashboardData } from '../api/operationsDashboard';
import { type CockpitDateRange, dateInRange, resolveCockpitDateRange, shiftDate } from './cockpitDateRange.ts';
import { rateAccountRevenue } from './accountRevenueRating.ts';
import { getOptimizationHealth } from './optimizationHealth.ts';
export { shiftDate } from './cockpitDateRange.ts';

function json(value: string): Record<string, any> {
  try { const parsed = JSON.parse(value || '{}'); return parsed && typeof parsed === 'object' ? parsed : {}; }
  catch { return {}; }
}

export function createCockpitModel(data: OperationsDashboardData, workScope: 'all' | 'software' = 'all', accountScope: AccountDisplayScope = 'all') {
  data = visibleOperationsData(data, accountScope);
  const analysisMappings=data.optimization_analysis_configuration?.mappings||[];
  const observedAnalyses=[...(data.work_history||data.publication_history||[]).map(r=>r.optimization?.analysis||''),...(data.pending_optimizations||[]).map(r=>r.analysis||''),...data.video_post_punishments.map(r=>String(json(r.payload_json).notice||''))];
  const optimizationDefinitions=buildOptimizationDefinitions(analysisMappings,observedAnalyses);
  const classifyAnalysis=(text:string)=>matchOptimizationAnalysis(text,analysisMappings);
  const getOptimizationAnalysisTexts=(tag:string)=>optimizationDefinitions[tag]?.analysisTexts||[];

  const softwareHistory = data.publication_history;
  const softwareByWork = new Map((softwareHistory || []).map(r => [JSON.stringify([r.account_id,r.post_id]),r]));
  const chosenHistory = (data.work_history === undefined ? softwareHistory : data.work_history)
    ?.filter(r => workScope === 'all' || r.software || softwareByWork.has(JSON.stringify([r.account_id,r.post_id])))
    .map(r => {
      const software = softwareByWork.get(JSON.stringify([r.account_id,r.post_id]));
      return { ...r, payload_json: JSON.stringify({...json(r.payload_json),...json(software?.payload_json || '{}')}) };
    });
  data = { ...data, publication_history: chosenHistory };
  const pendingOptimizations = (data.pending_optimizations || []).filter(r => workScope === 'all' ||
    chosenHistory?.some(h => h.account_id===r.account_id && h.publish_time===r.publish_time));
  const yesterday = shiftDate(data.today, -1);
  const palette = ['bg-indigo-500', 'bg-emerald-500', 'bg-violet-500', 'bg-amber-500', 'bg-cyan-500'];
  const THEATERS: TheaterInfo[] = data.theaters.map((t, i) => ({
    id: t.id, name: t.name, code: '', description: t.status,
    badgeColor: 'text-indigo-700', accentBg: palette[i % palette.length],
  }));
  const enabledTheaterIds = new Set(data.theaters.filter(theater => theater.status === '启用').map(theater => theater.id));
  const ENABLED_THEATERS = THEATERS.filter(theater => enabledTheaterIds.has(theater.id));
  const usable = (state: string) => ['record', 'confirmed_zero', 'zero', 'cached_only'].includes(state);
  const firstPublished = new Map<string,string>();
  for (const post of data.video_posts) {
    const day=post.post_time?.slice(0,10);
    if (!usable(post.data_state) || !day || day>data.today) continue;
    if (!firstPublished.has(post.account_id) || day<firstPublished.get(post.account_id)!) firstPublished.set(post.account_id,day);
  }
  const ACCOUNTS: AccountInfo[] = data.accounts.map((a, i) => {
    const profile = data.video_accounts.filter(snapshot =>
      (snapshot.account_id === a.id || (!!a.channel_id && snapshot.uid === a.channel_id)) && usable(snapshot.data_state))
      .sort((left, right) => (right.snapshot_date || '').localeCompare(left.snapshot_date || '') || (right.fetched_at || '').localeCompare(left.fetched_at || ''))[0];
    const followers = profile?.fans_total;
    const rating = rateAccountRevenue({accountId:a.id,theaterId:a.theater_id,status:a.status,today:data.today,
      periods:data.revenue_rating?.periods||data.revenue_account_periods,queries:data.revenue_rating?.queries,
      firstPublishDate:firstPublished.get(a.id)});
    return { id: a.id, name: a.nickname, channelId: a.channel_id, avatarUrl: a.avatar_url, theaterId: a.theater_id, theaterName: a.theater_name,
      tier: rating.tier, rating,
      avatarBg: palette[i % palette.length], platform: '微信视频号', businessStatus: a.status, description: a.notes || '',
      loginStatus: a.login_status, loginCheckedAt: a.login_checked_at,
      // Preserve unavailable profile fields as missing.
      videoTotal: profile?.video_total ?? null, followerTotal: typeof followers === 'number' && Number.isFinite(followers) && followers >= 0 ? Math.trunc(followers) : null,
    } as AccountInfo;
  });
  const AVAILABLE_ACCOUNTS = ACCOUNTS.filter(account => isAvailableAccountStatus(account.businessStatus));
  const byId = new Map(ACCOUNTS.map(a => [a.id, a]));
  const dramaById = new Map((data.dramas || []).map(d => [d.id, d]));
  const metric = (value: unknown): number | null => typeof value === 'number' && Number.isFinite(value) ? value : null;
  const DAILY_TRAFFIC_DETAILS: AccountDailyTrafficDetail[] = data.video_account_daily
    .filter(r => usable(r.data_state) || r.data_state === 'incomplete').map(r => ({
      id:r.id, accountId:r.account_id, accountName:byId.get(r.account_id)?.name || '',
      channelId:r.uid || byId.get(r.account_id)?.channelId || '',
      theater:byId.get(r.account_id)?.theaterName || '', date:r.stat_date,
      views:metric(r.view), followerTotal:metric(r.fans_total), followsAdded:metric(r.fans_add),
      follows:metric(r.fans_net), followsReduced:metric(r.fans_reduce), hearts:metric(r.like_count),
      thumbsUp:metric(r.favorite_count), comments:metric(r.comment_count), shares:metric(r.forward_count),
    })).sort((a,b) => a.date.localeCompare(b.date));
  const HISTORICAL_TRAFFIC: AccountDailyTraffic[] = data.video_account_daily.filter(r => usable(r.data_state)).map(r => ({
    id: r.id, accountId: r.account_id, accountName: byId.get(r.account_id)?.name || '',
    theater: byId.get(r.account_id)?.theaterName || '', date: r.stat_date,
    views: r.view, follows: r.fans_net, hearts: r.like_count, comments: r.comment_count,
  })).sort((a, b) => a.date.localeCompare(b.date));
  const HISTORICAL_REVENUE: RevenueRecord[] = data.revenue_account_periods.filter(r =>
    usable(r.data_state) && (r.include_in_analysis === 1 || r.settlement_state === 'settled') && r.amount !== null
    && ['day', 'month_cumulative'].includes(r.period_type)
  ).map(r => ({ id: r.id, accountId: r.account_id, accountName: byId.get(r.account_id)?.name || '',
    theater: byId.get(r.account_id)?.theaterName || '', date: r.period_end,
    amount: Number(r.amount), periodType: r.period_type, periodStart: r.period_start,
  })).sort((a, b) => a.date.localeCompare(b.date));
  const MONTHLY_REVENUE = HISTORICAL_REVENUE.filter(r => r.periodType === 'month_cumulative');
  const punishmentByPost = new Map(data.video_post_punishments.map(r => [r.post_id_or_export_id, r]));
  const OPTIMIZATION_RECORDS: OptimizationRecord[] = [];
  const publicationByWork = new Map((data.publication_history || [])
    .filter(r => r.match_state === 'matched' && r.post_id)
    .map(r => [JSON.stringify([r.account_id, r.post_id]), r]));
  const VIDEO_TRAFFIC_DATA: VideoTrafficItem[] = data.video_posts.filter(r => usable(r.data_state) && (workScope === 'all' || publicationByWork.has(JSON.stringify([r.account_id,r.post_id])))).map(r => {
    const account = byId.get(r.account_id);
    const publication = publicationByWork.get(JSON.stringify([r.account_id, r.post_id]));
    const releaseMeta = json(publication?.payload_json || '{}');
    const meta = { ...json(r.payload_json), ...releaseMeta };
    const drama = dramaById.get(meta.drama_id);
    const rawRisk = data.publication_history === undefined ? punishmentByPost.get(r.post_id) : undefined;
    const riskMeta = json(rawRisk?.payload_json || '{}');
    const analysis = typeof riskMeta.notice === 'string' ? riskMeta.notice : '';
    const reason = classifyAnalysis(analysis);
    const fileName = releaseMeta.name || `作品 ${r.post_id}`;
    const base = { id: r.post_id, accountId: r.account_id, accountName: account?.name || r.account_name,
      theater: account?.theaterName || '', publishTime: r.post_time, views: r.view,
      statsCollectedAt:r.fetched_at,statsDate:r.snapshot_date,statsState:r.data_state,
      completionRate: Number((r.full_view <= 1 ? r.full_view * 100 : r.full_view).toFixed(1)),
      hearts: r.love_count, comments: r.comment_count, shares: r.forward_count, thumbsUp: r.like_count,
      fileName, dramaTitle: drama?.name || meta.drama_name || '未关联剧集', episodeNumber: meta.episode || 0,
      dramaId: drama?.id, coverUrl: r.cover_url || releaseMeta.cover_url || drama?.cover_url,
      fallbackCoverUrl: drama?.cover_url, videoUrl: r.video_url || releaseMeta.video_url || undefined,
      videoDuration: r.video_duration ?? releaseMeta.video_duration ?? undefined, avatarUrl: account?.avatarUrl,
      hasOptimization: Boolean(rawRisk),
    };
    if (rawRisk) {
      const optimization: OptimizationRecord = { id: rawRisk.id, accountId: base.accountId, accountName: base.accountName,
        theater: base.theater, publishTime: base.publishTime, fileName, dramaTitle: base.dramaTitle,
        episodeNumber: base.episodeNumber, simplifiedReason: reason, reasonType: reason,
        officialNotice: analysis, severity: !riskMeta.generated && !riskMeta.simulation && ['严重','中度','轻微'].includes(riskMeta.severity) ? riskMeta.severity : '未判定',
        impactNotice: rawRisk.punish_state, detectedDate: riskMeta.detectedDate || rawRisk.snapshot_date, viewsAtDetection: r.view,
      };
      OPTIMIZATION_RECORDS.push(optimization);
      return { ...base, optimization };
    }
    return base;
  }).sort((a, b) => b.publishTime.localeCompare(a.publishTime));
  const HISTORY_VIDEOS: VideoTrafficItem[] = data.publication_history === undefined ? VIDEO_TRAFFIC_DATA :
    data.publication_history.filter(r => r.publication_state === 'published' && r.match_state === 'matched' && byId.has(r.account_id)).map(r => {
      const account = byId.get(r.account_id)!;
      const traffic = VIDEO_TRAFFIC_DATA.find(v => v.accountId === r.account_id && v.id === r.post_id);
      const meta = json(r.payload_json);
      const event = r.optimization;
      const reason = classifyAnalysis(event?.analysis || '');
      const fileName = meta.name || traffic?.fileName || `作品 ${r.post_id}`;
      const optimization: OptimizationRecord | undefined = event ? {
        id:r.id, accountId:r.account_id, accountName:account.name, theater:account.theaterName,
        publishTime:r.publish_time, fileName, dramaTitle:traffic?.dramaTitle || '未关联剧集',
        episodeNumber:traffic?.episodeNumber || 0, simplifiedReason:reason, reasonType:reason,
        officialNotice:event.analysis, severity:'未判定', impactNotice:event.platform_state,
        detectedDate:event.first_seen_at.slice(0,10), viewsAtDetection:Number.NaN,
      } : undefined;
      if(optimization) OPTIMIZATION_RECORDS.push(optimization);
      if(traffic && optimization) { traffic.hasOptimization = true; traffic.optimization = optimization; }
      return { ...traffic, id:r.post_id, accountId:r.account_id, accountName:account.name,
        theater:account.theaterName, publishTime:r.publish_time, fileName,
        dramaTitle:traffic?.dramaTitle || dramaById.get(meta.drama_id)?.name || '未关联剧集', episodeNumber:traffic?.episodeNumber || 0,
        coverUrl:traffic?.coverUrl || meta.cover_url || dramaById.get(meta.drama_id)?.cover_url,
        fallbackCoverUrl:traffic?.fallbackCoverUrl || dramaById.get(meta.drama_id)?.cover_url,
        videoUrl:traffic?.videoUrl || meta.video_url || undefined,
        videoDuration:traffic?.videoDuration ?? meta.video_duration ?? undefined,
        views:traffic?.views ?? Number.NaN, completionRate:traffic?.completionRate ?? Number.NaN,
        hearts:traffic?.hearts ?? Number.NaN, comments:traffic?.comments ?? Number.NaN,
        shares:traffic?.shares ?? Number.NaN, thumbsUp:traffic?.thumbsUp ?? Number.NaN,
        hasOptimization:!!event, optimization,
      };
    }).sort((a,b)=>b.publishTime.localeCompare(a.publishTime));
  const optimizationKnown = (videos: VideoTrafficItem[], range:CockpitDateRange='all', accountIds=videos.map(v=>v.accountId)) =>
    data.publication_history === undefined || (videos.length > 0 && !pendingOptimizations.some(p => accountIds.includes(p.account_id)
      && (!p.publish_time || isDateInRange(p.publish_time.slice(0,10),range))) && videos.every(v =>
      data.publication_history!.some(r=>r.account_id===v.accountId && r.post_id===v.id && r.optimization_state!=='unknown')));
  const optRate = (count:number, videos:VideoTrafficItem[], range:CockpitDateRange='all', accountIds?:string[]):number|null => optimizationKnown(videos,range,accountIds)
    ? (videos.length ? Number((count/videos.length*100).toFixed(1)) : 0) : null;
  OPTIMIZATION_RECORDS.sort((a, b) => b.publishTime.localeCompare(a.publishTime));
  const DATES = [...new Set(HISTORICAL_TRAFFIC.map(r => r.date))].sort();
  const ALL_SIMPLIFIED_REASONS = Object.keys(optimizationDefinitions) as SimplifiedOptimizationReason[];
  const earliestDate = [...HISTORICAL_TRAFFIC.map(r => r.date),
    ...HISTORICAL_REVENUE.map(r => r.periodStart || r.date), ...pendingOptimizations.map(p=>p.publish_time.slice(0,10)),
    ...VIDEO_TRAFFIC_DATA.map(v => v.publishTime.slice(0, 10)), ...HISTORY_VIDEOS.map(v=>v.publishTime.slice(0,10))].filter(Boolean).sort()[0] || yesterday;

const dateBoundsCache = new Map<CockpitDateRange, ReturnType<typeof resolveCockpitDateRange>>();
function getDateBounds(range: CockpitDateRange) {
  let bounds = dateBoundsCache.get(range);
  if (!bounds) {
    bounds = resolveCockpitDateRange(range, data.today, earliestDate);
    dateBoundsCache.set(range, bounds);
  }
  return bounds;
}

function getDateFilterBoundary(range: CockpitDateRange): string {
  return getDateBounds(range).start;
}

function isDateInRange(date: string, range: CockpitDateRange) {
  return dateInRange(date, getDateBounds(range));
}

function inRevenueRange(r: RevenueRecord, range: CockpitDateRange) {
  const bounds = getDateBounds(range);
  if (r.periodType === 'month_cumulative') {
    return bounds.days > 1 && (r.periodStart || r.date) >= bounds.start && r.date <= bounds.end;
  }
  return dateInRange(r.date, bounds);
}

// 5.2 综合 KPI 概览汇总
function getKPISummary(
  theaterFilter: string = 'ALL',
  accountFilter: string = 'ALL',
  dateRange: CockpitDateRange = '30days'
) {

  // 1. 收益
  const filteredRev = filterRevenue(theaterFilter, accountFilter, dateRange);
  const totalRevenue = filteredRev.reduce((sum, r) => sum + r.amount, 0);
  const monthlyRevenue = MONTHLY_REVENUE.filter(r => (theaterFilter === 'ALL' || r.theater === theaterFilter)
    && (accountFilter === 'ALL' || r.accountId === accountFilter)).reduce((sum, r) => sum + r.amount, 0);

  // 2. 账号流量
  const filteredTraf = HISTORICAL_TRAFFIC.filter(t => {
    if (theaterFilter !== 'ALL' && t.theater !== theaterFilter) return false;
    if (accountFilter !== 'ALL' && t.accountId !== accountFilter) return false;
    return isDateInRange(t.date, dateRange);
  });
  const totalViews = filteredTraf.reduce((sum, t) => sum + t.views, 0);
  const totalFollows = filteredTraf.reduce((sum, t) => sum + t.follows, 0);
  const totalHearts = filteredTraf.reduce((sum, t) => sum + t.hearts, 0);
  const totalComments = filteredTraf.reduce((sum, t) => sum + t.comments, 0);

  // 3. 视频与优化
  const filteredVids = HISTORY_VIDEOS.filter(v => {
    if (theaterFilter !== 'ALL' && v.theater !== theaterFilter) return false;
    if (accountFilter !== 'ALL' && v.accountId !== accountFilter) return false;
    const vDate = v.publishTime.slice(0, 10);
    return isDateInRange(vDate, dateRange);
  });
  const totalVideos = filteredVids.length;
  const publishedAccountCount = new Set(filteredVids.map(video => video.accountId)).size;
  const optimizedVideos = filteredVids.filter(v => v.hasOptimization).length;
  const originalOptimizedVideos = filteredVids.filter(video => video.hasOptimization && video.optimization
    && optimizationDefinitions[video.optimization.simplifiedReason].homogeneous).length;
  const rateAccounts = ACCOUNTS.filter(a=>(theaterFilter==='ALL'||a.theaterName===theaterFilter)&&(accountFilter==='ALL'||a.id===accountFilter)).map(a=>a.id);
  const overallOptRate = optRate(optimizedVideos, filteredVids,dateRange,rateAccounts);
  const originalOptRate = optRate(originalOptimizedVideos, filteredVids,dateRange,rateAccounts);

  // 4. 万播产值 (RPM)
  const rpm = totalViews > 0 ? Number(((totalRevenue / totalViews) * 10000).toFixed(1)) : 0;

  return {
    totalRevenue, monthlyRevenue, hasRevenue:filteredRev.length>0, hasTraffic:filteredTraf.length>0,
    totalViews,
    totalFollows,
    totalHearts,
    totalComments,
    totalVideos,
    publishedAccountCount,
    optimizedVideos,
    originalOptimizedVideos,
    overallOptRate,
    originalOptRate,
    rpm
  };
}

// 5.3 过滤收益明细
function filterRevenue(
  theaterFilter: string = 'ALL',
  accountFilter: string = 'ALL',
  dateRange: CockpitDateRange = '30days'
) {
  const candidates = HISTORICAL_REVENUE.filter(r => {
    if (theaterFilter !== 'ALL' && r.theater !== theaterFilter) return false;
    if (accountFilter !== 'ALL' && r.accountId !== accountFilter) return false;
    return inRevenueRange(r, dateRange);
  });
  // A whole monthly total already covers its daily facts; never add them twice.
  const months: RevenueRecord[] = [];
  for (const row of candidates.filter(r=>r.periodType==='month_cumulative').sort((a,b)=>b.date.localeCompare(a.date))) {
    if (!months.some(m=>m.accountId===row.accountId && (row.periodStart||row.date)<=m.date && row.date>=(m.periodStart||m.date))) months.push(row);
  }
  return candidates.filter(row=>row.periodType==='month_cumulative' ? months.includes(row) :
    !months.some(month=>month.accountId===row.accountId && row.date>=(month.periodStart||month.date) && row.date<=month.date));
}

// 5.4 过滤流量明细
function filterTraffic(
  theaterFilter: string = 'ALL',
  accountFilter: string = 'ALL',
  dateRange: CockpitDateRange = '30days'
) {
  return HISTORICAL_TRAFFIC.filter(t => {
    if (theaterFilter !== 'ALL' && t.theater !== theaterFilter) return false;
    if (accountFilter !== 'ALL' && t.accountId !== accountFilter) return false;
    return isDateInRange(t.date, dateRange);
  });
}

function filterTrafficDetails(theaterFilter = 'ALL', accountFilter = 'ALL', dateRange: CockpitDateRange = '30days') {
  return DAILY_TRAFFIC_DETAILS.filter(row => (theaterFilter === 'ALL' || row.theater === theaterFilter)
    && (accountFilter === 'ALL' || row.accountId === accountFilter) && isDateInRange(row.date,dateRange));
}

// 5.5 过滤视频列表
function filterVideos(
  theaterFilter: string = 'ALL',
  accountFilter: string = 'ALL',
  dateRange: CockpitDateRange = '30days',
  searchQuery: string = '',
  onlyOptimized: boolean = false
) {
  const q = searchQuery.trim().toLowerCase();

  return VIDEO_TRAFFIC_DATA.filter(v => {
    if (theaterFilter !== 'ALL' && v.theater !== theaterFilter) return false;
    if (accountFilter !== 'ALL' && v.accountId !== accountFilter) return false;

    const vDate = v.publishTime.slice(0, 10);
    if (!isDateInRange(vDate, dateRange)) return false;

    if (onlyOptimized && !v.hasOptimization) return false;

    if (q) {
      const matchFile = v.fileName.toLowerCase().includes(q);
      const matchDrama = v.dramaTitle.toLowerCase().includes(q);
      const matchAccount = v.accountName.toLowerCase().includes(q);
      const matchTheater = v.theater.toLowerCase().includes(q);
      if (!matchFile && !matchDrama && !matchAccount && !matchTheater) return false;
    }

    return true;
  });
}

// 5.6 账号经营排名 (以账号为单位统计收益、播放、发片、优化率)
interface AccountRankingItem {
  account: AccountInfo;
  dailySummary: AccountDailySummary;
  revenue: number;
  hasPeriodRevenue: boolean;
  hasPeriodTraffic: boolean;
  hasWorkData: boolean;
  monthlyRevenue: number | null;
  views: number;
  follows: number;
  hearts: number;
  comments: number;
  videoCount: number;
  optimizedCount: number;
  optimizationRate: number | null;
  rpm: number;
}

function getAccountRankings(
  theaterFilter: string = 'ALL',
  dateRange: CockpitDateRange = '30days',
  sortBy: 'revenue' | 'views' | 'optimizationRate' | 'videoCount' = 'revenue'
): AccountRankingItem[] {

  const matchedAccounts = theaterFilter === 'ALL' 
    ? ACCOUNTS 
    : ACCOUNTS.filter(a => a.theaterName === theaterFilter);

  const results: AccountRankingItem[] = matchedAccounts.map(account => {
    // 收益
    const revs = filterRevenue('ALL', account.id, dateRange);
    const revenue = revs.reduce((sum, r) => sum + r.amount, 0);

    // 流量
    const trafs = HISTORICAL_TRAFFIC.filter(t => {
      if (t.accountId !== account.id) return false;
      return isDateInRange(t.date, dateRange);
    });
    const views = trafs.reduce((sum, t) => sum + t.views, 0);
    const follows = trafs.reduce((sum, t) => sum + t.follows, 0);
    const hearts = trafs.reduce((sum, t) => sum + t.hearts, 0);
    const comments = trafs.reduce((sum, t) => sum + t.comments, 0);

    // 视频
    const vids = HISTORY_VIDEOS.filter(v => {
      if (v.accountId !== account.id) return false;
      const vDate = v.publishTime.slice(0, 10);
      return isDateInRange(vDate, dateRange);
    });
    const videoCount = vids.length;
    const cohort = HISTORY_VIDEOS.filter(v=>v.accountId===account.id && isDateInRange(v.publishTime.slice(0,10),dateRange));
    const optimizedCount = cohort.filter(v => v.hasOptimization).length;
    const optimizationRate = optRate(optimizedCount, cohort,dateRange,[account.id]);
    const rpm = views > 0 ? Number(((revenue / views) * 10000).toFixed(1)) : 0;

    return {
      account,
      dailySummary: accountDailySummary([...data.video_account_daily, ...(data.account_daily_latest || [])], account.id, account.channelId, yesterday),
      revenue,
      hasPeriodRevenue: revs.length > 0,
      hasPeriodTraffic: trafs.length > 0,
      hasWorkData: vids.length > 0 || account.videoTotal === 0,
      monthlyRevenue: MONTHLY_REVENUE.some(r => r.accountId === account.id) ? MONTHLY_REVENUE.filter(r => r.accountId === account.id).reduce((sum,r) => sum+r.amount,0) : null,
      views,
      follows,
      hearts,
      comments,
      videoCount,
      optimizedCount,
      optimizationRate,
      rpm
    };
  });

  return results.sort((a, b) => {
    if (sortBy === 'revenue') return b.revenue - a.revenue;
    if (sortBy === 'views') return b.views - a.views;
    if (sortBy === 'optimizationRate') return (b.optimizationRate ?? -1) - (a.optimizationRate ?? -1);
    return b.videoCount - a.videoCount;
  });
}

// 5.7 账号发视频优化分析 (以账号为核心，分析优化率、原因构成与风险等级)
function getAccountOptimizationStats(
  theaterFilter: string = 'ALL',
  dateRange: CockpitDateRange = '30days'
): AccountOptimizationStat[] {

  const matchedAccounts = theaterFilter === 'ALL' 
    ? ACCOUNTS 
    : ACCOUNTS.filter(a => a.theaterName === theaterFilter);

  return matchedAccounts.map(account => {
    const vids = HISTORY_VIDEOS.filter(v => {
      if (v.accountId !== account.id) return false;
      const vDate = v.publishTime.slice(0, 10);
      return isDateInRange(vDate, dateRange);
    });

    const totalVideos = vids.length;
    const optimizedVideosList = vids.filter(v => v.hasOptimization);
    const optimizedVideos = optimizedVideosList.length;
    const optimizationRate = optRate(optimizedVideos, vids,dateRange,[account.id]);
    const totalViews = VIDEO_TRAFFIC_DATA.filter(v=>v.accountId===account.id && isDateInRange(v.publishTime.slice(0,10),dateRange)).reduce((sum,v)=>sum+v.views,0);
    const impactedViews = optimizedVideosList.reduce((sum, v) => sum + (Number.isFinite(v.views) ? v.views : 0), 0);

    const reasonCounts = createOptimizationReasonCounts(ALL_SIMPLIFIED_REASONS);

    optimizedVideosList.forEach(v => {
      if (v.optimization?.simplifiedReason) {
        reasonCounts[v.optimization.simplifiedReason] = (reasonCounts[v.optimization.simplifiedReason] || 0) + 1;
      }
    });

    let topReason: SimplifiedOptimizationReason | undefined = undefined;
    let maxReasonCount = 0;
    ALL_SIMPLIFIED_REASONS.forEach(r => {
      if (reasonCounts[r] > maxReasonCount) {
        maxReasonCount = reasonCounts[r];
        topReason = r;
      }
    });

    const healthLevel=getOptimizationHealth(optimizationRate);

    const latestOptimizedDate = optimizedVideosList.length > 0 
      ? optimizedVideosList[0].publishTime.slice(0, 10) 
      : undefined;

    return {
      accountId: account.id,
      accountName: account.name,
      theater: account.theaterName,
      tier: account.tier,
      totalVideos,
      optimizedVideos,
      optimizationRate, optimizationKnown: optimizationKnown(vids,dateRange,[account.id]),
      hasTraffic: VIDEO_TRAFFIC_DATA.some(v=>v.accountId===account.id && isDateInRange(v.publishTime.slice(0,10),dateRange)),
      totalViews,
      impactedViews,
      reasonCounts,
      topReason,
      healthLevel,
      latestOptimizedDate
    };
  }).sort((a, b) => (b.optimizationRate ?? -1) - (a.optimizationRate ?? -1));
}

// 5.8 暂行作品分析标签分布统计
function getOptimizationReasonDistribution(
  theaterFilter: string = 'ALL',
  accountFilter: string = 'ALL',
  dateRange: CockpitDateRange = '30days'
) {

  const filteredOpts = OPTIMIZATION_RECORDS.filter(o => {
    if (theaterFilter !== 'ALL' && o.theater !== theaterFilter) return false;
    if (accountFilter !== 'ALL' && o.accountId !== accountFilter) return false;
    return isDateInRange(o.publishTime.slice(0, 10), dateRange);
  });

  const counts = createOptimizationReasonCounts(ALL_SIMPLIFIED_REASONS);

  filteredOpts.forEach(o => {
    if (counts[o.simplifiedReason] !== undefined) {
      counts[o.simplifiedReason]++;
    }
  });

  const total = filteredOpts.length;

  return ALL_SIMPLIFIED_REASONS.map(reason => {
    const count = counts[reason] || 0;
    const percentage = total > 0 ? Math.round((count / total) * 100) : 0;
    const def = optimizationDefinitions[reason];
    return {
      reason,
      count,
      percentage,
      severity: def.severity,
      officialNotice: def.officialNotice,
      impactNotice: def.impactNotice,
      shortTag: def.shortTag
    };
  }).sort((a, b) => b.count - a.count);
}

// 5.9 每日优化趋势统计 (按天统计优化量与发片量)
interface DailyOptimizationTrend {
  date: string;
  totalPublished: number;
  totalOptimized: number;
  rate: number | null;
}

function getDailyOptimizationTrends(
  theaterFilter: string = 'ALL',
  accountFilter: string = 'ALL',
  dateRange: CockpitDateRange = '30days'
): DailyOptimizationTrend[] {

  const days = [...new Set(HISTORY_VIDEOS.map(v=>v.publishTime.slice(0,10)))].sort().filter(d => isDateInRange(d, dateRange));

  return days.map(date => {
    const vids = HISTORY_VIDEOS.filter(v => {
      if (theaterFilter !== 'ALL' && v.theater !== theaterFilter) return false;
      if (accountFilter !== 'ALL' && v.accountId !== accountFilter) return false;
      return v.publishTime.slice(0, 10) === date;
    });

    const totalPublished = vids.length;
    const totalOptimized = vids.filter(v => v.hasOptimization).length;
    const rate = optRate(totalOptimized, vids,{kind:'day',date});

    return {
      date,
      totalPublished,
      totalOptimized,
      rate
    };
  });
}


  return { THEATERS, ENABLED_THEATERS, ACCOUNTS, AVAILABLE_ACCOUNTS, VIDEO_TRAFFIC_DATA, HISTORY_VIDEOS, HISTORICAL_REVENUE, HISTORICAL_TRAFFIC, OPTIMIZATION_RECORDS,
    MONTHLY_REVENUE, getDateFilterBoundary, getDateBounds, isDateInRange, getKPISummary, filterRevenue, filterTraffic, filterTrafficDetails, filterVideos, getAccountRankings,
    getAccountOptimizationStats, getOptimizationReasonDistribution, getDailyOptimizationTrends,
    optimizationDefinitions, getOptimizationAnalysisTexts, workScope, pendingOptimizations, optimizationActionSettings: data.optimization_action_settings, optimizationActionLog: data.optimization_action_log || [],
    accountScope, today: data.today, yesterday, latestDate: data.latest_date, coverage: data.coverage };
}

export type CockpitModel = ReturnType<typeof createCockpitModel>;
