import { v2Client } from './client';
import type { V1DailyRevenueResponse, V1RevenueCollectionResponse } from '../types/revenue';

export function getDailyRevenues(params: { startDate?: string; endDate?: string; theaterId?: number; accountId?: number } = {}): Promise<V1DailyRevenueResponse> {
  return v2Client.get('/api/v1/revenue/daily-revenues', {
    start_date: params.startDate,
    end_date: params.endDate,
    theater_id: params.theaterId,
    account_id: params.accountId,
  });
}

export function collectRevenueNow(scope: 'all' | 'theater' | 'account', target: { theaterId?: number; accountId?: number } = {}): Promise<V1RevenueCollectionResponse> {
  return v2Client.post('/api/v1/revenue/collect-now', { scope, theater_id: target.theaterId, account_id: target.accountId });
}

export function backfillRevenue(scope: 'all' | 'theater' | 'account', dates: { startDate: string; endDate: string }, target: { theaterId?: number; accountId?: number } = {}): Promise<V1RevenueCollectionResponse> {
  return v2Client.post('/api/v1/revenue/backfill', {
    scope, theater_id: target.theaterId, account_id: target.accountId,
    start_date: dates.startDate, end_date: dates.endDate,
  });
}
