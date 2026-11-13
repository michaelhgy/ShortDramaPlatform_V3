import { matchesAccountScope } from '../../services/accountVisibility.ts';
import { getLoginState } from '../../services/accountMatrixSort.ts';
import type { AccountInfo } from '../../types/shortDramaOps';
import type { CollectionJob, CollectionState, CollectionCategory } from '../../api/operationsDashboard';
import type { AccountCollectionProfile, AccountExecutionRow, CategoryExecutionItem, CollectionCategoryKey, ItemResultStatus } from './DataCollectionModal';

export const visibleCategory: Partial<Record<CollectionCategory, CollectionCategoryKey>> = {daily: 'daily_stats', works: 'video_traffic', optimization: 'optimization', revenue: 'revenue'};
const isoShift = (day: string, amount: number) => {const d = new Date(day + 'T00:00:00Z'); d.setUTCDate(d.getUTCDate() + amount); return d.toISOString().slice(0, 10);};
export const collectionToday = (state: CollectionState | null) => state?.yesterday ? isoShift(state.yesterday, 1) : '';
export const periodStart = (today: string, days: number) => today ? isoShift(today, 1 - days) : '';

export function allJobItems(job: CollectionJob | null) {
  return job ? [...new Map([...(job.retained_items || []), ...job.items].map(item => [item.id || `${item.account_id}:${item.category}`, item])).values()] : [];
}

