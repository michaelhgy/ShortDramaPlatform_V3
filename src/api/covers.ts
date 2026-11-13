import { v2Client } from './client';
import { getPublishingContext } from './publishing';

export interface TaskCoverContext {
  drama: { id: string; name?: string };
  cover: { path: string; exists: boolean; url: string };
  sheep_cover?: { path: string; exists: boolean; url: string };
  sheep_cover_visible?: boolean;
}
export async function getTaskCoverContext(taskId: string): Promise<TaskCoverContext> {
  try { return await v2Client.get(`/api/v2/cover-editor/tasks/${taskId}/context`, {t:Date.now()}); }
  catch (error) {
    // A still-running older backend can display repaired covers until restart.
    const e=error as Error & {status?: number};
    if (e.status===404 || e.status===400 && e.message.includes('封面编辑入口不存在')) return getPublishingContext(taskId);
    throw error;
  }
}
