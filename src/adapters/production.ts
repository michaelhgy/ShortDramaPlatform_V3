import type { V2ProductionTaskListItem } from '../api/v2Production';
import type { ProductionUnit, ProductionVideoItem, ScannedMaterialClip } from '../productionTypes';
import { formatRelativeDateTime } from '../utils/dateDisplay';

function formatFileSize(bytes: number): string {
  return `${Math.max(0.1, bytes / 1024 / 1024).toFixed(1)} MB`;
}

function formatPublishTime(value: string, createdDate: string): { scheduledDate: string; scheduledTime: string; sortTimestamp: number } {
  if (!value) {
    return { scheduledDate: createdDate, scheduledTime: '未设置计划发布时间', sortTimestamp: new Date(`${createdDate}T23:59`).getTime() };
  }
  const timestamp = new Date(value).getTime();
  const dateValue = value.slice(0, 10);
  return { scheduledDate: dateValue, scheduledTime: formatRelativeDateTime(value), sortTimestamp: timestamp };
}

function toMaterials(items: V2ProductionTaskListItem['materials'], dramaName: string): ScannedMaterialClip[] {
  return items.map((item, index) => ({
    id: item.id,
    sequenceNumber: item.sequence_no ?? index + 1,
    title: item.name,
    dramaPrefix: dramaName,
    fileSizeText: formatFileSize(item.size_bytes),
    durationSec: item.duration_seconds ?? 0,
    durationText: item.duration_seconds ? `${Math.floor(item.duration_seconds / 60).toString().padStart(2, '0')}:${Math.floor(item.duration_seconds % 60).toString().padStart(2, '0')}` : '—',
    thumbnailUrl: item.thumbnail_path ? `/api/v2/production-files/${item.id}/thumbnail` : undefined,
    videoUrl: `/api/v2/production-files/${item.id}/media`,
    filePath: item.path,
    scannedAt: item.scanned_at,
    isValid: true,
  }));
}

function toVideos(items: V2ProductionTaskListItem['videos'], dramaName: string): ProductionVideoItem[] {
  return items.map((item, index) => ({
    id: item.id,
    sequenceNumber: item.sequence_no ?? index + 1,
    title: item.name,
    dramaPrefix: dramaName,
    durationSec: 0,
    fileSizeText: formatFileSize(item.size_bytes),
    status: 'not_generated',
    draftDuration: '—',
    exportDuration: '—',
    capcutDraftName: '',
    outputFilePath: item.output_path || undefined,
  }));
}

export function toProductionUnit(task: V2ProductionTaskListItem): ProductionUnit {
  const materials = toMaterials(task.materials ?? [], task.drama_name);
  const videos = toVideos(task.videos ?? [], task.drama_name);
  const schedule = formatPublishTime(task.planned_publish_at, task.created_date);
  const isOverdue = Boolean(task.planned_publish_at) && schedule.sortTimestamp < Date.now();
  const template = task.template;
  const templateStatus = template?.status === 'queued' || template?.status === 'running' ? 'generating'
    : template?.status === 'draft_ready' ? 'draft_ready'
    : template?.status === 'error' || template?.status === 'timeout' ? 'error' : 'not_generated';
  return {
    id: task.id,
    accountId: task.account_name,
    accountName: task.account_name,
    dramaId: task.drama_name,
    dramaName: task.drama_name,
    scheduledDate: schedule.scheduledDate,
    scheduledTime: schedule.scheduledTime,
    sortTimestamp: schedule.sortTimestamp,
    isOverdue,
    isCompleted: false,
    currentStage: 'materials',
    materialFolder: task.paths.materials,
    materialsCount: materials.length,
    pendingMaterialCount: task.pending_material_count ?? 0,
    nextMaterialSequence: Math.max(0, ...materials.map((item) => item.sequenceNumber)) + 1,
    scannedMaterials: materials,
    templateStatus,
    templateDraftName: template?.draft_name,
    templateDraftDuration: template?.draft_duration_formatted || undefined,
    templateFileSizeText: template?.video_size_bytes ? `${(template.video_size_bytes / 1024 / 1024).toFixed(1)} MB` : undefined,
    templateVideoUrl: template?.video_path || undefined,
    templateUpdatedAt: template?.updated_at,
    templateErrorMessage: template?.error_message || undefined,
    videos,
    exportInspectionMode: false,
    isListeningExport: false,
    outputFolder: task.paths.finals,
    releaseStatus: 'unregistered',
    lastUpdated: task.created_date,
  };
}
