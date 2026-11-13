// 运营驾驶舱数据适配与强类型定义
// 数据严格源自 运营驾驶舱演示数据.json

import rawData from './workbenchDemoData.json';

export interface CockpitPackage {
  name: string;
  version: number;
  generated_at: string;
  data_is_demo: boolean;
  source_kind: string;
  latest_date: string;
  range: {
    start: string;
    end: string;
  };
}

export interface BusinessContext {
  account_model: string;
  traffic_source: string;
  revenue_source: string;
  settlement_rule: string;
  missing_rule: string;
}

export interface DashboardSummary {
  latest_day: {
    views: number;
    fans_add: number;
    fans_net: number;
    interaction: number;
    record_accounts: number;
    revenue: number;
  };
  previous_day: {
    views: number;
  };
  range_views: number;
  month_views: number;
  historical_views: number;
  range_fans_add: number;
  range_interaction: number;
  revenue_by_theater: Record<string, number>;
  current_month_revenue_by_theater: Record<string, number>;
  current_month_revenue: number;
}

export interface AccountLatestStats {
  account_id: string;
  stat_date: string;
  view: number;
  fans_total: number;
  fans_add: number;
  fans_net: number;
  fans_reduce: number;
  like_count: number;
  favorite_count: number;
  comment_count: number;
  forward_count: number;
  source_kind: string;
  data_state: 'record' | 'zero' | 'missing' | 'failed';
  freshness_state: string;
}

export interface AccountCard {
  account_id: string;
  uid: string;
  account_name: string;
  group_name: string;
  latest: AccountLatestStats;
  range_views: number;
  range_fans_add: number;
  range_fans_net: number;
  range_interaction: number;
  record_days: number;
  expected_days: number;
  record_status: string;
}

export interface AccountDailyTrend {
  date: string;
  account_count: number;
  views: number;
  fans_add: number;
  fans_net: number;
  interaction: number;
  source_kind: string;
}

export interface PostItem {
  post_id: string;
  account_id: string;
  account_name: string;
  title: string;
  description: string;
  post_time: string;
  post_type: string;
  publish_status: string;
  view: number;
  like_count: number;
  comment_count: number;
  forward_count: number;
  love_count: number;
  fans_add: number;
  full_view: number;
  view_time: number;
  snapshot_date: string;
  source_kind: string;
  data_state: 'record' | 'zero' | 'missing' | 'failed';
  freshness_state: string;
}

export interface PostDailyItem {
  post_id: string;
  account_id: string;
  stat_date: string;
  view: number;
  like_count: number;
  comment_count: number;
  forward_count: number;
  favorite_count: number;
  fans_add: number;
  metric_grain: string;
  source_kind: string;
  data_state: 'record' | 'zero' | 'missing' | 'failed';
  freshness_state: string;
}

export interface DiagnosticItem {
  account_id: string;
  account_name: string;
  verified: number;
  abnormal: number;
  video_status: string;
  heat_status: string;
  abnormal_post_count: number;
  last_verify_time: string;
  snapshot_date: string;
  source_kind: string;
  data_state: 'record' | 'zero' | 'missing' | 'failed';
  freshness_state: string;
}

export interface PunishmentItem {
  uid: string;
  post_id_or_export_id: string;
  title: string;
  publish_time: string;
  punish_state: string;
  snapshot_date: string;
  source_kind: string;
  data_state: 'record' | 'zero' | 'missing' | 'failed';
  freshness_state: string;
}

export interface RevenueSource {
  theater_id: string;
  adapter_key: string;
  query_mode: 'date_range' | 'month_cumulative';
  date_precision: 'day' | 'month';
  supports_detail: number;
  requires_account_id: number;
  requires_date: number;
  adapter_status: string;
  last_checked_at: string;
  notes: string;
  name?: string;
}

export interface RevenuePeriod {
  account_id: string;
  theater_id: string;
  period_label: string;
  period_start: string;
  period_end: string;
  period_type: 'day' | 'month_cumulative';
  date_precision: 'day' | 'month';
  amount: string;
  currency: string;
  data_state: 'record' | 'zero' | 'missing' | 'failed';
  freshness_state: string;
  settlement_state: 'unsettled' | 'settled';
  include_in_analysis: number;
  source_kind: string;
  collected_at: string;
}

export interface RevenueDetail {
  account_id: string;
  theater_id: string;
  detail_date: string;
  source_video_id: string;
  source_drama_name: string;
  video_views: number;
  drama_views: number;
  gross_revenue: string;
  source_rank: number;
  source_kind: string;
  data_state: string;
  freshness_state: string;
}

