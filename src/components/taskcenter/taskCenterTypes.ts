export type TaskCategory = 'template' | 'final_video';

export type DraftStageStatus = 'waiting' | 'running' | 'done' | 'error' | 'timeout';

export type VideoStageStatus = 'idle' | 'waiting' | 'running' | 'done' | 'error' | 'timeout';

export type TaskStatus = 'running' | 'waiting' | 'done' | 'timeout' | 'error';

// Compatibility types for executor identification
export type TaskType = 'template_draft' | 'final_draft' | 'video_export';
export type TaskSubType = 'template_video_export' | 'final_video_export';

export type ExecutorId = 'video_exporter' | 'final_generator' | 'template_generator';

export interface ExecutorInfo {
  id: ExecutorId;
  name: string;
  subtitle: string;
  description: string;
  status: 'running' | 'idle' | 'waiting';
  currentTaskId: string | null;
  runningSeconds: number;
  isTimeout: boolean;
  timeoutThresholdSeconds: number;
  queueStats: {
    completed: number;
    running: number;
    waiting: number;
    total: number;
    timeoutCount: number;
  };
}

export interface TaskItem {
  id: string;
  // Core Business Identity
  taskCategory: TaskCategory; // 'template' | 'final_video'
  accountName: string; // e.g. "微雨问海棠火"
  dramaName: string; // e.g. "风雪草原苍狼少女"
  materialName?: string; // e.g. "素材01", "素材02"
  materialFullName?: string; // e.g. "风雪草原_草原夜袭骑射开场_01s.mp4"
  title: string; // e.g. "微雨问海棠火 × 《风雪草原苍狼少女》 · 素材01"
  
  // Pipeline Stages (The 2 authentic steps within a single task)
  draftStage: {
    status: DraftStageStatus; // 'waiting' | 'running' | 'done' | 'error' | 'timeout'
    progress?: number; // 0 - 100
    durationFormatted?: string;
    errorDetail?: string;
  };
  videoStage: {
    status: VideoStageStatus; // 'idle' | 'waiting' | 'running' | 'done' | 'error' | 'timeout'
    progress?: number; // 0 - 100
    durationFormatted?: string;
    errorDetail?: string;
  };

  // Scheduling & Priority
  scheduledPublishTime: string; // e.g. "18:00"
  priorityRank: number; // 1 = highest
  priorityTag?: string; // e.g. "优先 #1", "模板优先"
  
  // High-level status & timing
  status: TaskStatus; // overall status ('running' | 'waiting' | 'done' | 'timeout' | 'error')
  progress: number; // 0 - 100
  createdAt: string;
  startedAt?: string;
  completedAt?: string;
  durationSeconds: number;
  durationFormatted: string;
  isTimeout: boolean;

  /** Runtime facts supplied by the V1 adapter; never inferred from UI actions. */
  hasValidDraft?: boolean;
  hasCompletedFirstExport?: boolean;
  isOrphan?: boolean;
  
  // Compatibility executor fields
  taskType?: TaskType;
  taskSubType?: TaskSubType;
  executorId: ExecutorId;
  executorName: string;
  
  // File paths & Diagnostics
  draftPath?: string;
  outputPath?: string;
  fileSizeMb?: number;
  diagnosticLog?: string;
  errorDetail?: string;
  
  stageInfo?: {
    currentStage: string;
    stepIndex: number;
    totalSteps: number;
  };
}

export interface DramaSchedulePriority {
  dramaName: string;
  scheduledPublishTime: string;
  priorityRank: number;
  startedAt: string;
  totalTasks: number;
  completedTasks: number;
  isSupplementing?: boolean;
}
