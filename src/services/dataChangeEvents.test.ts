/**
 * 报警器（第 0 步）
 *
 * 作用：把 `dataChangeEvents.ts` 里「哪个页面该被哪种变化唤醒」的**现状**固化成断言。
 * 一旦有人改动这段逻辑，测试就会变红 —— 那是**提醒**（"这里变了，看一眼"），不是阻止。
 *
 * ⚠️ 注意：下面的断言记录的是**现在实际的行为**，不是**理想行为**。
 *    其中带「已知问题」注释的几条，是故意把缺陷也钉住的 —— 这样修好它们时测试会红，
 *    强迫改动者确认"这是有意的修复"，而不是悄悄改了没人知道。
 *
 * 跑法：`npm test`（见 package.json）
 */

import assert from 'node:assert/strict';
import { test } from 'node:test';

import { changeAffects, type V2DataChangeDetail } from './dataChangeEvents.ts';

/** 造一个只带变化类型的消息 */
const byType = (changeType: V2DataChangeDetail['changeType']): V2DataChangeDetail => ({ changeType });

/** 造一个只带请求路径的消息（没有变化类型时的兜底分支） */
const byPath = (path: string): V2DataChangeDetail => ({ path });

// ---------------------------------------------------------------- analytics

test('analytics（数据分析页）只认 收益变化 和 发布登记', () => {
  assert.equal(changeAffects(byType('revenue_changed'), 'analytics'), true);
  assert.equal(changeAffects(byType('release_changed'), 'analytics'), true);
});

test('analytics 【已知问题】不认 账号/剧集 变化', () => {
  // 现状：在资料中心改了账号名或剧集，数据分析页不会收到唤醒。
  assert.equal(changeAffects(byType('account_changed'), 'analytics'), false);
  assert.equal(changeAffects(byType('drama_changed'), 'analytics'), false);
});

// ------------------------------------------------------------------- assets

test('assets（资料中心）认 资料类 和 资源类', () => {
  for (const t of [
    'account_changed', 'drama_changed', 'theater_changed',
    'sub_theater_changed', 'profile_changed', 'resource_changed',
  ] as const) {
    assert.equal(changeAffects(byType(t), 'assets'), true, `${t} 应该唤醒资料中心`);
  }
});

test('assets 不认 生产类变化（成片/导出/模板）', () => {
  assert.equal(changeAffects(byType('video_changed'), 'assets'), false);
  assert.equal(changeAffects(byType('video_export_changed'), 'assets'), false);
  assert.equal(changeAffects(byType('template_changed'), 'assets'), false);
});

// --------------------------------------------------------------- production

test('production（生产中心）认 生产类 和 发布登记', () => {
  for (const t of [
    'production_task_changed', 'material_changed', 'template_changed',
    'video_changed', 'video_export_changed', 'release_changed', 'task_changed',
  ] as const) {
    assert.equal(changeAffects(byType(t), 'production'), true, `${t} 应该唤醒生产中心`);
  }
});

// -------------------------------------------------------------- task_center

test('task_center（任务中心）认 五个生产类', () => {
  for (const t of [
    'production_task_changed', 'template_changed', 'video_changed',
    'video_export_changed', 'task_changed',
  ] as const) {
    assert.equal(changeAffects(byType(t), 'task_center'), true, `${t} 应该唤醒任务中心`);
  }
});

test('task_center 【已知问题】不认 material_changed 和 release_changed', () => {
  // 现状：素材扫描完成、发布登记完成，任务中心不会收到唤醒。
  assert.equal(changeAffects(byType('material_changed'), 'task_center'), false);
  assert.equal(changeAffects(byType('release_changed'), 'task_center'), false);
});

// ----------------------------------------------------- 没有变化类型时按路径

test('没有 changeType 时：路径为空 → 兜底全刷（true）', () => {
  assert.equal(changeAffects({}, 'production'), true);
  assert.equal(changeAffects({}, 'task_center'), true);
});

test('没有 changeType 时：按请求路径判断', () => {
  assert.equal(changeAffects(byPath('/api/v2/revenue/source-data'), 'analytics'), true);
  assert.equal(changeAffects(byPath('/api/v2/dramas'), 'analytics'), false);

  assert.equal(changeAffects(byPath('/api/v2/production-resources'), 'assets'), true);
  assert.equal(changeAffects(byPath('/api/v2/revenue/source-data'), 'assets'), false);

  assert.equal(changeAffects(byPath('/api/v2/production-tasks/abc/scan'), 'production'), true);
  assert.equal(changeAffects(byPath('/api/v2/revenue/source-data'), 'production'), false);

  assert.equal(changeAffects(byPath('/api/v2/task-center'), 'task_center'), true);
  assert.equal(changeAffects(byPath('/api/v2/revenue/source-data'), 'task_center'), false);
});

// ------------------------------------------------- 这一条专门看「未知类型」

test('unknown 类型不唤醒任何区域', () => {
  assert.equal(changeAffects(byType('unknown'), 'analytics'), false);
  assert.equal(changeAffects(byType('unknown'), 'assets'), false);
  assert.equal(changeAffects(byType('unknown'), 'production'), false);
  assert.equal(changeAffects(byType('unknown'), 'task_center'), false);
});
