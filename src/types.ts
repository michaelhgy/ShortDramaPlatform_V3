export type NavTab = 'workbench' | 'production' | 'analytics' | 'assets' | 'settings';

export type ManualAccountStatus = '正常' | '观察' | '暂停' | '实名' | '封号' | '其他';

export type DramaProductionStatus = '待制作' | '制作中' | '已完成' | '异常';

export interface DramaItem {
  id: string;
  name: string;
  coverUrl?: string;
  colorPlaceholder?: {
    bg: string;
    text: string;
    tag: string;
  };
  totalEpisodes?: number;
  category?: string;
  theaterId?: string;
  theaterName?: string;
  usageCount?: number; // 历史生产使用频次
}

export interface DramaPrediction {
  id: string;
  dramaId: string;
  name: string;
  coverUrl?: string;
  colorPlaceholder?: {
    bg: string;
    text: string;
    tag: string;
  };
  performance: '爆发起量' | '表现较好' | '持续稳定' | '潜力观察';
  estimatedRevenueMin: number;
  estimatedRevenueMax: number;
  confidence: '高' | '中' | '低';
  reason: string;
  isFeatured?: boolean; // Highlight top 1~2 opportunity dramas
}

export interface AccountItem {
  id: string;
  name: string;
  avatarSeed?: string;
  yesterdayRevenue: number;
  monthRevenue: number;
  manualStatus: ManualAccountStatus;
  platform: string; // e.g. "微信视频号"
  theaterId?: string;
  theaterName?: string;
}

export interface ScheduleTask {
  id: string;
  accountId: string;
  accountName: string;
  dramaId: string;
  dramaName: string;
  coverUrl?: string;
  colorPlaceholder?: {
    bg: string;
    text: string;
    tag: string;
    };
    publishTime: string; // e.g. "今天 18:30" or "明天 09:00"
    plannedPublishAt?: string; // YYYY-MM-DDTHH:mm, used by V2 backend scheduling
    status: DramaProductionStatus;
  theaterName?: string;
  notes?: string;
}

export interface AccountScheduleGroup {
  accountId: string;
  accountName: string;
  manualStatus: ManualAccountStatus;
  yesterdayRevenue: number;
  tasks: ScheduleTask[];
}

export interface ProductionSummary {
  totalToday: number;
  inProgress: number;
  completed: number;
  exceptions: number;
}

export interface TaskCenterTask {
  id: string;
  title: string;
  accountName: string;
  stage: '后台生成' | '剪映渲染' | '小V猫推送' | '数据回传';
  status: 'running' | 'waiting' | 'error' | 'done';
  time: string;
}
