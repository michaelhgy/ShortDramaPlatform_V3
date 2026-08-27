import {
  DailyRevenueDataPoint,
  RevenueSummaryMetrics,
  ContributionItem,
  ChangeSignalItem,
  AccountAnalyticsItem,
  DramaAnalyticsItem,
  PlatformVideoItem,
  CombinationRecord,
  RevenueCollectionLog,
  DataCoverageInfo,
  AccountVirtualLocation
} from './analyticsTypes';

export const DATA_COVERAGE_CONFIG: DataCoverageInfo = {
  revenueTheatersCount: 5,
  totalTheatersCount: 5,
  videoDataTheaters: ['青柠剧场'],
  coverageDescription: '收益覆盖：全部 5 个剧场 · 视频级指标与承接强度：青柠剧场 (42% 业务量)',
};

// 1. VIRTUAL LOCATIONS POOL (24+ Structured real addresses)
export const MOCK_LOCATIONS_POOL: AccountVirtualLocation[] = [
  { province: '广东省', city: '广州市', district: '天河区', detail: '体育西路103号维多利广场B座', fullAddress: '广东省广州市天河区体育西路103号维多利广场B座', usedCount: 38, lastUsedDate: '2026-08-23' },
  { province: '广东省', city: '深圳市', district: '南山区', detail: '粤海街道高新南一道科技园08栋', fullAddress: '广东省深圳市南山区粤海街道高新南一道科技园08栋', usedCount: 29, lastUsedDate: '2026-08-23' },
  { province: '浙江省', city: '杭州市', district: '余杭区', detail: '文一西路969号未来科技城5号楼', fullAddress: '浙江省杭州市余杭区文一西路969号未来科技城5号楼', usedCount: 42, lastUsedDate: '2026-08-23' },
  { province: '浙江省', city: '宁波市', district: '鄞州区', detail: '百丈东路99号国际金融会展中心', fullAddress: '浙江省宁波市鄞州区百丈东路99号国际金融会展中心', usedCount: 16, lastUsedDate: '2026-08-22' },
  { province: '江苏省', city: '苏州市', district: '工业园区', detail: '星湖街328号创意产业园A4栋', fullAddress: '江苏省苏州市工业园区星湖街328号创意产业园A4栋', usedCount: 24, lastUsedDate: '2026-08-23' },
  { province: '江苏省', city: '南京市', district: '玄武区', detail: '中山东路18号国际贸易中心33层', fullAddress: '江苏省南京市玄武区中山东路18号国际贸易中心33层', usedCount: 19, lastUsedDate: '2026-08-21' },
  { province: '上海市', city: '上海市', district: '静安区', detail: '南京西路1266号恒隆广场二期', fullAddress: '上海市静安区南京西路1266号恒隆广场二期', usedCount: 35, lastUsedDate: '2026-08-23' },
  { province: '上海市', city: '上海市', district: '浦东新区', detail: '世纪大道100号环球金融中心', fullAddress: '上海市浦东新区世纪大道100号环球金融中心', usedCount: 28, lastUsedDate: '2026-08-22' },
  { province: '北京市', city: '北京市', district: '朝阳区', detail: '建国门外大街1号国贸大厦B座', fullAddress: '北京市朝阳区建国门外大街1号国贸大厦B座', usedCount: 31, lastUsedDate: '2026-08-23' },
  { province: '北京市', city: '北京市', district: '海淀区', detail: '中关村南大街1号海龙数码大厦', fullAddress: '北京市海淀区中关村南大街1号海龙数码大厦', usedCount: 22, lastUsedDate: '2026-08-20' },
  { province: '四川省', city: '成都市', district: '武侯区', detail: '天府三街199号新希望国际大厦', fullAddress: '四川省成都市武侯区天府三街199号新希望国际大厦', usedCount: 33, lastUsedDate: '2026-08-23' },
  { province: '湖北省', city: '武汉市', district: '洪山区', detail: '关山大道光谷软件园F4栋创新楼', fullAddress: '湖北省武汉市洪山区关山大道光谷软件园F4栋创新楼', usedCount: 18, lastUsedDate: '2026-08-21' },
  { province: '湖南省', city: '长沙市', district: '岳麓区', detail: '麓谷大道627号新材料产业园2栋', fullAddress: '湖南省长沙市岳麓区麓谷大道627号新材料产业园2栋', usedCount: 27, lastUsedDate: '2026-08-23' },
  { province: '山东省', city: '青岛市', district: '市南区', detail: '香港中路6号世贸中心A座', fullAddress: '山东省青岛市市南区香港中路6号世贸中心A座', usedCount: 14, lastUsedDate: '2026-08-19' },
  { province: '福建省', city: '厦门市', district: '思明区', detail: '鹭江道8号厦门国际银行大厦', fullAddress: '福建省厦门市思明区鹭江道8号厦门国际银行大厦', usedCount: 15, lastUsedDate: '2026-08-22' },
  { province: '重庆市', city: '重庆市', district: '渝中区', detail: '解放碑民权路28号时代广场B栋', fullAddress: '重庆市渝中区解放碑民权路28号时代广场B栋', usedCount: 21, lastUsedDate: '2026-08-23' },
  { province: '陕西省', city: '西安市', district: '雁塔区', detail: '高新一路创新大厦12层', fullAddress: '陕西省西安市雁塔区高新一路创新大厦12层', usedCount: 12, lastUsedDate: '2026-08-18' },
  { province: '河南省', city: '郑州市', district: '金水区', detail: '农业路东段经三路金融广场', fullAddress: '河南省郑州市金水区农业路东段经三路金融广场', usedCount: 17, lastUsedDate: '2026-08-22' },
  { province: '安徽省', city: '合肥市', district: '蜀山区', detail: '潜山路111号华润大厦东塔', fullAddress: '安徽省合肥市蜀山区潜山路111号华润大厦东塔', usedCount: 11, lastUsedDate: '2026-08-17' },
  { province: '辽宁省', city: '沈阳市', district: '和平区', detail: '青年大街1号市府恒隆广场', fullAddress: '辽宁省沈阳市和平区青年大街1号市府恒隆广场', usedCount: 9, lastUsedDate: '2026-08-16' },
  { province: '广西壮族自治区', city: '南宁市', district: '青秀区', detail: '民族大道136号万象城写字楼', fullAddress: '广西壮族自治区南宁市青秀区民族大道136号万象城写字楼', usedCount: 8, lastUsedDate: '2026-08-15' },
  { province: '云南省', city: '昆明市', district: '盘龙区', detail: '白塔路131号汇都国际A座', fullAddress: '云南省昆明市盘龙区白塔路131号汇都国际A座', usedCount: 7, lastUsedDate: '2026-08-14' }
];

// 2. 30-DAY DAILY REVENUE TREND DATA (Authentic fluctuations & specific dates)
export const MOCK_DAILY_REVENUE: DailyRevenueDataPoint[] = [
  { date: '2026-07-25', dayLabel: '07-25', totalRevenue: 2180.5, qingningRevenue: 980.5, jiuzhouRevenue: 520, dianzhongRevenue: 380, fanqieRevenue: 200, huashengRevenue: 100, videoViews: 124000, dramaViews: 168000 },
  { date: '2026-07-26', dayLabel: '07-26', totalRevenue: 2420.0, qingningRevenue: 1120.0, jiuzhouRevenue: 590, dianzhongRevenue: 410, fanqieRevenue: 210, huashengRevenue: 90, videoViews: 141000, dramaViews: 198000 },
  { date: '2026-07-27', dayLabel: '07-27', totalRevenue: 2310.0, qingningRevenue: 1040.0, jiuzhouRevenue: 540, dianzhongRevenue: 390, fanqieRevenue: 220, huashengRevenue: 120, videoViews: 133000, dramaViews: 185000 },
  { date: '2026-07-28', dayLabel: '07-28', totalRevenue: 2650.0, qingningRevenue: 1280.0, jiuzhouRevenue: 610, dianzhongRevenue: 420, fanqieRevenue: 230, huashengRevenue: 110, videoViews: 162000, dramaViews: 228000 },
  { date: '2026-07-29', dayLabel: '07-29', totalRevenue: 2890.0, qingningRevenue: 1390.0, jiuzhouRevenue: 680, dianzhongRevenue: 450, fanqieRevenue: 240, huashengRevenue: 130, videoViews: 178000, dramaViews: 254000 },
  { date: '2026-07-30', dayLabel: '07-30', totalRevenue: 2740.0, qingningRevenue: 1290.0, jiuzhouRevenue: 650, dianzhongRevenue: 440, fanqieRevenue: 230, huashengRevenue: 130, videoViews: 165000, dramaViews: 232000 },
  { date: '2026-07-31', dayLabel: '07-31', totalRevenue: 3120.0, qingningRevenue: 1540.0, jiuzhouRevenue: 730, dianzhongRevenue: 480, fanqieRevenue: 240, huashengRevenue: 130, videoViews: 196000, dramaViews: 282000 },
  { date: '2026-08-01', dayLabel: '08-01', totalRevenue: 3450.0, qingningRevenue: 1680.0, jiuzhouRevenue: 820, dianzhongRevenue: 510, fanqieRevenue: 280, huashengRevenue: 160, videoViews: 215000, dramaViews: 310000 },
  { date: '2026-08-02', dayLabel: '08-02', totalRevenue: 3290.0, qingningRevenue: 1590.0, jiuzhouRevenue: 780, dianzhongRevenue: 490, fanqieRevenue: 270, huashengRevenue: 160, videoViews: 202000, dramaViews: 290000 },
  { date: '2026-08-03', dayLabel: '08-03', totalRevenue: 2980.0, qingningRevenue: 1410.0, jiuzhouRevenue: 710, dianzhongRevenue: 460, fanqieRevenue: 260, huashengRevenue: 140, videoViews: 181000, dramaViews: 255000 },
  { date: '2026-08-04', dayLabel: '08-04', totalRevenue: 2850.0, qingningRevenue: 1320.0, jiuzhouRevenue: 690, dianzhongRevenue: 450, fanqieRevenue: 250, huashengRevenue: 140, videoViews: 169000, dramaViews: 238000 },
  { date: '2026-08-05', dayLabel: '08-05', totalRevenue: 3180.0, qingningRevenue: 1520.0, jiuzhouRevenue: 750, dianzhongRevenue: 490, fanqieRevenue: 270, huashengRevenue: 150, videoViews: 194000, dramaViews: 276000 },
  { date: '2026-08-06', dayLabel: '08-06', totalRevenue: 3320.0, qingningRevenue: 1610.0, jiuzhouRevenue: 790, dianzhongRevenue: 510, fanqieRevenue: 260, huashengRevenue: 150, videoViews: 206000, dramaViews: 295000 },
  { date: '2026-08-07', dayLabel: '08-07', totalRevenue: 3590.0, qingningRevenue: 1780.0, jiuzhouRevenue: 850, dianzhongRevenue: 530, fanqieRevenue: 280, huashengRevenue: 150, videoViews: 228000, dramaViews: 326000 },
  { date: '2026-08-08', dayLabel: '08-08', totalRevenue: 3840.0, qingningRevenue: 1920.0, jiuzhouRevenue: 910, dianzhongRevenue: 560, fanqieRevenue: 290, huashengRevenue: 160, videoViews: 245000, dramaViews: 358000 },
  { date: '2026-08-09', dayLabel: '08-09', totalRevenue: 3710.0, qingningRevenue: 1840.0, jiuzhouRevenue: 880, dianzhongRevenue: 550, fanqieRevenue: 290, huashengRevenue: 150, videoViews: 236000, dramaViews: 341000 },
  { date: '2026-08-10', dayLabel: '08-10', totalRevenue: 3150.0, qingningRevenue: 1490.0, jiuzhouRevenue: 760, dianzhongRevenue: 480, fanqieRevenue: 270, huashengRevenue: 150, videoViews: 191000, dramaViews: 272000 },
  { date: '2026-08-11', dayLabel: '08-11', totalRevenue: 2890.0, qingningRevenue: 1340.0, jiuzhouRevenue: 710, dianzhongRevenue: 450, fanqieRevenue: 250, huashengRevenue: 140, videoViews: 172000, dramaViews: 242000 },
  { date: '2026-08-12', dayLabel: '08-12', totalRevenue: 3050.0, qingningRevenue: 1450.0, jiuzhouRevenue: 740, dianzhongRevenue: 460, fanqieRevenue: 260, huashengRevenue: 140, videoViews: 186000, dramaViews: 264000 },
  { date: '2026-08-13', dayLabel: '08-13', totalRevenue: 3260.0, qingningRevenue: 1580.0, jiuzhouRevenue: 780, dianzhongRevenue: 480, fanqieRevenue: 270, huashengRevenue: 150, videoViews: 202000, dramaViews: 289000 },
  { date: '2026-08-14', dayLabel: '08-14', totalRevenue: 3410.0, qingningRevenue: 1670.0, jiuzhouRevenue: 820, dianzhongRevenue: 500, fanqieRevenue: 270, huashengRevenue: 150, videoViews: 214000, dramaViews: 308000 },
  { date: '2026-08-15', dayLabel: '08-15', totalRevenue: 3680.0, qingningRevenue: 1810.0, jiuzhouRevenue: 890, dianzhongRevenue: 540, fanqieRevenue: 280, huashengRevenue: 160, videoViews: 231000, dramaViews: 335000 },
  { date: '2026-08-16', dayLabel: '08-16', totalRevenue: 3520.0, qingningRevenue: 1720.0, jiuzhouRevenue: 860, dianzhongRevenue: 520, fanqieRevenue: 270, huashengRevenue: 150, videoViews: 220000, dramaViews: 318000 },
  { date: '2026-08-17', dayLabel: '08-17', totalRevenue: 2990.0, qingningRevenue: 1390.0, jiuzhouRevenue: 730, dianzhongRevenue: 470, fanqieRevenue: 260, huashengRevenue: 140, videoViews: 178000, dramaViews: 251000 },
  { date: '2026-08-18', dayLabel: '08-18', totalRevenue: 2840.0, qingningRevenue: 1290.0, jiuzhouRevenue: 700, dianzhongRevenue: 450, fanqieRevenue: 260, huashengRevenue: 140, videoViews: 165000, dramaViews: 232000 },
  { date: '2026-08-19', dayLabel: '08-19', totalRevenue: 2950.0, qingningRevenue: 1380.0, jiuzhouRevenue: 720, dianzhongRevenue: 460, fanqieRevenue: 250, huashengRevenue: 140, videoViews: 177000, dramaViews: 249000 },
  { date: '2026-08-20', dayLabel: '08-20', totalRevenue: 3190.0, qingningRevenue: 1520.0, jiuzhouRevenue: 780, dianzhongRevenue: 490, fanqieRevenue: 260, huashengRevenue: 140, videoViews: 195000, dramaViews: 276000 },
  { date: '2026-08-21', dayLabel: '08-21', totalRevenue: 3340.0, qingningRevenue: 1610.0, jiuzhouRevenue: 810, dianzhongRevenue: 510, fanqieRevenue: 270, huashengRevenue: 140, videoViews: 206000, dramaViews: 294000 },
  { date: '2026-08-22', dayLabel: '08-22', totalRevenue: 3480.0, qingningRevenue: 1710.0, jiuzhouRevenue: 840, dianzhongRevenue: 520, fanqieRevenue: 270, huashengRevenue: 140, videoViews: 219000, dramaViews: 314000 },
  { date: '2026-08-23', dayLabel: '08-23', totalRevenue: 3310.0, qingningRevenue: 1580.0, jiuzhouRevenue: 810, dianzhongRevenue: 510, fanqieRevenue: 270, huashengRevenue: 140, videoViews: 202000, dramaViews: 290000 },
];

