import type { ProductionUnit } from '../productionTypes';
import { INITIAL_PRODUCTION_UNITS } from '../productionMockData';
import { dataSource } from './dataSource';

export async function loadProductionUnits(): Promise<ProductionUnit[]> {
  if (dataSource === 'mock') return INITIAL_PRODUCTION_UNITS;
  return [];
}
