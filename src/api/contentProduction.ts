/**
 * V3 内容生产 - 原剧二创、通版模板、高光库与生产方案任务契约
 * 对应后端表：v3_content_templates, v3_content_ai_runs
 * 对应后端服务：server/content_remix_service.py, server/content_remix_http.py
 */

export type PlayContinuityMode = '连续播放' | '跳集播放';
export type StrategyCounts = Record<PlayContinuityMode, number>;

export type HighlightClipStatus = '候选' | '已确认' | '已使用' | '暂停' | '已通过' | '已淘汰';
export type ProductionPurpose = '首轮覆盖' | '爆款扩量' | '失败重做' | '策略测试';

// 高光库中的单个具体原片小片段（默认通过可用，人工过一遍可淘汰）
export interface V3DramaHighlightClip {
  id: string;
  code: string;                   // 例如 H01, H02
  dramaId: string;
  dramaTitle: string;
  episodeLabel: string;           // 第几集，例如 "第01集"
  timeRange: string;              // 原片时间范围，例如 "00:14 - 00:48"
  durationSec?: number;           // 片段秒数，例如 34
  durationText?: string;          // 片段时长，例如 "34秒"
  sceneTag?: string;              // 画面场景标签，例如 "寿宴撕婚书"
  dialogueText: string;           // 台词内容
  description: string;            // 高光说明
  status: HighlightClipStatus;    // 默认可用，不合适可标记为 '已淘汰'
  usedCount: number;              // 当前使用次数
  generatedVideoNames: string[];  // 已经生成过哪些成片
  isViral?: boolean;              // 是否已跑出爆款
  accentColor?: string;           // 预览画面主题色
  previewUrl?: string;             // 后端按需截取的原片预览地址
}

// 后端高光库版本接口：保留原片时间范围和资料版本，供真实数据接入时映射到 UI 高光卡片。
export interface V3HighlightLibraryItem {
  id: string;
  libraryVersionId: string;
  dramaId: string;
  dramaTitle: string;
  analysisVersion: string;
  sourceFingerprint: string;
  rank: number;
  episode: number;
  startLine: string;
  endLine: string;
  startTime: number;
  endTime: number;
  durationSec: number;
  sourcePath: string;
  anchorText: string;
  hookLabel: string;
  conflictId: string;
  viewerQuestion: string;
  reason: string;
  boundaryStatus: string;
  status: string;
  usageCount: number;
  previewUrl?: string;
  createdAt: string;
}

export interface V3HighlightLibraryVersion {
  versionId: string;
  dramaId: string;
  dramaTitle: string;
  analysisVersion: string;
  sourceFingerprint: string;
  createdAt: string;
  items: V3HighlightLibraryItem[];
}

export type PipelineStepKey =
  | 'scan_raw'
  | 'local_recognize'
  | 'highlight_judge'
  | 'continuity_plan'
  | 'video_synthesize'
  | 'tech_inspect'
  | 'auto_ingest';

export type PipelineStepStatus = 'pending' | 'running' | 'completed' | 'failed' | 'skipped';

export interface V3PipelineStep {
  key: PipelineStepKey;
  label: string;
  status: PipelineStepStatus;
  durationSec?: number;
  durationText: string;
  detailText: string;
  errorReason?: string;
}

export type TechInspectionStatus = '合格' | '不合格' | '待检查';
export type ManualReviewStatus = '待审核' | '已通过' | '已淘汰';

export interface V3RemixBatchResultItem {
  id: string;
  jobId: string;
  videoName: string;
  dramaId: string;
  dramaTitle: string;
  durationSec: number;
  durationFormatted: string;
  episodeRange: string;           // 原剧范围，例如 "第01集 ~ 第04集"
  highlightCutPoint: string;      // 高光切入点，例如 "第01集 00:14-00:48 丈母娘当众撕毁婚书"
  sourceHighlightId?: string;     // 来自哪个高光 ID
  sourceHighlightLabel?: string;  // 来自哪个高光展示名
  jumpCutPositions: string[];     // 跳集位置
  playStrategy: PlayContinuityMode;
  templateId: string;
  templateVersion: string;
  filePath: string;
  techStatus: TechInspectionStatus;
  techReport: string;             // 技术检查详情：分辨率、黑帧、响度、音画同步
  manualStatus: ManualReviewStatus;
  ingestedAssetId?: string;       // 入库后关联的 v3_content_assets ID
  sourceReasoning: string;        // 模型规划依据（查看来源）
  previewHue: string;
  createdAt: string;
  isViralHighlight?: boolean;     // 人工标记爆款高光
}

// v3_content_templates 通版模板版本
export interface V3ContentTemplate {
  id: string;
  name: string;
  version: string;
  description: string;
  aspectRatio: '9:16' | '16:9';
  frameRatio?: string;
  previewColor?: string;
  resolution: string;
  subtitlePreset: string;
  antiDuplicateLayer: string;
  updatedAt: string;
  rendererTemplateId?: string;
  titlePolicy?: string;
}

// 原剧原片目录与剧集资料状态
export interface RawDramaDirectoryInfo {
  dramaId: string;
  dramaTitle: string;
  directoryPath: string;
  totalEpisodes: number;
  verifiedMp4Count: number;
  missingEpisodes: number[];
  corruptedFiles: string[];
  totalSizeGb: number;
  scanStatus: 'ready' | 'missing_files' | 'unscanned';
  statusSummary: string;
  theaterName?: string;           // 所属剧场，如 "触摸剧场"
  genreTags?: string[];           // 题材类型，如 ["男频", "战神逆袭", "豪门打脸"]
  historyNames?: string[];        // 曾用剧名/别名
  mountPlatforms?: string[];      // 支持挂载方式，如 ["小程序挂载", "视频号剧集挂载"]
  storySummary?: string;          // 剧情地图主线概述
  climaxEpisodes?: string;        // 核心爆发集分布
  totalDurationText?: string;     // 原片全集总时长
  coverColor?: string;            // 剧集封面色调
}