export const REVENUE_SUMMARY: RevenueSummaryMetrics = {
  isYesterday: false,
  currentPeriodRevenue: 22420.0,
  dailyAverageRevenue: 3202.86,
  prevPeriodRevenue: 19870.0,
  changePct: 12.8,
  yesterdayRevenue: 3310.0,
  recentAverageRevenue: 3202.86,
  recentAveragePeriodDays: 7,
  changeVsAveragePct: 3.3,
  yesterdayContextLabel: '+3.3% (处于近期稳定区间)',
  completenessRatio: 0.875,
  totalAccounts: 16,
  updatedAccounts: 14,
  pendingAccounts: 2,
  completenessText: '14/16 已更新 · 2 待补采',
  isFullyComplete: false,
  last7DaysRevenue: 22420.0,
  prev7DaysRevenue: 19870.0,
  thisMonthRevenue: 76420.0,
  last7DaysChangePct: 12.8,
};

// 3. CONTRIBUTIONS BREAKDOWNS (Theaters, Accounts, Dramas)
export const THEATER_CONTRIBUTIONS: ContributionItem[] = [
  { id: 't-1', name: '青柠剧场', revenue: 10480.0, sharePct: 46.7, changePct: 14.5, isAttributable: true, qualityTier: 'direct' },
  { id: 't-2', name: '九州剧场', revenue: 5490.0, sharePct: 24.5, changePct: 8.2, isAttributable: true, qualityTier: 'direct' },
  { id: 't-3', name: '点众微剧', revenue: 3490.0, sharePct: 15.6, changePct: 6.1, isAttributable: true, qualityTier: 'direct' },
  { id: 't-4', name: '番茄剧场', revenue: 1980.0, sharePct: 8.8, changePct: -2.4, isAttributable: true, qualityTier: 'direct' },
  { id: 't-5', name: '花生剧场', revenue: 980.0, sharePct: 4.4, changePct: 1.1, isAttributable: true, qualityTier: 'direct' },
];

export const ACCOUNT_CONTRIBUTIONS: ContributionItem[] = [
  { id: 'acc-1', name: '短剧黄鸡版', revenue: 4180.0, sharePct: 18.6, changePct: 22.4, isAttributable: true, qualityTier: 'direct' },
  { id: 'acc-2', name: '鸿记水产行', revenue: 3260.0, sharePct: 14.5, changePct: -12.1, isAttributable: true, qualityTier: 'direct' },
  { id: 'acc-3', name: '冷脸萌萌1701', revenue: 2750.0, sharePct: 12.3, changePct: 16.8, isAttributable: true, qualityTier: 'direct' },
  { id: 'acc-4', name: '格格芝LE', revenue: 2410.0, sharePct: 10.7, changePct: 9.5, isAttributable: true, qualityTier: 'direct' },
  { id: 'acc-5', name: '曾经几何7906', revenue: 1980.0, sharePct: 8.8, changePct: 4.2, isAttributable: true, qualityTier: 'direct' },
  { id: 'acc-6', name: '肯德基等你爱你', revenue: 1690.0, sharePct: 7.5, changePct: 15.0, isAttributable: true, qualityTier: 'direct' },
  { id: 'acc-7', name: '热播短剧社-01', revenue: 1450.0, sharePct: 6.5, changePct: 3.1, isAttributable: true, qualityTier: 'direct' },
  { id: 'acc-8', name: '深夜追剧馆02', revenue: 1220.0, sharePct: 5.4, changePct: 8.0, isAttributable: true, qualityTier: 'direct' },
  { id: 'acc-9', name: '逆袭短剧王', revenue: 1080.0, sharePct: 4.8, changePct: -4.5, isAttributable: true, qualityTier: 'direct' },
  { id: 'acc-10', name: '甜宠小剧场-03', revenue: 950.0, sharePct: 4.2, changePct: 7.2, isAttributable: true, qualityTier: 'direct' },
  { id: 'acc-11', name: '爆款微剧社-06', revenue: 760.0, sharePct: 3.4, changePct: -1.8, isAttributable: true, qualityTier: 'direct' },
  { id: 'acc-12', name: '一口爽剧-08', revenue: 700.0, sharePct: 3.1, changePct: 0.0, isAttributable: true, qualityTier: 'direct' },
];

export const DRAMA_CONTRIBUTIONS: ContributionItem[] = [
  { id: 'd-1', name: '风雪草原苍狼少女', category: '古装传奇', revenue: 5860.0, sharePct: 26.1, changePct: 38.5, isAttributable: true, qualityTier: 'direct' },
  { id: 'd-2', name: '辣厨回乡鲜椒越香店越旺', category: '都市生活', revenue: 3940.0, sharePct: 17.6, changePct: 19.2, isAttributable: true, qualityTier: 'direct' },
  { id: 'd-3', name: '坠海逢生我率万鲨踏浪归来', category: '玄幻动作', revenue: 3120.0, sharePct: 13.9, changePct: 8.4, isAttributable: true, qualityTier: 'direct' },
  { id: 'd-4', name: '我用十元盒饭惊艳全城', category: '美食创业', revenue: 2650.0, sharePct: 11.8, changePct: 12.0, isAttributable: true, qualityTier: 'direct' },
  { id: 'd-5', name: '惨遭同行背叛百年野猪认我为王', category: '山野逆袭', revenue: 2210.0, sharePct: 9.9, changePct: -6.5, isAttributable: true, qualityTier: 'direct' },
  { id: 'd-6', name: '我在武侠世界抽卡成神', category: '武侠系统', revenue: 1890.0, sharePct: 8.4, changePct: 24.1, isAttributable: true, qualityTier: 'direct' },
  { id: 'd-7', name: '重返巅峰2008', category: '都市重生', revenue: 1480.0, sharePct: 6.6, changePct: -15.0, isAttributable: true, qualityTier: 'direct' },
  { id: 'd-8', name: '顾总，太太又惊艳全球了', category: '豪门甜宠', revenue: 1270.0, sharePct: 5.7, changePct: 2.3, isAttributable: true, qualityTier: 'direct' },
];

// 4. RULE-DERIVED CHANGE SIGNALS
export const CHANGE_SIGNALS: ChangeSignalItem[] = [
  {
    id: 'cs-1',
    type: 'positive',
    title: '短剧黄鸡版 近3日收益连续上涨',
    description: '单日流水从 ¥480 攀升至 ¥720，主推剧目《风雪草原苍狼少女》完播承接表现强劲',
    metric: '近3日 +50.0%',
    date: '昨日 22:00 规则推导',
  },
  {
    id: 'cs-2',
    type: 'negative',
    title: '鸿记水产行 昨日低于7日均值 38%',
    description: '昨日收益 ¥310（7日均值 ¥500），主推剧目《惨遭同行背叛百年野猪认我为王》视频完播衰减明显',
    metric: '单日 -38.0%',
    date: '昨日 22:00 规则推导',
  },
  {
    id: 'cs-3',
    type: 'positive',
    title: '青柠剧场 昨日收益较前日增长 21%',
    description: '青柠渠道当日总流水 ¥1,580（前日 ¥1,305），视频号生态内《辣厨回乡》跑出高转化卡点',
    metric: '渠道 +21.0%',
    date: '昨日 22:00 规则推导',
  },
  {
    id: 'cs-4',
    type: 'neutral',
    title: '冷脸萌萌1701 切换虚拟定位后转化稳定',
    description: '定位切换为「浙江省杭州市未来科技城」后发布3条视频，千次播放收益保持 ¥14.8 高位',
    metric: 'RPM ¥14.8',
    date: '前日 18:30 规则推导',
  },
];

