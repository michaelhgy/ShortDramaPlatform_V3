import { TaskItem } from './taskCenterTypes';

export type TaskCenterAction = 'regenerate' | 'retry' | 'reExport';

/**
 * Formal task-card action policy. The UI must render only the actions returned here.
 * Optional runtime facts will be provided by the V2 task service; fallbacks keep
 * preview data readable without making the presence of a button the source of truth.
 */
export function getTaskCenterActions(task: TaskItem): TaskCenterAction[] {
  const draftStatus = task.draftStage.status;
  const videoStatus = task.videoStage.status;
  const draftAbnormal = draftStatus === 'error' || draftStatus === 'timeout';
  const videoAbnormal = videoStatus === 'error' || videoStatus === 'timeout';
  const hasValidDraft = task.hasValidDraft ?? (draftStatus === 'done' && Boolean(task.draftPath));
  const hasCompletedFirstExport = task.hasCompletedFirstExport ??
    ['done', 'error', 'timeout'].includes(videoStatus);

  if (draftAbnormal) {
    return task.taskCategory === 'template' ? ['regenerate'] : ['retry'];
  }

  if (videoAbnormal && hasValidDraft && hasCompletedFirstExport) {
    return ['reExport'];
  }

  // 模板草稿已经生成、但首次视频导出尚未完成时，允许重新生成模板。
  // 成片没有主动重新生成规则；正在导出中的任务仍不显示操作按钮。
  if (
    task.taskCategory === 'template' &&
    draftStatus === 'done' &&
    (videoStatus === 'waiting' || videoStatus === 'idle') &&
    hasValidDraft
  ) {
    return ['regenerate'];
  }

  if (draftStatus === 'done' && videoStatus === 'done' && hasValidDraft && hasCompletedFirstExport) {
    return task.taskCategory === 'template' ? ['regenerate', 'reExport'] : ['reExport'];
  }

  return [];
}

export function canTaskCenterAction(task: TaskItem, action: TaskCenterAction): boolean {
  return getTaskCenterActions(task).includes(action);
}
