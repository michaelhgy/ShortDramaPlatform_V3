import type { OptimizationAnalysisConfiguration } from '../types/optimizationNotices';
import { ApiClient, v2Client } from './client';
import type { AnalyticsVideoAccount, AnalyticsAccountDaily, AnalyticsVideoPost, AnalyticsPunishment, AnalyticsRevenuePeriod } from './analyticsDataBase';

export interface RevenueQueryResult {
  id: string; account_id: string; theater_id: string; revenue_date: string;
  collection_status: string; collected_at: string; error_message: string;
  adapter_key: string; data_kind: string; period_type: string;
}

export interface PublicationHistory {
  id: string; uid: string; account_id: string; post_id: string; publish_time: string;
  task_state?: string; publication_state: string; match_state: string; payload_json: string;
  software?: boolean; identity_state?: string;
  optimization_state: 'optimized' | 'not_detected' | 'unknown';
  optimization: null | { analysis: string; platform_state: string; first_seen_at: string };
}
export interface OperationsCollection {
  finished_at: string; accounts: number; post_rows: number;
  publications: Record<string, number>; errors: Array<{ uid: string; stage: string; message: string }>;
}

export interface OperationsDashboardData {
  optimization_analysis_configuration?:OptimizationAnalysisConfiguration;
  schema: string;
  publication_history?: PublicationHistory[];
  work_history?: PublicationHistory[];
  pending_optimizations?: PendingOptimization[];
  optimization_action_settings?: OptimizationActionSettings;
  optimization_action_log?: OptimizationActionLog[];
  collection?: OperationsCollection | null;
  today: string;
  latest_date: string;
  accounts: Array<{ id: string; nickname: string; channel_id: string; theater_id: string; theater_name: string; status: string; notes: string; avatar_url?: string; login_status?: string; login_checked_at?: string }>;
  dramas?: Array<{ id: string; name: string; cover_url: string }>;
  theaters: Array<{ id: string; name: string; status: string }>;
  video_accounts: AnalyticsVideoAccount[];
  video_account_daily: AnalyticsAccountDaily[];
  /** Latest usable complete day per account, retained separately from failed report snapshots. */
  account_daily_latest?: AnalyticsAccountDaily[];
  video_posts: AnalyticsVideoPost[];
  video_post_punishments: AnalyticsPunishment[];
  revenue_account_periods: AnalyticsRevenuePeriod[];
  revenue_rating?: { periods: AnalyticsRevenuePeriod[]; queries: RevenueQueryResult[] };
  coverage: { account_days: number; failed_account_days: number; failed_revenue_periods: number; unclassified_risks: number };
}

export const loadOperationsDashboard = (): Promise<OperationsDashboardData> => v2Client.get('/api/v3/operations-dashboard');

