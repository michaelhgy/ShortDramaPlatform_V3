import { toRevenueAnalytics, type V2RevenuePayload } from '../adapters/revenue';
import type { RevenueCollectionLog, TheaterFilter, TimeRangeFilter } from '../analyticsTypes';
import { calculateRevenueAnalytics } from '../utils/revenueEngine';
import { dataSource } from './dataSource';
import { loadAnalyticsSeed } from './mockServices';

export interface RevenuePageData {
  source: 'mock' | 'v2';
  analytics: V2RevenuePayload;
  collectionLogs: RevenueCollectionLog[];
}

export async function loadRevenuePageData(input: { timeRange: TimeRangeFilter; theaterFilter: TheaterFilter; customStart?: string; customEnd?: string }): Promise<RevenuePageData> {
  if (dataSource === 'mock') {
    const seed = await loadAnalyticsSeed();
    return { source: 'mock', analytics: calculateRevenueAnalytics(input.timeRange, input.theaterFilter, input.customStart, input.customEnd), collectionLogs: seed.collectionLogs };
  }
  return {
    source: 'v2',
    analytics: toRevenueAnalytics([], [], [], input.timeRange, input.theaterFilter, input.customStart, input.customEnd),
    collectionLogs: [],
  };
}

export async function requestRevenueCollection(scopeName: string, mode: 'immediate' | 'backfill', startDate: string, endDate: string): Promise<RevenueCollectionLog[]> {
  if (dataSource === 'mock') {
    return [{ id: `mock-${Date.now()}`, theaterName: scopeName === 'all' ? '模拟全部剧场' : scopeName, accountName: '模拟采集', period: `${startDate} ~ ${endDate}`, status: 'success', collectedAmount: 3420.5, qualityTier: 'direct', updatedAt: new Date().toLocaleTimeString('zh-CN'), note: 'Mock 模式：未调用 V2。' }];
  }
  throw new Error('V2 收益采集尚未接入；当前不会调用 V1，也不会补充模拟数据。');
}
