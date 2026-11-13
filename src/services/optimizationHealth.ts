import type {AccountOptimizationStat} from '../types/shortDramaOps';

export const OPTIMIZATION_HEALTH_LIMITS={critical:50,warning:20} as const;

export function getOptimizationHealth(rate:number|null):AccountOptimizationStat['healthLevel'] {
  if(rate===null || !Number.isFinite(rate))return 'unknown';
  return rate>=OPTIMIZATION_HEALTH_LIMITS.critical?'critical':rate>OPTIMIZATION_HEALTH_LIMITS.warning?'warning':'healthy';
}

export const formatOptimizationRate = (rate:number|null) => rate===null || !Number.isFinite(rate) ? '—' : `${rate}%`;
export const formatWorkMetric = (value:number) => Number.isFinite(value) ? value.toLocaleString('zh-CN') : '—';
