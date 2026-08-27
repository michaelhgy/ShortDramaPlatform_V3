import { v2Client } from './client';

export interface V1HealthResponse { status: string; version: number; }

export function getV1Health(): Promise<V1HealthResponse> {
  return v2Client.get('/api/v1/health');
}

export function getDashboard(): Promise<unknown> {
  return v2Client.get('/api/v1/dashboard');
}
