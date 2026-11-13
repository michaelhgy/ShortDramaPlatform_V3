import { v2Client } from './client';

export interface ContentTemplatePreviewResponse {
  template_id: string;
  title: string;
  layout: {
    text: string;
    lines: string[];
    font_size: number;
    box: number[];
  };
  canvas: [number, number];
  image_data_url: string;
}

export function renderContentTemplatePreview(templateId: string, title: string): Promise<ContentTemplatePreviewResponse> {
  return v2Client.post('/api/v3/content-templates/render-preview', {
    template_id: templateId,
    title,
  });
}
