import { v2Client } from './client';

export interface V2TheaterRecord {
  id: string;
  name: string;
  default_commission_rate: number;
  default_tax_rate: number;
  status: '启用' | '停用';
  revenue_collector_ids?: string[];
  revenue_collectors_confirmed?: boolean;
  accounts_count: number;
  sub_theaters_count: number;
  dramas_count: number;
}

export interface V2AccountRecord {
  avatar_url?: string;
  id: string;
  nickname: string;
  channel_id: string;
  theater_id: string;
  theater_name: string;
  sub_theater_name: string;
  status: '正常' | '观察' | '限流' | '二限' | '实名' | '封禁' | '停用' | '注销';
  revenue_collector_id?: string;
  reporting_date?: string;
  registration_date?: string;
  notes: string;
}

export interface V2SubTheaterRecord {
  id: string;
  theater_id: string;
  theater_name: string;
  name: string;
  commission_rate: number;
  is_commission_overridden: 0 | 1;
  status: '启用' | '停用';
  bound_accounts_count: number;
}
export interface V2DramaRecord {
  official_total_episodes?: number;
  episode_count_conflict?: boolean;
  platform_sources?: import('./dramaCatalog').PlatformDrama[];
  id: string; current_name: string; history_names: string[]; theater_id: string; theater_name: string; created_at: string;
  production_count: number; last_scheduled_at: string; active_production_count: number;
}

export interface CreateV2TheaterPayload {
  name: string;
  default_commission_rate: number;
  default_tax_rate: number;
  status: '启用' | '停用';
  revenue_collector_ids?: string[];
}

export interface CreateV2AccountPayload {
  nickname: string;
  channel_id: string;
  theater_id: string;
  sub_theater_name: string;
  status: V2AccountRecord['status'];
  revenue_collector_id?: string;
  reporting_date?: string;
  registration_date?: string;
  notes: string;
}

export function getV2Theaters(): Promise<{ items: V2TheaterRecord[] }> {
  return v2Client.get('/api/v2/theaters');
}

export function getV2Accounts(): Promise<{ items: V2AccountRecord[] }> {
  return v2Client.get('/api/v2/accounts');
}
export function getV2Account(id: string): Promise<V2AccountRecord> { return v2Client.get(`/api/v2/accounts/${id}`); }

