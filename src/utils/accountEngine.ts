// Pure deterministic calculation engine for Data Analysis > Accounts (账号)
import {
  TimeRangeFilter,
  TheaterFilter,
  AccountAnalyticsItem,
  AccountDramaPerformance,
  AccountLocationPerformance,
  AccountVirtualLocation,
} from '../analyticsTypes';
import { MOCK_LOCATIONS_POOL } from '../analyticsMockData';

export interface CalculatedAccountItem extends AccountAnalyticsItem {
  theaterKey: 'qingning' | 'jiuzhou' | 'dianzhong' | 'fanqie' | 'huasheng';
  periodRevenue: number;
  dailyAverageRevenue: number;
  recent7DayAvgRevenue: number;
  periodVideoViews?: number;
  periodDramaViews?: number;
  yesterdayRevenue: number;
  yesterdayVideoViews?: number;
  changeVsRecentAvgPct: number | null;
  dailyTrendPoints: {
    date: string;
    dayLabel: string;
    revenue: number;
    videoViews?: number;
    isYesterday?: boolean;
  }[];
  dramaPerformancesInPeriod: {
    dramaId: string;
    dramaName: string;
    publishCount: number;
    totalRevenue?: number;
    avgRevenuePerVideo?: number;
    videoViews?: number;
    dramaViews?: number;
    isAttributable: boolean;
  }[];
}

// 16 Structured Accounts across 5 theaters
interface RawAccountMeta {
  id: string;
  name: string;
  theaterKey: 'qingning' | 'jiuzhou' | 'dianzhong' | 'fanqie' | 'huasheng';
  theaterName: string;
  hasQingningVideoData: boolean;
  baseDailyRevenue: number;
  recentMainDrama: string;
  defaultLocation: AccountVirtualLocation;
  historicalLocations: AccountLocationPerformance[];
  dramasMeta: {
    dramaId: string;
    dramaName: string;
    shareWeight: number;
    basePubPerDay: number;
    isAttributable: boolean;
  }[];
}

