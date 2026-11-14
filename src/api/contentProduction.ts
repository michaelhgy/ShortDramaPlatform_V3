/**
 * V3 内容生产 - 原剧二创、通版模板与 AI 规划任务接口契约
 * 对应后端表：v3_content_templates, v3_content_ai_runs
 * 对应后端服务：server/drama_remix.py, server/v2_file_service.py
 */

export type PlayContinuityMode = '连续播放' | '跳集播放';
export type StrategyCounts = Record<PlayContinuityMode, number>;

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
  highlightCutPoint: string;      // 高光切入点，例如 "第01集 00:18 退婚亮明身份高潮切入"
  highlightId?: string;           // 剧目高光库中的稳定来源 ID
  jumpCutPositions: string[];     // 跳集位置，例如 ["第02集 02:15 → 跳第05集 00:08", "第05集 01:52 → 跳第07集 00:15"]
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
}

// v3_content_templates 通版模板版本
export interface V3ContentTemplate {
  id: string;
  name: string;
  version: string;
  description: string;
  aspectRatio: '9:16' | '16:9';
  resolution: string;
  subtitlePreset: string;
  antiDuplicateLayer: string;
  updatedAt: string;
  rendererTemplateId?: string;
  titlePolicy?: string;
}

// 原剧原片目录扫描状态
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
}

// v3_content_ai_runs 模型判断与二创生成任务记录
export interface V3ContentAiRun {
  id: string;
  jobCode: string;
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
  productionPurpose?: '首轮覆盖' | '失败重做' | '爆款扩量' | '策略测试' | string;
  highlightIds?: string[];
  highlightLibraryVersion?: string;
  highlightCount?: number;
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

export type HighlightLibraryItemStatus = 'candidate' | 'confirmed' | 'used' | 'paused' | 'retired';

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
  boundaryStatus: 'ready' | 'needs_boundary_review' | string;
  status: HighlightLibraryItemStatus;
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

// 通版模板预设库 (v3_content_templates)
export const INITIAL_V3_TEMPLATES: V3ContentTemplate[] = [
  {
    id: 'tpl-mumu-original',
    name: '木木短剧·原版配色',
    version: 'mumu-v1.0',
    description: '原版斜切标题板 + 木木短剧品牌条，标题自动换名',
    aspectRatio: '9:16',
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
    resolution: '1080×1920 (30fps)',
    subtitlePreset: '红色版标题板字形',
    antiDuplicateLayer: '静态品牌模板层',
    updatedAt: '2026-11-10',
    rendererTemplateId: 'mumu-red',
    titlePolicy: '按标题板宽度自动缩小，必要时按标点换两行'
  }
];

// 原剧目录扫描字典
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
    statusSummary: '85/85 集 MP4 母带校验完整 · 含内置SRT时间轴字幕与音频轨'
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
    statusSummary: '92/92 集 MP4 母带校验完整 · 音画同步率 100%'
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
    statusSummary: '76/78 集可用 · 缺第42、43集原片，第39集音轨有残缺（跳集规划将自动规避）'
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
    statusSummary: '100/100 集 MP4 母带校验完整 · 已生成本地ASR对白索引'
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
    statusSummary: '80/80 集 MP4 母带校验完整 · 含分集高潮时间戳标记'
  }
];

// 可配置的任务规划模型列表 (支持用户在界面新增或自由输入模型ID，不写死)
export const CONFIGURABLE_MODEL_OPTIONS = [
  { id: 'gemini-2.5-pro-drama-planner', label: 'Gemini 2.5 Pro (长上下文跨集剧情跳集规划)' },
  { id: 'gemini-2.5-flash-highlight', label: 'Gemini 2.5 Flash (高速台词冲突与高光切入识别)' },
  { id: 'deepseek-r1-storyline-local', label: 'DeepSeek-R1-Distill (本地剧情逻辑链推理)' },
  { id: 'qwen-vl-max-scene', label: 'Qwen-VL-Max (多模态画面卡点与情绪识别)' }
];

