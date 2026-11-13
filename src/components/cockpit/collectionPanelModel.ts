import type { CollectionCapabilities, CollectionCategory, CollectionJob, CollectionOptions, CollectionScope } from '../../api/operationsDashboard';

export type VisibleCategory = Exclude<CollectionCategory, 'profile'>;
export type CollectionEntry = 'routine' | 'works' | 'optimization';
export const categoryLabels: Record<CollectionCategory, string> = {
  daily: '账号日数据', works: '视频最新流量', optimization: '优化记录', revenue: '剧场收益', profile: '视频数 / 关注者数',
};
export function supports(capabilities: CollectionCapabilities | undefined, feature: 'daily_reset_online' | 'daily_force_range' | 'works_publication_range' | 'optimization_detection' | 'revenue') {
  return capabilities?.version === 1 && capabilities[feature] === true;
}
export function entryCategories(entry: CollectionEntry, capabilities?: CollectionCapabilities): VisibleCategory[] {
  return entry === 'works' ? ['works'] : entry === 'optimization' ? ['optimization']
    : supports(capabilities, 'revenue') ? ['daily', 'optimization', 'revenue'] : ['daily', 'optimization'];
}
export function validDateRange(start: string, end: string, latest: string) {
  const valid = (value: string) => /^\d{4}-\d{2}-\d{2}$/.test(value) && !Number.isNaN(Date.parse(value + 'T00:00:00Z')) && new Date(value + 'T00:00:00Z').toISOString().slice(0, 10) === value;
  return valid(start) && valid(end) && valid(latest) && start <= end && end <= latest;
}
export function recentPublicationRange(yesterday: string, days: number) {
  // The server supplies yesterday in its business timezone. Include today for current work totals.
  const end = new Date(yesterday + 'T00:00:00Z'); end.setUTCDate(end.getUTCDate() + 1);
  const start = new Date(end); start.setUTCDate(start.getUTCDate() - days + 1);
  return { start: start.toISOString().slice(0, 10), end: end.toISOString().slice(0, 10) };
}
export interface CollectionDraft {
  accountIds: string[];
  platformAccountIds?: string[];
  categories: VisibleCategory[];
  interval: string;
  cooldown: string;
  forceWorks: boolean;
  dailyMode: 'fill_missing' | 'force_range' | 'reset_online';
  dailyStart: string;
  dailyEnd: string;
  worksMode: 'all' | 'recent7' | 'recent30' | 'custom';
  worksStart: string;
  worksEnd: string;
  revenueMode: 'routine' | 'date_range';
  revenueStart: string;
  revenueEnd: string;
}
export function buildCollectionRequest(draft: CollectionDraft, yesterday: string, capabilities?: CollectionCapabilities): {options?: CollectionOptions; error?: string} {
  if (!draft.accountIds.length) return {error: '请至少选择一个可采集账号'};
  if (!draft.categories.length) return {error: '请至少选择一种采集内容'};
  const works = draft.categories.includes('works');
  const interval = Number(draft.interval), cooldown = Number(draft.cooldown);
  if (works && (!draft.interval.trim() || !Number.isFinite(interval) || interval < .1 || interval > 60 || !draft.cooldown.trim() || !Number.isFinite(cooldown) || cooldown < 0 || cooldown > 168)) return {error: '每页等待上限应为0.1～60秒，重复更新间隔应为0～168小时'};
  const scope: CollectionScope = {};
  if (draft.categories.includes('daily')) {
    if (draft.dailyMode === 'force_range') {
      if (!supports(capabilities, 'daily_force_range')) return {error: '账号日数据强制重取尚待后端接入，本次不能执行'};
      if (!validDateRange(draft.dailyStart, draft.dailyEnd, yesterday)) return {error: '请选择有效的日数据日期范围，最晚为昨天'};
    }
    if (draft.dailyMode === 'reset_online' && !supports(capabilities, 'daily_reset_online')) return {error: '账号每日数据在线重置尚待后端接入，本次不能执行'};
    scope.daily = draft.dailyMode === 'reset_online' ? {mode: 'reset_online'} : draft.dailyMode === 'force_range' ? {mode: 'force_range', start_date: draft.dailyStart, end_date: draft.dailyEnd} : {mode: 'fill_missing'};
  }
  if (works) {
    if (draft.worksMode === 'all') scope.works = {mode: 'all'};
    else {
      if (!supports(capabilities, 'works_publication_range')) return {error: '按作品发布时间截断翻页尚待后端接入，本次不能执行'};
      const range = draft.worksMode === 'custom' ? {start: draft.worksStart, end: draft.worksEnd} : recentPublicationRange(yesterday, draft.worksMode === 'recent7' ? 7 : 30);
      if (!validDateRange(range.start, range.end, recentPublicationRange(yesterday, 1).end)) return {error: '请选择有效的作品发布时间范围，最晚为今天'};
      scope.works = {mode: 'published_range', start_date: range.start, end_date: range.end};
    }
  }
  if (draft.categories.includes('revenue')) {
    if (!supports(capabilities, 'revenue')) return {error: '剧场收益尚待统一任务接口接入，本次不能执行'};
    if (draft.revenueMode !== 'routine') return {error: '收益日期由后台按历史和缺口自动安排，请使用自动补齐'};
    scope.revenue = {mode: 'routine'};
  }
  const categories: CollectionCategory[] = [...draft.categories];
  // Reuse daily totals; when the complete daily range is skipped, only read existing Xiao V totals.
  if (categories.includes('daily')) categories.push('profile');
  const options: CollectionOptions = {
    account_ids: [...new Set(draft.accountIds)], categories, page_interval_seconds: works ? interval : 2,
    works_cooldown_hours: works ? cooldown : 1, force_works: works && draft.forceWorks,
  };
  if (draft.platformAccountIds) options.platform_account_ids = draft.platformAccountIds.filter(id => draft.accountIds.includes(id));
  // Old backends must never silently receive an unsupported date restriction or force flag.
  if (capabilities?.version === 1) Object.assign(options, {scope_version: 1, scope});
  return {options};
}
export function accountProgress(job: CollectionJob) {
  const groups = new Map<string, {id: string; name: string; items: CollectionJob['items']; done: boolean; needsAttention: boolean}>();
  for (const item of job.items) {
    if (!groups.has(item.account_id)) groups.set(item.account_id, {id: item.account_id, name: item.account_name, items: [], done: false, needsAttention: false});
    groups.get(item.account_id)!.items.push(item);
  }
  return [...groups.values()].map(group => ({...group,
    done: group.items.every(item => ['success', 'skipped'].includes(item.status)),
    needsAttention: group.items.some(item => ['partial', 'failed', 'stopped'].includes(item.status)),
  }));
}
