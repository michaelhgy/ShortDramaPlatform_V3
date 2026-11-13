import type { ScenerySnapshot } from '../../api/scenery';
import type { FinalJob, FinalSnapshot } from '../../api/finalComposition';
import type { GenerationSnapshot } from '../../api/templateGeneration';
import type { ProductionUnit, ProductionVideoItem } from '../../productionTypes';

export type JobStatus = FinalJob['status'];
export type QueueKind = 'final' | 'template' | 'scenery';

export function jobPercent(progress: number): number {
  return Number.isFinite(progress) ? Math.max(0, Math.min(99, Math.floor(progress))) : 0;
}

export function jobStatusText(status: JobStatus, progress: number, kind: QueueKind, paused = false): string {
  if (status === 'running') return `${kind === 'final' ? '合成中' : kind === 'scenery' ? '处理中' : '制作中'} ${jobPercent(progress)}%`;
  if (status === 'waiting') return paused ? '等待恢复' : '排队中';
  return { done: '已完成', error: '失败', cancelled: '已取消' }[status];
}

export function queueState(snapshot: { paused: boolean; counts: { running: number; waiting: number; error: number } }): string {
  if (snapshot.paused) return snapshot.counts.running ? '本条完成后暂停' : '已暂停';
  if (snapshot.counts.running) return '正在执行';
  if (snapshot.counts.waiting) return '等待执行';
  return snapshot.counts.error ? '有失败任务' : '空闲';
}

export function currentCounts(final?: FinalSnapshot, template?: GenerationSnapshot, scenery?: ScenerySnapshot) {
  return Object.fromEntries(['running', 'waiting', 'done', 'error', 'cancelled'].map(key => [key,
    (final?.counts[key] || 0) + (template?.counts[key] || 0) + (scenery?.counts[key] || 0),
  ])) as Record<JobStatus, number>;
}

/** Overlay the shared live queue onto the slower production-detail snapshot. */
export function insertionResultText(job: FinalJob): string | undefined {
  const plan = job.insertions;
  if (!plan) return undefined;
  return [
    plan.midroll.status === 'inserted' ? '中插' : '',
    plan.endroll.status === 'inserted' ? '尾插' : '',
  ].filter(Boolean).join(' · ') || undefined;
}

export function liveVideo(video: ProductionVideoItem, jobs: FinalJob[]): ProductionVideoItem {
  const job = jobs.find(j => j.id === video.id || video.id === `pending-${j.material_id}`);
  if (!job) return video;
  const status = { running: 'exporting', waiting: 'pending_export', error: 'video_error', cancelled: 'cancelled', done: 'exported' } as const;
  return { ...video, id: job.id, status: status[job.status], engine: 'ffmpeg', exportProgress: jobPercent(job.progress),
    generationStage: job.stage, generationDurationSeconds: job.elapsed_seconds, errorMessage: job.error,
    durationSec: job.insertions?.total_frames ? job.insertions.total_frames / 30 : video.durationSec,
    insertionResultText: insertionResultText(job) };
}

export function productionProgress(unit: ProductionUnit, jobs: FinalJob[] = []) {
  const own = jobs.filter(j => j.task_id === unit.id);
  const videos = unit.videos.map(v => liveVideo(v, own));
  const total = Math.max(unit.materialsCount || 0, unit.scannedMaterials.length, videos.length, own.length);
  // Summary-only cards have no videos. Fall back to their persisted counts,
  // while the queue contributes every newly submitted FFmpeg job immediately.
  const count = (states: ProductionVideoItem['status'][], jobStates: JobStatus[], fallback: number) =>
    own.length === total && total > 0 ? own.filter(j => jobStates.includes(j.status)).length
      : videos.length ? videos.filter(v => states.includes(v.status)).length
      : Math.max(fallback, own.filter(j => jobStates.includes(j.status)).length);
  const done = Math.min(total, count(['exported'], ['done'], unit.exportedCount || 0));
  const running = count(['exporting', 'draft_generating'], ['running'], (unit.exportingCount || 0) + (unit.draftGeneratingCount || 0));
  const waiting = count(['pending_export', 'draft_queued'], ['waiting'], (unit.exportQueuedCount || 0) + (unit.draftQueuedCount || 0));
  const errors = count(['video_error', 'draft_error'], ['error'], unit.errorCount || 0);
  const cancelled = count(['cancelled'], ['cancelled'], 0);
  return { total, done, running, waiting, errors, cancelled,
    pending: Math.max(0, total - done - running - waiting - errors - cancelled),
    percent: total ? Math.floor(done / total * 100) : 0,
    current: own.find(j => j.status === 'running'),
  };
}
