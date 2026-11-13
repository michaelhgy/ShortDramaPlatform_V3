import { createOptimizationReasonCounts, getOptimizationAppearance } from '../types/optimizationNotices.ts';
import { 
  TheaterInfo, 
  AccountInfo, 
  RevenueRecord, 
  AccountDailyTraffic, 
  VideoTrafficItem, 
  OptimizationRecord,
  SimplifiedOptimizationReason,
  OFFICIAL_OPTIMIZATION_DEFINITIONS,
  AccountOptimizationStat
} from '../types/shortDramaOps';

// ==========================================
// 1. 十三大主力短剧剧场档案 (十几个剧场)
// ==========================================
export const THEATERS: TheaterInfo[] = [
  {
    id: 'theater-qingning',
    name: '青柠剧场',
    code: 'QN-LIME',
    description: '主打甜宠、女频复仇、都市豪门，高粘性年轻女性受众',
    badgeColor: '#10B981',
    accentBg: 'bg-emerald-50 text-emerald-700 border-emerald-200'
  },
  {
    id: 'theater-chumo',
    name: '触摸剧场',
    code: 'CM-TOUCH',
    description: '男频头部阵地，涵盖战神逆袭、都市神医与反转赘婿',
    badgeColor: '#6366F1',
    accentBg: 'bg-indigo-50 text-indigo-700 border-indigo-200'
  },
  {
    id: 'theater-jiuzhou',
    name: '九州剧场',
    code: 'JZ-EXP',
    description: '热血高燃大男主、年代创业、家庭伦理，爆发力强',
    badgeColor: '#EC4899',
    accentBg: 'bg-pink-50 text-pink-700 border-pink-200'
  },
  {
    id: 'theater-maiya',
    name: '麦芽剧场',
    code: 'MY-MALT',
    description: '萌宝寻亲、长辈家庭、婚姻反击，二创裂变率极高',
    badgeColor: '#F59E0B',
    accentBg: 'bg-amber-50 text-amber-700 border-amber-200'
  },
  {
    id: 'theater-dianzhong',
    name: '点众剧场',
    code: 'DZ-CLICK',
    description: '综合头部厂牌，亿级投流爆剧分发主力，万播产值高',
    badgeColor: '#3B82F6',
    accentBg: 'bg-blue-50 text-blue-700 border-blue-200'
  },
  {
    id: 'theater-jukan',
    name: '聚看剧场',
    code: 'JK-WATCH',
    description: '悬疑反转、探案追凶与都市奇幻，长尾付费表现稳定',
    badgeColor: '#8B5CF6',
    accentBg: 'bg-purple-50 text-purple-700 border-purple-200'
  },
  {
    id: 'theater-zhangwan',
    name: '掌玩剧场',
    code: 'ZW-PLAY',
    description: '轻喜剧、脑洞爽文、穿越反套路，年轻泛受众池广',
    badgeColor: '#14B8A6',
    accentBg: 'bg-teal-50 text-teal-700 border-teal-200'
  },
  {
    id: 'theater-mitang',
    name: '蜜糖剧场',
    code: 'MT-HONEY',
    description: '极致虐恋、破镜重圆、民国烽火，高付费意愿女性群体',
    badgeColor: '#F43F5E',
    accentBg: 'bg-rose-50 text-rose-700 border-rose-200'
  },
  {
    id: 'theater-yinhe',
    name: '银河剧场',
    code: 'YH-GALAXY',
    description: '末世求生、异能觉醒、修仙穿越，高播放裂变爆点',
    badgeColor: '#06B6D4',
    accentBg: 'bg-cyan-50 text-cyan-700 border-cyan-200'
  },
  {
    id: 'theater-fanqie',
    name: '番茄剧场',
    code: 'FQ-TOMATO',
    description: '网文超级IP改编联动，下沉市场覆盖率广，完播率高',
    badgeColor: '#EA580C',
    accentBg: 'bg-orange-50 text-orange-700 border-orange-200'
  },
  {
    id: 'theater-rongliang',
    name: '容量剧场',
    code: 'RL-CAPACITY',
    description: '精品古装、非遗武侠、民国悬疑，制作水准业界领先',
    badgeColor: '#84CC16',
    accentBg: 'bg-lime-50 text-lime-700 border-lime-200'
  },
  {
    id: 'theater-youbao',
    name: '友宝剧场',
    code: 'YB-TREASURE',
    description: '银发怀旧、乡村励志与亲情伦理，中老年高粘性赛道',
    badgeColor: '#D97706',
    accentBg: 'bg-yellow-50 text-yellow-700 border-yellow-200'
  },
  {
    id: 'theater-huaxia',
    name: '华夏剧场',
    code: 'HX-HERITAGE',
    description: '国风大宋、历史商战与传统美德短剧，高官方推流系数',
    badgeColor: '#64748B',
    accentBg: 'bg-slate-50 text-slate-700 border-slate-200'
  }
];