export function collectionProfiles(accounts: AccountInfo[], state: CollectionState | null): AccountCollectionProfile[] {
  return accounts.map(account => {
    const meta = state?.accounts.find(item => item.id === account.id);
    const businessStatus=meta?.business_status ?? account.businessStatus;
    const loginStatus=meta?.login_status ?? account.loginStatus;
    const loginInvalid=getLoginState(loginStatus)==='invalid';
    const platformAvailable=businessStatus !== '注销' && (meta?.platform_available ?? !!meta?.available);
    const available=businessStatus !== '注销' && !!meta?.available;
    const missingDates = meta?.daily_missing_dates || [];
    let dailyGapState: AccountCollectionProfile['dailyGapState'] = 'unknown';
    let dailyGapDesc = '本地完整性尚未确认';
    if (meta) {
      if (!available) {dailyGapState = 'auth_expired'; dailyGapDesc = meta.unavailable_reason || '账号暂不可采集';}
      else if (!meta.daily_boundary) {dailyGapState = 'initial_backfill'; dailyGapDesc = '历史边界未确认，需继续补齐；不代表新注册账号';}
      else if (meta.daily_through === state?.yesterday && meta.daily_state === 'complete') {dailyGapState = 'complete'; dailyGapDesc = `截至 ${state.yesterday} 已完整，普通采集跳过`;}
      else if (missingDates.length === 1 && missingDates[0] === state?.yesterday) {dailyGapState = 'missing_yesterday'; dailyGapDesc = `仅缺昨日 ${state.yesterday}`;}
      else {dailyGapState = 'missing_days'; dailyGapDesc = missingDates.length ? `已确认 ${missingDates.length} 个缺日，仍需核对最新日期` : `需核对截至 ${state?.yesterday} 的缺口`;}
    }
    const lastFailed = allJobItems(state?.job || null).some(item => item.account_id === account.id && ['failed','partial','stopped'].includes(item.status)) || false;
    return {
      account:{...account,businessStatus,loginStatus,loginCheckedAt:meta?.login_checked_at ?? account.loginCheckedAt}, available, platformAvailable, unavailableReason: businessStatus === '注销' ? '账号已注销，停止采集；历史数据保留' : loginInvalid ? '登录失效，平台数据默认不选，可手动选择后核对；剧场收益不受影响' : meta?.unavailable_reason || (meta ? '' : '尚未取得账号采集状态'), dailyGapState, dailyGapDesc, missingDates,
      historyBoundaryConfirmed: !!meta?.daily_boundary, earliestActiveDate: meta?.daily_boundary || '',
      videoTotalCount: meta?.profile_total?.postCount ?? account.videoTotal ?? null,
      followerCount: meta?.profile_total?.fans ?? account.followerTotal ?? null,
      profileSourceTime: meta?.profile_source_time || '来源更新时间未提供',
      recent7dVideoCount: null, uncollectedOptimizationCount: null,
      optimizationNeedsCheck: meta?.optimization_due ?? !meta?.last_success.optimization,
      lastFailed, revenueMode: meta?.revenue?.mode || 'unknown',
      revenueCollectorName: meta?.revenue?.collector_name || '',
      revenueAvailable: businessStatus !== '注销' && !!meta?.revenue?.available, revenueState: meta?.revenue?.state || 'unconfigured',
      revenueStatusDesc: meta?.revenue?.message || '未配置收益采集器',
      revenueUnupdated: !!meta?.revenue?.available && meta.revenue.state !== 'complete',
    };
  }).sort((a,b)=>loginOrder(a.account.loginStatus)-loginOrder(b.account.loginStatus));
}
const loginOrder=(value?:string)=>{const state=getLoginState(value);return state==='valid'?0:state==='unknown'?1:2;};
export function needsCollection(profile: AccountCollectionProfile) {
  return profile.available && (profile.dailyGapState !== 'complete' || profile.revenueUnupdated || profile.optimizationNeedsCheck || profile.lastFailed);
}
export type CollectionScenario = 'daily_routine' | 'targeted_video_7d' | 'optimization_now' | 'revenue_only';
export const collectionScenarios: ReadonlyArray<{id: CollectionScenario; label: string; description: string}> = [
  {id:'daily_routine', label:'日常补齐数据', description:'补齐每日数据和已配置的剧场收益；已有确定结果跳过，不发起优化检测'},
  {id:'targeted_video_7d', label:'更新近期视频流量', description:'更新近7天发布作品的累计流量，保留逐页随机等待并遵守重复更新间隔'},
  {id:'optimization_now', label:'立即检测优化', description:'本次直接检测所选账号，不改变全局自动检测设置'},
  {id:'revenue_only', label:'只补剧场收益', description:'仅补已配置来源的收益；补齐历史和缺日，已确定结果不重复查询'},
];
export function scenarioCategories(id: CollectionScenario, revenueReady = true): Record<CollectionCategoryKey, boolean> {
  return {daily_stats:id==='daily_routine', video_traffic:id==='targeted_video_7d', optimization:id==='optimization_now', revenue:revenueReady && (id==='daily_routine'||id==='revenue_only')};
}
/** Recommendations follow this task only. Source login and range cooldown are checked again by the backend. */
export function collectionAccountSelectable(profile:AccountCollectionProfile,enabled:Record<CollectionCategoryKey,boolean>) {
  return profile.account.businessStatus !== '注销' && profile.available && ((profile.platformAvailable!==false && (enabled.daily_stats||enabled.video_traffic||enabled.optimization)) || (enabled.revenue&&profile.revenueAvailable));
}
export function taskAccountIds(profiles: AccountCollectionProfile[], enabled: Record<CollectionCategoryKey, boolean>, dailyMode: string): string[] {
  return profiles.filter(p => p.account.businessStatus !== '注销' && p.available && (
    (matchesAccountScope(p.account.businessStatus,'current') && getLoginState(p.account.loginStatus)!=='invalid' && p.platformAvailable !== false &&
      ((enabled.daily_stats && (dailyMode==='reset_online' || p.dailyGapState!=='complete')) || enabled.video_traffic || enabled.optimization)) ||
    (enabled.revenue && p.revenueAvailable && p.revenueUnupdated)
  )).map(p=>p.account.id);
}

