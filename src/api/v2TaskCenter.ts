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

export function loadV2TaskCenterProductionTask(taskId: string): Promise<{ items: TaskItem[] }> {
  return v2Client.get(`/api/v2/task-center/production-tasks/${taskId}`);
}

export function setV2TaskCenterPaused(paused: boolean): Promise<V2TaskCenterSnapshot> {
  return v2Client.post(`/api/v2/task-center/${paused ? 'pause' : 'resume'}`);
}

export function setV2ExecutorPaused(executorId: string, paused: boolean): Promise<V2TaskCenterSnapshot> {
  return v2Client.post(`/api/v2/task-center/executors/${executorId}/${paused ? 'pause' : 'resume'}`);
}

export function regenerateV2Template(jobId: string): Promise<{ id: string; task_id: string; version_no: number; draft_name: string; status: string }> {
  return v2Client.post(`/api/v2/task-center/tasks/${jobId}/regenerate`);
}

export function retryV2Template(jobId: string): Promise<{ id: string; task_id: string; status: string }> {
  return v2Client.post(`/api/v2/task-center/tasks/${jobId}/retry`);
}

export function reExportV2Task(taskId: string): Promise<{ id: string; status: string }> {
  return v2Client.post(`/api/v2/task-center/tasks/${taskId}/re-export`);
}

export function cleanupV2OrphanTask(jobId: string): Promise<{ deleted: boolean }> {
  return v2Client.delete(`/api/v2/task-center/tasks/${jobId}/orphan`);
}

/**
 * 手动调整一个「账号 × 剧集」的生产顺序。
 * 这个顺序同时是三个执行器的取任务顺序（用户 2026-09-19 拍板）。
 */
export function reorderV2ProductionUnit(
  productionTaskId: string,
  action: 'top' | 'up' | 'down',
): Promise<{ order: string[] }> {
  return v2Client.post('/api/v2/task-center/manual-order', {
    production_task_id: productionTaskId,
    action,
  });
}
