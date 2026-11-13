import { v2Client } from './client';

export type AccountDataSnapshot = {
  id: string;
  run_id: string;
  account_id: string;
  uid: string;
  platform: string;
  data_kind: string;
  collection_day: string;
  fetched_at: string;
  status: 'success' | 'failed' | 'unavailable';
  data_state: 'record' | 'no_daily_record' | 'unavailable' | 'refresh_failed' | 'refresh_precheck_failed' | 'query_failed' | 'legacy_unknown';
  refresh_status: 'success' | 'failed' | 'not_attempted' | 'not_confirmed' | 'legacy_unknown';
  refresh_result: unknown;
  payload: unknown;
  error_message: string;
  account_name?: string;
};

export type AccountDataOverview = {
  collection_day: string;
  start_date?: string;
  end_date?: string;
  accounts: Array<{ id: string; nickname: string; uid: string; status: string }>;
  snapshots: AccountDataSnapshot[];
  post_snapshots: AccountPostSnapshot[];
  latest_run: { id: string; status: string; collection_day: string; requested_start_date: string; requested_end_date: string; started_at: string; finished_at: string; error_message: string } | null;
  active_run: { id: string; status: string; collection_day: string } | null;
  policy: { automatic_enabled: boolean; same_day_success_is_reused: boolean; platform_refresh_is_never_triggered_by_page_read: boolean };
};

export type AccountPostSnapshot = {
  id: string;
  account_id: string;
  uid: string;
  account_name: string;
  platform: string;
  collection_day: string;
  post_id: string;
  post_time: string;
  title: string;
  post_type: string;
  publish_status: string;
  data_state: 'record' | 'no_daily_record' | 'failed' | 'unknown';
  metric_grain: 'daily' | 'snapshot' | 'unknown';
  source_kind: string;
  fetched_at: string;
  payload: Record<string, unknown>;
  error_message: string;
};

export type AccountDataRefreshResult = { run_id: string; status: string; collection_day: string; account_count: number; message?: string };

export function loadAccountDataOverview(date?: string, endDate?: string): Promise<AccountDataOverview> {
  return v2Client.get('/api/v2/account-data', date && endDate
    ? { start_date: date, end_date: endDate }
    : date ? { date } : undefined);
}

export function refreshAccountData(accountIds?: string[], force = false, startDate?: string, endDate?: string): Promise<AccountDataRefreshResult> {
  return v2Client.post('/api/v2/account-data/refresh', { account_ids: accountIds, force, start_date: startDate, end_date: endDate });
}