// v3_content_ai_runs 模型判断与二创生成任务记录
export interface V3ContentAiRun {
  id: string;
  jobCode: string;
  roundCode?: string;                 // 例如 R1, R2, R3
  productionPurpose?: ProductionPurpose; // 首轮覆盖 | 补做失败 | 爆款扩量
  selectedHighlightIds?: string[];    // 本批次生产方案选用的高光片段 ID
  basedOnHighlight?: string;          // 围绕哪条爆款高光追加生产
  dramaId: string;
  dramaTitle: string;
  sourceDirectory: string;
  totalSourceEpisodes: number;
  sourceFilesStatus: string;
  templateId: string;
  templateName: string;
  templateVersion: string;
  playStrategy: PlayContinuityMode;
  durationRangeMin: [number, number]; // 例如 [5, 10] 分钟
  targetCount: number;
  modelId: string;                    // 动态可配置模型ID，不写死
  modelAssignments?: Partial<Record<'highlight' | 'continuous' | 'jump' | 'review', string>>;
  playStrategies?: PlayContinuityMode[];
  strategyCounts?: StrategyCounts;
  status: 'running' | 'completed' | 'partial_failed' | 'failed' | 'queued';
  pipelineSteps: V3PipelineStep[];
  results: V3RemixBatchResultItem[];
  createdAt: string;
  finishedAt?: string;
  error?: string;
  planNotes?: string[];
  synthFailures?: string[];
  methodVersion?: string;
  modelCalls?: { taskRole: string; model: string; usage?: Record<string, unknown>; elapsedS?: number; createdAt: string }[];
}

// 通版模板预设库 (v3_content_templates)
export const INITIAL_V3_TEMPLATES: V3ContentTemplate[] = [
  {
    id: 'tpl-mumu-original',
    name: '木木短剧·原版配色',
    version: 'mumu-v1.0',
    description: '原版斜切标题板 + 木木短剧品牌条，标题自动换名',
    aspectRatio: '9:16',
    frameRatio: '9:16 竖屏',
    previewColor: '#F59E0B',
    resolution: '1080×1920 (30fps)',
    subtitlePreset: '原版标题板字形',
    antiDuplicateLayer: '静态品牌模板层',
    updatedAt: '2026-11-10',
    rendererTemplateId: 'mumu-original',
    titlePolicy: '单行自动缩小，必要时按标点换两行'
  },
  {
    id: 'tpl-mumu-blue',
    name: '木木短剧·蓝色版',
    version: 'mumu-v1.0-blue',
    description: '蓝色标题板与品牌条，标题自动换名',
    aspectRatio: '9:16',
    frameRatio: '9:16 竖屏',
    previewColor: '#3B82F6',
    resolution: '1080×1920 (30fps)',
    subtitlePreset: '蓝色版标题板字形',
    antiDuplicateLayer: '静态品牌模板层',
    updatedAt: '2026-11-10',
    rendererTemplateId: 'mumu-blue',
    titlePolicy: '按标题板宽度自动缩小，必要时按标点换两行'
  },
  {
    id: 'tpl-mumu-cyan',
    name: '木木短剧·青色版',
    version: 'mumu-v1.0-cyan',
    description: '青色标题板与品牌条，标题自动换名',
    aspectRatio: '9:16',
    frameRatio: '9:16 竖屏',
    previewColor: '#06B6D4',
    resolution: '1080×1920 (30fps)',
    subtitlePreset: '青色版标题板字形',
    antiDuplicateLayer: '静态品牌模板层',
    updatedAt: '2026-11-10',
    rendererTemplateId: 'mumu-cyan',
    titlePolicy: '按标题板宽度自动缩小，必要时按标点换两行'
  },
  {
    id: 'tpl-mumu-red',
    name: '木木短剧·红色版',
    version: 'mumu-v1.0-red',
    description: '红色标题板与品牌条，标题自动换名',
    aspectRatio: '9:16',
    frameRatio: '9:16 竖屏',
    previewColor: '#EF4444',
    resolution: '1080×1920 (30fps)',
    subtitlePreset: '红色版标题板字形',
    antiDuplicateLayer: '静态品牌模板层',
    updatedAt: '2026-11-10',
    rendererTemplateId: 'mumu-red',
    titlePolicy: '按标题板宽度自动缩小，必要时按标点换两行'
  }
];

