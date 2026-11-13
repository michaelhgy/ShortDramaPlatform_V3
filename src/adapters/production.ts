import type { V2ProductionTaskListItem } from '../api/v2Production';
import type { ProductionUnit, ProductionVideoItem, ScannedMaterialClip } from '../productionTypes';
import { plannedDate, formatPlannedDate, plannedSortTimestamp, isPlanOverdue } from '../utils/plannedDate';
import { formatElapsedSeconds } from '../utils/duration';

function formatFileSize(bytes: number): string {
  return `${Math.max(0.1, bytes / 1024 / 1024).toFixed(1)} MB`;
}

function elapsedSecondsFromTimestamps(startedAt?: string, finishedAt?: string): number | null {
  if (!startedAt) return null;
  const started = new Date(startedAt).getTime();
  const finished = finishedAt ? new Date(finishedAt).getTime() : Date.now();
  if (!Number.isFinite(started) || !Number.isFinite(finished)) return null;
  return Math.max(0, Math.floor((finished - started) / 1000));
}

function elapsedFromTimestamps(startedAt?: string, finishedAt?: string): string {
  const seconds = elapsedSecondsFromTimestamps(startedAt, finishedAt);
  return seconds === null ? '—' : formatElapsedSeconds(seconds, '—');
}

function toMaterials(items: V2ProductionTaskListItem['materials'], dramaName: string): ScannedMaterialClip[] {
  return items.map((item, index) => ({
    id: item.id,
    sequenceNumber: item.sequence_no ?? index + 1,
    title: item.name,
    dramaPrefix: dramaName,
    fileSizeText: formatFileSize(item.size_bytes),
    durationSec: item.duration_seconds ?? 0,
    durationText: formatElapsedSeconds(item.duration_seconds, '—'),
    resolution: item.resolution,
    thumbnailUrl: item.thumbnail_path ? `/api/v2/production-files/${item.id}/thumbnail` : undefined,
    videoUrl: `/api/v2/production-files/${item.id}/media`,
    filePath: item.path,
    scannedAt: item.scanned_at,
    insertionStrategy: item.insertion_strategy || null,
    isValid: item.status === 'available' || !item.status,
    status: item.status,
  }));
}

function toVideos(items: V2ProductionTaskListItem['videos'], dramaName: string): ProductionVideoItem[] {
  return items.map((item, index) => {
    const draftSeconds = elapsedSecondsFromTimestamps(item.generation_started_at, item.generation_finished_at);
    const exportSeconds = elapsedSecondsFromTimestamps(item.export_started_at, item.export_finished_at);
    const totalSeconds = (draftSeconds ?? 0) + (exportSeconds ?? 0);
    const canonical = item.display_status || '';
    const status: ProductionVideoItem['status'] = canonical === 'video_queued' ? 'pending_export'
      : canonical === 'video_exporting' ? 'exporting'
      : canonical === 'video_exported' ? 'exported'
      : canonical === 'draft_error' ? 'draft_error'
      : canonical === 'video_error' ? 'video_error'
      : (canonical as ProductionVideoItem['status']) || 'not_generated';
    // A regeneration retains the job ID but changes the media file.
    const mediaVersion = item.engine === 'ffmpeg' ? `?version=${encodeURIComponent(item.output_media_version || item.output_path || '')}` : '';
    return {
    id: item.id,
    sequenceNumber: item.sequence_no ?? index + 1,
    title: (item.output_exists && item.output_path ? item.output_path.split(/[\\/]/).pop() : '') || item.name,
    dramaPrefix: dramaName,
    durationSec: item.output_duration_seconds || item.source_duration_seconds || 0,
    fileSizeText: formatFileSize(item.output_exists ? (item.output_size_bytes ?? 0) : item.size_bytes),
    status,
    engine: item.engine,
    generationDuration: draftSeconds === null && exportSeconds === null ? '—' : formatElapsedSeconds(totalSeconds, '—'),
    generationDurationSeconds: draftSeconds === null && exportSeconds === null ? undefined : totalSeconds,
    totalDuration: draftSeconds === null && exportSeconds === null ? '—' : formatElapsedSeconds(totalSeconds, '—'),
    draftDurationSeconds: draftSeconds ?? undefined,
    exportDurationSeconds: exportSeconds ?? undefined,
    draftDuration: elapsedFromTimestamps(item.generation_started_at, item.generation_finished_at),
    exportDuration: elapsedFromTimestamps(item.export_started_at, item.export_finished_at),
    capcutDraftName: '',
    outputFilePath: item.output_exists ? (item.output_path || undefined) : undefined,
    videoUrl: item.output_exists ? `/api/v2/production-videos/${item.id}/media${mediaVersion}` : undefined,
    thumbnailUrl: item.output_exists ? `/api/v2/production-videos/${item.id}/thumbnail${mediaVersion}` : undefined,
    materialName: item.original_name || item.name,
    exportAttemptId: item.export_attempt_id || undefined,
    errorMessage: item.export_error_message || item.error_message || undefined,
    };
  });
}

