/**
 * V3 内容生产 - 成片库接口契约与初始数据集
 * 对应后端表：v3_content_assets
 * 对应后端服务：server/content_library.py, server/v2_file_service.py
 *
 * 业务约束：
 * - 成片库独立在“内容生产”内部，不混入旧“生产资源”；
 * - 接受三种来源：原剧二创、旧流程成片、外部导入视频；
 * - 成片与编组为多对多关系 (groupIds: string[])；
 * - 原创状态与授权已用次数 (默认上限 9 次，可配置) 独立核算。
 */

import { TechInspectionStatus, ManualReviewStatus } from './contentProduction';

export type ContentAssetSourceType = '原剧二创' | '旧流程成片' | '外部导入视频';

export type OriginalDeclarationStatus = '已声明原创' | '未声明原创' | '声明失败';

export interface AccountUsageCount {
  accountId: string;
  accountName: string;
  publishCount: number; // 实际发布次数 (1次、2次、3次等均如实记录)
  mode: '原创发布' | '授权发布';
  lastPublishedAt: string;
}

// v3_content_assets 成片库核心实体
export interface V3ContentAsset {
  id: string;
  videoName: string;
  sourceType: ContentAssetSourceType;
  dramaId: string;
  dramaTitle: string;
  generationRecord: string;          // 生成记录 (追溯批次/模型/来源防重)
  generationJobId?: string;
  templateVersion: string;           // 模板版本 (外部导入显示 "外部原生/无模板")
  durationSec: number;
  durationFormatted: string;
  filePath: string;                  // 真实本地文件路径，不直接覆写原片
  episodeRange: string;
  highlightCutPoint?: string;
  sourceHighlightId?: string;
  sourceHighlightLabel?: string;
  productionPurpose?: string;
  isViralHighlight?: boolean;
  jumpCutPositions?: string[];
  techStatus: TechInspectionStatus;
  techDetail: string;
  manualStatus: ManualReviewStatus;
  originalStatus: OriginalDeclarationStatus;
  originalDeclaredAccountId?: string;
  originalDeclaredAccountName?: string;
  originalDeclaredAt?: string;
  authUsedCount: number;             // 授权已用次数 (仅成功发布后扣减)
  authMaxLimit: number;              // 授权上限，默认 9，支持动态配置
  usedAccounts: AccountUsageCount[]; // 使用过的账号及实际发布次数
  createdAt: string;
  previewHue: string;
}

export interface ContentAssetFilterState {
  dramaTitle: string;                // 'ALL' or dramaTitle
  sourceType: ContentAssetSourceType | 'ALL';
  techQualified: 'ALL' | '合格' | '不合格' | '待检查';
  originalDeclared: 'ALL' | '已声明原创' | '未声明原创' | '声明失败';
  authUsageRange: 'ALL' | 'unused' | 'available' | 'exhausted'; // 0次 / 仍有额度(<上限) / 已满额(>=上限)
  publishState: 'ALL' | 'published' | 'unpublished';
  eliminatedState: 'ALL' | 'active' | 'eliminated';              // 未淘汰 vs 已淘汰
  searchQuery: string;
}

