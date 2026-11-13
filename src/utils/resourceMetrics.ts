import type { ProductionResourceItem, ResourceInventoryMetrics } from '../assetsTypes';

export function currentProductionResources(resources: ProductionResourceItem[]): ProductionResourceItem[] {
  return resources.filter(item => ['scenery_video', 'real_image', 'lead_video'].includes(item.category));
}

export function calculateResourceMetrics(resources: ProductionResourceItem[]): ResourceInventoryMetrics {
  const current = currentProductionResources(resources);
  const isUsed = (item: ProductionResourceItem) => item.status === 'used' || item.name.trimStart().startsWith('已使用');
  return {
    videoCount: current.filter(item => item.category === 'scenery_video'
      && (typeof item.remainingCount === 'number' ? item.remainingCount > 0 : !isUsed(item))).length,
    imageCount: current.filter(item => item.category === 'real_image' && !isUsed(item)).length,
    leadVideoCount: current.filter(item => item.category === 'lead_video').length,
    totalVideoCount: current.filter(item => item.category === 'scenery_video').length,
    totalImageCount: current.filter(item => item.category === 'real_image').length,
    totalResourceCount: current.length,
  };
}
