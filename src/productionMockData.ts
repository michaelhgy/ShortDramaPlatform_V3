import { ProductionUnit, ScannedMaterialClip, ProductionVideoItem } from './productionTypes';

// Helper to generate 26 realistic materials for a drama
function generate26Materials(dramaName: string, baseSec: number = 600): ScannedMaterialClip[] {
  const clips: ScannedMaterialClip[] = [];
  const covers = [
    'https://images.unsplash.com/photo-1534447677768-be436bb09401?w=300&auto=format&fit=crop&q=80',
    'https://images.unsplash.com/photo-1485846234645-a62644f84728?w=300&auto=format&fit=crop&q=80',
    'https://images.unsplash.com/photo-1478720568477-152d9b164e26?w=300&auto=format&fit=crop&q=80',
    'https://images.unsplash.com/photo-1518709268805-4e9042af9f23?w=300&auto=format&fit=crop&q=80',
    'https://images.unsplash.com/photo-1536440136628-849c177e76a1?w=300&auto=format&fit=crop&q=80',
    'https://images.unsplash.com/photo-1509198397868-475647b2a1e5?w=300&auto=format&fit=crop&q=80',
  ];

  for (let i = 1; i <= 26; i++) {
    const durationSec = baseSec + (i * 17) % 180;
    const min = Math.floor(durationSec / 60);
    const sec = durationSec % 60;
    const durationText = `${min < 10 ? '0' + min : min}:${sec < 10 ? '0' + sec : sec}`;
    const fileSizeText = `${38 + ((i * 11) % 35)}MB`;

    clips.push({
      id: `mat-${dramaName}-${i}`,
      sequenceNumber: i,
      title: `${dramaName}-${i}`,
      dramaPrefix: dramaName,
      durationSec,
      durationText,
      fileSizeText,
      thumbnailUrl: covers[(i - 1) % covers.length],
      filePath: `D:/DramaAssets/Materials/${dramaName}/Segment_${i < 10 ? '0' + i : i}.mp4`,
      scannedAt: '09:30',
      isValid: true,
    });
  }
  return clips;
}

// Helper to generate 26 realistic video clips corresponding to materials
function generate26Videos(
  dramaName: string,
  exportedCount: number = 18,
  exportingIndex: number = 19,
  draftReadyCount: number = 24
): ProductionVideoItem[] {
  const videos: ProductionVideoItem[] = [];

  for (let i = 1; i <= 26; i++) {
    const durationSec = 85 + (i * 7) % 25; // 85s - 105s
    let status: ProductionVideoItem['status'] = 'not_generated';
    let draftDuration = '—';
    let exportDuration = '—';
    let exportProgress = 0;
    let fileSizeText = '—';
    let errorMessage: string | undefined;

    if (i <= exportedCount) {
      status = 'exported';
      draftDuration = `${1 + (i % 2)}分${10 + (i * 3) % 40}秒`;
      exportDuration = `${1 + (i % 2)}分${40 + (i * 5) % 30}秒`;
      exportProgress = 100;
      fileSizeText = `${18 + ((i * 7) % 20)}MB`;
    } else if (i === exportingIndex) {
      status = 'exporting';
      draftDuration = '1分15秒';
      exportDuration = '—';
      exportProgress = 62;
      fileSizeText = '—';
    } else if (i <= draftReadyCount) {
      status = 'draft_ready';
      draftDuration = '1分12秒';
      exportDuration = '—';
      exportProgress = 0;
      fileSizeText = '—';
    } else {
      status = 'not_generated';
      draftDuration = '—';
      exportDuration = '—';
      exportProgress = 0;
      fileSizeText = '—';
    }

    videos.push({
      id: `vid-${dramaName}-${i}`,
      sequenceNumber: i,
      title: `${dramaName}-${i}`,
      dramaPrefix: dramaName,
      durationSec,
      fileSizeText,
      status,
      draftDuration,
      exportDuration,
      capcutDraftName: `Draft_${dramaName}_EP${i < 10 ? '0' + i : i}`,
      outputFilePath: `D:/DramaOutput/${dramaName}_EP${i < 10 ? '0' + i : i}.mp4`,
      exportProgress,
      errorMessage,
    });
  }
  return videos;
}

