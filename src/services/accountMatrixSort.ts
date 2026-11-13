import type { AccountInfo } from '../types/shortDramaOps.ts';

export type MatrixSortKey = 'revenue' | 'historicalRevenue' | 'views' | 'businessStatus' | 'loginStatus';
export type MatrixSortOrder = 'desc' | 'asc';
export const MATRIX_SORT_OPTIONS: ReadonlyArray<{ key: MatrixSortKey; label: string }> = [
  { key: 'revenue', label: '当前创收' }, { key: 'historicalRevenue', label: '历史创收' },
  { key: 'views', label: '总播放量' }, { key: 'businessStatus', label: '账号状态' },
  { key: 'loginStatus', label: '登录状态' },
];

export function getLoginState(value?: string): 'valid' | 'invalid' | 'unknown' {
  if (value === '登录有效') return 'valid';
  if (['登录失效', '未登录', '登录过期', '已过期', '登录无效'].includes(value || '')) return 'invalid';
  return 'unknown';
}

export function defaultMatrixSortOrder(key: MatrixSortKey): MatrixSortOrder {
  return key === 'businessStatus' || key === 'loginStatus' ? 'asc' : 'desc';
}

interface MatrixItem {
  account: AccountInfo;
  revenue: number;
  views: number;
  hasPeriodRevenue: boolean;
  hasPeriodTraffic: boolean;
}

const businessOrder = ['正常', '观察', '限流', '二限', '实名', '封禁', '停用'];
function sortValue(item: MatrixItem, key: MatrixSortKey): number | null {
  let value: number | null | undefined;
  if (key === 'revenue') value = item.hasPeriodRevenue ? item.revenue : null;
  else if (key === 'historicalRevenue') value = item.account.rating?.recordedTotal;
  else if (key === 'views') value = item.hasPeriodTraffic ? item.views : null;
  else if (key === 'loginStatus') {
    const state = getLoginState(item.account.loginStatus);
    value = state === 'valid' ? 0 : state === 'invalid' ? 1 : null;
  } else {
    const status = item.account.businessStatus === '封号' ? '封禁' : item.account.businessStatus;
    const index = businessOrder.indexOf(status || '');
    value = index < 0 ? null : index;
  }
  return typeof value === 'number' && Number.isFinite(value) ? value : null;
}

/** Missing values always stay last; equal values use the original account order. */
export function sortMatrixAccounts<T extends MatrixItem>(items: readonly T[], key: MatrixSortKey, order: MatrixSortOrder): T[] {
  return [...items].sort((a, b) => {
    const left = sortValue(a, key), right = sortValue(b, key);
    if (left === null || right === null) return left === right ? 0 : left === null ? 1 : -1;
    return (left - right) * (order === 'asc' ? 1 : -1);
  });
}
