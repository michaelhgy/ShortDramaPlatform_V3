/**
 * V3 内容生产 - 编组管理、原创声明记录与授权发布记录接口契约
 * 对应后端表：
 * - v3_content_groups           编组（发布管理集合，非制作批次）
 * - v3_content_group_items      编组与成片多对多关系及顺序
 * - v3_content_original_records 原创声明记录
 * - v3_content_publications     发布记录
 * 对应后端服务：server/content_groups.py, server/v2_file_service.py
 */

// 1. v3_content_groups 编组
export interface V3ContentGroup {
  id: string;
  name: string;
  description: string;
  tags: string[];
  createdAt: string;
  updatedAt: string;
}

// 2. v3_content_group_items 编组与成片多对多关联表
export interface V3ContentGroupItem {
  id: string;
  groupId: string;
  assetId: string;
  sortOrder: number; // 支持组内上下调整顺序
  addedAt: string;
  note?: string;
}

// 3. v3_content_original_records 原创声明独立记录
export interface V3ContentOriginalRecord {
  id: string;
  assetId: string;
  videoName: string;
  dramaTitle: string;
  groupId?: string;
  groupName?: string;
  accountId: string;
  accountName: string;
  theaterName: string;
  actualPublishCount: number; // 设置账号实际发布次数 (1次、2次、3次...)
  status: '原创声明成功' | '原创声明失败';
  consumedOriginalCount: number; // 仅成功时记录消耗次数，失败为 0 且不算原创成功
  failureReason?: string;
  recordedAt: string;
}

// 4. v3_content_publications 账号发布记录 (含原创发布与小V猫授权发布)
export interface V3ContentPublication {
  id: string;
  assetId: string;
  videoName: string;
  dramaTitle: string;
  sourceType: '原剧二创' | '旧流程成片' | '外部导入视频';
  groupId?: string;
  groupName?: string;
  publishMode: '原创发布' | '授权发布';
  accountId: string;
  accountName: string;
  theaterName: string;
  actualPublishCount: number; // 账号实际发布1次、2次、3次都作为实际记录保存
  status: '发布成功' | '发布失败';
  authQuotaDeducted: number;  // 授权发布仅在成功发布后扣次数；失败扣 0 次
  xiaovmaoFlowCode: string;   // 小V猫授权/发布流水号
  failureReason?: string;
  publishedAt: string;
}

// 初始编组列表 (v3_content_groups) — 演示跨剧集、跨来源混合编组，以及同一成片加入多个编组
export const INITIAL_V3_CONTENT_GROUPS: V3ContentGroup[] = [
  {
    id: 'grp-v3-01',
    name: '晚间黄金档·男频高燃混发组',
    description: '混合《隐龙归来》二创切片与《狂飙天王》外部导入精剪，供触摸与九州男频号晚间轮播',
    tags: ['跨剧集混合', '男频主力', '晚间档'],
    createdAt: '2026-11-08 16:00',
    updatedAt: '2026-11-09 15:10'
  },
  {
    id: 'grp-v3-02',
    name: '女频甜宠反击·周末冲量编组',
    description: '整合《真千金的绝地逆袭》旧流程成片与《顾总请自重》新二创成片，供青柠、蜜糖矩阵号分发',
    tags: ['新旧来源混合', '女频甜宠', '高转化'],
    createdAt: '2026-11-08 18:30',
    updatedAt: '2026-11-09 14:40'
  },
  {
    id: 'grp-v3-03',
    name: 'S/SS级头部账号·王牌首发库',
    description: '跨男频女频精选高完播成片（同一视频可同时存在于专项组与本王牌组）',
    tags: ['多对多复用', '头部号首发'],
    createdAt: '2026-11-09 10:00',
    updatedAt: '2026-11-09 15:20'
  }
];

