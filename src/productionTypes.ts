// Production Center Types (Business-Driven Model)

export type ProductionTaskStage = 
  | 'materials'          // 素材阶段
  | 'template'           // 模板阶段
  | 'videos'             // 成片生成与导出
  | 'release_registered' // 发布登记完成
  | 'completed';         // 已完成

export type TemplateStatus = 
  | 'not_generated'      // 未生成
  | 'generating'         // 正在生成草稿
  | 'draft_ready'        // 草稿已生成 / 待导出
  | 'exporting'          // 导出中
  | 'generated'          // 已导出
  | 'error';             // 异常

export type VideoClipStatus = 
  | 'not_generated'      // 未生成
  | 'draft_generating'   // 草稿生成中
  | 'draft_ready'        // 草稿已生成
  | 'pending_export'     // 待导出
  | 'exporting'          // 导出中
  | 'exported'           // 已导出
  | 'error';             // 异常

export interface ScannedMaterialClip {
  id: string;
  sequenceNumber: number;   // 递增序号 (1, 2, 3...)，不复用
  title: string;            // e.g. 辣厨回乡鲜椒越香店越旺-1 (无书名号)
  dramaPrefix: string;      // 纯剧名，用于截断渲染时保留 -n
  durationSec: number;      // 时长秒数
  durationText: string;     // e.g. 09:57
  fileSizeText: string;     // e.g. 40MB
  thumbnailUrl?: string;    // 缩略图
  videoUrl?: string;        // 预览播放地址
  filePath?: string;        // 完整文件路径 (仅用于 Tooltip / 详情查看)
  scannedAt: string;
  isValid: boolean;
}

export interface ProductionVideoItem {
  id: string;
  sequenceNumber: number;   // 1, 2, 3...
  title: string;            // e.g. 辣厨回乡鲜椒越香店越旺-1
  dramaPrefix: string;      // 纯剧名
  durationSec: number;      // 视频时长 (秒)
  fileSizeText: string;     // e.g. 18MB 或 —
  status: VideoClipStatus;
  draftDuration: string;    // 成片草稿耗时，如 '1分18秒' 或 '—'
  exportDuration: string;   // 导出耗时，如 '2分06秒' 或 '—'
  capcutDraftName: string;  // 对应剪映草稿工程名
  outputFilePath?: string;
  exportProgress?: number;  // 0-100
  errorMessage?: string;
  thumbnailUrl?: string;
}

export interface ProductionUnit {
  id: string; // e.g. "prod-acc1-drama1"
  accountId: string;
  accountName: string;
  dramaId: string;
  dramaName: string;
  coverUrl?: string;
  
  // 计划与状态
  scheduledDate: string;     // 日期，如 "2026-08-22", "2026-08-23"
  scheduledTime: string;     // 如 "8月22日 19:30", "今天 18:30", "明天 09:00"
  sortTimestamp: number;     // 排序时间戳
  isOverdue?: boolean;       // 是否逾期未完成
  isCompleted: boolean;      // 是否已登记发布 (已登记发布即已完成)
  currentStage: ProductionTaskStage;
  
  // 1. 素材区域 (Material-driven)
  materialFolder: string;
  materialsCount: number;
  pendingMaterialCount?: number; // 素材目录中尚未扫描登记的有效视频数量
  nextMaterialSequence: number; // 下一个可用素材序号，确保重扫或加素材不复用旧序号
  scannedMaterials: ScannedMaterialClip[];
  
  // 2. 独立模板区域 (Account × Drama = 独立模板)
  templateStatus: TemplateStatus;
  templateDraftName?: string;
  templateVideoUrl?: string;
  templateDurationSec?: number;
  templateDurationText?: string; // e.g. "02:36"
  templateFileSizeText?: string; // e.g. "58MB"
  templateDraftDuration?: string;
  templateExportDuration?: string;
  templateUpdatedAt?: string;
  templateErrorMessage?: string;
  
  // 3. 素材驱动的成片列表
  videos: ProductionVideoItem[];
  
  // 4. 导出检查与监听
  exportInspectionMode: boolean; // 成片导出检查 (默认 false)
  isListeningExport: boolean;    // 是否处于后台文件监听状态 (用户在剪映中手动取消后继续静默监听)
  listeningMessage?: string;
  
  // 5. 发布登记 (发布阶段)
  outputFolder: string;
  releaseStatus: 'unregistered' | 'registered'; // 未登记发布 / 已登记发布
  actualReleaseTime?: string;   // 实际登记发布时间，如 "今天 18:30" 或 "今天 19:10"
  
  lastUpdated: string;
}

export interface CleanupItemDetail {
  name: string;
  sizeMb: number;
  sizeText: string;
  description?: string;
}

export interface CleanupPreviewData {
  isRegisteredRelease: boolean; // 是否已登记发布 (true: 立即清理, false: 删除剧集)
  taskTitle: string;
  accountName: string;
  dramaName: string;
  currentStage: string;
  canExecute: boolean;
  estimatedSpaceMb: number;
  estimatedSpaceText: string;
  itemsToDelete: CleanupItemDetail[];
  itemsToRetain: string[];
  blockingReason?: string;
}
