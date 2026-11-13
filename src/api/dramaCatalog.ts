import { v2Client } from './client';

export type MountSource = 'mini_drama' | 'channels_drama' | 'plugin';
export type OnlineSource = Exclude<MountSource, 'plugin'>;
export interface PlatformDrama {
  source: OnlineSource; external_id: string; name: string; mediaCount?: number; coverUrl?: string;
  miniAppName?: string; miniAppIconUrl?: string; srcMiniAppName?: string; srcMiniAppIconUrl?: string;
  questFlag?: unknown; updated_at?: string;
}
export interface CatalogueItem extends PlatformDrama {
  drama_id: string | null; current_name: string | null; usable: number | null;
  reason: string; issue: string | null; checked_at: string;
}
export interface CataloguePage { items: CatalogueItem[]; total: number; page: number; page_size: number }
export interface MountChoice { account_id: string; drama_id: string; external_id: string; name: string; miniAppName: string; checked_at: string }
export interface CatalogueJob {
  id: string; status: 'queued' | 'running' | 'stopping' | 'stopped' | 'partial' | 'completed' | 'error';
  account_ids: string[]; sources: OnlineSource[]; mode: 'usable' | 'all'; message: string;
  fetched: number; created: number; linked: number; updated: number; skipped: number; conflicts: number;
  covers: number; cover_errors: number; avatars: number; removed?: number; page: number; total_reported: number; errors: string[];
}
const root = '/api/v3/drama-catalog';
export const getCataloguePage = (accountId: string, source: OnlineSource, query = '', page = 1, usableOnly = false, pageSize = 24) =>
  v2Client.get<CataloguePage>(`${root}/items`, { account_id: accountId, source, query, page, usable_only: usableOnly ? 1 : 0, page_size: pageSize });
export const getMountChoices = (accountIds: string[], source: MountSource) =>
  v2Client.get<{ items: MountChoice[] }>(`${root}/eligibility`, { account_ids: accountIds.join(','), source });
export const startCatalogueSync = (accountIds: string[], sources: OnlineSource[], mode: 'usable' | 'all') =>
  v2Client.post<CatalogueJob>(`${root}/sync`, { account_ids: accountIds, sources, mode });
export const getCatalogueJob = (id: string) => v2Client.get<CatalogueJob>(`${root}/jobs/${id}`);
export const latestCatalogueJob = () => v2Client.get<CatalogueJob | null>(`${root}/latest`);
export const stopCatalogueJob = (id: string) => v2Client.post<CatalogueJob>(`${root}/jobs/${id}/stop`);
export const linkCatalogueDrama = (accountId: string, source: OnlineSource, externalId: string, dramaId: string) =>
  v2Client.post(`${root}/link`, { account_id: accountId, source, external_id: externalId, drama_id: dramaId });