// 5. 16+ ACCOUNTS LIST & DETAILS (With real mock names)
export const MOCK_ACCOUNTS_ANALYTICS: AccountAnalyticsItem[] = [
  {
    id: 'acc-1',
    name: '短剧黄鸡版',
    theater: '青柠剧场',
    hasQingningVideoData: true,
    sevenDaysRevenue: 4180.0,
    sevenDaysRevenueTrend: [480, 520, 550, 610, 640, 660, 720],
    thirtyDaysRevenue: 14850.0,
    recentMainDrama: '风雪草原苍狼少女',
    defaultLocation: MOCK_LOCATIONS_POOL[0], // 广州天河
    sevenDaysVideoViews: 312000,
    sevenDaysDramaViews: 448000,
    dailyTrend: [
      { date: '08-17', revenue: 480, videoViews: 35000 },
      { date: '08-18', revenue: 520, videoViews: 39000 },
      { date: '08-19', revenue: 550, videoViews: 42000 },
      { date: '08-20', revenue: 610, videoViews: 46000 },
      { date: '08-21', revenue: 640, videoViews: 48000 },
      { date: '08-22', revenue: 660, videoViews: 50000 },
      { date: '08-23', revenue: 720, videoViews: 52000 },
    ],
    dramaPerformances: [
      { dramaId: 'd-1', dramaName: '风雪草原苍狼少女', publishCount: 8, totalRevenue: 2450.0, avgRevenuePerVideo: 306.2, videoViews: 185000, dramaViews: 268000 },
      { dramaId: 'd-2', dramaName: '辣厨回乡鲜椒越香店越旺', publishCount: 5, totalRevenue: 1120.0, avgRevenuePerVideo: 224.0, videoViews: 84000, dramaViews: 118000 },
      { dramaId: 'd-3', dramaName: '坠海逢生我率万鲨踏浪归来', publishCount: 3, totalRevenue: 610.0, avgRevenuePerVideo: 203.3, videoViews: 43000, dramaViews: 62000 },
    ],
    locationPerformances: [
      { locationId: 'loc-1', fullAddress: '广东省广州市天河区体育西路103号维多利广场B座', usedCount: 10, totalRevenue: 2890.0, videoViews: 215000, dramaViews: 310000, lastUsedDate: '2026-08-23' },
      { locationId: 'loc-2', fullAddress: '广东省深圳市南山区粤海街道高新南一道科技园08栋', usedCount: 4, totalRevenue: 890.0, videoViews: 65000, dramaViews: 92000, lastUsedDate: '2026-08-19' },
      { locationId: 'loc-3', fullAddress: '浙江省杭州市余杭区文一西路969号未来科技城5号楼', usedCount: 2, totalRevenue: 400.0, videoViews: 32000, dramaViews: 46000, lastUsedDate: '2026-08-15' },
    ],
  },
  {
    id: 'acc-2',
    name: '鸿记水产行',
    theater: '青柠剧场',
    hasQingningVideoData: true,
    sevenDaysRevenue: 3260.0,
    sevenDaysRevenueTrend: [590, 560, 510, 480, 430, 380, 310],
    thirtyDaysRevenue: 13200.0,
    recentMainDrama: '惨遭同行背叛百年野猪认我为王',
    defaultLocation: MOCK_LOCATIONS_POOL[1], // 深圳南山
    sevenDaysVideoViews: 246000,
    sevenDaysDramaViews: 318000,
    dailyTrend: [
      { date: '08-17', revenue: 590, videoViews: 44000 },
      { date: '08-18', revenue: 560, videoViews: 41000 },
      { date: '08-19', revenue: 510, videoViews: 38000 },
      { date: '08-20', revenue: 480, videoViews: 36000 },
      { date: '08-21', revenue: 430, videoViews: 32000 },
      { date: '08-22', revenue: 380, videoViews: 29000 },
      { date: '08-23', revenue: 310, videoViews: 26000 },
    ],
    dramaPerformances: [
      { dramaId: 'd-5', dramaName: '惨遭同行背叛百年野猪认我为王', publishCount: 9, totalRevenue: 1850.0, avgRevenuePerVideo: 205.5, videoViews: 142000, dramaViews: 184000 },
      { dramaId: 'd-4', dramaName: '我用十元盒饭惊艳全城', publishCount: 4, totalRevenue: 930.0, avgRevenuePerVideo: 232.5, videoViews: 68000, dramaViews: 89000 },
      { dramaId: 'd-1', dramaName: '风雪草原苍狼少女', publishCount: 2, totalRevenue: 480.0, avgRevenuePerVideo: 240.0, videoViews: 36000, dramaViews: 45000 },
    ],
    locationPerformances: [
      { locationId: 'loc-2', fullAddress: '广东省深圳市南山区粤海街道高新南一道科技园08栋', usedCount: 11, totalRevenue: 2410.0, videoViews: 182000, dramaViews: 236000, lastUsedDate: '2026-08-23' },
      { locationId: 'loc-1', fullAddress: '广东省广州市天河区体育西路103号维多利广场B座', usedCount: 4, totalRevenue: 850.0, videoViews: 64000, dramaViews: 82000, lastUsedDate: '2026-08-18' },
    ],
  },
  {
    id: 'acc-3',
    name: '冷脸萌萌1701',
    theater: '青柠剧场',
    hasQingningVideoData: true,
    sevenDaysRevenue: 2750.0,
    sevenDaysRevenueTrend: [310, 340, 380, 410, 430, 420, 460],
    thirtyDaysRevenue: 10400.0,
    recentMainDrama: '辣厨回乡鲜椒越香店越旺',
    defaultLocation: MOCK_LOCATIONS_POOL[2], // 杭州余杭
    sevenDaysVideoViews: 208000,
    sevenDaysDramaViews: 295000,
    dailyTrend: [
      { date: '08-17', revenue: 310, videoViews: 23000 },
      { date: '08-18', revenue: 340, videoViews: 26000 },
      { date: '08-19', revenue: 380, videoViews: 29000 },
      { date: '08-20', revenue: 410, videoViews: 31000 },
      { date: '08-21', revenue: 430, videoViews: 33000 },
      { date: '08-22', revenue: 420, videoViews: 32000 },
      { date: '08-23', revenue: 460, videoViews: 34000 },
    ],
    dramaPerformances: [
      { dramaId: 'd-2', dramaName: '辣厨回乡鲜椒越香店越旺', publishCount: 7, totalRevenue: 1720.0, avgRevenuePerVideo: 245.7, videoViews: 131000, dramaViews: 186000 },
      { dramaId: 'd-6', dramaName: '我在武侠世界抽卡成神', publishCount: 4, totalRevenue: 750.0, avgRevenuePerVideo: 187.5, videoViews: 56000, dramaViews: 79000 },
      { dramaId: 'd-8', dramaName: '顾总，太太又惊艳全球了', publishCount: 2, totalRevenue: 280.0, avgRevenuePerVideo: 140.0, videoViews: 21000, dramaViews: 30000 },
    ],
    locationPerformances: [
      { locationId: 'loc-3', fullAddress: '浙江省杭州市余杭区文一西路969号未来科技城5号楼', usedCount: 9, totalRevenue: 2010.0, videoViews: 152000, dramaViews: 216000, lastUsedDate: '2026-08-23' },
      { locationId: 'loc-7', fullAddress: '上海市静安区南京西路1266号恒隆广场二期', usedCount: 4, totalRevenue: 740.0, videoViews: 56000, dramaViews: 79000, lastUsedDate: '2026-08-19' },
    ],
  },
  {
    id: 'acc-4',
    name: '格格芝LE',
    theater: '青柠剧场',
    hasQingningVideoData: true,
    sevenDaysRevenue: 2410.0,
    sevenDaysRevenueTrend: [280, 310, 330, 350, 370, 380, 390],
    thirtyDaysRevenue: 8900.0,
    recentMainDrama: '风雪草原苍狼少女',
    defaultLocation: MOCK_LOCATIONS_POOL[6], // 上海静安
    sevenDaysVideoViews: 178000,
    sevenDaysDramaViews: 242000,
    dailyTrend: [
      { date: '08-17', revenue: 280, videoViews: 21000 },
      { date: '08-18', revenue: 310, videoViews: 23000 },
      { date: '08-19', revenue: 330, videoViews: 24000 },
      { date: '08-20', revenue: 350, videoViews: 26000 },
      { date: '08-21', revenue: 370, videoViews: 27000 },
      { date: '08-22', revenue: 380, videoViews: 28000 },
      { date: '08-23', revenue: 390, videoViews: 29000 },
    ],
    dramaPerformances: [
      { dramaId: 'd-1', dramaName: '风雪草原苍狼少女', publishCount: 6, totalRevenue: 1560.0, avgRevenuePerVideo: 260.0, videoViews: 116000, dramaViews: 158000 },
      { dramaId: 'd-3', dramaName: '坠海逢生我率万鲨踏浪归来', publishCount: 4, totalRevenue: 850.0, avgRevenuePerVideo: 212.5, videoViews: 62000, dramaViews: 84000 },
    ],
    locationPerformances: [
      { locationId: 'loc-7', fullAddress: '上海市静安区南京西路1266号恒隆广场二期', usedCount: 8, totalRevenue: 1950.0, videoViews: 144000, dramaViews: 196000, lastUsedDate: '2026-08-23' },
      { locationId: 'loc-8', fullAddress: '上海市浦东新区世纪大道100号环球金融中心', usedCount: 2, totalRevenue: 460.0, videoViews: 34000, dramaViews: 46000, lastUsedDate: '2026-08-18' },
    ],
  },
  {
    id: 'acc-5',
    name: '曾经几何7906',
    theater: '九州剧场',
    hasQingningVideoData: false, // Regular theater (no video-level views)
    sevenDaysRevenue: 1980.0,
    sevenDaysRevenueTrend: [240, 260, 270, 290, 300, 310, 310],
    thirtyDaysRevenue: 7600.0,
    recentMainDrama: '坠海逢生我率万鲨踏浪归来',
    defaultLocation: MOCK_LOCATIONS_POOL[10], // 成都武侯
    sevenDaysVideoViews: undefined, // undefined in regular theater
    sevenDaysDramaViews: undefined,
    dailyTrend: [
      { date: '08-17', revenue: 240 },
      { date: '08-18', revenue: 260 },
      { date: '08-19', revenue: 270 },
      { date: '08-20', revenue: 290 },
      { date: '08-21', revenue: 300 },
      { date: '08-22', revenue: 310 },
      { date: '08-23', revenue: 310 },
    ],
    dramaPerformances: [
      { dramaId: 'd-3', dramaName: '坠海逢生我率万鲨踏浪归来', publishCount: 5, totalRevenue: 1240.0, avgRevenuePerVideo: 248.0 },
      { dramaId: 'd-4', dramaName: '我用十元盒饭惊艳全城', publishCount: 3, totalRevenue: 740.0, avgRevenuePerVideo: 246.7 },
    ],
    locationPerformances: [
      { locationId: 'loc-11', fullAddress: '四川省成都市武侯区天府三街199号新希望国际大厦', usedCount: 8, totalRevenue: 1980.0, lastUsedDate: '2026-08-23' },
    ],
  },
  {
    id: 'acc-6',
    name: '肯德基等你爱你',
    theater: '九州剧场',
    hasQingningVideoData: false,
    sevenDaysRevenue: 1690.0,
    sevenDaysRevenueTrend: [190, 210, 230, 250, 260, 270, 280],
    thirtyDaysRevenue: 6300.0,
    recentMainDrama: '我用十元盒饭惊艳全城',
    defaultLocation: MOCK_LOCATIONS_POOL[12], // 长沙岳麓
    dailyTrend: [
      { date: '08-17', revenue: 190 },
      { date: '08-18', revenue: 210 },
      { date: '08-19', revenue: 230 },
      { date: '08-20', revenue: 250 },
      { date: '08-21', revenue: 260 },
      { date: '08-22', revenue: 270 },
      { date: '08-23', revenue: 280 },
    ],
    dramaPerformances: [
      { dramaId: 'd-4', dramaName: '我用十元盒饭惊艳全城', publishCount: 6, totalRevenue: 1180.0, avgRevenuePerVideo: 196.7 },
      { dramaId: 'd-7', dramaName: '重返巅峰2008', publishCount: 3, totalRevenue: 510.0, avgRevenuePerVideo: 170.0 },
    ],
    locationPerformances: [
      { locationId: 'loc-13', fullAddress: '湖南省长沙市岳麓区麓谷大道627号新材料产业园2栋', usedCount: 9, totalRevenue: 1690.0, lastUsedDate: '2026-08-23' },
    ],
  },
  {
    id: 'acc-7',
    name: '热播短剧社-01',
    theater: '点众微剧',
    hasQingningVideoData: false,
    sevenDaysRevenue: 1450.0,
    sevenDaysRevenueTrend: [170, 190, 210, 220, 210, 220, 230],
    thirtyDaysRevenue: 5800.0,
    recentMainDrama: '重返巅峰2008',
    defaultLocation: MOCK_LOCATIONS_POOL[8], // 北京朝阳
    dailyTrend: [
      { date: '08-17', revenue: 170 },
      { date: '08-18', revenue: 190 },
      { date: '08-19', revenue: 210 },
      { date: '08-20', revenue: 220 },
      { date: '08-21', revenue: 210 },
      { date: '08-22', revenue: 220 },
      { date: '08-23', revenue: 230 },
    ],
    dramaPerformances: [
      { dramaId: 'd-7', dramaName: '重返巅峰2008', publishCount: 5, totalRevenue: 970.0, avgRevenuePerVideo: 194.0 },
      { dramaId: 'd-8', dramaName: '顾总，太太又惊艳全球了', publishCount: 3, totalRevenue: 480.0, avgRevenuePerVideo: 160.0 },
    ],
    locationPerformances: [
      { locationId: 'loc-9', fullAddress: '北京市朝阳区建国门外大街1号国贸大厦B座', usedCount: 8, totalRevenue: 1450.0, lastUsedDate: '2026-08-23' },
    ],
  },
  {
    id: 'acc-8',
    name: '深夜追剧馆02',
    theater: '点众微剧',
    hasQingningVideoData: false,
    sevenDaysRevenue: 1220.0,
    sevenDaysRevenueTrend: [150, 160, 170, 180, 180, 190, 190],
    thirtyDaysRevenue: 4900.0,
    recentMainDrama: '顾总，太太又惊艳全球了',
    defaultLocation: MOCK_LOCATIONS_POOL[4], // 苏州工业园
    dailyTrend: [
      { date: '08-17', revenue: 150 },
      { date: '08-18', revenue: 160 },
      { date: '08-19', revenue: 170 },
      { date: '08-20', revenue: 180 },
      { date: '08-21', revenue: 180 },
      { date: '08-22', revenue: 190 },
      { date: '08-23', revenue: 190 },
    ],
    dramaPerformances: [
      { dramaId: 'd-8', dramaName: '顾总，太太又惊艳全球了', publishCount: 6, totalRevenue: 790.0, avgRevenuePerVideo: 131.7 },
      { dramaId: 'd-2', dramaName: '辣厨回乡鲜椒越香店越旺', publishCount: 3, totalRevenue: 430.0, avgRevenuePerVideo: 143.3 },
    ],
    locationPerformances: [
      { locationId: 'loc-5', fullAddress: '江苏省苏州市工业园区星湖街328号创意产业园A4栋', usedCount: 9, totalRevenue: 1220.0, lastUsedDate: '2026-08-23' },
    ],
  },
  {
    id: 'acc-9',
    name: '逆袭短剧王',
    theater: '番茄剧场',
    hasQingningVideoData: false,
    sevenDaysRevenue: 1080.0,
    sevenDaysRevenueTrend: [170, 160, 150, 150, 150, 150, 150],
    thirtyDaysRevenue: 4300.0,
    recentMainDrama: '我在武侠世界抽卡成神',
    defaultLocation: MOCK_LOCATIONS_POOL[15], // 重庆渝中
    dailyTrend: [
      { date: '08-17', revenue: 170 },
      { date: '08-18', revenue: 160 },
      { date: '08-19', revenue: 150 },
      { date: '08-20', revenue: 150 },
      { date: '08-21', revenue: 150 },
      { date: '08-22', revenue: 150 },
      { date: '08-23', revenue: 150 },
    ],
    dramaPerformances: [
      { dramaId: 'd-6', dramaName: '我在武侠世界抽卡成神', publishCount: 5, totalRevenue: 640.0, avgRevenuePerVideo: 128.0 },
      { dramaId: 'd-5', dramaName: '惨遭同行背叛百年野猪认我为王', publishCount: 3, totalRevenue: 440.0, avgRevenuePerVideo: 146.7 },
    ],
    locationPerformances: [
      { locationId: 'loc-16', fullAddress: '重庆市渝中区解放碑民权路28号时代广场B栋', usedCount: 8, totalRevenue: 1080.0, lastUsedDate: '2026-08-23' },
    ],
  },
  {
    id: 'acc-10',
    name: '甜宠小剧场-03',
    theater: '花生剧场',
    hasQingningVideoData: false,
    sevenDaysRevenue: 950.0,
    sevenDaysRevenueTrend: [110, 120, 130, 140, 140, 150, 160],
    thirtyDaysRevenue: 3700.0,
    recentMainDrama: '顾总，太太又惊艳全球了',
    defaultLocation: MOCK_LOCATIONS_POOL[14], // 厦门思明
    dailyTrend: [
      { date: '08-17', revenue: 110 },
      { date: '08-18', revenue: 120 },
      { date: '08-19', revenue: 130 },
      { date: '08-20', revenue: 140 },
      { date: '08-21', revenue: 140 },
      { date: '08-22', revenue: 150 },
      { date: '08-23', revenue: 160 },
    ],
    dramaPerformances: [
      { dramaId: 'd-8', dramaName: '顾总，太太又惊艳全球了', publishCount: 5, totalRevenue: 590.0, avgRevenuePerVideo: 118.0 },
      { dramaId: 'd-1', dramaName: '风雪草原苍狼少女', publishCount: 3, totalRevenue: 360.0, avgRevenuePerVideo: 120.0 },
    ],
    locationPerformances: [
      { locationId: 'loc-15', fullAddress: '福建省厦门市思明区鹭江道8号厦门国际银行大厦', usedCount: 8, totalRevenue: 950.0, lastUsedDate: '2026-08-23' },
    ],
  },
  {
    id: 'acc-11',
    name: '爆款微剧社-06',
    theater: '青柠剧场',
    hasQingningVideoData: true,
    sevenDaysRevenue: 760.0,
    sevenDaysRevenueTrend: [100, 110, 110, 110, 110, 110, 110],
    thirtyDaysRevenue: 3100.0,
    recentMainDrama: '我在武侠世界抽卡成神',
    defaultLocation: MOCK_LOCATIONS_POOL[17], // 郑州金水
    sevenDaysVideoViews: 68000,
    sevenDaysDramaViews: 88000,
    dailyTrend: [
      { date: '08-17', revenue: 100, videoViews: 9000 },
      { date: '08-18', revenue: 110, videoViews: 10000 },
      { date: '08-19', revenue: 110, videoViews: 10000 },
      { date: '08-20', revenue: 110, videoViews: 10000 },
      { date: '08-21', revenue: 110, videoViews: 10000 },
      { date: '08-22', revenue: 110, videoViews: 10000 },
      { date: '08-23', revenue: 110, videoViews: 9000 },
    ],
    dramaPerformances: [
      { dramaId: 'd-6', dramaName: '我在武侠世界抽卡成神', publishCount: 5, totalRevenue: 500.0, avgRevenuePerVideo: 100.0, videoViews: 45000, dramaViews: 58000 },
      { dramaId: 'd-4', dramaName: '我用十元盒饭惊艳全城', publishCount: 3, totalRevenue: 260.0, avgRevenuePerVideo: 86.7, videoViews: 23000, dramaViews: 30000 },
    ],
    locationPerformances: [
      { locationId: 'loc-18', fullAddress: '河南省郑州市金水区农业路东段经三路金融广场', usedCount: 8, totalRevenue: 760.0, videoViews: 68000, dramaViews: 88000, lastUsedDate: '2026-08-22' },
    ],
  },
  {
    id: 'acc-12',
    name: '一口爽剧-08',
    theater: '九州剧场',
    hasQingningVideoData: false,
    sevenDaysRevenue: 700.0,
    sevenDaysRevenueTrend: [90, 95, 100, 100, 105, 105, 105],
    thirtyDaysRevenue: 2800.0,
    recentMainDrama: '辣厨回乡鲜椒越香店越旺',
    defaultLocation: MOCK_LOCATIONS_POOL[11], // 武汉洪山
    dailyTrend: [
      { date: '08-17', revenue: 90 },
      { date: '08-18', revenue: 95 },
      { date: '08-19', revenue: 100 },
      { date: '08-20', revenue: 100 },
      { date: '08-21', revenue: 105 },
      { date: '08-22', revenue: 105 },
      { date: '08-23', revenue: 105 },
    ],
    dramaPerformances: [
      { dramaId: 'd-2', dramaName: '辣厨回乡鲜椒越香店越旺', publishCount: 4, totalRevenue: 440.0, avgRevenuePerVideo: 110.0 },
      { dramaId: 'd-1', dramaName: '风雪草原苍狼少女', publishCount: 3, totalRevenue: 260.0, avgRevenuePerVideo: 86.7 },
    ],
    locationPerformances: [
      { locationId: 'loc-12', fullAddress: '湖北省武汉市洪山区关山大道光谷软件园F4栋创新楼', usedCount: 7, totalRevenue: 700.0, lastUsedDate: '2026-08-21' },
    ],
  },
  {
    id: 'acc-13',
    name: '独角兽短剧-09',
    theater: '青柠剧场',
    hasQingningVideoData: true,
    sevenDaysRevenue: 520.0,
    sevenDaysRevenueTrend: [60, 70, 70, 80, 80, 80, 80],
    thirtyDaysRevenue: 2100.0,
    recentMainDrama: '我用十元盒饭惊艳全城',
    defaultLocation: MOCK_LOCATIONS_POOL[16], // 西安雁塔
    sevenDaysVideoViews: 45000,
    sevenDaysDramaViews: 61000,
    dailyTrend: [
      { date: '08-17', revenue: 60, videoViews: 5000 },
      { date: '08-18', revenue: 70, videoViews: 6000 },
      { date: '08-19', revenue: 70, videoViews: 6000 },
      { date: '08-20', revenue: 80, videoViews: 7000 },
      { date: '08-21', revenue: 80, videoViews: 7000 },
      { date: '08-22', revenue: 80, videoViews: 7000 },
      { date: '08-23', revenue: 80, videoViews: 7000 },
    ],
    dramaPerformances: [
      { dramaId: 'd-4', dramaName: '我用十元盒饭惊艳全城', publishCount: 4, totalRevenue: 340.0, avgRevenuePerVideo: 85.0, videoViews: 30000, dramaViews: 40000 },
      { dramaId: 'd-6', dramaName: '我在武侠世界抽卡成神', publishCount: 2, totalRevenue: 180.0, avgRevenuePerVideo: 90.0, videoViews: 15000, dramaViews: 21000 },
    ],
    locationPerformances: [
      { locationId: 'loc-17', fullAddress: '陕西省西安市雁塔区高新一路创新大厦12层', usedCount: 6, totalRevenue: 520.0, videoViews: 45000, dramaViews: 61000, lastUsedDate: '2026-08-18' },
    ],
  },
  {
    id: 'acc-14',
    name: '星芒短剧工作室',
    theater: '点众微剧',
    hasQingningVideoData: false,
    sevenDaysRevenue: 410.0,
    sevenDaysRevenueTrend: [50, 55, 60, 60, 60, 60, 65],
    thirtyDaysRevenue: 1650.0,
    recentMainDrama: '重返巅峰2008',
    defaultLocation: MOCK_LOCATIONS_POOL[18], // 合肥蜀山
    dailyTrend: [
      { date: '08-17', revenue: 50 },
      { date: '08-18', revenue: 55 },
      { date: '08-19', revenue: 60 },
      { date: '08-20', revenue: 60 },
      { date: '08-21', revenue: 60 },
      { date: '08-22', revenue: 60 },
      { date: '08-23', revenue: 65 },
    ],
    dramaPerformances: [
      { dramaId: 'd-7', dramaName: '重返巅峰2008', publishCount: 4, totalRevenue: 410.0, avgRevenuePerVideo: 102.5 },
    ],
    locationPerformances: [
      { locationId: 'loc-19', fullAddress: '安徽省合肥市蜀山区潜山路111号华润大厦东塔', usedCount: 4, totalRevenue: 410.0, lastUsedDate: '2026-08-17' },
    ],
  },
  {
    id: 'acc-15',
    name: '剧迷老陈',
    theater: '青柠剧场',
    hasQingningVideoData: true,
    sevenDaysRevenue: 310.0,
    sevenDaysRevenueTrend: [30, 40, 45, 50, 45, 50, 50],
    thirtyDaysRevenue: 1200.0,
    recentMainDrama: '惨遭同行背叛百年野猪认我为王',
    defaultLocation: MOCK_LOCATIONS_POOL[19], // 沈阳和平
    sevenDaysVideoViews: 26000,
    sevenDaysDramaViews: 34000,
    dailyTrend: [
      { date: '08-17', revenue: 30, videoViews: 2500 },
      { date: '08-18', revenue: 40, videoViews: 3500 },
      { date: '08-19', revenue: 45, videoViews: 4000 },
      { date: '08-20', revenue: 50, videoViews: 4000 },
      { date: '08-21', revenue: 45, videoViews: 4000 },
      { date: '08-22', revenue: 50, videoViews: 4000 },
      { date: '08-23', revenue: 50, videoViews: 4000 },
    ],
    dramaPerformances: [
      { dramaId: 'd-5', dramaName: '惨遭同行背叛百年野猪认我为王', publishCount: 3, totalRevenue: 310.0, avgRevenuePerVideo: 103.3, videoViews: 26000, dramaViews: 34000 },
    ],
    locationPerformances: [
      { locationId: 'loc-20', fullAddress: '辽宁省沈阳市和平区青年大街1号市府恒隆广场', usedCount: 3, totalRevenue: 310.0, videoViews: 26000, dramaViews: 34000, lastUsedDate: '2026-08-16' },
    ],
  },
  {
    id: 'acc-16',
    name: '极光短剧精选',
    theater: '花生剧场',
    hasQingningVideoData: false,
    sevenDaysRevenue: 180.0,
    sevenDaysRevenueTrend: [20, 20, 25, 30, 25, 30, 30],
    thirtyDaysRevenue: 720.0,
    recentMainDrama: '顾总，太太又惊艳全球了',
    defaultLocation: MOCK_LOCATIONS_POOL[20], // 南宁青秀
    dailyTrend: [
      { date: '08-17', revenue: 20 },
      { date: '08-18', revenue: 20 },
      { date: '08-19', revenue: 25 },
      { date: '08-20', revenue: 30 },
      { date: '08-21', revenue: 25 },
      { date: '08-22', revenue: 30 },
      { date: '08-23', revenue: 30 },
    ],
    dramaPerformances: [
      { dramaId: 'd-8', dramaName: '顾总，太太又惊艳全球了', publishCount: 3, totalRevenue: 180.0, avgRevenuePerVideo: 60.0 },
    ],
    locationPerformances: [
      { locationId: 'loc-21', fullAddress: '广西壮族自治区南宁市青秀区民族大道136号万象城写字楼', usedCount: 3, totalRevenue: 180.0, lastUsedDate: '2026-08-15' },
    ],
  }
];

