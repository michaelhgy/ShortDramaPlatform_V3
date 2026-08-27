import type { ProductionResourceItem, ResourceCapacityMetrics } from '../assetsTypes';

export function calculateResourceMetrics(resources: ProductionResourceItem[]): ResourceCapacityMetrics {
  // 生产资源的真实领取规则以文件名为准：文件名以“已使用”开头即不再计入剩余量。
  // 同时兼容 API 返回的 status 字段，避免历史数据字段未同步时把已领取资源算入产能。
  const isUsed = (item: ProductionResourceItem) =>
    item.status === 'used' || item.name.trimStart().startsWith('已使用');
  const videoCount = resources.filter((item) => item.category === 'real_video' && !isUsed(item)).length;
  const imageCount = resources.filter((item) => item.category === 'real_image' && !isUsed(item)).length;
  const totalVideoCount = resources.filter((item) => item.category === 'real_video').length;
  const totalImageCount = resources.filter((item) => item.category === 'real_image').length;
  const bgmCount = resources.filter((item) => item.category === 'bgm').length;
  const videoSupportableDramas = Math.floor(videoCount / 3);
  const imageSupportableDramas = Math.floor(imageCount / 6);
  const supportableDramas = Math.min(videoSupportableDramas, imageSupportableDramas);
  const bottleneckType = videoSupportableDramas < imageSupportableDramas ? 'video'
    : imageSupportableDramas < videoSupportableDramas ? 'image' : 'balanced';
  const shortageTip = bottleneckType === 'video' ? '真人视频储备不足。'
    : bottleneckType === 'image' ? '真人图片储备不足。' : '暂无生产资源。';
  return { videoCount, imageCount, bgmCount, totalVideoCount, totalImageCount, videoSupportableDramas, imageSupportableDramas, supportableDramas, bottleneckType, shortageTip };
}
