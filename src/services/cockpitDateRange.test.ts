import assert from 'node:assert/strict';
import test from 'node:test';
import { dateInRange, dateRangeError, resolveCockpitDateRange } from './cockpitDateRange.ts';

test('rolling windows include the exact number of days ending yesterday across years and leap days', () => {
  const bounds = resolveCockpitDateRange('14days', '2027-01-05');
  assert.deepEqual(bounds, { start: '2026-12-22', end: '2027-01-04', days: 14, label: '近14天' });
  assert.equal(resolveCockpitDateRange('7days', '2024-03-02').start, '2024-02-24');
  assert.equal(resolveCockpitDateRange('30days', '2026-11-01').days, 30);
});

test('this month begins on the first and includes today, even on month rollover', () => {
  assert.deepEqual(resolveCockpitDateRange('month', '2026-11-01'), {
    start: '2026-11-01', end: '2026-11-01', days: 1, label: '本月',
  });
  assert.equal(resolveCockpitDateRange('month', '2024-02-29').days, 29);
});

test('single-day and custom ranges include both endpoints and exclude adjacent dates', () => {
  const day = resolveCockpitDateRange({ kind: 'day', date: '2026-10-15' }, '2026-11-01');
  assert.equal(day.days, 1);
  assert.equal(dateInRange('2026-10-15', day), true);
  assert.equal(dateInRange('2026-10-16', day), false);
  const range = resolveCockpitDateRange({ kind: 'range', start: '2026-10-30', end: '2026-11-01' }, '2026-11-01');
  assert.equal(range.days, 3);
  assert.equal(dateInRange('2026-10-30', range), true);
  assert.equal(dateInRange('2026-11-01', range), true);
  assert.equal(dateInRange('2026-11-02', range), false);
});

test('empty, invalid, reversed and future dates cannot be applied', () => {
  for (const [start, end] of [['', ''], ['2026-02-29', '2026-03-01'], ['2026-10-20', '2026-10-19'], ['2026-11-01', '2026-11-02']]) {
    assert.notEqual(dateRangeError(start, end, '2026-11-01'), '');
    assert.throws(() => resolveCockpitDateRange({ kind: 'range', start, end }, '2026-11-01'), RangeError);
  }
  assert.equal(dateRangeError('2024-02-29', '2024-02-29', '2026-11-01'), '');
});
