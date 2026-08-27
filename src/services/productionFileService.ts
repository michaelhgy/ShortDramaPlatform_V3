import { createV2ProductionTask, scanV2ProductionTask } from '../api/v2Production';
import type { ProductionUnit, ScannedMaterialClip } from '../productionTypes';

function formatSize(bytes: number): string {
  return `${Math.max(0.1, bytes / 1024 / 1024).toFixed(1)} MB`;
}

function currentLocalDateTime(): string {
  const now = new Date();
  return new Date(now.getTime() - now.getTimezoneOffset() * 60_000).toISOString().slice(0, 16);
}

export async function scanProductionMaterials(unit: ProductionUnit): Promise<{ directory: string; discovered: number; materials: ScannedMaterialClip[] }> {
  const task = await createV2ProductionTask({
    source_id: unit.id,
    account_name: unit.accountName,
    drama_name: unit.dramaName,
    planned_publish_at: currentLocalDateTime(),
  });
  const result = await scanV2ProductionTask(task.id);
  return {
    directory: result.directory,
    discovered: result.discovered,
    materials: result.items.map((item) => ({
      id: `v2-${item.md5}`, sequenceNumber: item.sequence_no, title: item.name, dramaPrefix: unit.dramaName, durationSec: 0,
      durationText: '—', fileSizeText: formatSize(item.size_bytes), filePath: item.path,
      scannedAt: '刚刚', isValid: true,
    })),
  };
}
