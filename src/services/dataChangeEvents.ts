/** Shared browser event contract for targeted refreshes across V2 pages. */
export type V2DataChangeType =
  | 'production_task_changed' | 'material_changed' | 'template_changed'
  | 'video_changed' | 'video_export_changed' | 'task_changed'
  | 'release_changed' | 'revenue_changed' | 'account_changed'
  | 'drama_changed' | 'resource_changed' | 'unknown';

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
  updatedAt?: string;
};

export function eventDetail(event: Event): V2DataChangeDetail {
  const detail = (event as CustomEvent<V2DataChangeDetail>).detail;
  return detail && typeof detail === 'object' ? detail : {};
}

export function changeAffects(detail: V2DataChangeDetail, area: 'analytics' | 'assets' | 'production' | 'task_center'): boolean {
  if (detail.changeType) {
    if (area === 'analytics') return detail.changeType === 'revenue_changed' || detail.changeType === 'release_changed';
    if (area === 'assets') return ['account_changed', 'drama_changed', 'resource_changed'].includes(detail.changeType);
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
