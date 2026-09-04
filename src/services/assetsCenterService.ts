import {
  MOCK_BUSINESS_ACCOUNTS,
  MOCK_BUSINESS_THEATERS,
  MOCK_BUSINESS_SUB_THEATERS,
  MOCK_BUSINESS_DRAMAS,
  MOCK_DRAMA_CONTENT_PROFILES,
  MOCK_PRODUCTION_RESOURCES,
  MOCK_VIRAL_ASSETS,
  MOCK_CANDIDATE_PRODUCTION_MATERIALS,
} from '../assetsMockData';
import { dataSource } from './dataSource';
import { createV2Account, createV2AccountsBatch, createV2Drama, createV2DramasBatch, createV2SubTheater, createV2SubTheatersBatch, createV2Theater, createV2TheatersBatch, deleteV2Account, deleteV2Drama, deleteV2SubTheater, deleteV2Theater, getV2Account, getV2Accounts, getV2Drama, getV2Dramas, getV2DramaProfiles, getV2ProductionResources, getV2SubTheaters, getV2Theaters, updateV2Account, updateV2Drama, updateV2SubTheater, updateV2Theater } from '../api/v2Catalog';
import { toBusinessAccount, toBusinessDrama, toBusinessSubTheater, toBusinessTheater } from '../adapters/catalog';
import type { AccountBusinessItem, DramaBusinessItem, ProductionResourceItem, SubTheaterBusinessItem, TheaterBusinessItem, ViralAssetItem } from '../assetsTypes';

type AssetsCenterSeed = {
  accounts: AccountBusinessItem[];
  theaters: TheaterBusinessItem[];
  subTheaters: SubTheaterBusinessItem[];
  dramas: DramaBusinessItem[];
  profiles: any[];
  productionResources: ProductionResourceItem[];
  viralAssets: ViralAssetItem[];
};
let cachedAssetsSeed: AssetsCenterSeed | null = null;
let assetsSeedPromise: Promise<AssetsCenterSeed> | null = null;
const ASSETS_CACHE_KEY = 'v2-assets-center-seed-v1';
const ASSETS_CACHE_UPDATED_KEY = `${ASSETS_CACHE_KEY}:updated-at`;

export function getCachedAssetsCenterSeed(): AssetsCenterSeed | null {
  if (!cachedAssetsSeed) {
    try {
      const raw = localStorage.getItem(ASSETS_CACHE_KEY);
      cachedAssetsSeed = raw ? JSON.parse(raw) as AssetsCenterSeed : null;
    } catch { cachedAssetsSeed = null; }
  }
  return cachedAssetsSeed;
}

function persistAssetsSeed(seed: AssetsCenterSeed): void {
  cachedAssetsSeed = seed;
  try { localStorage.setItem(ASSETS_CACHE_KEY, JSON.stringify(seed)); localStorage.setItem(ASSETS_CACHE_UPDATED_KEY, new Date().toISOString()); } catch { /* optional */ }
}

export async function refreshCachedAssetsItem(change: {
  accountId?: string;
  dramaId?: string;
  changeType?: string;
  method?: string;
}): Promise<Partial<AssetsCenterSeed> | null> {
  const current = getCachedAssetsCenterSeed();
  if (!current) return null;
  if (change.accountId) {
    if (change.method === 'DELETE') {
      const accounts = current.accounts.filter((item) => item.id !== change.accountId);
      persistAssetsSeed({ ...current, accounts }); return { accounts };
    }
    const account = toBusinessAccount(await getV2Account(change.accountId));
    const accounts = [...current.accounts.filter((item) => item.id !== account.id), account];
    persistAssetsSeed({ ...current, accounts });
    return { accounts };
  }
  if (change.dramaId) {
    if (change.method === 'DELETE') {
      const dramas = current.dramas.filter((item) => item.id !== change.dramaId);
      persistAssetsSeed({ ...current, dramas }); return { dramas };
    }
    const drama = toBusinessDrama(await getV2Drama(change.dramaId));
    const dramas = [...current.dramas.filter((item) => item.id !== drama.id), drama];
    persistAssetsSeed({ ...current, dramas });
    return { dramas };
  }
  // Theater, sub-theater and profile endpoints currently return list records.
  // Refresh only that reference collection rather than the whole assets seed
  // (which also reads production resources).
  if (change.changeType === 'theater_changed') {
    const theaters = (await getV2Theaters()).items.map(toBusinessTheater);
    persistAssetsSeed({ ...current, theaters });
    return { theaters };
  }
  if (change.changeType === 'sub_theater_changed') {
    const subTheaters = (await getV2SubTheaters()).items.map(toBusinessSubTheater);
    persistAssetsSeed({ ...current, subTheaters });
    return { subTheaters };
  }
  if (change.changeType === 'profile_changed') {
    const profiles = await getV2DramaProfiles();
    const profileItems = profiles.items.map((profile) => {
      const drama = current.dramas.find((item) => item.id === profile.drama_id);
      return drama ? { id: `profile-${profile.drama_id}`, dramaId: profile.drama_id, dramaCurrentName: drama.currentName, theaterName: drama.theaterName, category: '', tags: [], totalEpisodes: 0, cover: { filePath: profile.cover_path, mainCoverUrl: profile.cover_path ? `/api/v2/dramas/${profile.drama_id}/cover` : '' }, masterVideoPackage: { folderPath: profile.master_path, totalFiles: 0, totalSizeGb: 0, resolution: '', status: '待导入' as const, files: [] }, associatedViralAssetsCount: 0, updatedAt: profile.updated_at } : null;
    }).filter((profile): profile is NonNullable<typeof profile> => Boolean(profile));
    persistAssetsSeed({ ...current, profiles: profileItems });
    return { profiles: profileItems };
  }
  return null;
}