// ==========================================
// 2. 账号档案 (34个账号，严格1:1绑定剧场)
// ==========================================
export const ACCOUNTS: AccountInfo[] = [
  // 1. 青柠剧场旗下 (3个)
  {
    id: 'acc-qn-01',
    name: '青柠-爆米花追剧',
    theaterId: 'theater-qingning',
    theaterName: '青柠剧场',
    tier: '头部爆款',
    avatarBg: 'bg-gradient-to-br from-emerald-400 to-teal-600',
    platform: '微信视频号',
    description: '粉丝128W，女频甜宠第一流量号，平均万播产值¥158'
  },
  {
    id: 'acc-qn-02',
    name: '青柠-微光甜宠社',
    theaterId: 'theater-qingning',
    theaterName: '青柠剧场',
    tier: '腰部主力',
    avatarBg: 'bg-gradient-to-br from-teal-400 to-cyan-600',
    platform: '微信视频号',
    description: '稳定每日2更，女性完播率高，擅长情感虐恋转折剪辑'
  },
  {
    id: 'acc-qn-03',
    name: '青柠-深夜看点03',
    theaterId: 'theater-qingning',
    theaterName: '青柠剧场',
    tier: '新锐测试',
    avatarBg: 'bg-gradient-to-br from-rose-400 to-pink-600',
    platform: '微信视频号',
    description: '新签约测试号，重点承接晚间21:15档女频悬疑剧目'
  },

  // 2. 触摸剧场旗下 (3个)
  {
    id: 'acc-cm-01',
    name: '触摸-战神归来主理人',
    theaterId: 'theater-chumo',
    theaterName: '触摸剧场',
    tier: '头部爆款',
    avatarBg: 'bg-gradient-to-br from-indigo-500 to-blue-700',
    platform: '微信视频号',
    description: '粉丝186W，战神爽剧单月GMV超40万，万播产值达¥228'
  },
  {
    id: 'acc-cm-02',
    name: '触摸-热血爽剧狂',
    theaterId: 'theater-chumo',
    theaterName: '触摸剧场',
    tier: '腰部主力',
    avatarBg: 'bg-gradient-to-br from-blue-500 to-indigo-600',
    platform: '微信视频号',
    description: '主打高节奏冲突卡点，男粉占比86%，黄金前3秒抓手极稳'
  },
  {
    id: 'acc-cm-03',
    name: '触摸-神医天下',
    theaterId: 'theater-chumo',
    theaterName: '触摸剧场',
    tier: '限流观察',
    avatarBg: 'bg-gradient-to-br from-slate-500 to-gray-700',
    platform: '微信视频号',
    description: '近期因同质化切片被平台频次预警，正在优化重剪策略'
  },

  // 3. 九州剧场旗下 (3个)
  {
    id: 'acc-jz-01',
    name: '九州-逆风翻盘局',
    theaterId: 'theater-jiuzhou',
    theaterName: '九州剧场',
    tier: '头部爆款',
    avatarBg: 'bg-gradient-to-br from-pink-500 to-rose-600',
    platform: '微信视频号',
    description: '粉丝145W，热血翻盘第一号，单剧最高带收益突破18万'
  },
  {
    id: 'acc-jz-02',
    name: '九州-热血英雄志',
    theaterId: 'theater-jiuzhou',
    theaterName: '九州剧场',
    tier: '腰部主力',
    avatarBg: 'bg-gradient-to-br from-rose-500 to-orange-500',
    platform: '微信视频号',
    description: '专注大男主成长线剪辑，晚间20点黄金流量峰值稳固'
  },
  {
    id: 'acc-jz-03',
    name: '九州-狂飙微剧精选',
    theaterId: 'theater-jiuzhou',
    theaterName: '九州剧场',
    tier: '新锐测试',
    avatarBg: 'bg-gradient-to-br from-amber-500 to-red-500',
    platform: '微信视频号',
    description: '新设孵化矩阵号，专打年轻职场反卷题材'
  },

  // 4. 麦芽剧场旗下 (3个)
  {
    id: 'acc-my-01',
    name: '麦芽-萌宝催泪剧场',
    theaterId: 'theater-maiya',
    theaterName: '麦芽剧场',
    tier: '头部爆款',
    avatarBg: 'bg-gradient-to-br from-amber-400 to-orange-600',
    platform: '微信视频号',
    description: '粉丝172W，母婴宝妈与银发群第一大号，高赞互动率达14.2%'
  },
  {
    id: 'acc-my-02',
    name: '麦芽-亲情反转日记',
    theaterId: 'theater-maiya',
    theaterName: '麦芽剧场',
    tier: '腰部主力',
    avatarBg: 'bg-gradient-to-br from-yellow-400 to-amber-600',
    platform: '微信视频号',
    description: '伦理破防神剧，以高反转台词设计著称，完播率高达28%'
  },
  {
    id: 'acc-my-03',
    name: '麦芽-暖心微光派',
    theaterId: 'theater-maiya',
    theaterName: '麦芽剧场',
    tier: '腰部主力',
    avatarBg: 'bg-gradient-to-br from-orange-400 to-red-500',
    platform: '微信视频号',
    description: '聚焦家庭亲子伦理，用户转发率极高'
  },

  // 5. 点众剧场旗下 (3个)
  {
    id: 'acc-dz-01',
    name: '点众-都市热播社',
    theaterId: 'theater-dianzhong',
    theaterName: '点众剧场',
    tier: '头部爆款',
    avatarBg: 'bg-gradient-to-br from-blue-500 to-cyan-600',
    platform: '微信视频号',
    description: '全平台投流主阵地，单月分发切片超120条，流量极具爆发力'
  },
  {
    id: 'acc-dz-02',
    name: '点众-豪门总裁专线',
    theaterId: 'theater-dianzhong',
    theaterName: '点众剧场',
    tier: '腰部主力',
    avatarBg: 'bg-gradient-to-br from-sky-400 to-blue-600',
    platform: '微信视频号',
    description: '深耕高能反转总裁剧，受众客单价全矩阵最高'
  },
  {
    id: 'acc-dz-03',
    name: '点众-黄金爽文切片',
    theaterId: 'theater-dianzhong',
    theaterName: '点众剧场',
    tier: '新锐测试',
    avatarBg: 'bg-gradient-to-br from-cyan-400 to-indigo-500',
    platform: '微信视频号',
    description: '测试A/B切片实验账号，专门验证各剧前3秒黄金钩子'
  },

  // 6. 聚看剧场旗下 (2个)
  {
    id: 'acc-jk-01',
    name: '聚看-迷雾探案社',
    theaterId: 'theater-jukan',
    theaterName: '聚看剧场',
    tier: '腰部主力',
    avatarBg: 'bg-gradient-to-br from-purple-500 to-violet-700',
    platform: '微信视频号',
    description: '悬疑高智商解谜剧目，评论区剧情讨论留存深度极佳'
  },
  {
    id: 'acc-jk-02',
    name: '聚看-夜半反转局',
    theaterId: 'theater-jukan',
    theaterName: '聚看剧场',
    tier: '腰部主力',
    avatarBg: 'bg-gradient-to-br from-violet-500 to-purple-800',
    platform: '微信视频号',
    description: '主打冷门精品反转短剧，忠诚付费用户比例高'
  },

  // 7. 掌玩剧场旗下 (3个)
  {
    id: 'acc-zw-01',
    name: '掌玩-爆笑下饭微剧',
    theaterId: 'theater-zhangwan',
    theaterName: '掌玩剧场',
    tier: '腰部主力',
    avatarBg: 'bg-gradient-to-br from-teal-400 to-emerald-600',
    platform: '微信视频号',
    description: '搞笑反套路微短剧，午间12点午餐时段流量巨量集聚'
  },
  {
    id: 'acc-zw-02',
    name: '掌玩-脑洞大开君',
    theaterId: 'theater-zhangwan',
    theaterName: '掌玩剧场',
    tier: '新锐测试',
    avatarBg: 'bg-gradient-to-br from-emerald-400 to-teal-700',
    platform: '微信视频号',
    description: '新上线穿越题材实验号，首月播放已破800万'
  },
  {
    id: 'acc-zw-03',
    name: '掌玩-超能打脸官',
    theaterId: 'theater-zhangwan',
    theaterName: '掌玩剧场',
    tier: '限流观察',
    avatarBg: 'bg-gradient-to-br from-slate-400 to-teal-900',
    platform: '微信视频号',
    description: '按未挂链接提示调整短剧挂载'
  },

  // 8. 蜜糖剧场旗下 (3个)
  {
    id: 'acc-mt-01',
    name: '蜜糖-替身虐恋局',
    theaterId: 'theater-mitang',
    theaterName: '蜜糖剧场',
    tier: '头部爆款',
    avatarBg: 'bg-gradient-to-br from-rose-400 to-pink-600',
    platform: '微信视频号',
    description: '女频极致虐恋，全网破千万播放切片累计达24支'
  },
  {
    id: 'acc-mt-02',
    name: '蜜糖-心动回响社',
    theaterId: 'theater-mitang',
    theaterName: '蜜糖剧场',
    tier: '腰部主力',
    avatarBg: 'bg-gradient-to-br from-pink-400 to-rose-700',
    platform: '微信视频号',
    description: '双向奔赴情感戏，女性充值率达18.5%'
  },
  {
    id: 'acc-mt-03',
    name: '蜜糖-民国烟雨情',
    theaterId: 'theater-mitang',
    theaterName: '蜜糖剧场',
    tier: '新锐测试',
    avatarBg: 'bg-gradient-to-br from-fuchsia-400 to-pink-500',
    platform: '微信视频号',
    description: '民国复古风短剧，视觉质感出众'
  },

  // 9. 银河剧场旗下 (2个)
  {
    id: 'acc-yh-01',
    name: '银河-末世觉醒录',
    theaterId: 'theater-yinhe',
    theaterName: '银河剧场',
    tier: '腰部主力',
    avatarBg: 'bg-gradient-to-br from-cyan-500 to-blue-700',
    platform: '微信视频号',
    description: '科幻末世异能短剧，受众年轻化，点赞率高达8.2%'
  },
  {
    id: 'acc-yh-02',
    name: '银河-修真都市行',
    theaterId: 'theater-yinhe',
    theaterName: '银河剧场',
    tier: '腰部主力',
    avatarBg: 'bg-gradient-to-br from-sky-500 to-indigo-700',
    platform: '微信视频号',
    description: '都市修真题材，节奏极其明快'
  },

  // 10. 番茄剧场旗下 (3个)
  {
    id: 'acc-fq-01',
    name: '番茄-全民追更榜',
    theaterId: 'theater-fanqie',
    theaterName: '番茄剧场',
    tier: '头部爆款',
    avatarBg: 'bg-gradient-to-br from-orange-500 to-amber-600',
    platform: '微信视频号',
    description: '番茄原著大IP，粉丝210W，矩阵全网综合流量第一'
  },
  {
    id: 'acc-fq-02',
    name: '番茄-爽剧大本营',
    theaterId: 'theater-fanqie',
    theaterName: '番茄剧场',
    tier: '腰部主力',
    avatarBg: 'bg-gradient-to-br from-amber-500 to-orange-700',
    platform: '微信视频号',
    description: '高频日更3部剧，累计分发播放突破8000万'
  },
  {
    id: 'acc-fq-03',
    name: '番茄-新剧抢先看',
    theaterId: 'theater-fanqie',
    theaterName: '番茄剧场',
    tier: '新锐测试',
    avatarBg: 'bg-gradient-to-br from-orange-400 to-red-600',
    platform: '微信视频号',
    description: '新剧试水首播号，评测用户反馈与跳出率'
  },

  // 11. 容量剧场旗下 (3个)
  {
    id: 'acc-rl-01',
    name: '容量-精品短剧坊',
    theaterId: 'theater-rongliang',
    theaterName: '容量剧场',
    tier: '头部爆款',
    avatarBg: 'bg-gradient-to-br from-lime-500 to-emerald-700',
    platform: '微信视频号',
    description: '电影级调色与打光，单集平均完播率达31.4%'
  },
  {
    id: 'acc-rl-02',
    name: '容量-国风古韵社',
    theaterId: 'theater-rongliang',
    theaterName: '容量剧场',
    tier: '腰部主力',
    avatarBg: 'bg-gradient-to-br from-emerald-500 to-lime-600',
    platform: '微信视频号',
    description: '主打古装权谋短剧，高完播率与高私域沉淀'
  },
  {
    id: 'acc-rl-03',
    name: '容量-悬疑深渊',
    theaterId: 'theater-rongliang',
    theaterName: '容量剧场',
    tier: '新锐测试',
    avatarBg: 'bg-gradient-to-br from-green-500 to-teal-700',
    platform: '微信视频号',
    description: '电影感硬核悬疑，探索引流新变现模式'
  },

  // 12. 友宝剧场旗下 (3个)
  {
    id: 'acc-yb-01',
    name: '友宝-家和万事兴',
    theaterId: 'theater-youbao',
    theaterName: '友宝剧场',
    tier: '腰部主力',
    avatarBg: 'bg-gradient-to-br from-amber-600 to-yellow-700',
    platform: '微信视频号',
    description: '中老年家庭矛盾与真情故事，完播稳定，长尾效应持久'
  },
  {
    id: 'acc-yb-02',
    name: '友宝-岁月中转站',
    theaterId: 'theater-youbao',
    theaterName: '友宝剧场',
    tier: '腰部主力',
    avatarBg: 'bg-gradient-to-br from-yellow-600 to-amber-700',
    platform: '微信视频号',
    description: '年代回忆杀短剧，深受45岁以上群体喜爱'
  },
  {
    id: 'acc-yb-03',
    name: '友宝-夕阳红追剧社',
    theaterId: 'theater-youbao',
    theaterName: '友宝剧场',
    tier: '限流观察',
    avatarBg: 'bg-gradient-to-br from-stone-500 to-amber-900',
    platform: '微信视频号',
    description: '封面大字夸张提示封面优化，正在逐步调整'
  },

  // 13. 华夏剧场旗下 (3个)
  {
    id: 'acc-hx-01',
    name: '华夏-盛世传奇社',
    theaterId: 'theater-huaxia',
    theaterName: '华夏剧场',
    tier: '头部爆款',
    avatarBg: 'bg-gradient-to-br from-slate-600 to-slate-800',
    platform: '微信视频号',
    description: '大宋商海风云与家国情怀，官方推荐流扶持高'
  },
  {
    id: 'acc-hx-02',
    name: '华夏-古风英雄传',
    theaterId: 'theater-huaxia',
    theaterName: '华夏剧场',
    tier: '腰部主力',
    avatarBg: 'bg-gradient-to-br from-slate-500 to-zinc-700',
    platform: '微信视频号',
    description: '武侠江湖与传统美德短剧，粉丝忠诚度极高'
  },
  {
    id: 'acc-hx-03',
    name: '华夏-新国潮影话',
    theaterId: 'theater-huaxia',
    theaterName: '华夏剧场',
    tier: '新锐测试',
    avatarBg: 'bg-gradient-to-br from-zinc-500 to-slate-700',
    platform: '微信视频号',
    description: '传统文化二创短剧，完播率高于大盘均值20%'
  }
];

