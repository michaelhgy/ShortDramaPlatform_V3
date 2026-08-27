// Pure deterministic calculation engine for Data Analysis > Dramas (剧集)
import {
  TimeRangeFilter,
  TheaterFilter,
} from '../analyticsTypes';
import { MOCK_LOCATIONS_POOL } from '../analyticsMockData';

export interface CalculatedDramaLocationPerformance {
  locationId: string;
  fullAddress: string;
  usedCount: number;
  totalRevenue: number;
  videoViews?: number;
  dramaViews?: number;
  lastUsedDate: string;
}

export interface CalculatedDramaAccountDifference {
  accountId: string;
  accountName: string;
  publishCount: number;
  totalRevenue: number;
  avgRevenuePerVideo: number;
  videoViews?: number;
  dramaViews?: number;
}

export interface CalculatedDramaVideoVariance {
  publishedVideoCount: number;
  bestSingleVideoRevenue: number;
  avgSingleVideoRevenue: number;
  medianSingleVideoRevenue: number;
  zeroRevenueCount: number; // 零收益视频数量
  bestVideoDisplay: {
    isLinked: boolean;
    displayName: string;
    videoId: string;
    firstObservedDate: string;
    accountName: string;
    candidateBatch?: string;
    linkedInternalClipName?: string;
  };
  hasVideoLevelData: boolean;
}

export interface CalculatedDramaItem {
  id: string;
  name: string;
  theaterKey: 'qingning' | 'jiuzhou' | 'dianzhong' | 'fanqie' | 'huasheng';
  theaterName: string;
  hasQingningVideoData: boolean;
  isAttributable: boolean; // 花生剧场等无法准确归因至单剧时为 false

  // 1. 历史累计数据 (不受顶部时间筛选影响)
  historicalTotalAccounts: number;
  historicalTotalRevenue: number;

  // 2. 当前周期摘要数据 (随 Global Filter 联动)
  periodRevenue: number; // 当前周期可归因收益 (若不可归因则为 0)
  periodAccountsCount: number; // 当前周期发布账号数 (实际去重)
  periodVideoViews?: number; // 青柠剧场有，其它为 undefined
  periodDramaViews?: number;

  // 3. 平台视频表现差异 (按视频ID在周期内聚合)
  videoVariance: CalculatedDramaVideoVariance;

  // 4. 不同账号表现 (所选周期内)
  accountDifferences: CalculatedDramaAccountDifference[];

  // 5. 虚拟定位历史表现 (历史累计，不受时间筛选影响)
  locationPerformances: CalculatedDramaLocationPerformance[];
}

// -----------------------------------------------------------------------------
// Raw Seed Video Item for Platform Video Aggregation
// -----------------------------------------------------------------------------
interface RawPlatformVideoDailyEntry {
  videoId: string;
  date: string; // YYYY-MM-DD
  dramaId: string;
  accountId: string;
  accountName: string;
  firstObservedDate: string;
  candidateBatch: string;
  isLinked: boolean;
  linkedInternalClipName?: string;
  revenue: number;
  videoViews?: number;
  dramaViews?: number;
}

// -----------------------------------------------------------------------------
// Raw Drama Definition Metadata (22 Dramas across 5 Theaters)
// -----------------------------------------------------------------------------
interface RawDramaDef {
  id: string;
  name: string;
  theaterKey: 'qingning' | 'jiuzhou' | 'dianzhong' | 'fanqie' | 'huasheng';
  theaterName: string;
  hasQingningVideoData: boolean;
  isAttributable: boolean;
  baseDailyRevenue: number;
  historicalTotalAccounts: number;
  historicalTotalRevenue: number;
  accounts: {
    id: string;
    name: string;
    weight: number;
    dailyPubRate: number; // 平均每日发布该剧视频数
  }[];
  locations: CalculatedDramaLocationPerformance[];
}

