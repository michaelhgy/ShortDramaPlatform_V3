import assert from 'node:assert/strict';
import test from 'node:test';
import { sortMatrixAccounts, getLoginState, defaultMatrixSortOrder } from './accountMatrixSort.ts';
import type { AccountInfo } from '../types/shortDramaOps.ts';

function item(id: string, revenue: number, available = true, history: number | null = revenue) {
  return { account: { id, name: id, businessStatus: '正常', rating: { recordedTotal: history } } as AccountInfo,
    revenue, views: revenue * 10, hasPeriodRevenue: available, hasPeriodTraffic: available };
}
const ids = (items: Array<{account: AccountInfo}>) => items.map(item => item.account.id);

test('current revenue and views keep confirmed zero above missing in both directions without mutating input', () => {
  const rows = [item('missing', 0, false), item('zero', 0), item('high', 30), item('tie', 30)];
  for (const key of ['revenue', 'views'] as const) {
    assert.deepEqual(ids(sortMatrixAccounts(rows, key, 'desc')), ['high','tie','zero','missing']);
    assert.deepEqual(ids(sortMatrixAccounts(rows, key, 'asc')), ['zero','high','tie','missing']);
  }
  assert.deepEqual(ids(rows), ['missing','zero','high','tie']);
});

test('history sorts its own cumulative field, with missing and non-finite values last', () => {
  const rows = [item('missing', 100, true, null), item('currentHigh', 80, true, 10), item('historyHigh', 1, true, 100), item('zero', 30, true, 0), item('nan', 3, true, NaN)];
  assert.deepEqual(ids(sortMatrixAccounts(rows, 'historicalRevenue', 'desc')), ['historyHigh','currentHigh','zero','missing','nan']);
  assert.deepEqual(ids(sortMatrixAccounts(rows, 'historicalRevenue', 'asc')), ['zero','currentHigh','historyHigh','missing','nan']);
});

test('business states group in the agreed order and reverse without moving unknown first', () => {
  const states = ['其他','停用','二限','正常','封号','实名','观察','限流'];
  const rows = states.map(status => { const row = item(status, 0); row.account.businessStatus = status; return row; });
  assert.deepEqual(ids(sortMatrixAccounts(rows, 'businessStatus', 'asc')), ['正常','观察','限流','二限','实名','封号','停用','其他']);
  assert.deepEqual(ids(sortMatrixAccounts(rows, 'businessStatus', 'desc')), ['停用','封号','实名','二限','限流','观察','正常','其他']);
});

test('only explicit login results count as valid or invalid; unknown always stays last', () => {
  const rows = ['新状态','登录失效','登录有效','未登录',''].map(status => { const row = item(status, 0); row.account.loginStatus = status; return row; });
  assert.deepEqual(ids(sortMatrixAccounts(rows, 'loginStatus', 'asc')), ['登录有效','登录失效','未登录','新状态','']);
  assert.deepEqual(ids(sortMatrixAccounts(rows, 'loginStatus', 'desc')), ['登录失效','未登录','登录有效','新状态','']);
  assert.equal(getLoginState(undefined), 'unknown'); assert.equal(getLoginState('新状态'), 'unknown');
  assert.equal(getLoginState('登录过期'), 'invalid');
});

test('numeric options start descending; state options start in the agreed forward order', () => {
  assert.equal(defaultMatrixSortOrder('revenue'), 'desc'); assert.equal(defaultMatrixSortOrder('historicalRevenue'), 'desc');
  assert.equal(defaultMatrixSortOrder('views'), 'desc'); assert.equal(defaultMatrixSortOrder('businessStatus'), 'asc'); assert.equal(defaultMatrixSortOrder('loginStatus'), 'asc');
});
