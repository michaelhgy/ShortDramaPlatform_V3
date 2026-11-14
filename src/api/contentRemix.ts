import { ApiClient, v2Client } from './client';
import { V3ContentAiRun, V3HighlightLibraryVersion } from './contentProduction';

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
  production_purpose?: '首轮覆盖' | '失败重做' | '爆款扩量' | '策略测试' | string;
  highlight_ids?: string[];
  highlight_library_version?: string;
  based_on_highlight?: string;
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

export interface ContentHighlightLibraryResponse {
  libraries: Array<Pick<V3HighlightLibraryVersion, 'versionId' | 'dramaId' | 'dramaTitle' | 'analysisVersion' | 'sourceFingerprint' | 'createdAt'> & { highlightCount: number }>;
  latest: V3HighlightLibraryVersion | null;
}

export function getContentHighlightLibraries(dramaId: string): Promise<ContentHighlightLibraryResponse> {
  return v2Client.get(`/api/v3/content-remix/highlights/${encodeURIComponent(dramaId)}`);
}

export function getContentHighlightLibraryVersion(dramaId: string, versionId: string): Promise<V3HighlightLibraryVersion> {
  return v2Client.get(`/api/v3/content-remix/highlights/${encodeURIComponent(dramaId)}/versions/${encodeURIComponent(versionId)}`);
}

export interface HighlightAnalysisRun {
  id: string;
  dramaId: string;
  dramaTitle: string;
  sourceDirectory: string;
  status: 'queued' | 'running' | 'completed' | 'failed';
  stage: string;
  detail: string;
  error?: string;
  totalEpisodes: number;
  lineCount: number;
  highlightCount: number;
  libraryVersionId?: string;
  createdAt: string;
  finishedAt?: string;
}

export function startContentHighlightAnalysis(payload: {
  drama_id: string;
  drama_title: string;
  source_directory: string;
}): Promise<HighlightAnalysisRun> {
  return v2Client.post('/api/v3/content-remix/highlights/analysis', payload);
}

export function getContentHighlightAnalysis(runId: string): Promise<HighlightAnalysisRun> {
  return v2Client.get(`/api/v3/content-remix/highlights/analysis/${runId}`);
}