// ==========================================
// 3. 剧目切片片库 (剧名-n 格式规范)
// ==========================================
const DRAMA_CATALOG = [
  { title: '隐龙归来', episodes: 5, category: '战神逆袭', baseViews: 85000 },
  { title: '真千金的绝地逆袭', episodes: 5, category: '豪门打脸', baseViews: 92000 },
  { title: '顾总请自重', episodes: 4, category: '都市甜宠', baseViews: 76000 },
  { title: '长生万古诀', episodes: 5, category: '玄幻修真', baseViews: 68000 },
  { title: '狂飙天王', episodes: 4, category: '热血商战', baseViews: 98000 },
  { title: '替嫁娇妻是神医', episodes: 5, category: '女频打脸', baseViews: 82000 },
  { title: '风起大江东去', episodes: 4, category: '年代传奇', baseViews: 54000 },
  { title: '龙王殿前谁争锋', episodes: 5, category: '战神爽剧', baseViews: 88000 },
  { title: '萌宝寻爹记', episodes: 4, category: '家庭亲子', baseViews: 95000 },
  { title: '重回1990当首富', episodes: 5, category: '年代经商', baseViews: 79000 },
  { title: '夜幕下的法医', episodes: 4, category: '悬疑反转', baseViews: 62000 },
  { title: '天降百亿遗产', episodes: 5, category: '都市爆笑', baseViews: 73000 },
  { title: '大宋提刑录', episodes: 4, category: '古风破案', baseViews: 58000 },
  { title: '掌中雀的复仇', episodes: 5, category: '民国虐恋', baseViews: 81000 }
];

