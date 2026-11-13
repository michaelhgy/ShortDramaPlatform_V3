import type { CropRect, SceneryDetail } from '../../api/scenery';

export type CropLayout = 'auto' | 1 | 2 | 3;

export function initialCrops(width: number, height: number, layout: CropLayout): CropRect[] {
  const count = layout === 'auto' ? (height > width ? 3 : 1) : layout;
  const w = Math.floor(width / 2) * 2;
  if (width > height && count === 1) return [{x:0,y:0,width:w,height:Math.floor(height/2)*2}];
  const h = Math.floor(Math.min(height / count, w * .75) / 2) * 2;
  return Array.from({ length: count }, (_, i) => ({
    x: 0, y: Math.floor((height / count * i + (height / count - h) / 2) / 2) * 2, width: w, height: h,
  }));
}

export function sceneryOutputCount(source: SceneryDetail, crops: CropRect[]): number {
  return crops.length * (source.time_segments?.length || 1);
}

export function sceneryTimeSummary(source: SceneryDetail): string {
  const segments=source.time_segments;
  if (!segments?.length) return source.duration>30 ? '提交时随机切段，每段不超过30秒' : '保留整段时长';
  if (segments.length===1) return `保留整段 ${(segments[0].frames/30).toFixed(1)} 秒`;
  const seconds=segments.map(s=>s.frames/30);
  return `时间切成 ${segments.length} 段，每段 ${Math.min(...seconds).toFixed(1)}—${Math.max(...seconds).toFixed(1)} 秒`;
}

export function validCrops(crops: CropRect[], source: { width: number; height: number }): boolean {
  return crops.length > 0 && crops.length <= 12 && crops.every((c, index) =>
    Object.values(c).every(value => Number.isInteger(value) && value % 2 === 0)
    && c.width > c.height && c.width >= 32 && c.height >= 32 && c.x >= 0 && c.y >= 0
    && c.x + c.width <= source.width && c.y + c.height <= source.height
    && !crops.slice(0, index).some(previous => previous.x === c.x && previous.y === c.y && previous.width === c.width && previous.height === c.height),
  );
}
