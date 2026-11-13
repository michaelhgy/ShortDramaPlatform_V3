import test from 'node:test';
import assert from 'node:assert/strict';
import { beijingDateString, beijingDateTimeString, shiftBeijingDateTime } from './beijingTime.ts';

test('user-facing current date and time use Beijing regardless of host timezone', () => {
  const instant = new Date('2026-10-29T16:05:06.000Z');
  assert.equal(beijingDateString(instant), '2026-10-30');
  assert.equal(beijingDateTimeString(instant), '2026-10-30 00:05');
});

test('publishing schedule arithmetic keeps Beijing wall-clock time across midnight', () => {
  assert.equal(shiftBeijingDateTime('2026-10-30 23:58', 5), '2026-10-31 00:03');
});
