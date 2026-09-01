// Deterministic Data Engine for Platform Promotion Videos (平台推广视频分析引擎)
import { TimeRangeFilter, TheaterFilter } from '../analyticsTypes';

export interface DailyVideoRecord {
  date: string; // YYYY-MM-DD
  dayLabel: string; // e.g. 08-20
  videoViews: number;
  dramaViews: number;
  revenue: number;
}

export interface CandidateClipInfo {
  clipId: string;
  clipName: string; // e.g. "风雪草原苍狼少女-08"
  sourceMaterialId: string; // e.g. "素材-12"
  sourceMaterialName: string; // e.g. "风雪草原苍狼少女-12 (开场高潮剪辑)"
  duration: string;
  exportDate: string;
}

export interface PlatformVideoEntity {
  id: string; // 平台视频唯一标识, e.g. "vid-qn-1001"
  theaterKey: 'qingning' | 'jiuzhou' | 'dianzhong' | 'fanqie' | 'huasheng';
  theaterName: string;
  accountId: string;
  accountName: string;
  dramaId: string;
  dramaName: string;
  firstObservedDate: string; // 首次观测日期 YYYY-MM-DD
  candidateBatch: string; // e.g. "08-20 · 短剧黄鸡版"
  isLinked: boolean;
  linkedClipName?: string; // e.g. "风雪草原苍狼少女-08"
  sourceMaterialId?: string; // e.g. "素材-12"
  sourceMaterialName?: string; // e.g. "风雪草原苍狼少女-12"
  candidateClips: CandidateClipInfo[];
  allDailyRecords: DailyVideoRecord[]; // 30-day full lifecycle records
}

export interface AggregatedPlatformVideo {
  id: string; // 平台视频ID
  theaterKey: string;
  theaterName: string;
  accountId: string;
  accountName: string;
  dramaId: string;
  dramaName: string;
  firstObservedDate: string; // 首次观测
  firstObservedShort: string; // e.g. "08-19"
  candidateBatch: string; // e.g. "08-19 · 短剧黄鸡版"
  isLinked: boolean;
  linkedClipName?: string;
  sourceMaterialId?: string;
  sourceMaterialName?: string;
  candidateClips: CandidateClipInfo[];
  
  // Period Aggregated Metrics (随 Global Filter 动态变化)
  periodVideoViews: number;
  periodDramaViews: number;
  periodRevenue: number;
  receptionStrength: number; // 承接强度 = 周期剧集播放 ÷ 周期视频播放
  rpm: number; // 千次视频播放收益 = 周期收益 ÷ 周期视频播放 × 1000
  
  // Filtered period daily records for Drawer
  periodDailyRecords: DailyVideoRecord[];
  
  // Quadrant classification based on current sample P75
  quadrant: 'breakout' | 'hook' | 'high_ticket' | 'long_tail';
  /** Available only after a human confirms the production-material link. */
  linkedTaskId?: string;
  linkedReleaseAddress?: string;
  linkedActualReleaseTime?: string;
}

export interface VideoAnalysisResult {
  hasVideoLevelData: boolean;
  unsupportedReason?: string;
  totalPlatformVideosCount: number; // 平台视频样本总数 (去重视频ID数)
  totalDailyRecordsCount: number;
  videos: AggregatedPlatformVideo[];
  
  // Dynamic P75 Thresholds for current filtered sample
  p75Views: number;
  p75Revenue: number;
  isLowSampleCount: boolean; // sample < 20
  
  // Max boundaries for scatter coordinate scaling
  maxViews: number;
  maxRevenue: number;
}

// -----------------------------------------------------------------------------
// SEED DATA: 95 Distinct Platform Videos with realistic multi-day records
// -----------------------------------------------------------------------------
const RAW_PLATFORM_VIDEOS: PlatformVideoEntity[] = [];