// 初始编组与成片多对多关系 (v3_content_group_items)
// 注意：asset-v3-001 和 asset-v3-006 同时加入了多个编组，体现真实多对多关系
export const INITIAL_V3_GROUP_ITEMS: V3ContentGroupItem[] = [
  // 编组 1：男频高燃混发组 (含隐龙归来 + 狂飙天王外部导入)
  { id: 'gi-01', groupId: 'grp-v3-01', assetId: 'asset-v3-001', sortOrder: 1, addedAt: '2026-11-09 14:35' },
  { id: 'gi-02', groupId: 'grp-v3-01', assetId: 'asset-v3-002', sortOrder: 2, addedAt: '2026-11-09 14:36' },
  { id: 'gi-03', groupId: 'grp-v3-01', assetId: 'asset-v3-005', sortOrder: 3, addedAt: '2026-11-09 14:38' },
  { id: 'gi-04', groupId: 'grp-v3-01', assetId: 'asset-v3-003', sortOrder: 4, addedAt: '2026-11-09 14:40' },

  // 编组 2：女频甜宠反击组 (含旧流程成片 + 原剧二创)
  { id: 'gi-05', groupId: 'grp-v3-02', assetId: 'asset-v3-004', sortOrder: 1, addedAt: '2026-11-08 18:35' },
  { id: 'gi-06', groupId: 'grp-v3-02', assetId: 'asset-v3-006', sortOrder: 2, addedAt: '2026-11-08 20:00' },

  // 编组 3：头部王牌首发库 (同一视频 asset-v3-001、asset-v3-004、asset-v3-006 跨编组复用)
  { id: 'gi-07', groupId: 'grp-v3-03', assetId: 'asset-v3-001', sortOrder: 1, addedAt: '2026-11-09 14:42' },
  { id: 'gi-08', groupId: 'grp-v3-03', assetId: 'asset-v3-006', sortOrder: 2, addedAt: '2026-11-09 14:43' },
  { id: 'gi-09', groupId: 'grp-v3-03', assetId: 'asset-v3-004', sortOrder: 3, addedAt: '2026-11-09 14:44' }
];

// 初始原创声明记录 (v3_content_original_records)
export const INITIAL_V3_ORIGINAL_RECORDS: V3ContentOriginalRecord[] = [
  {
    id: 'orig-rec-01',
    assetId: 'asset-v3-001',
    videoName: '隐龙归来_跳集高燃_EP01-06_A版.mp4',
    dramaTitle: '隐龙归来',
    groupId: 'grp-v3-01',
    groupName: '晚间黄金档·男频高燃混发组',
    accountId: 'acc-cm-01',
    accountName: '触摸-战神巅峰剧场',
    theaterName: '触摸剧场',
    actualPublishCount: 2,
    status: '原创声明成功',
    consumedOriginalCount: 2,
    recordedAt: '2026-11-09 14:45:12'
  },
  {
    id: 'orig-rec-02',
    assetId: 'asset-v3-005',
    videoName: '狂飙天王_外部剪辑师精剪_高燃混剪02.mp4',
    dramaTitle: '狂飙天王',
    groupId: 'grp-v3-01',
    groupName: '晚间黄金档·男频高燃混发组',
    accountId: 'acc-jz-01',
    accountName: '九州-热血男儿志',
    theaterName: '九州剧场',
    actualPublishCount: 1,
    status: '原创声明失败',
    consumedOriginalCount: 0, // 失败不算原创成功，不计入有效消耗
    failureReason: '平台返回：该外部视频首帧特征与站内已有作品重合度过高，原创声明被驳回',
    recordedAt: '2026-11-08 20:10:05'
  },
  {
    id: 'orig-rec-03',
    assetId: 'asset-v3-006',
    videoName: '顾总请自重_跳集甜虐_EP01-05.mp4',
    dramaTitle: '顾总请自重',
    groupId: 'grp-v3-02',
    groupName: '女频甜宠反击·周末冲量编组',
    accountId: 'acc-qn-02',
    accountName: '青柠-微光甜宠社',
    theaterName: '青柠剧场',
    actualPublishCount: 1,
    status: '原创声明成功',
    consumedOriginalCount: 1,
    recordedAt: '2026-11-08 21:00:33'
  },
  {
    id: 'orig-rec-04',
    assetId: 'asset-v3-004',
    videoName: '真千金的绝地逆袭_旧模板合成_01.mp4',
    dramaTitle: '真千金的绝地逆袭',
    groupId: 'grp-v3-02',
    groupName: '女频甜宠反击·周末冲量编组',
    accountId: 'acc-qn-01',
    accountName: '青柠-爆米花追剧',
    theaterName: '青柠剧场',
    actualPublishCount: 3,
    status: '原创声明成功',
    consumedOriginalCount: 3,
    recordedAt: '2026-11-07 10:15:00'
  }
];

