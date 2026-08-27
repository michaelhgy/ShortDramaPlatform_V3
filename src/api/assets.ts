import { v2Client } from './client';
import type { V1CatalogAccount, V1CatalogTheater } from '../types/revenue';

export function getAccounts(): Promise<{ items: V1CatalogAccount[] }> { return v2Client.get('/api/v1/accounts'); }
export function getTheaters(): Promise<{ items: V1CatalogTheater[] }> { return v2Client.get('/api/v1/theaters'); }
export function getDramas(theaterId?: number): Promise<unknown> { return v2Client.get('/api/v1/dramas', { theater_id: theaterId }); }
export function getResources(): Promise<unknown> { return v2Client.get('/api/v1/resources'); }
