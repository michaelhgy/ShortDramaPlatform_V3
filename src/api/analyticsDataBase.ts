import { v2Client } from './client';

export type AnalyticsSourceKind = 'simulation_ui' | 'all';

export type AnalyticsVideoAccount = {
  video_total?: number | null;
  id: string;
  uid: string;
  account_id: string;
  account_name: string;
  platform: string;
  login_status: string;
  fans_total: number;
  group_name: string;
  tags_json: string;
  snapshot_date: string;
  source_kind: string;
  data_state: string;
  freshness_state: string;
  fetched_at: string;
  payload_json: string;
};

export type AnalyticsAccountDaily = {
  id: string;
  uid: string;
  account_id: string;
  stat_date: string;
  view: number;
  fans_total: number;
  fans_add: number;
  fans_net: number;
  fans_reduce: number;
  like_count: number;
  favorite_count: number;
  comment_count: number;
  forward_count: number;
  source_kind: string;
  data_state: string;
  freshness_state: string;
  collection_run_id: string;
  fetched_at: string;
  payload_json: string;
};

export type AnalyticsVideoPost = {
  cover_url?: string;
  video_url?: string;
  video_duration?: number | null;
  id: string;
  post_id: string;
  uid: string;
  account_id: string;
  account_name: string;
  platform: string;
  post_time: string;
  title: string;
  description: string;
  cover_present: number;
  url_present: number;
  post_type: string;
  publish_status: string;
  timing: string;
  view: number;
  like_count: number;
  comment_count: number;
  forward_count: number;
  love_count: number;
  fans_add: number;
  full_view: number;
  view_time: number;
  snapshot_date: string;
  source_kind: string;
  data_state: string;
  freshness_state: string;
  collection_run_id: string;
  fetched_at: string;
  payload_json: string;
};

export type AnalyticsPostDaily = {
  id: string;
  post_id: string;
  uid: string;
  account_id: string;
  stat_date: string;
  view: number;
  like_count: number;
  comment_count: number;
  forward_count: number;
  favorite_count: number;
  fans_add: number;
  metric_grain: string;
  source_kind: string;
  data_state: string;
  freshness_state: string;
  collection_run_id: string;
  fetched_at: string;
  payload_json: string;
};

export type AnalyticsDiagnostic = {
  id: string;
  uid: string;
  account_id: string;
  account_name: string;
  verified: number | null;
  abnormal: number | null;
  video_status: string;
  heat_status: string;
  abnormal_post_count: number;
  last_verify_time: string;
  snapshot_date: string;
  source_kind: string;
  data_state: string;
  freshness_state: string;
  fetched_at: string;
  payload_json: string;
};

export type AnalyticsPunishment = {
  id: string;
  uid: string;
  account_id: string;
  post_id_or_export_id: string;
  title: string;
  publish_time: string;
  punish_state: string;
  snapshot_date: string;
  source_kind: string;
  data_state: string;
  freshness_state: string;
  fetched_at: string;
  payload_json: string;
};

export type AnalyticsRevenueSource = {
  id: string;
  theater_id: string;
  adapter_key: string;
  query_url: string;
  query_mode: string;
  date_precision: string;
  supports_detail: number;
  requires_account_id: number;
  requires_date: number;
  adapter_status: string;
  last_checked_at: string;
  notes: string;
};

export type AnalyticsRevenuePeriod = {
  id: string;
  account_id: string;
  theater_id: string;
  period_label: string;
  period_start: string;
  period_end: string;
  period_type: string;
  date_precision: string;
  amount: string | null;
  currency: string;
  data_state: string;
  freshness_state: string;
  settlement_state: string;
  include_in_analysis: number;
  source_kind: string;
  source_attempt_id: string;
  collection_run_id: string;
  collected_at: string;
  raw_result_json: string;
};

export type AnalyticsRevenueDetail = {
  id: string;
  account_id: string;
  theater_id: string;
  detail_date: string;
  source_video_id: string;
  source_drama_name: string;
  video_views: number;
  drama_views: number;
  gross_revenue: string | null;
  source_rank: number;
  matched_drama_id: string;
  match_status: string;
  data_state: string;
  freshness_state: string;
  include_in_analysis: number;
  source_kind: string;
  source_attempt_id: string;
  collection_run_id: string;
  collected_at: string;
  raw_result_json: string;
};

export type AnalyticsCollectionRun = {
  id: string;
  domain: string;
  source_system: string;
  acquisition_layer: string;
  storage_layer?: string;
  requested_start_date: string;
  requested_end_date: string;
  trigger_source: string;
  refresh_triggered: number;
  source_captured_at: string;
  status: string;
  created_at: string;
  finished_at: string;
  coverage: Record<string, number>;
};

export type AnalyticsCoverage = {
  source_kind: string;
  data_state: string;
  include_in_analysis: number;
  row_count: number;
  min_period_start?: string;
  max_period_end?: string;
  min_detail_date?: string;
  max_detail_date?: string;
};

export type AnalyticsDataBase = {
  schema: string;
  source_kind: string;
  counts: Record<string, number>;
  runs: AnalyticsCollectionRun[];
  revenue_source_inventory: AnalyticsRevenueSource[];
  revenue_period_coverage: AnalyticsCoverage[];
  revenue_detail_coverage: AnalyticsCoverage[];
  video_account_daily: AnalyticsAccountDaily[];
  video_accounts: AnalyticsVideoAccount[];
  video_posts: AnalyticsVideoPost[];
  video_post_daily: AnalyticsPostDaily[];
  video_account_diagnostics: AnalyticsDiagnostic[];
  video_post_punishments: AnalyticsPunishment[];
  revenue_account_periods: AnalyticsRevenuePeriod[];
  revenue_details: AnalyticsRevenueDetail[];
  policy: {
    page_read_triggers_refresh: boolean;
    legacy_revenue_included: boolean;
    cached_video_freshness: string;
  };
};

export function loadAnalyticsDataBase(options: {
  sourceKind?: AnalyticsSourceKind;
  startDate?: string;
  endDate?: string;
} = {}): Promise<AnalyticsDataBase> {
  const params: Record<string, string> = {};
  if (options.sourceKind && options.sourceKind !== 'all') params.source_kind = options.sourceKind;
  if (options.startDate) params.start_date = options.startDate;
  if (options.endDate) params.end_date = options.endDate;
  return v2Client.get('/api/v3/analytics-data-base', params);
}