(() => {
  const dates: string[] = [];
  const start = new Date(2026, 6, 25);
  for (let i = 0; i < 30; i++) {
    const d = new Date(start);
    d.setDate(start.getDate() + i);
    const yyyy = d.getFullYear();
    const mm = String(d.getMonth() + 1).padStart(2, '0');
    const dd = String(d.getDate()).padStart(2, '0');
    dates.push(`${yyyy}-${mm}-${dd}`);
  }

  const qingningAccounts = [
    { id: 'acc-1', name: '短剧黄鸡版' },
    { id: 'acc-4', name: '格格芝LE' },
    { id: 'acc-3', name: '冷脸萌萌1701' },
    { id: 'acc-2', name: '鸿记水产行' },
    { id: 'acc-11', name: '爆款微剧社-06' },
    { id: 'acc-13', name: '独角兽短剧-09' },
  ];

  const qingningDramas = [
    { id: 'd-1', name: '风雪草原苍狼少女' },
    { id: 'd-2', name: '辣厨回乡鲜椒越香店越旺' },
    { id: 'd-3', name: '坠海逢生我率万鲨踏浪归来' },
    { id: 'd-4', name: '我用十元盒饭惊艳全城' },
    { id: 'd-5', name: '惨遭同行背叛百年野猪认我为王' },
    { id: 'd-6', name: '我在武侠世界抽卡成神' },
  ];

  let seq = 1000;

  // Helper to generate candidate clips for a video
  const makeCandidates = (dramaName: string, batchDate: string, accName: string) => {
    const num = Math.floor(Math.random() * 30) + 1;
    return [
      {
        clipId: `clip-${num}`,
        clipName: `${dramaName}-${String(num).padStart(2, '0')}`,
        sourceMaterialId: `素材-${String(num).padStart(2, '0')}`,
        sourceMaterialName: `${dramaName}-原始素材分段${num}`,
        duration: '01:08',
        exportDate: `${batchDate} 09:30`,
      },
      {
        clipId: `clip-${num + 1}`,
        clipName: `${dramaName}-${String(num + 1).padStart(2, '0')}`,
        sourceMaterialId: `素材-${String(num + 1).padStart(2, '0')}`,
        sourceMaterialName: `${dramaName}-高潮反转分段${num + 1}`,
        duration: '00:54',
        exportDate: `${batchDate} 10:15`,
      },
      {
        clipId: `clip-${num + 2}`,
        clipName: `${dramaName}-${String(num + 2).padStart(2, '0')}`,
        sourceMaterialId: `素材-${String(num + 2).padStart(2, '0')}`,
        sourceMaterialName: `${dramaName}-虐心卡点分段${num + 2}`,
        duration: '01:16',
        exportDate: `${batchDate} 11:00`,
      },
    ];
  };

  // Group 1: Breakout Videos (爆款转化: High Views + High Revenue) ~40 videos
  for (let i = 0; i < 40; i++) {
    seq++;
    const acc = qingningAccounts[i % qingningAccounts.length];
    const drama = qingningDramas[i % qingningDramas.length];
    // Spread creation across the 30-day window (day 0 to 28)
    const creationDayOffset = (i * 3 + (i % 5)) % 29;
    const firstObservedDate = dates[creationDayOffset];
    const shortDate = firstObservedDate.slice(5);
    const candidateBatch = `${shortDate} · ${acc.name}`;
    const isLinked = i % 3 !== 0;
    const candidates = makeCandidates(drama.name, firstObservedDate, acc.name);
    const chosenClip = candidates[0];

    // Breakouts have active lifecycles from 6 to 18 days
    const lifeDuration = 6 + (i % 13);
    const endDayOffset = Math.min(dates.length - 1, creationDayOffset + lifeDuration);

    const allDailyRecords: DailyVideoRecord[] = [];
    for (let d = creationDayOffset; d <= endDayOffset; d++) {
      const dayDiff = d - creationDayOffset;
      let multiplier = 1.0;
      if (dayDiff === 0) multiplier = 0.85;
      else if (dayDiff === 1) multiplier = 1.0;
      else if (dayDiff === 2) multiplier = 0.65;
      else if (dayDiff === 3) multiplier = 0.42;
      else if (dayDiff <= 6) multiplier = 0.25;
      else if (dayDiff <= 10) multiplier = 0.12;
      else multiplier = 0.05;

      // Base daily views: 8k ~ 32k on peak day
      const baseDailyViews = 8000 + (i * 600) + Math.floor(Math.sin(i * 1.5) * 2000);
      const views = Math.max(80, Math.floor(baseDailyViews * multiplier));
      const receptionRatio = 1.4 + (i % 6) * 0.12;
      const dramaViews = Math.floor(views * receptionRatio);
      // RPM: ¥14 ~ ¥28
      const rpmBase = 14.0 + (i * 0.35) + (i % 4) * 1.2;
      const rev = Number(((views / 1000) * rpmBase).toFixed(2));

      allDailyRecords.push({
        date: dates[d],
        dayLabel: dates[d].slice(5),
        videoViews: views,
        dramaViews,
        revenue: rev,
      });
    }

    RAW_PLATFORM_VIDEOS.push({
      id: `vid-qn-${seq}`,
      theaterKey: 'qingning',
      theaterName: '青柠剧场',
      accountId: acc.id,
      accountName: acc.name,
      dramaId: drama.id,
      dramaName: drama.name,
      firstObservedDate,
      candidateBatch,
      isLinked,
      linkedClipName: isLinked ? chosenClip.clipName : undefined,
      sourceMaterialId: isLinked ? chosenClip.sourceMaterialId : undefined,
      sourceMaterialName: isLinked ? chosenClip.sourceMaterialName : undefined,
      candidateClips: candidates,
      allDailyRecords,
    });
  }

  // Group 2: Hook / High Traffic Low Revenue (引流卡点: High Views + Low Revenue) ~45 videos
  for (let i = 0; i < 45; i++) {
    seq++;
    const acc = qingningAccounts[(i + 1) % qingningAccounts.length];
    const drama = qingningDramas[(i + 2) % qingningDramas.length];
    // Spread creation across the 30-day window
    const creationDayOffset = (i * 2 + (i % 7)) % 29;
    const firstObservedDate = dates[creationDayOffset];
    const shortDate = firstObservedDate.slice(5);
    const candidateBatch = `${shortDate} · ${acc.name}`;
    const isLinked = i % 2 === 0;
    const candidates = makeCandidates(drama.name, firstObservedDate, acc.name);
    const chosenClip = candidates[0];

    // Hooks have active lifecycles from 3 to 10 days
    const lifeDuration = 3 + (i % 8);
    const endDayOffset = Math.min(dates.length - 1, creationDayOffset + lifeDuration);

    const allDailyRecords: DailyVideoRecord[] = [];
    for (let d = creationDayOffset; d <= endDayOffset; d++) {
      const dayDiff = d - creationDayOffset;
      const multiplier = dayDiff === 0 ? 0.9 : dayDiff === 1 ? 1.0 : dayDiff <= 3 ? 0.45 : dayDiff <= 6 ? 0.18 : 0.06;
      // High daily views 9k ~ 28k
      const baseDailyViews = 9000 + (i * 450) + Math.floor(Math.cos(i) * 1500);
      const views = Math.max(100, Math.floor(baseDailyViews * multiplier));
      const dramaViews = Math.floor(views * (0.65 + (i % 4) * 0.08));
      // Very low RPM: ¥0.8 ~ ¥2.4
      const rpmBase = 0.8 + (i % 5) * 0.35;
      const rev = Number(((views / 1000) * rpmBase).toFixed(2));

      allDailyRecords.push({
        date: dates[d],
        dayLabel: dates[d].slice(5),
        videoViews: views,
        dramaViews,
        revenue: rev,
      });
    }

    RAW_PLATFORM_VIDEOS.push({
      id: `vid-qn-${seq}`,
      theaterKey: 'qingning',
      theaterName: '青柠剧场',
      accountId: acc.id,
      accountName: acc.name,
      dramaId: drama.id,
      dramaName: drama.name,
      firstObservedDate,
      candidateBatch,
      isLinked,
      linkedClipName: isLinked ? chosenClip.clipName : undefined,
      sourceMaterialId: isLinked ? chosenClip.sourceMaterialId : undefined,
      sourceMaterialName: isLinked ? chosenClip.sourceMaterialName : undefined,
      candidateClips: candidates,
      allDailyRecords,
    });
  }

  // Group 3: High Ticket / Low Views High Revenue (高客单转化: Low Views + High Revenue) ~35 videos
  for (let i = 0; i < 35; i++) {
    seq++;
    const acc = qingningAccounts[(i + 2) % qingningAccounts.length];
    const drama = qingningDramas[(i + 3) % qingningDramas.length];
    // Spread creation across the 30-day window
    const creationDayOffset = (i * 3 + 1) % 29;
    const firstObservedDate = dates[creationDayOffset];
    const shortDate = firstObservedDate.slice(5);
    const candidateBatch = `${shortDate} · ${acc.name}`;
    const isLinked = i % 3 !== 1;
    const candidates = makeCandidates(drama.name, firstObservedDate, acc.name);
    const chosenClip = candidates[0];

    // High ticket lifecycles 4 to 12 days
    const lifeDuration = 4 + (i % 9);
    const endDayOffset = Math.min(dates.length - 1, creationDayOffset + lifeDuration);

    const allDailyRecords: DailyVideoRecord[] = [];
    for (let d = creationDayOffset; d <= endDayOffset; d++) {
      const dayDiff = d - creationDayOffset;
      const multiplier = dayDiff <= 2 ? 1.0 : dayDiff <= 5 ? 0.5 : dayDiff <= 8 ? 0.22 : 0.08;
      // Low/Medium daily views: 1.2k ~ 4.5k
      const baseDailyViews = 1500 + (i * 90) + Math.floor(Math.sin(i * 2) * 300);
      const views = Math.max(50, Math.floor(baseDailyViews * multiplier));
      const dramaViews = Math.floor(views * (1.5 + (i % 4) * 0.22));
      // Very high RPM: ¥28 ~ ¥48
      const rpmBase = 28.0 + (i * 0.45) + (i % 4) * 2.5;
      const rev = Number(((views / 1000) * rpmBase).toFixed(2));

      allDailyRecords.push({
        date: dates[d],
        dayLabel: dates[d].slice(5),
        videoViews: views,
        dramaViews,
        revenue: rev,
      });
    }

    RAW_PLATFORM_VIDEOS.push({
      id: `vid-qn-${seq}`,
      theaterKey: 'qingning',
      theaterName: '青柠剧场',
      accountId: acc.id,
      accountName: acc.name,
      dramaId: drama.id,
      dramaName: drama.name,
      firstObservedDate,
      candidateBatch,
      isLinked,
      linkedClipName: isLinked ? chosenClip.clipName : undefined,
      sourceMaterialId: isLinked ? chosenClip.sourceMaterialId : undefined,
      sourceMaterialName: isLinked ? chosenClip.sourceMaterialName : undefined,
      candidateClips: candidates,
      allDailyRecords,
    });
  }

  // Group 4: Regular Long-tail & Zero-revenue (常规长尾: Low Views + Low Revenue) ~130 videos
  for (let i = 0; i < 130; i++) {
    seq++;
    const acc = qingningAccounts[i % qingningAccounts.length];
    const drama = qingningDramas[i % qingningDramas.length];
    // Spread creation across all 30 days
    const creationDayOffset = (i * 2 + (i % 9)) % 29;
    const firstObservedDate = dates[creationDayOffset];
    const shortDate = firstObservedDate.slice(5);
    const candidateBatch = `${shortDate} · ${acc.name}`;
    const isLinked = i % 4 === 0;
    const candidates = makeCandidates(drama.name, firstObservedDate, acc.name);
    const chosenClip = candidates[0];

    const isZeroRevVideo = i % 3 === 0;

    // Long-tail lifecycles 2 to 6 days
    const lifeDuration = 2 + (i % 5);
    const endDayOffset = Math.min(dates.length - 1, creationDayOffset + lifeDuration);

    const allDailyRecords: DailyVideoRecord[] = [];
    for (let d = creationDayOffset; d <= endDayOffset; d++) {
      const dayDiff = d - creationDayOffset;
      const multiplier = dayDiff <= 1 ? 1.0 : dayDiff <= 3 ? 0.35 : 0.08;
      // Low daily views: 200 ~ 2200
      const baseDailyViews = 300 + (i * 25) + Math.floor(Math.sin(i * 3) * 120);
      const views = Math.max(20, Math.floor(baseDailyViews * multiplier));
      const dramaViews = Math.floor(views * (0.7 + (i % 3) * 0.15));
      let rev = 0;
      if (!isZeroRevVideo) {
        const rpmBase = 1.8 + (i % 4) * 0.8;
        rev = Number(((views / 1000) * rpmBase).toFixed(2));
      }

      allDailyRecords.push({
        date: dates[d],
        dayLabel: dates[d].slice(5),
        videoViews: views,
        dramaViews,
        revenue: rev,
      });
    }

    RAW_PLATFORM_VIDEOS.push({
      id: `vid-qn-${seq}`,
      theaterKey: 'qingning',
      theaterName: '青柠剧场',
      accountId: acc.id,
      accountName: acc.name,
      dramaId: drama.id,
      dramaName: drama.name,
      firstObservedDate,
      candidateBatch,
      isLinked,
      linkedClipName: isLinked ? chosenClip.clipName : undefined,
      sourceMaterialId: isLinked ? chosenClip.sourceMaterialId : undefined,
      sourceMaterialName: isLinked ? chosenClip.sourceMaterialName : undefined,
      candidateClips: candidates,
      allDailyRecords,
    });
  }
})();