export const collectOperationsDashboard = (): Promise<OperationsCollection> => new ApiClient({ timeoutMs: 1800000 }).post('/api/v3/operations-dashboard/collect');
export type CollectionCategory = 'profile' | 'daily' | 'works' | 'optimization' | 'revenue';
/** Only advertise after the collector implements validation, persistence and retry semantics. */
export interface CollectionCapabilities {
  version: 1;
  daily_force_range?: boolean;
  daily_reset_online?: boolean;
  works_publication_range?: boolean;
  optimization_detection?: boolean;
  revenue?: boolean;
}
export interface CollectionScope {
  daily?: {mode: 'fill_missing' | 'force_range' | 'reset_online'; start_date?: string; end_date?: string};
  works?: {mode: 'all' | 'published_range'; start_date?: string; end_date?: string};
  revenue?: {mode: 'routine'};
}
export interface CollectionAccount {
  id: string; uid: string; name: string; available: boolean; unavailable_reason: string;
  login_status?:string;login_checked_at?:string;
  optimization_due?: boolean;
  platform_available?: boolean;
  business_status?: string;
  revenue?: {available: boolean; mode: 'daily' | 'cumulative' | 'unknown'; state: 'backfill' | 'missing' | 'complete' | 'unconfigured' | 'disabled'; collector_name: string; message: string; missing_days?: number | null; last_success?: string};
  last_success: Partial<Record<CollectionCategory, string>>; daily_through?: string; daily_boundary?: string; daily_missing: number; daily_state?: string; daily_missing_dates?: string[];
  profile_total?: {postCount: number | null; fans: number | null}; profile_source_time?: string;
}
export type CollectionItemStatus = 'waiting' | 'running' | 'success' | 'skipped' | 'partial' | 'failed' | 'stopped';
export interface CollectionJob {
  source?: 'manual'|'automatic'|'retry'|'unknown'; parent_job_id?: string;
  id: string; state: 'running' | 'stopping' | 'completed' | 'partial' | 'paused' | 'stopped' | 'failed';
  started_at: string; finished_at: string; current_item: string;
  options: {platform_account_ids?: string[]; force_optimization?: boolean; page_interval_seconds: number; works_cooldown_hours: number; force_works: boolean; scope_version?: 1; scope?: CollectionScope};
  items: Array<{id: string; account_id: string; uid: string; account_name: string; category: CollectionCategory; status: CollectionItemStatus; message: string; updated_at: string; started_at?: string; finished_at?: string; events_truncated?: boolean; revenue_result?: {mode?: 'daily'|'cumulative'; collector_id?: string; collector_name?: string; saved_amount?: string; source_amount?: string|null; source_period?: string; query_start?: string; query_end?: string; pending_days: number; failed_days: number; history_pending: boolean; empty_days: number; saved_days: number; skipped_days: number}}>;
  retained_items?: CollectionJob['items'];
  events: Array<{time: string; account_id?: string; account_name: string; category: CollectionCategory; message: string}>;
}
export interface OptimizationDetectionSettings {
  enabled: boolean; min_minutes: number; max_minutes: number;
}
export interface OptimizationDetectionState extends OptimizationDetectionSettings {
  paused_reason: string;
  accounts: Array<{uid: string; account_id: string; next_due: number; requested_at: number; last_attempt: string; last_success: string; last_error: string}>;
}
export interface CollectionRecordSummary {job_id:string;source:string;started_at:string;item:CollectionJob['items'][number]}
export interface CollectionRecord extends CollectionRecordSummary {parent_job_id:string;finished_at:string;options:CollectionJob['options'];events:CollectionJob['events']}
export const loadCollectionRecords=(accountId:string,category:CollectionCategory,offset=0):Promise<{records:CollectionRecord[];has_more:boolean}>=>v2Client.get('/api/v3/operations-dashboard/collection/records?'+new URLSearchParams({account_id:accountId,category,offset:String(offset)}));
export interface CollectionState {record_summaries?:CollectionRecordSummary[];optimization_detection?: OptimizationDetectionState; job: CollectionJob | null; accounts: CollectionAccount[]; page_interval_seconds: number; yesterday: string; capabilities?: CollectionCapabilities}
export interface CollectionOptions {platform_account_ids?: string[]; force_optimization?: boolean; account_ids: string[]; categories: CollectionCategory[]; page_interval_seconds: number; works_cooldown_hours: number; force_works: boolean; scope_version?: 1; scope?: CollectionScope}
export const loadCollectionState = (): Promise<CollectionState> => v2Client.get('/api/v3/operations-dashboard/collection');
export const startCollection = (options: CollectionOptions): Promise<{job: CollectionJob; reused: boolean; message?: string}> => v2Client.post('/api/v3/operations-dashboard/collection/start', options);
export const retryCollection = (accountIds?: string[], jobId?:string, categories?:CollectionCategory[]): Promise<{job: CollectionJob; reused: boolean}> => v2Client.post('/api/v3/operations-dashboard/collection/retry', {...(accountIds?{account_ids:accountIds}:{}),...(jobId?{job_id:jobId}:{}),...(categories?{categories}: {})});
export const stopCollection = (jobId: string): Promise<{job: CollectionJob}> => v2Client.post('/api/v3/operations-dashboard/collection/stop', {job_id: jobId});

export const saveOptimizationDetection = (settings: OptimizationDetectionSettings): Promise<{optimization_detection: OptimizationDetectionState}> => v2Client.post('/api/v3/operations-dashboard/collection/optimization/settings', settings);

export const refreshCollectionLogins=():Promise<{state:CollectionState;message:string}>=>v2Client.post('/api/v3/operations-dashboard/collection/logins/refresh',{});

export interface PendingOptimization {
  id: string; uid: string; account_id: string; publish_time: string;
  export_id: string; match_state: string; analysis: string;
}
export interface OptimizationActionSettings {
  enabled: boolean; action: 'hide' | 'delete'; scope: 'all' | 'software';
  min_play_count: number | null; exclude_sticky: boolean; post_publish_hours: number;
}
export interface OptimizationActionLog {
  uid: string; post_id: string; action: string; state: string; message: string; at: string; views: number;
  account_name?: string; title?: string; publish_time?: string; analysis?: string;
}
export const saveOptimizationActions = (settings: OptimizationActionSettings): Promise<{settings: OptimizationActionSettings}> =>
  v2Client.post('/api/v3/operations-dashboard/optimization/actions/settings', settings);

export interface OptimizationActionRecords {
  records: OptimizationActionLog[]; total: number; page: number; page_size: number; page_count: number; snapshot: number;
}
export const loadOptimizationActionRecords = (page=1, snapshot?:number): Promise<OptimizationActionRecords> => {
  const query=new URLSearchParams({page:String(page),page_size:'10'});
  if(snapshot!==undefined) query.set('snapshot',String(snapshot));
  return v2Client.get('/api/v3/operations-dashboard/optimization/actions/records?'+query);
};

export interface OptimizationAnalysisGroup {key:string;analysis:string;variants:string[];record_count:number;account_count:number;last_seen_at:string}
export interface OptimizationAnalysisData {configuration:OptimizationAnalysisConfiguration;groups:OptimizationAnalysisGroup[]}
export const loadOptimizationAnalysis=():Promise<OptimizationAnalysisData>=>v2Client.get('/api/v3/operations-dashboard/optimization/analysis');
export const saveOptimizationAnalysis=(key:string,tag:string|null,expected_version:number):Promise<OptimizationAnalysisData>=>v2Client.post('/api/v3/operations-dashboard/optimization/analysis',{key,tag,expected_version});
