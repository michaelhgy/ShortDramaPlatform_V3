import { v2Client } from './client';
import type { DramaSchedulePriority, ExecutorInfo, TaskItem } from '../components/taskcenter/taskCenterTypes';

export interface V2TaskCenterSnapshot {
  executors: ExecutorInfo[];
  tasks: TaskItem[];
  dramaPriorities: DramaSchedulePriority[];
  isQueuePaused?: boolean;
}

export function loadV2TaskCenter(): Promise<V2TaskCenterSnapshot> {
  return v2Client.get('/api/v2/task-center');
}

export function setV2TaskCenterPaused(paused: boolean): Promise<V2TaskCenterSnapshot> {
  return v2Client.post(`/api/v2/task-center/${paused ? 'pause' : 'resume'}`);
}

export function regenerateV2Template(jobId: string): Promise<{ id: string; task_id: string; version_no: number; draft_name: string; status: string }> {
  return v2Client.post(`/api/v2/task-center/tasks/${jobId}/regenerate`);
}

export function retryV2Template(jobId: string): Promise<{ id: string; task_id: string; status: string }> {
  return v2Client.post(`/api/v2/task-center/tasks/${jobId}/retry`);
}

export function cleanupV2OrphanTask(jobId: string): Promise<{ deleted: boolean }> {
  return v2Client.delete(`/api/v2/task-center/tasks/${jobId}/orphan`);
}
