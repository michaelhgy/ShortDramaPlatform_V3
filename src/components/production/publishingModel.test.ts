import assert from 'node:assert/strict';
import { test } from 'node:test';
import { expandedPreview, expandedTimeline, effectiveGroups, coverForVideo, moveVideo } from './publishingModel.ts';
import type { PublishGroup, PublishContext, PublishSettings } from '../../api/publishing.ts';

const videos = [{ id: 'a', name: '视频1' }, { id: 'b', name: '视频2' }] as PublishContext['videos'];
const group = { id: 'g', video_ids: ['b', 'a'], copies: 2, interval: 7, start_time: '2030-01-01 12:00', schedule_type: 'timing', order: 'round' } as PublishGroup;
test('preview preserves selected order, copies, and minute offsets', () => {
  const rows = expandedPreview(group, videos);
  assert.deepEqual(rows.map(v => v.video.id), ['b', 'a', 'b', 'a']);
  assert.equal(rows[3].time, '2030-01-01 12:21');
});
test('one task schedule connects the next group after all copies', () => {
  const settings = { groups: [{ ...group, kind: 'normal', video_ids: ['a'] }, { ...group, id: 'sheep', kind: 'sheep', video_ids: ['b'], copies: 1 }],
    schedule: { schedule_type: 'timing', start_time: '2030-01-01 12:00', interval: 7 } } as PublishSettings;
  const rows = expandedTimeline(settings, videos);
  assert.deepEqual(rows.map(r => r.time), ['2030-01-01 12:00', '2030-01-01 12:07', '2030-01-01 12:14']);
  assert.equal(effectiveGroups(settings)[1].start_time, '2030-01-01 12:14');
});
test('group order and day rollover apply to the whole timeline', () => {
  const settings = { groups: [{ ...group, kind: 'normal', video_ids: ['a'], copies: 1 }, { ...group, id: 'sheep', kind: 'sheep', video_ids: ['b'], copies: 1 }],
    group_order: 'sheep_first', schedule: { schedule_type: 'localTiming', start_time: '2030-01-01 23:58', interval: 7 } } as PublishSettings;
  const rows = expandedTimeline(settings, videos);
  assert.equal(rows[0].video.id, 'b');assert.equal(rows[1].time, '2030-01-02 00:05');
});
test('each actual video kind chooses the corresponding cover, without requiring an image', () => {
  const data = { cover: { exists: true, path: 'normal.png', url: '' }, sheep_cover: { exists: false, path: '', url: '' } };
  assert.equal(coverForVideo(data, false)?.path, 'normal.png');assert.equal(coverForVideo(data, true)?.exists, false);
});
test('consecutive copies and immediate mode have explicit behavior', () => {
  const rows = expandedPreview({ ...group, order: 'consecutive', schedule_type: 'now' }, videos);
  assert.deepEqual(rows.map(v => v.video.id), ['b', 'b', 'a', 'a']);
  assert.ok(rows.every(v => v.time === '立即模式'));
});
test('moving a video leaves exactly one owner and deselection preserves other videos', () => {
  const groups = [group, { ...group, id: 'other', video_ids: [] }];
  const moved = moveVideo(groups, 'other', 'a', true);
  assert.deepEqual(moved.map(g => g.video_ids), [['b'], ['a']]);
  assert.deepEqual(moveVideo(moved, 'other', 'a', false).map(g => g.video_ids), [['b'], []]);
});
