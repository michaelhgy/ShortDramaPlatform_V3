// Pure deterministic calculation engine for Data Analysis > Combinations (组合矩阵)
import {
  TimeRangeFilter,
  TheaterFilter,
  CombinationDimension,
  CombinationMetric,
} from '../analyticsTypes';
import { MOCK_LOCATIONS_POOL } from '../analyticsMockData';

export interface CombinationPublishRecord {
  id: string;
  date: string;
  videoName: string;
  accountId: string;
  accountName: string;
  dramaId: string;
  dramaName: string;
  theaterName: string;
  theaterKey: 'qingning' | 'jiuzhou' | 'dianzhong' | 'fanqie' | 'huasheng';
  locationId: string;
  locationText: string;
  revenue: number; // 0 if zero-revenue
  videoViews?: number;
  dramaViews?: number;
  isAttributable: boolean; // if false, revenue is not attributable
}

export interface CalculatedCombinationCell {
  id: string;
  dimension: CombinationDimension;
  rowKey: string;
  rowLabel: string;
  rowSubLabel?: string;
  colKey: string;
  colLabel: string;
  colSubLabel?: string;
  
  // Theater metadata
  rowTheaterKey?: string;
  colTheaterKey?: string;
  theaterName?: string;

  // Status flags
  isInapplicable: boolean; // 跨剧场组合 -> 不适用
  hasRecords: boolean;      // 当前周期是否有发布记录
  isAttributable: boolean;  // 是否具备收益归因能力

  // Metrics
  sampleCount: number;      // 当前周期发布次数
  attributableCount: number; // 具备归因收益的发布数
  zeroRevenueCount: number; // 0收益视频数量 (e.g. 18 / 38)
  totalRevenue: number;     // 可归因收益之和 (不可归因为 0)
  avgRevenue: number;       // 平均单条收益
  medianRevenue: number;    // 中位单条收益
  bestRevenue: number;      // 最高单条收益
  worstRevenue: number;     // 最低单条收益 (非0或包含0中的最低)
  videoViews?: number;      // 视频播放量 (仅青柠支持)
  dramaViews?: number;      // 剧集播放量 (仅青柠支持)

  // Real evidence records
  publishRecords: CombinationPublishRecord[];
}

export interface CombinationMatrixResult {
  dimension: CombinationDimension;
  metric: CombinationMetric;
  timeRange: TimeRangeFilter;
  selectedTheater: TheaterFilter;
  rowHeaders: { key: string; label: string; theaterName?: string }[];
  colHeaders: { key: string; label: string; theaterName?: string }[];
  cellMap: Map<string, CalculatedCombinationCell>;
  
  // Percentile thresholds computed across valid, active positive cells
  percentiles: {
    p25: number;
    p50: number;
    p75: number;
    p90: number;
    maxVal: number;
    count: number;
  };
}

// ---------------------------------------------------------------------------
// 1. RAW ENTITY METADATA (Accounts, Dramas, Virtual Locations)
// ---------------------------------------------------------------------------
interface AccountMeta {
  id: string;
  name: string;
  theaterKey: 'qingning' | 'jiuzhou' | 'dianzhong' | 'fanqie' | 'huasheng';
  theaterName: string;
  hasQingningVideoData: boolean;
  baseDailyPub: number;
  locations: { locationId: string; weight: number }[];
}

interface DramaMeta {
  id: string;
  name: string;
  theaterKey: 'qingning' | 'jiuzhou' | 'dianzhong' | 'fanqie' | 'huasheng';
  theaterName: string;
  hasQingningVideoData: boolean;
  isAttributable: boolean;
  baseRevenueMultiplier: number;
}

