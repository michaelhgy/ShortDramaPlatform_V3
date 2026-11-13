import assert from 'node:assert/strict';
import { test } from 'node:test';
import { calculateResourceMetrics, currentProductionResources } from './resourceMetrics.ts';
import type { ProductionResourceItem } from '../assetsTypes';

const item = (category: string, name: string, status = 'available') => ({ category, name, status } as ProductionResourceItem);

test('资源库存只纳入 V3 类别，历史真人视频和音乐不会进入全部资源或统计', () => {
  const input = [item('scenery_video', '山水.mp4'), item('real_video', '人物.mp4'), item('bgm', '音乐.mp3'), item('real_image', '照片.jpg'), item('lead_video', '引流.mp4')];
  assert.deepEqual(currentProductionResources(input).map(value => value.category), ['scenery_video', 'real_image', 'lead_video']);
  assert.deepEqual(calculateResourceMetrics(input), { videoCount: 1, imageCount: 1, leadVideoCount: 1, totalVideoCount: 1, totalImageCount: 1, totalResourceCount: 3 });
});

test('库存分别统计可用与总量，已使用文件前缀和旧状态都能识别，引流文件继续可复用', () => {
  const input = [item('scenery_video', '山水.mp4'), item('scenery_video', ' 已使用-旧.mp4'), item('scenery_video', '旧.mp4', 'used'), item('real_image', '已使用-照片.jpg'), item('lead_video', '已使用-引流.mp4', 'used')];
  assert.deepEqual(calculateResourceMetrics(input), { videoCount: 1, imageCount: 0, leadVideoCount: 1, totalVideoCount: 3, totalImageCount: 1, totalResourceCount: 5 });
});

test('加工风景以剩余额度计可用条数，已用满或预留完不计入，次数不累加成条数', () => {
  const input = [
    { ...item('scenery_video', '风景001.mp4'), remainingCount: 5 },
    { ...item('scenery_video', '风景002.mp4'), remainingCount: 0 },
    { ...item('scenery_video', '已使用旧名.mp4', 'used'), remainingCount: 2 },
    item('real_image', '照片.jpg'),
  ];
  assert.equal(calculateResourceMetrics(input).videoCount, 2);
  assert.equal(calculateResourceMetrics(input).totalVideoCount, 3);
});
