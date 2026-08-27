import { v2Client } from './client';

export interface V2TheaterRecord {
  id: string;
  name: string;
  default_commission_rate: number;
  default_tax_rate: number;
  status: '启用' | '停用';
  accounts_count: number;
  sub_theaters_count: number;
  dramas_count: number;
}

export interface V2AccountRecord {
  id: string;
  nickname: string;
  channel_id: string;
  theater_id: string;
  theater_name: string;
  sub_theater_name: string;
  status: '正常' | '观察' | '限流' | '二限' | '实名' | '封禁' | '停用';
  reporting_date: string;
  registration_date: string;
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
export interface V2DramaRecord { id: string; current_name: string; history_names: string[]; theater_id: string; theater_name: string; created_at: string; }

export interface CreateV2TheaterPayload {
  name: string;
  default_commission_rate: number;
  default_tax_rate: number;
  status: '启用' | '停用';
}

export interface CreateV2AccountPayload {
  nickname: string;
  channel_id: string;
  theater_id: string;
  sub_theater_name: string;
  status: V2AccountRecord['status'];
  reporting_date: string;
  registration_date: string;
  notes: string;
}

export function getV2Theaters(): Promise<{ items: V2TheaterRecord[] }> {
  return v2Client.get('/api/v2/theaters');
}

export function getV2Accounts(): Promise<{ items: V2AccountRecord[] }> {
  return v2Client.get('/api/v2/accounts');
}

export function getV2SubTheaters(): Promise<{ items: V2SubTheaterRecord[] }> {
  return v2Client.get('/api/v2/sub-theaters');
}
export function getV2Dramas(): Promise<{ items: V2DramaRecord[] }> { return v2Client.get('/api/v2/dramas'); }
export function createV2Drama(payload: { current_name: string; history_names: string[]; theater_id: string }): Promise<V2DramaRecord> { return v2Client.post('/api/v2/dramas', payload); }
export function createV2DramasBatch(payload: { current_name: string; history_names: string[]; theater_id: string }[]): Promise<{ items: V2DramaRecord[]; created_count: number; skipped_names: string[] }> { return v2Client.post('/api/v2/dramas/batch', { items: payload }); }
export function updateV2Drama(id: string, payload: { current_name: string; history_names: string[] }): Promise<V2DramaRecord> { return v2Client.patch(`/api/v2/dramas/${id}`, payload); }
export function deleteV2Drama(id: string): Promise<{ deleted: true }> { return v2Client.delete(`/api/v2/dramas/${id}`); }
export function uploadV2DramaCover(id: string, payload: { filename: string; content_base64: string }): Promise<{ drama_id: string; file_path: string; filename: string }> {
  return v2Client.post(`/api/v2/dramas/${id}/cover`, payload);
}
export function createV2DramaProfile(id: string): Promise<{ drama_id: string; folder_path: string; master_folder_path: string; cover_folder_path: string }> {
  return v2Client.post(`/api/v2/dramas/${id}/profile`, {});
}
export function getV2DramaProfiles(): Promise<{ items: { drama_id: string; root_path: string; master_path: string; cover_path: string; updated_at: string }[] }> { return v2Client.get('/api/v2/drama-profiles'); }
export function openV2Folder(path: string): Promise<{ opened: boolean }> { return v2Client.post('/api/v2/open-folder', { path }); }
export function openV2File(path: string): Promise<{ opened: boolean }> { return v2Client.post('/api/v2/open-file', { path }); }
export function getV2ProductionResources(): Promise<{ items: import('../assetsTypes').ProductionResourceItem[] }> { return v2Client.get('/api/v2/production-resources'); }
export interface V2Settings {
  data_root_dir: string;
  raw_material_retention_days: number;
  short_term_cleanup_hours: number;
  publish_presets: string[];
  publish_date_offset_days: number;
  jianying_executable: string;
  jianying_draft_root: string;
  template_timeout_min: number;
  video_export_timeout_min: number;
  final_video_manual_check: boolean;
  video_export_debug: boolean;
}
export function getV2Settings(): Promise<V2Settings> { return v2Client.get('/api/v2/settings'); }
export function updateV2Settings(payload: Partial<V2Settings>): Promise<V2Settings> { return v2Client.post('/api/v2/settings', payload); }
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
export function updateV2Account(id: string, payload: CreateV2AccountPayload): Promise<V2AccountRecord> { return v2Client.patch(`/api/v2/accounts/${id}`, payload); }
export function deleteV2Account(id: string): Promise<{ deleted: true }> { return v2Client.delete(`/api/v2/accounts/${id}`); }
