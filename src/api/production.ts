import { v2Client } from './client';

export function getPlans(): Promise<unknown> { return v2Client.get('/api/v1/plans'); }
export function getPlan(planId: number): Promise<unknown> { return v2Client.get(`/api/v1/plans/${planId}`); }
export function getGenerationTasks(): Promise<unknown> { return v2Client.get('/api/v1/generation-tasks'); }
export function getExportTasks(): Promise<unknown> { return v2Client.get('/api/v1/export-tasks'); }