// 初始发布记录 (v3_content_publications)
export const INITIAL_V3_PUBLICATIONS: V3ContentPublication[] = [
  {
    id: 'pub-rec-01',
    assetId: 'asset-v3-001',
    videoName: '隐龙归来_跳集高燃_EP01-06_A版.mp4',
    dramaTitle: '隐龙归来',
    sourceType: '原剧二创',
    groupId: 'grp-v3-01',
    groupName: '晚间黄金档·男频高燃混发组',
    publishMode: '原创发布',
    accountId: 'acc-cm-01',
    accountName: '触摸-战神巅峰剧场',
    theaterName: '触摸剧场',
    actualPublishCount: 2,
    status: '发布成功',
    authQuotaDeducted: 0,
    xiaovmaoFlowCode: 'XVM-ORIG-20261109-881',
    publishedAt: '2026-11-09 14:50:00'
  },
  {
    id: 'pub-rec-02',
    assetId: 'asset-v3-001',
    videoName: '隐龙归来_跳集高燃_EP01-06_A版.mp4',
    dramaTitle: '隐龙归来',
    sourceType: '原剧二创',
    groupId: 'grp-v3-01',
    groupName: '晚间黄金档·男频高燃混发组',
    publishMode: '授权发布',
    accountId: 'acc-cm-02',
    accountName: '触摸-都市狂龙录',
    theaterName: '触摸剧场',
    actualPublishCount: 2,
    status: '发布成功',
    authQuotaDeducted: 2,
    xiaovmaoFlowCode: 'XVM-AUTH-20261109-904',
    publishedAt: '2026-11-09 15:10:22'
  },
  {
    id: 'pub-rec-03',
    assetId: 'asset-v3-001',
    videoName: '隐龙归来_跳集高燃_EP01-06_A版.mp4',
    dramaTitle: '隐龙归来',
    sourceType: '原剧二创',
    groupId: 'grp-v3-03',
    groupName: 'S/SS级头部账号·王牌首发库',
    publishMode: '授权发布',
    accountId: 'acc-dz-01',
    accountName: '点众-王牌剧场主号',
    theaterName: '点众剧场',
    actualPublishCount: 1,
    status: '发布成功',
    authQuotaDeducted: 1,
    xiaovmaoFlowCode: 'XVM-AUTH-20261109-918',
    publishedAt: '2026-11-09 15:25:40'
  },
  {
    id: 'pub-rec-04',
    assetId: 'asset-v3-001',
    videoName: '隐龙归来_跳集高燃_EP01-06_A版.mp4',
    dramaTitle: '隐龙归来',
    sourceType: '原剧二创',
    groupId: 'grp-v3-01',
    groupName: '晚间黄金档·男频高燃混发组',
    publishMode: '授权发布',
    accountId: 'acc-jz-02',
    accountName: '九州-战魂觉醒台',
    theaterName: '九州剧场',
    actualPublishCount: 2,
    status: '发布失败',
    authQuotaDeducted: 0, // 失败不扣减授权额度
    xiaovmaoFlowCode: 'XVM-AUTH-20261109-930',
    failureReason: '小V猫回传：目标账号扫码登录态超时未确认，本次授权发布未生效（未扣除授权次数）',
    publishedAt: '2026-11-09 15:31:10'
  },
  {
    id: 'pub-rec-05',
    assetId: 'asset-v3-006',
    videoName: '顾总请自重_跳集甜虐_EP01-05.mp4',
    dramaTitle: '顾总请自重',
    sourceType: '原剧二创',
    groupId: 'grp-v3-02',
    groupName: '女频甜宠反击·周末冲量编组',
    publishMode: '授权发布',
    accountId: 'acc-qn-01',
    accountName: '青柠-爆米花追剧',
    theaterName: '青柠剧场',
    actualPublishCount: 2,
    status: '发布成功',
    authQuotaDeducted: 2,
    xiaovmaoFlowCode: 'XVM-AUTH-20261109-712',
    publishedAt: '2026-11-09 08:30:15'
  }
];
