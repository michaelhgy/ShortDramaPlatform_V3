/** Shared browser event contract for targeted refreshes across V2 pages. */
export type V2DataChangeType =
  | 'production_task_changed' | 'material_changed' | 'template_changed'
  | 'video_changed' | 'video_export_changed' | 'task_changed'
  | 'release_changed' | 'revenue_changed' | 'account_changed'
  | 'drama_changed' | 'theater_changed' | 'sub_theater_changed'
  | 'profile_changed' | 'settings_changed' | 'resource_changed' | 'unknown';

export type V2DataChangeDetail = {
  path?: string;
  method?: string;
  changeType?: V2DataChangeType;
  accountId?: string;
  dramaId?: string;
  productionTaskId?: string;
  taskId?: string;
  videoId?: string;
  materialId?: string;
  entityId?: string;
  updatedAt?: string;
  /** Database event id when the notification came from the local change feed. */
  eventId?: number;
  /** A local mutation is published immediately; the later database echo is ignored once. */
  origin?: 'client' | 'feed';
};

const recentClientChanges = new Map<string, number>();

function changeScope(detail: V2DataChangeDetail): string {
  return [
    detail.changeType || 'unknown', detail.productionTaskId || detail.taskId || detail.videoId
      || detail.materialId || detail.accountId || detail.dramaId || detail.entityId || detail.path || '',
  ].join(':');
}

/**
 * Publish the one application-wide data-change event.
 *
 * A button save reaches the page immediately. SQLite then reports the same
 * write through the feed shortly afterwards. Keeping that second echo from
 * starting another refresh is important, but real later background changes
 * are never permanently ignored.
 */
export function publishV2DataChange(detail: V2DataChangeDetail): void {
  const now = Date.now();
  const scope = changeScope(detail);
  if (detail.origin === 'feed') {
    const clientAt = recentClientChanges.get(scope);
    if (clientAt && now - clientAt < 2500) return;
  }
  if (detail.origin === 'client') recentClientChanges.set(scope, now);
  for (const [key, at] of recentClientChanges) {
    if (now - at > 10_000) recentClientChanges.delete(key);
  }
  window.dispatchEvent(new CustomEvent('v2-data-changed', { detail }));
}

export function eventDetail(event: Event): V2DataChangeDetail {
  const detail = (event as CustomEvent<V2DataChangeDetail>).detail;
  return detail && typeof detail === 'object' ? detail : {};
}

export function changeAffects(detail: V2DataChangeDetail, area: 'analytics' | 'assets' | 'production' | 'task_center'): boolean {
  if (detail.changeType) {
    if (area === 'analytics') return detail.changeType === 'revenue_changed' || detail.changeType === 'release_changed';
    if (area === 'assets') return ['account_changed', 'drama_changed', 'theater_changed', 'sub_theater_changed', 'profile_changed', 'resource_changed'].includes(detail.changeType);
    if (area === 'production') return ['production_task_changed', 'material_changed', 'template_changed', 'video_changed', 'video_export_changed', 'release_changed', 'task_changed'].includes(detail.changeType);
    return ['production_task_changed', 'template_changed', 'video_changed', 'video_export_changed', 'task_changed'].includes(detail.changeType);
  }
  const path = detail.path || '';
  if (!path) return true;
  if (area === 'analytics') return path.includes('/revenue/');
  if (area === 'assets') return /\/catalog|\/production-resources|\/drama-profiles/.test(path);
  if (area === 'production') return /\/production-/.test(path) || path.includes('/task-center');
  return path.includes('/task-center') || path.includes('/production-');
}
