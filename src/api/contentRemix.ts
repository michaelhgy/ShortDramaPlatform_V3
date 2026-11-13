import { ApiClient, v2Client } from './client';
import { V3ContentAiRun } from './contentProduction';

// 扫描网络盘上的原片目录可能较慢，单独放宽超时。
const slowClient = new ApiClient({ timeoutMs: 90_000 });

export interface ContentRemixSourceDrama {
  drama_id: string;
  drama_title: string;
  theater_name: string;
  directory: string;
  mp4_count: number;
  size_gb: number;
}

export function getContentRemixSourceDramas(): Promise<{ download_root: string; download_root_ok: boolean; items: ContentRemixSourceDrama[] }> {
  return slowClient.get('/api/v3/content-remix/source-dramas');
}

export interface StartContentRemixPayload {
  drama_id: string;
  drama_title: string;
  source_directory: string;
  template_id: string;
  template_name: string;
  template_version: string;
  renderer_template_id?: string;
  strategy_counts: Record<'连续播放' | '跳集播放', number>;
  duration_range_min: [number, number];
  model_id: string;
  model_assignments?: Record<'highlight' | 'continuous' | 'jump' | 'review', string>;
}

export function getContentRemixRuns(): Promise<{ items: V3ContentAiRun[] }> {
  return v2Client.get('/api/v3/content-remix/runs');
}

export function getContentRemixRun(runId: string): Promise<V3ContentAiRun> {
  return v2Client.get(`/api/v3/content-remix/runs/${runId}`);
}

export function startContentRemixRun(payload: StartContentRemixPayload): Promise<V3ContentAiRun> {
  return v2Client.post('/api/v3/content-remix/runs', payload);
}
