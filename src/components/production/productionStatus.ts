import type { ProductionUnit, ProductionVideoItem } from '../../productionTypes';

export type ProductionStageFilter = 'all' | 'in_progress' | 'overdue' | 'completed';
type StageUnit = Pick<ProductionUnit, 'isCompleted' | 'isOverdue'>;

// Completed cards form their own group; overdue remains a subset of unfinished work.
export function matchesProductionStage(unit: StageUnit, filter: ProductionStageFilter): boolean {
  if (filter === 'completed') return unit.isCompleted;
  if (unit.isCompleted) return false;
  if (filter === 'overdue') return Boolean(unit.isOverdue);
  return true;
}

export function productionStageCounts(units: StageUnit[]) {
  return {
    all: units.filter(u => matchesProductionStage(u, 'all')).length,
    in_progress: units.filter(u => matchesProductionStage(u, 'in_progress')).length,
    overdue: units.filter(u => matchesProductionStage(u, 'overdue')).length,
    completed: units.filter(u => matchesProductionStage(u, 'completed')).length,
  };
}

// Legacy Jianying phases remain readable without leaking draft/export stages
// into the current FFmpeg composition interface.
export function compositionStatusLabel(video: Pick<ProductionVideoItem, 'status' | 'exportProgress'>): string {
  switch (video.status) {
    case 'exported': return '已生成';
    case 'draft_ready': return '待合成';
    case 'exporting': return video.exportProgress == null ? '合成中' : `合成中 ${Math.max(0, Math.min(99, Math.round(video.exportProgress)))}%`;
    case 'draft_generating': return '合成中';
    case 'draft_queued': case 'pending_export': return '等待合成';
    case 'draft_error': case 'video_error': return '合成异常';
    case 'cancelled': return '已取消';
    default: return '待合成';
  }
}
