import type { PublishGroup, PublishContext, PublishSettings } from '../../api/publishing';
import { shiftBeijingDateTime } from '../../utils/beijingTime.ts';

export function effectiveGroups(settings: PublishSettings): PublishGroup[] {
  const schedule = settings.schedule;
  if (!schedule) return settings.groups;
  let offset = 0;
  const first = settings.group_order === 'sheep_first' ? 'sheep' : 'normal';
  const groups = [...settings.groups].sort((a, b) => {
    const rank = (g: PublishGroup) => g.kind === first ? 0 : ['normal', 'sheep'].includes(g.kind || '') ? 1 : 2;
    return rank(a) - rank(b);
  });
  return groups.map(group => {
    const start = schedule.start_time && /^\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}/.test(schedule.start_time)
      ? shiftBeijingDateTime(schedule.start_time, offset * Math.max(0, schedule.interval || 0)) : '';
    const result = { ...group, schedule_type: schedule.schedule_type, interval: schedule.interval,
      start_time: schedule.schedule_type !== 'now' ? start : '' };
    offset += group.video_ids.length * Math.max(1, Math.floor(group.copies || 1));
    return result;
  });
}

export function expandedTimeline(settings: PublishSettings, videos: PublishContext['videos']) {
  return effectiveGroups(settings).flatMap(group => expandedPreview(group, videos).map(item => ({ ...item, groupId: group.id, groupName: group.name })));
}

export function coverForVideo(data: Pick<PublishContext, 'cover' | 'sheep_cover'>, sheep: boolean) {
  return sheep ? data.sheep_cover : data.cover;
}

export function expandedPreview(group: PublishGroup, videos: PublishContext['videos']) {
  const selected = group.video_ids.flatMap(id => videos.find(video => video.id === id) || []);
  const copies = Math.min(100, Math.max(1, Math.floor(group.copies || 1)));
  const pairs = group.order === 'round' ? Array.from({ length: copies }, (_, copy) => selected.map(video => ({ video, copy: copy + 1 }))).flat()
    : selected.flatMap(video => Array.from({ length: copies }, (_, copy) => ({ video, copy: copy + 1 })));
  return pairs.map((item, index) => {
    const date = group.start_time ? shiftBeijingDateTime(group.start_time, index * Math.max(0, group.interval || 0)) : '';
    const time = group.schedule_type === 'now' ? '立即模式' : date ? date : '待设置时间';
    return { ...item, time };
  });
}

export function moveVideo(groups: PublishGroup[], groupId: string, videoId: string, selected: boolean) {
  return groups.map(group => ({ ...group, video_ids: group.id === groupId && selected
    ? [...new Set([...group.video_ids, videoId])] : group.video_ids.filter(id => id !== videoId) }));
}