const ALL_ACCOUNTS: AccountMeta[] = [
  // 青柠剧场 (7 accounts)
  { id: 'acc-1', name: '短剧黄鸡版', theaterKey: 'qingning', theaterName: '青柠剧场', hasQingningVideoData: true, baseDailyPub: 2.5, locations: [{ locationId: 'loc-1', weight: 0.6 }, { locationId: 'loc-2', weight: 0.3 }, { locationId: 'loc-3', weight: 0.1 }] },
  { id: 'acc-2', name: '鸿记水产行', theaterKey: 'qingning', theaterName: '青柠剧场', hasQingningVideoData: true, baseDailyPub: 2.0, locations: [{ locationId: 'loc-2', weight: 0.7 }, { locationId: 'loc-1', weight: 0.3 }] },
  { id: 'acc-3', name: '冷脸萌萌1701', theaterKey: 'qingning', theaterName: '青柠剧场', hasQingningVideoData: true, baseDailyPub: 1.8, locations: [{ locationId: 'loc-3', weight: 0.65 }, { locationId: 'loc-7', weight: 0.35 }] },
  { id: 'acc-4', name: '格格芝LE', theaterKey: 'qingning', theaterName: '青柠剧场', hasQingningVideoData: true, baseDailyPub: 1.6, locations: [{ locationId: 'loc-7', weight: 0.75 }, { locationId: 'loc-8', weight: 0.25 }] },
  { id: 'acc-11', name: '爆款微剧社-06', theaterKey: 'qingning', theaterName: '青柠剧场', hasQingningVideoData: true, baseDailyPub: 1.2, locations: [{ locationId: 'loc-18', weight: 0.8 }, { locationId: 'loc-4', weight: 0.2 }] },
  { id: 'acc-13', name: '独角兽短剧-09', theaterKey: 'qingning', theaterName: '青柠剧场', hasQingningVideoData: true, baseDailyPub: 1.0, locations: [{ locationId: 'loc-17', weight: 0.9 }, { locationId: 'loc-1', weight: 0.1 }] },
  { id: 'acc-15', name: '剧迷老陈', theaterKey: 'qingning', theaterName: '青柠剧场', hasQingningVideoData: true, baseDailyPub: 0.8, locations: [{ locationId: 'loc-20', weight: 0.8 }, { locationId: 'loc-2', weight: 0.2 }] },

  // 九州剧场 (3 accounts)
  { id: 'acc-5', name: '曾经几何7906', theaterKey: 'jiuzhou', theaterName: '九州剧场', hasQingningVideoData: false, baseDailyPub: 1.8, locations: [{ locationId: 'loc-11', weight: 0.7 }, { locationId: 'loc-12', weight: 0.3 }] },
  { id: 'acc-6', name: '肯德基等你爱你', theaterKey: 'jiuzhou', theaterName: '九州剧场', hasQingningVideoData: false, baseDailyPub: 1.5, locations: [{ locationId: 'loc-13', weight: 0.8 }, { locationId: 'loc-16', weight: 0.2 }] },
  { id: 'acc-12', name: '一口爽剧-08', theaterKey: 'jiuzhou', theaterName: '九州剧场', hasQingningVideoData: false, baseDailyPub: 1.0, locations: [{ locationId: 'loc-11', weight: 0.5 }, { locationId: 'loc-13', weight: 0.5 }] },

  // 点众微剧 (3 accounts)
  { id: 'acc-7', name: '热播短剧社-01', theaterKey: 'dianzhong', theaterName: '点众微剧', hasQingningVideoData: false, baseDailyPub: 1.5, locations: [{ locationId: 'loc-9', weight: 0.7 }, { locationId: 'loc-10', weight: 0.3 }] },
  { id: 'acc-8', name: '深夜追剧馆02', theaterKey: 'dianzhong', theaterName: '点众微剧', hasQingningVideoData: false, baseDailyPub: 1.3, locations: [{ locationId: 'loc-5', weight: 0.8 }, { locationId: 'loc-6', weight: 0.2 }] },
  { id: 'acc-14', name: '星芒短剧工作室', theaterKey: 'dianzhong', theaterName: '点众微剧', hasQingningVideoData: false, baseDailyPub: 0.9, locations: [{ locationId: 'loc-19', weight: 0.85 }, { locationId: 'loc-9', weight: 0.15 }] },

  // 番茄剧场 (2 accounts)
  { id: 'acc-9', name: '逆袭短剧王', theaterKey: 'fanqie', theaterName: '番茄剧场', hasQingningVideoData: false, baseDailyPub: 1.4, locations: [{ locationId: 'loc-16', weight: 0.7 }, { locationId: 'loc-11', weight: 0.3 }] },
  { id: 'acc-10', name: '甜宠小剧场-03', theaterKey: 'fanqie', theaterName: '番茄剧场', hasQingningVideoData: false, baseDailyPub: 1.2, locations: [{ locationId: 'loc-15', weight: 0.8 }, { locationId: 'loc-14', weight: 0.2 }] },

  // 花生剧场 (1 account - 部分收益聚合无法精确单条归因)
  { id: 'acc-16', name: '极光短剧精选', theaterKey: 'huasheng', theaterName: '花生剧场', hasQingningVideoData: false, baseDailyPub: 0.9, locations: [{ locationId: 'loc-21', weight: 0.7 }, { locationId: 'loc-22', weight: 0.3 }] },
];

