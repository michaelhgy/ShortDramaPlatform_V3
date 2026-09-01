// Assets Center Types (资料中心类型定义 - 第二版优化)

export type AssetsCenterTab = 'business_data' | 'drama_library' | 'production_resources' | 'viral_assets';
export type AssetsModuleTab = AssetsCenterTab;
export type BusinessSubTab = 'accounts' | 'theaters' | 'sub_theaters' | 'dramas';

// ================= 1. 业务资料 (Business Data) =================

// 1.1 账号状态：正常 / 观察 / 限流 / 二限 / 实名 / 封禁 / 停用
export type AccountBusinessStatus = '正常' | '观察' | '限流' | '二限' | '实名' | '封禁' | '停用';

export interface AccountBusinessItem {
  id: string;
  nickname: string;         // 账号昵称
  accountId: string;        // 账号 ID (原始/平台ID)
  theaterId: string;        // 所属剧场 ID
  theaterName: string;      // 所属剧场
  subTheaterName: string;   // 所属子剧场（方便用户查看结算找谁）
  status: AccountBusinessStatus;
  whitelistedDate: string;  // 报白时间 (如 "2024-03-12" 或 "未报白")
  registeredDate: string;   // 注册时间
  notes: string;            // 备注
  isUsedInBusiness?: boolean; // 是否已被实际业务使用（有绑定发布/生产），若有则禁止删除
}

// 1.2 剧场 (20-30个)
export interface TheaterBusinessItem {
  id: string;
  name: string;                   // 剧场名称
  defaultCommissionRate: number;  // 默认分成 % (如 72 表示 72%)
  defaultTaxRate: number;         // 默认税率 % (如 6 表示 6%)
  status: '启用' | '停用';        // 状态
  subTheatersCount?: number;      // 下属子剧场数量统计
  dramasCount?: number;           // 关联剧集数量统计
  isUsedInBusiness?: boolean;     // 是否已被实际业务使用
}

// 1.3 子剧场 (每个剧场下 20-30个)
export interface SubTheaterBusinessItem {
  id: string;
  name: string;                   // 子剧场名称
  theaterId: string;              // 所属剧场 ID
  theaterName: string;            // 所属剧场名称
  commissionRate: number;         // 分成比例 % (默认继承剧场，可手动覆盖)
  isCommissionOverridden: boolean;// 是否为手动修改覆盖
  status: '启用' | '停用';        // 状态
  boundAccountsCount?: number;    // 已绑定账号数（若 > 0 则锁定所属剧场不允许修改）
  isUsedInBusiness?: boolean;     // 是否已被实际业务使用
}

// 1.4 剧集 (大量，改名时自动沉淀历史剧名)
export interface DramaBusinessItem {
  id: string;
  currentName: string;      // 当前生效剧名
  historyNames: string[];   // 历史剧名列表 (改名时自动追加，支持切换为当前生效剧名或删除错误名)
  theaterId: string;        // 所属剧场 ID
  theaterName: string;      // 所属剧场名称
  createdAt: string;        // 录入时间
  productionCount?: number;
  lastScheduledAt?: string;
  activeProductionCount?: number;
  hasContentProfile?: boolean; // 是否已建立更丰富的剧集资料库档案
  isUsedInBusiness?: boolean; // 是否已有真实生产/发布关系（若有则禁止删除）
  tags?: string[];          // 标签（来自标签库）
}

// ================= 2. 剧集资料库 (Drama Content Library) =================

export interface MasterVideoEpisodeFile {
  episode: number;
  filename: string;
  fileSizeMb: number;
  durationText: string;
  resolution: string;
  path: string;
}

export interface DramaContentProfile {
  id: string;
  dramaId: string;              // 引用的业务剧集 ID
  dramaCurrentName: string;     // 当前生效剧名
  theaterName: string;          // 所属剧场
  category?: string;            // 题材归类
  tags: string[];               // 剧集标签（可为0个、1个或多个）
  totalEpisodes: number;        // 总集数
  
  // 封面资料 (以竖版主封面为主)
  cover: {
    mainCoverUrl?: string;      // 竖版主封面
    filePath?: string;          // 本地文件路径
    updateTime?: string;        // 替换/更新时间
  };

  // 原片库
  masterVideoPackage: {
    folderPath: string;         // 本地原片 Windows 文件夹路径
    totalFiles: number;         // 已录入文件数
    totalSizeGb: number;        // 总大小 GB
    resolution: string;         // 分辨率
    status: '就绪' | '部分缺失' | '待导入';
    files: MasterVideoEpisodeFile[];
  };

  // 预留的内容资料扩展空间 (无AI生成花哨内容)
  plotKnowledgeBase?: {
    synopsis: string;           // 剧情主线概要
    characterNotes: string;     // 人物小传
    hookPointsCount: number;    // 高光反转点数量
    hasScript: boolean;         // 是否有剧本分镜
    scriptFolderPath?: string;  // 剧本文档路径
  };

  associatedViralAssetsCount: number; // 关联爆款素材数
  updatedAt: string;
}

