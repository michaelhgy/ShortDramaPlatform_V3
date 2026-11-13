import type { AnalyticsAccountDaily } from '../api/analyticsDataBase';

export interface AccountDailySummary {
  date: string | null;
  targetDate: string;
  status: 'yesterday' | 'previous' | 'missing';
  follows: number | null;
  views: number | null;
  hearts: number | null;
  comments: number | null;
}

/** One complete account-day fact; never mix dates, sum a range, or treat missing as zero. */
export function accountDailySummary(rows: AnalyticsAccountDaily[], accountId: string, uid: string | undefined, yesterday: string): AccountDailySummary {
  const number = (value: unknown, signed = false): value is number =>
    typeof value === 'number' && Number.isFinite(value) && (signed || value >= 0);
  const row = rows.filter(item =>
    (item.account_id === accountId || (!!uid && item.uid === uid))
    && ['record', 'confirmed_zero', 'zero', 'cached_only'].includes(item.data_state)
    && /^\d{4}-\d{2}-\d{2}$/.test(item.stat_date) && item.stat_date <= yesterday
    && number(item.fans_net, true) && number(item.view) && number(item.like_count) && number(item.comment_count))
    .sort((a, b) => b.stat_date.localeCompare(a.stat_date)
      || (b.fetched_at || '').localeCompare(a.fetched_at || '') || (b.id || '').localeCompare(a.id || ''))[0];
  return {
    date: row?.stat_date || null, targetDate: yesterday,
    status: !row ? 'missing' : row.stat_date === yesterday ? 'yesterday' : 'previous',
    follows: row ? row.fans_net : null, views: row ? row.view : null,
    hearts: row ? row.like_count : null, comments: row ? row.comment_count : null,
  };
}