// 6. 20+ DRAMAS LIST & DETAILS (With required names)
export const MOCK_DRAMAS_ANALYTICS: DramaAnalyticsItem[] = [
  {
    id: 'd-1',
    name: '风雪草原苍狼少女',
    category: '古装传奇',
    activeAccountsCount: 6,
    sevenDaysRevenue: 5860.0,
    sevenDaysRevenueTrend: [640, 710, 780, 850, 920, 960, 1000],
    thirtyDaysRevenue: 21400.0,
    hasQingningData: true,
    sevenDaysVideoViews: 432000,
    sevenDaysDramaViews: 618000,
    dailyTrend: [
      { date: '08-17', revenue: 640, videoViews: 48000 },
      { date: '08-18', revenue: 710, videoViews: 53000 },
      { date: '08-19', revenue: 780, videoViews: 58000 },
      { date: '08-20', revenue: 850, videoViews: 63000 },
      { date: '08-21', revenue: 920, videoViews: 68000 },
      { date: '08-22', revenue: 960, videoViews: 70000 },
      { date: '08-23', revenue: 1000, videoViews: 72000 },
    ],
    accountDifferences: [
      { accountId: 'acc-1', accountName: '短剧黄鸡版', publishCount: 8, totalRevenue: 2450.0, avgRevenuePerVideo: 306.2, videoViews: 185000, dramaViews: 268000 },
      { accountId: 'acc-4', accountName: '格格芝LE', publishCount: 6, totalRevenue: 1560.0, avgRevenuePerVideo: 260.0, videoViews: 116000, dramaViews: 158000 },
      { accountId: 'acc-2', accountName: '鸿记水产行', publishCount: 3, totalRevenue: 680.0, avgRevenuePerVideo: 226.7, videoViews: 52000, dramaViews: 73000 },
      { accountId: 'acc-10', accountName: '甜宠小剧场-03', publishCount: 3, totalRevenue: 490.0, avgRevenuePerVideo: 163.3, videoViews: 38000, dramaViews: 52000 },
      { accountId: 'acc-12', accountName: '一口爽剧-08', publishCount: 2, totalRevenue: 380.0, avgRevenuePerVideo: 190.0, videoViews: 26000, dramaViews: 39000 },
      { accountId: 'acc-3', accountName: '冷脸萌萌1701', publishCount: 2, totalRevenue: 300.0, avgRevenuePerVideo: 150.0, videoViews: 15000, dramaViews: 28000 },
    ],
    videoVariance: {
      publishedVideoCount: 24,
      bestSingleVideoRevenue: 520.0,
      avgSingleVideoRevenue: 244.2,
      medianSingleVideoRevenue: 235.0,
      worstSingleVideoRevenue: 25.0,
      bestVideoName: '风雪草原苍狼少女-08 (第3分段高光反杀)',
    },
    locationPerformances: [
      { locationId: 'loc-1', fullAddress: '广东省广州市天河区体育西路103号维多利广场B座', usedCount: 9, totalRevenue: 2780.0, videoViews: 205000, dramaViews: 294000 },
      { locationId: 'loc-7', fullAddress: '上海市静安区南京西路1266号恒隆广场二期', usedCount: 7, totalRevenue: 1840.0, videoViews: 135000, dramaViews: 192000 },
      { locationId: 'loc-3', fullAddress: '浙江省杭州市余杭区文一西路969号未来科技城5号楼', usedCount: 4, totalRevenue: 720.0, videoViews: 54000, dramaViews: 76000 },
      { locationId: 'loc-2', fullAddress: '广东省深圳市南山区粤海街道高新南一道科技园08栋', usedCount: 4, totalRevenue: 520.0, videoViews: 38000, dramaViews: 56000 },
    ],
  },
  {
    id: 'd-2',
    name: '辣厨回乡鲜椒越香店越旺',
    category: '都市生活',
    activeAccountsCount: 5,
    sevenDaysRevenue: 3940.0,
    sevenDaysRevenueTrend: [450, 490, 530, 570, 610, 640, 650],
    thirtyDaysRevenue: 14200.0,
    hasQingningData: true,
    sevenDaysVideoViews: 295000,
    sevenDaysDramaViews: 416000,
    dailyTrend: [
      { date: '08-17', revenue: 450, videoViews: 34000 },
      { date: '08-18', revenue: 490, videoViews: 37000 },
      { date: '08-19', revenue: 530, videoViews: 40000 },
      { date: '08-20', revenue: 570, videoViews: 43000 },
      { date: '08-21', revenue: 610, videoViews: 46000 },
      { date: '08-22', revenue: 640, videoViews: 47000 },
      { date: '08-23', revenue: 650, videoViews: 48000 },
    ],
    accountDifferences: [
      { accountId: 'acc-3', accountName: '冷脸萌萌1701', publishCount: 7, totalRevenue: 1720.0, avgRevenuePerVideo: 245.7, videoViews: 131000, dramaViews: 186000 },
      { accountId: 'acc-1', accountName: '短剧黄鸡版', publishCount: 5, totalRevenue: 1120.0, avgRevenuePerVideo: 224.0, videoViews: 84000, dramaViews: 118000 },
      { accountId: 'acc-12', accountName: '一口爽剧-08', publishCount: 4, totalRevenue: 580.0, avgRevenuePerVideo: 145.0, videoViews: 42000, dramaViews: 58000 },
      { accountId: 'acc-8', accountName: '深夜追剧馆02', publishCount: 3, totalRevenue: 520.0, avgRevenuePerVideo: 173.3, videoViews: 38000, dramaViews: 54000 },
    ],
    videoVariance: {
      publishedVideoCount: 19,
      bestSingleVideoRevenue: 380.0,
      avgSingleVideoRevenue: 207.4,
      medianSingleVideoRevenue: 195.0,
      worstSingleVideoRevenue: 40.0,
      bestVideoName: '辣厨回乡鲜椒越香店越旺-04 (独门秘方打脸恶霸)',
    },
    locationPerformances: [
      { locationId: 'loc-3', fullAddress: '浙江省杭州市余杭区文一西路969号未来科技城5号楼', usedCount: 8, totalRevenue: 1960.0, videoViews: 146000, dramaViews: 206000 },
      { locationId: 'loc-1', fullAddress: '广东省广州市天河区体育西路103号维多利广场B座', usedCount: 6, totalRevenue: 1280.0, videoViews: 96000, dramaViews: 135000 },
      { locationId: 'loc-5', fullAddress: '江苏省苏州市工业园区星湖街328号创意产业园A4栋', usedCount: 5, totalRevenue: 700.0, videoViews: 53000, dramaViews: 75000 },
    ],
  },
  {
    id: 'd-3',
    name: '坠海逢生我率万鲨踏浪归来',
    category: '玄幻动作',
    activeAccountsCount: 4,
    sevenDaysRevenue: 3120.0,
    sevenDaysRevenueTrend: [380, 410, 440, 460, 470, 480, 480],
    thirtyDaysRevenue: 11800.0,
    hasQingningData: true,
    sevenDaysVideoViews: 228000,
    sevenDaysDramaViews: 312000,
    dailyTrend: [
      { date: '08-17', revenue: 380, videoViews: 28000 },
      { date: '08-18', revenue: 410, videoViews: 30000 },
      { date: '08-19', revenue: 440, videoViews: 32000 },
      { date: '08-20', revenue: 460, videoViews: 34000 },
      { date: '08-21', revenue: 470, videoViews: 35000 },
      { date: '08-22', revenue: 480, videoViews: 35000 },
      { date: '08-23', revenue: 480, videoViews: 34000 },
    ],
    accountDifferences: [
      { accountId: 'acc-5', accountName: '曾经几何7906', publishCount: 5, totalRevenue: 1240.0, avgRevenuePerVideo: 248.0 },
      { accountId: 'acc-4', accountName: '格格芝LE', publishCount: 4, totalRevenue: 850.0, avgRevenuePerVideo: 212.5, videoViews: 62000, dramaViews: 84000 },
      { accountId: 'acc-1', accountName: '短剧黄鸡版', publishCount: 3, totalRevenue: 610.0, avgRevenuePerVideo: 203.3, videoViews: 43000, dramaViews: 62000 },
      { accountId: 'acc-9', accountName: '逆袭短剧王', publishCount: 2, totalRevenue: 420.0, avgRevenuePerVideo: 210.0 },
    ],
    videoVariance: {
      publishedVideoCount: 14,
      bestSingleVideoRevenue: 340.0,
      avgSingleVideoRevenue: 222.8,
      medianSingleVideoRevenue: 210.0,
      worstSingleVideoRevenue: 60.0,
      bestVideoName: '坠海逢生我率万鲨踏浪归来-02 (龙王踏浪群鲨叩拜)',
    },
    locationPerformances: [
      { locationId: 'loc-11', fullAddress: '四川省成都市武侯区天府三街199号新希望国际大厦', usedCount: 5, totalRevenue: 1240.0 },
      { locationId: 'loc-7', fullAddress: '上海市静安区南京西路1266号恒隆广场二期', usedCount: 4, totalRevenue: 850.0, videoViews: 62000, dramaViews: 84000 },
      { locationId: 'loc-1', fullAddress: '广东省广州市天河区体育西路103号维多利广场B座', usedCount: 3, totalRevenue: 610.0, videoViews: 43000, dramaViews: 62000 },
    ],
  },
  {
    id: 'd-4',
    name: '我用十元盒饭惊艳全城',
    category: '美食创业',
    activeAccountsCount: 5,
    sevenDaysRevenue: 2650.0,
    sevenDaysRevenueTrend: [320, 350, 370, 390, 400, 410, 410],
    thirtyDaysRevenue: 9800.0,
    hasQingningData: true,
    sevenDaysVideoViews: 195000,
    sevenDaysDramaViews: 268000,
    dailyTrend: [
      { date: '08-17', revenue: 320, videoViews: 24000 },
      { date: '08-18', revenue: 350, videoViews: 26000 },
      { date: '08-19', revenue: 370, videoViews: 27000 },
      { date: '08-20', revenue: 390, videoViews: 29000 },
      { date: '08-21', revenue: 400, videoViews: 30000 },
      { date: '08-22', revenue: 410, videoViews: 30000 },
      { date: '08-23', revenue: 410, videoViews: 29000 },
    ],
    accountDifferences: [
      { accountId: 'acc-6', accountName: '肯德基等你爱你', publishCount: 6, totalRevenue: 1180.0, avgRevenuePerVideo: 196.7 },
      { accountId: 'acc-2', accountName: '鸿记水产行', publishCount: 4, totalRevenue: 930.0, avgRevenuePerVideo: 232.5, videoViews: 68000, dramaViews: 89000 },
      { accountId: 'acc-13', accountName: '独角兽短剧-09', publishCount: 4, totalRevenue: 340.0, avgRevenuePerVideo: 85.0, videoViews: 30000, dramaViews: 40000 },
      { accountId: 'acc-11', accountName: '爆款微剧社-06', publishCount: 3, totalRevenue: 200.0, avgRevenuePerVideo: 66.7, videoViews: 18000, dramaViews: 24000 },
    ],
    videoVariance: {
      publishedVideoCount: 17,
      bestSingleVideoRevenue: 290.0,
      avgSingleVideoRevenue: 155.8,
      medianSingleVideoRevenue: 150.0,
      worstSingleVideoRevenue: 20.0,
      bestVideoName: '我用十元盒饭惊艳全城-05 (米其林主厨跪求学艺)',
    },
    locationPerformances: [
      { locationId: 'loc-13', fullAddress: '湖南省长沙市岳麓区麓谷大道627号新材料产业园2栋', usedCount: 6, totalRevenue: 1180.0 },
      { locationId: 'loc-2', fullAddress: '广东省深圳市南山区粤海街道高新南一道科技园08栋', usedCount: 4, totalRevenue: 930.0, videoViews: 68000, dramaViews: 89000 },
      { locationId: 'loc-17', fullAddress: '陕西省西安市雁塔区高新一路创新大厦12层', usedCount: 4, totalRevenue: 340.0, videoViews: 30000, dramaViews: 40000 },
    ],
  },
  {
    id: 'd-5',
    name: '惨遭同行背叛百年野猪认我为王',
    category: '山野逆袭',
    activeAccountsCount: 4,
    sevenDaysRevenue: 2210.0,
    sevenDaysRevenueTrend: [420, 390, 350, 310, 270, 240, 230],
    thirtyDaysRevenue: 9400.0,
    hasQingningData: true,
    sevenDaysVideoViews: 172000,
    sevenDaysDramaViews: 220000,
    dailyTrend: [
      { date: '08-17', revenue: 420, videoViews: 32000 },
      { date: '08-18', revenue: 390, videoViews: 30000 },
      { date: '08-19', revenue: 350, videoViews: 27000 },
      { date: '08-20', revenue: 310, videoViews: 24000 },
      { date: '08-21', revenue: 270, videoViews: 21000 },
      { date: '08-22', revenue: 240, videoViews: 19000 },
      { date: '08-23', revenue: 230, videoViews: 19000 },
    ],
    accountDifferences: [
      { accountId: 'acc-2', accountName: '鸿记水产行', publishCount: 9, totalRevenue: 1850.0, avgRevenuePerVideo: 205.5, videoViews: 142000, dramaViews: 184000 },
      { accountId: 'acc-15', accountName: '剧迷老陈', publishCount: 3, totalRevenue: 310.0, avgRevenuePerVideo: 103.3, videoViews: 26000, dramaViews: 34000 },
      { accountId: 'acc-9', accountName: '逆袭短剧王', publishCount: 1, totalRevenue: 50.0, avgRevenuePerVideo: 50.0 },
    ],
    videoVariance: {
      publishedVideoCount: 13,
      bestSingleVideoRevenue: 260.0,
      avgSingleVideoRevenue: 170.0,
      medianSingleVideoRevenue: 160.0,
      worstSingleVideoRevenue: 10.0,
      bestVideoName: '惨遭同行背叛百年野猪认我为王-01 (野猪王率万兽护山)',
    },
    locationPerformances: [
      { locationId: 'loc-2', fullAddress: '广东省深圳市南山区粤海街道高新南一道科技园08栋', usedCount: 9, totalRevenue: 1850.0, videoViews: 142000, dramaViews: 184000 },
      { locationId: 'loc-20', fullAddress: '辽宁省沈阳市和平区青年大街1号市府恒隆广场', usedCount: 3, totalRevenue: 310.0, videoViews: 26000, dramaViews: 34000 },
    ],
  },
  {
    id: 'd-6',
    name: '我在武侠世界抽卡成神',
    category: '武侠系统',
    activeAccountsCount: 4,
    sevenDaysRevenue: 1890.0,
    sevenDaysRevenueTrend: [210, 240, 260, 280, 290, 300, 310],
    thirtyDaysRevenue: 6900.0,
    hasQingningData: true,
    sevenDaysVideoViews: 142000,
    sevenDaysDramaViews: 198000,
    dailyTrend: [
      { date: '08-17', revenue: 210, videoViews: 16000 },
      { date: '08-18', revenue: 240, videoViews: 18000 },
      { date: '08-19', revenue: 260, videoViews: 20000 },
      { date: '08-20', revenue: 280, videoViews: 21000 },
      { date: '08-21', revenue: 290, videoViews: 22000 },
      { date: '08-22', revenue: 300, videoViews: 22000 },
      { date: '08-23', revenue: 310, videoViews: 23000 },
    ],
    accountDifferences: [
      { accountId: 'acc-3', accountName: '冷脸萌萌1701', publishCount: 4, totalRevenue: 750.0, avgRevenuePerVideo: 187.5, videoViews: 56000, dramaViews: 79000 },
      { accountId: 'acc-9', accountName: '逆袭短剧王', publishCount: 5, totalRevenue: 640.0, avgRevenuePerVideo: 128.0 },
      { accountId: 'acc-11', accountName: '爆款微剧社-06', publishCount: 5, totalRevenue: 500.0, avgRevenuePerVideo: 100.0, videoViews: 45000, dramaViews: 58000 },
    ],
    videoVariance: {
      publishedVideoCount: 14,
      bestSingleVideoRevenue: 280.0,
      avgSingleVideoRevenue: 135.0,
      medianSingleVideoRevenue: 120.0,
      worstSingleVideoRevenue: 15.0,
      bestVideoName: '我在武侠世界抽卡成神-07 (十连抽获金色降龙十八掌)',
    },
    locationPerformances: [
      { locationId: 'loc-3', fullAddress: '浙江省杭州市余杭区文一西路969号未来科技城5号楼', usedCount: 4, totalRevenue: 750.0, videoViews: 56000, dramaViews: 79000 },
      { locationId: 'loc-16', fullAddress: '重庆市渝中区解放碑民权路28号时代广场B栋', usedCount: 5, totalRevenue: 640.0 },
      { locationId: 'loc-18', fullAddress: '河南省郑州市金水区农业路东段经三路金融广场', usedCount: 5, totalRevenue: 500.0, videoViews: 45000, dramaViews: 58000 },
    ],
  },
  {
    id: 'd-7',
    name: '重返巅峰2008',
    category: '都市重生',
    activeAccountsCount: 3,
    sevenDaysRevenue: 1480.0,
    sevenDaysRevenueTrend: [240, 230, 220, 210, 200, 190, 190],
    thirtyDaysRevenue: 6800.0,
    hasQingningData: false,
    dailyTrend: [
      { date: '08-17', revenue: 240 },
      { date: '08-18', revenue: 230 },
      { date: '08-19', revenue: 220 },
      { date: '08-20', revenue: 210 },
      { date: '08-21', revenue: 200 },
      { date: '08-22', revenue: 190 },
      { date: '08-23', revenue: 190 },
    ],
    accountDifferences: [
      { accountId: 'acc-7', accountName: '热播短剧社-01', publishCount: 5, totalRevenue: 970.0, avgRevenuePerVideo: 194.0 },
      { accountId: 'acc-6', accountName: '肯德基等你爱你', publishCount: 3, totalRevenue: 510.0, avgRevenuePerVideo: 170.0 },
    ],
    videoVariance: {
      publishedVideoCount: 8,
      bestSingleVideoRevenue: 240.0,
      avgSingleVideoRevenue: 185.0,
      medianSingleVideoRevenue: 180.0,
      worstSingleVideoRevenue: 80.0,
    },
    locationPerformances: [
      { locationId: 'loc-9', fullAddress: '北京市朝阳区建国门外大街1号国贸大厦B座', usedCount: 5, totalRevenue: 970.0 },
      { locationId: 'loc-13', fullAddress: '湖南省长沙市岳麓区麓谷大道627号新材料产业园2栋', usedCount: 3, totalRevenue: 510.0 },
    ],
  },
  {
    id: 'd-8',
    name: '顾总，太太又惊艳全球了',
    category: '豪门甜宠',
    activeAccountsCount: 4,
    sevenDaysRevenue: 1270.0,
    sevenDaysRevenueTrend: [160, 170, 180, 190, 190, 190, 190],
    thirtyDaysRevenue: 5400.0,
    hasQingningData: false,
    dailyTrend: [
      { date: '08-17', revenue: 160 },
      { date: '08-18', revenue: 170 },
      { date: '08-19', revenue: 180 },
      { date: '08-20', revenue: 190 },
      { date: '08-21', revenue: 190 },
      { date: '08-22', revenue: 190 },
      { date: '08-23', revenue: 190 },
    ],
    accountDifferences: [
      { accountId: 'acc-8', accountName: '深夜追剧馆02', publishCount: 6, totalRevenue: 790.0, avgRevenuePerVideo: 131.7 },
      { accountId: 'acc-7', accountName: '热播短剧社-01', publishCount: 3, totalRevenue: 480.0, avgRevenuePerVideo: 160.0 },
    ],
    videoVariance: {
      publishedVideoCount: 9,
      bestSingleVideoRevenue: 190.0,
      avgSingleVideoRevenue: 141.1,
      medianSingleVideoRevenue: 140.0,
      worstSingleVideoRevenue: 60.0,
    },
    locationPerformances: [
      { locationId: 'loc-5', fullAddress: '江苏省苏州市工业园区星湖街328号创意产业园A4栋', usedCount: 6, totalRevenue: 790.0 },
      { locationId: 'loc-9', fullAddress: '北京市朝阳区建国门外大街1号国贸大厦B座', usedCount: 3, totalRevenue: 480.0 },
    ],
  },
  {
    id: 'd-9',
    name: '我在八零年代当首富',
    category: '年代逆袭',
    activeAccountsCount: 2,
    sevenDaysRevenue: 980.0,
    sevenDaysRevenueTrend: [130, 135, 140, 140, 145, 145, 145],
    thirtyDaysRevenue: 4100.0,
    hasQingningData: false,
    dailyTrend: [
      { date: '08-17', revenue: 130 },
      { date: '08-18', revenue: 135 },
      { date: '08-19', revenue: 140 },
      { date: '08-20', revenue: 140 },
      { date: '08-21', revenue: 145 },
      { date: '08-22', revenue: 145 },
      { date: '08-23', revenue: 145 },
    ],
    accountDifferences: [
      { accountId: 'acc-5', accountName: '曾经几何7906', publishCount: 4, totalRevenue: 620.0, avgRevenuePerVideo: 155.0 },
      { accountId: 'acc-6', accountName: '肯德基等你爱你', publishCount: 2, totalRevenue: 360.0, avgRevenuePerVideo: 180.0 },
    ],
    videoVariance: {
      publishedVideoCount: 6,
      bestSingleVideoRevenue: 200.0,
      avgSingleVideoRevenue: 163.3,
      medianSingleVideoRevenue: 160.0,
      worstSingleVideoRevenue: 90.0,
    },
    locationPerformances: [
      { locationId: 'loc-11', fullAddress: '四川省成都市武侯区天府三街199号新希望国际大厦', usedCount: 4, totalRevenue: 620.0 },
      { locationId: 'loc-13', fullAddress: '湖南省长沙市岳麓区麓谷大道627号新材料产业园2栋', usedCount: 2, totalRevenue: 360.0 },
    ],
  },
  {
    id: 'd-10',
    name: '绝世龙帅狂飙都市',
    category: '战神霸总',
    activeAccountsCount: 2,
    sevenDaysRevenue: 850.0,
    sevenDaysRevenueTrend: [110, 115, 120, 125, 125, 125, 130],
    thirtyDaysRevenue: 3600.0,
    hasQingningData: false,
    dailyTrend: [
      { date: '08-17', revenue: 110 },
      { date: '08-18', revenue: 115 },
      { date: '08-19', revenue: 120 },
      { date: '08-20', revenue: 125 },
      { date: '08-21', revenue: 125 },
      { date: '08-22', revenue: 125 },
      { date: '08-23', revenue: 130 },
    ],
    accountDifferences: [
      { accountId: 'acc-7', accountName: '热播短剧社-01', publishCount: 4, totalRevenue: 520.0, avgRevenuePerVideo: 130.0 },
      { accountId: 'acc-9', accountName: '逆袭短剧王', publishCount: 3, totalRevenue: 330.0, avgRevenuePerVideo: 110.0 },
    ],
    videoVariance: {
      publishedVideoCount: 7,
      bestSingleVideoRevenue: 160.0,
      avgSingleVideoRevenue: 121.4,
      medianSingleVideoRevenue: 120.0,
      worstSingleVideoRevenue: 50.0,
    },
    locationPerformances: [
      { locationId: 'loc-9', fullAddress: '北京市朝阳区建国门外大街1号国贸大厦B座', usedCount: 4, totalRevenue: 520.0 },
      { locationId: 'loc-16', fullAddress: '重庆市渝中区解放碑民权路28号时代广场B栋', usedCount: 3, totalRevenue: 330.0 },
    ],
  }
];