export function projectedJobRows(job: CollectionJob | null, profiles: AccountCollectionProfile[]): AccountExecutionRow[] {
  if (!job) return [];
  const groups = new Map<string, CollectionJob['items']>();
  for (const item of allJobItems(job)) {if (!groups.has(item.account_id)) groups.set(item.account_id, []); groups.get(item.account_id)!.push(item);}
  return [...groups.entries()].map(([accountId, items]) => {
    const profile = profiles.find(p => p.account.id === accountId);
    const categories: AccountExecutionRow['categories'] = {};
    for (const item of items) {
      const category = visibleCategory[item.category]; if (!category) continue;
      const status: ItemResultStatus = item.category === 'revenue' && item.revenue_result?.pending_days && !item.revenue_result.failed_days ? 'source_unupdated' : item.status === 'waiting' ? 'pending' : item.status === 'success' ? 'updated' : item.status;
      categories[category] = {category, status, summaryText: item.message || '等待前序请求完成',
        detailBadge: item.status === 'success' ? '已完成' : undefined,
        preservedOldData: ['failed','partial','stopped'].includes(item.status)};
    }
    const states = items.map(item => item.status);
    const overallStatus: AccountExecutionRow['overallStatus'] = states.includes('running') ? 'running' : states.includes('waiting') ? 'waiting' : states.includes('failed') ? 'failed' : states.includes('partial') ? 'partial' : states.includes('stopped') ? 'stopped' : states.every(status => status === 'skipped') ? 'skipped' : 'completed';
    const totals = items.find(item => item.category === 'profile');
    return {
      accountId, accountName: items[0].account_name, theaterName: profile?.account.theaterName || '未提供剧场', revenueMode: profile?.revenueMode || 'unknown',
      overallStatus, categories,
      errorReason: items.filter(item => ['failed','partial','stopped'].includes(item.status)).map(item => item.message).join('；') || undefined,
      profilePiggybacked: totals && profile ? {videos: profile.videoTotalCount, followers: profile.followerCount, sourceUpdatedAt: profile.profileSourceTime, isReusedCache: true} : undefined,
    };
  });
}
export function mergeRetryRows(previous: AccountExecutionRow[], current: AccountExecutionRow[]) {
  const map = new Map(previous.map(row => [row.accountId, row]));
  for (const row of current) {
    const old = map.get(row.accountId);
    const combined = {...old?.categories, ...row.categories};
    const states = Object.values(combined).map(item => item!.status);
    let overallStatus = row.overallStatus;
    if (!['running','waiting','failed','partial','stopped'].includes(overallStatus)) {
      if (states.some(status => ['failed','partial','stopped'].includes(status))) overallStatus = 'partial';
    }
    map.set(row.accountId, {...row, categories: combined, overallStatus, profilePiggybacked: row.profilePiggybacked || old?.profilePiggybacked});
  }
  return [...map.values()];
}
export function planSummary(profiles: AccountCollectionProfile[], selectedIds: Set<string>, enabled: Record<CollectionCategoryKey, boolean>, dailyMode: string, videoMode: string, platformAccountIds?: ReadonlySet<string>) {
  const selected = profiles.filter(p => collectionAccountSelectable(p,enabled) && selectedIds.has(p.account.id));
  const platformSelected=selected.filter(p=>p.platformAvailable!==false && (platformAccountIds ? platformAccountIds.has(p.account.id) : matchesAccountScope(p.account.businessStatus,'current')));
  return {
    platformUnavailableCount:selected.length-platformSelected.length,
    selectedCount: selected.length,
    activeCats: (Object.keys(enabled) as CollectionCategoryKey[]).filter(key => enabled[key]),
    dailyNeedFetchCount: platformSelected.filter(p => ['force_range','reset_online'].includes(dailyMode) || p.dailyGapState !== 'complete').length,
    dailySkipCompleteCount: platformSelected.filter(p => !['force_range','reset_online'].includes(dailyMode) && p.dailyGapState === 'complete').length,
    dailyInitialBackfillCount: platformSelected.filter(p => !p.historyBoundaryConfirmed).length,
    estimatedVideoPages: videoMode === 'all_pages' && platformSelected.every(p => p.videoTotalCount !== null) ? platformSelected.reduce((sum, p) => sum + Math.ceil(p.videoTotalCount! / 40), 0) : null,
    dailyTheaterCount: selected.filter(p => p.revenueMode === 'daily').length,
    cumulativeTheaterCount: selected.filter(p => p.revenueMode === 'cumulative').length,
    revenueReadyCount: selected.filter(p => p.revenueAvailable).length,
    revenueBackfillCount: selected.filter(p => p.revenueAvailable && p.revenueState === 'backfill').length,
    revenueMissingCount: selected.filter(p => p.revenueAvailable && p.revenueState === 'missing').length,
    revenueCompleteCount: selected.filter(p => p.revenueAvailable && p.revenueState === 'complete').length,
    revenueUnavailableCount: selected.filter(p => !p.revenueAvailable).length,
    revenueSkipCount: selected.filter(p => p.revenueMode === 'daily' && !p.revenueUnupdated).length,
  };
}

