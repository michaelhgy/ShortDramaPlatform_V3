import { INITIAL_DRAMA_PRIORITIES, INITIAL_EXECUTORS, INITIAL_TASKS } from '../components/taskcenter/taskCenterMockData';
import { dataSource } from './dataSource';
import { loadV2TaskCenter, loadV2TaskCenterProductionTask } from '../api/v2TaskCenter';
import type { V2TaskCenterSnapshot } from '../api/v2TaskCenter';
import type { TaskItem } from '../components/taskcenter/taskCenterTypes';

let cachedTaskCenterSnapshot: V2TaskCenterSnapshot | null = null;
let taskCenterRequest: Promise<V2TaskCenterSnapshot> | null = null;
const TASK_CENTER_CACHE_KEY = 'v2-task-center-snapshot-v1';
const TASK_CENTER_CACHE_UPDATED_KEY = `${TASK_CENTER_CACHE_KEY}:updated-at`;

/** Shared in-process snapshot: header, preview and full task center see one source. */
export function getCachedTaskCenterSnapshot(): V2TaskCenterSnapshot | null {
  if (!cachedTaskCenterSnapshot) {
    try {
      const raw = localStorage.getItem(TASK_CENTER_CACHE_KEY);
      cachedTaskCenterSnapshot = raw ? JSON.parse(raw) as V2TaskCenterSnapshot : null;
    } catch { cachedTaskCenterSnapshot = null; }
  }
  return cachedTaskCenterSnapshot;
}

/**
 * Keep every task-center entry point on the same confirmed backend snapshot.
 * Actions such as global pause return a complete snapshot, so there is no
 * reason for the header and the full modal to wait for their next poll.
 */
export function storeSharedTaskCenterSnapshot(snapshot: V2TaskCenterSnapshot): void {
  cachedTaskCenterSnapshot = snapshot;
  try {
    localStorage.setItem(TASK_CENTER_CACHE_KEY, JSON.stringify(snapshot));
    localStorage.setItem(TASK_CENTER_CACHE_UPDATED_KEY, new Date().toISOString());
  } catch {
    // The cache is only an acceleration layer; the backend remains authoritative.
  }
}

export function loadSharedTaskCenter(force = false): Promise<V2TaskCenterSnapshot> {
  if (!force && cachedTaskCenterSnapshot) return Promise.resolve(cachedTaskCenterSnapshot);
  if (taskCenterRequest) return taskCenterRequest;
  taskCenterRequest = loadTaskCenterSeed().then((snapshot) => {
    storeSharedTaskCenterSnapshot(snapshot);
    return snapshot;
  }).finally(() => { taskCenterRequest = null; });
  return taskCenterRequest;
}

export async function refreshSharedTaskCenterProductionTask(productionTaskId: string): Promise<TaskItem[]> {
  const response = await loadV2TaskCenterProductionTask(productionTaskId);
  const current = getCachedTaskCenterSnapshot();
  if (current) {
    const unaffected = current.tasks.filter((item) => item.productionTaskId !== productionTaskId);
    storeSharedTaskCenterSnapshot({ ...current, tasks: [...unaffected, ...response.items] });
  }
  return response.items;
}

/** The task-center visual shell must never present mock task execution as live. */
export function loadTaskCenterSeed() {
  if (dataSource === 'mock') {
    return Promise.resolve({ executors: INITIAL_EXECUTORS, tasks: INITIAL_TASKS, dramaPriorities: INITIAL_DRAMA_PRIORITIES, isQueuePaused: false });
  }
  return loadV2TaskCenter();
}