// 原剧目录与剧集档案字典
export const INITIAL_RAW_DRAMA_DIRS: RawDramaDirectoryInfo[] = [
  {
    dramaId: 'drama-yinlong',
    dramaTitle: '隐龙归来',
    directoryPath: 'D:\\ShortDramaPlatform_V3\\raw_dramas\\隐龙归来_1080P_母带',
    totalEpisodes: 85,
    verifiedMp4Count: 85,
    missingEpisodes: [],
    corruptedFiles: [],
    totalSizeGb: 14.8,
    scanStatus: 'ready',
    statusSummary: '85/85 集 MP4 母带校验完整 · 含内置SRT时间轴字幕与音频轨',
    theaterName: '触摸剧场',
    genreTags: ['男频战神', '都市逆袭', '豪门打脸'],
    historyNames: ['龙帅归来', '江城第一婿'],
    mountPlatforms: ['小程序挂载', '视频号剧集挂载'],
    storySummary: '隐忍三年上门女婿在丈母娘寿宴被当众撕毁婚书，亮明北境龙帅身份横扫江城豪门、夺回家族祠堂大权。',
    climaxEpisodes: '第01集(退婚)、第07集(亮黑卡)、第15集(地下拳场)、第23集(祠堂夺权)、第34集(坠崖真相)',
    totalDurationText: '148分20秒 (单集约1分45秒)',
    coverColor: '#1E293B'
  },
  {
    dramaId: 'drama-zhenqianjin',
    dramaTitle: '真千金的绝地逆袭',
    directoryPath: 'D:\\ShortDramaPlatform_V3\\raw_dramas\\真千金的绝地逆袭_全集',
    totalEpisodes: 92,
    verifiedMp4Count: 92,
    missingEpisodes: [],
    corruptedFiles: [],
    totalSizeGb: 16.2,
    scanStatus: 'ready',
    statusSummary: '92/92 集 MP4 母带校验完整 · 音画同步率 100%',
    theaterName: '点众剧场',
    genreTags: ['女频大女主', '真假千金', '马甲打脸'],
    historyNames: ['豪门真千金不好惹', '归来即巅峰'],
    mountPlatforms: ['小程序挂载', '视频号剧集挂载'],
    storySummary: '乡下找回的真千金在认亲宴遭假千金泼红酒陷害，当场反击并陆续揭晓神医、首席钢琴家与财团继承人多重马甲。',
    climaxEpisodes: '第01集(认亲宴反击)、第09集(DNA报告曝光)、第18集(钢琴演奏会打脸)',
    totalDurationText: '164分10秒 (单集约1分47秒)',
    coverColor: '#31102F'
  },
  {
    dramaId: 'drama-guzong',
    dramaTitle: '顾总请自重',
    directoryPath: 'D:\\ShortDramaPlatform_V3\\raw_dramas\\顾总请自重_原片库',
    totalEpisodes: 78,
    verifiedMp4Count: 76,
    missingEpisodes: [42, 43],
    corruptedFiles: ['EP39_raw.mp4 (尾部音轨缺失2.4s)'],
    totalSizeGb: 12.1,
    scanStatus: 'missing_files',
    statusSummary: '76/78 集可用 · 缺第42、43集原片，第39集音轨有残缺（跳集规划将自动规避）',
    theaterName: '青柠剧场',
    genreTags: ['女频甜虐', '追妻火葬场', '契约婚姻'],
    historyNames: ['离婚后顾总哭红了眼'],
    mountPlatforms: ['小程序挂载'],
    storySummary: '三年契约婚姻期满，女主潇洒签下离婚协议转身以投行总裁身份收购男主集团30%股份，开启高甜追妻火葬场。',
    climaxEpisodes: '第01集(甩离婚协议)、第12集(投行总裁马甲曝光)、第26集(拍卖会碾压白月光)',
    totalDurationText: '132分40秒 (缺第42、43集)',
    coverColor: '#1E1B4B'
  },
  {
    dramaId: 'drama-kuangbiao',
    dramaTitle: '狂飙天王',
    directoryPath: 'D:\\ShortDramaPlatform_V3\\raw_dramas\\狂飙天王_高清母片',
    totalEpisodes: 100,
    verifiedMp4Count: 100,
    missingEpisodes: [],
    corruptedFiles: [],
    totalSizeGb: 18.6,
    scanStatus: 'ready',
    statusSummary: '100/100 集 MP4 母带校验完整 · 已生成本地ASR对白索引',
    theaterName: '九州剧场',
    genreTags: ['男频热血', '商战风云', '逆袭爽剧'],
    historyNames: ['重返1998当首富'],
    mountPlatforms: ['小程序挂载', '视频号剧集挂载'],
    storySummary: '底层青年凭未来眼光在商海一路狂飙，连破三大财阀围剿登顶江州首富。',
    climaxEpisodes: '第01集(当众立赌约)、第10集(股市翻盘)、第28集(商会封王)',
    totalDurationText: '178分00秒 (100集完整)',
    coverColor: '#172554'
  },
  {
    dramaId: 'drama-tijia',
    dramaTitle: '替嫁娇妻是神医',
    directoryPath: 'D:\\ShortDramaPlatform_V3\\raw_dramas\\替嫁娇妻是神医_原片',
    totalEpisodes: 80,
    verifiedMp4Count: 80,
    missingEpisodes: [],
    corruptedFiles: [],
    totalSizeGb: 13.5,
    scanStatus: 'ready',
    statusSummary: '80/80 集 MP4 母带校验完整 · 含分集高潮时间戳标记',
    theaterName: '点众剧场',
    genreTags: ['女频神医', '替嫁先婚后爱', '虐渣打脸'],
    historyNames: ['替嫁后植物人老公醒了'],
    mountPlatforms: ['小程序挂载'],
    storySummary: '被迫替嫁给植物人豪门家主的女主一手银针妙手回春，联手霸总老公横扫偏心娘家。',
    climaxEpisodes: '第01集(替嫁冲喜)、第06集(银针救醒家主)、第19集(寿宴打脸继母)',
    totalDurationText: '140分15秒 (80集完整)',
    coverColor: '#0F292A'
  }
];