const RAW_ACCOUNTS_METAS: RawAccountMeta[] = [
  // 1. 青柠剧场 (Qingning - 7 accounts with full video-level metrics)
  {
    id: 'acc-1',
    name: '短剧黄鸡版',
    theaterKey: 'qingning',
    theaterName: '青柠剧场',
    hasQingningVideoData: true,
    baseDailyRevenue: 620,
    recentMainDrama: '风雪草原苍狼少女',
    defaultLocation: MOCK_LOCATIONS_POOL[0], // 广州天河
    historicalLocations: [
      { locationId: 'loc-1', fullAddress: '广东省广州市天河区体育西路103号维多利广场B座', usedCount: 26, totalRevenue: 13890.0, videoViews: 980000, dramaViews: 1390000, lastUsedDate: '2026-08-23' },
      { locationId: 'loc-2', fullAddress: '广东省深圳市南山区粤海街道高新南一道科技园08栋', usedCount: 9, totalRevenue: 4320.0, videoViews: 310000, dramaViews: 440000, lastUsedDate: '2026-08-19' },
      { locationId: 'loc-3', fullAddress: '浙江省杭州市余杭区文一西路969号未来科技城5号楼', usedCount: 4, totalRevenue: 1850.0, videoViews: 140000, dramaViews: 195000, lastUsedDate: '2026-08-14' },
    ],
    dramasMeta: [
      { dramaId: 'd-1', dramaName: '风雪草原苍狼少女', shareWeight: 0.58, basePubPerDay: 1.1, isAttributable: true },
      { dramaId: 'd-2', dramaName: '辣厨回乡鲜椒越香店越旺', shareWeight: 0.27, basePubPerDay: 0.6, isAttributable: true },
      { dramaId: 'd-3', dramaName: '坠海逢生我率万鲨踏浪归来', shareWeight: 0.15, basePubPerDay: 0.4, isAttributable: true },
    ],
  },
  {
    id: 'acc-2',
    name: '鸿记水产行',
    theaterKey: 'qingning',
    theaterName: '青柠剧场',
    hasQingningVideoData: true,
    baseDailyRevenue: 480,
    recentMainDrama: '惨遭同行背叛百年野猪认我为王',
    defaultLocation: MOCK_LOCATIONS_POOL[1], // 深圳南山
    historicalLocations: [
      { locationId: 'loc-2', fullAddress: '广东省深圳市南山区粤海街道高新南一道科技园08栋', usedCount: 22, totalRevenue: 9860.0, videoViews: 730000, dramaViews: 940000, lastUsedDate: '2026-08-23' },
      { locationId: 'loc-1', fullAddress: '广东省广州市天河区体育西路103号维多利广场B座', usedCount: 8, totalRevenue: 3450.0, videoViews: 260000, dramaViews: 330000, lastUsedDate: '2026-08-18' },
    ],
    dramasMeta: [
      { dramaId: 'd-5', dramaName: '惨遭同行背叛百年野猪认我为王', shareWeight: 0.55, basePubPerDay: 1.0, isAttributable: true },
      { dramaId: 'd-4', dramaName: '我用十元盒饭惊艳全城', shareWeight: 0.30, basePubPerDay: 0.5, isAttributable: true },
      { dramaId: 'd-1', dramaName: '风雪草原苍狼少女', shareWeight: 0.15, basePubPerDay: 0.3, isAttributable: true },
    ],
  },
  {
    id: 'acc-3',
    name: '冷脸萌萌1701',
    theaterKey: 'qingning',
    theaterName: '青柠剧场',
    hasQingningVideoData: true,
    baseDailyRevenue: 390,
    recentMainDrama: '辣厨回乡鲜椒越香店越旺',
    defaultLocation: MOCK_LOCATIONS_POOL[2], // 杭州余杭
    historicalLocations: [
      { locationId: 'loc-3', fullAddress: '浙江省杭州市余杭区文一西路969号未来科技城5号楼', usedCount: 20, totalRevenue: 8400.0, videoViews: 630000, dramaViews: 890000, lastUsedDate: '2026-08-23' },
      { locationId: 'loc-7', fullAddress: '上海市静安区南京西路1266号恒隆广场二期', usedCount: 7, totalRevenue: 2820.0, videoViews: 210000, dramaViews: 300000, lastUsedDate: '2026-08-19' },
    ],
    dramasMeta: [
      { dramaId: 'd-2', dramaName: '辣厨回乡鲜椒越香店越旺', shareWeight: 0.62, basePubPerDay: 0.9, isAttributable: true },
      { dramaId: 'd-6', dramaName: '我在武侠世界抽卡成神', shareWeight: 0.26, basePubPerDay: 0.5, isAttributable: true },
      { dramaId: 'd-8', dramaName: '顾总，太太又惊艳全球了', shareWeight: 0.12, basePubPerDay: 0.3, isAttributable: true },
    ],
  },
  {
    id: 'acc-4',
    name: '格格芝LE',
    theaterKey: 'qingning',
    theaterName: '青柠剧场',
    hasQingningVideoData: true,
    baseDailyRevenue: 350,
    recentMainDrama: '坠海逢生我率万鲨踏浪归来',
    defaultLocation: MOCK_LOCATIONS_POOL[6], // 上海静安
    historicalLocations: [
      { locationId: 'loc-7', fullAddress: '上海市静安区南京西路1266号恒隆广场二期', usedCount: 19, totalRevenue: 7350.0, videoViews: 540000, dramaViews: 730000, lastUsedDate: '2026-08-23' },
      { locationId: 'loc-8', fullAddress: '上海市浦东新区世纪大道100号环球金融中心', usedCount: 6, totalRevenue: 2280.0, videoViews: 170000, dramaViews: 230000, lastUsedDate: '2026-08-18' },
    ],
    dramasMeta: [
      { dramaId: 'd-3', dramaName: '坠海逢生我率万鲨踏浪归来', shareWeight: 0.65, basePubPerDay: 0.8, isAttributable: true },
      { dramaId: 'd-1', dramaName: '风雪草原苍狼少女', shareWeight: 0.35, basePubPerDay: 0.5, isAttributable: true },
    ],
  },
  {
    id: 'acc-11',
    name: '爆款微剧社-06',
    theaterKey: 'qingning',
    theaterName: '青柠剧场',
    hasQingningVideoData: true,
    baseDailyRevenue: 110,
    recentMainDrama: '我在武侠世界抽卡成神',
    defaultLocation: MOCK_LOCATIONS_POOL[4], // 苏州工业园
    historicalLocations: [
      { locationId: 'loc-5', fullAddress: '江苏省苏州市工业园区星湖街328号创意产业园A4栋', usedCount: 14, totalRevenue: 3120.0, videoViews: 230000, dramaViews: 320000, lastUsedDate: '2026-08-23' },
    ],
    dramasMeta: [
      { dramaId: 'd-6', dramaName: '我在武侠世界抽卡成神', shareWeight: 0.70, basePubPerDay: 0.6, isAttributable: true },
      { dramaId: 'd-7', dramaName: '重返巅峰2008', shareWeight: 0.30, basePubPerDay: 0.3, isAttributable: true },
    ],
  },
  {
    id: 'acc-13',
    name: '独角兽短剧-09',
    theaterKey: 'qingning',
    theaterName: '青柠剧场',
    hasQingningVideoData: true,
    baseDailyRevenue: 75,
    recentMainDrama: '我用十元盒饭惊艳全城',
    defaultLocation: MOCK_LOCATIONS_POOL[14], // 厦门思明
    historicalLocations: [
      { locationId: 'loc-15', fullAddress: '福建省厦门市思明区鹭江道8号厦门国际银行大厦', usedCount: 10, totalRevenue: 2150.0, videoViews: 160000, dramaViews: 220000, lastUsedDate: '2026-08-22' },
    ],
    dramasMeta: [
      { dramaId: 'd-4', dramaName: '我用十元盒饭惊艳全城', shareWeight: 1.0, basePubPerDay: 0.5, isAttributable: true },
    ],
  },
  {
    id: 'acc-15',
    name: '剧迷老陈',
    theaterKey: 'qingning',
    theaterName: '青柠剧场',
    hasQingningVideoData: true,
    baseDailyRevenue: 45,
    recentMainDrama: '惨遭同行背叛百年野猪认我为王',
    defaultLocation: MOCK_LOCATIONS_POOL[3], // 宁波鄞州
    historicalLocations: [
      { locationId: 'loc-4', fullAddress: '浙江省宁波市鄞州区百丈东路99号国际金融会展中心', usedCount: 8, totalRevenue: 1310.0, videoViews: 95000, dramaViews: 130000, lastUsedDate: '2026-08-21' },
    ],
    dramasMeta: [
      { dramaId: 'd-5', dramaName: '惨遭同行背叛百年野猪认我为王', shareWeight: 1.0, basePubPerDay: 0.4, isAttributable: true },
    ],
  },

  // 2. 九州剧场 (Jiuzhou - 3 accounts, Regular billing, No video-level views)
  {
    id: 'acc-5',
    name: '曾经几何7906',
    theaterKey: 'jiuzhou',
    theaterName: '九州剧场',
    hasQingningVideoData: false,
    baseDailyRevenue: 280,
    recentMainDrama: '我用十元盒饭惊艳全城',
    defaultLocation: MOCK_LOCATIONS_POOL[10], // 成都武侯
    historicalLocations: [
      { locationId: 'loc-11', fullAddress: '四川省成都市武侯区天府三街199号新希望国际大厦', usedCount: 21, totalRevenue: 6480.0, lastUsedDate: '2026-08-23' },
      { locationId: 'loc-16', fullAddress: '重庆市渝中区解放碑民权路28号时代广场B栋', usedCount: 5, totalRevenue: 1420.0, lastUsedDate: '2026-08-16' },
    ],
    dramasMeta: [
      { dramaId: 'd-4', dramaName: '我用十元盒饭惊艳全城', shareWeight: 0.65, basePubPerDay: 0.7, isAttributable: true },
      { dramaId: 'd-3', dramaName: '坠海逢生我率万鲨踏浪归来', shareWeight: 0.35, basePubPerDay: 0.4, isAttributable: true },
    ],
  },
  {
    id: 'acc-6',
    name: '肯德基等你爱你',
    theaterKey: 'jiuzhou',
    theaterName: '九州剧场',
    hasQingningVideoData: false,
    baseDailyRevenue: 240,
    recentMainDrama: '我在武侠世界抽卡成神',
    defaultLocation: MOCK_LOCATIONS_POOL[12], // 长沙岳麓
    historicalLocations: [
      { locationId: 'loc-13', fullAddress: '湖南省长沙市岳麓区麓谷大道627号新材料产业园2栋', usedCount: 18, totalRevenue: 5740.0, lastUsedDate: '2026-08-23' },
    ],
    dramasMeta: [
      { dramaId: 'd-6', dramaName: '我在武侠世界抽卡成神', shareWeight: 0.70, basePubPerDay: 0.7, isAttributable: true },
      { dramaId: 'd-7', dramaName: '重返巅峰2008', shareWeight: 0.30, basePubPerDay: 0.3, isAttributable: true },
    ],
  },
  {
    id: 'acc-12',
    name: '一口爽剧-08',
    theaterKey: 'jiuzhou',
    theaterName: '九州剧场',
    hasQingningVideoData: false,
    baseDailyRevenue: 100,
    recentMainDrama: '辣厨回乡鲜椒越香店越旺',
    defaultLocation: MOCK_LOCATIONS_POOL[11], // 武汉洪山
    historicalLocations: [
      { locationId: 'loc-12', fullAddress: '湖北省武汉市洪山区关山大道光谷软件园F4栋创新楼', usedCount: 11, totalRevenue: 2350.0, lastUsedDate: '2026-08-21' },
    ],
    dramasMeta: [
      { dramaId: 'd-2', dramaName: '辣厨回乡鲜椒越香店越旺', shareWeight: 1.0, basePubPerDay: 0.5, isAttributable: true },
    ],
  },

  // 3. 点众微剧 (Dianzhong - 3 accounts, Direct flow, No video-level views)
  {
    id: 'acc-7',
    name: '热播短剧社-01',
    theaterKey: 'dianzhong',
    theaterName: '点众微剧',
    hasQingningVideoData: false,
    baseDailyRevenue: 210,
    recentMainDrama: '重返巅峰2008',
    defaultLocation: MOCK_LOCATIONS_POOL[8], // 北京朝阳
    historicalLocations: [
      { locationId: 'loc-9', fullAddress: '北京市朝阳区建国门外大街1号国贸大厦B座', usedCount: 17, totalRevenue: 5120.0, lastUsedDate: '2026-08-23' },
      { locationId: 'loc-10', fullAddress: '北京市海淀区中关村南大街1号海龙数码大厦', usedCount: 4, totalRevenue: 1180.0, lastUsedDate: '2026-08-17' },
    ],
    dramasMeta: [
      { dramaId: 'd-7', dramaName: '重返巅峰2008', shareWeight: 0.68, basePubPerDay: 0.6, isAttributable: true },
      { dramaId: 'd-8', dramaName: '顾总，太太又惊艳全球了', shareWeight: 0.32, basePubPerDay: 0.3, isAttributable: true },
    ],
  },
  {
    id: 'acc-8',
    name: '深夜追剧馆02',
    theaterKey: 'dianzhong',
    theaterName: '点众微剧',
    hasQingningVideoData: false,
    baseDailyRevenue: 170,
    recentMainDrama: '顾总，太太又惊艳全球了',
    defaultLocation: MOCK_LOCATIONS_POOL[5], // 南京玄武
    historicalLocations: [
      { locationId: 'loc-6', fullAddress: '江苏省南京市玄武区中山东路18号国际贸易中心33层', usedCount: 15, totalRevenue: 4320.0, lastUsedDate: '2026-08-23' },
    ],
    dramasMeta: [
      { dramaId: 'd-8', dramaName: '顾总，太太又惊艳全球了', shareWeight: 1.0, basePubPerDay: 0.5, isAttributable: true },
    ],
  },
  {
    id: 'acc-14',
    name: '星芒短剧工作室',
    theaterKey: 'dianzhong',
    theaterName: '点众微剧',
    hasQingningVideoData: false,
    baseDailyRevenue: 60,
    recentMainDrama: '重返巅峰2008',
    defaultLocation: MOCK_LOCATIONS_POOL[13], // 青岛市南
    historicalLocations: [
      { locationId: 'loc-14', fullAddress: '山东省青岛市市南区香港中路6号世贸中心A座', usedCount: 8, totalRevenue: 1520.0, lastUsedDate: '2026-08-20' },
    ],
    dramasMeta: [
      { dramaId: 'd-7', dramaName: '重返巅峰2008', shareWeight: 1.0, basePubPerDay: 0.4, isAttributable: true },
    ],
  },

  // 4. 番茄剧场 (Fanqie - 2 accounts, Direct flow, No video-level views)
  {
    id: 'acc-9',
    name: '逆袭短剧王',
    theaterKey: 'fanqie',
    theaterName: '番茄剧场',
    hasQingningVideoData: false,
    baseDailyRevenue: 150,
    recentMainDrama: '我在武侠世界抽卡成神',
    defaultLocation: MOCK_LOCATIONS_POOL[17], // 郑州金水
    historicalLocations: [
      { locationId: 'loc-18', fullAddress: '河南省郑州市金水区农业路东段经三路金融广场', usedCount: 14, totalRevenue: 3890.0, lastUsedDate: '2026-08-23' },
    ],
    dramasMeta: [
      { dramaId: 'd-6', dramaName: '我在武侠世界抽卡成神', shareWeight: 1.0, basePubPerDay: 0.5, isAttributable: true },
    ],
  },
  {
    id: 'acc-16',
    name: '番茄新风-04',
    theaterKey: 'fanqie',
    theaterName: '番茄剧场',
    hasQingningVideoData: false,
    baseDailyRevenue: 120,
    recentMainDrama: '风雪草原苍狼少女',
    defaultLocation: MOCK_LOCATIONS_POOL[18], // 合肥蜀山
    historicalLocations: [
      { locationId: 'loc-19', fullAddress: '安徽省合肥市蜀山区潜山路111号华润大厦东塔', usedCount: 11, totalRevenue: 2880.0, lastUsedDate: '2026-08-22' },
    ],
    dramasMeta: [
      { dramaId: 'd-1', dramaName: '风雪草原苍狼少女', shareWeight: 1.0, basePubPerDay: 0.4, isAttributable: true },
    ],
  },

  // 5. 花生剧场 (Huasheng - 1 account, Estimated billing, Unattributable revenue to drama)
  {
    id: 'acc-10',
    name: '甜宠小剧场-03',
    theaterKey: 'huasheng',
    theaterName: '花生剧场',
    hasQingningVideoData: false,
    baseDailyRevenue: 140,
    recentMainDrama: '顾总，太太又惊艳全球了',
    defaultLocation: MOCK_LOCATIONS_POOL[16], // 西安雁塔
    historicalLocations: [
      { locationId: 'loc-17', fullAddress: '陕西省西安市雁塔区高新一路创新大厦12层', usedCount: 12, totalRevenue: 3450.0, lastUsedDate: '2026-08-23' },
    ],
    dramasMeta: [
      { dramaId: 'd-8', dramaName: '顾总，太太又惊艳全球了', shareWeight: 1.0, basePubPerDay: 0.5, isAttributable: false }, // Unattributable in Peanut!
    ],
  },
];

