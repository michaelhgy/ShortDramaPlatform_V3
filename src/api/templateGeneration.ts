import { v2Client, ApiClient } from './client';
import type { EncoderStatus } from './encoderStatus';
export type TemplateConfig = Record<string, number | [number, number] | boolean>;
export interface GenerationJob { encoding?: EncoderStatus | null; availability?: 'available' | 'exhausted'; id: string; display_name: string; batch_id: string; batch_name: string; ordinal: number; status: 'waiting' | 'running' | 'done' | 'error' | 'cancelled'; progress: number; stage: string; error: string; seconds: number; family: string; elapsed_seconds: number; preview_url: string | null; created_at: string; output_path: string | null; output_sha256: string | null; }
export interface GenerationSnapshot { jobs: GenerationJob[]; paused: boolean; counts: Record<GenerationJob['status'], number>; output_directory: string; }
export interface ParameterInfo { label: string; description: string; rule: string; unit: string; }
export interface GenerationConfigResponse { config: TemplateConfig; limits: Record<string, [number, number]>; suggested_ranges?: Record<string, [number, number]>; fields?: Record<string, ParameterInfo>; profile: string; library: { effects: number; borders: number; fullscreen_stickers?: number }; }
const root = '/api/v3/template-generation';
const batchClient = new ApiClient({ timeoutMs: 120_000 });
export const getGenerationConfig = (): Promise<GenerationConfigResponse> => v2Client.get(`${root}/config`);
export const saveGenerationConfig = (config: TemplateConfig): Promise<{config: TemplateConfig}> => v2Client.post(`${root}/config`, { config });
export const createTemplateBatch = (count: number, request_id: string): Promise<{batch_id: string; warnings?: string[]}> => batchClient.post(`${root}/batches`, { count, request_id });
export const generationAction = (path: string): Promise<GenerationSnapshot> => v2Client.post(`${root}/${path}`, {});
