import assert from 'node:assert/strict';
import { test } from 'node:test';
import { plannedDate, planningToday, planningDayOffset, formatPlannedDate, plannedSortTimestamp, isPlanOverdue } from './plannedDate.ts';
import { formatRelativeDateTime } from './dateDisplay.ts';

test('new dates and legacy timestamp plans display the same day without clock', () => {
  assert.equal(formatPlannedDate('2026-10-26T08:00'), '10月26日');
  assert.equal(formatPlannedDate('2026-10-11'), '10月11日');
  assert.equal(plannedSortTimestamp('2026-10-26T08:00'), plannedSortTimestamp('2026-10-26T23:59'));
  assert.equal(plannedDate('2026-02-30'), '');
  assert.equal(plannedDate('2024-02-29'), '2024-02-29');
  assert.equal(formatPlannedDate(''), '未设置计划发布日期');
  assert.ok(plannedSortTimestamp('') > plannedSortTimestamp('2030-01-01'));
});
test('planned day is not overdue until the next Shanghai calendar day', () => {
  assert.equal(isPlanOverdue('2026-10-26T08:00', new Date('2026-10-26T23:59:59+08:00')), false);
  assert.equal(isPlanOverdue('2026-10-26', new Date('2026-10-27T00:00:00+08:00')), true);
  assert.equal(isPlanOverdue('', new Date('2026-10-27T00:00:00+08:00')), false);
  assert.equal(planningToday(new Date('2026-10-26T18:00:00Z')), '2026-10-27');
  assert.equal(planningDayOffset(1, new Date('2026-12-31T12:00:00+08:00')), '2027-01-01');
});
test('actual execution time formatter still includes the original clock', () => {
  assert.match(formatRelativeDateTime('2026-10-26T18:37'), /18:37$/);
});
