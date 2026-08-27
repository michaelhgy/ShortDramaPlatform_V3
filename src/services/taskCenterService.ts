import { INITIAL_DRAMA_PRIORITIES, INITIAL_EXECUTORS, INITIAL_TASKS } from '../components/taskcenter/taskCenterMockData';
import { dataSource } from './dataSource';
import { loadV2TaskCenter } from '../api/v2TaskCenter';

/** The task-center visual shell must never present mock task execution as live. */
export function loadTaskCenterSeed() {
  if (dataSource === 'mock') {
    return Promise.resolve({ executors: INITIAL_EXECUTORS, tasks: INITIAL_TASKS, dramaPriorities: INITIAL_DRAMA_PRIORITIES, isQueuePaused: false });
  }
  return loadV2TaskCenter();
}
