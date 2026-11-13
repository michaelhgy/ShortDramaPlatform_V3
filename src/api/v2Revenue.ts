import { v2Client } from './client';

export type V2RevenueSourceData = {
  rows: Array<{ id: string; revenue_date: string; account_id: string; account_nickname: string; theater_id: string; theater_name: string; amount: string; quality: 'direct'; updated_at: string }>;
  accounts: Array<{ id: string; nickname: string; status: string; theater_id: string | null }>;
  theaters: Array<{ id: string; name: string; status: string }>;
};

export type V2RevenueCollectionLog = {
  id: string; account_name: string; theater_name: string; revenue_date: string;
  collection_status: 'success' | 'no_data' | 'pending' | 'failed'; amount: string | null;
  error_message: string; collected_at: string;
};
export type V2RevenueCollectionRun = {
  id: string; status: 'queued' | 'running' | 'completed' | 'failed' | 'stopped'; total_units: number; completed_units: number;
  success_units: number; no_data_units: number; failed_units: number; current_theater: string; current_account: string;
  error_message: string; created_at: string; started_at: string; finished_at: string;
};

export type V2DailyAccountRevenueSummary = {
  revenue_date: string;
  items: Array<{ account_id: string; amount: string | null; collection_status: 'success' | 'no_data' | 'pending' | 'failed' | 'uncollected' }>;
};

/** Canonical Qingning fact: one account + one video ID + one data date. */
export type V2RevenueVideoDetail = {
  id: string; revenue_date: string; account_id: string; account_name: string;
  theater_id: string; theater_name: string; source_video_id: string;
  source_drama_name: string; video_views: number; drama_views: number;
  gross_revenue: string; source_rank: number; matched_drama_id: string | null;
  matched_drama_name: string; match_status: 'matched' | 'unmatched'; updated_at: string;
  first_observed_date?: string; linked_task_id?: string | null; linked_video_task_id?: string | null;
  linked_material_id?: string | null; linked_note?: string | null;
  linked_material_name?: string | null;
  inferred_task_id?: string | null; inferred_actual_release_time?: string | null;
  inferred_release_province?: string | null; inferred_release_city?: string | null;
  inferred_release_district?: string | null; inferred_release_detail_address?: string | null;
  linked_actual_release_time?: string | null; linked_release_province?: string | null;
  linked_release_city?: string | null; linked_release_district?: string | null; linked_release_detail_address?: string | null;
};

export type V2RevenueVideoDetailsResponse = {
  items: V2RevenueVideoDetail[]; start_date: string; end_date: string;
  truncated: boolean; limit: number;
};

export type V2RevenueVideoCandidate = {
  production_task_id: string; production_video_task_id: string; source_material_id: string;
  file_name: string; original_name: string; duration_seconds: number; thumbnail_url: string; media_url: string;
  planned_publish_at: string; actual_release_time: string;
};

export function loadV2RevenueSourceData(): Promise<V2RevenueSourceData> {
  return v2Client.get('/api/v2/revenue/source-data');
}

export function loadV2DailyAccountRevenueSummary(date: string): Promise<V2DailyAccountRevenueSummary> {
  return v2Client.get(`/api/v2/revenue/daily-account-summary?${new URLSearchParams({ date }).toString()}`);
}

export function loadV2RevenueCollectionLogs(): Promise<{ items: V2RevenueCollectionLog[] }> {
  return v2Client.get('/api/v2/revenue/collection-logs?limit=2000');
}

export function loadV2RevenueVideoDetails(startDate: string, endDate: string, accountId?: string): Promise<V2RevenueVideoDetailsResponse> {
  const query = new URLSearchParams({ start_date: startDate, end_date: endDate, limit: '12000' });
  if (accountId) query.set('account_id', accountId);
  return v2Client.get(`/api/v2/revenue/video-details?${query.toString()}`);
}

export function loadV2RevenueVideoCandidates(accountId: string, videoId: string): Promise<{ platform_video: Record<string, string>; candidates: V2RevenueVideoCandidate[] }> {
  return v2Client.get(`/api/v2/revenue/video-candidates?${new URLSearchParams({ account_id: accountId, video_id: videoId }).toString()}`);
}

export function confirmV2RevenueVideoLink(payload: { account_id: string; video_id: string; production_task_id: string; production_video_task_id: string; source_material_id: string; note?: string }): Promise<{ linked: boolean }> {
  return v2Client.post('/api/v2/revenue/video-links', payload);
}

export function collectV2QingningRevenue(start_date: string, end_date: string, theaters?: string[], account_ids?: string[]): Promise<{ run_id: string; status: string; total_units: number }> {
  return v2Client.post('/api/v2/revenue/collect', { start_date, end_date, theaters, account_ids });
}

export function loadV2RevenueCollectionRun(runId: string): Promise<V2RevenueCollectionRun> {
  return v2Client.get(`/api/v2/revenue/collection-runs/${runId}`);
}