// 暂行标签与用户提供文案
const ALL_SIMPLIFIED_REASONS = (Object.keys(OFFICIAL_OPTIMIZATION_DEFINITIONS) as SimplifiedOptimizationReason[]).filter(tag=>tag!=='待归类');

// ==========================================
// 4. 数据生成器 (模拟1个月全真实数据)
// ==========================================
// 生成 2026-10-01 到 2026-10-31 的日期序列
const DATES: string[] = [];
for (let d = 1; d <= 31; d++) {
  const dayStr = d < 10 ? `0${d}` : `${d}`;
  DATES.push(`2026-10-${dayStr}`);
}

// 4.1 生成每日账号收益 (RevenueRecord[])
// 规则：账号、剧场、日期、金额
export const HISTORICAL_REVENUE: RevenueRecord[] = [];
let revenueIdCounter = 1;

ACCOUNTS.forEach(acc => {
  // 基础收益系数根据账号评级调整
  let baseDailyMin = 1800;
  let baseDailyMax = 4200;
  if (acc.tier === '头部爆款') {
    baseDailyMin = 5000;
    baseDailyMax = 12000;
  } else if (acc.tier === '新锐测试') {
    baseDailyMin = 800;
    baseDailyMax = 2200;
  } else if (acc.tier === '限流观察') {
    baseDailyMin = 300;
    baseDailyMax = 1100;
  }

  DATES.forEach((date, dayIdx) => {
    // 周末波峰波谷模拟
    const dayOfWeek = (dayIdx + 3) % 7; // 10-01是周四
    const isWeekend = dayOfWeek === 5 || dayOfWeek === 6;
    const weekendMultiplier = isWeekend ? 1.35 : 1.0;
    
    // 随机微扰
    const seed = (acc.id.charCodeAt(5) || 7) + dayIdx * 13;
    const rand = ((seed % 100) / 100);
    const dailyAmount = Math.round((baseDailyMin + (baseDailyMax - baseDailyMin) * rand) * weekendMultiplier);

    HISTORICAL_REVENUE.push({
      id: `rev-${revenueIdCounter++}`,
      accountId: acc.id,
      accountName: acc.name,
      theater: acc.theaterName,
      date,
      amount: dailyAmount
    });
  });
});

