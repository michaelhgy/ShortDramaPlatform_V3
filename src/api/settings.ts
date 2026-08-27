import { v2Client } from './client';

export function getSettings(): Promise<unknown> { return v2Client.get('/api/v1/settings'); }
export function updateSettings(changes: Record<string, unknown>): Promise<unknown> { return v2Client.patch('/api/v1/settings', changes); }