export function getV2SubTheaters(): Promise<{ items: V2SubTheaterRecord[] }> {
  return v2Client.get('/api/v2/sub-theaters');
}
export function getV2Dramas(): Promise<{ items: V2DramaRecord[] }> { return v2Client.get('/api/v2/dramas'); }
export function getV2Drama(id: string): Promise<V2DramaRecord> { return v2Client.get(`/api/v2/dramas/${id}`); }
export function createV2Drama(payload: { current_name: string; history_names: string[]; theater_id: string }): Promise<V2DramaRecord> { return v2Client.post('/api/v2/dramas', payload); }
export function createV2DramasBatch(payload: { current_name: string; history_names: string[]; theater_id: string }[]): Promise<{ items: V2DramaRecord[]; created_count: number; skipped_names: string[] }> { return v2Client.post('/api/v2/dramas/batch', { items: payload }); }
export function updateV2Drama(id: string, payload: { current_name: string; history_names: string[] }): Promise<V2DramaRecord> { return v2Client.patch(`/api/v2/dramas/${id}`, payload); }
export function deleteV2Drama(id: string): Promise<{ deleted: true }> { return v2Client.delete(`/api/v2/dramas/${id}`); }
export function uploadV2DramaCover(id: string, payload: { filename: string; content_base64: string; kind?: 'drama' | 'sheep' }): Promise<{ drama_id: string; file_path: string; filename: string }> {
  return v2Client.post(`/api/v2/dramas/${id}/cover`, payload);
}
export function createV2DramaProfile(id: string): Promise<{ drama_id: string; folder_path: string; master_folder_path: string; cover_folder_path: string }> {
  return v2Client.post(`/api/v2/dramas/${id}/profile`, {});
}
export function getV2DramaProfiles(): Promise<{ items: { drama_id: string; root_path: string; master_path: string; cover_path: string; updated_at: string; official_total_episodes?: number; episode_count_conflict?: boolean; platform_sources?: import('./dramaCatalog').PlatformDrama[]; master_files?: import('../assetsTypes').MasterVideoEpisodeFile[]; master_file_count?: number; master_total_size_gb?: number; downloaded_episode_count?: number; downloaded_episode_numbers?: number[]; downloaded_folder_path?: string }[] }> { return v2Client.get('/api/v2/drama-profiles'); }
export function openV2Folder(path: string): Promise<{ opened: boolean }> { return v2Client.post('/api/v2/open-folder', { path }); }
export function openV2File(path: string): Promise<{ opened: boolean }> { return v2Client.post('/api/v2/open-file', { path }); }
export function openV2ProductionResourceFolder(category: import('../assetsTypes').ResourceCategory): Promise<{ opened: boolean }> {
  return v2Client.post('/api/v2/production-resources/open-folder', { category });
}
export function getV2ProductionResources(): Promise<{ items: import('../assetsTypes').ProductionResourceItem[] }> { return v2Client.get('/api/v2/production-resources'); }
export interface V2Settings {
  data_drive: string;
  data_root_dir: string;
  drama_download_root: string;
  raw_material_retention_days: number;
  short_term_cleanup_hours: number;
  publish_presets: string[];
  publish_date_offset_days: number;
  jianying_executable: string;
  jianying_draft_root: string;
  jianying_user_data_root: string;
  template_timeout_min: number;
  final_generation_timeout_min: number;
  video_export_timeout_min: number;
  final_video_manual_check: boolean;
  final_raw_material_process: boolean;
  video_export_debug: boolean;
  revenue_auto_collection_enabled: boolean;
  revenue_auto_collection_times: string[];
  local_vision_ai_mode: 'compatibility' | 'quality' | 'disabled';
}
export function getV2Settings(): Promise<V2Settings> { return v2Client.get('/api/v2/settings'); }
export function updateV2Settings(payload: Partial<V2Settings>): Promise<V2Settings> { return v2Client.post('/api/v2/settings', payload); }
export interface DramaDownloadReadTaskState {
  status: 'idle' | 'queued' | 'running' | 'succeeded' | 'failed' | 'stopped';
  phase: 'idle' | 'read-task' | 'collect-links' | 'parse-download' | 'verify-download' | 'cleanup-task' | 'completed';
  current_step?: string;
  stop_requested?: boolean;
  error?: string;
  logs?: string[];
  stage_logs?: Record<string, string[]>;
  stage_states?: Record<string, 'pending' | 'running' | 'done' | 'failed'>;
  downloaded_episodes?: number[];
  verified_episodes?: number[];
  missing_video_episodes?: number[];
  resume_phase?: 'parse-download' | 'verify-download' | null;
  completed_task_count?: number;
  total_conflict?: boolean;
  cleanup_pending?: boolean;
  cleanup_state?: 'pending' | 'running' | 'failed' | 'done';
  cleanup_error?: string;
  completed_tasks?: Array<{task_label?: string; chat_name?: string; drama_name: string; verified_count?: number}>;
  theater_name?: string;
  task?: {
    chat_name: string;
    task_label: string;
    drama_name: string;
    label_position?: { x: number; y: number };
    card_position?: { x: number; y: number };
  };
  tasks?: Array<{
    chat_name: string;
    task_label: string;
    drama_name: string;
    label_position?: { x: number; y: number };
    card_position?: { x: number; y: number };
  }>;
  task_count?: number;
  current_task_index?: number;
  collected_count?: number;
  collected_episodes?: number[];
  missing_link_episodes?: number[];
  parse_failed_episodes?: number[];
  repair_episodes?: number[];
  parsed_episodes?: number[];
  link_episode_map?: Array<{ drama_name: string; episode: number; episode_label: string; share_url: string }>;
  parse_records?: Record<string, {
    status?: string;
    expected_episode?: number;
    returned_episode?: number;
    title?: string;
    file?: string;
    error?: string;
  }>;
  manual_cleanup_required?: boolean;
  manual_cleanup_message?: string;
  table_path?: string;
  link_manifest_path?: string;
  link_record_count?: number;
  result_path?: string;
  download_root?: string;
  verified_count?: number;
  downloaded_file_count?: number;
  expected_count?: number;
  complete?: boolean;
  created_at?: string;
  updated_at?: string;
}
export function getDramaDownloadReadTask(): Promise<DramaDownloadReadTaskState> {
  return v2Client.get('/api/v2/drama-download/read-task');
}
export interface DramaDownloadLinkRecord {
  drama_name: string;
  episode: number;
  episode_label: string;
  share_url: string;
}
export function getDramaDownloadLinks(): Promise<{ schema_version: number; source: string; updated_at: string; table_path: string; manifest_path: string; records: DramaDownloadLinkRecord[] }> {
  return v2Client.get('/api/v2/drama-download/links');
}
export function startDramaDownloadReadTask(): Promise<DramaDownloadReadTaskState> {
  return v2Client.post('/api/v2/drama-download/read-task', {});
}
export function startDramaDownloadCollectLinks(count = 0): Promise<DramaDownloadReadTaskState> {
  return v2Client.post('/api/v2/drama-download/collect-links', { count });
}
export function startDramaDownloadPipeline(count = 0): Promise<DramaDownloadReadTaskState> {
  return v2Client.post('/api/v2/drama-download/start', { count });
}
export function stopDramaDownloadPipeline(): Promise<DramaDownloadReadTaskState> {
  return v2Client.post('/api/v2/drama-download/stop', {});
}
export interface LocalVisionAiStatus {
  ollamaFound: boolean;
  ollamaExecutable: string;
  installedModels: string[];
  supportedModels: Array<{ id: string; label: string; size: string; installed: boolean }>;
  download: { model: string; status: 'idle' | 'queued' | 'downloading' | 'completed' | 'error'; progress: string; error: string };
  error: string;
}
export function getLocalVisionAiStatus(): Promise<LocalVisionAiStatus> { return v2Client.get('/api/v2/local-vision-ai/status'); }
export function downloadLocalVisionAiModel(model: string): Promise<LocalVisionAiStatus> { return v2Client.post('/api/v2/local-vision-ai/download', { model }); }
export function getV2Drives(): Promise<{ items: string[] }> { return v2Client.get('/api/v2/drives'); }

