import { v2Client, ApiClient } from './client';
import type { EncoderStatus } from './encoderStatus';
export interface InsertionResult { total_frames: number; midroll: { status: string; insert_at_seconds?: number }; endroll: { status: string }; }
export interface FinalJob { insertions?: InsertionResult | null; encoding?: EncoderStatus | null; automatic?:boolean; auto_held?:boolean; id: string; task_id: string; material_id: string; template_id: string; status: 'waiting'|'running'|'done'|'error'|'cancelled'; name: string; account_name: string; drama_name: string; stage: string; progress: number; elapsed_seconds: number; error: string; output_path: string|null; }
export interface FinalSnapshot { jobs: FinalJob[]; paused: boolean; auto_enabled?:boolean; auto_error?:string; counts: Record<FinalJob['status'], number>; }
const root='/api/v3/final-composition';
const client=new ApiClient({timeoutMs:120_000});
export const createFinalBatch=(taskId:string):Promise<{created_count:number;skipped_count:number}>=>client.post(`${root}/batches`,{task_id:taskId});
export const finalAction=(path:string):Promise<FinalSnapshot>=>v2Client.post(`${root}/${path}`,{});
export const setAutomaticComposition=(enabled:boolean):Promise<FinalSnapshot>=>v2Client.post(`${root}/automatic`,{enabled});
export const moveProductionTask=(task_id:string,target_id:string,placement:'before'|'after'):Promise<{order:string[]}>=>v2Client.post(`${root}/order`,{task_id,target_id,placement});

export const regenerateFinals=(taskId:string,jobId?:string):Promise<{regenerated_count:number}>=>client.post(jobId ? `${root}/jobs/${jobId}/regenerate` : `${root}/regenerate`,jobId ? {} : {task_id:taskId});

export interface CompositionDiagnosticsOptions { scope: 'recent' | 'selected' | 'all'; limit: number; include_baseline: boolean; attempt_keys?: string[]; session_id?: string; }
export interface CompositionDiagnosticRecord { key: string; name: string; attempt: number; session_id: string; started_at: string; status: string; }
export interface CompositionDiagnosticsCatalog { items: CompositionDiagnosticRecord[]; latest_session_id: string; latest_session_count: number; total: number; read_error_count: number; }
export interface CompositionDiagnosticsExport { directory: string; report_path: string; bundle_path: string; attempts: number; summary_attempts: number; selection: { primary_attempts: number; baseline_attempts: number; omitted_detail_attempts: number }; files: number; opened: boolean; warnings: string[]; }
export const loadCompositionDiagnosticsCatalog=():Promise<CompositionDiagnosticsCatalog>=>client.get(`${root}/diagnostics/catalog`);
export const exportCompositionDiagnostics=(options:CompositionDiagnosticsOptions):Promise<CompositionDiagnosticsExport>=>client.post(`${root}/diagnostics/export`,options);
