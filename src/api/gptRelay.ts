import { v2Client } from './client';

export type GptRelayApiFormat = 'responses' | 'openai_chat_completions';
export type GptRelayRoute = 'highlight' | 'continuous' | 'jump' | 'review';

export interface GptRelayModel {
  id: string;
  owned_by?: string;
}

export interface GptRelayConfig {
  provider_name: string;
  base_url: string;
  api_format: GptRelayApiFormat;
  api_key_set: boolean;
  api_key_masked: string;
  enabled: boolean;
  use_system_proxy: boolean;
  models: GptRelayModel[];
  models_fetched_at: string;
  model_routes: Record<GptRelayRoute, string>;
  last_test: GptRelayTestResult | null;
}

export interface GptRelayTestResult {
  ok: boolean;
  status: number;
  model: string;
  usage: Record<string, unknown>;
  tested_at: string;
}

export function getGptRelayConfig(): Promise<GptRelayConfig> {
  return v2Client.get('/api/v3/gpt-relay');
}

export function saveGptRelayConfig(payload: {
  provider_name: string;
  base_url: string;
  api_format: GptRelayApiFormat;
  api_key?: string;
  use_system_proxy?: boolean;
  model_routes: Record<GptRelayRoute, string>;
}): Promise<GptRelayConfig> {
  return v2Client.post('/api/v3/gpt-relay', payload);
}

export function refreshGptRelayModels(): Promise<GptRelayConfig> {
  return v2Client.post('/api/v3/gpt-relay/models', {});
}

export function testGptRelayConnection(model = ''): Promise<GptRelayTestResult & { config: GptRelayConfig }> {
  return v2Client.post('/api/v3/gpt-relay/test', { model });
}

export interface GptRelayJsonRequest {
  task_role: GptRelayRoute;
  model?: string;
  prompt: string;
  schema_name?: string;
  schema: Record<string, unknown>;
  reasoning_effort?: 'low' | 'medium' | 'high';
  max_output_tokens?: number;
}

export interface GptRelayJsonResponse {
  ok: true;
  status: number;
  task_role: GptRelayRoute;
  model: string;
  data: Record<string, unknown>;
  usage: Record<string, unknown>;
  elapsed_s: number;
  created_at: string;
}

export function generateGptRelayJson(payload: GptRelayJsonRequest): Promise<GptRelayJsonResponse> {
  return v2Client.post('/api/v3/gpt-relay/generate-json', payload);
}