// 初始高光库片段数据（每个高光对应原片中的一个15~35秒具体小片段，默认通过可用，人工快速观看后可淘汰）
export const INITIAL_DRAMA_HIGHLIGHTS: V3DramaHighlightClip[] = [
  {
    id: 'hl-yl-01',
    code: 'H01',
    dramaId: 'drama-yinlong',
    dramaTitle: '隐龙归来',
    episodeLabel: '第01集',
    timeRange: '00:14 - 00:48',
    durationSec: 34,
    durationText: '34秒',
    sceneTag: '寿宴当众撕毁婚书',
    dialogueText: '“区区一个穷酸上门女婿，也配进我江家大门？今天这婚书，我当众撕了！”',
    description: '丈母娘寿宴当众撕毁婚书逼男主下跪，前3秒冲突极强，已验证跑出高转化爆款',
    status: '已通过',
    usedCount: 3,
    isViral: true,
    accentColor: '#991B1B',
    generatedVideoNames: [
      '隐龙归来_跳集高燃_EP01-06_A版.mp4',
      '隐龙归来_R2爆款扩量_EP01-08_跳集1.mp4',
      '隐龙归来_R2爆款扩量_EP01-05_连续2.mp4'
    ]
  },
  {
    id: 'hl-yl-02',
    code: 'H02',
    dramaId: 'drama-yinlong',
    dramaTitle: '隐龙归来',
    episodeLabel: '第07集',
    timeRange: '00:08 - 00:36',
    durationSec: 28,
    durationText: '28秒',
    sceneTag: '慈善晚宴亮黑金龙卡',
    dialogueText: '“睁大你们的狗眼看清楚，这张黑金龙卡，够不够买下你们整座江城商会！”',
    description: '江城慈善晚宴反派逼迫男主下跪，男主亮出黑金龙卡全场震慑',
    status: '已通过',
    usedCount: 1,
    accentColor: '#1E3A8A',
    generatedVideoNames: ['隐龙归来_跳集逆袭_EP07-14_B版.mp4']
  },
  {
    id: 'hl-yl-03',
    code: 'H03',
    dramaId: 'drama-yinlong',
    dramaTitle: '隐龙归来',
    episodeLabel: '第15集',
    timeRange: '00:22 - 00:46',
    durationSec: 24,
    durationText: '24秒',
    sceneTag: '地下拳场签生死状',
    dialogueText: '“生死状我签了！三招之内他还能站着，我把命留在这地下拳场！”',
    description: '地下拳场签生死状切入，动作张力拉满（首轮合成时第19集母带出现黑帧，可重做）',
    status: '已通过',
    usedCount: 1,
    accentColor: '#3B0764',
    generatedVideoNames: ['隐龙归来_跳集悬念_EP15-22_C版.mp4']
  },
  {
    id: 'hl-yl-04',
    code: 'H04',
    dramaId: 'drama-yinlong',
    dramaTitle: '隐龙归来',
    episodeLabel: '第23集',
    timeRange: '00:05 - 00:31',
    durationSec: 26,
    durationText: '26秒',
    sceneTag: '家族祠堂霸气护妻',
    dialogueText: '“今日祠堂开宗，谁敢动她一根汗毛，我让整个江北豪门陪葬！”',
    description: '家族祠堂夺权大会霸气护妻切入，适合长时长高留存成片',
    status: '已通过',
    usedCount: 1,
    accentColor: '#064E3B',
    generatedVideoNames: ['隐龙归来_跳集终局_EP23-30_D版.mp4']
  },
  {
    id: 'hl-yl-05',
    code: 'H05',
    dramaId: 'drama-yinlong',
    dramaTitle: '隐龙归来',
    episodeLabel: '第34集',
    timeRange: '00:11 - 00:33',
    durationSec: 22,
    durationText: '22秒',
    sceneTag: '天台对峙揭晓龙帅身份',
    dialogueText: '“三年前你们把我推下悬崖，可曾想过我就是执掌北境的龙帅！”',
    description: '天台对峙揭晓三年前坠崖真相，情绪爆发力强，尚未投入生产',
    status: '已通过',
    usedCount: 0,
    accentColor: '#0F172A',
    generatedVideoNames: []
  },
  {
    id: 'hl-yl-06',
    code: 'H06',
    dramaId: 'drama-yinlong',
    dramaTitle: '隐龙归来',
    episodeLabel: '第48集',
    timeRange: '00:18 - 00:37',
    durationSec: 19,
    durationText: '19秒',
    sceneTag: '董事会百亿项目反击',
    dialogueText: '“区区百亿项目也拿来威胁我？通知下去，立刻终止与林氏的一切合作！”',
    description: '集团董事会反击前妻家族，节奏明快，适合首轮覆盖测试',
    status: '已通过',
    usedCount: 0,
    accentColor: '#1E293B',
    generatedVideoNames: []
  },
  {
    id: 'hl-yl-07',
    code: 'H07',
    dramaId: 'drama-yinlong',
    dramaTitle: '隐龙归来',
    episodeLabel: '第55集',
    timeRange: '01:02 - 01:20',
    durationSec: 18,
    durationText: '18秒',
    sceneTag: '古玉家产支线文戏',
    dialogueText: '“这枚古玉是当年老太爷亲手交给我母亲的，你们拿什么争！”',
    description: '家产争夺支线铺垫较多，前3秒吸引力偏弱，人工巡检已淘汰',
    status: '已淘汰',
    usedCount: 0,
    accentColor: '#475569',
    generatedVideoNames: []
  },
  // 真千金的绝地逆袭 高光库
  {
    id: 'hl-zqj-01',
    code: 'H01',
    dramaId: 'drama-zhenqianjin',
    dramaTitle: '真千金的绝地逆袭',
    episodeLabel: '第01集',
    timeRange: '00:11 - 00:39',
    durationSec: 28,
    durationText: '28秒',
    sceneTag: '认亲宴红酒反击打脸',
    dialogueText: '“姐姐刚从乡下回来不懂规矩，这杯红酒是我自己不小心洒的，爸妈别怪姐姐！”',
    description: '豪门认亲宴假千金泼红酒绿茶嫁祸，真千金反手一巴掌打脸切入',
    status: '已通过',
    usedCount: 1,
    isViral: true,
    accentColor: '#831843',
    generatedVideoNames: ['真千金的绝地逆袭_连续沉浸_EP01-04.mp4']
  },
  {
    id: 'hl-zqj-02',
    code: 'H02',
    dramaId: 'drama-zhenqianjin',
    dramaTitle: '真千金的绝地逆袭',
    episodeLabel: '第09集',
    timeRange: '00:06 - 00:30',
    durationSec: 24,
    durationText: '24秒',
    sceneTag: '订婚宴投屏DNA鉴定报告',
    dialogueText: '“亲子鉴定报告就在这！当年在医院偷换孩子的人，就是你亲生母亲！”',
    description: '订婚宴大屏幕直接晒出DNA鉴定报告，全场哗然',
    status: '已通过',
    usedCount: 0,
    accentColor: '#4C1D95',
    generatedVideoNames: []
  },
  {
    id: 'hl-zqj-03',
    code: 'H03',
    dramaId: 'drama-zhenqianjin',
    dramaTitle: '真千金的绝地逆袭',
    episodeLabel: '第18集',
    timeRange: '00:15 - 00:37',
    durationSec: 22,
    durationText: '22秒',
    sceneTag: '慈善晚会揭穿假弹穿帮',
    dialogueText: '“你们求着见面的国际首席钢琴大师，远在天边近在眼前！”',
    description: '慈善演奏会假千金假弹穿帮，真千金登台惊艳全场',
    status: '已通过',
    usedCount: 0,
    accentColor: '#1E3A8A',
    generatedVideoNames: []
  },
  // 顾总请自重 高光库
  {
    id: 'hl-gz-01',
    code: 'H01',
    dramaId: 'drama-guzong',
    dramaTitle: '顾总请自重',
    episodeLabel: '第01集',
    timeRange: '00:06 - 00:31',
    durationSec: 25,
    durationText: '25秒',
    sceneTag: '三年期满甩出离婚协议',
    dialogueText: '“顾先生，契约婚姻三年期满，离婚协议我签好了，祝你和白月光百年好合！”',
    description: '女主潇洒甩出离婚协议转身搞事业，追妻火葬场高甜开局',
    status: '已通过',
    usedCount: 1,
    accentColor: '#312E81',
    generatedVideoNames: ['顾总请自重_跳集甜虐_EP01-05.mp4']
  },
  {
    id: 'hl-gz-02',
    code: 'H02',
    dramaId: 'drama-guzong',
    dramaTitle: '顾总请自重',
    episodeLabel: '第12集',
    timeRange: '00:09 - 00:32',
    durationSec: 23,
    durationText: '23秒',
    sceneTag: '神秘投行总裁收购股份',
    dialogueText: '“顾总，夫人刚刚以神秘投行总裁的身份，收购了咱们集团30%的股份！”',
    description: '女主马甲曝光反客为主，男主震惊悔悟',
    status: '已通过',
    usedCount: 0,
    accentColor: '#0F172A',
    generatedVideoNames: []
  }
];

