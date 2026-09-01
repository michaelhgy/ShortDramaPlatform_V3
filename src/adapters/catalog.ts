import type { AccountBusinessItem, DramaBusinessItem, SubTheaterBusinessItem, TheaterBusinessItem } from '../assetsTypes';
import type { V2AccountRecord, V2SubTheaterRecord, V2TheaterRecord } from '../api/v2Catalog';

export function toBusinessTheater(item: V2TheaterRecord): TheaterBusinessItem {
  return {
    id: item.id,
    name: item.name,
    defaultCommissionRate: item.default_commission_rate,
    defaultTaxRate: item.default_tax_rate,
    status: item.status,
    subTheatersCount: item.sub_theaters_count,
    dramasCount: item.dramas_count,
    isUsedInBusiness: item.accounts_count > 0,
  };
}

export function toBusinessAccount(item: V2AccountRecord): AccountBusinessItem {
  return {
    id: item.id,
    nickname: item.nickname,
    accountId: item.channel_id,
    theaterId: item.theater_id,
    theaterName: item.theater_name,
    subTheaterName: item.sub_theater_name || '—',
    status: item.status,
    whitelistedDate: item.reporting_date || '未报白',
    registeredDate: item.registration_date || '—',
    notes: item.notes,
    isUsedInBusiness: false,
  };
}

export function toBusinessSubTheater(item: V2SubTheaterRecord): SubTheaterBusinessItem {
  return {
    id: item.id,
    theaterId: item.theater_id,
    theaterName: item.theater_name,
    name: item.name,
    commissionRate: item.commission_rate,
    isCommissionOverridden: Boolean(item.is_commission_overridden),
    status: item.status,
    boundAccountsCount: item.bound_accounts_count,
    isUsedInBusiness: item.bound_accounts_count > 0,
  };
}
export function toBusinessDrama(item: import('../api/v2Catalog').V2DramaRecord): DramaBusinessItem { return { id: item.id, currentName: item.current_name, historyNames: item.history_names, theaterId: item.theater_id, theaterName: item.theater_name, createdAt: item.created_at, productionCount: Number(item.production_count) || 0, lastScheduledAt: item.last_scheduled_at || '', activeProductionCount: Number(item.active_production_count) || 0, isUsedInBusiness: false }; }
