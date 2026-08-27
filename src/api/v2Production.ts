import { v2Client } from './client';

export interface V2ProductionTaskRequest {
  source_id: string;
  account_name: string;
  drama_name: string;
  planned_publish_at: string;
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
  status: string;
  materials: Array<{ id: string; name: string; path: string; sequence_no: number | null; size_bytes: number; duration_seconds?: number; thumbnail_path?: string; scanned_at: string }>;
  pending_material_count: number;
  template: null | {
    id: string; version_no: number; status: 'queued' | 'running' | 'draft_ready' | 'error' | 'timeout';
    draft_name: string; draft_path: string; video_path: string; pairing_path: string;
    report_path: string; log_path: string; error_message: string; created_at: string; updated_at: string;
    draft_duration_seconds?: number; draft_duration_formatted?: string; video_size_bytes?: number;
  };
  videos: Array<{
    id: string;
    source_material_id: string;
    status: 'pending_generation';
    sequence_no: number | null;
    name: string;
    size_bytes: number;
    draft_path: string;
    output_path: string;
  }>;
}

export function listV2ProductionTasks(): Promise<{ items: V2ProductionTaskListItem[] }> {
  return v2Client.get('/api/v2/production-tasks');
}

export interface V2ScanResult {
  task_id: string;
  directory: string;
  discovered: number;
  items: Array<{ name: string; path: string; sequence_no: number; md5: string; size_bytes: number }>;
}

export function createV2ProductionTask(payload: V2ProductionTaskRequest): Promise<V2ProductionTask> {
  return v2Client.post('/api/v2/production-tasks', payload);
}

export function scanV2ProductionTask(taskId: string): Promise<V2ScanResult> {
  return v2Client.post(`/api/v2/production-tasks/${taskId}/scan`);
}

export function queueV2Template(taskId: string, regenerate = false): Promise<{ id: string; version_no: number; draft_name: string; status: string }> {
  return v2Client.post(`/api/v2/production-tasks/${taskId}/template`, { regenerate });
}