// 7. 250+ QINGNING PLATFORM VIDEO DAILY RECORDS (Authentic distribution & quadrants)
const MOCK_PLATFORM_VIDEOS_SEED: PlatformVideoItem[] = [];

// Realistic video generators
const qingningAccounts = [
  { id: 'acc-1', name: '短剧黄鸡版' },
  { id: 'acc-2', name: '鸿记水产行' },
  { id: 'acc-3', name: '冷脸萌萌1701' },
  { id: 'acc-4', name: '格格芝LE' },
  { id: 'acc-11', name: '爆款微剧社-06' },
  { id: 'acc-13', name: '独角兽短剧-09' },
  { id: 'acc-15', name: '剧迷老陈' }
];

const qingningDramas = [
  { id: 'd-1', name: '风雪草原苍狼少女' },
  { id: 'd-2', name: '辣厨回乡鲜椒越香店越旺' },
  { id: 'd-3', name: '坠海逢生我率万鲨踏浪归来' },
  { id: 'd-4', name: '我用十元盒饭惊艳全城' },
  { id: 'd-5', name: '惨遭同行背叛百年野猪认我为王' },
  { id: 'd-6', name: '我在武侠世界抽卡成神' },
];

const dates = ['2026-08-23', '2026-08-22', '2026-08-21', '2026-08-20', '2026-08-19', '2026-08-18', '2026-08-17'];

