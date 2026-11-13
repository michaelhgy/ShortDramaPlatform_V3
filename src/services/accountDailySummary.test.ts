import assert from 'node:assert/strict';
import test from 'node:test';
import { accountDailySummary } from './accountDailySummary.ts';
import type { AnalyticsAccountDaily } from '../api/analyticsDataBase';

const fact = (id: string, date: string, values: Partial<AnalyticsAccountDaily> = {}): AnalyticsAccountDaily => ({
  id, account_id:'a', uid:'uid-a', stat_date:date, data_state:'record', fans_net:16,
  view:2402, like_count:43, comment_count:9, fetched_at:'2026-11-01T12:00:00+08:00', ...values,
}) as AnalyticsAccountDaily;

test('yesterday uses one account-day row and excludes today and other accounts', () => {
  const result = accountDailySummary([fact('today','2026-11-01'),fact('other','2026-10-31',{account_id:'b',uid:'uid-b',view:9999}),fact('ok','2026-10-31')], 'a','uid-a','2026-10-31');
  assert.deepEqual(result, {date:'2026-10-31',targetDate:'2026-10-31',status:'yesterday',follows:16,views:2402,hearts:43,comments:9});
});

test('failed or incomplete yesterday falls back to the latest complete earlier date', () => {
  const result = accountDailySummary([fact('old','2026-10-28'),fact('recent','2026-10-30',{view:123}),fact('incomplete','2026-10-31',{comment_count:undefined}),fact('failed','2026-10-31',{data_state:'failed',view:99999})],'a','uid-a','2026-10-31');
  assert.equal(result.status,'previous');assert.equal(result.date,'2026-10-30');assert.equal(result.views,123);assert.equal(result.comments,9);
});

test('confirmed zeros and negative follower movement remain valid', () => {
  const result = accountDailySummary([fact('zero','2026-10-31',{data_state:'confirmed_zero',fans_net:-3,view:0,like_count:0,comment_count:0})],'a','uid-a','2026-10-31');
  assert.equal(result.status,'yesterday');assert.equal(result.follows,-3);assert.equal(result.views,0);assert.equal(result.hearts,0);assert.equal(result.comments,0);
});

test('missing, nonfinite or invalid data stays unknown instead of becoming zero', () => {
  const result = accountDailySummary([fact('nan','2026-10-31',{view:NaN}),fact('negative','2026-10-30',{like_count:-1}),fact('inf','2026-10-29',{fans_net:Infinity})],'a','uid-a','2026-10-31');
  assert.equal(result.status,'missing');assert.equal(result.date,null);
  assert.deepEqual([result.follows,result.views,result.hearts,result.comments],[null,null,null,null]);
});

test('cached UID-only facts can be used and same-day snapshots do not accumulate', () => {
  const result = accountDailySummary([fact('old','2026-10-31',{view:1,fetched_at:'2026-11-01T10:00:00+08:00'}),fact('cached','2026-10-31',{account_id:'',data_state:'cached_only',view:200})],'a','uid-a','2026-10-31');
  assert.equal(result.views,200);assert.equal(result.status,'yesterday');
});
