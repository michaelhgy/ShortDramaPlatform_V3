/**
 * `reuseUnchanged` 的报警器
 *
 * 要钉住的核心契约只有一条：
 * **内容没变时，必须返回"同一个引用"** —— 因为 React 靠引用相等跳过重画，
 * 这正是"不卡、不闪"的关键（用户 2026-09-18 的历史经验）。
 *
 * 跑法：`npm test`
 */

import assert from 'node:assert/strict';
import { test } from 'node:test';

import { reuseUnchanged, reuseUnchangedRecord } from './reuseUnchanged.ts';

type Item = { id: string; name: string; count: number };

const item = (id: string, name = 'x', count = 0): Item => ({ id, name, count });

// ------------------------------------------------------------------ 数组版

test('内容完全相同（但是新对象）：返回原数组引用', () => {
  const previous: Item[] = [item('a'), item('b')];
  const next: Item[] = [item('a'), item('b')];

  const result = reuseUnchanged(previous, next);

  assert.equal(result, previous, '必须返回同一个数组引用，React 才会跳过重画');
  assert.equal(result[0], previous[0], '元素本身也要沿用旧引用');
  assert.equal(result[1], previous[1]);
});

test('有一条真的变了：数组是新的，但只有那条是新引用', () => {
  const a = item('a');
  const b = item('b');
  const previous: Item[] = [a, b];
  const next: Item[] = [item('a'), item('b', 'y', 5)];

  const result = reuseUnchanged(previous, next);

  assert.notEqual(result, previous, '有变化就不能沿用整个数组');
  assert.equal(result[0], a, '没变的那条要沿用旧引用');
  assert.equal(result[1], next[1], '变了的那条用新对象');
});

test('顺序变了：不能沿用旧数组（否则界面顺序会错）', () => {
  const previous: Item[] = [item('a'), item('b')];
  const next: Item[] = [item('b'), item('a')];

  const result = reuseUnchanged(previous, next);

  assert.notEqual(result, previous);
  assert.deepEqual(result.map((entry) => entry.id), ['b', 'a']);
});

test('新增条目：返回新数组，旧条目仍沿用旧引用', () => {
  const a = item('a');
  const result = reuseUnchanged([a], [item('a'), item('b')]);

  assert.equal(result.length, 2);
  assert.equal(result[0], a);
  assert.equal(result[1].id, 'b');
});

test('减少条目：返回新数组', () => {
  const result = reuseUnchanged([item('a'), item('b')], [item('a')]);
  assert.equal(result.length, 1);
  assert.equal(result[0].id, 'a');
});

test('两边都空：返回原数组引用', () => {
  const previous: Item[] = [];
  assert.equal(reuseUnchanged(previous, []), previous);
});

test('旧的是空、新的非空：用新的', () => {
  const previous: Item[] = [];
  const next: Item[] = [item('a')];
  assert.equal(reuseUnchanged(previous, next), next);
});

test('同一条数据连续对比两次：第二次仍返回第一次的结果（不会越比越新）', () => {
  const previous: Item[] = [item('a'), item('b')];
  const first = reuseUnchanged(previous, [item('a'), item('b')]);
  const second = reuseUnchanged(first, [item('a'), item('b')]);
  assert.equal(first, previous);
  assert.equal(second, previous);
});

// ------------------------------------------------------------ 字典版（详情）

test('字典版：内容没变 → 返回原字典引用', () => {
  const previous = { a: item('a'), b: item('b') };
  const result = reuseUnchangedRecord(previous, { a: item('a'), b: item('b') });

  assert.equal(result, previous);
  assert.equal(result.a, previous.a);
});

test('字典版：有一条变了 → 新字典，且只有那条是新对象', () => {
  const previous = { a: item('a'), b: item('b') };
  const result = reuseUnchangedRecord(previous, { a: item('a'), b: item('b', 'y', 9) });

  assert.notEqual(result, previous);
  assert.equal(result.a, previous.a, '没变的沿用旧引用');
  assert.notEqual(result.b, previous.b, '变了的换新对象');
});

test('字典版：新增键 → 新字典', () => {
  const previous = { a: item('a') };
  const result = reuseUnchangedRecord(previous, { a: item('a'), b: item('b') });
  assert.notEqual(result, previous);
  assert.equal(result.a, previous.a);
  assert.equal(result.b.id, 'b');
});