export const CONFIGURABLE_MODEL_OPTIONS = [
  { id: 'gemini-2.5-pro-drama-planner', label: 'Gemini 2.5 Pro (长上下文跨集剧情跳集规划)' },
  { id: 'gemini-2.5-flash-highlight', label: 'Gemini 2.5 Flash (高速台词冲突与高光切入识别)' },
  { id: 'deepseek-r1-storyline-local', label: 'DeepSeek-R1-Distill (本地剧情逻辑链推理)' },
  { id: 'qwen-vl-max-scene', label: 'Qwen-VL-Max (多模态画面卡点与情绪识别)' }
];

// 初始二创生成任务记录 (保留 R1、R2 和成片数据)
export const INITIAL_AI_RUNS: V3ContentAiRun[] = [
  {
    id: 'airun-20261109-03',
    jobCode: 'RMX-20261109-03',
    roundCode: 'R2',
    productionPurpose: '爆款扩量',
    selectedHighlightIds: ['hl-yl-01'],
    basedOnHighlight: '[H01] 第01集 00:14-00:48 丈母娘当众撕毁婚书',
    dramaId: 'drama-yinlong',
    dramaTitle: '隐龙归来',
    sourceDirectory: 'D:\\ShortDramaPlatform_V3\\raw_dramas\\隐龙归来_1080P_母带',
    totalSourceEpisodes: 85,
    sourceFilesStatus: '85集原片完整',
    templateId: 'tpl-mumu-blue',
    templateName: '木木短剧·蓝色版',
    templateVersion: 'mumu-v1.0-blue',
    playStrategy: '跳集播放',
    playStrategies: ['跳集播放', '连续播放'],
    strategyCounts: { '跳集播放': 1, '连续播放': 1 },
    durationRangeMin: [5, 10],
    targetCount: 2,
    modelId: 'gemini-2.5-pro-drama-planner',
    methodVersion: '2026-11-12.3',
    status: 'completed',
    createdAt: '2026-11-09 16:10:00',
    finishedAt: '2026-11-09 16:18:22',
    pipelineSteps: [
      {
        key: 'scan_raw',
        label: '扫描原片',
        status: 'completed',
        durationSec: 2,
        durationText: '2.1s',
        detailText: '校验 85 集 MP4 原片完整'
      },
      {
        key: 'local_recognize',
        label: '本地识别',
        status: 'completed',
        durationSec: 1,
        durationText: '0.6s',
        detailText: '直接复用本剧已缓存的转写时间轴资料'
      },
      {
        key: 'highlight_judge',
        label: '剧情地图',
        status: 'completed',
        durationSec: 2,
        durationText: '1.8s',
        detailText: '读取高光库 [H01] 第01集 00:14-00:48 片段作为固定开头'
      },
      {
        key: 'continuity_plan',
        label: '组合与复核',
        status: 'completed',
        durationSec: 8,
        durationText: '8.4s',
        detailText: '按生产方案生成 1 条跳集版(EP01-08) + 1 条连续版(EP01-05)'
      },
      {
        key: 'video_synthesize',
        label: '视频合成',
        status: 'completed',
        durationSec: 185,
        durationText: '3m 05s',
        detailText: 'FFmpeg 合成 2 条扩量成片，套用 mumu-v1.0-blue 模板'
      },
      {
        key: 'tech_inspect',
        label: '技术检查',
        status: 'completed',
        durationSec: 9,
        durationText: '9.2s',
        detailText: '2 条成片全部通过音画同步与黑帧检测'
      },
      {
        key: 'auto_ingest',
        label: '保存成片',
        status: 'completed',
        durationSec: 2,
        durationText: '1.5s',
        detailText: '已写入成片列表并关联高光 [H01]'
      }
    ],
    results: [
      {
        id: 'res-yl-r2-01',
        jobId: 'airun-20261109-03',
        videoName: '隐龙归来_R2爆款扩量_EP01-08_跳集1.mp4',
        dramaId: 'drama-yinlong',
        dramaTitle: '隐龙归来',
        durationSec: 462,
        durationFormatted: '07分42秒',
        episodeRange: '第01集 ~ 第08集',
        highlightCutPoint: '[H01] 第01集 00:14-00:48 丈母娘当众撕毁婚书',
        sourceHighlightId: 'hl-yl-01',
        sourceHighlightLabel: '[H01] 第01集 00:14-00:48 丈母娘当众撕毁婚书',
        jumpCutPositions: ['第02集 01:40 → 跳第05集 00:10', '第06集 01:50 → 跳第08集 00:05'],
        playStrategy: '跳集播放',
        templateId: 'tpl-mumu-blue',
        templateVersion: 'mumu-v1.0-blue',
        filePath: 'D:\\ShortDramaPlatform_V3\\content_assets\\20261109\\隐龙归来_R2爆款扩量_EP01-08_跳集1.mp4',
        techStatus: '合格',
        techReport: '1080×1920 30fps · 响度 -14.1 LUFS · 无黑屏帧',
        manualStatus: '已通过',
        ingestedAssetId: 'asset-v3-008',
        sourceReasoning: '复用 H01 爆款开头，向后延伸至第8集商会宴会悬念点。',
        previewHue: '#0F172A',
        createdAt: '2026-11-09 16:18',
        isViralHighlight: true
      },
      {
        id: 'res-yl-r2-02',
        jobId: 'airun-20261109-03',
        videoName: '隐龙归来_R2爆款扩量_EP01-05_连续2.mp4',
        dramaId: 'drama-yinlong',
        dramaTitle: '隐龙归来',
        durationSec: 395,
        durationFormatted: '06分35秒',
        episodeRange: '第01集 ~ 第05集 (连续)',
        highlightCutPoint: '[H01] 第01集 00:14-00:48 丈母娘当众撕毁婚书',
        sourceHighlightId: 'hl-yl-01',
        sourceHighlightLabel: '[H01] 第01集 00:14-00:48 丈母娘当众撕毁婚书',
        jumpCutPositions: ['连续播放 · 去片头片尾无缝连播'],
        playStrategy: '连续播放',
        templateId: 'tpl-mumu-blue',
        templateVersion: 'mumu-v1.0-blue',
        filePath: 'D:\\ShortDramaPlatform_V3\\content_assets\\20261109\\隐龙归来_R2爆款扩量_EP01-05_连续2.mp4',
        techStatus: '合格',
        techReport: '1080×1920 30fps · 响度 -14.0 LUFS · 无黑屏帧',
        manualStatus: '已通过',
        ingestedAssetId: 'asset-v3-009',
        sourceReasoning: '复用 H01 爆款开头，采用第1~5集连续无缝播放满足偏好连贯叙事受众。',
        previewHue: '#0F172A',
        createdAt: '2026-11-09 16:18'
      }
    ]
  },
  {
    id: 'airun-20261109-01',
    jobCode: 'RMX-20261109-01',
    roundCode: 'R1',
    productionPurpose: '首轮覆盖',
    selectedHighlightIds: ['hl-yl-01', 'hl-yl-02', 'hl-yl-03', 'hl-yl-04'],
    dramaId: 'drama-yinlong',
    dramaTitle: '隐龙归来',
    sourceDirectory: 'D:\\ShortDramaPlatform_V3\\raw_dramas\\隐龙归来_1080P_母带',
    totalSourceEpisodes: 85,
    sourceFilesStatus: '85集原片完整',
    templateId: 'tpl-mumu-original',
    templateName: '木木短剧·原版配色',
    templateVersion: 'mumu-v1.0',
    playStrategy: '跳集播放',
    playStrategies: ['连续播放', '跳集播放'],
    strategyCounts: { '连续播放': 1, '跳集播放': 3 },
    durationRangeMin: [5, 10],
    targetCount: 4,
    modelId: 'gemini-2.5-pro-drama-planner',
    methodVersion: '2026-11-12.3',
    status: 'partial_failed',
    createdAt: '2026-11-09 14:20:15',
    finishedAt: '2026-11-09 14:32:48',
    pipelineSteps: [
      {
        key: 'scan_raw',
        label: '扫描原片',
        status: 'completed',
        durationSec: 4,
        durationText: '4.2s',
        detailText: '校验 85 集 MP4 原片通过，总时长 148分20秒'
      },
      {
        key: 'local_recognize',
        label: '本地识别',
        status: 'completed',
        durationSec: 38,
        durationText: '38.5s',
        detailText: '完成本地对白时间轴提取与镜头切分点检测'
      },
      {
        key: 'highlight_judge',
        label: '剧情地图',
        status: 'completed',
        durationSec: 19,
        durationText: '19.1s',
        detailText: '识别出 H01~H07 共 7 处高光片段写入高光库'
      },
      {
        key: 'continuity_plan',
        label: '组合与复核',
        status: 'completed',
        durationSec: 14,
        durationText: '14.6s',
        detailText: '基于所选高光 [H01, H02, H03, H04] 生成 4 组叙事方案'
      },
      {
        key: 'video_synthesize',
        label: '视频合成',
        status: 'completed',
        durationSec: 412,
        durationText: '6m 52s',
        detailText: '调用 FFmpeg 硬件加速合成 4 条长成片，套用 mumu-v1.0 模板'
      },
      {
        key: 'tech_inspect',
        label: '技术检查',
        status: 'failed',
        durationSec: 22,
        durationText: '22.0s',
        detailText: '3 条成片通过检查；第 3 条发现跳集衔接处存在 1.8s 静音黑屏帧',
        errorReason: '《隐龙归来_跳集悬念_EP15-22_C版.mp4》在 04:12 处检测到连续 54 帧黑屏与音频断流，已拦截并标记为「技术不合格」'
      },
      {
        key: 'auto_ingest',
        label: '保存成片',
        status: 'completed',
        durationSec: 3,
        durationText: '3.1s',
        detailText: '已将 3 条技术合格成片写入成片库（1条不合格未入可用列表）'
      }
    ],
    results: [
      {
        id: 'res-yl-01',
        jobId: 'airun-20261109-01',
        videoName: '隐龙归来_跳集高燃_EP01-06_A版.mp4',
        dramaId: 'drama-yinlong',
        dramaTitle: '隐龙归来',
        durationSec: 438,
        durationFormatted: '07分18秒',
        episodeRange: '第01集 ~ 第06集',
        highlightCutPoint: '[H01] 第01集 00:14-00:48 丈母娘当众撕毁婚书',
        sourceHighlightId: 'hl-yl-01',
        sourceHighlightLabel: '[H01] 第01集 00:14-00:48 丈母娘当众撕毁婚书',
        jumpCutPositions: [
          '第02集 01:45 → 跳第04集 00:10 (略过街头偶遇支线)',
          '第05集 01:20 → 跳第06集 00:05 (直连龙帅车队降临悬念)'
        ],
        playStrategy: '跳集播放',
        templateId: 'tpl-mumu-original',
        templateVersion: 'mumu-v1.0',
        filePath: 'D:\\ShortDramaPlatform_V3\\content_assets\\20261109\\隐龙归来_跳集高燃_EP01-06_A版.mp4',
        techStatus: '合格',
        techReport: '1080×1920 30fps · 响度 -14.2 LUFS · 无黑屏帧 · 音画同步误差 <15ms',
        manualStatus: '已通过',
        ingestedAssetId: 'asset-v3-001',
        sourceReasoning: '以前3秒婚书撕毁建立情绪压迫，跳过第3集铺垫直奔第4集身份暗线，第6集车队停在门口卡断留钩子。',
        previewHue: '#0F172A',
        createdAt: '2026-11-09 14:32',
        isViralHighlight: true
      },
      {
        id: 'res-yl-02',
        jobId: 'airun-20261109-01',
        videoName: '隐龙归来_跳集逆袭_EP07-14_B版.mp4',
        dramaId: 'drama-yinlong',
        dramaTitle: '隐龙归来',
        durationSec: 512,
        durationFormatted: '08分32秒',
        episodeRange: '第07集 ~ 第14集',
        highlightCutPoint: '[H02] 第07集 00:08-00:42 江城慈善晚宴逼迫下跪',
        sourceHighlightId: 'hl-yl-02',
        sourceHighlightLabel: '[H02] 第07集 00:08-00:42 江城慈善晚宴逼迫下跪',
        jumpCutPositions: [
          '第08集 01:50 → 跳第11集 00:12 (跳过医院回忆桥段)',
          '第12集 02:05 → 跳第14集 00:00 (直达黑卡验资反转高潮)'
        ],
        playStrategy: '跳集播放',
        templateId: 'tpl-mumu-original',
        templateVersion: 'mumu-v1.0',
        filePath: 'D:\\ShortDramaPlatform_V3\\content_assets\\20261109\\隐龙归来_跳集逆袭_EP07-14_B版.mp4',
        techStatus: '合格',
        techReport: '1080×1920 30fps · 响度 -13.8 LUFS · 无黑屏帧 · 字幕安全区合规',
        manualStatus: '已通过',
        ingestedAssetId: 'asset-v3-002',
        sourceReasoning: '聚焦江城晚宴单场景强反转，剔除第9~10集支线人物对话，使8分半钟内包含3次密集爽点。',
        previewHue: '#0F172A',
        createdAt: '2026-11-09 14:32'
      },
      {
        id: 'res-yl-03',
        jobId: 'airun-20261109-01',
        videoName: '隐龙归来_跳集悬念_EP15-22_C版.mp4',
        dramaId: 'drama-yinlong',
        dramaTitle: '隐龙归来',
        durationSec: 365,
        durationFormatted: '06分05秒',
        episodeRange: '第15集 ~ 第22集',
        highlightCutPoint: '[H03] 第15集 00:22-00:56 地下拳场生死状签字',
        sourceHighlightId: 'hl-yl-03',
        sourceHighlightLabel: '[H03] 第15集 00:22-00:56 地下拳场生死状签字',
        jumpCutPositions: [
          '第16集 01:30 → 跳第19集 00:08 (合成点出现黑屏异常)'
        ],
        playStrategy: '跳集播放',
        templateId: 'tpl-mumu-original',
        templateVersion: 'mumu-v1.0',
        filePath: 'D:\\ShortDramaPlatform_V3\\content_assets\\20261109\\隐龙归来_跳集悬念_EP15-22_C版.mp4',
        techStatus: '不合格',
        techReport: '异常拦截：04:12 处存在 1.8s (54帧) 连续黑屏且左声道断流，未通过技术质检',
        manualStatus: '已淘汰',
        sourceReasoning: '拳场对决跨集剪辑，但第19集母带开头存在编码时间戳跳变导致转场黑帧。',
        previewHue: '#0F172A',
        createdAt: '2026-11-09 14:32'
      },
      {
        id: 'res-yl-04',
        jobId: 'airun-20261109-01',
        videoName: '隐龙归来_跳集终局_EP23-30_D版.mp4',
        dramaId: 'drama-yinlong',
        dramaTitle: '隐龙归来',
        durationSec: 564,
        durationFormatted: '09分24秒',
        episodeRange: '第23集 ~ 第30集',
        highlightCutPoint: '[H04] 第23集 00:05-00:39 家族祠堂夺权大会',
        sourceHighlightId: 'hl-yl-04',
        sourceHighlightLabel: '[H04] 第23集 00:05-00:39 家族祠堂夺权大会',
        jumpCutPositions: [
          '第25集 01:55 → 跳第28集 00:15 (略过外围保镖打斗，直切族谱揭秘)'
        ],
        playStrategy: '跳集播放',
        templateId: 'tpl-mumu-original',
        templateVersion: 'mumu-v1.0',
        filePath: 'D:\\ShortDramaPlatform_V3\\content_assets\\20261109\\隐龙归来_跳集终局_EP23-30_D版.mp4',
        techStatus: '合格',
        techReport: '1080×1920 30fps · 响度 -14.0 LUFS · 无黑屏帧 · 完播钩子完整',
        manualStatus: '已通过',
        ingestedAssetId: 'asset-v3-003',
        sourceReasoning: '长时长高留存段落，9分24秒完整覆盖祠堂问责到最终亮明帅印悬念点。',
        previewHue: '#0F172A',
        createdAt: '2026-11-09 14:32'
      }
    ]
  },
  {
    id: 'airun-20261109-02',
    jobCode: 'RMX-20261109-02',
    roundCode: 'R1',
    productionPurpose: '首轮覆盖',
    selectedHighlightIds: ['hl-zqj-01'],
    dramaId: 'drama-zhenqianjin',
    dramaTitle: '真千金的绝地逆袭',
    sourceDirectory: 'D:\\ShortDramaPlatform_V3\\raw_dramas\\真千金的绝地逆袭_全集',
    totalSourceEpisodes: 92,
    sourceFilesStatus: '92集原片完整',
    templateId: 'tpl-mumu-blue',
    templateName: '木木短剧·蓝色版',
    templateVersion: 'mumu-v1.0-blue',
    playStrategy: '连续播放',
    playStrategies: ['连续播放'],
    strategyCounts: { '连续播放': 3, '跳集播放': 0 },
    durationRangeMin: [6, 9],
    targetCount: 3,
    modelId: 'gemini-2.5-flash-highlight',
    methodVersion: '2026-11-12.3',
    status: 'running',
    createdAt: '2026-11-09 15:05:10',
    pipelineSteps: [
      {
        key: 'scan_raw',
        label: '扫描原片',
        status: 'completed',
        durationSec: 5,
        durationText: '5.0s',
        detailText: '已扫描 92 集原片，无缺失损坏'
      },
      {
        key: 'local_recognize',
        label: '本地识别',
        status: 'completed',
        durationSec: 41,
        durationText: '41.2s',
        detailText: '字幕时间轴与情绪峰值曲线识别完成'
      },
      {
        key: 'highlight_judge',
        label: '剧情地图',
        status: 'completed',
        durationSec: 16,
        durationText: '16.4s',
        detailText: '定位真假千金DNA鉴定报告揭晓等 3 个高光片段'
      },
      {
        key: 'continuity_plan',
        label: '组合与复核',
        status: 'completed',
        durationSec: 9,
        durationText: '9.3s',
        detailText: '已基于 [H01] 生成 3 段 6~9 分钟连续播放方案'
      },
      {
        key: 'video_synthesize',
        label: '视频合成',
        status: 'running',
        durationSec: 145,
        durationText: '进行中 (已耗时 2m25s)',
        detailText: '正在渲染第 2/3 条成片《真千金_连续沉浸_EP05-09.mp4》...'
      },
      {
        key: 'tech_inspect',
        label: '技术检查',
        status: 'pending',
        durationText: '等待前序合成',
        detailText: '尚未开始'
      },
      {
        key: 'auto_ingest',
        label: '保存成片',
        status: 'pending',
        durationText: '等待技术质检',
        detailText: '待技术检查合格后自动写入成片库'
      }
    ],
    results: [
      {
        id: 'res-zqj-01',
        jobId: 'airun-20261109-02',
        videoName: '真千金的绝地逆袭_连续沉浸_EP01-04.mp4',
        dramaId: 'drama-zhenqianjin',
        dramaTitle: '真千金的绝地逆袭',
        durationSec: 468,
        durationFormatted: '07分48秒',
        episodeRange: '第01集 ~ 第04集 (连续无缝)',
        highlightCutPoint: '[H01] 第01集 00:11-00:44 豪门认亲宴泼红酒反击',
        sourceHighlightId: 'hl-zqj-01',
        sourceHighlightLabel: '[H01] 第01集 00:11-00:44 豪门认亲宴泼红酒反击',
        jumpCutPositions: ['连续播放 · 自动裁除第1~4集片尾重复回放帧'],
        playStrategy: '连续播放',
        templateId: 'tpl-mumu-blue',
        templateVersion: 'mumu-v1.0-blue',
        filePath: 'D:\\ShortDramaPlatform_V3\\content_assets\\20261109\\真千金的绝地逆袭_连续沉浸_EP01-04.mp4',
        techStatus: '合格',
        techReport: '1080×1920 30fps · 响度 -14.0 LUFS · 无黑屏帧',
        manualStatus: '已通过',
        sourceReasoning: '前4集剧情高度连贯，裁掉每集末尾3秒重复镜头后形成7分48秒完整叙事流。',
        previewHue: '#0F172A',
        createdAt: '2026-11-09 15:07'
      }
    ]
  }
];
