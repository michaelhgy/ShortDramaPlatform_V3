/**
 * 短剧推广运营驾驶舱 - 真实业务数据契约
 * 
 * 核心规则与业务约束：
 * 1. 收益：账号、剧场、日期、金额
 * 2. 账号流量情况：账号、剧场、指定日期的总计流量（关注、播放量、爱心、评论）
 * 3. 账号的视频流量情况：账号、剧场、发布时间（具体时分）、播放量、完播率、爱心、评论、转发、点赞、文件名（剧名-n）
 * 4. 优化分析：账号、剧场、发布时间、作品分析（优化原因、具体对应的视频）
 * 5. 硬约束：
 *    - 1个账号只能绑定1个剧场，1个剧场可以绑定很多账号（十几个剧场，30多个账号）；
 *    - 1条视频只会对应1个优化；
 *    - 1个账号在1个发布时间只会发布1条视频（账号 + 发布时间 构成自然联合主键）；
 *    - 作品分析原文通过用户暂行规则映射标签，无法匹配时保留原文并标为待归类；
 *    - 优化无需复杂处理流，重点是按天/日期区间统计优化数据、优化率及受影响视频；
 *    - 视频文件名规范统一为「剧名-n」。
 */

export interface TheaterInfo {
  id: string;
  name: string;
  code: string;
  description: string;
  badgeColor: string;
  accentBg: string;
}

export type RevenueAccountTier = 'SS' | 'S' | 'A' | 'B' | 'C' | '待评';
/** Old literals remain compatible with the unmounted prototype data only. */
export type AccountPerformanceTier = RevenueAccountTier | '头部爆款' | '腰部主力' | '新锐测试' | '限流观察';

export interface AccountRevenueRating {
  tier: RevenueAccountTier;
  phase: '试投' | '起量' | '爆发' | '平稳' | '回落' | '尾量' | '停用' | '待判';
  updateStatus: '待更新' | '已更新' | '查询失败';
  confirmedThrough: string | null;
  lastQueryAt: string | null;
  updateReason: string;
  reason: string;
  phaseReason: string;
  lastValid: { date: string; amount: number } | null;
  peak: { date: string; amount: number } | null;
  recordedTotal: number | null;
  recentDays: Array<{ date: string; amount: number | null; state: 'record' | 'failed' | 'missing' | 'partial' }>;
  recentTotal: number;
  recentComplete: boolean;
  reviewReason: string | null;
}

export interface AccountInfo {
  avatarUrl?: string;
  channelId?: string;
  id: string;
  name: string;
  theaterId: string;
  theaterName: string; // 严格1:1绑定此剧场
  tier: AccountPerformanceTier;
  rating?: AccountRevenueRating;
  businessStatus?: string;
  loginStatus?: string;
  loginCheckedAt?: string;
  /** Account totals, independent of the dashboard date filter; unknown stays null. */
  videoTotal?: number | null;
  followerTotal?: number | null;
  avatarBg: string;
  platform: string;
  description: string;
}

// 1. 收益 (账号、剧场、日期、金额)
export interface RevenueRecord {
  periodType?: string;
  periodStart?: string;
  id: string;
  accountId: string;
  accountName: string;
  theater: string;
  date: string; // YYYY-MM-DD
  amount: number; // 金额 (元)
}

// 2. 账号指定日期的总计流量 (账号、剧场、指定日期的总计流量：关注、播放量、爱心、评论)
export interface AccountDailyTraffic {
  id: string;
  accountId: string;
  accountName: string;
  theater: string;
  date: string; // YYYY-MM-DD
  follows: number; // 净增关注
  views: number; // 总播放量
  hearts: number; // 爱心
  comments: number; // 评论
}

/** Every collected account-day field, including partial observations for export. */
export interface AccountDailyTrafficDetail {
  id: string;
  accountId: string;
  accountName: string;
  channelId: string;
  theater: string;
  date: string;
  views: number | null;
  followerTotal: number | null;
  followsAdded: number | null;
  follows: number | null;
  followsReduced: number | null;
  hearts: number | null;
  thumbsUp: number | null;
  comments: number | null;
  shares: number | null;
}

