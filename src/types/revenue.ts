import type { RevenueQualityTier } from '../analyticsTypes';

export interface V1DailyRevenue {
  id: string | number;
  revenue_date: string;
  account_id: string | number;
  account_nickname: string;
  theater_id: string | number;
  theater_name: string;
  amount: string;
  quality: RevenueQualityTier;
  updated_at: string;
}

export interface V1DailyRevenueResponse {
  start_date: string;
  end_date: string;
  items: V1DailyRevenue[];
}

export interface V1CatalogAccount { id: string | number; nickname: string; status: string; theater_id: string | number | null; }
export interface V1CatalogTheater { id: string | number; name: string; status?: string; }

export interface V1RevenueAttempt {
  date: string;
  status: 'success' | 'no_data' | 'failed' | 'indeterminate';
  amount: string | null;
  period_start: string;
  period_end: string | null;
  message: string;
}

export interface V1RevenueCollectionItem {
  account_id: number;
  theater_id: number;
  theater: string;
  job_id?: number;
  status: 'success' | 'no_data' | 'failed' | 'indeterminate' | 'unsupported' | 'skipped';
  message?: string;
  attempts?: V1RevenueAttempt[];
}

export interface V1RevenueCollectionResponse {
  request_id: string;
  total_accounts: number;
  items: V1RevenueCollectionItem[];
}