const RAW_DRAMAS: RawDramaDef[] = [
  // =========================================================================
  // 1. 青柠剧场 (6 Dramas, full video-level data)
  // =========================================================================
  {
    id: 'd-1',
    name: '风雪草原苍狼少女',
    theaterKey: 'qingning',
    theaterName: '青柠剧场',
    hasQingningVideoData: true,
    isAttributable: true,
    baseDailyRevenue: 850,
    historicalTotalAccounts: 6,
    historicalTotalRevenue: 28600.0,
    accounts: [
      { id: 'acc-1', name: '短剧黄鸡版', weight: 0.42, dailyPubRate: 1.1 },
      { id: 'acc-4', name: '格格芝LE', weight: 0.26, dailyPubRate: 0.9 },
      { id: 'acc-2', name: '鸿记水产行', weight: 0.12, dailyPubRate: 0.5 },
      { id: 'acc-11', name: '爆款微剧社-06', weight: 0.09, dailyPubRate: 0.4 },
      { id: 'acc-13', name: '独角兽短剧-09', weight: 0.06, dailyPubRate: 0.3 },
      { id: 'acc-15', name: '剧迷老陈', weight: 0.05, dailyPubRate: 0.2 },
    ],
    locations: [
      { locationId: 'loc-1', fullAddress: '广东省广州市天河区体育西路103号维多利广场B座', usedCount: 14, totalRevenue: 13500.0, videoViews: 980000, dramaViews: 1420000, lastUsedDate: '2026-08-23' },
      { locationId: 'loc-7', fullAddress: '上海市静安区南京西路1266号恒隆广场二期', usedCount: 10, totalRevenue: 8920.0, videoViews: 650000, dramaViews: 920000, lastUsedDate: '2026-08-22' },
      { locationId: 'loc-3', fullAddress: '浙江省杭州市余杭区文一西路969号未来科技城5号楼', usedCount: 6, totalRevenue: 3860.0, videoViews: 280000, dramaViews: 390000, lastUsedDate: '2026-08-20' },
      { locationId: 'loc-2', fullAddress: '广东省深圳市南山区粤海街道高新南一道科技园08栋', usedCount: 4, totalRevenue: 2320.0, videoViews: 170000, dramaViews: 240000, lastUsedDate: '2026-08-18' },
    ],
  },
  {
    id: 'd-2',
    name: '辣厨回乡鲜椒越香店越旺',
    theaterKey: 'qingning',
    theaterName: '青柠剧场',
    hasQingningVideoData: true,
    isAttributable: true,
    baseDailyRevenue: 570,
    historicalTotalAccounts: 5,
    historicalTotalRevenue: 19400.0,
    accounts: [
      { id: 'acc-3', name: '冷脸萌萌1701', weight: 0.45, dailyPubRate: 1.0 },
      { id: 'acc-1', name: '短剧黄鸡版', weight: 0.28, dailyPubRate: 0.7 },
      { id: 'acc-4', name: '格格芝LE', weight: 0.15, dailyPubRate: 0.5 },
      { id: 'acc-11', name: '爆款微剧社-06', weight: 0.08, dailyPubRate: 0.3 },
      { id: 'acc-13', name: '独角兽短剧-09', weight: 0.04, dailyPubRate: 0.2 },
    ],
    locations: [
      { locationId: 'loc-3', fullAddress: '浙江省杭州市余杭区文一西路969号未来科技城5号楼', usedCount: 12, totalRevenue: 9800.0, videoViews: 720000, dramaViews: 1040000, lastUsedDate: '2026-08-23' },
      { locationId: 'loc-1', fullAddress: '广东省广州市天河区体育西路103号维多利广场B座', usedCount: 8, totalRevenue: 6200.0, videoViews: 460000, dramaViews: 650000, lastUsedDate: '2026-08-21' },
      { locationId: 'loc-5', fullAddress: '江苏省苏州市工业园区星湖街328号创意产业园A4栋', usedCount: 5, totalRevenue: 3400.0, videoViews: 250000, dramaViews: 360000, lastUsedDate: '2026-08-19' },
    ],
  },
  {
    id: 'd-3',
    name: '坠海逢生我率万鲨踏浪归来',
    theaterKey: 'qingning',
    theaterName: '青柠剧场',
    hasQingningVideoData: true,
    isAttributable: true,
    baseDailyRevenue: 450,
    historicalTotalAccounts: 4,
    historicalTotalRevenue: 15200.0,
    accounts: [
      { id: 'acc-4', name: '格格芝LE', weight: 0.48, dailyPubRate: 0.9 },
      { id: 'acc-1', name: '短剧黄鸡版', weight: 0.30, dailyPubRate: 0.6 },
      { id: 'acc-3', name: '冷脸萌萌1701', weight: 0.14, dailyPubRate: 0.4 },
      { id: 'acc-15', name: '剧迷老陈', weight: 0.08, dailyPubRate: 0.2 },
    ],
    locations: [
      { locationId: 'loc-7', fullAddress: '上海市静安区南京西路1266号恒隆广场二期', usedCount: 11, totalRevenue: 7800.0, videoViews: 580000, dramaViews: 790000, lastUsedDate: '2026-08-23' },
      { locationId: 'loc-1', fullAddress: '广东省广州市天河区体育西路103号维多利广场B座', usedCount: 7, totalRevenue: 4900.0, videoViews: 360000, dramaViews: 500000, lastUsedDate: '2026-08-20' },
      { locationId: 'loc-2', fullAddress: '广东省深圳市南山区粤海街道高新南一道科技园08栋', usedCount: 4, totalRevenue: 2500.0, videoViews: 190000, dramaViews: 260000, lastUsedDate: '2026-08-17' },
    ],
  },
  {
    id: 'd-4',
    name: '我用十元盒饭惊艳全城',
    theaterKey: 'qingning',
    theaterName: '青柠剧场',
    hasQingningVideoData: true,
    isAttributable: true,
    baseDailyRevenue: 380,
    historicalTotalAccounts: 4,
    historicalTotalRevenue: 12900.0,
    accounts: [
      { id: 'acc-2', name: '鸿记水产行', weight: 0.52, dailyPubRate: 0.8 },
      { id: 'acc-13', name: '独角兽短剧-09', weight: 0.28, dailyPubRate: 0.5 },
      { id: 'acc-11', name: '爆款微剧社-06', weight: 0.12, dailyPubRate: 0.3 },
      { id: 'acc-15', name: '剧迷老陈', weight: 0.08, dailyPubRate: 0.2 },
    ],
    locations: [
      { locationId: 'loc-2', fullAddress: '广东省深圳市南山区粤海街道高新南一道科技园08栋', usedCount: 9, totalRevenue: 6800.0, videoViews: 510000, dramaViews: 690000, lastUsedDate: '2026-08-23' },
      { locationId: 'loc-17', fullAddress: '陕西省西安市雁塔区高新一路创新大厦12层', usedCount: 6, totalRevenue: 4100.0, videoViews: 310000, dramaViews: 420000, lastUsedDate: '2026-08-21' },
      { locationId: 'loc-12', fullAddress: '湖北省武汉市洪山区关山大道光谷软件园F4栋创新楼', usedCount: 3, totalRevenue: 2000.0, videoViews: 150000, dramaViews: 200000, lastUsedDate: '2026-08-16' },
    ],
  },
  {
    id: 'd-5',
    name: '惨遭同行背叛百年野猪认我为王',
    theaterKey: 'qingning',
    theaterName: '青柠剧场',
    hasQingningVideoData: true,
    isAttributable: true,
    baseDailyRevenue: 320,
    historicalTotalAccounts: 3,
    historicalTotalRevenue: 10800.0,
    accounts: [
      { id: 'acc-2', name: '鸿记水产行', weight: 0.65, dailyPubRate: 0.9 },
      { id: 'acc-15', name: '剧迷老陈', weight: 0.25, dailyPubRate: 0.4 },
      { id: 'acc-1', name: '短剧黄鸡版', weight: 0.10, dailyPubRate: 0.2 },
    ],
    locations: [
      { locationId: 'loc-2', fullAddress: '广东省深圳市南山区粤海街道高新南一道科技园08栋', usedCount: 10, totalRevenue: 7200.0, videoViews: 540000, dramaViews: 710000, lastUsedDate: '2026-08-23' },
      { locationId: 'loc-20', fullAddress: '辽宁省沈阳市和平区青年大街1号市府恒隆广场', usedCount: 5, totalRevenue: 2600.0, videoViews: 200000, dramaViews: 270000, lastUsedDate: '2026-08-20' },
      { locationId: 'loc-1', fullAddress: '广东省广州市天河区体育西路103号维多利广场B座', usedCount: 2, totalRevenue: 1000.0, videoViews: 75000, dramaViews: 100000, lastUsedDate: '2026-08-15' },
    ],
  },
  {
    id: 'd-6',
    name: '我在武侠世界抽卡成神',
    theaterKey: 'qingning',
    theaterName: '青柠剧场',
    hasQingningVideoData: true,
    isAttributable: true,
    baseDailyRevenue: 270,
    historicalTotalAccounts: 4,
    historicalTotalRevenue: 9100.0,
    accounts: [
      { id: 'acc-11', name: '爆款微剧社-06', weight: 0.48, dailyPubRate: 0.7 },
      { id: 'acc-3', name: '冷脸萌萌1701', weight: 0.28, dailyPubRate: 0.4 },
      { id: 'acc-13', name: '独角兽短剧-09', weight: 0.16, dailyPubRate: 0.3 },
      { id: 'acc-4', name: '格格芝LE', weight: 0.08, dailyPubRate: 0.2 },
    ],
    locations: [
      { locationId: 'loc-4', fullAddress: '浙江省宁波市鄞州区百丈东路99号国际金融会展中心', usedCount: 8, totalRevenue: 4900.0, videoViews: 370000, dramaViews: 490000, lastUsedDate: '2026-08-23' },
      { locationId: 'loc-3', fullAddress: '浙江省杭州市余杭区文一西路969号未来科技城5号楼', usedCount: 5, totalRevenue: 2800.0, videoViews: 210000, dramaViews: 280000, lastUsedDate: '2026-08-19' },
      { locationId: 'loc-17', fullAddress: '陕西省西安市雁塔区高新一路创新大厦12层', usedCount: 3, totalRevenue: 1400.0, videoViews: 105000, dramaViews: 140000, lastUsedDate: '2026-08-16' },
    ],
  },

  // =========================================================================
  // 2. 九州剧场 (4 Dramas, no video-level metrics)
  // =========================================================================
  {
    id: 'd-7',
    name: '九天狂尊',
    theaterKey: 'jiuzhou',
    theaterName: '九州剧场',
    hasQingningVideoData: false,
    isAttributable: true,
    baseDailyRevenue: 340,
    historicalTotalAccounts: 3,
    historicalTotalRevenue: 11500.0,
    accounts: [
      { id: 'acc-5', name: '曾经几何7906', weight: 0.58, dailyPubRate: 0.8 },
      { id: 'acc-6', name: '肯德基等你爱你', weight: 0.28, dailyPubRate: 0.5 },
      { id: 'acc-12', name: '一口爽剧-08', weight: 0.14, dailyPubRate: 0.3 },
    ],
    locations: [
      { locationId: 'loc-11', fullAddress: '四川省成都市武侯区天府三街199号新希望国际大厦', usedCount: 9, totalRevenue: 6800.0, lastUsedDate: '2026-08-23' },
      { locationId: 'loc-13', fullAddress: '湖南省长沙市岳麓区麓谷大道627号新材料产业园2栋', usedCount: 5, totalRevenue: 3200.0, lastUsedDate: '2026-08-20' },
      { locationId: 'loc-12', fullAddress: '湖北省武汉市洪山区关山大道光谷软件园F4栋创新楼', usedCount: 3, totalRevenue: 1500.0, lastUsedDate: '2026-08-17' },
    ],
  },
  {
    id: 'd-8',
    name: '重返巅峰2008',
    theaterKey: 'jiuzhou',
    theaterName: '九州剧场',
    hasQingningVideoData: false,
    isAttributable: true,
    baseDailyRevenue: 280,
    historicalTotalAccounts: 3,
    historicalTotalRevenue: 9500.0,
    accounts: [
      { id: 'acc-6', name: '肯德基等你爱你', weight: 0.55, dailyPubRate: 0.7 },
      { id: 'acc-5', name: '曾经几何7906', weight: 0.30, dailyPubRate: 0.4 },
      { id: 'acc-12', name: '一口爽剧-08', weight: 0.15, dailyPubRate: 0.3 },
    ],
    locations: [
      { locationId: 'loc-13', fullAddress: '湖南省长沙市岳麓区麓谷大道627号新材料产业园2栋', usedCount: 8, totalRevenue: 5400.0, lastUsedDate: '2026-08-23' },
      { locationId: 'loc-11', fullAddress: '四川省成都市武侯区天府三街199号新希望国际大厦', usedCount: 5, totalRevenue: 2900.0, lastUsedDate: '2026-08-21' },
      { locationId: 'loc-16', fullAddress: '重庆市渝中区解放碑民权路28号时代广场B栋', usedCount: 2, totalRevenue: 1200.0, lastUsedDate: '2026-08-16' },
    ],
  },
  {
    id: 'd-9',
    name: '逆天狂婿叶辰',
    theaterKey: 'jiuzhou',
    theaterName: '九州剧场',
    hasQingningVideoData: false,
    isAttributable: true,
    baseDailyRevenue: 190,
    historicalTotalAccounts: 2,
    historicalTotalRevenue: 6400.0,
    accounts: [
      { id: 'acc-5', name: '曾经几何7906', weight: 0.65, dailyPubRate: 0.5 },
      { id: 'acc-12', name: '一口爽剧-08', weight: 0.35, dailyPubRate: 0.3 },
    ],
    locations: [
      { locationId: 'loc-11', fullAddress: '四川省成都市武侯区天府三街199号新希望国际大厦', usedCount: 6, totalRevenue: 4200.0, lastUsedDate: '2026-08-22' },
      { locationId: 'loc-12', fullAddress: '湖北省武汉市洪山区关山大道光谷软件园F4栋创新楼', usedCount: 3, totalRevenue: 2200.0, lastUsedDate: '2026-08-18' },
    ],
  },
  {
    id: 'd-10',
    name: '大夏第一战神',
    theaterKey: 'jiuzhou',
    theaterName: '九州剧场',
    hasQingningVideoData: false,
    isAttributable: true,
    baseDailyRevenue: 130,
    historicalTotalAccounts: 2,
    historicalTotalRevenue: 4400.0,
    accounts: [
      { id: 'acc-6', name: '肯德基等你爱你', weight: 0.70, dailyPubRate: 0.4 },
      { id: 'acc-12', name: '一口爽剧-08', weight: 0.30, dailyPubRate: 0.2 },
    ],
    locations: [
      { locationId: 'loc-13', fullAddress: '湖南省长沙市岳麓区麓谷大道627号新材料产业园2栋', usedCount: 5, totalRevenue: 3100.0, lastUsedDate: '2026-08-20' },
      { locationId: 'loc-16', fullAddress: '重庆市渝中区解放碑民权路28号时代广场B栋', usedCount: 2, totalRevenue: 1300.0, lastUsedDate: '2026-08-15' },
    ],
  },

  // =========================================================================
  // 3. 点众微剧 (4 Dramas, no video-level metrics)
  // =========================================================================
  {
    id: 'd-11',
    name: '顾总，太太又惊艳全球了',
    theaterKey: 'dianzhong',
    theaterName: '点众微剧',
    hasQingningVideoData: false,
    isAttributable: true,
    baseDailyRevenue: 260,
    historicalTotalAccounts: 2,
    historicalTotalRevenue: 8800.0,
    accounts: [
      { id: 'acc-7', name: '热播短剧社-01', weight: 0.58, dailyPubRate: 0.7 },
      { id: 'acc-8', name: '深夜追剧馆02', weight: 0.42, dailyPubRate: 0.5 },
    ],
    locations: [
      { locationId: 'loc-9', fullAddress: '北京市朝阳区建国门外大街1号国贸大厦B座', usedCount: 8, totalRevenue: 5200.0, lastUsedDate: '2026-08-23' },
      { locationId: 'loc-5', fullAddress: '江苏省苏州市工业园区星湖街328号创意产业园A4栋', usedCount: 5, totalRevenue: 3600.0, lastUsedDate: '2026-08-21' },
    ],
  },
  {
    id: 'd-12',
    name: '我在八零年代当首富',
    theaterKey: 'dianzhong',
    theaterName: '点众微剧',
    hasQingningVideoData: false,
    isAttributable: true,
    baseDailyRevenue: 180,
    historicalTotalAccounts: 2,
    historicalTotalRevenue: 6100.0,
    accounts: [
      { id: 'acc-8', name: '深夜追剧馆02', weight: 0.65, dailyPubRate: 0.5 },
      { id: 'acc-14', name: '星芒短剧工作室', weight: 0.35, dailyPubRate: 0.3 },
    ],
    locations: [
      { locationId: 'loc-5', fullAddress: '江苏省苏州市工业园区星湖街328号创意产业园A4栋', usedCount: 6, totalRevenue: 4000.0, lastUsedDate: '2026-08-22' },
      { locationId: 'loc-19', fullAddress: '安徽省合肥市蜀山区潜山路111号华润大厦东塔', usedCount: 3, totalRevenue: 2100.0, lastUsedDate: '2026-08-17' },
    ],
  },
  {
    id: 'd-13',
    name: '绝世神医闯花都',
    theaterKey: 'dianzhong',
    theaterName: '点众微剧',
    hasQingningVideoData: false,
    isAttributable: true,
    baseDailyRevenue: 140,
    historicalTotalAccounts: 2,
    historicalTotalRevenue: 4700.0,
    accounts: [
      { id: 'acc-7', name: '热播短剧社-01', weight: 0.60, dailyPubRate: 0.4 },
      { id: 'acc-14', name: '星芒短剧工作室', weight: 0.40, dailyPubRate: 0.3 },
    ],
    locations: [
      { locationId: 'loc-9', fullAddress: '北京市朝阳区建国门外大街1号国贸大厦B座', usedCount: 5, totalRevenue: 2900.0, lastUsedDate: '2026-08-21' },
      { locationId: 'loc-19', fullAddress: '安徽省合肥市蜀山区潜山路111号华润大厦东塔', usedCount: 3, totalRevenue: 1800.0, lastUsedDate: '2026-08-16' },
    ],
  },
  {
    id: 'd-14',
    name: '错嫁豪门傲娇总裁宠上天',
    theaterKey: 'dianzhong',
    theaterName: '点众微剧',
    hasQingningVideoData: false,
    isAttributable: true,
    baseDailyRevenue: 110,
    historicalTotalAccounts: 2,
    historicalTotalRevenue: 3700.0,
    accounts: [
      { id: 'acc-8', name: '深夜追剧馆02', weight: 0.60, dailyPubRate: 0.3 },
      { id: 'acc-7', name: '热播短剧社-01', weight: 0.40, dailyPubRate: 0.2 },
    ],
    locations: [
      { locationId: 'loc-5', fullAddress: '江苏省苏州市工业园区星湖街328号创意产业园A4栋', usedCount: 4, totalRevenue: 2300.0, lastUsedDate: '2026-08-19' },
      { locationId: 'loc-9', fullAddress: '北京市朝阳区建国门外大街1号国贸大厦B座', usedCount: 2, totalRevenue: 1400.0, lastUsedDate: '2026-08-14' },
    ],
  },

  // =========================================================================
  // 4. 番茄剧场 (4 Dramas, no video-level metrics)
  // =========================================================================
  {
    id: 'd-15',
    name: '绝世龙帅狂飙都市',
    theaterKey: 'fanqie',
    theaterName: '番茄剧场',
    hasQingningVideoData: false,
    isAttributable: true,
    baseDailyRevenue: 160,
    historicalTotalAccounts: 2,
    historicalTotalRevenue: 5400.0,
    accounts: [
      { id: 'acc-9', name: '逆袭短剧王', weight: 0.65, dailyPubRate: 0.5 },
      { id: 'acc-16', name: '番茄新风-04', weight: 0.35, dailyPubRate: 0.3 },
    ],
    locations: [
      { locationId: 'loc-16', fullAddress: '重庆市渝中区解放碑民权路28号时代广场B栋', usedCount: 6, totalRevenue: 3600.0, lastUsedDate: '2026-08-23' },
      { locationId: 'loc-11', fullAddress: '四川省成都市武侯区天府三街199号新希望国际大厦', usedCount: 3, totalRevenue: 1800.0, lastUsedDate: '2026-08-18' },
    ],
  },
  {
    id: 'd-16',
    name: '神级奶爸在都市',
    theaterKey: 'fanqie',
    theaterName: '番茄剧场',
    hasQingningVideoData: false,
    isAttributable: true,
    baseDailyRevenue: 120,
    historicalTotalAccounts: 2,
    historicalTotalRevenue: 4000.0,
    accounts: [
      { id: 'acc-16', name: '番茄新风-04', weight: 0.60, dailyPubRate: 0.4 },
      { id: 'acc-9', name: '逆袭短剧王', weight: 0.40, dailyPubRate: 0.3 },
    ],
    locations: [
      { locationId: 'loc-16', fullAddress: '重庆市渝中区解放碑民权路28号时代广场B栋', usedCount: 5, totalRevenue: 2500.0, lastUsedDate: '2026-08-22' },
      { locationId: 'loc-13', fullAddress: '湖南省长沙市岳麓区麓谷大道627号新材料产业园2栋', usedCount: 3, totalRevenue: 1500.0, lastUsedDate: '2026-08-17' },
    ],
  },
  {
    id: 'd-17',
    name: '逍遥天王',
    theaterKey: 'fanqie',
    theaterName: '番茄剧场',
    hasQingningVideoData: false,
    isAttributable: true,
    baseDailyRevenue: 90,
    historicalTotalAccounts: 2,
    historicalTotalRevenue: 3000.0,
    accounts: [
      { id: 'acc-9', name: '逆袭短剧王', weight: 0.60, dailyPubRate: 0.3 },
      { id: 'acc-16', name: '番茄新风-04', weight: 0.40, dailyPubRate: 0.2 },
    ],
    locations: [
      { locationId: 'loc-16', fullAddress: '重庆市渝中区解放碑民权路28号时代广场B栋', usedCount: 4, totalRevenue: 1900.0, lastUsedDate: '2026-08-20' },
      { locationId: 'loc-11', fullAddress: '四川省成都市武侯区天府三街199号新希望国际大厦', usedCount: 2, totalRevenue: 1100.0, lastUsedDate: '2026-08-15' },
    ],
  },
  {
    id: 'd-18',
    name: '千金归来倾天下',
    theaterKey: 'fanqie',
    theaterName: '番茄剧场',
    hasQingningVideoData: false,
    isAttributable: true,
    baseDailyRevenue: 60,
    historicalTotalAccounts: 2,
    historicalTotalRevenue: 2000.0,
    accounts: [
      { id: 'acc-16', name: '番茄新风-04', weight: 0.60, dailyPubRate: 0.2 },
      { id: 'acc-9', name: '逆袭短剧王', weight: 0.40, dailyPubRate: 0.2 },
    ],
    locations: [
      { locationId: 'loc-16', fullAddress: '重庆市渝中区解放碑民权路28号时代广场B栋', usedCount: 3, totalRevenue: 1200.0, lastUsedDate: '2026-08-19' },
      { locationId: 'loc-13', fullAddress: '湖南省长沙市岳麓区麓谷大道627号新材料产业园2栋', usedCount: 2, totalRevenue: 800.0, lastUsedDate: '2026-08-14' },
    ],
  },

  // =========================================================================
  // 5. 花生剧场 (4 Dramas, unattributable channel, estimated)
  // =========================================================================
  {
    id: 'd-19',
    name: '乡村小仙医',
    theaterKey: 'huasheng',
    theaterName: '花生剧场',
    hasQingningVideoData: false,
    isAttributable: false, // 无法准确归因至单剧
    baseDailyRevenue: 0,
    historicalTotalAccounts: 1,
    historicalTotalRevenue: 0,
    accounts: [
      { id: 'acc-10', name: '甜宠小剧场-03', weight: 1.0, dailyPubRate: 0.3 },
    ],
    locations: [
      { locationId: 'loc-10', fullAddress: '北京市海淀区中关村南大街1号海龙数码大厦', usedCount: 4, totalRevenue: 0, lastUsedDate: '2026-08-20' },
    ],
  },
  {
    id: 'd-20',
    name: '黄金瞳之鉴宝神王',
    theaterKey: 'huasheng',
    theaterName: '花生剧场',
    hasQingningVideoData: false,
    isAttributable: false,
    baseDailyRevenue: 0,
    historicalTotalAccounts: 1,
    historicalTotalRevenue: 0,
    accounts: [
      { id: 'acc-10', name: '甜宠小剧场-03', weight: 1.0, dailyPubRate: 0.3 },
    ],
    locations: [
      { locationId: 'loc-10', fullAddress: '北京市海淀区中关村南大街1号海龙数码大厦', usedCount: 3, totalRevenue: 0, lastUsedDate: '2026-08-19' },
    ],
  },
  {
    id: 'd-21',
    name: '女总裁的极品高手',
    theaterKey: 'huasheng',
    theaterName: '花生剧场',
    hasQingningVideoData: false,
    isAttributable: false,
    baseDailyRevenue: 0,
    historicalTotalAccounts: 1,
    historicalTotalRevenue: 0,
    accounts: [
      { id: 'acc-10', name: '甜宠小剧场-03', weight: 1.0, dailyPubRate: 0.2 },
    ],
    locations: [
      { locationId: 'loc-10', fullAddress: '北京市海淀区中关村南大街1号海龙数码大厦', usedCount: 2, totalRevenue: 0, lastUsedDate: '2026-08-18' },
    ],
  },
  {
    id: 'd-22',
    name: '隐世龙皇',
    theaterKey: 'huasheng',
    theaterName: '花生剧场',
    hasQingningVideoData: false,
    isAttributable: false,
    baseDailyRevenue: 0,
    historicalTotalAccounts: 1,
    historicalTotalRevenue: 0,
    accounts: [
      { id: 'acc-10', name: '甜宠小剧场-03', weight: 1.0, dailyPubRate: 0.2 },
    ],
    locations: [
      { locationId: 'loc-10', fullAddress: '北京市海淀区中关村南大街1号海龙数码大厦', usedCount: 2, totalRevenue: 0, lastUsedDate: '2026-08-16' },
    ],
  },
];