/**
 * Temporary data boundary for the new Assets Center UI.
 * V2 mode loads only the V2 catalog. Modules without an implemented V2 contract
 * remain empty; mock content remains opt-in only.
 */
export async function loadAssetsCenterSeed(force = false) {
  if (dataSource === 'mock') {
    return {
      accounts: MOCK_BUSINESS_ACCOUNTS,
      theaters: MOCK_BUSINESS_THEATERS,
      subTheaters: MOCK_BUSINESS_SUB_THEATERS,
      dramas: MOCK_BUSINESS_DRAMAS,
      profiles: MOCK_DRAMA_CONTENT_PROFILES,
      productionResources: MOCK_PRODUCTION_RESOURCES,
      viralAssets: MOCK_VIRAL_ASSETS,
    };
  }
  if (cachedAssetsSeed && !force) return cachedAssetsSeed;
  if (assetsSeedPromise) return assetsSeedPromise;
  assetsSeedPromise = (async () => {
  const [accounts, theaters, subTheaters, dramas, profiles, productionResources] = await Promise.all([getV2Accounts(), getV2Theaters(), getV2SubTheaters(), getV2Dramas(), getV2DramaProfiles(), getV2ProductionResources()]);
  const dramaItems = dramas.items.map(toBusinessDrama);
  const profileItems = profiles.items.map((profile) => {
    const drama = dramaItems.find((item) => item.id === profile.drama_id);
    return drama ? { id: `profile-${profile.drama_id}`, dramaId: profile.drama_id, dramaCurrentName: drama.currentName, theaterName: drama.theaterName, category: '', tags: [], totalEpisodes: 0, cover: { filePath: profile.cover_path, mainCoverUrl: profile.cover_path ? `/api/v2/dramas/${profile.drama_id}/cover` : '' }, masterVideoPackage: { folderPath: profile.master_path, totalFiles: 0, totalSizeGb: 0, resolution: '', status: '待导入' as const, files: [] }, associatedViralAssetsCount: 0, updatedAt: profile.updated_at } : null;
  }).filter((profile): profile is NonNullable<typeof profile> => Boolean(profile));
  const seed = {
    accounts: accounts.items.map(toBusinessAccount),
    theaters: theaters.items.map(toBusinessTheater),
    subTheaters: subTheaters.items.map(toBusinessSubTheater), dramas: dramaItems, profiles: profileItems, productionResources: productionResources.items as ProductionResourceItem[], viralAssets: [],
  };
  persistAssetsSeed(seed);
  assetsSeedPromise = null;
  return seed;
  })();
  try { return await assetsSeedPromise; } catch (error) { assetsSeedPromise = null; throw error; }
}

export function loadViralCandidateMaterials() {
  return Promise.resolve(dataSource === 'mock' ? MOCK_CANDIDATE_PRODUCTION_MATERIALS : []);
}

export async function createBusinessTheater(input: Omit<TheaterBusinessItem, 'id'>): Promise<TheaterBusinessItem> {
  const record = await createV2Theater({
    name: input.name,
    default_commission_rate: input.defaultCommissionRate,
    default_tax_rate: input.defaultTaxRate,
    status: input.status,
  });
  return toBusinessTheater({ ...record, accounts_count: 0, sub_theaters_count: 0, dramas_count: 0 });
}

export async function createBusinessTheatersBatch(inputs: Omit<TheaterBusinessItem, 'id'>[]): Promise<{ items: TheaterBusinessItem[]; skippedNames: string[] }> {
  const response = await createV2TheatersBatch(inputs.map((input) => ({
    name: input.name,
    default_commission_rate: input.defaultCommissionRate,
    default_tax_rate: input.defaultTaxRate,
    status: input.status,
  })));
  return { items: response.items.map((record) => toBusinessTheater({ ...record, accounts_count: 0, sub_theaters_count: 0, dramas_count: 0 })), skippedNames: response.skipped_names };
}

export async function updateBusinessTheater(id: string, input: Omit<TheaterBusinessItem, 'id'>): Promise<TheaterBusinessItem> {
  const record = await updateV2Theater(id, {
    name: input.name,
    default_commission_rate: input.defaultCommissionRate,
    default_tax_rate: input.defaultTaxRate,
    status: input.status,
  });
  return toBusinessTheater(record);
}

