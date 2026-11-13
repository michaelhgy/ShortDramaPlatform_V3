import type { ProductionPublishItem, ProductionPublishProgress, ProductionPublishCard } from '../../api/publishing';

export type VideoPublication = { kind: 'publication' | 'draft'; items: ProductionPublishItem[] };
const completed = new Set(['success', 'ready']);
const problems = new Set(['uncertain', 'needs_help', 'failed', 'rejected', 'canceled']);
export const publicationStatus: Record<string, string> = {
  pending: '待提交', submitting: '正在提交', submitted: '排队中', publishing: '小V猫正在处理',
  success: '发布提交成功', failed: '发布失败', rejected: '提交未完成', uncertain: '结果待核对',
  needs_help: '需要处理', canceled: '已取消', paused: '小V猫已暂停', localTiming: '等待本机定时',
  creating: '正在创建草稿', checking: '正在核对草稿', ready: '草稿已就绪',
};

export function publicationsByVideo(data: ProductionPublishProgress | null): Record<string, VideoPublication> {
  if (!data) return {};
  const result: Record<string, VideoPublication> = {};
  for (const kind of ['draft', 'publication'] as const) {
    const groups = new Map<string, ProductionPublishItem[]>();
    for (const item of (kind === 'publication' ? data.publication : data.drafts).items) {
      if (!item.video_id) continue;
      groups.set(item.video_id, [...(groups.get(item.video_id) || []), item]);
    }
    for (const [id, items] of groups) {
      const previous = result[id];
      const newest = (rows: ProductionPublishItem[]) => rows.reduce((s, r) => r.submitted_at > s ? r.submitted_at : s, '');
      if (!previous || newest(items) >= newest(previous.items)) result[id] = { kind, items: [...items].sort((a, b) => a.copy - b.copy) };
    }
  }
  return result;
}

export function publicationCounts(items: ProductionPublishItem[]) {
  return { total: items.length, done: items.filter(i => completed.has(i.status)).length,
    processing: items.filter(i => ['submitting', 'publishing', 'creating', 'checking'].includes(i.status)).length,
    queued: items.filter(i => ['pending', 'submitted', 'localTiming'].includes(i.status)).length,
    paused: items.filter(i => i.status === 'paused').length, issues: items.filter(i => problems.has(i.status)).length };
}

export function publicationSummary(value: VideoPublication) {
  const n = publicationCounts(value.items);
  const allDone = n.total > 0 && n.done === n.total;
  const delivered = value.kind === 'publication' && value.items.every(i => i.status === 'success' && i.delivery_confirmed);
  const doneLabel = value.kind === 'draft' ? '小V猫草稿已就绪' : delivered ? (value.items.every(i => i.schedule_type === 'timing') ? '官方已定时' : '发布完成') : value.items.every(i => i.schedule_type === 'timing') ? '定时已提交' : '发布提交成功';
  const parts = [allDone ? `${doneLabel} ${n.done}/${n.total} 份` : `已${value.kind === 'draft' ? '就绪' : '提交'} ${n.done}/${n.total} 份`];
  if (n.processing) parts.push(`${n.processing} 份处理中`);
  if (n.queued) parts.push(`${n.queued} 份${value.kind === 'draft' ? '待处理' : '排队'}`);
  if (n.paused) parts.push(`${n.paused} 份已暂停`);
  if (n.issues) parts.push(`${n.issues} 份待处理`);
  return { text: parts.join(' · '), tone: n.issues || n.paused ? 'amber' : allDone ? (value.kind === 'draft' ? 'violet' : 'emerald') : 'blue', ...n };
}

export function publicationTime(value: VideoPublication) {
  const times = value.items.map(i => i.time).filter(Boolean).sort();
  if (!times.length) return value.kind === 'draft' ? '小V猫本地草稿' : '立即发布';
  const first = times[0], last = times[times.length - 1];
  const format = (time: string) => time.replace(/^\d{4}-(\d{2})-(\d{2})[ T]/, (_, m, d) => `${Number(m)}月${Number(d)}日 `);
  const tail = first === last ? '' : `—${first.slice(0, 10) === last.slice(0, 10) ? last.slice(11, 16) : format(last)}`;
  return `${value.kind === 'draft' ? '草稿计划 · ' : ''}${format(first)}${tail}`;
}

export function publicationMount(value?: VideoPublication) {
  const rows = value?.items.filter(i => i.submitted) || [];
  if (!rows.length) return null;
  const mounted = rows.filter(i => i.mount.enabled);
  const text = mounted.length === rows.length ? '挂载' : mounted.length ? '挂载不一致' : '未挂载';
  const titles = rows.map(i => i.mount.enabled ? `${i.mount.source === 'channels_drama' ? '视频号剧集' : '小程序短剧'} · ${i.mount.name}` : (i.mount.source === 'plugin' ? '未挂载 · 小V猫本地草稿，待插件处理' : '未挂载'));
  return { text, title: `${[...new Set(titles)].join('；')}。按提交时的设置显示。`, tone: mounted.length === rows.length ? 'emerald' : mounted.length ? 'amber' : 'slate' };
}

export function publicationLocation(values: Record<string, VideoPublication>) {
  const rows = Object.values(values).flatMap(v => v.items).filter(i => i.submitted);
  if (!rows.length) return null;
  const label = (row: ProductionPublishItem) => row.location.name || '不显示位置';
  const locations = [...new Set(rows.map(label))];
  const detail = [...new Set(rows.map(r => `${r.group_name || '视频'} · ${label(r)}${r.location.full_address ? `（${r.location.full_address}）` : ''}`))].join('；');
  const text = locations.length === 1 ? locations[0] : [...new Set(rows.map(r => `${r.group_name.replace(/视频$/, '') || '视频'} · ${label(r)}`))].join(' ｜ ');
  return { text, title: detail };
}

export function publicationCard(values: Record<string, VideoPublication>): ProductionPublishCard | null {
  const rows = Object.values(values).flatMap(v => v.items);
  if (!rows.some(r => r.submitted)) return null;
  return { ...publicationCounts(rows), delivered: rows.filter(r => r.status === 'success' && r.delivery_confirmed).length, draft_only: Object.values(values).every(v => v.kind === 'draft'), scheduled: rows.every(r => r.schedule_type === 'timing') };
}

export function publicationCardStatus(card: ProductionPublishCard) {
  if (card.issues) return card.draft_only ? '草稿待处理' : '发布待处理';
  if (card.paused && !card.processing && !card.queued) return '发布已暂停';
  if (card.done === card.total) return card.draft_only ? '草稿已就绪' : card.delivered === card.total ? (card.scheduled ? '官方已定时' : '发布完成') : card.scheduled ? '定时已提交' : '发布已提交';
  return card.draft_only ? '草稿处理中' : '发布中';
}