// 4.2 生成账号每日总计流量 (AccountDailyTraffic[])
// 规则：账号、剧场、指定日期的总计流量（关注、播放量、爱心、评论）
export const HISTORICAL_TRAFFIC: AccountDailyTraffic[] = [];
let trafficIdCounter = 1;

ACCOUNTS.forEach(acc => {
  let baseViewsMin = 30000;
  let baseViewsMax = 90000;
  if (acc.tier === '头部爆款') {
    baseViewsMin = 120000;
    baseViewsMax = 320000;
  } else if (acc.tier === '新锐测试') {
    baseViewsMin = 15000;
    baseViewsMax = 45000;
  } else if (acc.tier === '限流观察') {
    baseViewsMin = 8000;
    baseViewsMax = 25000;
  }

  DATES.forEach((date, dayIdx) => {
    const dayOfWeek = (dayIdx + 3) % 7;
    const isWeekend = dayOfWeek === 5 || dayOfWeek === 6;
    const weekendMultiplier = isWeekend ? 1.3 : 1.0;

    const seed = (acc.id.charCodeAt(6) || 9) + dayIdx * 17;
    const rand = ((seed % 100) / 100);
    const views = Math.round((baseViewsMin + (baseViewsMax - baseViewsMin) * rand) * weekendMultiplier);

    const follows = Math.round(views * (0.008 + rand * 0.007)); // 0.8% - 1.5% 转化
    const hearts = Math.round(views * (0.045 + rand * 0.035)); // 4.5% - 8% 点赞
    const comments = Math.round(views * (0.003 + rand * 0.004)); // 0.3% - 0.7% 评论

    HISTORICAL_TRAFFIC.push({
      id: `traf-${trafficIdCounter++}`,
      accountId: acc.id,
      accountName: acc.name,
      theater: acc.theaterName,
      date,
      follows,
      views,
      hearts,
      comments
    });
  });
});

// 4.3 生成视频流量情况与优化分析
// 严格业务约束：
// 1个账号在1个发布时间只发1条视频；
// 视频文件名规范统一为「剧名-n」；
// 1条视频只会对应1个优化；
// 优化原因使用平台7条真实固定官方通知。
export const VIDEO_TRAFFIC_DATA: VideoTrafficItem[] = [];
export const OPTIMIZATION_RECORDS: OptimizationRecord[] = [];

let videoIdCounter = 1;
let optIdCounter = 1;

// 发布时间点池 (同一账号不会在同一时分重复发布)
const TIME_SLOTS = ['07:30', '10:15', '12:30', '14:20', '17:45', '19:15', '20:30', '21:45', '22:30'];

// 为每个账号生成发布视频
ACCOUNTS.forEach((acc, accIdx) => {
  // 根据评级分配近一个月的视频数量 (头部发片更多)
  const videoCount = acc.tier === '头部爆款' ? 24 : acc.tier === '腰部主力' ? 18 : acc.tier === '新锐测试' ? 12 : 8;

  // 账号对应的优化概率：限流观察号高达 40%，新锐测试 15%，腰部主力 8%，头部爆款 4%
  const optProbability = acc.tier === '限流观察' ? 0.40 : acc.tier === '新锐测试' ? 0.15 : acc.tier === '腰部主力' ? 0.08 : 0.04;

  for (let v = 0; v < videoCount; v++) {
    // 日期分布在后半月较多（近期）
    const dayNum = Math.min(31, Math.max(1, 31 - Math.floor(v * 1.25)));
    const dayStr = dayNum < 10 ? `0${dayNum}` : `${dayNum}`;
    const dateStr = `2026-10-${dayStr}`;
    const timeSlot = TIME_SLOTS[(accIdx + v) % TIME_SLOTS.length];
    const publishTime = `${dateStr} ${timeSlot}`;

    // 选择剧目与集数，规范严格统一为「剧名-n」
    const drama = DRAMA_CATALOG[(accIdx * 3 + v) % DRAMA_CATALOG.length];
    const episodeNum = (v % drama.episodes) + 1;
    const episodeStr = episodeNum < 10 ? `0${episodeNum}` : `${episodeNum}`;
    const fileName = `${drama.title}-${episodeStr}`;

    // 播放量与完播指标
    const rankSeed = (acc.tier === '头部爆款' ? 1.8 : acc.tier === '腰部主力' ? 1.0 : acc.tier === '新锐测试' ? 0.6 : 0.35);
    const epDrop = 1.0 - (episodeNum - 1) * 0.08; // 随着集数略微有递减留存
    const randF = 0.75 + (((v * 19 + accIdx * 7) % 50) / 100);

    const views = Math.round(drama.baseViews * rankSeed * epDrop * randF);
    const completionRate = Number((18 + ((v * 13 + accIdx) % 18) * 0.8).toFixed(1));
    const hearts = Math.round(views * (0.04 + ((v * 7) % 40) * 0.001));
    const comments = Math.round(views * (0.004 + ((v * 3) % 20) * 0.0003));
    const shares = Math.round(views * (0.002 + ((v * 5) % 15) * 0.0002));
    const thumbsUp = Math.round(hearts * 1.15);

    // 判断是否被平台优化 (1条视频至多1个优化)
    const isOptimized = ((v + accIdx * 3) % 100) < (optProbability * 100);
    let optimizationRecord: OptimizationRecord | undefined = undefined;

    if (isOptimized) {
      const reasonIdx = (accIdx + v) % ALL_SIMPLIFIED_REASONS.length;
      const simplifiedReason = ALL_SIMPLIFIED_REASONS[reasonIdx];
      const officialDef = OFFICIAL_OPTIMIZATION_DEFINITIONS[simplifiedReason];

      optimizationRecord = {
        id: `opt-rec-${optIdCounter++}`,
        accountId: acc.id,
        accountName: acc.name,
        theater: acc.theaterName,
        publishTime,
        fileName,
        dramaTitle: drama.title,
        episodeNumber: episodeNum,
        simplifiedReason,
        reasonType: simplifiedReason,
        officialNotice: officialDef.officialNotice,
        severity: officialDef.severity,
        impactNotice: officialDef.impactNotice,
        detectedDate: dateStr,
        viewsAtDetection: views
      };

      OPTIMIZATION_RECORDS.push(optimizationRecord);
    }

    VIDEO_TRAFFIC_DATA.push({
      id: `vid-${videoIdCounter++}`,
      accountId: acc.id,
      accountName: acc.name,
      theater: acc.theaterName,
      publishTime,
      views,
      completionRate,
      hearts,
      comments,
      shares,
      thumbsUp,
      fileName,
      dramaTitle: drama.title,
      episodeNumber: episodeNum,
      hasOptimization: isOptimized,
      optimization: optimizationRecord
    });
  }
});