// 初始二创生成任务记录 (v3_content_ai_runs) — 包含进行中、部分异常、已完成真实状态，绝不伪造全部完成
export const INITIAL_AI_RUNS: V3ContentAiRun[] = [
  {
    id: 'airun-20261109-01',
    jobCode: 'RMX-20261109-01',
    dramaId: 'drama-yinlong',
    dramaTitle: '隐龙归来',
    sourceDirectory: 'D:\\ShortDramaPlatform_V3\\raw_dramas\\隐龙归来_1080P_母带',
    totalSourceEpisodes: 85,
    sourceFilesStatus: '85集原片完整',
    templateId: 'tpl-v3-general-02',
    templateName: '剧场组件挂载·高完播通版',
    templateVersion: 'v3.5.0-Pro',
    playStrategy: '跳集播放',
    durationRangeMin: [5, 10],
    targetCount: 4,
    modelId: 'gemini-2.5-pro-drama-planner',
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
        label: '高光判断',
        status: 'completed',
        durationSec: 19,
        durationText: '19.1s',
        detailText: '识别出 12 处强冲突切入点（退婚、亮出龙戒、拍卖会打脸等）'
      },
      {
        key: 'continuity_plan',
        label: '连续/跳集规划',
        status: 'completed',
        durationSec: 14,
        durationText: '14.6s',
        detailText: '生成 4 组跳集叙事方案（剔除过场水词，保留核心悬念钩子）'
      },
      {
        key: 'video_synthesize',
        label: '视频合成',
        status: 'completed',
        durationSec: 412,
        durationText: '6m 52s',
        detailText: '调用 FFmpeg 硬件加速合成 4 条长成片，套用 v3.5.0-Pro 模板'
      },
      {
        key: 'tech_inspect',
        label: '技术检查',
        status: 'failed',
        durationSec: 22,
        durationText: '22.0s',
        detailText: '3 条成片通过检查；第 3 条发现跳集衔接处存在 1.8s 静音黑屏帧',
        errorReason: '《隐龙归来_跳集二创_03.mp4》在 04:12 处检测到连续 54 帧黑屏与音频断流，已拦截自动入库并标记为「技术不合格」'
      },
      {
        key: 'auto_ingest',
        label: '自动入库',
        status: 'completed',
        durationSec: 3,
        durationText: '3.1s',
        detailText: '已将 3 条技术合格成片写入 v3_content_assets 成片库（1条不合格未入库）'
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
        highlightCutPoint: '第01集 00:14 丈母娘当众撕毁婚书高潮切入',
        jumpCutPositions: [
          '第02集 01:45 → 跳第04集 00:10 (略过街头偶遇支线)',
          '第05集 01:20 → 跳第06集 00:05 (直连龙帅车队降临悬念)'
        ],
        playStrategy: '跳集播放',
        templateId: 'tpl-v3-general-02',
        templateVersion: 'v3.5.0-Pro',
        filePath: 'D:\\ShortDramaPlatform_V3\\content_assets\\20261109\\隐龙归来_跳集高燃_EP01-06_A版.mp4',
        techStatus: '合格',
        techReport: '1080×1920 60fps · 响度 -14.2 LUFS · 无黑屏帧 · 音画同步误差 <15ms',
        manualStatus: '已通过',
        ingestedAssetId: 'asset-v3-001',
        sourceReasoning: '以前3秒婚书撕毁建立情绪压迫，跳过第3集铺垫直奔第4集身份暗线，第6集车队停在门口卡断留钩子。',
        previewHue: 'from-indigo-900 via-slate-900 to-purple-950',
        createdAt: '2026-11-09 14:32'
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
        highlightCutPoint: '第07集 00:08 江城慈善晚宴反派逼迫下跪切入',
        jumpCutPositions: [
          '第08集 01:50 → 跳第11集 00:12 (跳过医院回忆桥段)',
          '第12集 02:05 → 跳第14集 00:00 (直达黑卡验资反转高潮)'
        ],
        playStrategy: '跳集播放',
        templateId: 'tpl-v3-general-02',
        templateVersion: 'v3.5.0-Pro',
        filePath: 'D:\\ShortDramaPlatform_V3\\content_assets\\20261109\\隐龙归来_跳集逆袭_EP07-14_B版.mp4',
        techStatus: '合格',
        techReport: '1080×1920 60fps · 响度 -13.8 LUFS · 无黑屏帧 · 字幕安全区合规',
        manualStatus: '待审核',
        ingestedAssetId: 'asset-v3-002',
        sourceReasoning: '聚焦江城晚宴单场景强反转，剔除第9~10集支线人物对话，使8分半钟内包含3次密集爽点。',
        previewHue: 'from-slate-900 via-indigo-950 to-emerald-950',
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
        highlightCutPoint: '第15集 00:22 地下拳场生死状签字切入',
        jumpCutPositions: [
          '第16集 01:30 → 跳第19集 00:08 (合成点出现黑屏异常)'
        ],
        playStrategy: '跳集播放',
        templateId: 'tpl-v3-general-02',
        templateVersion: 'v3.5.0-Pro',
        filePath: 'D:\\ShortDramaPlatform_V3\\content_assets\\20261109\\隐龙归来_跳集悬念_EP15-22_C版.mp4',
        techStatus: '不合格',
        techReport: '异常拦截：04:12 处存在 1.8s (54帧) 连续黑屏且左声道断流，未通过技术质检',
        manualStatus: '已淘汰',
        sourceReasoning: '拳场对决跨集剪辑，但第19集母带开头存在编码时间戳跳变导致转场黑帧。',
        previewHue: 'from-rose-950 via-slate-900 to-stone-900',
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
        highlightCutPoint: '第23集 00:05 家族祠堂夺权大会切入',
        jumpCutPositions: [
          '第25集 01:55 → 跳第28集 00:15 (略过外围保镖打斗，直切族谱揭秘)'
        ],
        playStrategy: '跳集播放',
        templateId: 'tpl-v3-general-02',
        templateVersion: 'v3.5.0-Pro',
        filePath: 'D:\\ShortDramaPlatform_V3\\content_assets\\20261109\\隐龙归来_跳集终局_EP23-30_D版.mp4',
        techStatus: '合格',
        techReport: '1080×1920 60fps · 响度 -14.0 LUFS · 无黑屏帧 · 完播钩子完整',
        manualStatus: '待审核',
        ingestedAssetId: 'asset-v3-003',
        sourceReasoning: '长时长高留存段落，9分24秒完整覆盖祠堂问责到最终亮明帅印悬念点。',
        previewHue: 'from-purple-950 via-slate-900 to-indigo-950',
        createdAt: '2026-11-09 14:32'
      }
    ]
  },
  {
    id: 'airun-20261109-02',
    jobCode: 'RMX-20261109-02',
    dramaId: 'drama-zhenqianjin',
    dramaTitle: '真千金的绝地逆袭',
    sourceDirectory: 'D:\\ShortDramaPlatform_V3\\raw_dramas\\真千金的绝地逆袭_全集',
    totalSourceEpisodes: 92,
    sourceFilesStatus: '92集原片完整',
    templateId: 'tpl-v3-general-01',
    templateName: '微信视频号·沉浸全屏通版',
    templateVersion: 'v3.4.2-Std',
    playStrategy: '连续播放',
    durationRangeMin: [6, 9],
    targetCount: 3,
    modelId: 'gemini-2.5-flash-highlight',
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
        label: '高光判断',
        status: 'completed',
        durationSec: 16,
        durationText: '16.4s',
        detailText: '定位真假千金DNA鉴定报告揭晓等 8 个高光切入点'
      },
      {
        key: 'continuity_plan',
        label: '连续/跳集规划',
        status: 'completed',
        durationSec: 9,
        durationText: '9.3s',
        detailText: '已生成 3 段 6~9 分钟连续播放去片头片尾无缝拼接方案'
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
        detailText: '尚未开始（不提前伪造已完成状态）'
      },
      {
        key: 'auto_ingest',
        label: '自动入库',
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
        highlightCutPoint: '第01集 00:11 豪门认亲宴假千金泼红酒嫁祸切入',
        jumpCutPositions: ['连续播放 · 自动裁除第1~4集片尾重复回放帧'],
        playStrategy: '连续播放',
        templateId: 'tpl-v3-general-01',
        templateVersion: 'v3.4.2-Std',
        filePath: 'D:\\ShortDramaPlatform_V3\\content_assets\\20261109\\真千金的绝地逆袭_连续沉浸_EP01-04.mp4',
        techStatus: '待检查',
        techReport: '合成完毕，等待本批全部合成后统一执行声画质检',
        manualStatus: '待审核',
        sourceReasoning: '前4集剧情高度连贯，裁掉每集末尾3秒重复镜头后形成7分48秒完整叙事流。',
        previewHue: 'from-fuchsia-950 via-slate-900 to-indigo-950',
        createdAt: '2026-11-09 15:07'
      }
    ]
  }
];