// Precompute 30 continuous dates (2026-07-25 to 2026-08-23)
const ALL_DATES: string[] = [];
(() => {
  const d = new Date(2026, 6, 25);
  for (let i = 0; i < 30; i++) {
    const y = d.getFullYear();
    const m = String(d.getMonth() + 1).padStart(2, '0');
    const day = String(d.getDate()).padStart(2, '0');
    ALL_DATES.push(`${y}-${m}-${day}`);
    d.setDate(d.getDate() + 1);
  }
})();

// Calculate account revenue for a specific date deterministically
function getDailyAccountMetrics(acc: RawAccountMeta, date: string, dayIdx: number) {
  let rev = acc.baseDailyRevenue;
  const wave = Math.sin(dayIdx * 0.4 + acc.baseDailyRevenue * 0.01) * 0.12 + Math.cos(dayIdx * 0.7) * 0.08;
  rev = Math.round(rev * (1 + wave));

  // Specific realistic scenario tuning:
  if (acc.id === 'acc-1') {
    if (date === '2026-08-21') rev = 640;
    if (date === '2026-08-22') rev = 660;
    if (date === '2026-08-23') rev = 720;
  } else if (acc.id === 'acc-2') {
    if (date === '2026-08-21') rev = 430;
    if (date === '2026-08-22') rev = 380;
    if (date === '2026-08-23') rev = 310;
  } else if (acc.id === 'acc-12') {
    if (date === '2026-08-22' || date === '2026-08-23') rev = 0;
  } else if (acc.id === 'acc-16') {
    if (date === '2026-08-23') rev = 0; // pending collection
  }

  const isQingning = acc.hasQingningVideoData;
  const videoViews = isQingning ? (rev > 0 ? Math.round(rev * 72 + (dayIdx % 7) * 450) : 0) : undefined;
  const dramaViews = isQingning ? (rev > 0 ? Math.round(rev * 105 + (dayIdx % 5) * 620) : 0) : undefined;

  return { revenue: rev, videoViews, dramaViews };
}

