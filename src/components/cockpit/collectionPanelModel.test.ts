import test from 'node:test';
import assert from 'node:assert/strict';
import { accountProgress, buildCollectionRequest, entryCategories, recentPublicationRange, validDateRange, type CollectionDraft } from './collectionPanelModel.ts';
import type { CollectionJob } from '../../api/operationsDashboard.ts';
const draft = (changes: Partial<CollectionDraft> = {}): CollectionDraft => ({
  accountIds: ['a'], categories: ['daily'], interval: '2', cooldown: '1', forceWorks: false,
  dailyMode: 'fill_missing', dailyStart: '2026-11-01', dailyEnd: '2026-11-02',
  worksMode: 'all', worksStart: '2026-10-28', worksEnd: '2026-11-03',
  revenueMode: 'routine', revenueStart: '2026-11-01', revenueEnd: '2026-11-02', ...changes,
});
test('日常补齐不主动选视频，收益只在接口确认就绪时加入', () => {
  assert.deepEqual(entryCategories('routine'), ['daily', 'optimization']);
  assert.deepEqual(entryCategories('routine', {version: 1, revenue: true}), ['daily', 'optimization', 'revenue']);
  assert.deepEqual(entryCategories('works'), ['works']);
});
test('日数据附带账号总量，兼容旧后端，不发送不受支持的范围', () => {
  const request = buildCollectionRequest(draft(), '2026-11-02');
  assert.deepEqual(request.options?.categories, ['daily', 'profile']);
  assert.equal(request.options?.scope, undefined);
  assert.equal(request.options?.force_works, false);
});
test('范围与强制能力未接入时明确阻止，不能默默全量', () => {
  for (const changes of [
    {dailyMode: 'force_range'} as const,
    {categories: ['works'], worksMode: 'recent7'} as Partial<CollectionDraft>,
    {categories: ['revenue']} as Partial<CollectionDraft>,
  ]) {
    const result = buildCollectionRequest(draft(changes), '2026-11-02');
    assert.ok(result.error?.includes('接入')); assert.equal(result.options, undefined);
  }
});
test('视频近7天含今天，范围只传给作品，作品强制不影响其他类别', () => {
  const result = buildCollectionRequest(draft({categories: ['daily', 'works'], worksMode: 'recent7', forceWorks: true}), '2026-11-02', {version: 1, works_publication_range: true});
  assert.deepEqual(result.options?.scope, {daily: {mode: 'fill_missing'}, works: {mode: 'published_range', start_date: '2026-10-28', end_date: '2026-11-03'}});
  assert.equal(result.options?.force_works, true);
  assert.deepEqual(recentPublicationRange('2026-02-28', 7), {start: '2026-02-23', end: '2026-03-01'});
});
test('强制日数据限定账号日期，不能选今天', () => {
  const caps = {version: 1, daily_force_range: true} as const;
  assert.deepEqual(buildCollectionRequest(draft({dailyMode: 'force_range'}), '2026-11-02', caps).options?.scope?.daily, {mode: 'force_range', start_date: '2026-11-01', end_date: '2026-11-02'});
  assert.ok(buildCollectionRequest(draft({dailyMode: 'force_range', dailyEnd: '2026-11-03'}), '2026-11-02', caps).error);
});
test('收益只提交自动补齐，拒绝前端指定日期，不在前端判断首次完成', () => {
  const caps = {version: 1, revenue: true} as const;
  assert.deepEqual(buildCollectionRequest(draft({categories: ['revenue']}), '2026-11-02', caps).options?.scope?.revenue, {mode: 'routine'});
  assert.match(buildCollectionRequest(draft({categories: ['revenue'], revenueMode: 'date_range'}), '2026-11-02', caps).error!, /后台/);
});
test('日期校验拒绝不存在、倒置和未来日期', () => {
  assert.equal(validDateRange('2026-02-30', '2026-03-01', '2026-11-02'), false);
  assert.equal(validDateRange('2026-11-02', '2026-11-01', '2026-11-02'), false);
  assert.equal(validDateRange('', '', '2026-11-02'), false);
});
test('阻止空账号、空类别和无效翻页参数', () => {
  assert.ok(buildCollectionRequest(draft({accountIds: []}), '2026-11-02').error);
  assert.ok(buildCollectionRequest(draft({categories: []}), '2026-11-02').error);
  assert.ok(buildCollectionRequest(draft({categories: ['works'], interval: ''}), '2026-11-02').error);
  assert.ok(buildCollectionRequest(draft({categories: ['works'], cooldown: '-1'}), '2026-11-02').error);
});
test('按账号汇总，停止和失败不计完成，跳过计完成', () => {
  const items = [
    {account_id: 'a', account_name: '甲', status: 'success'}, {account_id: 'a', account_name: '甲', status: 'skipped'},
    {account_id: 'b', account_name: '乙', status: 'success'}, {account_id: 'b', account_name: '乙', status: 'stopped'},
    {account_id: 'c', account_name: '丙', status: 'failed'},
  ];
  const groups = accountProgress({items} as CollectionJob);
  assert.equal(groups.length, 3); assert.equal(groups.filter(group => group.done).length, 1);
  assert.equal(groups.filter(group => group.needsAttention).length, 2);
});

test('在线重置只传每日数据模式，不带日期；缺能力时禁止静默执行普通补缺',()=>{
 assert.ok(buildCollectionRequest(draft({dailyMode:'reset_online'}), '2026-11-02').error);
 const result=buildCollectionRequest(draft({dailyMode:'reset_online'}), '2026-11-02', {version:1,daily_reset_online:true});
 assert.deepEqual(result.options?.scope, {daily:{mode:'reset_online'}});
 assert.deepEqual(result.options?.categories, ['daily','profile']);
 assert.equal(result.options?.force_works, false);
});


test('混合采集明确发送平台账号子集，停用收益不会顺带触发平台请求',()=>{
 const result=buildCollectionRequest(draft({accountIds:['a','paused'],platformAccountIds:['a'],categories:['daily','revenue']}),'2026-11-02',{version:1,revenue:true});
 assert.equal(result.error,undefined);assert.deepEqual(result.options?.account_ids,['a','paused']);
 assert.deepEqual(result.options?.platform_account_ids,['a']);
 assert.deepEqual(buildCollectionRequest(draft({platformAccountIds:[]}),'2026-11-02').options?.platform_account_ids,[]);
});
