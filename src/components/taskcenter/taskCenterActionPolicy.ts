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

  // 成片生成卡住时，“重试”就是停止当前运行并重新执行成片生成步骤。
  // 视频导出进行中仍使用单独的“重新导出”动作。
  // 导出尝试本身失败或超时时，草稿仍然有效即可重新导出。
  // “已有成功导出”只用于已完成卡片的附加操作，不能让首次导出
  // 失败的模板失去恢复入口。
  if (videoAbnormal && hasValidDraft) {
    return ['reExport'];
  }

  if (draftAbnormal) {
    return task.taskCategory === 'template' ? ['regenerate'] : ['retry'];
  }

  if (task.taskCategory === 'final_video' && draftStatus === 'running') {
    return ['retry'];
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