export const INITIAL_V3_CONTENT_ASSETS: V3ContentAsset[] = [
  {
    id: 'asset-v3-001',
    videoName: '隐龙归来_跳集高燃_EP01-06_A版.mp4',
    sourceType: '原剧二创',
    dramaId: 'drama-yinlong',
    dramaTitle: '隐龙归来',
    generationRecord: 'RMX-20261109-01 · Gemini 2.5 Pro · 跳集播放(EP01-06)',
    generationJobId: 'airun-20261109-01',
    templateVersion: 'v3.5.0-Pro (组件高完播版)',
    durationSec: 438,
    durationFormatted: '07分18秒',
    filePath: 'D:\\ShortDramaPlatform_V3\\content_assets\\20261109\\隐龙归来_跳集高燃_EP01-06_A版.mp4',
    episodeRange: '第01集 ~ 第06集',
    highlightCutPoint: '第01集 00:14 丈母娘当众撕毁婚书高潮切入',
    jumpCutPositions: ['第02集 01:45 → 跳第04集 00:10', '第05集 01:20 → 跳第06集 00:05'],
    techStatus: '合格',
    techDetail: '1080×1920 60fps · 响度 -14.2 LUFS · 无黑屏/静音帧',
    manualStatus: '已通过',
    originalStatus: '已声明原创',
    originalDeclaredAccountId: 'acc-cm-01',
    originalDeclaredAccountName: '触摸-战神巅峰剧场',
    originalDeclaredAt: '2026-11-09 14:45',
    authUsedCount: 3,
    authMaxLimit: 9,
    usedAccounts: [
      { accountId: 'acc-cm-01', accountName: '触摸-战神巅峰剧场', publishCount: 2, mode: '原创发布', lastPublishedAt: '2026-11-09 14:50' },
      { accountId: 'acc-cm-02', accountName: '触摸-都市狂龙录', publishCount: 2, mode: '授权发布', lastPublishedAt: '2026-11-09 15:10' },
      { accountId: 'acc-dz-01', accountName: '点众-王牌剧场主号', publishCount: 1, mode: '授权发布', lastPublishedAt: '2026-11-09 15:25' }
    ],
    createdAt: '2026-11-09 14:32',
    previewHue: 'from-indigo-900 via-slate-900 to-purple-950'
  },
  {
    id: 'asset-v3-002',
    videoName: '隐龙归来_跳集逆袭_EP07-14_B版.mp4',
    sourceType: '原剧二创',
    dramaId: 'drama-yinlong',
    dramaTitle: '隐龙归来',
    generationRecord: 'RMX-20261109-01 · Gemini 2.5 Pro · 跳集播放(EP07-14)',
    generationJobId: 'airun-20261109-01',
    templateVersion: 'v3.5.0-Pro (组件高完播版)',
    durationSec: 512,
    durationFormatted: '08分32秒',
    filePath: 'D:\\ShortDramaPlatform_V3\\content_assets\\20261109\\隐龙归来_跳集逆袭_EP07-14_B版.mp4',
    episodeRange: '第07集 ~ 第14集',
    highlightCutPoint: '第07集 00:08 江城慈善晚宴逼迫下跪切入',
    jumpCutPositions: ['第08集 01:50 → 跳第11集 00:12', '第12集 02:05 → 跳第14集 00:00'],
    techStatus: '合格',
    techDetail: '1080×1920 60fps · 响度 -13.8 LUFS · 无黑帧',
    manualStatus: '已通过',
    originalStatus: '未声明原创',
    authUsedCount: 0,
    authMaxLimit: 9,
    usedAccounts: [],
    createdAt: '2026-11-09 14:32',
    previewHue: 'from-slate-900 via-indigo-950 to-emerald-950'
  },
  {
    id: 'asset-v3-003',
    videoName: '隐龙归来_跳集终局_EP23-30_D版.mp4',
    sourceType: '原剧二创',
    dramaId: 'drama-yinlong',
    dramaTitle: '隐龙归来',
    generationRecord: 'RMX-20261109-01 · Gemini 2.5 Pro · 跳集播放(EP23-30)',
    generationJobId: 'airun-20261109-01',
    templateVersion: 'v3.5.0-Pro (组件高完播版)',
    durationSec: 564,
    durationFormatted: '09分24秒',
    filePath: 'D:\\ShortDramaPlatform_V3\\content_assets\\20261109\\隐龙归来_跳集终局_EP23-30_D版.mp4',
    episodeRange: '第23集 ~ 第30集',
    highlightCutPoint: '第23集 00:05 家族祠堂夺权大会切入',
    jumpCutPositions: ['第25集 01:55 → 跳第28集 00:15'],
    techStatus: '合格',
    techDetail: '1080×1920 60fps · 响度 -14.0 LUFS · 完播钩子完整',
    manualStatus: '待审核',
    originalStatus: '未声明原创',
    authUsedCount: 0,
    authMaxLimit: 9,
    usedAccounts: [],
    createdAt: '2026-11-09 14:32',
    previewHue: 'from-purple-950 via-slate-900 to-indigo-950'
  },
  {
    id: 'asset-v3-004',
    videoName: '真千金的绝地逆袭_旧模板合成_01.mp4',
    sourceType: '旧流程成片',
    dramaId: 'drama-zhenqianjin',
    dramaTitle: '真千金的绝地逆袭',
    generationRecord: 'LEGACY-PROD-20261106-08 · 剪映草稿渲染归档',
    templateVersion: 'Legacy-JianYing-v2.1',
    durationSec: 392,
    durationFormatted: '06分32秒',
    filePath: 'D:\\ShortDramaPlatform_V3\\legacy_exports\\真千金的绝地逆袭_旧模板合成_01.mp4',
    episodeRange: '第01集 ~ 第03集',
    techStatus: '合格',
    techDetail: '1080×1920 30fps · 旧生产中心历史归档成片（只读引用，未修改原片）',
    manualStatus: '已通过',
    originalStatus: '已声明原创',
    originalDeclaredAccountId: 'acc-qn-01',
    originalDeclaredAccountName: '青柠-爆米花追剧',
    originalDeclaredAt: '2026-11-07 10:15',
    authUsedCount: 9,
    authMaxLimit: 9,
    usedAccounts: [
      { accountId: 'acc-qn-01', accountName: '青柠-爆米花追剧', publishCount: 3, mode: '原创发布', lastPublishedAt: '2026-11-07 18:00' },
      { accountId: 'acc-qn-02', accountName: '青柠-微光甜宠社', publishCount: 3, mode: '授权发布', lastPublishedAt: '2026-11-08 12:30' },
      { accountId: 'acc-qn-03', accountName: '青柠-心动信号台', publishCount: 2, mode: '授权发布', lastPublishedAt: '2026-11-08 19:00' },
      { accountId: 'acc-mt-01', accountName: '蜜糖-替身虐恋局', publishCount: 4, mode: '授权发布', lastPublishedAt: '2026-11-09 09:20' }
    ],
    createdAt: '2026-11-06 16:40',
    previewHue: 'from-emerald-950 via-slate-900 to-teal-950'
  },
  {
    id: 'asset-v3-005',
    videoName: '狂飙天王_外部剪辑师精剪_高燃混剪02.mp4',
    sourceType: '外部导入视频',
    dramaId: 'drama-kuangbiao',
    dramaTitle: '狂飙天王',
    generationRecord: 'EXT-IMPORT-20261108-03 · 外部精剪团队交付导入',
    templateVersion: '外部原生精剪 (无内部模板)',
    durationSec: 485,
    durationFormatted: '08分05秒',
    filePath: 'D:\\ShortDramaPlatform_V3\\external_imports\\狂飙天王_外部剪辑师精剪_高燃混剪02.mp4',
    episodeRange: '第01集 ~ 第08集 (跨集混剪)',
    techStatus: '合格',
    techDetail: '1080×1920 60fps · 外部导入自动校验通过',
    manualStatus: '已通过',
    originalStatus: '声明失败',
    originalDeclaredAccountId: 'acc-jz-01',
    originalDeclaredAccountName: '九州-热血男儿志',
    originalDeclaredAt: '2026-11-08 20:10',
    authUsedCount: 0,
    authMaxLimit: 9,
    usedAccounts: [],
    createdAt: '2026-11-08 18:10',
    previewHue: 'from-amber-950 via-slate-900 to-orange-950'
  },
  {
    id: 'asset-v3-006',
    videoName: '顾总请自重_跳集甜虐_EP01-05.mp4',
    sourceType: '原剧二创',
    dramaId: 'drama-guzong',
    dramaTitle: '顾总请自重',
    generationRecord: 'RMX-20261108-04 · DeepSeek-R1 · 跳集播放(EP01-05)',
    templateVersion: 'v3.4.2-Std (沉浸全屏通版)',
    durationSec: 350,
    durationFormatted: '05分50秒',
    filePath: 'D:\\ShortDramaPlatform_V3\\content_assets\\20261108\\顾总请自重_跳集甜虐_EP01-05.mp4',
    episodeRange: '第01集 ~ 第05集',
    highlightCutPoint: '第01集 00:06 契约协议签署现场切入',
    jumpCutPositions: ['第02集 01:35 → 跳第04集 00:20'],
    techStatus: '合格',
    techDetail: '1080×1920 60fps · 响度 -14.1 LUFS',
    manualStatus: '已通过',
    originalStatus: '已声明原创',
    originalDeclaredAccountId: 'acc-qn-02',
    originalDeclaredAccountName: '青柠-微光甜宠社',
    originalDeclaredAt: '2026-11-08 21:00',
    authUsedCount: 5,
    authMaxLimit: 9,
    usedAccounts: [
      { accountId: 'acc-qn-02', accountName: '青柠-微光甜宠社', publishCount: 1, mode: '原创发布', lastPublishedAt: '2026-11-08 21:05' },
      { accountId: 'acc-qn-01', accountName: '青柠-爆米花追剧', publishCount: 2, mode: '授权发布', lastPublishedAt: '2026-11-09 08:30' }
    ],
    createdAt: '2026-11-08 19:45',
    previewHue: 'from-pink-950 via-slate-900 to-rose-950'
  },
  {
    id: 'asset-v3-007',
    videoName: '隐龙归来_跳集悬念_EP15-22_C版_黑屏残次.mp4',
    sourceType: '原剧二创',
    dramaId: 'drama-yinlong',
    dramaTitle: '隐龙归来',
    generationRecord: 'RMX-20261109-01 · Gemini 2.5 Pro · 跳集播放(EP15-22)',
    generationJobId: 'airun-20261109-01',
    templateVersion: 'v3.5.0-Pro (组件高完播版)',
    durationSec: 365,
    durationFormatted: '06分05秒',
    filePath: 'D:\\ShortDramaPlatform_V3\\content_assets\\20261109\\隐龙归来_跳集悬念_EP15-22_C版.mp4',
    episodeRange: '第15集 ~ 第22集',
    techStatus: '不合格',
    techDetail: '04:12 处存在 1.8s 连续黑屏与左声道断流',
    manualStatus: '已淘汰',
    originalStatus: '未声明原创',
    authUsedCount: 0,
    authMaxLimit: 9,
    usedAccounts: [],
    createdAt: '2026-11-09 14:32',
    previewHue: 'from-rose-950 via-slate-900 to-stone-900'
  }
];