export function calculateAccountsAnalytics(
  timeRange: TimeRangeFilter,
  selectedTheater: TheaterFilter,
  customStart?: string,
  customEnd?: string
): {
  accounts: CalculatedAccountItem[];
  totalAccountsInScope: number;
  theaterFilterName: string;
} {
  // 1. Determine date array for current timeRange
  let activeDates: string[] = [];
  const latestDate = ALL_DATES[ALL_DATES.length - 1]; // '2026-08-23'

  if (timeRange === 'yesterday') {
    activeDates = [latestDate];
  } else if (timeRange === '7days') {
    activeDates = ALL_DATES.slice(-7); // '2026-08-17' ~ '2026-08-23'
  } else if (timeRange === '30days') {
    activeDates = [...ALL_DATES]; // 30 days
  } else if (timeRange === 'this_month') {
    activeDates = ALL_DATES.filter((d) => d.startsWith('2026-08')); // '2026-08-01' ~ '2026-08-23' (23 days)
  } else if (timeRange === 'custom') {
    const start = customStart || '2026-08-03';
    const end = customEnd || '2026-08-17';
    activeDates = ALL_DATES.filter((d) => d >= start && d <= end);
    if (activeDates.length === 0) {
      activeDates = ALL_DATES.slice(-14);
    }
  } else {
    activeDates = ALL_DATES.slice(-14);
  }

  const recent7Dates = ALL_DATES.slice(-7);

  // 2. Filter accounts by theater
  const filteredMetas = RAW_ACCOUNTS_METAS.filter((acc) => {
    if (selectedTheater === 'all') return true;
    return acc.theaterKey === selectedTheater;
  });

  const theaterNamesMap: Record<string, string> = {
    all: '全部剧场',
    qingning: '青柠剧场',
    jiuzhou: '九州剧场',
    dianzhong: '点众微剧',
    fanqie: '番茄剧场',
    huasheng: '花生剧场',
  };

  // 3. Compute dynamic metrics for each account
  const calculatedAccounts: CalculatedAccountItem[] = filteredMetas.map((acc) => {
    // A. Period Revenue & Daily Breakdown
    let periodRevenue = 0;
    let periodVideoViews = 0;
    let periodDramaViews = 0;

    const dailyTrendPoints = activeDates.map((date) => {
      const dayIdx = ALL_DATES.indexOf(date);
      const metrics = getDailyAccountMetrics(acc, date, dayIdx);
      periodRevenue += metrics.revenue;
      if (metrics.videoViews) periodVideoViews += metrics.videoViews;
      if (metrics.dramaViews) periodDramaViews += metrics.dramaViews;

      return {
        date,
        dayLabel: date.slice(5),
        revenue: metrics.revenue,
        videoViews: metrics.videoViews,
        isYesterday: date === latestDate,
      };
    });

    const dailyAverageRevenue = Math.round((periodRevenue / activeDates.length) * 100) / 100;

    // B. Yesterday & Recent 7-Day Baseline
    const yesterdayDayIdx = ALL_DATES.length - 1;
    const yesterdayMetrics = getDailyAccountMetrics(acc, latestDate, yesterdayDayIdx);
    const yesterdayRevenue = yesterdayMetrics.revenue;
    const yesterdayVideoViews = yesterdayMetrics.videoViews;

    let recent7DaysRevSum = 0;
    recent7Dates.forEach((date) => {
      const dayIdx = ALL_DATES.indexOf(date);
      recent7DaysRevSum += getDailyAccountMetrics(acc, date, dayIdx).revenue;
    });
    const recent7DayAvgRevenue = Math.round((recent7DaysRevSum / 7) * 100) / 100;

    const changeVsRecentAvgPct = recent7DayAvgRevenue > 0
      ? Math.round(((yesterdayRevenue - recent7DayAvgRevenue) / recent7DayAvgRevenue) * 1000) / 10
      : null;

    // Special trend points when 'yesterday' is selected:
    // Display recent 7 days with yesterday highlighted!
    const trendPointsToDisplay = timeRange === 'yesterday'
      ? recent7Dates.map((date) => {
          const dayIdx = ALL_DATES.indexOf(date);
          const m = getDailyAccountMetrics(acc, date, dayIdx);
          return {
            date,
            dayLabel: date.slice(5),
            revenue: m.revenue,
            videoViews: m.videoViews,
            isYesterday: date === latestDate,
          };
        })
      : dailyTrendPoints;

    // C. Dynamic Drama Performances for Selected Period
    // Publish Count: number of platform promotion videos published in the selected date range
    const daysCount = activeDates.length;
    const dramaPerformancesInPeriod = acc.dramasMeta.map((dm) => {
      // Calculate publish count strictly in this period
      let pubCount = Math.max(1, Math.round(dm.basePubPerDay * daysCount));
      if (timeRange === 'yesterday') {
        pubCount = dm.basePubPerDay >= 0.8 ? 1 : (acc.id === 'acc-1' && dm.dramaId === 'd-1' ? 2 : (Math.random() > 0.5 ? 1 : 0));
        if (pubCount === 0 && dm.shareWeight > 0.5) pubCount = 1;
      }

      if (dm.isAttributable) {
        const dramaTotalRev = Math.round(periodRevenue * dm.shareWeight * 100) / 100;
        const avgPerVideo = pubCount > 0 ? Math.round((dramaTotalRev / pubCount) * 10) / 10 : 0;
        const vViews = acc.hasQingningVideoData ? Math.round(periodVideoViews * dm.shareWeight) : undefined;
        const dViews = acc.hasQingningVideoData ? Math.round(periodDramaViews * dm.shareWeight) : undefined;

        return {
          dramaId: dm.dramaId,
          dramaName: dm.dramaName,
          publishCount: pubCount,
          totalRevenue: dramaTotalRev,
          avgRevenuePerVideo: avgPerVideo,
          videoViews: vViews,
          dramaViews: dViews,
          isAttributable: true,
        };
      } else {
        // Unattributable revenue (e.g. Peanut / Huasheng)
        return {
          dramaId: dm.dramaId,
          dramaName: dm.dramaName,
          publishCount: pubCount,
          totalRevenue: undefined,
          avgRevenuePerVideo: undefined,
          videoViews: undefined,
          dramaViews: undefined,
          isAttributable: false,
        };
      }
    }).filter((dp) => dp.publishCount > 0 || (dp.totalRevenue && dp.totalRevenue > 0));

    return {
      id: acc.id,
      name: acc.name,
      theater: acc.theaterName,
      theaterKey: acc.theaterKey,
      hasQingningVideoData: acc.hasQingningVideoData,
      periodRevenue,
      dailyAverageRevenue,
      recent7DayAvgRevenue,
      periodVideoViews: acc.hasQingningVideoData ? periodVideoViews : undefined,
      periodDramaViews: acc.hasQingningVideoData ? periodDramaViews : undefined,
      yesterdayRevenue,
      yesterdayVideoViews,
      changeVsRecentAvgPct,
      sevenDaysRevenue: recent7DaysRevSum,
      sevenDaysRevenueTrend: recent7Dates.map((d) => getDailyAccountMetrics(acc, d, ALL_DATES.indexOf(d)).revenue),
      thirtyDaysRevenue: ALL_DATES.reduce((sum, d) => sum + getDailyAccountMetrics(acc, d, ALL_DATES.indexOf(d)).revenue, 0),
      recentMainDrama: acc.recentMainDrama,
      defaultLocation: acc.defaultLocation,
      sevenDaysVideoViews: acc.hasQingningVideoData ? periodVideoViews : undefined,
      sevenDaysDramaViews: acc.hasQingningVideoData ? periodDramaViews : undefined,
      dailyTrend: trendPointsToDisplay.map((tp) => ({
        date: tp.date,
        revenue: tp.revenue,
        videoViews: tp.videoViews,
      })),
      dailyTrendPoints: trendPointsToDisplay,
      dramaPerformances: dramaPerformancesInPeriod.map((dp) => ({
        dramaId: dp.dramaId,
        dramaName: dp.dramaName,
        publishCount: dp.publishCount,
        totalRevenue: dp.totalRevenue ?? 0,
        avgRevenuePerVideo: dp.avgRevenuePerVideo ?? 0,
        videoViews: dp.videoViews,
        dramaViews: dp.dramaViews,
      })),
      dramaPerformancesInPeriod,
      // Location performance is HISTORICAL CUMULATIVE (stays across all filters)
      locationPerformances: acc.historicalLocations,
    };
  });

  return {
    accounts: calculatedAccounts,
    totalAccountsInScope: calculatedAccounts.length,
    theaterFilterName: theaterNamesMap[selectedTheater] || '全部剧场',
  };
}
