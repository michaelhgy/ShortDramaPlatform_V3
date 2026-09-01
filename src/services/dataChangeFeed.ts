import { v2Client } from '../api/client';
import type { V2DataChangeDetail, V2DataChangeType } from './dataChangeEvents';

type ChangeEventRow = {
  id: number; change_type: V2DataChangeType; production_task_id: string; task_id: string;
  account_id: string; drama_id: string; video_id: string; material_id: string; updated_at: string;
};

let started = false;
let cursor: number | null = null;
let timer: number | null = null;
let fetching = false;

function dispatch(row: ChangeEventRow): void {
  const detail: V2DataChangeDetail = {
    changeType: row.change_type, productionTaskId: row.production_task_id || undefined,
    taskId: row.task_id || undefined, accountId: row.account_id || undefined,
    dramaId: row.drama_id || undefined, videoId: row.video_id || undefined,
    materialId: row.material_id || undefined, updatedAt: row.updated_at,
  };
  window.dispatchEvent(new CustomEvent('v2-data-changed', { detail }));
}

async function poll(): Promise<void> {
  if (fetching || document.hidden) return;
  fetching = true;
  try {
    const query = cursor == null ? '' : `?after_id=${cursor}`;
    const response = await v2Client.get<{ items: ChangeEventRow[]; latest_id: number }>(`/api/v2/change-events${query}`);
    cursor = response.latest_id;
    // One database action can update several rows. Keep only the last change
    // for each production task within this poll to prevent duplicate requests.
    const latestByScope = new Map<string, ChangeEventRow>();
    response.items.forEach((row) => latestByScope.set(row.production_task_id || `${row.change_type}:${row.task_id}:${row.account_id}:${row.drama_id}`, row));
    latestByScope.forEach(dispatch);
  } catch {
    // Existing pages retain their last valid data. The next poll or the normal
    // low-frequency reconciliation will recover when the local service returns.
  } finally { fetching = false; }
}

/** One application-wide lightweight change feed. Safe to call repeatedly. */
export function startV2DataChangeFeed(): () => void {
  if (started) return () => undefined;
  started = true;
  void poll();
  timer = window.setInterval(() => { void poll(); }, 1500);
  const resume = () => { if (!document.hidden) void poll(); };
  document.addEventListener('visibilitychange', resume);
  return () => {
    started = false;
    if (timer) window.clearInterval(timer);
    timer = null;
    document.removeEventListener('visibilitychange', resume);
  };
}