// 按发布时间降序排序
VIDEO_TRAFFIC_DATA.sort((a, b) => b.publishTime.localeCompare(a.publishTime));
OPTIMIZATION_RECORDS.sort((a, b) => b.publishTime.localeCompare(a.publishTime));

// ==========================================
// 5. 核心查询与聚合计算函数
// ==========================================

// 5.1 获取选定日期范围 (针对 2026-10-31 作为最新日期)
export function getDateFilterBoundary(range: 'yesterday' | '7days' | '30days' | 'all'): string {
  if (range === 'yesterday') return '2026-10-30'; // 模拟以 10-31 为今天，昨天即 10-30
  if (range === '7days') return '2026-10-25';
  if (range === '30days') return '2026-10-01';
  return '2026-10-01';
}

// 5.2 综合 KPI 概览汇总
export function getKPISummary(
  theaterFilter: string = 'ALL',
  accountFilter: string = 'ALL',
  dateRange: 'yesterday' | '7days' | '30days' | 'all' = '30days'
) {
  const boundary = getDateFilterBoundary(dateRange);

  // 1. 收益
  const filteredRev = HISTORICAL_REVENUE.filter(r => {
    if (theaterFilter !== 'ALL' && r.theater !== theaterFilter) return false;
    if (accountFilter !== 'ALL' && r.accountId !== accountFilter) return false;
    if (dateRange === 'yesterday') return r.date === boundary;
    return r.date >= boundary;
  });
  const totalRevenue = filteredRev.reduce((sum, r) => sum + r.amount, 0);

  // 2. 账号流量
  const filteredTraf = HISTORICAL_TRAFFIC.filter(t => {
    if (theaterFilter !== 'ALL' && t.theater !== theaterFilter) return false;
    if (accountFilter !== 'ALL' && t.accountId !== accountFilter) return false;
    if (dateRange === 'yesterday') return t.date === boundary;
    return t.date >= boundary;
  });
  const totalViews = filteredTraf.reduce((sum, t) => sum + t.views, 0);
  const totalFollows = filteredTraf.reduce((sum, t) => sum + t.follows, 0);
  const totalHearts = filteredTraf.reduce((sum, t) => sum + t.hearts, 0);
  const totalComments = filteredTraf.reduce((sum, t) => sum + t.comments, 0);

  // 3. 视频与优化
  const filteredVids = VIDEO_TRAFFIC_DATA.filter(v => {
    if (theaterFilter !== 'ALL' && v.theater !== theaterFilter) return false;
    if (accountFilter !== 'ALL' && v.accountId !== accountFilter) return false;
    const vDate = v.publishTime.slice(0, 10);
    if (dateRange === 'yesterday') return vDate === boundary;
    return vDate >= boundary;
  });
  const totalVideos = filteredVids.length;
  const optimizedVideos = filteredVids.filter(v => v.hasOptimization).length;
  const overallOptRate = totalVideos > 0 ? Number(((optimizedVideos / totalVideos) * 100).toFixed(1)) : 0;

  // 4. 万播产值 (RPM)
  const rpm = totalViews > 0 ? Number(((totalRevenue / totalViews) * 10000).toFixed(1)) : 0;

  return {
    totalRevenue,
    totalViews,
    totalFollows,
    totalHearts,
    totalComments,
    totalVideos,
    optimizedVideos,
    overallOptRate,
    rpm
  };
}

// 5.3 过滤收益明细
export function filterRevenue(
  theaterFilter: string = 'ALL',
  accountFilter: string = 'ALL',
  dateRange: 'yesterday' | '7days' | '30days' | 'all' = '30days'
) {
  const boundary = getDateFilterBoundary(dateRange);
  return HISTORICAL_REVENUE.filter(r => {
    if (theaterFilter !== 'ALL' && r.theater !== theaterFilter) return false;
    if (accountFilter !== 'ALL' && r.accountId !== accountFilter) return false;
    if (dateRange === 'yesterday') return r.date === boundary;
    return r.date >= boundary;
  });
}

