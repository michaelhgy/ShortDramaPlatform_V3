import { v2Client } from './client';

export interface PublicTemplate {
  id: string;
  name: string;
  file_name?: string;
  usage_limit: number;
  reserved_count: number;
  can_delete: boolean;
  duration_seconds: number;
  resolution: string;
  size_bytes: number;
  usage_count: number;
  preview_url: string | null;
  thumbnail_url: string | null;
  available: boolean;
  unavailable_reason: string;
}

export interface TemplateCatalogue {
  items: PublicTemplate[];
  selected_template_id: string | null;
  selection_locked: boolean;
  selection_lock_reason: string;
  directory: string;
  warnings?: string[];
}

export const getTemplateCatalogue = (taskId: string): Promise<TemplateCatalogue> =>
  v2Client.get(`/api/v2/template-library?task_id=${encodeURIComponent(taskId)}`);

export const refreshTemplateCatalogue = (taskId: string): Promise<TemplateCatalogue> =>
  v2Client.post('/api/v2/template-library/refresh', { task_id: taskId });

export const setTaskTemplate = (taskId: string, templateId: string | null): Promise<TemplateCatalogue> =>
  v2Client.post('/api/v2/template-library/select', { task_id: taskId, template_id: templateId });

export const openPublicTemplateFolder = (): Promise<{ opened: boolean }> =>
  v2Client.post('/api/v2/template-library/open-folder', {});

export const deletePublicTemplate = (taskId: string, templateId: string): Promise<TemplateCatalogue> =>
  v2Client.post('/api/v2/template-library/delete', { task_id: taskId, template_id: templateId });