// User-provided provisional analysis-to-tag rules; originals are stored independently.
import type { SimplifiedOptimizationReason, OptimizationSeverity } from './optimizationNotices.ts';
export type { SimplifiedOptimizationReason, OptimizationReasonType, OptimizationSeverity, OfficialNoticeDefinition } from './optimizationNotices.ts';
export { OFFICIAL_OPTIMIZATION_DEFINITIONS } from './optimizationNotices.ts';

// 4. 优化分析 (账号、剧场、发布时间、作品分析[优化原因、具体对应的视频])
export interface OptimizationRecord {
  id: string;
  accountId: string;
  accountName: string;
  theater: string;
  publishTime: string; // 具体发布时间 (YYYY-MM-DD HH:mm)
  fileName: string; // 格式必须为 剧名-n
  dramaTitle: string;
  episodeNumber: number;
  simplifiedReason: SimplifiedOptimizationReason; // 简化原因
  reasonType: SimplifiedOptimizationReason; // 兼容字段
  officialNotice: string; // 原始作品分析文本，不能用分类模板或影响摘要覆盖
  severity: OptimizationSeverity;
  impactNotice: string; // 平台处理结果通知
  detectedDate: string; // 优化识别日期 (YYYY-MM-DD)
  viewsAtDetection: number; // 触发时播放量
}

// 3. 账号的视频流量情况
// (账号、剧场、发布时间(具体时分)、播放量、完播率、爱心、评论、转发、点赞、文件名(剧名-n))
export interface VideoTrafficItem {
  videoUrl?: string;
  videoDuration?: number;
  fallbackCoverUrl?: string;
  statsCollectedAt?: string;
  statsDate?: string;
  statsState?: string;
  dramaId?: string;
  coverUrl?: string;
  avatarUrl?: string;
  id: string;
  accountId: string;
  accountName: string;
  theater: string;
  publishTime: string; // 具体时分，例如 "2026-10-30 18:30"
  views: number;
  completionRate: number; // 完播率 (百分比数值，如 24.5 代表 24.5%)
  hearts: number; // 爱心
  comments: number; // 评论
  shares: number; // 转发
  thumbsUp: number; // 点赞
  fileName: string; // 已关联发布记录的实际文件名；未关联显示作品ID
  dramaTitle: string; // "隐龙归来"
  episodeNumber: number; // 1
  hasOptimization: boolean; // 是否存在优化记录 (1条视频最多1个优化)
  optimization?: OptimizationRecord; // 关联的优化分析
}

// 账号发视频优化综合统计指标 (以账号为单位)
export interface AccountOptimizationStat {
  accountId: string;
  accountName: string;
  theater: string;
  tier: AccountPerformanceTier;
  totalVideos: number;
  optimizedVideos: number;
  optimizationKnown?: boolean;
  optimizationRate: number | null; // 百分比，如 8.5
  totalViews: number;
  hasTraffic?: boolean;
  impactedViews: number;
  reasonCounts: Record<SimplifiedOptimizationReason, number>;
  topReason?: SimplifiedOptimizationReason;
  healthLevel: 'healthy' | 'warning' | 'critical' | 'unknown'; // ≤20% 健康, >20%且<50% 关注, ≥50% 高危
  latestOptimizedDate?: string;
}

// 筛选条件聚合
export interface FilterState {
  selectedTheater: string; // 'ALL' or theater name
  selectedAccountId: string; // 'ALL' or accountId
  dateRange: 'yesterday' | '7days' | '30days' | 'all';
  searchQuery: string; // 搜文件名(剧名-n)或剧名或账号
  onlyOptimized: boolean; // 仅看有优化预警的
  reasonFilter?: SimplifiedOptimizationReason | 'ALL';
}

export type OptimizationStatus = '待处置' | '处置中' | '已重剪替换' | '已下架止损' | '已复盘闭环';