// 5.4 过滤流量明细
export function filterTraffic(
  theaterFilter: string = 'ALL',
  accountFilter: string = 'ALL',
  dateRange: 'yesterday' | '7days' | '30days' | 'all' = '30days'
) {
  const boundary = getDateFilterBoundary(dateRange);
  return HISTORICAL_TRAFFIC.filter(t => {
    if (theaterFilter !== 'ALL' && t.theater !== theaterFilter) return false;
    if (accountFilter !== 'ALL' && t.accountId !== accountFilter) return false;
    if (dateRange === 'yesterday') return t.date === boundary;
    return t.date >= boundary;
  });
}

// 5.5 过滤视频列表
export function filterVideos(
  theaterFilter: string = 'ALL',
  accountFilter: string = 'ALL',
  dateRange: 'yesterday' | '7days' | '30days' | 'all' = '30days',
  searchQuery: string = '',
  onlyOptimized: boolean = false
) {
  const boundary = getDateFilterBoundary(dateRange);
  const q = searchQuery.trim().toLowerCase();

  return VIDEO_TRAFFIC_DATA.filter(v => {
    if (theaterFilter !== 'ALL' && v.theater !== theaterFilter) return false;
    if (accountFilter !== 'ALL' && v.accountId !== accountFilter) return false;

    const vDate = v.publishTime.slice(0, 10);
    if (dateRange === 'yesterday') {
      if (vDate !== boundary) return false;
    } else {
      if (vDate < boundary) return false;
    }

    if (onlyOptimized && !v.hasOptimization) return false;

    if (q) {
      const matchFile = v.fileName.toLowerCase().includes(q);
      const matchDrama = v.dramaTitle.toLowerCase().includes(q);
      const matchAccount = v.accountName.toLowerCase().includes(q);
      const matchTheater = v.theater.toLowerCase().includes(q);
      if (!matchFile && !matchDrama && !matchAccount && !matchTheater) return false;
    }

    return true;
  });
}

// 5.6 账号经营排名 (以账号为单位统计收益、播放、发片、优化率)
export interface AccountRankingItem {
  account: AccountInfo;
  revenue: number;
  views: number;
  follows: number;
  hearts: number;
  comments: number;
  videoCount: number;
  optimizedCount: number;
  optimizationRate: number;
  rpm: number;
}

export function getAccountRankings(
  theaterFilter: string = 'ALL',
  dateRange: 'yesterday' | '7days' | '30days' | 'all' = '30days',
  sortBy: 'revenue' | 'views' | 'optimizationRate' | 'videoCount' = 'revenue'
): AccountRankingItem[] {
  const boundary = getDateFilterBoundary(dateRange);

  const matchedAccounts = theaterFilter === 'ALL' 
    ? ACCOUNTS 
    : ACCOUNTS.filter(a => a.theaterName === theaterFilter);

  const results: AccountRankingItem[] = matchedAccounts.map(account => {
    // 收益
    const revs = HISTORICAL_REVENUE.filter(r => {
      if (r.accountId !== account.id) return false;
      if (dateRange === 'yesterday') return r.date === boundary;
      return r.date >= boundary;
    });
    const revenue = revs.reduce((sum, r) => sum + r.amount, 0);

    // 流量
    const trafs = HISTORICAL_TRAFFIC.filter(t => {
      if (t.accountId !== account.id) return false;
      if (dateRange === 'yesterday') return t.date === boundary;
      return t.date >= boundary;
    });
    const views = trafs.reduce((sum, t) => sum + t.views, 0);
    const follows = trafs.reduce((sum, t) => sum + t.follows, 0);
    const hearts = trafs.reduce((sum, t) => sum + t.hearts, 0);
    const comments = trafs.reduce((sum, t) => sum + t.comments, 0);

    // 视频
    const vids = VIDEO_TRAFFIC_DATA.filter(v => {
      if (v.accountId !== account.id) return false;
      const vDate = v.publishTime.slice(0, 10);
      if (dateRange === 'yesterday') return vDate === boundary;
      return vDate >= boundary;
    });
    const videoCount = vids.length;
    const optimizedCount = vids.filter(v => v.hasOptimization).length;
    const optimizationRate = videoCount > 0 ? Number(((optimizedCount / videoCount) * 100).toFixed(1)) : 0;
    const rpm = views > 0 ? Number(((revenue / views) * 10000).toFixed(1)) : 0;

    return {
      account,
      revenue,
      views,
      follows,
      hearts,
      comments,
      videoCount,
      optimizedCount,
      optimizationRate,
      rpm
    };
  });

  return results.sort((a, b) => {
    if (sortBy === 'revenue') return b.revenue - a.revenue;
    if (sortBy === 'views') return b.views - a.views;
    if (sortBy === 'optimizationRate') return b.optimizationRate - a.optimizationRate;
    return b.videoCount - a.videoCount;
  });
}

