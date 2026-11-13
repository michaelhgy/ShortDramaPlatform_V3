import assert from 'node:assert/strict';
import { test } from 'node:test';
import { newPublishProfile, taskProfileState, profileMatchesSettings } from './publishingProfileModel.ts';
import type { ProfileLibrary, PublishSettings } from '../../api/publishing.ts';

const profile = { ...newPublishProfile(), id: 'p', name: '日常', revision: 1 };
const library: ProfileLibrary = { items: [profile], account_default_id: null, software_default_id: 'p' };
const settings = {
  account_id: 'account', drama_id: 'drama', port: 9222,
  schedule: { schedule_type: 'timing', interval: 3, start_time: '2030-01-01 12:00' }, group_order: 'normal_first',
  groups: [{ ...profile.config.groups.normal, id: 'g', name: '正剧视频', kind: 'normal', video_ids: ['v'], title: '', cover_mode: 'auto', schedule_type: 'timing', start_time: '2030-01-01 12:00', interval: 3, location: null, mount_required: true }],
  profile_ref: { id: 'p', name: '日常', revision: 1, scopes: ['schedule', 'copies'], baseline: { root: { schedule_type: 'timing', interval: 3 }, groups: { normal: { copies: 1 } } } },
} as PublishSettings;

test('profile adjustment status covers managed settings and excludes task clock and unrelated text', () => {
  const value = structuredClone(settings); value.schedule!.start_time = '2030-02-01 17:29'; value.groups[0].desc = '本次简介';
  assert.equal(taskProfileState(value, library)?.modified, false);
  value.groups[0].copies = 3;
  assert.equal(taskProfileState(value, library)?.modified, true);
});

test('profile library rename, update and deletion are separate from applied task snapshot', () => {
  const updated = { ...library, items: [{ ...profile, name: '日常新版', revision: 2 }] };
  assert.deepEqual(taskProfileState(settings, updated), { id: 'p', name: '日常新版', modified: false, deleted: false, update_available: true });
  assert.equal(taskProfileState(settings, { ...library, items: [] })?.deleted, true);
  assert.equal(settings.profile_ref?.revision, 1);
});

test('address comparisons ignore JSON object key order', () => {
  const value = structuredClone(settings);
  value.profile_ref!.baseline.groups.normal.location = { name: '地点', poiCheckSum: 'a' };
  value.groups[0].location = { poiCheckSum: 'a', name: '地点' } as typeof value.groups[0]['location'];
  assert.equal(taskProfileState(value, library)?.modified, false);
});

test('configuration consistency compares all reusable fields and excludes the task clock and profile metadata', () => {
  const value=structuredClone(settings);value.sync_location=true;
  assert.equal(profileMatchesSettings(value,profile),true);
  value.schedule!.start_time='2030-02-01 19:37';value.groups[0].shoot_date='2030-01-01';
  assert.equal(profileMatchesSettings(value,{...profile,name:'改名',revision:2}),true);
  value.groups[0].desc='没有套用的文案';
  assert.equal(profileMatchesSettings(value,profile),false);
});

test('configuration consistency includes address sync and independently configured sheep mounting', () => {
  const value=structuredClone(settings);value.sync_location=true;
  value.groups.push({...value.groups[0],id:'s',kind:'sheep',mount_required:false});
  assert.equal(profileMatchesSettings(value,profile),true);
  value.groups[1].mount_required=true;assert.equal(profileMatchesSettings(value,profile),false);
  value.groups[1].mount_required=false;value.sync_location=false;assert.equal(profileMatchesSettings(value,profile),false);
});


test('configuration matching and changed marker include cover choice and reusable image', () => {
  const expected = structuredClone(profile);
  expected.config.location.mode = 'none';
  expected.config.groups.normal.cover_mode = 'custom';
  expected.config.groups.normal.cover_source = 'custom';
  expected.config.groups.normal.custom_cover_id = 'a'.repeat(64);
  const value = structuredClone(settings);
  value.sync_location = expected.config.location.sync;
  Object.assign(value.groups[0], expected.config.groups.normal);
  assert.equal(profileMatchesSettings(value, expected), true);
  value.profile_ref!.baseline.groups.normal = { cover_mode: 'custom', cover_source: 'custom', custom_cover_id: 'a'.repeat(64) };
  assert.equal(taskProfileState(value, library)?.modified, false);
  value.groups[0].cover_mode = 'none';
  assert.equal(profileMatchesSettings(value, expected), false);
  assert.equal(taskProfileState(value, library)?.modified, true);
  assert.equal(value.groups[0].custom_cover_id, 'a'.repeat(64));
});