// Helper to compute Percentile (P75)
function calculatePercentile(values: number[], percentile: number = 0.75): number {
  if (values.length === 0) return 0;
  const sorted = [...values].sort((a, b) => a - b);
  const index = (sorted.length - 1) * percentile;
  const lower = Math.floor(index);
  const upper = Math.ceil(index);
  const weight = index - lower;
  if (upper === lower) return sorted[lower];
  return sorted[lower] * (1 - weight) + sorted[upper] * weight;
}

// -----------------------------------------------------------------------------
// MAIN CALCULATION FUNCTION: Aggregates Raw Videos by TimeRange and Theater
// -----------------------------------------------------------------------------
export function calculatePlatformVideosAnalytics(
  timeRange: TimeRangeFilter,
  selectedTheater: TheaterFilter,
  userLinkOverrides?: Record<string, { isLinked: boolean; clipName: string; materialId: string; materialName: string }>,
  customStart?: string,
  customEnd?: string
): VideoAnalysisResult {
  // If selected theater is NOT qingning and NOT all, return capability empty state
  if (selectedTheater !== 'all' && selectedTheater !== 'qingning') {
    return {
      hasVideoLevelData: false,
      unsupportedReason: '当前剧场未提供平台视频级数据',
      totalPlatformVideosCount: 0,
      totalDailyRecordsCount: 0,
      videos: [],
      p75Views: 0,
      p75Revenue: 0,
      isLowSampleCount: true,
      maxViews: 10000,
      maxRevenue: 100,
    };
  }

  // 1. Determine active date range
  let targetDates: string[] = [];
  if (timeRange === 'yesterday') {
    targetDates = ['2026-08-23'];
  } else if (timeRange === '7days') {
    targetDates = [
      '2026-08-17', '2026-08-18', '2026-08-19', '2026-08-20',
      '2026-08-21', '2026-08-22', '2026-08-23'
    ];
  } else if (timeRange === 'this_month') {
    targetDates = Array.from({ length: 23 }, (_, i) => {
      const dd = String(i + 1).padStart(2, '0');
      return `2026-08-${dd}`;
    });
  } else if (timeRange === 'custom') {
    const start = customStart || '2026-08-03';
    const end = customEnd || '2026-08-17';
    const all30: string[] = [];
    const dStart = new Date(2026, 6, 25);
    for (let i = 0; i < 30; i++) {
      const d = new Date(dStart);
      d.setDate(dStart.getDate() + i);
      const mm = String(d.getMonth() + 1).padStart(2, '0');
      const dd = String(d.getDate()).padStart(2, '0');
      all30.push(`${d.getFullYear()}-${mm}-${dd}`);
    }
    targetDates = all30.filter((d) => d >= start && d <= end);
    if (targetDates.length === 0) {
      targetDates = all30.slice(-14);
    }
  } else {
    // 30days
    const start = new Date(2026, 6, 25);
    targetDates = Array.from({ length: 30 }, (_, i) => {
      const d = new Date(start);
      d.setDate(start.getDate() + i);
      const mm = String(d.getMonth() + 1).padStart(2, '0');
      const dd = String(d.getDate()).padStart(2, '0');
      return `${d.getFullYear()}-${mm}-${dd}`;
    });
  }

  const targetDateSet = new Set(targetDates);
  let totalDailyRecordsCount = 0;

  // 2. Aggregate each unique video over the selected time range
  const aggregatedList: AggregatedPlatformVideo[] = [];

  RAW_PLATFORM_VIDEOS.forEach((raw) => {
    // Filter daily records belonging to active period
    const activeDailyRecords = raw.allDailyRecords.filter((rec) => targetDateSet.has(rec.date));
    if (activeDailyRecords.length === 0) return; // Video was not active in this period

    totalDailyRecordsCount += activeDailyRecords.length;

    // Sum period metrics
    const periodVideoViews = activeDailyRecords.reduce((sum, r) => sum + r.videoViews, 0);
    const periodDramaViews = activeDailyRecords.reduce((sum, r) => sum + r.dramaViews, 0);
    const periodRevenue = Math.round(activeDailyRecords.reduce((sum, r) => sum + r.revenue, 0) * 10) / 10;

    const receptionStrength = periodVideoViews > 0
      ? Math.round((periodDramaViews / periodVideoViews) * 100) / 100
      : 0;

    const rpm = periodVideoViews > 0
      ? Math.round((periodRevenue / periodVideoViews) * 1000 * 100) / 100
      : 0;

    // Apply any user link override if modified in current session
    let isLinked = raw.isLinked;
    let linkedClipName = raw.linkedClipName;
    let sourceMaterialId = raw.sourceMaterialId;
    let sourceMaterialName = raw.sourceMaterialName;

    if (userLinkOverrides && userLinkOverrides[raw.id]) {
      const override = userLinkOverrides[raw.id];
      isLinked = override.isLinked;
      linkedClipName = override.clipName;
      sourceMaterialId = override.materialId;
      sourceMaterialName = override.materialName;
    }

    aggregatedList.push({
      id: raw.id,
      theaterKey: raw.theaterKey,
      theaterName: raw.theaterName,
      accountId: raw.accountId,
      accountName: raw.accountName,
      dramaId: raw.dramaId,
      dramaName: raw.dramaName,
      firstObservedDate: raw.firstObservedDate,
      firstObservedShort: raw.firstObservedDate.slice(5),
      candidateBatch: raw.candidateBatch,
      isLinked,
      linkedClipName,
      sourceMaterialId,
      sourceMaterialName,
      candidateClips: raw.candidateClips,
      periodVideoViews,
      periodDramaViews,
      periodRevenue,
      receptionStrength,
      rpm,
      periodDailyRecords: activeDailyRecords,
      quadrant: 'long_tail', // Will classify next
    });
  });

  // 3. Compute dynamic P75 Thresholds for current sample
  const viewsList = aggregatedList.map((v) => v.periodVideoViews);
  const revList = aggregatedList.map((v) => v.periodRevenue);

  const p75Views = calculatePercentile(viewsList, 0.75);
  const p75Revenue = calculatePercentile(revList, 0.75);
  const isLowSampleCount = aggregatedList.length < 20;

  // 4. Assign dynamic quadrants based on P75
  aggregatedList.forEach((v) => {
    const isHighViews = v.periodVideoViews >= p75Views;
    const isHighRev = v.periodRevenue >= p75Revenue;

    if (isHighViews && isHighRev) {
      v.quadrant = 'breakout'; // 爆款转化
    } else if (isHighViews && !isHighRev) {
      v.quadrant = 'hook'; // 引流卡点
    } else if (!isHighViews && isHighRev) {
      v.quadrant = 'high_ticket'; // 高客单转化
    } else {
      v.quadrant = 'long_tail'; // 常规长尾
    }
  });

  const maxViews = Math.max(...viewsList, 50000);
  const maxRevenue = Math.max(...revList, 400);

  return {
    hasVideoLevelData: true,
    totalPlatformVideosCount: aggregatedList.length,
    totalDailyRecordsCount,
    videos: aggregatedList,
    p75Views: Math.round(p75Views),
    p75Revenue: Math.round(p75Revenue * 10) / 10,
    isLowSampleCount,
    maxViews,
    maxRevenue,
  };
}