// 5.7 账号发视频优化分析 (以账号为核心，分析优化率、原因构成与风险等级)
export function getAccountOptimizationStats(
  theaterFilter: string = 'ALL',
  dateRange: 'yesterday' | '7days' | '30days' | 'all' = '30days'
): AccountOptimizationStat[] {
  const boundary = getDateFilterBoundary(dateRange);

  const matchedAccounts = theaterFilter === 'ALL' 
    ? ACCOUNTS 
    : ACCOUNTS.filter(a => a.theaterName === theaterFilter);

  return matchedAccounts.map(account => {
    const vids = VIDEO_TRAFFIC_DATA.filter(v => {
      if (v.accountId !== account.id) return false;
      const vDate = v.publishTime.slice(0, 10);
      if (dateRange === 'yesterday') return vDate === boundary;
      return vDate >= boundary;
    });

    const totalVideos = vids.length;
    const optimizedVideosList = vids.filter(v => v.hasOptimization);
    const optimizedVideos = optimizedVideosList.length;
    const optimizationRate = totalVideos > 0 ? Number(((optimizedVideos / totalVideos) * 100).toFixed(1)) : 0;
    const totalViews = vids.reduce((sum, v) => sum + v.views, 0);
    const impactedViews = optimizedVideosList.reduce((sum, v) => sum + v.views, 0);

    const reasonCounts = createOptimizationReasonCounts();

    optimizedVideosList.forEach(v => {
      if (v.optimization?.simplifiedReason) {
        reasonCounts[v.optimization.simplifiedReason] = (reasonCounts[v.optimization.simplifiedReason] || 0) + 1;
      }
    });

    let topReason: SimplifiedOptimizationReason | undefined = undefined;
    let maxReasonCount = 0;
    ALL_SIMPLIFIED_REASONS.forEach(r => {
      if (reasonCounts[r] > maxReasonCount) {
        maxReasonCount = reasonCounts[r];
        topReason = r;
      }
    });

    const healthLevel: 'healthy' | 'warning' | 'critical' = 
      optimizationRate > 15 ? 'critical' : optimizationRate >= 5 ? 'warning' : 'healthy';

    const latestOptimizedDate = optimizedVideosList.length > 0 
      ? optimizedVideosList[0].publishTime.slice(0, 10) 
      : undefined;

    return {
      accountId: account.id,
      accountName: account.name,
      theater: account.theaterName,
      tier: account.tier,
      totalVideos,
      optimizedVideos,
      optimizationRate,
      totalViews,
      impactedViews,
      reasonCounts,
      topReason,
      healthLevel,
      latestOptimizedDate
    };
  }).sort((a, b) => b.optimizationRate - a.optimizationRate);
}

// 5.8 暂行作品分析标签分布统计
export function getOptimizationReasonDistribution(
  theaterFilter: string = 'ALL',
  accountFilter: string = 'ALL',
  dateRange: 'yesterday' | '7days' | '30days' | 'all' = '30days'
) {
  const boundary = getDateFilterBoundary(dateRange);

  const filteredOpts = OPTIMIZATION_RECORDS.filter(o => {
    if (theaterFilter !== 'ALL' && o.theater !== theaterFilter) return false;
    if (accountFilter !== 'ALL' && o.accountId !== accountFilter) return false;
    if (dateRange === 'yesterday') return o.detectedDate === boundary;
    return o.detectedDate >= boundary;
  });

  const counts = createOptimizationReasonCounts();

  filteredOpts.forEach(o => {
    if (counts[o.simplifiedReason] !== undefined) {
      counts[o.simplifiedReason]++;
    }
  });

  const total = filteredOpts.length;

  return ALL_SIMPLIFIED_REASONS.map(reason => {
    const count = counts[reason] || 0;
    const percentage = total > 0 ? Math.round((count / total) * 100) : 0;
    const def = OFFICIAL_OPTIMIZATION_DEFINITIONS[reason];
    return {
      reason,
      count,
      percentage,
      severity: def.severity,
      officialNotice: def.officialNotice,
      impactNotice: def.impactNotice,
      shortTag: def.shortTag
    };
  }).sort((a, b) => b.count - a.count);
}

// 5.9 每日优化趋势统计 (按天统计优化量与发片量)
export interface DailyOptimizationTrend {
  date: string;
  totalPublished: number;
  totalOptimized: number;
  rate: number;
}

export function getDailyOptimizationTrends(
  theaterFilter: string = 'ALL',
  accountFilter: string = 'ALL',
  dateRange: 'yesterday' | '7days' | '30days' | 'all' = '30days'
): DailyOptimizationTrend[] {
  const boundary = getDateFilterBoundary(dateRange);

  const days = DATES.filter(d => (dateRange === 'yesterday' ? d === boundary : d >= boundary));

  return days.map(date => {
    const vids = VIDEO_TRAFFIC_DATA.filter(v => {
      if (theaterFilter !== 'ALL' && v.theater !== theaterFilter) return false;
      if (accountFilter !== 'ALL' && v.accountId !== accountFilter) return false;
      return v.publishTime.slice(0, 10) === date;
    });

    const totalPublished = vids.length;
    const totalOptimized = vids.filter(v => v.hasOptimization).length;
    const rate = totalPublished > 0 ? Number(((totalOptimized / totalPublished) * 100).toFixed(1)) : 0;

    return {
      date,
      totalPublished,
      totalOptimized,
      rate
    };
  });
}

// 兼容老模块类型
export interface DramaAnalysisItem {
  dramaTitle: string;
  category: string;
  totalEpisodes: number;
  totalViews: number;
  episodes: Array<{
    episode: number;
    views: number;
    retentionRate: number;
    dropOff: number;
    hasHook: boolean;
  }>;
  totalOptimizations: number;
}

export interface TimeSlotPerformance {
  slot: string;
  count: number;
  avgViews: number;
  avgCompletion: number;
  isPeak: boolean;
}

export function getDramaAnalysis(_theater?: string, _account?: string, _dateRange?: string): DramaAnalysisItem[] {
  return DRAMA_CATALOG.map(d => ({
    dramaTitle: d.title,
    category: d.category,
    totalEpisodes: d.episodes,
    totalViews: d.baseViews * 5,
    episodes: Array.from({ length: d.episodes }).map((_, i) => ({
      episode: i + 1,
      views: Math.round(d.baseViews * (1 - i * 0.1)),
      retentionRate: Math.max(15, 100 - i * 18),
      dropOff: i === 0 ? 0 : 18,
      hasHook: i === 0 || i === 4
    })),
    totalOptimizations: 2
  }));
}

export function getTimeSlotPerformance(_theater?: string, _account?: string, _dateRange?: string): TimeSlotPerformance[] {
  return [
    { slot: '12:00-13:00', count: 45, avgViews: 65000, avgCompletion: 24.5, isPeak: true },
    { slot: '18:00-19:00', count: 58, avgViews: 82000, avgCompletion: 26.2, isPeak: true },
    { slot: '21:00-22:00', count: 62, avgViews: 94000, avgCompletion: 28.0, isPeak: true }
  ];
}
