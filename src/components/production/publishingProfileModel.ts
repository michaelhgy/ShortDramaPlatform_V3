import type { PublishProfile, PublishProfileConfig, ProfileGroup, ProfileLibrary, ProfileState, PublishSettings, ProfileScope, LocationValue } from '../../api/publishing';

export const profileScopes: { key: ProfileScope; label: string }[] = [
  { key: 'cover', label: '封面设置' }, { key: 'schedule', label: '排期规则' }, { key: 'copies', label: '份数与排列' }, { key: 'text', label: '文案与追评' },
  { key: 'declaration', label: '视频声明与原创' }, { key: 'location_mount', label: '地址与挂载' },
];
export const sharedProfileKeys = ['video_title', 'desc', 'tags', 'short_title', 'comment', 'comment_top', 'tag_type', 'original', 'repost_source', 'shoot_region_codes'] as const;
export const cloneProfile = <T,>(value: T): T => structuredClone(value);
export function defaultProfileGroup(): ProfileGroup {
  return { cover_mode: 'auto', cover_source: 'auto', custom_cover_id: '', copies: 1, order: 'round', mount_required: true, video_title: '', desc: '', tags: [], short_title: '', comment: '', comment_top: false, tag_type: 0, original: false, repost_source: '', shoot_region_codes: [] };
}
export function newPublishProfile(): PublishProfile {
  const config: PublishProfileConfig = { schedule: { schedule_type: 'timing', interval: 3 }, group_order: 'normal_first', sheep_inherit: true,
    groups: { normal: defaultProfileGroup(), sheep: { ...defaultProfileGroup(), mount_required: false } }, location: { mode: 'account', checksum: '', sync: true } };
  return { id: '', name: '新方案', revision: 0, config };
}
function canonical(value: unknown): string {
  if (value && typeof value === 'object' && !Array.isArray(value)) return JSON.stringify(Object.fromEntries(Object.entries(value).sort(([a], [b]) => a.localeCompare(b)).map(([k, v]) => [k, canonical(v)])));
  if (Array.isArray(value)) return JSON.stringify(value.map(canonical));
  return JSON.stringify(value ?? null);
}
export function profileMatchesSettings(settings: PublishSettings, profile?: PublishProfile, accountAddress?: LocationValue | null, addresses: LocationValue[] = []): boolean {
  if (!profile) return false;
  const config=profile.config;
  if (settings.schedule?.schedule_type !== config.schedule.schedule_type || settings.schedule?.interval !== config.schedule.interval || settings.group_order !== config.group_order || settings.sync_location !== config.location.sync) return false;
  const location=config.location.mode === 'account' ? accountAddress ?? null : config.location.mode === 'public' ? addresses.find(a => a.poiCheckSum === config.location.checksum) : null;
  if (config.location.mode === 'public' && !location) return false;
  for (const group of settings.groups) {
    if (group.kind !== 'normal' && group.kind !== 'sheep') continue;
    const expected={...config.groups[group.kind]};
    if (group.kind === 'sheep' && config.sheep_inherit) for (const key of sharedProfileKeys) Object.assign(expected,{[key]:config.groups.normal[key]});
    for (const [key,value] of Object.entries(expected)) {
      const actual=(group as unknown as Record<string,unknown>)[key] ?? (key === 'short_title' ? group.title : (defaultProfileGroup() as unknown as Record<string,unknown>)[key]);
      if (canonical(actual) !== canonical(value)) return false;
    }
    if (canonical(group.location ?? null) !== canonical(location)) return false;
  }
  return true;
}
export function taskProfileState(settings: PublishSettings, library?: ProfileLibrary): ProfileState | null {
  const ref = settings.profile_ref;
  if (!ref) return null;
  const live = library?.items.find(p => p.id === ref.id);
  let modified = Object.entries(ref.baseline.root).some(([key, value]) => canonical(key === 'group_order' ? settings.group_order : key === 'sync_location' ? settings.sync_location : settings.schedule?.[key as 'schedule_type' | 'interval']) !== canonical(value));
  const defaults = defaultProfileGroup() as unknown as Record<string, unknown>;
  for (const group of settings.groups) for (const [key, value] of Object.entries(ref.baseline.groups[group.kind || ''] || {})) {
    if (canonical((group as unknown as Record<string, unknown>)[key] ?? defaults[key]) !== canonical(value)) modified = true;
  }
  return { id: ref.id, name: live?.name || ref.name, modified, deleted: !live, update_available: Boolean(live && live.revision !== ref.revision) };
}