const ALL_DRAMAS: DramaMeta[] = [
  // 1. 青柠剧场 (6 Dramas)
  { id: 'd-1', name: '风雪草原苍狼少女', theaterKey: 'qingning', theaterName: '青柠剧场', hasQingningVideoData: true, isAttributable: true, baseRevenueMultiplier: 1.6 },
  { id: 'd-2', name: '辣厨回乡鲜椒越香店越旺', theaterKey: 'qingning', theaterName: '青柠剧场', hasQingningVideoData: true, isAttributable: true, baseRevenueMultiplier: 1.3 },
  { id: 'd-3', name: '坠海逢生我率万鲨踏浪归来', theaterKey: 'qingning', theaterName: '青柠剧场', hasQingningVideoData: true, isAttributable: true, baseRevenueMultiplier: 1.1 },
  { id: 'd-4', name: '我用十元盒饭惊艳全城', theaterKey: 'qingning', theaterName: '青柠剧场', hasQingningVideoData: true, isAttributable: true, baseRevenueMultiplier: 0.95 },
  { id: 'd-5', name: '惨遭同行背叛百年野猪认我为王', theaterKey: 'qingning', theaterName: '青柠剧场', hasQingningVideoData: true, isAttributable: true, baseRevenueMultiplier: 0.85 },
  { id: 'd-6', name: '我在武侠世界抽卡成神', theaterKey: 'qingning', theaterName: '青柠剧场', hasQingningVideoData: true, isAttributable: true, baseRevenueMultiplier: 0.75 },

  // 2. 九州剧场 (4 Dramas)
  { id: 'd-7', name: '九天狂尊', theaterKey: 'jiuzhou', theaterName: '九州剧场', hasQingningVideoData: false, isAttributable: true, baseRevenueMultiplier: 1.15 },
  { id: 'd-8', name: '重返巅峰2008', theaterKey: 'jiuzhou', theaterName: '九州剧场', hasQingningVideoData: false, isAttributable: true, baseRevenueMultiplier: 1.0 },
  { id: 'd-9', name: '逆天狂婿叶辰', theaterKey: 'jiuzhou', theaterName: '九州剧场', hasQingningVideoData: false, isAttributable: true, baseRevenueMultiplier: 0.8 },
  { id: 'd-10', name: '大夏第一战神', theaterKey: 'jiuzhou', theaterName: '九州剧场', hasQingningVideoData: false, isAttributable: true, baseRevenueMultiplier: 0.65 },

  // 3. 点众微剧 (4 Dramas)
  { id: 'd-11', name: '顾总，太太又惊艳全球了', theaterKey: 'dianzhong', theaterName: '点众微剧', hasQingningVideoData: false, isAttributable: true, baseRevenueMultiplier: 1.1 },
  { id: 'd-12', name: '我在八零年代当首富', theaterKey: 'dianzhong', theaterName: '点众微剧', hasQingningVideoData: false, isAttributable: true, baseRevenueMultiplier: 0.85 },
  { id: 'd-13', name: '绝世神医闯花都', theaterKey: 'dianzhong', theaterName: '点众微剧', hasQingningVideoData: false, isAttributable: true, baseRevenueMultiplier: 0.7 },
  { id: 'd-14', name: '错嫁豪门傲娇总裁宠上天', theaterKey: 'dianzhong', theaterName: '点众微剧', hasQingningVideoData: false, isAttributable: true, baseRevenueMultiplier: 0.6 },

  // 4. 番茄剧场 (4 Dramas)
  { id: 'd-15', name: '重生之都市修仙', theaterKey: 'fanqie', theaterName: '番茄剧场', hasQingningVideoData: false, isAttributable: true, baseRevenueMultiplier: 0.9 },
  { id: 'd-16', name: '极品小神医', theaterKey: 'fanqie', theaterName: '番茄剧场', hasQingningVideoData: false, isAttributable: true, baseRevenueMultiplier: 0.8 },
  { id: 'd-17', name: '千金归来倾天下', theaterKey: 'fanqie', theaterName: '番茄剧场', hasQingningVideoData: false, isAttributable: true, baseRevenueMultiplier: 0.65 },
  { id: 'd-18', name: '闪婚神秘老公', theaterKey: 'fanqie', theaterName: '番茄剧场', hasQingningVideoData: false, isAttributable: true, baseRevenueMultiplier: 0.5 },

  // 5. 花生剧场 (4 Dramas - 单一账号日收益无法准确细分至单剧，归因缺失)
  { id: 'd-19', name: '战龙出狱', theaterKey: 'huasheng', theaterName: '花生剧场', hasQingningVideoData: false, isAttributable: false, baseRevenueMultiplier: 0.8 },
  { id: 'd-20', name: '首富从摆摊开始', theaterKey: 'huasheng', theaterName: '花生剧场', hasQingningVideoData: false, isAttributable: false, baseRevenueMultiplier: 0.6 },
  { id: 'd-21', name: '龙王归来', theaterKey: 'huasheng', theaterName: '花生剧场', hasQingningVideoData: false, isAttributable: false, baseRevenueMultiplier: 0.5 },
  { id: 'd-22', name: '真假千金逆袭记', theaterKey: 'huasheng', theaterName: '花生剧场', hasQingningVideoData: false, isAttributable: false, baseRevenueMultiplier: 0.4 },
];