export interface CockpitPayload {
  package: CockpitPackage;
  business_context: BusinessContext;
  dashboard_summary: DashboardSummary;
  account_cards: AccountCard[];
  account_daily_trend: AccountDailyTrend[];
  posts: PostItem[];
  post_daily: PostDailyItem[];
  diagnostics: DiagnosticItem[];
  punishments: PunishmentItem[];
  revenue_sources: RevenueSource[];
  revenue_periods: RevenuePeriod[];
  revenue_details: RevenueDetail[];
  demo_scenarios: Array<{ scenario: string; meaning: string }>;
  field_dictionary: Record<string, Record<string, string>>;
}

// 剧场名称可读化映射
export const THEATER_NAME_MAP: Record<string, { name: string; tag: string; description: string }> = {
  '3a319630f5cb4dfb8b30e1670bca3172': {
    name: '青柠剧场',
    tag: '按日明细接口',
    description: '支持精确至单日、账号、单片与剧名的流水明细',
  },
  'e2293cc1d7d440e886ab08862961d832': {
    name: '触摸剧场',
    tag: '月累计接口',
    description: '仅支持月度未结算累计总额，不支持按日与单片拆分',
  },
};

// 导出强类型数据实例
export const COCKPIT_DATA = rawData as unknown as CockpitPayload;

// 辅助计算函数
export function getYesterdaySummary() {
  const sum = COCKPIT_DATA.dashboard_summary;
  const latestViews = sum.latest_day.views;
  const prevViews = sum.previous_day.views;
  const viewsGrowth = ((latestViews - prevViews) / prevViews) * 100;

  // 互动量拆分（从所有账号 latest 累加）
  const breakdown = COCKPIT_DATA.account_cards.reduce(
    (acc, card) => {
      acc.like += card.latest.like_count || 0;
      acc.favorite += card.latest.favorite_count || 0;
      acc.comment += card.latest.comment_count || 0;
      acc.forward += card.latest.forward_count || 0;
      return acc;
    },
    { like: 0, favorite: 0, comment: 0, forward: 0 }
  );

  return {
    ...sum.latest_day,
    previous_views: prevViews,
    views_growth_pct: viewsGrowth,
    interaction_breakdown: breakdown,
    month_views: sum.month_views,
    historical_views: sum.historical_views,
    current_month_revenue: sum.current_month_revenue,
  };
}

// 获取各账号最高播放作品
export function getHighestPostPerAccount(): Array<{
  account: AccountCard;
  highestPost: PostItem | null;
  diagnostic: DiagnosticItem | undefined;
}> {
  return COCKPIT_DATA.account_cards.map(account => {
    // 找出该账号的所有作品
    const accountPosts = COCKPIT_DATA.posts.filter(p => p.account_id === account.account_id);
    accountPosts.sort((a, b) => b.view - a.view);
    const highestPost = accountPosts[0] || null;
    const diagnostic = COCKPIT_DATA.diagnostics.find(d => d.account_id === account.account_id);
    return {
      account,
      highestPost,
      diagnostic,
    };
  });
}

// 全账号播放 Top 10 作品
export function getTop10Posts(): Array<PostItem & { interaction_rate: number; total_interaction: number }> {
  const sorted = [...COCKPIT_DATA.posts].sort((a, b) => b.view - a.view);
  return sorted.slice(0, 10).map(p => {
    const totalInteraction = (p.like_count || 0) + (p.comment_count || 0) + (p.forward_count || 0) + (p.love_count || 0);
    const interactionRate = p.view > 0 ? (totalInteraction / p.view) * 100 : 0;
    return {
      ...p,
      total_interaction: totalInteraction,
      interaction_rate: interactionRate,
    };
  });
}

// 识别“高播放低互动 / 低完播”预警作品
export function getHighViewLowRetentionPosts(): Array<PostItem & { reason: string }> {
  // 找出全平台播放较高 (> 40,000)，但完播率偏低 (<= 25%) 的作品
  return COCKPIT_DATA.posts
    .filter(p => p.view >= 40000 && p.full_view <= 0.25)
    .map(p => ({
      ...p,
      reason: `播放量高达 ${(p.view / 10000).toFixed(1)}w，但完播率仅 ${(p.full_view * 100).toFixed(1)}%，流失严重`,
    }));
}
