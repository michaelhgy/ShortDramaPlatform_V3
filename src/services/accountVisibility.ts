import type { OperationsDashboardData } from '../api/operationsDashboard';

/** Selection eligibility is separate from historical reporting. */
export function isAvailableAccountStatus(status?: string): boolean {
  return !['封禁', '封号', '注销', '停用'].includes(status || '');
}

export type AccountDisplayScope = 'all' | 'current' | 'paused' | 'cancelled';
export const ACCOUNT_DISPLAY_SCOPES: ReadonlyArray<{value: AccountDisplayScope; label: string}> = [
  {value: 'all', label: '全部状态'}, {value: 'current', label: '未停用、未注销'},
  {value: 'paused', label: '停用'}, {value: 'cancelled', label: '注销'},
];
export function matchesAccountScope(status: string | undefined, scope: AccountDisplayScope): boolean {
  if (scope === 'all') return true;
  if (scope === 'paused') return status === '停用';
  if (scope === 'cancelled') return status === '注销';
  return !['停用', '注销', 'disabled'].includes(status || '');
}

/** Apply a page's explicit range to every metric and detail; all history is the default. */
export function visibleOperationsData(data: OperationsDashboardData, scope: AccountDisplayScope = 'all'): OperationsDashboardData {
  if (scope === 'all') return data;
  const accounts = data.accounts.filter(account => matchesAccountScope(account.status, scope));
  const ids = new Set(accounts.map(account => account.id));
  const uids = new Set(accounts.map(account => account.channel_id).filter(Boolean));
  const visible = (row: { account_id?: string; uid?: string }) => row.account_id ? ids.has(row.account_id) : uids.has(row.uid || '');
  const daily = data.video_account_daily.filter(visible);
  const revenue = data.revenue_account_periods.filter(visible);
  const risks = data.video_post_punishments.filter(visible);
  return { ...data, accounts,
    work_history: data.work_history?.filter(visible), pending_optimizations: data.pending_optimizations?.filter(visible),
    publication_history: data.publication_history?.filter(visible),
    video_accounts: data.video_accounts.filter(visible), video_account_daily: daily,
    account_daily_latest: data.account_daily_latest?.filter(visible),
    video_posts: data.video_posts.filter(visible), video_post_punishments: risks,
    revenue_account_periods: revenue,
    revenue_rating: data.revenue_rating && { periods: data.revenue_rating.periods.filter(visible), queries: data.revenue_rating.queries.filter(visible) },
    coverage: {...data.coverage, account_days: daily.length,
      failed_account_days: daily.filter(row => row.data_state === 'failed').length,
      failed_revenue_periods: revenue.filter(row => row.data_state === 'failed').length,
      unclassified_risks: risks.filter(row => !row.payload_json.includes('simplifiedReason')).length},
  };
}