let videoCounter = 1000;

// High views + High revenue (爆款转化)
for (let i = 0; i < 35; i++) {
  videoCounter++;
  const acc = qingningAccounts[i % 4];
  const drama = qingningDramas[i % 3];
  const date = dates[i % dates.length];
  const views = Math.floor(38000 + Math.random() * 45000);
  const dramaViews = Math.floor(views * (1.2 + Math.random() * 0.7)); // 承接强度 1.2 ~ 1.9
  const revenue = Number((views * (0.007 + Math.random() * 0.006)).toFixed(1)); // High RPM: ¥7 ~ ¥13
  const receptionStrength = Number((dramaViews / views).toFixed(2));
  const rpm = Number(((revenue / views) * 1000).toFixed(2));
  const isLinked = i % 2 === 0;

  MOCK_PLATFORM_VIDEOS_SEED.push({
    id: `vid-qn-${videoCounter}`,
    date,
    accountName: acc.name,
    accountId: acc.id,
    dramaName: drama.name,
    dramaId: drama.id,
    theater: '青柠剧场',
    videoViews: views,
    dramaViews: dramaViews,
    revenue,
    receptionStrength,
    rpm,
    associationStatus: isLinked ? 'linked' : 'unlinked',
    linkedMaterialId: isLinked ? `素材-${String((i % 12) + 1).padStart(2, '0')}` : undefined,
    linkedInternalClipName: isLinked ? `${drama.name}-片段${(i % 12) + 1}` : undefined,
    linkedAt: isLinked ? '2026-08-22 14:30' : undefined,
    isOutlier: true,
  });
}

