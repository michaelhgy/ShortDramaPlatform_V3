import type { ProductionUnit } from '../productionTypes';
import { INITIAL_PRODUCTION_UNITS } from '../productionMockData';
import { dataSource } from './dataSource';
import { listV2ProductionTasks, listV2ProductionTaskSummaries } from '../api/v2Production';
import { toProductionUnit } from '../adapters/production';

export async function loadProductionUnits(): Promise<ProductionUnit[]> {
  if (dataSource === 'mock') return INITIAL_PRODUCTION_UNITS;
  const response = await listV2ProductionTasks();
  return response.items.map(toProductionUnit);
}

const SUMMARY_CACHE_KEY = 'v2-production-task-summaries-v1';
const SUMMARY_CACHE_UPDATED_KEY = `${SUMMARY_CACHE_KEY}:updated-at`;
let cachedSummaryUnits: ProductionUnit[] | null = null;
let summaryRequest: Promise<ProductionUnit[]> | null = null;

function readSummaryCache(): ProductionUnit[] | null {
  try {
    const value = localStorage.getItem(SUMMARY_CACHE_KEY);
    const parsed = value ? JSON.parse(value) : null;
    return Array.isArray(parsed) ? parsed as ProductionUnit[] : null;
  } catch { return null; }
}

export function getCachedProductionSummary(): ProductionUnit[] | null {
  if (cachedSummaryUnits) return cachedSummaryUnits;
  cachedSummaryUnits = readSummaryCache();
  return cachedSummaryUnits;
}

export function loadProductionSummary(force = false): Promise<ProductionUnit[]> {
  const cached = getCachedProductionSummary();
  if (!force && cached) return Promise.resolve(cached);
  if (summaryRequest) return summaryRequest;
  summaryRequest = (dataSource === 'mock'
    ? Promise.resolve(INITIAL_PRODUCTION_UNITS)
    : listV2ProductionTaskSummaries().catch(() => listV2ProductionTasks()).then((response) => response.items.map(toProductionUnit)))
    .then((units) => {
      cachedSummaryUnits = units;
      try { localStorage.setItem(SUMMARY_CACHE_KEY, JSON.stringify(units)); localStorage.setItem(SUMMARY_CACHE_UPDATED_KEY, new Date().toISOString()); } catch { /* cache is optional */ }
      return units;
    }).finally(() => { summaryRequest = null; });
  return summaryRequest;
}