// 12 Realistic Production Units matching user specification:
// Accounts: 短剧黄鸡版, 鸿记水产行, 冷脸萌萌1701, 曾经几何7906, 肯德基等你爱你, 格格芝LE
// Dramas: 风雪草原苍狼少女, 辣厨回乡鲜椒越香店越旺, 坠海逢生我率万鲨踏浪归来, 我用十元盒饭惊艳全城, 惨遭同行背叛百年野猪认我为王, 我在武侠世界抽卡成神
export const INITIAL_PRODUCTION_UNITS: ProductionUnit[] = [
  // 1. 逾期未完成 (短剧黄鸡版 × 风雪草原苍狼少女)
  {
    id: 'prod-unit-1',
    accountId: 'acc-huangji',
    accountName: '短剧黄鸡版',
    dramaId: 'drama-canglang',
    dramaName: '风雪草原苍狼少女',
    coverUrl: 'https://images.unsplash.com/photo-1534447677768-be436bb09401?w=400&auto=format&fit=crop&q=80',
    scheduledDate: '2026-08-22',
    scheduledTime: '8月22日 19:30',
    sortTimestamp: 1771760000000,
    isOverdue: true,
    isCompleted: false,
    currentStage: 'videos',
    materialFolder: 'D:/DramaAssets/Materials/风雪草原苍狼少女/短剧黄鸡版',
    materialsCount: 26,
    nextMaterialSequence: 27,
    scannedMaterials: generate26Materials('风雪草原苍狼少女', 610),
    templateStatus: 'generated',
    templateDraftName: 'Jianying_风雪草原苍狼少女_短剧黄鸡版_Master',
    templateDurationText: '02:36',
    templateFileSizeText: '58MB',
    templateDraftDuration: '1分18秒',
    templateExportDuration: '2分06秒',
    templateUpdatedAt: '昨日 20:00',
    videos: generate26Videos('风雪草原苍狼少女', 15, 16, 22),
    exportInspectionMode: false,
    isListeningExport: false,
    outputFolder: 'D:/DramaOutput/短剧黄鸡版/风雪草原苍狼少女/',
    releaseStatus: 'unregistered',
    lastUpdated: '昨日 20:15',
  },

  // 2. 逾期未完成 (鸿记水产行 × 辣厨回乡鲜椒越香店越旺)
  {
    id: 'prod-unit-2',
    accountId: 'acc-hongji',
    accountName: '鸿记水产行',
    dramaId: 'drama-lachu',
    dramaName: '辣厨回乡鲜椒越香店越旺',
    coverUrl: 'https://images.unsplash.com/photo-1555396273-367ea4eb4db5?w=400&auto=format&fit=crop&q=80',
    scheduledDate: '2026-08-22',
    scheduledTime: '8月22日 21:00',
    sortTimestamp: 1771765400000,
    isOverdue: true,
    isCompleted: false,
    currentStage: 'videos',
    materialFolder: 'D:/DramaAssets/Materials/辣厨回乡/鸿记水产行',
    materialsCount: 26,
    nextMaterialSequence: 27,
    scannedMaterials: generate26Materials('辣厨回乡鲜椒越香店越旺', 580),
    templateStatus: 'generated',
    templateDraftName: 'Jianying_辣厨回乡_鸿记水产行_Master',
    templateDurationText: '02:15',
    templateFileSizeText: '52MB',
    templateDraftDuration: '1分10秒',
    templateExportDuration: '1分48秒',
    templateUpdatedAt: '昨日 21:30',
    videos: generate26Videos('辣厨回乡鲜椒越香店越旺', 12, 13, 20),
    exportInspectionMode: false,
    isListeningExport: false,
    outputFolder: 'D:/DramaOutput/鸿记水产行/辣厨回乡/',
    releaseStatus: 'unregistered',
    lastUpdated: '昨日 21:40',
  },

  // 3. 今天 18:30 (短剧黄鸡版 × 坠海逢生我率万鲨踏浪归来 - 同一账号第2部剧)
  {
    id: 'prod-unit-3',
    accountId: 'acc-huangji',
    accountName: '短剧黄鸡版',
    dramaId: 'drama-wansha',
    dramaName: '坠海逢生我率万鲨踏浪归来',
    coverUrl: 'https://images.unsplash.com/photo-1518709268805-4e9042af9f23?w=400&auto=format&fit=crop&q=80',
    scheduledDate: '2026-08-23',
    scheduledTime: '今天 18:30',
    sortTimestamp: 1771842600000,
    isOverdue: false,
    isCompleted: false,
    currentStage: 'videos',
    materialFolder: 'D:/DramaAssets/Materials/坠海逢生/短剧黄鸡版',
    materialsCount: 26,
    nextMaterialSequence: 27,
    scannedMaterials: generate26Materials('坠海逢生我率万鲨踏浪归来', 620),
    templateStatus: 'generated',
    templateDraftName: 'Jianying_坠海逢生_短剧黄鸡版_Master',
    templateDraftDuration: '1分22秒',
    templateExportDuration: '2分12秒',
    templateUpdatedAt: '10:30',
    videos: generate26Videos('坠海逢生我率万鲨踏浪归来', 18, 19, 25),
    exportInspectionMode: false,
    isListeningExport: false,
    outputFolder: 'D:/DramaOutput/短剧黄鸡版/坠海逢生/',
    releaseStatus: 'unregistered',
    lastUpdated: '10:45',
  },

  // 4. 今天 19:00 (冷脸萌萌1701 × 我用十元盒饭惊艳全城)
  {
    id: 'prod-unit-4',
    accountId: 'acc-lengliang',
    accountName: '冷脸萌萌1701',
    dramaId: 'drama-hefan',
    dramaName: '我用十元盒饭惊艳全城',
    coverUrl: 'https://images.unsplash.com/photo-1498654896293-37aacf113fd9?w=400&auto=format&fit=crop&q=80',
    scheduledDate: '2026-08-23',
    scheduledTime: '今天 19:00',
    sortTimestamp: 1771844400000,
    isOverdue: false,
    isCompleted: false,
    currentStage: 'videos',
    materialFolder: 'D:/DramaAssets/Materials/十元盒饭/冷脸萌萌1701',
    materialsCount: 26,
    nextMaterialSequence: 27,
    scannedMaterials: generate26Materials('我用十元盒饭惊艳全城', 540),
    templateStatus: 'generated',
    templateDraftName: 'Jianying_十元盒饭_冷脸萌萌_Master',
    templateDraftDuration: '1分08秒',
    templateExportDuration: '1分45秒',
    templateUpdatedAt: '11:15',
    videos: generate26Videos('我用十元盒饭惊艳全城', 20, 21, 26),
    exportInspectionMode: false,
    isListeningExport: true,
    listeningMessage: '正在静默监听目标输出文件：Draft_十元盒饭_EP21.mp4。用户可在剪映调整草稿后直接导出，系统检测到有效文件将自动继续。',
    outputFolder: 'D:/DramaOutput/冷脸萌萌1701/十元盒饭/',
    releaseStatus: 'unregistered',
    lastUpdated: '11:30',
  },

  // 5. 今天 20:00 (曾经几何7906 × 惨遭同行背叛百年野猪认我为王)
  {
    id: 'prod-unit-5',
    accountId: 'acc-cengjing',
    accountName: '曾经几何7906',
    dramaId: 'drama-yezhu',
    dramaName: '惨遭同行背叛百年野猪认我为王',
    coverUrl: 'https://images.unsplash.com/photo-1478720568477-152d9b164e26?w=400&auto=format&fit=crop&q=80',
    scheduledDate: '2026-08-23',
    scheduledTime: '今天 20:00',
    sortTimestamp: 1771848000000,
    isOverdue: false,
    isCompleted: false,
    currentStage: 'videos',
    materialFolder: 'D:/DramaAssets/Materials/百年野猪/曾经几何7906',
    materialsCount: 26,
    nextMaterialSequence: 27,
    scannedMaterials: generate26Materials('惨遭同行背叛百年野猪认我为王', 590),
    templateStatus: 'generated',
    templateDraftName: 'Jianying_百年野猪_曾经几何_Master',
    templateDraftDuration: '1分14秒',
    templateExportDuration: '1分52秒',
    templateUpdatedAt: '12:00',
    videos: generate26Videos('惨遭同行背叛百年野猪认我为王', 10, 11, 18),
    exportInspectionMode: true,
    isListeningExport: false,
    outputFolder: 'D:/DramaOutput/曾经几何7906/百年野猪/',
    releaseStatus: 'unregistered',
    lastUpdated: '12:15',
  },

  // 6. 今天 21:00 (肯德基等你爱你 × 我在武侠世界抽卡成神)
  {
    id: 'prod-unit-6',
    accountId: 'acc-kfc',
    accountName: '肯德基等你爱你',
    dramaId: 'drama-wuxia',
    dramaName: '我在武侠世界抽卡成神',
    coverUrl: 'https://images.unsplash.com/photo-1509198397868-475647b2a1e5?w=400&auto=format&fit=crop&q=80',
    scheduledDate: '2026-08-23',
    scheduledTime: '今天 21:00',
    sortTimestamp: 1771851600000,
    isOverdue: false,
    isCompleted: false,
    currentStage: 'videos',
    materialFolder: 'D:/DramaAssets/Materials/武侠抽卡/肯德基等你爱你',
    materialsCount: 26,
    nextMaterialSequence: 27,
    scannedMaterials: generate26Materials('我在武侠世界抽卡成神', 650),
    templateStatus: 'generated',
    templateDraftName: 'Jianying_武侠抽卡_肯德基_Master',
    templateDraftDuration: '1分25秒',
    templateExportDuration: '2分15秒',
    templateUpdatedAt: '13:00',
    videos: generate26Videos('我在武侠世界抽卡成神', 8, 9, 16),
    exportInspectionMode: false,
    isListeningExport: false,
    outputFolder: 'D:/DramaOutput/肯德基等你爱你/武侠抽卡/',
    releaseStatus: 'unregistered',
    lastUpdated: '13:20',
  },

  // 7. 今天 21:30 (格格芝LE × 风雪草原苍狼少女 - 同一部剧分配给不同账号)
  {
    id: 'prod-unit-7',
    accountId: 'acc-gegezhi',
    accountName: '格格芝LE',
    dramaId: 'drama-canglang',
    dramaName: '风雪草原苍狼少女',
    coverUrl: 'https://images.unsplash.com/photo-1534447677768-be436bb09401?w=400&auto=format&fit=crop&q=80',
    scheduledDate: '2026-08-23',
    scheduledTime: '今天 21:30',
    sortTimestamp: 1771853400000,
    isOverdue: false,
    isCompleted: false,
    currentStage: 'template',
    materialFolder: 'D:/DramaAssets/Materials/风雪草原苍狼少女/格格芝LE',
    materialsCount: 26,
    nextMaterialSequence: 27,
    scannedMaterials: generate26Materials('风雪草原苍狼少女', 610),
    templateStatus: 'draft_ready',
    templateDraftName: 'Jianying_风雪草原苍狼少女_格格芝LE_Master',
    templateDurationText: '02:30',
    templateFileSizeText: '55MB',
    templateDraftDuration: '1分16秒',
    templateExportDuration: '—',
    templateUpdatedAt: '14:00',
    videos: generate26Videos('风雪草原苍狼少女', 0, 0, 8),
    exportInspectionMode: false,
    isListeningExport: false,
    outputFolder: 'D:/DramaOutput/格格芝LE/风雪草原苍狼少女/',
    releaseStatus: 'unregistered',
    lastUpdated: '14:00',
  },

  // 8. 今天 22:00 (短剧黄鸡版 × 辣厨回乡鲜椒越香店越旺 - 短剧黄鸡版第3部剧)
  {
    id: 'prod-unit-8',
    accountId: 'acc-huangji',
    accountName: '短剧黄鸡版',
    dramaId: 'drama-lachu',
    dramaName: '辣厨回乡鲜椒越香店越旺',
    coverUrl: 'https://images.unsplash.com/photo-1555396273-367ea4eb4db5?w=400&auto=format&fit=crop&q=80',
    scheduledDate: '2026-08-23',
    scheduledTime: '今天 22:00',
    sortTimestamp: 1771855200000,
    isOverdue: false,
    isCompleted: false,
    currentStage: 'materials',
    materialFolder: 'D:/DramaAssets/Materials/辣厨回乡/短剧黄鸡版',
    materialsCount: 26,
    nextMaterialSequence: 27,
    scannedMaterials: generate26Materials('辣厨回乡鲜椒越香店越旺', 580),
    templateStatus: 'not_generated',
    videos: generate26Videos('辣厨回乡鲜椒越香店越旺', 0, 0, 0),
    exportInspectionMode: false,
    isListeningExport: false,
    outputFolder: 'D:/DramaOutput/短剧黄鸡版/辣厨回乡/',
    releaseStatus: 'unregistered',
    lastUpdated: '14:30',
  },

  // 9. 明天 09:00 (鸿记水产行 × 我用十元盒饭惊艳全城 - 鸿记水产行第2部剧)
  {
    id: 'prod-unit-9',
    accountId: 'acc-hongji',
    accountName: '鸿记水产行',
    dramaId: 'drama-hefan',
    dramaName: '我用十元盒饭惊艳全城',
    coverUrl: 'https://images.unsplash.com/photo-1498654896293-37aacf113fd9?w=400&auto=format&fit=crop&q=80',
    scheduledDate: '2026-08-24',
    scheduledTime: '明天 09:00',
    sortTimestamp: 1771894800000,
    isOverdue: false,
    isCompleted: false,
    currentStage: 'materials',
    materialFolder: 'D:/DramaAssets/Materials/十元盒饭/鸿记水产行',
    materialsCount: 26,
    nextMaterialSequence: 27,
    scannedMaterials: generate26Materials('我用十元盒饭惊艳全城', 540),
    templateStatus: 'not_generated',
    videos: generate26Videos('我用十元盒饭惊艳全城', 0, 0, 0),
    exportInspectionMode: false,
    isListeningExport: false,
    outputFolder: 'D:/DramaOutput/鸿记水产行/十元盒饭/',
    releaseStatus: 'unregistered',
    lastUpdated: '15:00',
  },

  // 10. 明天 11:30 (曾经几何7906 × 我在武侠世界抽卡成神 - 曾经几何第2部剧)
  {
    id: 'prod-unit-10',
    accountId: 'acc-cengjing',
    accountName: '曾经几何7906',
    dramaId: 'drama-wuxia',
    dramaName: '我在武侠世界抽卡成神',
    coverUrl: 'https://images.unsplash.com/photo-1509198397868-475647b2a1e5?w=400&auto=format&fit=crop&q=80',
    scheduledDate: '2026-08-24',
    scheduledTime: '明天 11:30',
    sortTimestamp: 1771903800000,
    isOverdue: false,
    isCompleted: false,
    currentStage: 'materials',
    materialFolder: 'D:/DramaAssets/Materials/武侠抽卡/曾经几何7906',
    materialsCount: 26,
    nextMaterialSequence: 27,
    scannedMaterials: generate26Materials('我在武侠世界抽卡成神', 650),
    templateStatus: 'not_generated',
    videos: generate26Videos('我在武侠世界抽卡成神', 0, 0, 0),
    exportInspectionMode: false,
    isListeningExport: false,
    outputFolder: 'D:/DramaOutput/曾经几何7906/武侠抽卡/',
    releaseStatus: 'unregistered',
    lastUpdated: '15:20',
  },

  // 11. 已完成 (已登记发布) - 肯德基等你爱你 × 坠海逢生我率万鲨踏浪归来 (排在未完成任务之后)
  {
    id: 'prod-unit-11-completed',
    accountId: 'acc-kfc',
    accountName: '肯德基等你爱你',
    dramaId: 'drama-wansha',
    dramaName: '坠海逢生我率万鲨踏浪归来',
    coverUrl: 'https://images.unsplash.com/photo-1518709268805-4e9042af9f23?w=400&auto=format&fit=crop&q=80',
    scheduledDate: '2026-08-23',
    scheduledTime: '今天 12:00',
    sortTimestamp: 1771819200000,
    isOverdue: false,
    isCompleted: true,
    currentStage: 'completed',
    materialFolder: 'D:/DramaAssets/Materials/坠海逢生/肯德基等你爱你',
    materialsCount: 26,
    nextMaterialSequence: 27,
    scannedMaterials: generate26Materials('坠海逢生我率万鲨踏浪归来', 620),
    templateStatus: 'generated',
    templateDraftName: 'Jianying_坠海逢生_肯德基_Master',
    templateDraftDuration: '1分15秒',
    templateExportDuration: '1分55秒',
    templateUpdatedAt: '12:10',
    videos: generate26Videos('坠海逢生我率万鲨踏浪归来', 26, 0, 26),
    exportInspectionMode: false,
    isListeningExport: false,
    outputFolder: 'D:/DramaOutput/肯德基等你爱你/坠海逢生/',
    releaseStatus: 'registered',
    actualReleaseTime: '今天 12:00',
    lastUpdated: '12:20',
  },

  // 12. 已完成 (已登记发布) - 格格芝LE × 惨遭同行背叛百年野猪认我为王 (排在未完成任务之后)
  {
    id: 'prod-unit-12-completed',
    accountId: 'acc-gegezhi',
    accountName: '格格芝LE',
    dramaId: 'drama-yezhu',
    dramaName: '惨遭同行背叛百年野猪认我为王',
    coverUrl: 'https://images.unsplash.com/photo-1478720568477-152d9b164e26?w=400&auto=format&fit=crop&q=80',
    scheduledDate: '2026-08-23',
    scheduledTime: '今天 14:00',
    sortTimestamp: 1771826400000,
    isOverdue: false,
    isCompleted: true,
    currentStage: 'completed',
    materialFolder: 'D:/DramaAssets/Materials/百年野猪/格格芝LE',
    materialsCount: 26,
    nextMaterialSequence: 27,
    scannedMaterials: generate26Materials('惨遭同行背叛百年野猪认我为王', 590),
    templateStatus: 'generated',
    templateDraftName: 'Jianying_百年野猪_格格芝LE_Master',
    templateDraftDuration: '1分12秒',
    templateExportDuration: '1分50秒',
    templateUpdatedAt: '14:15',
    videos: generate26Videos('惨遭同行背叛百年野猪认我为王', 26, 0, 26),
    exportInspectionMode: false,
    isListeningExport: false,
    outputFolder: 'D:/DramaOutput/格格芝LE/百年野猪/',
    releaseStatus: 'registered',
    actualReleaseTime: '今天 14:20',
    lastUpdated: '14:30',
  }
];