// ---------------------------------------------------------------------------
// 2. LOCATIONS LIST (Mapped from Pool)
// ---------------------------------------------------------------------------
export interface LocationMeta {
  id: string;
  name: string; // e.g. "广州 · 天河"
  fullAddress: string;
  province: string;
  city: string;
  district: string;
}

const ALL_LOCATIONS: LocationMeta[] = MOCK_LOCATIONS_POOL.slice(0, 12).map((loc, idx) => ({
  id: `loc-${idx + 1}`,
  name: `${loc.city} · ${loc.district}`,
  fullAddress: loc.fullAddress,
  province: loc.province,
  city: loc.city,
  district: loc.district,
}));

// ---------------------------------------------------------------------------
// 3. GENERATE DETERMINISTIC REPOSITORY OF PUBLISHED VIDEOS
// ---------------------------------------------------------------------------
// 30 full days of published video records from 2026-07-25 to 2026-08-23
function buildAllPublishRecords(): CombinationPublishRecord[] {
  const records: CombinationPublishRecord[] = [];
  const dateList: string[] = [];
  
  // Construct 30 days
  const baseDate = new Date(2026, 7, 23); // Aug 23, 2026
  for (let i = 29; i >= 0; i--) {
    const d = new Date(baseDate);
    d.setDate(baseDate.getDate() - i);
    const y = d.getFullYear();
    const m = String(d.getMonth() + 1).padStart(2, '0');
    const day = String(d.getDate()).padStart(2, '0');
    dateList.push(`${y}-${m}-${day}`);
  }

  // Generate videos per account and its drama pairs
  ALL_ACCOUNTS.forEach((account) => {
    // Only pair with dramas in the SAME theater!
    const applicableDramas = ALL_DRAMAS.filter((d) => d.theaterKey === account.theaterKey);

    applicableDramas.forEach((drama, dramaIdx) => {
      // Deterministic seed for this pair
      const pairSeed = (account.name.charCodeAt(0) * 17 + drama.name.charCodeAt(0) * 23 + dramaIdx * 31);

      dateList.forEach((dateStr, dayIdx) => {
        // Daily activity probability
        const dayMod = (pairSeed + dayIdx * 7) % 100;
        // High affinity dramas publish more frequently
        const shouldPublish = dramaIdx === 0 ? dayMod < 75 : dramaIdx === 1 ? dayMod < 55 : dayMod < 35;

        if (!shouldPublish) return;

        // Number of clips published this day: 1 to 2
        const clipCount = (dayMod % 5 === 0) ? 2 : 1;

        for (let c = 1; c <= clipCount; c++) {
          const videoId = `vid-${account.id}-${drama.id}-${dayIdx}-${c}`;
          const clipNum = ((pairSeed + dayIdx * 3 + c) % 15) + 1;
          const videoName = `${drama.name}-第${clipNum}分段剪辑0${c}`;

          // Pick location based on account's location affinity
          const locIdx = (pairSeed + c + dayIdx) % account.locations.length;
          const locEntry = account.locations[locIdx];
          const fullLoc = ALL_LOCATIONS.find((l) => l.id === locEntry.locationId) || ALL_LOCATIONS[0];

          // Determine revenue distribution
          // High realistic variance: 40% zero or near zero, 50% normal, 10% high-revenue
          const varianceRoll = (pairSeed * 13 + dayIdx * 19 + c * 29) % 100;
          let revenue = 0;
          let videoViews: number | undefined = undefined;
          let dramaViews: number | undefined = undefined;

          if (drama.isAttributable) {
            if (varianceRoll < 35) {
              // 0 revenue (真实业务中约 35% 推广视频无转化产生)
              revenue = 0;
            } else if (varianceRoll < 85) {
              // Normal revenue: ¥15 ~ ¥180
              const base = 25 + (varianceRoll % 40) * 3.5;
              revenue = Number((base * drama.baseRevenueMultiplier).toFixed(2));
            } else {
              // High breakout video: ¥220 ~ ¥680
              const base = 220 + (varianceRoll % 15) * 28;
              revenue = Number((base * drama.baseRevenueMultiplier).toFixed(2));
            }
          } else {
            // Huasheng theater cannot attribute revenue to individual videos
            revenue = 0;
          }

          // Views for Qingning theater
          if (account.hasQingningVideoData) {
            if (revenue === 0) {
              videoViews = Math.floor(1200 + (varianceRoll % 20) * 450);
              dramaViews = Math.floor(videoViews * 0.8);
            } else {
              videoViews = Math.floor(15000 + (revenue * 120) + (varianceRoll % 30) * 1500);
              dramaViews = Math.floor(videoViews * (1.25 + (varianceRoll % 10) * 0.05));
            }
          }

          records.push({
            id: videoId,
            date: dateStr,
            videoName,
            accountId: account.id,
            accountName: account.name,
            dramaId: drama.id,
            dramaName: drama.name,
            theaterName: account.theaterName,
            theaterKey: account.theaterKey,
            locationId: fullLoc.id,
            locationText: fullLoc.fullAddress,
            revenue,
            videoViews,
            dramaViews,
            isAttributable: drama.isAttributable,
          });
        }
      });
    });
  });

  return records;
}