// ================= 3. 生产资源 (Production Resources) =================

export type ResourceCategory = 'real_video' | 'real_image' | 'bgm' | 'lead_video';
export type ResourceStatus = 'available' | 'used'; // 可用 | 已使用

export interface ProductionResourceItem {
  id: string;
  name: string;
  category: ResourceCategory;
  categoryName: string;
  filePath: string;
  fileSizeMb: number;
  thumbnailUrl?: string;
  mediaUrl?: string;
  durationSeconds?: number;
  resolution?: string;
  status: ResourceStatus;       // 'available' 可用 | 'used' 已使用
  usedInDramaName?: string;     // 若已使用，记录所用剧名
  addedAt: string;
}

// 生产资源容量统计与计算
export interface ResourceCapacityMetrics {
  videoCount: number;           // 可用真人视频数量
  imageCount: number;           // 可用真人图片数量
  bgmCount: number;             // BGM 数量
  totalVideoCount: number;      // 真人视频总数量（含已使用）
  totalImageCount: number;      // 真人图片总数量（含已使用）
  
  // 生产规则：每生产 1 部剧集需要消耗 3 个真人视频 + 6 张真人图片
  supportableDramas: number;    // 可支持剧集数 = Math.floor(Math.min(videoCount / 3, imageCount / 6))
  videoSupportableDramas: number; // 视频可支持剧集数 = Math.floor(videoCount / 3)
  imageSupportableDramas: number; // 图片可支持剧集数 = Math.floor(imageCount / 6)
  
  bottleneckType: 'video' | 'image' | 'balanced'; // 产能短板
  shortageTip?: string;         // 补充建议
}

// ================= 4. 爆款资产 (Viral Assets Pool) =================

// 单条爆款记录 (一素材多记录沉淀)
export interface ViralRecordItem {
  id: string;
  date: string;               // 爆款日期 (如 "2026-08-20")
  viralDate?: string;         // 兼容别名
  accountName: string;        // 爆款投放账号
  dramaName: string;          // 投放关联剧集
  publishTime?: string;       // 发布时间 (如 "14:30")
  publishInfo?: string;       // 兼容描述
  videoPlayCount?: number;    // 视频播放量 (数值)
  videoPlayCountText?: string;// 视频播放量文本 (如 "38.6万")
  playCountText?: string;     // 兼容别名
  dramaPlayCount?: number;    // 剧集播放量 (数值，仅部分平台如青柠具备)
  dramaPlayCountText?: string;// 剧集播放量文本 (如 "72.4万")
  revenue?: number;           // 带来收益金额 (仅真实存在时有值)
  conversionRevenue?: number; // 兼容别名
  dataSource: '青柠平台数据' | '人工录入' | string; // 数据来源
  notes?: string;             // 运营亮点 / 调优说明
}

// 爆款源素材资产 (以物理原始视频文件为唯一核心载体)
export interface ViralAssetItem {
  id: string;
  materialName: string;       // 原始素材视频文件名 (如 "顾总夫人_雨夜下跪撑伞打脸开场_03s.mp4")
  title?: string;             // 别名/展示名
  sourceDramaName: string;    // 首次沉淀爆款时的原始来源剧集
  sourceTheaterName?: string; // 来源剧场
  sourceAccountName?: string; // 首次来源账号
  md5: string;                // MD5 唯一指纹 (用于系统物理去重)
  filePath: string;           // 本地物理文件路径
  fileSizeMb: number;         // 文件大小 (MB)
  durationSeconds: number;    // 视频时长 (秒)
  thumbnailUrl?: string;      // 缩略图
  firstViralDate: string;     // 首次爆款时间 (如 "2026-08-01")
  latestViralDate: string;    // 最近一次爆款时间 (如 "2026-08-24")
  lastViralDate?: string;     // 兼容别名
  viralCount: number;         // 爆款次数 (等于 records.length)
  reuseCount?: number;        // 复用频次
  
  // 汇总表现数据 (依据 records 真实数据累计计算)
  totalVideoPlays?: number;   // 累计视频播放量
  totalVideoPlaysText?: string;
  totalDramaPlays?: number;   // 累计剧集播放量 (仅当有记录包含时)
  totalDramaPlaysText?: string;
  totalRevenue?: number;      // 已记录累计收益 (仅当有记录包含真实收益时)
  hasDramaPlayData?: boolean; // 是否包含剧集播放数据
  hasRevenueData?: boolean;   // 是否包含真实收益数据
  isPartialDramaPlays?: boolean; // 是否仅部分记录有剧集播放数据

  records: ViralRecordItem[]; // 爆款记录列表 (多次爆款实战记录)
  createdAt?: string;
}

// 生产批次候选素材 (供新建爆款素材选择)
export interface ProductionBatchCandidateMaterial {
  id: string;
  name: string;
  filename?: string;
  filePath: string;
  durationSeconds: number;
  fileSizeMb: number;
  thumbnailUrl?: string;
  productionDate?: string;
  accountName: string;
  dramaName: string;
  theaterName?: string;
  md5: string;
}