// High views + Low revenue (引流卡点 / 低转化)
for (let i = 0; i < 40; i++) {
  videoCounter++;
  const acc = qingningAccounts[(i + 1) % qingningAccounts.length];
  const drama = qingningDramas[(i + 2) % qingningDramas.length];
  const date = dates[i % dates.length];
  const views = Math.floor(32000 + Math.random() * 38000);
  const dramaViews = Math.floor(views * (0.4 + Math.random() * 0.3)); // 承接强度低 0.4 ~ 0.7
  const revenue = Number((views * (0.0008 + Math.random() * 0.0012)).toFixed(1)); // Low RPM: ¥0.8 ~ ¥2.0
  const receptionStrength = Number((dramaViews / views).toFixed(2));
  const rpm = Number(((revenue / views) * 1000).toFixed(2));
  const isLinked = i % 3 === 0;

  MOCK_PLATFORM_VIDEOS_SEED.push({
    id: `vid-qn-${videoCounter}`,
    date,
    accountName: acc.name,
    accountId: acc.id,
    dramaName: drama.name,
    dramaId: drama.id,
    theater: '青柠剧场',
    videoViews: views,
    dramaViews: dramaViews,
    revenue,
    receptionStrength,
    rpm,
    associationStatus: isLinked ? 'linked' : 'unlinked',
    linkedMaterialId: isLinked ? `素材-${String((i % 10) + 1).padStart(2, '0')}` : undefined,
    linkedInternalClipName: isLinked ? `${drama.name}-片段${(i % 10) + 1}` : undefined,
    linkedAt: isLinked ? '2026-08-21 11:20' : undefined,
  });
}

// Low views + High revenue (高客单私域 / 强付费转化)
for (let i = 0; i < 35; i++) {
  videoCounter++;
  const acc = qingningAccounts[(i + 2) % 4];
  const drama = qingningDramas[(i + 1) % qingningDramas.length];
  const date = dates[i % dates.length];
  const views = Math.floor(4500 + Math.random() * 9000);
  const dramaViews = Math.floor(views * (1.5 + Math.random() * 0.9)); // 承接强度 1.5 ~ 2.4
  const revenue = Number((views * (0.016 + Math.random() * 0.015)).toFixed(1)); // Very High RPM: ¥16 ~ ¥31
  const receptionStrength = Number((dramaViews / views).toFixed(2));
  const rpm = Number(((revenue / views) * 1000).toFixed(2));
  const isLinked = i % 2 === 1;

  MOCK_PLATFORM_VIDEOS_SEED.push({
    id: `vid-qn-${videoCounter}`,
    date,
    accountName: acc.name,
    accountId: acc.id,
    dramaName: drama.name,
    dramaId: drama.id,
    theater: '青柠剧场',
    videoViews: views,
    dramaViews: dramaViews,
    revenue,
    receptionStrength,
    rpm,
    associationStatus: isLinked ? 'linked' : 'unlinked',
    linkedMaterialId: isLinked ? `素材-${String((i % 8) + 1).padStart(2, '0')}` : undefined,
    linkedInternalClipName: isLinked ? `${drama.name}-精选${(i % 8) + 1}` : undefined,
    linkedAt: isLinked ? '2026-08-23 09:10' : undefined,
    isOutlier: true,
  });
}