// -----------------------------------------------------------------------------
// Generate 30-Day Platform Video Daily Dataset (2026-07-25 to 2026-08-23)
// -----------------------------------------------------------------------------
const RAW_PLATFORM_VIDEO_DAILY_ENTRIES: RawPlatformVideoDailyEntry[] = [];

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

  let videoSeq = 1000;

  RAW_DRAMAS.forEach((drama) => {
    if (!drama.isAttributable) return;

    drama.accounts.forEach((acc) => {
      // Create 4-7 persistent platform videos for this drama × account pair
      const numVideos = Math.floor(4 + acc.weight * 6); // 4 to 10 videos
      for (let v = 0; v < numVideos; v++) {
        videoSeq++;
        const videoId = `vid-plat-${drama.id}-${acc.id}-${videoSeq}`;
        const creationDayOffset = Math.floor(Math.random() * 20); // created between day 0 and day 20
        const firstObservedDate = dates[creationDayOffset];
        const monthDayStr = firstObservedDate.slice(5); // e.g. 08-12
        const candidateBatch = `${monthDayStr} · 批次${(v % 3) + 1}`;

        // Artificial linking: roughly 35% of videos are manually linked to internal clips
        const isLinked = (videoSeq % 3 === 0);
        const clipNum = String((v % 12) + 1).padStart(2, '0');
        const linkedInternalClipName = isLinked ? `${drama.name}-${clipNum}` : undefined;

        // Base revenue potential for this video: some high breakout, some moderate, some 0!
        let revProfile: 'breakout' | 'normal' | 'zero' = 'normal';
        const rand = Math.random();
        if (rand < 0.15 && v === 0) revProfile = 'breakout';
        else if (rand < 0.38) revProfile = 'zero'; // ~30% zero revenue videos

        // Generate daily data from creation date to 2026-08-23
        for (let dIdx = creationDayOffset; dIdx < dates.length; dIdx++) {
          const date = dates[dIdx];
          let dailyRev = 0;
          let dailyViews: number | undefined = undefined;
          let dailyDramaViews: number | undefined = undefined;

          if (revProfile === 'breakout') {
            dailyRev = Number((drama.baseDailyRevenue * acc.weight * (0.35 + Math.random() * 0.45)).toFixed(1));
          } else if (revProfile === 'normal') {
            dailyRev = Number((drama.baseDailyRevenue * acc.weight * (0.04 + Math.random() * 0.12)).toFixed(1));
          } else {
            dailyRev = 0;
          }

          if (drama.hasQingningVideoData) {
            if (revProfile === 'zero') {
              dailyViews = Math.floor(300 + Math.random() * 1200);
              dailyDramaViews = Math.floor(dailyViews * 0.3);
            } else {
              const rpm = revProfile === 'breakout' ? (9 + Math.random() * 5) : (4 + Math.random() * 4);
              dailyViews = Math.max(800, Math.floor((dailyRev / rpm) * 1000));
              dailyDramaViews = Math.floor(dailyViews * (1.1 + Math.random() * 0.6));
            }
          }

          RAW_PLATFORM_VIDEO_DAILY_ENTRIES.push({
            videoId,
            date,
            dramaId: drama.id,
            accountId: acc.id,
            accountName: acc.name,
            firstObservedDate,
            candidateBatch,
            isLinked,
            linkedInternalClipName,
            revenue: dailyRev,
            videoViews: dailyViews,
            dramaViews: dailyDramaViews,
          });
        }
      }
    });
  });
})();