export function createV2Theater(payload: CreateV2TheaterPayload): Promise<V2TheaterRecord> {
  return v2Client.post('/api/v2/theaters', payload);
}

export function updateV2Theater(id: string, payload: CreateV2TheaterPayload): Promise<V2TheaterRecord> {
  return v2Client.patch(`/api/v2/theaters/${id}`, payload);
}

export function deleteV2Theater(id: string): Promise<{ deleted: true }> {
  return v2Client.delete(`/api/v2/theaters/${id}`);
}

export function createV2TheatersBatch(payload: CreateV2TheaterPayload[]): Promise<{ items: V2TheaterRecord[]; created_count: number; skipped_names: string[] }> {
  return v2Client.post('/api/v2/theaters/batch', { items: payload });
}

export function createV2Account(payload: CreateV2AccountPayload): Promise<V2AccountRecord> {
  return v2Client.post('/api/v2/accounts', payload);
}

export function createV2AccountsBatch(payload: (CreateV2AccountPayload & { theater_name: string })[]): Promise<{ items: V2AccountRecord[]; created_count: number; skipped_names: string[] }> {
  return v2Client.post('/api/v2/accounts/batch', { items: payload });
}

export interface CreateV2SubTheaterPayload {
  theater_id: string;
  name: string;
  commission_rate: number;
  is_commission_overridden: boolean;
  status: '启用' | '停用';
}

export function createV2SubTheater(payload: CreateV2SubTheaterPayload): Promise<V2SubTheaterRecord> {
  return v2Client.post('/api/v2/sub-theaters', payload);
}

export function createV2SubTheatersBatch(payload: CreateV2SubTheaterPayload[]): Promise<{ items: V2SubTheaterRecord[]; created_count: number; skipped_names: string[] }> {
  return v2Client.post('/api/v2/sub-theaters/batch', { items: payload });
}

export function updateV2SubTheater(id: string, payload: CreateV2SubTheaterPayload): Promise<V2SubTheaterRecord> { return v2Client.patch(`/api/v2/sub-theaters/${id}`, payload); }
export function deleteV2SubTheater(id: string): Promise<{ deleted: true }> { return v2Client.delete(`/api/v2/sub-theaters/${id}`); }
export function updateV2Account(id: string, payload: Partial<CreateV2AccountPayload>): Promise<V2AccountRecord> { return v2Client.patch(`/api/v2/accounts/${id}`, payload); }
export function deleteV2Account(id: string): Promise<{ deleted: true }> { return v2Client.delete(`/api/v2/accounts/${id}`); }

export interface RevenueCollectorDefinition {
  id: string;
  name: string;
  aliases: string[];
  date_precision: string;
  notes: string;
  runtime_verified: boolean;
}

export function getV2RevenueCollectorDefinitions(): Promise<{ definitions: RevenueCollectorDefinition[] }> {
  return v2Client.get('/api/v2/revenue/collectors');
}