// Low views + Low revenue / Normal regular videos (大量常规与长尾)
for (let i = 0; i < 140; i++) {
  videoCounter++;
  const acc = qingningAccounts[i % qingningAccounts.length];
  const drama = qingningDramas[i % qingningDramas.length];
  const date = dates[i % dates.length];
  const views = Math.floor(1200 + Math.random() * 11000);
  const dramaViews = Math.floor(views * (0.7 + Math.random() * 0.6));
  // Some explicit 0.0 revenue cases
  const isExplicitZero = i % 15 === 0;
  const revenue = isExplicitZero ? 0.0 : Number((views * (0.003 + Math.random() * 0.004)).toFixed(1));
  const receptionStrength = views > 0 ? Number((dramaViews / views).toFixed(2)) : 0;
  const rpm = views > 0 ? Number(((revenue / views) * 1000).toFixed(2)) : 0;
  const isLinked = i % 4 === 0;

  MOCK_PLATFORM_VIDEOS_SEED.push({
    id: `vid-qn-${videoCounter}`,
    date,
    accountName: acc.name,
    accountId: acc.id,
    dramaName: drama.name,
    dramaId: drama.id,
    theater: '青柠剧场',
    videoViews: views,
    dramaViews: dramaViews,
    revenue,
    receptionStrength,
    rpm,
    associationStatus: isLinked ? 'linked' : 'unlinked',
    linkedMaterialId: isLinked ? `素材-${String((i % 15) + 1).padStart(2, '0')}` : undefined,
    linkedInternalClipName: isLinked ? `${drama.name}-普通剪辑${(i % 15) + 1}` : undefined,
    linkedAt: isLinked ? '2026-08-20 16:40' : undefined,
  });
}

export const MOCK_PLATFORM_VIDEOS = MOCK_PLATFORM_VIDEOS_SEED;

// 8. COMBINATIONS MATRIX DATA (90+ combinations for Account x Drama, Account x Location, Drama x Location)
export const MOCK_COMBINATION_RECORDS: CombinationRecord[] = [];

// A. Account x Drama combinations
MOCK_ACCOUNTS_ANALYTICS.forEach((acc) => {
  MOCK_DRAMAS_ANALYTICS.slice(0, 8).forEach((drama) => {
    // Generate realistic correlation
    const hasRecord = (acc.name === '短剧黄鸡版' && drama.name === '风雪草原苍狼少女') ||
                      (acc.name === '鸿记水产行' && drama.name === '惨遭同行背叛百年野猪认我为王') ||
                      (acc.name === '冷脸萌萌1701' && drama.name === '辣厨回乡鲜椒越香店越旺') ||
                      (acc.name === '曾经几何7906' && drama.name === '坠海逢生我率万鲨踏浪归来') ||
                      (acc.name === '肯德基等你爱你' && drama.name === '我用十元盒饭惊艳全城') ||
                      (acc.name === '格格芝LE' && drama.name === '风雪草原苍狼少女') ||
                      Math.random() > 0.45;

    if (hasRecord) {
      const sampleCount = Math.floor(3 + Math.random() * 12);
      const avgRevenue = Number((80 + Math.random() * 220).toFixed(1));
      const totalRevenue = Number((sampleCount * avgRevenue).toFixed(1));
      const bestRevenue = Number((avgRevenue * (1.3 + Math.random() * 0.8)).toFixed(1));
      const worstRevenue = Number((avgRevenue * (0.2 + Math.random() * 0.4)).toFixed(1));
      const medianRevenue = Number((avgRevenue * (0.95 + Math.random() * 0.1)).toFixed(1));
      const videoViews = acc.hasQingningVideoData ? sampleCount * Math.floor(15000 + Math.random() * 20000) : undefined;
      const dramaViews = acc.hasQingningVideoData && videoViews ? Math.floor(videoViews * 1.35) : undefined;

      MOCK_COMBINATION_RECORDS.push({
        id: `comb-ad-${acc.id}-${drama.id}`,
        rowKey: acc.id,
        rowLabel: acc.name,
        colKey: drama.id,
        colLabel: drama.name,
        dimension: 'account_x_drama',
        sampleCount,
        totalRevenue,
        avgRevenue,
        medianRevenue,
        bestRevenue,
        worstRevenue,
        videoViews,
        dramaViews,
        recentTrend: [
          Number((avgRevenue * 0.8).toFixed(1)),
          Number((avgRevenue * 0.9).toFixed(1)),
          Number((avgRevenue * 1.05).toFixed(1)),
          Number((avgRevenue * 0.95).toFixed(1)),
          Number(avgRevenue.toFixed(1)),
        ],
        recentPublishRecords: [
          { id: `rec-1`, date: '2026-08-23', videoName: `${drama.name}-高光01`, revenue: bestRevenue, videoViews: videoViews ? Math.floor(videoViews / sampleCount) : undefined, locationText: acc.defaultLocation.fullAddress },
          { id: `rec-2`, date: '2026-08-22', videoName: `${drama.name}-正片02`, revenue: avgRevenue, videoViews: videoViews ? Math.floor(videoViews / sampleCount * 0.9) : undefined, locationText: acc.defaultLocation.fullAddress },
          { id: `rec-3`, date: '2026-08-20', videoName: `${drama.name}-卡点03`, revenue: medianRevenue, videoViews: videoViews ? Math.floor(videoViews / sampleCount * 0.8) : undefined, locationText: acc.defaultLocation.fullAddress },
        ]
      });
    }
  });
});

// B. Account x Location combinations
MOCK_ACCOUNTS_ANALYTICS.slice(0, 10).forEach((acc) => {
  MOCK_LOCATIONS_POOL.slice(0, 8).forEach((loc, idx) => {
    if (idx < 3 || Math.random() > 0.6) {
      const sampleCount = Math.floor(2 + Math.random() * 8);
      const avgRevenue = Number((90 + Math.random() * 180).toFixed(1));
      const totalRevenue = Number((sampleCount * avgRevenue).toFixed(1));
      const bestRevenue = Number((avgRevenue * 1.5).toFixed(1));
      const worstRevenue = Number((avgRevenue * 0.4).toFixed(1));
      const medianRevenue = avgRevenue;

      MOCK_COMBINATION_RECORDS.push({
        id: `comb-al-${acc.id}-loc-${idx}`,
        rowKey: acc.id,
        rowLabel: acc.name,
        colKey: `loc-${idx}`,
        colLabel: `${loc.city} · ${loc.district}`,
        dimension: 'account_x_location',
        sampleCount,
        totalRevenue,
        avgRevenue,
        medianRevenue,
        bestRevenue,
        worstRevenue,
        recentTrend: [avgRevenue * 0.9, avgRevenue, avgRevenue * 1.1],
        recentPublishRecords: [
          { id: `rec-al-1`, date: '2026-08-23', videoName: `发布记录A`, revenue: bestRevenue, locationText: loc.fullAddress },
          { id: `rec-al-2`, date: '2026-08-21', videoName: `发布记录B`, revenue: avgRevenue, locationText: loc.fullAddress },
        ]
      });
    }
  });
});

// C. Drama x Location combinations
MOCK_DRAMAS_ANALYTICS.slice(0, 8).forEach((drama) => {
  MOCK_LOCATIONS_POOL.slice(0, 8).forEach((loc, idx) => {
    if (idx < 4 || Math.random() > 0.5) {
      const sampleCount = Math.floor(3 + Math.random() * 9);
      const avgRevenue = Number((100 + Math.random() * 200).toFixed(1));
      const totalRevenue = Number((sampleCount * avgRevenue).toFixed(1));
      const bestRevenue = Number((avgRevenue * 1.6).toFixed(1));
      const worstRevenue = Number((avgRevenue * 0.3).toFixed(1));
      const medianRevenue = avgRevenue;

      MOCK_COMBINATION_RECORDS.push({
        id: `comb-dl-${drama.id}-loc-${idx}`,
        rowKey: drama.id,
        rowLabel: drama.name,
        colKey: `loc-${idx}`,
        colLabel: `${loc.city} · ${loc.district}`,
        dimension: 'drama_x_location',
        sampleCount,
        totalRevenue,
        avgRevenue,
        medianRevenue,
        bestRevenue,
        worstRevenue,
        recentTrend: [avgRevenue * 0.85, avgRevenue * 0.95, avgRevenue * 1.05],
        recentPublishRecords: [
          { id: `rec-dl-1`, date: '2026-08-23', videoName: `${drama.name}-定位实测`, revenue: bestRevenue, locationText: loc.fullAddress },
          { id: `rec-dl-2`, date: '2026-08-20', videoName: `${drama.name}-对比分发`, revenue: avgRevenue, locationText: loc.fullAddress },
        ]
      });
    }
  });
});

// 9. REVENUE COLLECTION LOGS
export const MOCK_COLLECTION_LOGS: RevenueCollectionLog[] = [
  {
    id: 'rc-101',
    theaterName: '青柠剧场',
    accountName: '短剧黄鸡版',
    period: '2026-08-23 (昨日)',
    status: 'success',
    collectedAmount: 720.00,
    qualityTier: 'direct',
    updatedAt: '06:01:12',
    note: '已校验日结算明细，同时同步拉取当日视频播放与剧集播放数据',
  },
  {
    id: 'rc-102',
    theaterName: '青柠剧场',
    accountName: '冷脸萌萌1701',
    period: '2026-08-23 (昨日)',
    status: 'success',
    collectedAmount: 460.00,
    qualityTier: 'direct',
    updatedAt: '06:01:15',
    note: '日流水正常归集',
  },
  {
    id: 'rc-103',
    theaterName: '九州剧场',
    accountName: '曾经几何7906',
    period: '2026-08-23 (昨日)',
    status: 'success',
    collectedAmount: 310.00,
    qualityTier: 'direct',
    updatedAt: '06:01:30',
  },
  {
    id: 'rc-104',
    theaterName: '点众微剧',
    accountName: '热播短剧社-01',
    period: '2026-08-23 (昨日)',
    status: 'success',
    collectedAmount: 230.00,
    qualityTier: 'direct',
    updatedAt: '06:01:45',
  },
  {
    id: 'rc-105',
    theaterName: '番茄剧场',
    accountName: '逆袭短剧王',
    period: '2026-08-23 (昨日)',
    status: 'success',
    collectedAmount: 150.00,
    qualityTier: 'direct',
    updatedAt: '06:02:00',
  },
  {
    id: 'rc-106',
    theaterName: '花生剧场',
    accountName: '极光短剧精选',
    period: '2026-08-23 (昨日)',
    status: 'no_data',
    collectedAmount: 0,
    qualityTier: 'direct',
    updatedAt: '06:02:10',
    note: '接口返回正常，当日该账号无分销流水发生 (明确为 0)',
  },
  {
    id: 'rc-107',
    theaterName: '九州剧场',
    accountName: '一口爽剧-08',
    period: '2026-08-21 (历史补采)',
    status: 'success',
    collectedAmount: 105.00,
    qualityTier: 'direct',
    updatedAt: '08-22 14:20',
    note: '手动触发离线账单补采对账',
  },
];