export function deleteBusinessTheater(id: string): Promise<{ deleted: true }> {
  return deleteV2Theater(id);
}

export async function createBusinessAccount(input: Omit<AccountBusinessItem, 'id'>): Promise<AccountBusinessItem> {
  const record = await createV2Account({
    nickname: input.nickname,
    channel_id: input.accountId,
    theater_id: input.theaterId,
    sub_theater_name: input.subTheaterName === '—' ? '' : input.subTheaterName,
    status: input.status,
    reporting_date: input.whitelistedDate === '未报白' ? '' : input.whitelistedDate,
    registration_date: input.registeredDate === '—' ? '' : input.registeredDate,
    notes: input.notes,
  });
  return toBusinessAccount({ ...record, theater_name: input.theaterName });
}

export async function createBusinessAccountsBatch(inputs: Omit<AccountBusinessItem, 'id'>[]): Promise<{ items: AccountBusinessItem[]; skippedNames: string[] }> {
  const response = await createV2AccountsBatch(inputs.map((input) => ({
    nickname: input.nickname, channel_id: input.accountId, theater_id: input.theaterId, theater_name: input.theaterName,
    sub_theater_name: input.subTheaterName === '—' ? '' : input.subTheaterName, status: input.status,
    reporting_date: input.whitelistedDate === '未报白' ? '' : input.whitelistedDate,
    registration_date: input.registeredDate === '—' ? '' : input.registeredDate, notes: input.notes,
  })));
  return { items: response.items.map((record) => toBusinessAccount(record)), skippedNames: response.skipped_names };
}

export async function createBusinessSubTheater(input: Omit<SubTheaterBusinessItem, 'id'>): Promise<SubTheaterBusinessItem> {
  const record = await createV2SubTheater({
    theater_id: input.theaterId, name: input.name, commission_rate: input.commissionRate,
    is_commission_overridden: input.isCommissionOverridden, status: input.status,
  });
  return toBusinessSubTheater(record);
}

export async function createBusinessSubTheatersBatch(inputs: Omit<SubTheaterBusinessItem, 'id'>[]): Promise<{ items: SubTheaterBusinessItem[]; skippedNames: string[] }> {
  const response = await createV2SubTheatersBatch(inputs.map((input) => ({
    theater_id: input.theaterId, name: input.name, commission_rate: input.commissionRate,
    is_commission_overridden: input.isCommissionOverridden, status: input.status,
  })));
  return { items: response.items.map(toBusinessSubTheater), skippedNames: response.skipped_names };
}

export async function updateBusinessSubTheater(id: string, input: Omit<SubTheaterBusinessItem, 'id'>): Promise<SubTheaterBusinessItem> {
  return toBusinessSubTheater(await updateV2SubTheater(id, { theater_id: input.theaterId, name: input.name, commission_rate: input.commissionRate, is_commission_overridden: input.isCommissionOverridden, status: input.status }));
}
export function deleteBusinessSubTheater(id: string): Promise<{ deleted: true }> { return deleteV2SubTheater(id); }
export async function updateBusinessAccount(id: string, input: Omit<AccountBusinessItem, 'id'>): Promise<AccountBusinessItem> {
  return toBusinessAccount(await updateV2Account(id, { nickname: input.nickname, channel_id: input.accountId, theater_id: input.theaterId, sub_theater_name: input.subTheaterName === '—' ? '' : input.subTheaterName, status: input.status, reporting_date: input.whitelistedDate === '未报白' ? '' : input.whitelistedDate, registration_date: input.registeredDate === '—' ? '' : input.registeredDate, notes: input.notes }));
}
export function deleteBusinessAccount(id: string): Promise<{ deleted: true }> { return deleteV2Account(id); }
export async function createBusinessDrama(input: Omit<DramaBusinessItem, 'id' | 'createdAt' | 'hasContentProfile'>): Promise<DramaBusinessItem> { return toBusinessDrama(await createV2Drama({ current_name: input.currentName, history_names: input.historyNames, theater_id: input.theaterId })); }
export async function createBusinessDramasBatch(inputs: Omit<DramaBusinessItem, 'id' | 'createdAt' | 'hasContentProfile'>[]): Promise<{ items: DramaBusinessItem[]; skippedNames: string[] }> { const r = await createV2DramasBatch(inputs.map((i) => ({ current_name: i.currentName, history_names: i.historyNames, theater_id: i.theaterId }))); return { items: r.items.map(toBusinessDrama), skippedNames: r.skipped_names }; }
export async function updateBusinessDrama(id: string, input: Omit<DramaBusinessItem, 'id' | 'createdAt' | 'hasContentProfile'>): Promise<DramaBusinessItem> { return toBusinessDrama(await updateV2Drama(id, { current_name: input.currentName, history_names: input.historyNames })); }
export function deleteBusinessDrama(id: string): Promise<{ deleted: true }> { return deleteV2Drama(id); }