const GLOBAL_PUBLISH_RECORDS = buildAllPublishRecords();

// ---------------------------------------------------------------------------
// 4. FILTER RECORDS BY TIMERANGE
// ---------------------------------------------------------------------------
function getStartDateForTimeRange(timeRange: TimeRangeFilter, customStart?: string): string {
  if (timeRange === 'yesterday') return '2026-08-23';
  if (timeRange === '7days') return '2026-08-17';
  if (timeRange === '30days') return '2026-07-25';
  if (timeRange === 'this_month') return '2026-08-01';
  if (timeRange === 'custom') return customStart || '2026-08-03';
  return '2026-08-17';
}

function filterRecordsByTime(
  records: CombinationPublishRecord[], 
  timeRange: TimeRangeFilter,
  customStart?: string,
  customEnd?: string
): CombinationPublishRecord[] {
  const startDate = getStartDateForTimeRange(timeRange, customStart);
  const endDate = timeRange === 'custom' ? (customEnd || '2026-08-17') : '2026-08-23';

  if (timeRange === 'yesterday') {
    return records.filter((r) => r.date === '2026-08-23');
  }
  return records.filter((r) => r.date >= startDate && r.date <= endDate);
}

// ---------------------------------------------------------------------------
// 5. MAIN COMBINATION CALCULATION ENGINE
// ---------------------------------------------------------------------------
export function calculateCombinationMatrix(
  dimension: CombinationDimension,
  metric: CombinationMetric,
  timeRange: TimeRangeFilter,
  selectedTheater: TheaterFilter,
  customStart?: string,
  customEnd?: string
): CombinationMatrixResult {
  // 1. Filter global publish records by timeRange
  const periodRecords = filterRecordsByTime(GLOBAL_PUBLISH_RECORDS, timeRange, customStart, customEnd);

  // 2. Filter available entities by selectedTheater
  const theaterFilterKey = selectedTheater === 'all' ? null : selectedTheater;

  let filteredAccounts = ALL_ACCOUNTS;
  let filteredDramas = ALL_DRAMAS;
  let filteredLocations = ALL_LOCATIONS;

  if (theaterFilterKey) {
    filteredAccounts = ALL_ACCOUNTS.filter((a) => a.theaterKey === theaterFilterKey);
    filteredDramas = ALL_DRAMAS.filter((d) => d.theaterKey === theaterFilterKey);
  }

  // 3. Build Row & Column headers based on dimension
  let rowHeaders: { key: string; label: string; theaterName?: string }[] = [];
  let colHeaders: { key: string; label: string; theaterName?: string }[] = [];

  if (dimension === 'account_x_drama') {
    rowHeaders = filteredAccounts.map((a) => ({ key: a.id, label: a.name, theaterName: a.theaterName }));
    colHeaders = filteredDramas.map((d) => ({ key: d.id, label: d.name, theaterName: d.theaterName }));
  } else if (dimension === 'account_x_location') {
    rowHeaders = filteredAccounts.map((a) => ({ key: a.id, label: a.name, theaterName: a.theaterName }));
    colHeaders = filteredLocations.map((l) => ({ key: l.id, label: l.name }));
  } else if (dimension === 'drama_x_location') {
    rowHeaders = filteredDramas.map((d) => ({ key: d.id, label: d.name, theaterName: d.theaterName }));
    colHeaders = filteredLocations.map((l) => ({ key: l.id, label: l.name }));
  }

  // 4. Populate Cells
  const cellMap = new Map<string, CalculatedCombinationCell>();
  const activeMetricValues: number[] = [];

  rowHeaders.forEach((row) => {
    colHeaders.forEach((col) => {
      const mapKey = `${row.key}:::${col.key}`;
      const cellId = `cell-${dimension}-${row.key}-${col.key}`;

      let isInapplicable = false;
      let matchingRecords: CombinationPublishRecord[] = [];
      let isAttributable = true;

      if (dimension === 'account_x_drama') {
        const acc = ALL_ACCOUNTS.find((a) => a.id === row.key);
        const drama = ALL_DRAMAS.find((d) => d.id === col.key);

        // Official Business Rule: A drama belongs to only one theater!
        // If account theater !== drama theater -> 不适用
        if (acc && drama && acc.theaterKey !== drama.theaterKey) {
          isInapplicable = true;
        } else {
          isInapplicable = false;
          matchingRecords = periodRecords.filter((r) => r.accountId === row.key && r.dramaId === col.key);
          if (drama && !drama.isAttributable) {
            isAttributable = false;
          }
        }
      } else if (dimension === 'account_x_location') {
        matchingRecords = periodRecords.filter((r) => r.accountId === row.key && r.locationId === col.key);
        const acc = ALL_ACCOUNTS.find((a) => a.id === row.key);
        if (acc?.theaterKey === 'huasheng') {
          isAttributable = false;
        }
      } else if (dimension === 'drama_x_location') {
        matchingRecords = periodRecords.filter((r) => r.dramaId === row.key && r.locationId === col.key);
        const drama = ALL_DRAMAS.find((d) => d.id === row.key);
        if (drama && !drama.isAttributable) {
          isAttributable = false;
        }
      }

      if (isInapplicable) {
        cellMap.set(mapKey, {
          id: cellId,
          dimension,
          rowKey: row.key,
          rowLabel: row.label,
          colKey: col.key,
          colLabel: col.label,
          rowTheaterKey: row.theaterName,
          colTheaterKey: col.theaterName,
          isInapplicable: true,
          hasRecords: false,
          isAttributable: false,
          sampleCount: 0,
          attributableCount: 0,
          zeroRevenueCount: 0,
          totalRevenue: 0,
          avgRevenue: 0,
          medianRevenue: 0,
          bestRevenue: 0,
          worstRevenue: 0,
          publishRecords: [],
        });
        return;
      }

      const sampleCount = matchingRecords.length;
      const hasRecords = sampleCount > 0;

      if (!hasRecords) {
        cellMap.set(mapKey, {
          id: cellId,
          dimension,
          rowKey: row.key,
          rowLabel: row.label,
          colKey: col.key,
          colLabel: col.label,
          isInapplicable: false,
          hasRecords: false,
          isAttributable,
          sampleCount: 0,
          attributableCount: 0,
          zeroRevenueCount: 0,
          totalRevenue: 0,
          avgRevenue: 0,
          medianRevenue: 0,
          bestRevenue: 0,
          worstRevenue: 0,
          publishRecords: [],
        });
        return;
      }

      // Calculate statistics on matching records
      const attributableRecords = matchingRecords.filter((r) => r.isAttributable);
      const zeroRevenueCount = matchingRecords.filter((r) => r.revenue === 0).length;
      const totalRevenue = attributableRecords.reduce((acc, r) => acc + r.revenue, 0);
      const avgRevenue = attributableRecords.length > 0 ? totalRevenue / attributableRecords.length : 0;

      // Sorted revenues for median and extremes
      const sortedRevenues = attributableRecords.map((r) => r.revenue).sort((a, b) => a - b);
      const bestRevenue = sortedRevenues.length > 0 ? sortedRevenues[sortedRevenues.length - 1] : 0;
      const worstRevenue = sortedRevenues.length > 0 ? sortedRevenues[0] : 0;
      const midIdx = Math.floor(sortedRevenues.length / 2);
      const medianRevenue = sortedRevenues.length > 0 
        ? (sortedRevenues.length % 2 !== 0 ? sortedRevenues[midIdx] : (sortedRevenues[midIdx - 1] + sortedRevenues[midIdx]) / 2)
        : 0;

      // Views
      const hasViews = matchingRecords.some((r) => r.videoViews !== undefined);
      const totalVideoViews = hasViews ? matchingRecords.reduce((acc, r) => acc + (r.videoViews || 0), 0) : undefined;
      const totalDramaViews = hasViews ? matchingRecords.reduce((acc, r) => acc + (r.dramaViews || 0), 0) : undefined;

      const cellData: CalculatedCombinationCell = {
        id: cellId,
        dimension,
        rowKey: row.key,
        rowLabel: row.label,
        colKey: col.key,
        colLabel: col.label,
        isInapplicable: false,
        hasRecords: true,
        isAttributable,
        sampleCount,
        attributableCount: attributableRecords.length,
        zeroRevenueCount,
        totalRevenue: Number(totalRevenue.toFixed(2)),
        avgRevenue: Number(avgRevenue.toFixed(2)),
        medianRevenue: Number(medianRevenue.toFixed(2)),
        bestRevenue: Number(bestRevenue.toFixed(2)),
        worstRevenue: Number(worstRevenue.toFixed(2)),
        videoViews: totalVideoViews,
        dramaViews: totalDramaViews,
        publishRecords: matchingRecords.sort((a, b) => b.date.localeCompare(a.date)),
      };

      cellMap.set(mapKey, cellData);

      // Collect active metric value for percentile calculation
      let metricVal = 0;
      if (metric === 'total_revenue') {
        if (isAttributable && totalRevenue > 0) metricVal = totalRevenue;
      } else if (metric === 'avg_revenue') {
        if (isAttributable && avgRevenue > 0) metricVal = avgRevenue;
      } else if (metric === 'publish_count') {
        if (sampleCount > 0) metricVal = sampleCount;
      } else if (metric === 'video_views') {
        if (totalVideoViews && totalVideoViews > 0) metricVal = totalVideoViews;
      } else if (metric === 'drama_views') {
        if (totalDramaViews && totalDramaViews > 0) metricVal = totalDramaViews;
      }

      if (metricVal > 0) {
        activeMetricValues.push(metricVal);
      }
    });
  });

  // 5. Percentile calculation
  activeMetricValues.sort((a, b) => a - b);
  const count = activeMetricValues.length;

  const getPercentile = (p: number) => {
    if (count === 0) return 1;
    const index = Math.min(count - 1, Math.max(0, Math.floor(count * p)));
    return activeMetricValues[index];
  };

  const p25 = getPercentile(0.25);
  const p50 = getPercentile(0.50);
  const p75 = getPercentile(0.75);
  const p90 = getPercentile(0.90);
  const maxVal = count > 0 ? activeMetricValues[count - 1] : 1;

  return {
    dimension,
    metric,
    timeRange,
    selectedTheater,
    rowHeaders,
    colHeaders,
    cellMap,
    percentiles: {
      p25,
      p50,
      p75,
      p90,
      maxVal,
      count,
    },
  };
}