export function toProductionUnit(task: V2ProductionTaskListItem): ProductionUnit {
  const materials = toMaterials(task.materials ?? [], task.drama_name);
  const submittedVideos = toVideos(task.videos ?? [], task.drama_name);
  const submittedMaterialIds = new Set((task.videos ?? []).map((item) => item.source_material_id));
  const pendingDisplays: ProductionVideoItem[] = materials
    .filter((material) => !submittedMaterialIds.has(material.id))
    .map((material) => ({
      id: `pending-${material.id}`,
      sequenceNumber: material.sequenceNumber,
      title: material.title,
      dramaPrefix: task.drama_name,
      durationSec: material.durationSec,
      fileSizeText: material.fileSizeText,
      status: 'not_generated',
      totalDuration: '—',
      draftDuration: '—',
      exportDuration: '—',
      capcutDraftName: '',
      thumbnailUrl: material.thumbnailUrl,
    }));
  const videos = [...submittedVideos, ...pendingDisplays].sort((a, b) => a.sequenceNumber - b.sequenceNumber);
  const dateValue = plannedDate(task.planned_publish_at);
  const template = task.template;
  const templateStatus = (task.template_display_status || 'not_generated') as ProductionUnit['templateStatus'];
  return {
    id: task.id,
    accountId: task.account_id || '',
    accountName: task.account_name,
    mountSource: task.mount_source,
    mountExternalId: task.mount_external_id,
    dramaId: task.drama_name,
    dramaName: task.drama_name,
    scheduledDate: dateValue,
    manualOrder: task.manual_order || 0,
    scheduledTime: formatPlannedDate(dateValue),
    sortTimestamp: plannedSortTimestamp(dateValue),
    isOverdue: isPlanOverdue(dateValue),
    createdAt: task.created_at || task.created_date,
    isCompleted: task.release_status === 'registered',
    currentStage: task.release_status === 'registered' ? 'completed' : 'materials',
    taskDisplayStatus: task.task_display_status,
    materialFolder: task.paths.materials,
    materialsCount: task.materials_count ?? materials.length,
    draftCount: task.draft_count,
    draftQueuedCount: task.draft_queued_count,
    draftGeneratingCount: task.draft_generating_count,
    exportQueuedCount: task.export_queued_count,
    exportingCount: task.exporting_count,
    exportedCount: task.exported_count,
    errorCount: task.error_count,
    pendingMaterialCount: task.pending_material_count ?? 0,
    nextMaterialSequence: Math.max(0, ...materials.map((item) => item.sequenceNumber)) + 1,
    scannedMaterials: materials,
    templateStatus,
    templateDraftName: template?.draft_name,
    templateFileSizeText: template?.export_file_size_bytes ? `${(template.export_file_size_bytes / 1024 / 1024).toFixed(1)} MB` : (template?.video_size_bytes ? `${(template.video_size_bytes / 1024 / 1024).toFixed(1)} MB` : undefined),
    templateVideoUrl: template?.export_target_path || template?.video_path ? `/api/v2/production-tasks/${task.id}/template-media` : undefined,
    templateVideoName: template?.export_file_name || undefined,
    templateDurationSec: template?.video_duration_seconds || undefined,
    templateDurationText: template?.video_duration_seconds ? formatElapsedSeconds(template.video_duration_seconds) : undefined,
    templateUpdatedAt: template?.updated_at,
    templateDraftDuration: template?.draft_duration_seconds ? formatElapsedSeconds(template.draft_duration_seconds) : undefined,
    templateDraftDurationSeconds: template?.draft_duration_seconds,
    templateExportDuration: template?.export_duration_seconds ? formatElapsedSeconds(template.export_duration_seconds) : undefined,
    templateExportDurationSeconds: template?.export_duration_seconds,
    templateTotalDuration: template?.draft_duration_seconds == null && template?.export_duration_seconds == null
      ? undefined
      : formatElapsedSeconds((template?.draft_duration_seconds ?? 0) + (template?.export_duration_seconds ?? 0), '—'),
    templateErrorMessage: template?.export_error_message || template?.error_message || undefined,
    templateExportTaskId: template?.export_attempt_id || undefined,
    templateExportStatus: template?.export_status || undefined,
    videos,
    exportInspectionMode: Boolean(task.final_video_manual_check),
    isListeningExport: false,
    outputFolder: task.paths.finals,
    releaseStatus: task.release_status === 'registered' ? 'registered' : 'unregistered',
    actualReleaseTime: task.actual_release_time || undefined,
    releaseAddress: [task.release_province, task.release_city, task.release_district, task.release_detail_address].filter(Boolean).join('') || undefined,
    releaseProvince: task.release_province || undefined,
    releaseCity: task.release_city || undefined,
    releaseDistrict: task.release_district || undefined,
    releaseDetailAddress: task.release_detail_address || undefined,
    lastUpdated: task.created_date,
    insertionStrategy: task.midroll_endroll_strategy || null,
  };
}