// -----------------------------------------------------------------------------
// Calculate Drama Analytics based on TimeRange and TheaterFilter
// -----------------------------------------------------------------------------
export function calculateDramasAnalytics(
  timeRange: TimeRangeFilter,
  selectedTheater: TheaterFilter,
  customStart?: string,
  customEnd?: string
): CalculatedDramaItem[] {
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
    // 2026-08-01 to 2026-08-23 (23 days)
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

  // 2. Filter raw dramas by theater
  const filteredRawDramas = RAW_DRAMAS.filter((d) => {
    if (selectedTheater === 'all') return true;
    if (selectedTheater === 'qingning' && d.theaterKey === 'qingning') return true;
    if (selectedTheater === 'jiuzhou' && d.theaterKey === 'jiuzhou') return true;
    if (selectedTheater === 'dianzhong' && d.theaterKey === 'dianzhong') return true;
    if (selectedTheater === 'fanqie' && d.theaterKey === 'fanqie') return true;
    if (selectedTheater === 'huasheng' && d.theaterKey === 'huasheng') return true;
    return false;
  });

  // 3. Process each drama
  return filteredRawDramas.map((drama) => {
    if (!drama.isAttributable) {
      // Unattributable drama (e.g. Peanut/Huasheng)
      return {
        id: drama.id,
        name: drama.name,
        theaterKey: drama.theaterKey,
        theaterName: drama.theaterName,
        hasQingningVideoData: false,
        isAttributable: false,
        historicalTotalAccounts: drama.historicalTotalAccounts,
        historicalTotalRevenue: 0,
        periodRevenue: 0,
        periodAccountsCount: 0,
        videoVariance: {
          publishedVideoCount: 0,
          bestSingleVideoRevenue: 0,
          avgSingleVideoRevenue: 0,
          medianSingleVideoRevenue: 0,
          zeroRevenueCount: 0,
          bestVideoDisplay: {
            isLinked: false,
            displayName: '暂无关联成片',
            videoId: '—',
            firstObservedDate: '—',
            accountName: '—',
          },
          hasVideoLevelData: false,
        },
        accountDifferences: [],
        locationPerformances: drama.locations,
      };
    }

    // Filter raw daily entries for this drama within the active period
    const dramaEntriesInPeriod = RAW_PLATFORM_VIDEO_DAILY_ENTRIES.filter(
      (e) => e.dramaId === drama.id && targetDateSet.has(e.date)
    );

    // Group by videoId (to get ONE platform video entity per period)
    const videoMap = new Map<
      string,
      {
        videoId: string;
        accountId: string;
        accountName: string;
        firstObservedDate: string;
        candidateBatch: string;
        isLinked: boolean;
        linkedInternalClipName?: string;
        totalRevenue: number;
        totalVideoViews: number;
        totalDramaViews: number;
        observedDays: number;
      }
    >();

    dramaEntriesInPeriod.forEach((entry) => {
      const existing = videoMap.get(entry.videoId);
      if (!existing) {
        videoMap.set(entry.videoId, {
          videoId: entry.videoId,
          accountId: entry.accountId,
          accountName: entry.accountName,
          firstObservedDate: entry.firstObservedDate,
          candidateBatch: entry.candidateBatch,
          isLinked: entry.isLinked,
          linkedInternalClipName: entry.linkedInternalClipName,
          totalRevenue: entry.revenue,
          totalVideoViews: entry.videoViews || 0,
          totalDramaViews: entry.dramaViews || 0,
          observedDays: 1,
        });
      } else {
        existing.totalRevenue += entry.revenue;
        if (entry.videoViews) existing.totalVideoViews += entry.videoViews;
        if (entry.dramaViews) existing.totalDramaViews += entry.dramaViews;
        existing.observedDays += 1;
      }
    });

    const aggregatedVideos = Array.from(videoMap.values());

    // Calculate Video Variance Metrics
    const publishedVideoCount = aggregatedVideos.length;
    const sortedByRev = [...aggregatedVideos].sort((a, b) => b.totalRevenue - a.totalRevenue);

    const bestVideo = sortedByRev[0];
    const bestSingleVideoRevenue = bestVideo ? Math.round(bestVideo.totalRevenue * 10) / 10 : 0;

    const totalRevAllVideos = aggregatedVideos.reduce((sum, v) => sum + v.totalRevenue, 0);
    const avgSingleVideoRevenue = publishedVideoCount > 0
      ? Math.round((totalRevAllVideos / publishedVideoCount) * 10) / 10
      : 0;

    // Median single video revenue
    let medianSingleVideoRevenue = 0;
    if (publishedVideoCount > 0) {
      const revsAsc = [...aggregatedVideos].map((v) => v.totalRevenue).sort((a, b) => a - b);
      const mid = Math.floor(revsAsc.length / 2);
      medianSingleVideoRevenue = revsAsc.length % 2 !== 0
        ? Math.round(revsAsc[mid] * 10) / 10
        : Math.round(((revsAsc[mid - 1] + revsAsc[mid]) / 2) * 10) / 10;
    }

    // Zero revenue videos count
    const zeroRevenueCount = aggregatedVideos.filter((v) => v.totalRevenue <= 0.05).length;

    // Format best video display according to rules:
    // If linked: show internal clip name (e.g. 风雪草原苍狼少女-08)
    // If unlinked: show date + account (e.g. 08-20 · 短剧黄鸡版)
    let bestVideoDisplay = {
      isLinked: false,
      displayName: '暂无视频数据',
      videoId: '—',
      firstObservedDate: '—',
      accountName: '—',
      candidateBatch: '—',
      linkedInternalClipName: undefined as string | undefined,
    };

    if (bestVideo) {
      const dateShort = bestVideo.firstObservedDate.slice(5); // e.g. 08-20
      const unlinkedName = `${dateShort} · ${bestVideo.accountName}`;
      bestVideoDisplay = {
        isLinked: bestVideo.isLinked,
        displayName: bestVideo.isLinked && bestVideo.linkedInternalClipName
          ? bestVideo.linkedInternalClipName
          : unlinkedName,
        videoId: bestVideo.videoId,
        firstObservedDate: bestVideo.firstObservedDate,
        accountName: bestVideo.accountName,
        candidateBatch: bestVideo.candidateBatch,
        linkedInternalClipName: bestVideo.linkedInternalClipName,
      };
    }

    // Calculate Account Differences for this period
    const accountGroupMap = new Map<
      string,
      {
        accountId: string;
        accountName: string;
        videoIds: Set<string>;
        totalRevenue: number;
        videoViews: number;
        dramaViews: number;
      }
    >();

    dramaEntriesInPeriod.forEach((entry) => {
      const existing = accountGroupMap.get(entry.accountId);
      if (!existing) {
        const vSet = new Set<string>();
        vSet.add(entry.videoId);
        accountGroupMap.set(entry.accountId, {
          accountId: entry.accountId,
          accountName: entry.accountName,
          videoIds: vSet,
          totalRevenue: entry.revenue,
          videoViews: entry.videoViews || 0,
          dramaViews: entry.dramaViews || 0,
        });
      } else {
        existing.videoIds.add(entry.videoId);
        existing.totalRevenue += entry.revenue;
        if (entry.videoViews) existing.videoViews += entry.videoViews;
        if (entry.dramaViews) existing.dramaViews += entry.dramaViews;
      }
    });

    const accountDifferences: CalculatedDramaAccountDifference[] = Array.from(accountGroupMap.values())
      .map((acc) => {
        const pubCount = acc.videoIds.size;
        const totalRevenue = Math.round(acc.totalRevenue * 10) / 10;
        const avgRevenuePerVideo = pubCount > 0 ? Math.round((totalRevenue / pubCount) * 10) / 10 : 0;
        return {
          accountId: acc.accountId,
          accountName: acc.accountName,
          publishCount: pubCount,
          totalRevenue,
          avgRevenuePerVideo,
          videoViews: drama.hasQingningVideoData ? acc.videoViews : undefined,
          dramaViews: drama.hasQingningVideoData ? acc.dramaViews : undefined,
        };
      })
      .sort((a, b) => b.totalRevenue - a.totalRevenue);

    // Period Summary Metrics
    const periodRevenue = Math.round(totalRevAllVideos * 10) / 10;
    const periodAccountsCount = accountGroupMap.size;
    let periodVideoViews: number | undefined = undefined;
    let periodDramaViews: number | undefined = undefined;

    if (drama.hasQingningVideoData) {
      periodVideoViews = aggregatedVideos.reduce((sum, v) => sum + v.totalVideoViews, 0);
      periodDramaViews = aggregatedVideos.reduce((sum, v) => sum + v.totalDramaViews, 0);
    }

    return {
      id: drama.id,
      name: drama.name,
      theaterKey: drama.theaterKey,
      theaterName: drama.theaterName,
      hasQingningVideoData: drama.hasQingningVideoData,
      isAttributable: true,
      historicalTotalAccounts: drama.historicalTotalAccounts,
      historicalTotalRevenue: drama.historicalTotalRevenue,
      periodRevenue,
      periodAccountsCount,
      periodVideoViews,
      periodDramaViews,
      videoVariance: {
        publishedVideoCount,
        bestSingleVideoRevenue,
        avgSingleVideoRevenue,
        medianSingleVideoRevenue,
        zeroRevenueCount,
        bestVideoDisplay,
        hasVideoLevelData: drama.hasQingningVideoData,
      },
      accountDifferences,
      locationPerformances: drama.locations,
    };
  });
}