export interface AccountCollectionStatusRow {
  key: CollectionCategoryKey;
  label: string;
  text: string;
  detail: string;
  tone: 'muted' | 'ready' | 'warning' | 'danger';
}
const collectedTime = (value?: string) => {
  if (!value) return '';
  const date = new Date(value);
  if (!Number.isFinite(date.getTime())) return '';
  return new Intl.DateTimeFormat('zh-CN', {timeZone:'Asia/Shanghai', month:'2-digit', day:'2-digit', hour:'2-digit', minute:'2-digit', hour12:false}).format(date);
};
/** Four categories share a stable order; saved timestamps describe observations, not completeness. */
export function collectionStatusRows(profile: AccountCollectionProfile, state: CollectionState | null): AccountCollectionStatusRow[] {
  const meta = state?.accounts.find(a => a.id === profile.account.id);
  const last = meta?.last_success;
  const detection = state?.optimization_detection?.accounts.find(a => a.account_id === profile.account.id);
  const detected = collectedTime(detection?.last_success || last?.optimization);
  const works = collectedTime(last?.works);
  const dailyText = profile.dailyGapState === 'complete' ? '完整至 '+(meta?.daily_through || '').slice(5)
    : profile.dailyGapState === 'initial_backfill' ? '历史待补齐'
    : profile.dailyGapState === 'missing_yesterday' ? '待补昨日'
    : profile.dailyGapState === 'missing_days' ? (profile.missingDates.length ? '缺 '+profile.missingDates.length+' 天' : '待核对缺口')
    : profile.dailyGapState === 'auth_expired' ? '账号待核对' : '尚未采集';
  const rows: AccountCollectionStatusRow[] = [
    {key:'daily_stats',label:'昨日数据',text:dailyText,detail:profile.dailyGapDesc,tone:profile.dailyGapState==='complete'?'ready':meta?'warning':'muted'},
    {key:'video_traffic',label:'视频流量',text:works?'上次 '+works:'尚未采集',detail:last?.works?'作品累计数据上次采集：'+last.works+'；不表示全部作品已更新。':'尚无作品累计数据的采集记录',tone:works?'muted':'warning'},
    {key:'optimization',label:'优化记录',text:detected?'检测 '+detected:'尚未检测',detail:detected?'最近成功检测：'+(detection?.last_success || last?.optimization):'尚无成功检测记录；没有优化记录不等于没有检测',tone:detected?'muted':'warning'},
    {key:'revenue',label:'剧场收益',text:profile.revenueStatusDesc,detail:[profile.revenueCollectorName,profile.revenueStatusDesc,last?.revenue?'上次成功：'+last.revenue:''].filter(Boolean).join(' · '),tone:profile.revenueState==='complete'?'ready':profile.revenueAvailable?'warning':'muted'},
  ];
  const latest = allJobItems(state?.job || null).filter(i => i.account_id === profile.account.id);
  for (const row of rows) {
    const item = latest.find(i => visibleCategory[i.category] === row.key);
    if(row.key!=='revenue' && getLoginState(profile.account.loginStatus)==='invalid' && (!item || item.status==='waiting')){row.text='登录待核对';row.detail='登录失效账号默认不选，可手动勾选；执行时重新读取小V猫本地登录状态，仍失效则跳过平台项。剧场收益不受登录影响。';row.tone='warning';continue;}
    // Configuration problems remain visible even if the last run failed for that reason.
    if (row.key === 'revenue' && !profile.revenueAvailable) continue;
    if (item?.status === 'running') {row.text='正在采集';row.tone='ready';}
    else if (item?.status === 'failed') {row.text='查询失败';row.tone='danger';}
    else if (item?.status === 'skipped' && row.key!=='revenue' && /登录/.test(item.message)) {row.text='登录失效，已跳过';row.tone='muted';}
    else if (item?.status === 'stopped') {row.text='已停止，待继续';row.tone='warning';}
    else if (item?.status === 'partial') {
      row.text=item.revenue_result?.pending_days && !item.revenue_result.failed_days?'来源待更新':'未完成，待续采';
      row.tone='warning';
    } else continue;
    row.detail = [row.detail,item.message].filter(Boolean).join('；');
  }
  return rows;
}
