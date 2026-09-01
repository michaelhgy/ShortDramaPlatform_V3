import { v2Client } from './client';

export interface V2ProductionTaskRequest {
  source_id: string;
  account_name: string;
  drama_name: string;
  planned_publish_at: string;
  release_status?: 'unregistered' | 'registered';
  actual_release_time?: string;
  release_province?: string;
  release_city?: string;
  release_district?: string;
  release_detail_address?: string;
  final_video_manual_check?: boolean;
}

export interface V2ProductionTask {
  id: string;
  source_id: string;
  paths: { root: string; materials: string; template: string; finals: string };
}

export interface V2ProductionTaskListItem extends V2ProductionTask {
  created_date: string;
  account_name: string;
  drama_name: string;
  planned_publish_at: string;
  release_status?: 'unregistered' | 'registered';
  actual_release_time?: string;
  release_province?: string;
  release_city?: string;
  release_district?: string;
  release_detail_address?: string;
  final_video_manual_check?: boolean;
  status: string;
  task_display_status?: string;
  template_display_status?: string;
  materials: Array<{ id: string; name: string; path: string; sequence_no: number | null; size_bytes: number; duration_seconds?: number; resolution?: string; thumbnail_path?: string; scanned_at: string; status?: string }>;
  pending_material_count: number;
  materials_count?: number;
  videos_count?: number;
  draft_count?: number;
  draft_queued_count?: number;
  draft_generating_count?: number;
  export_queued_count?: number;
  exporting_count?: number;
  exported_count?: number;
  error_count?: number;
  template: null | {
    id: string; version_no: number; status: 'queued' | 'running' | 'draft_ready' | 'error' | 'timeout';
    draft_name: string; draft_path: string; video_path: string; pairing_path: string;
    report_path: string; log_path: string; error_message: string; created_at: string; updated_at: string;
    draft_duration_seconds?: number; draft_duration_formatted?: string; video_size_bytes?: number;
    export_job_id?: string; export_attempt_id?: string; export_status?: string; export_error_message?: string;
    export_target_path?: string; export_duration_seconds?: number; export_duration_formatted?: string; export_file_size_bytes?: number;
    export_file_name?: string; video_duration_seconds?: number;
  };
  videos: Array<{
    id: string;
    source_material_id: string;
    status: string;
    error_message?: string;
    generation_started_at?: string;
    generation_finished_at?: string;
    sequence_no: number | null;
    name: string;
    original_name?: string;
    size_bytes: number;
    source_duration_seconds?: number;
    draft_path: string;
    output_path: string;
    output_exists?: boolean;
    output_size_bytes?: number;
    export_job_id?: string;
    export_attempt_id?: string;
    export_status?: string;
    export_job_status?: string;
    export_error_message?: string;
    export_started_at?: string;
    export_finished_at?: string;
    output_duration_seconds?: number;
    display_status?: string;
  }>;
}

export function openV2FinishedVideoDraft(videoId: string): Promise<{ accepted: boolean; video_id: string }> {
  return v2Client.post(`/api/v2/production-videos/${videoId}/open-draft`);
}
export function openV2TemplateDraft(taskId: string): Promise<{ accepted: boolean; task_id: string }> {
  return v2Client.post(`/api/v2/production-tasks/${taskId}/template/open-draft`);
}

export function listV2ProductionTasks(): Promise<{ items: V2ProductionTaskListItem[] }> {
  return v2Client.get('/api/v2/production-tasks');
}

export function listV2ProductionTaskSummaries(): Promise<{ items: V2ProductionTaskListItem[] }> {
  return v2Client.get('/api/v2/production-task-summaries');
}

export function getV2ProductionTaskDetails(taskId: string): Promise<V2ProductionTaskListItem> {
  return v2Client.get(`/api/v2/production-tasks/${taskId}/details`);
}

export interface V2ScanResult {
  task_id: string;
  directory: string;
  discovered: number;
  items: Array<{ name: string; path: string; sequence_no: number; md5: string; size_bytes: number; duration_seconds?: number }>;
}

export function createV2ProductionTask(payload: V2ProductionTaskRequest): Promise<V2ProductionTask> {
  return v2Client.post('/api/v2/production-tasks', payload);
}

export function scanV2ProductionTask(taskId: string): Promise<V2ScanResult> {
  return v2Client.post(`/api/v2/production-tasks/${taskId}/scan`);
}

export function updateV2TaskManualCheck(taskId: string, enabled: boolean): Promise<V2ProductionTaskListItem> {
  return v2Client.post(`/api/v2/production-tasks/${taskId}/manual-check`, { enabled });
}

export function queueV2Template(taskId: string, regenerate = false): Promise<{ id: string; version_no: number; draft_name: string; status: string }> {
  return v2Client.post(`/api/v2/production-tasks/${taskId}/template`, { regenerate });
}

export function submitV2FinishedVideos(taskId: string, sourceMaterialIds: string[]): Promise<{ task_id: string; items: Array<{ id: string; source_material_id: string; status: string }>; created_count: number }> {
  return v2Client.post(`/api/v2/production-tasks/${taskId}/videos/batch`, { source_material_ids: sourceMaterialIds });
}

export function registerV2Release(taskId: string, payload: { actual_release_time: string; province: string; city: string; district: string; detail_address: string }): Promise<{ id: string; release_status: string; actual_release_time: string }> {
  return v2Client.post(`/api/v2/production-tasks/${taskId}/release`, payload);
}

export interface V2ReleaseAddress { province: string; city: string; district: string; detail_address: string; use_count: number; last_used_at: string; }
export function listV2ReleaseAddresses(accountName: string): Promise<{ account: V2ReleaseAddress[]; public: V2ReleaseAddress[] }> {
  return v2Client.get(`/api/v2/release-addresses?account_name=${encodeURIComponent(accountName)}`);
}

export function revokeV2Release(taskId: string): Promise<{ id: string; release_status: string; actual_release_time: string }> {
  return v2Client.post(`/api/v2/production-tasks/${taskId}/release/revoke`, {});
}
export function previewV2Cleanup(taskId: string): Promise<import('../productionTypes').CleanupPreviewData> {
  return v2Client.get(`/api/v2/production-tasks/${taskId}/cleanup/preview`);
}
export function executeV2Cleanup(taskId: string): Promise<{ status: string; deleted: string[]; errors: string[] }> {
  return v2Client.post(`/api/v2/production-tasks/${taskId}/cleanup`);
}
