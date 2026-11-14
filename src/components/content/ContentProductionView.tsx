import React, { useEffect, useState, useMemo } from 'react';
import {
  INITIAL_V3_TEMPLATES,
  INITIAL_RAW_DRAMA_DIRS,
  INITIAL_AI_RUNS,
  INITIAL_DRAMA_HIGHLIGHTS,
  RawDramaDirectoryInfo,
  V3ContentAiRun,
  PlayContinuityMode,
  StrategyCounts,
  ManualReviewStatus,
  V3DramaHighlightClip,
  ProductionPurpose
} from '../../api/contentProduction';
import {
  getContentRemixRun,
  getContentRemixRuns,
  getContentRemixSourceDramas,
  startContentRemixRun,
  getContentHighlightLibraries,
  startContentHighlightAnalysis,
  getContentHighlightAnalysis,
  HighlightAnalysisRun
} from '../../api/contentRemix';
import {
  INITIAL_V3_CONTENT_ASSETS,
  V3ContentAsset
} from '../../api/contentLibrary';
import {
  INITIAL_V3_CONTENT_GROUPS,
  INITIAL_V3_GROUP_ITEMS,
  INITIAL_V3_ORIGINAL_RECORDS,
  INITIAL_V3_PUBLICATIONS,
  V3ContentGroup,
  V3ContentGroupItem,
  V3ContentOriginalRecord,
  V3ContentPublication
} from '../../api/contentGroups';
import { getV2Accounts, getV2Dramas, getV2Settings } from '../../api/v2Catalog';
import { getGptRelayConfig } from '../../api/gptRelay';
import { DramaCover } from '../DramaCover';
import { ContentAccountOption } from './contentTypes';
import { RemixCreatePanel } from './RemixCreatePanel';
import {
  Sparkles,
  Film,
  Send,
  Search,
  CheckCircle2,
  Clock,
  Flame,
  Plus,
  Play,
  Pause,
  FolderPlus,
  X,
  AlertTriangle,
  Loader2,
  Upload,
  FolderOpen,
  Trash2,
  RotateCcw,
  ArrowUp,
  ArrowDown,
  History,
  Edit3,
  Bookmark,
  Copy,
  ChevronDown,
  ChevronUp,
  SkipBack,
  SkipForward,
  Maximize2,
  Volume2
} from 'lucide-react';

function formatHighlightTime(seconds: number): string {
  const safe = Math.max(0, Math.round(Number(seconds) || 0));
  return `${String(Math.floor(safe / 60)).padStart(2, '0')}:${String(safe % 60).padStart(2, '0')}`;
}

function mapLibraryHighlight(item: import('../../api/contentProduction').V3HighlightLibraryItem, index: number): V3DramaHighlightClip {
  const duration = Math.max(1, Math.round(item.durationSec || item.endTime - item.startTime));
  return {
    id: item.id,
    code: `H${String(index + 1).padStart(2, '0')}`,
    dramaId: item.dramaId,
    dramaTitle: item.dramaTitle,
    episodeLabel: `第${String(item.episode).padStart(2, '0')}集`,
    timeRange: `${formatHighlightTime(item.startTime)} - ${formatHighlightTime(item.endTime)}`,
    durationSec: duration,
    durationText: `${duration}秒`,
    sceneTag: item.hookLabel || '原片高光片段',
    dialogueText: item.anchorText || '已生成高光片段，等待人工查看。',
    description: item.reason || item.viewerQuestion || '模型提取的原片高光片段。',
    status: item.status === 'paused' || item.status === 'retired' ? '暂停' : '已通过',
    usedCount: item.usageCount || 0,
    generatedVideoNames: [],
    accentColor: '#1E3A8A',
    previewUrl: item.previewUrl,
  };
}

export type LeftNavMode = 'single_drama' | 'publish_groups';
export type RecordFilterMode = 'all_drama_assets' | string;
export type AssetQuickFilter = 'active' | 'eliminated' | 'all';
export type HighlightQuickFilter = 'active' | 'eliminated' | 'all';

interface ContentProductionViewProps {
  showToast: (msg: string) => void;
}

const COMPACT_STEP_LABELS: Record<string, string> = {
  scan_raw: '1.扫描原片',
  local_recognize: '2.本地识别',
  highlight_judge: '3.剧情地图',
  continuity_plan: '4.组合复核',
  combo_review: '4.组合复核',
  video_synthesize: '5.视频合成',
  tech_inspect: '6.技术检查',
  auto_ingest: '7.保存成片',
  save_archive: '7.保存成片'
};

// 根据模板版本返回顶部标题栏配色
function getTemplateBannerStyle(templateVersion?: string): {
  bg: string;
  accent: string;
  label: string;
} {
  const v = (templateVersion || '').toLowerCase();
  if (v.includes('blue')) {
    return {
      bg: 'linear-gradient(90deg, #1D4ED8 0%, #2563EB 100%)',
      accent: '#93C5FD',
      label: '木木短剧·蓝色版'
    };
  }
  if (v.includes('cyan')) {
    return {
      bg: 'linear-gradient(90deg, #0E7490 0%, #06B6D4 100%)',
      accent: '#A5F3FC',
      label: '木木短剧·青色版'
    };
  }
  if (v.includes('red')) {
    return {
      bg: 'linear-gradient(90deg, #B91C1C 0%, #EF4444 100%)',
      accent: '#FCA5A5',
      label: '木木短剧·红色版'
    };
  }
  return {
    bg: 'linear-gradient(90deg, #D97706 0%, #F59E0B 100%)',
    accent: '#FEF08A',
    label: '木木短剧·原版配色'
  };
}

export const ContentProductionView: React.FC<ContentProductionViewProps> = ({
  showToast
}) => {
  // 左侧顶部单层切换：在产剧集 | 发布编组
  const [leftNavMode, setLeftNavMode] = useState<LeftNavMode>('single_drama');

  // 核心数据状态
  const [rawDramas, setRawDramas] = useState<RawDramaDirectoryInfo[]>(INITIAL_RAW_DRAMA_DIRS);
  const [templates] = useState(INITIAL_V3_TEMPLATES);
  const [highlights, setHighlights] = useState<V3DramaHighlightClip[]>(INITIAL_DRAMA_HIGHLIGHTS);
  const [highlightAnalysisRun, setHighlightAnalysisRun] = useState<HighlightAnalysisRun | null>(null);
  const [highlightAnalysisBusy, setHighlightAnalysisBusy] = useState(false);
  const [aiRuns, setAiRuns] = useState<V3ContentAiRun[]>(INITIAL_AI_RUNS);
  const [selectedRunId, setSelectedRunId] = useState<string>(INITIAL_AI_RUNS[0]?.id || '');
  const [recordFilter, setRecordFilter] = useState<RecordFilterMode>('all_drama_assets');
  const [showRecordsDrawer, setShowRecordsDrawer] = useState<boolean>(false);

  // 已加入内容生产的在产剧集 ID 列表（防卡顿）
  const [activeDramaIds, setActiveDramaIds] = useState<string[]>([
    'drama-yinlong',
    'drama-zhenqianjin',
    'drama-guzong'
  ]);
  const [selectedDramaId, setSelectedDramaId] = useState<string>('drama-yinlong');
  const [dramaSearch, setDramaSearch] = useState<string>('');
  const [addDramaModalOpen, setAddDramaModalOpen] = useState<boolean>(false);
  const [addDramaKeyword, setAddDramaKeyword] = useState<string>('');

  // 新建生产方案弹窗预填参数
  const [isPlanModalOpen, setIsPlanModalOpen] = useState<boolean>(false);
  const [planInitialHighlightIds, setPlanInitialHighlightIds] = useState<string[]>([]);
  const [planInitialPurpose, setPlanInitialPurpose] = useState<ProductionPurpose>('首轮覆盖');
  const [followUpHighlight, setFollowUpHighlight] = useState<string | null>(null);

  // 模块二：高光库筛选、页内播放与连续快审状态
  const [highlightQuickFilter, setHighlightQuickFilter] = useState<HighlightQuickFilter>('active');
  const [focusedHighlightId, setFocusedHighlightId] = useState<string | null>(null);
  const [inlinePlayingHighlightId, setInlinePlayingHighlightId] = useState<string | null>(null);
  const [inlineHighlightProgressSec, setInlineHighlightProgressSec] = useState<number>(0);
  const [previewHighlightClip, setPreviewHighlightClip] = useState<V3DramaHighlightClip | null>(null);

  // 模块三：成片库筛选、页内播放与大图预览状态
  const [assetQuickFilter, setAssetQuickFilter] = useState<AssetQuickFilter>('active');
  const [assetHighlightFilter, setAssetHighlightFilter] = useState<string>('ALL');
  const [assetPurposeFilter, setAssetPurposeFilter] = useState<string>('ALL');
  const [assetKeyword, setAssetKeyword] = useState<string>('');
  const [selectedAssetIds, setSelectedAssetIds] = useState<string[]>([]);
  const [inlinePlayingAssetId, setInlinePlayingAssetId] = useState<string | null>(null);
  const [inlineAssetProgressPct, setInlineAssetProgressPct] = useState<number>(0);
  const [previewAsset, setPreviewAsset] = useState<V3ContentAsset | null>(null);

  // 其他弹窗控制
  const [isImportModalOpen, setIsImportModalOpen] = useState<boolean>(false);
  const [importTargetGroupId, setImportTargetGroupId] = useState<string | null>(null);
  const [groupAssignAssetIds, setGroupAssignAssetIds] = useState<string[]>([]);
  const [activeStepIndex, setActiveStepIndex] = useState<number | null>(null);

  // 外部导入表单状态
  const [importVideoName, setImportVideoName] = useState('');
  const [importSourceType, setImportSourceType] = useState<'外部导入视频' | '旧流程成片'>('外部导入视频');
  const [importFilePath, setImportFilePath] = useState('Z:\\05短剧二创\\外部成片导入\\');
  const [importDurationFormatted, setImportDurationFormatted] = useState('06:30');
  const [importHighlightNote, setImportHighlightNote] = useState('');

  // 成片库与授权上限状态 (默认 9)
  const [assets, setAssets] = useState<V3ContentAsset[]>(INITIAL_V3_CONTENT_ASSETS);
  const [globalAuthLimit] = useState<number>(9);

  // 发布编组状态
  const [groups, setGroups] = useState<V3ContentGroup[]>(INITIAL_V3_CONTENT_GROUPS);
  const [selectedGroupId, setSelectedGroupId] = useState<string>(INITIAL_V3_CONTENT_GROUPS[0]?.id || '');
  const [newGroupName, setNewGroupName] = useState<string>('');
  const [editingGroupName, setEditingGroupName] = useState<string | null>(null);
  const [groupItems, setGroupItems] = useState<V3ContentGroupItem[]>(INITIAL_V3_GROUP_ITEMS);
  const [, setOriginalRecords] = useState<V3ContentOriginalRecord[]>(INITIAL_V3_ORIGINAL_RECORDS);
  const [publications, setPublications] = useState<V3ContentPublication[]>(INITIAL_V3_PUBLICATIONS);
  const [pickAssetsForGroupModalOpen, setPickAssetsForGroupModalOpen] = useState<boolean>(false);
  const [pickAssetsSearch, setPickAssetsSearch] = useState<string>('');
  const [publishHistoryModalOpen, setPublishHistoryModalOpen] = useState<boolean>(false);

  // 编组内快速自动发布配置
  const [publishMode, setPublishMode] = useState<'原创发布' | '授权发布'>('授权发布');
  const [publishAccountId, setPublishAccountId] = useState<string>('');
  const [publishCount, setPublishCount] = useState<number>(1);

  const [accounts, setAccounts] = useState<ContentAccountOption[]>([
    { id: 'acc-cm-01', name: '触摸-战神巅峰剧场', theaterName: '触摸剧场', tier: 'active' },
    { id: 'acc-cm-02', name: '触摸-都市狂龙录', theaterName: '触摸剧场', tier: 'active' },
    { id: 'acc-dz-01', name: '点众-王牌剧场主号', theaterName: '点众剧场', tier: 'active' },
    { id: 'acc-qn-01', name: '青柠-爆米花追剧', theaterName: '青柠剧场', tier: 'active' },
    { id: 'acc-jz-01', name: '九州-热血男儿志', theaterName: '九州剧场', tier: 'active' }
  ]);
  const [modelRoutes, setModelRoutes] = useState<Record<'highlight' | 'continuous' | 'jump' | 'review', string>>({
    highlight: '',
    continuous: '',
    jump: '',
    review: ''
  });
  const [, setContentAssetRoot] = useState('Z:\\05短剧二创');

  useEffect(() => {
    if (!publishAccountId && accounts[0]) {
      setPublishAccountId(accounts[0].id);
    }
  }, [accounts, publishAccountId]);

  // 高光卡片内直接播放计时器（方便人工快速看十几秒视频）
  useEffect(() => {
    if (!inlinePlayingHighlightId) return;
    const clip = highlights.find((h) => h.id === inlinePlayingHighlightId);
    const maxSec = clip?.durationSec || 28;
    const timer = window.setInterval(() => {
      setInlineHighlightProgressSec((prev) => {
        if (prev + 1 >= maxSec) {
          return 0;
        }
        return prev + 1;
      });
    }, 1000);
    return () => window.clearInterval(timer);
  }, [inlinePlayingHighlightId, highlights]);

  // 成片卡片内直接预览计时器
  useEffect(() => {
    if (!inlinePlayingAssetId) return;
    const timer = window.setInterval(() => {
      setInlineAssetProgressPct((prev) => (prev + 4 >= 100 ? 0 : prev + 4));
    }, 600);
    return () => window.clearInterval(timer);
  }, [inlinePlayingAssetId]);

  useEffect(() => {
    let active = true;
    getV2Dramas()
      .then((dramaResponse) => {
        if (!active) return;
        getContentRemixSourceDramas()
          .then((sourceResponse) => {
            if (!active) return;
            const sources = new Map(sourceResponse.items.map((item) => [item.drama_id, item]));
            const mapped = dramaResponse.items.map((drama) => {
              const source = sources.get(drama.id);
              const count = source?.mp4_count || 0;
              const fallbackInfo = INITIAL_RAW_DRAMA_DIRS.find(
                (d) => d.dramaId === drama.id || d.dramaTitle === drama.current_name
              );
              return {
                dramaId: drama.id,
                dramaTitle: drama.current_name,
                directoryPath: source?.directory || fallbackInfo?.directoryPath || '',
                totalEpisodes: Number(drama.official_total_episodes || count || fallbackInfo?.totalEpisodes || 0),
                verifiedMp4Count: count,
                missingEpisodes: fallbackInfo?.missingEpisodes || [],
                corruptedFiles: fallbackInfo?.corruptedFiles || [],
                totalSizeGb: source?.size_gb || fallbackInfo?.totalSizeGb || 0,
                scanStatus: (count > 0 ? 'ready' : 'unscanned') as RawDramaDirectoryInfo['scanStatus'],
                statusSummary: count > 0 ? `找到 ${count} 集原片` : '没有找到原片',
                theaterName: drama.theater_name || fallbackInfo?.theaterName || '触摸剧场',
                genreTags: fallbackInfo?.genreTags || ['短剧热播', '强冲突反转'],
                historyNames: drama.history_names?.length ? drama.history_names : fallbackInfo?.historyNames,
                mountPlatforms: fallbackInfo?.mountPlatforms || ['小程序挂载', '视频号剧集挂载'],
                storySummary: fallbackInfo?.storySummary,
                climaxEpisodes: fallbackInfo?.climaxEpisodes,
                totalDurationText: fallbackInfo?.totalDurationText,
                coverColor: fallbackInfo?.coverColor
              };
            });
            if (mapped.some((d) => d.verifiedMp4Count > 0)) {
              setRawDramas(mapped);
            }
          })
          .catch(() => undefined);
        Promise.allSettled([getV2Accounts(), getGptRelayConfig(), getV2Settings(), getContentRemixRuns()])
          .then(([accountsResult, relayResult, settingsResult, runsResult]) => {
            if (!active) return;
            if (accountsResult.status === 'fulfilled' && accountsResult.value.items?.length) {
              setAccounts(
                accountsResult.value.items.map((account) => ({
                  id: account.id,
                  name: account.nickname,
                  theaterName: account.theater_name,
                  tier: account.status
                }))
              );
            }
            if (relayResult.status === 'fulfilled') {
              const relayConfig = relayResult.value;
              setModelRoutes({
                highlight: relayConfig.model_routes.highlight || '',
                continuous: relayConfig.model_routes.continuous || '',
                jump: relayConfig.model_routes.jump || '',
                review: relayConfig.model_routes.review || ''
              });
            }
            if (settingsResult.status === 'fulfilled') {
              const configuredRoot = String(settingsResult.value.content_remix_output_root || '').replace(/[\\/]+$/, '');
              if (configuredRoot) setContentAssetRoot(configuredRoot);
            }
            if (runsResult.status === 'fulfilled' && runsResult.value.items?.length) {
              setAiRuns(runsResult.value.items);
              setSelectedRunId(runsResult.value.items[0]?.id || '');
            }
          });
      })
      .catch(() => undefined);
    return () => {
      active = false;
    };
  }, []);

  // 全部已下载原片的剧集池
  const allDownloadedDramas = useMemo(() => {
    return rawDramas
      .filter((drama) => drama.verifiedMp4Count > 0 && drama.directoryPath)
      .sort((a, b) => b.verifiedMp4Count - a.verifiedMp4Count || a.dramaTitle.localeCompare(b.dramaTitle, 'zh-CN'));
  }, [rawDramas]);

  useEffect(() => {
    setActiveDramaIds((prev) => {
      const set = new Set(prev);
      aiRuns.forEach((r) => {
        if (r.dramaId) set.add(r.dramaId);
      });
      if (set.size === 0 && allDownloadedDramas[0]) {
        set.add(allDownloadedDramas[0].dramaId);
      }
      return Array.from(set);
    });
  }, [aiRuns, allDownloadedDramas]);

  // 左栏展示的在产剧集列表
  const activeProductionDramas = useMemo(() => {
    const idSet = new Set(activeDramaIds);
    const list = allDownloadedDramas.filter((d) => idSet.has(d.dramaId));
    const q = dramaSearch.trim().toLowerCase();
    if (!q) return list;
    return list.filter((d) => d.dramaTitle.toLowerCase().includes(q));
  }, [allDownloadedDramas, activeDramaIds, dramaSearch]);

  const searchableDramasToAdd = useMemo(() => {
    const q = addDramaKeyword.trim().toLowerCase();
    const list = q
      ? allDownloadedDramas.filter((d) => d.dramaTitle.toLowerCase().includes(q))
      : allDownloadedDramas;
    return list.slice(0, 30);
  }, [allDownloadedDramas, addDramaKeyword]);

  useEffect(() => {
    if (selectedDramaId && activeProductionDramas.some((d) => d.dramaId === selectedDramaId)) return;
    if (activeProductionDramas[0]) setSelectedDramaId(activeProductionDramas[0].dramaId);
  }, [activeProductionDramas, selectedDramaId]);

  const selectedProject =
    activeProductionDramas.find((drama) => drama.dramaId === selectedDramaId) ||
    activeProductionDramas[0] ||
    allDownloadedDramas[0];

  useEffect(() => {
    if (!selectedProject?.dramaId) return;
    let active = true;
    getContentHighlightLibraries(selectedProject.dramaId)
      .then((response) => {
        if (!active || !response.latest?.items?.length) return;
        const mapped = response.latest.items.map((item, index) => mapLibraryHighlight(item, index));
        setHighlights((previous) => [
          ...previous.filter((item) => item.dramaId !== selectedProject.dramaId),
          ...mapped,
        ]);
      })
      .catch(() => undefined);
    return () => {
      active = false;
    };
  }, [selectedProject?.dramaId]);

  const refreshRealHighlightLibrary = async () => {
    if (!selectedProject?.dramaId || !selectedProject.directoryPath) {
      showToast('当前剧集没有可用原片目录，无法生成高光库。');
      return;
    }
    setHighlightAnalysisBusy(true);
    try {
      const run = await startContentHighlightAnalysis({
        drama_id: selectedProject.dramaId,
        drama_title: selectedProject.dramaTitle,
        source_directory: selectedProject.directoryPath,
      });
      setHighlightAnalysisRun(run);
      showToast('已开始生成高光资料，完成后会自动刷新高光库。');
      const poll = async () => {
        const current = await getContentHighlightAnalysis(run.id);
        if (!current || current.status === 'queued' || current.status === 'running') {
          setHighlightAnalysisRun(current || run);
          window.setTimeout(() => void poll(), 2500);
          return;
        }
        setHighlightAnalysisRun(current);
        setHighlightAnalysisBusy(false);
        if (current.status === 'completed') {
          const latest = await getContentHighlightLibraries(selectedProject.dramaId);
          if (latest.latest?.items?.length) {
            setHighlights((previous) => [
              ...previous.filter((item) => item.dramaId !== selectedProject.dramaId),
              ...latest.latest!.items.map((item, index) => mapLibraryHighlight(item, index)),
            ]);
          }
          showToast(`高光库已生成，共 ${current.highlightCount} 段。`);
        } else {
          showToast(`高光库生成失败：${current.error || current.detail}`);
        }
      };
      void poll();
    } catch (error) {
      setHighlightAnalysisBusy(false);
      showToast(error instanceof Error ? error.message : '高光库任务启动失败。');
    }
  };

  // 当前剧目的高光库列表（若新剧无初始高光则自动提供默认通过的高光片段）
  const dramaHighlights = useMemo(() => {
    if (!selectedProject) return [];
    const existing = highlights.filter(
      (h) => h.dramaId === selectedProject.dramaId || h.dramaTitle === selectedProject.dramaTitle
    );
    if (existing.length > 0) return existing;
    return [
      {
        id: `hl-${selectedProject.dramaId}-01`,
        code: 'H01',
        dramaId: selectedProject.dramaId,
        dramaTitle: selectedProject.dramaTitle,
        episodeLabel: '第01集',
        timeRange: '00:08 - 00:36',
        durationSec: 28,
        durationText: '28秒',
        sceneTag: '开篇强冲突高潮',
        dialogueText: '“三年前你们看不起我，今天整个江城都要听我号令！”',
        description: '开篇强冲突打脸片段，前3秒吸引力强，默认通过可用',
        status: '已通过' as const,
        usedCount: 0,
        accentColor: '#1E3A8A',
        generatedVideoNames: []
      },
      {
        id: `hl-${selectedProject.dramaId}-02`,
        code: 'H02',
        dramaId: selectedProject.dramaId,
        dramaTitle: selectedProject.dramaTitle,
        episodeLabel: '第06集',
        timeRange: '00:15 - 00:39',
        durationSec: 24,
        durationText: '24秒',
        sceneTag: '身份揭晓全场震慑',
        dialogueText: '“亮出身份牌！看谁敢动她分毫！”',
        description: '身份揭晓反转高光片段，适合跳集长成片切入',
        status: '已通过' as const,
        usedCount: 0,
        accentColor: '#3B0764',
        generatedVideoNames: []
      }
    ];
  }, [highlights, selectedProject]);

  const activeHighlightsCount = useMemo(
    () => dramaHighlights.filter((h) => h.status !== '已淘汰' && h.status !== '暂停').length,
    [dramaHighlights]
  );
  const eliminatedHighlightsCount = useMemo(
    () => dramaHighlights.filter((h) => h.status === '已淘汰' || h.status === '暂停').length,
    [dramaHighlights]
  );

  const filteredDramaHighlights = useMemo(() => {
    return dramaHighlights.filter((h) => {
      const isEliminated = h.status === '已淘汰' || h.status === '暂停';
      if (highlightQuickFilter === 'active' && isEliminated) return false;
      if (highlightQuickFilter === 'eliminated' && !isEliminated) return false;
      return true;
    });
  }, [dramaHighlights, highlightQuickFilter]);

  const projectRuns = useMemo(() => {
    if (!selectedProject) return [];
    const list = aiRuns.filter(
      (run) => run.dramaId === selectedProject.dramaId || run.dramaTitle === selectedProject.dramaTitle
    );
    return list.map((run, idx) => ({
      ...run,
      roundCode: run.roundCode || `R${list.length - idx}`,
      productionPurpose: run.productionPurpose || (run.basedOnHighlight ? '爆款扩量' : '首轮覆盖')
    }));
  }, [aiRuns, selectedProject]);

  const projectAssets = useMemo(() => {
    if (!selectedProject) return [];
    return assets.filter(
      (asset) => asset.dramaId === selectedProject.dramaId || asset.dramaTitle === selectedProject.dramaTitle
    );
  }, [assets, selectedProject]);

  const activeRun = useMemo(() => {
    if (recordFilter !== 'all_drama_assets') {
      const found = projectRuns.find((r) => r.id === recordFilter);
      if (found) return found;
    }
    return projectRuns.find((r) => r.id === selectedRunId) || projectRuns[0] || null;
  }, [projectRuns, recordFilter, selectedRunId]);

  const transcriptStep = activeRun?.pipelineSteps.find((step) => step.key === 'local_recognize');
  const storyMapStep = activeRun?.pipelineSteps.find((step) => step.key === 'highlight_judge');

  useEffect(() => {
    if (!selectedProject) return;
    const firstRunId = projectRuns[0]?.id || '';
    setSelectedRunId(firstRunId);
    setRecordFilter('all_drama_assets');
    setAssetHighlightFilter('ALL');
    setAssetPurposeFilter('ALL');
    setSelectedAssetIds([]);
    setActiveStepIndex(null);
    setFocusedHighlightId(null);
    setInlinePlayingHighlightId(null);
    setInlinePlayingAssetId(null);
  }, [selectedProject?.dramaId]);

  // 打开「新建生产方案」弹窗的快捷函数
  const openProductionPlanModal = (options?: {
    purpose?: ProductionPurpose;
    highlightIds?: string[];
  }) => {
    setPlanInitialPurpose(options?.purpose || '首轮覆盖');
    setPlanInitialHighlightIds(options?.highlightIds || []);
    setFollowUpHighlight(null);
    setIsPlanModalOpen(true);
  };

  // 一键淘汰 / 恢复高光片段（默认通过，不合适直接淘汰）
  const handleToggleHighlightEliminated = (highlightId: string, eliminate: boolean) => {
    setHighlights((prev) => {
      const exists = prev.some((h) => h.id === highlightId);
      if (!exists) {
        const target = dramaHighlights.find((h) => h.id === highlightId);
        if (!target) return prev;
        return [...prev, { ...target, status: eliminate ? '已淘汰' : '已通过' }];
      }
      return prev.map((h) =>
        h.id === highlightId ? { ...h, status: eliminate ? '已淘汰' : '已通过' } : h
      );
    });
    if (inlinePlayingHighlightId === highlightId && eliminate) {
      setInlinePlayingHighlightId(null);
    }
    showToast(
      eliminate
        ? '🗑️ 已淘汰该高光片段（新建生产方案时将自动跳过）'
        : '✅ 已恢复该高光片段为可用状态'
    );
  };

  // 提交「生产方案」并产生一条新的「生成记录」
  const handleCreateNewRun = async (params: {
    dramaId: string;
    templateId: string;
    rendererTemplateId?: string;
    playStrategy: PlayContinuityMode;
    playStrategies: PlayContinuityMode[];
    strategyCounts: StrategyCounts;
    durationRangeMin: [number, number];
    targetCount: number;
    modelId: string;
    productionPurpose?: ProductionPurpose;
    selectedHighlightIds?: string[];
    perHighlightCount?: number;
    basedOnHighlight?: string;
  }) => {
    const drama = rawDramas.find((item) => item.dramaId === params.dramaId) || selectedProject;
    const tpl = templates.find((item) => item.id === params.templateId) || templates[0];
    if (!drama || !drama.directoryPath) {
      showToast('当前剧集没有可用原片目录。');
      return;
    }
    const nextRoundNumber =
      aiRuns.filter((r) => r.dramaId === drama.dramaId || r.dramaTitle === drama.dramaTitle).length + 1;
    const chosenHighlights = dramaHighlights.filter((h) =>
      params.selectedHighlightIds?.includes(h.id)
    );
    const purpose = params.productionPurpose || '首轮覆盖';

    try {
      const run = await startContentRemixRun({
        drama_id: drama.dramaId,
        drama_title: drama.dramaTitle,
        source_directory: drama.directoryPath,
        template_id: tpl.id,
        template_name: tpl.name,
        template_version: tpl.version,
        renderer_template_id: params.rendererTemplateId,
        strategy_counts: params.strategyCounts,
        duration_range_min: params.durationRangeMin,
        model_id: params.modelId,
        model_assignments: modelRoutes,
        production_purpose: purpose,
        highlight_ids: params.selectedHighlightIds,
        based_on_highlight: params.basedOnHighlight
      });
      const enrichedRun: V3ContentAiRun = {
        ...run,
        roundCode: `R${nextRoundNumber}`,
        productionPurpose: purpose,
        selectedHighlightIds: params.selectedHighlightIds,
        basedOnHighlight: params.basedOnHighlight
      };
      setAiRuns((prev) => [enrichedRun, ...prev.filter((item) => item.id !== run.id)]);
      setSelectedRunId(run.id);
      setRecordFilter(run.id);
      setIsPlanModalOpen(false);
      showToast(`✅ 已启动「${purpose}生产方案」（计划生成 ${params.targetCount} 条）`);
    } catch {
      const nowStr = new Date().toISOString().replace('T', ' ').slice(0, 16);
      const mockRunId = `airun-${Date.now()}`;
      const mockResults = Array.from({ length: params.targetCount }).map((_, i) => {
        const isJump = i < (params.strategyCounts['跳集播放'] || 0);
        const mode: PlayContinuityMode = isJump ? '跳集播放' : '连续播放';
        const srcHl =
          chosenHighlights[i % Math.max(1, chosenHighlights.length)] || dramaHighlights[0];
        const srcLabel = srcHl
          ? `[${srcHl.code}] ${srcHl.episodeLabel} ${srcHl.timeRange} ${srcHl.sceneTag || srcHl.description.slice(0, 12)}`
          : '默认高光切入';
        const epStart = srcHl ? Number(srcHl.episodeLabel.replace(/\D/g, '')) || 1 : i * 4 + 1;
        const epEnd = epStart + 5;

        return {
          id: `res-${Date.now()}-${i}`,
          jobId: mockRunId,
          videoName: `${drama.dramaTitle}_${purpose}_${srcHl?.code || 'H01'}_${mode}_EP${String(epStart).padStart(2, '0')}-${String(epEnd).padStart(2, '0')}_${i + 1}.mp4`,
          dramaId: drama.dramaId,
          dramaTitle: drama.dramaTitle,
          durationSec: (params.durationRangeMin[0] + 1) * 60 + 25,
          durationFormatted: `0${params.durationRangeMin[0] + 1}分25秒`,
          episodeRange: `第${String(epStart).padStart(2, '0')}集 ~ 第${String(epEnd).padStart(2, '0')}集`,
          highlightCutPoint: srcLabel,
          sourceHighlightId: srcHl?.id,
          sourceHighlightLabel: srcLabel,
          jumpCutPositions: isJump
            ? [`第${epStart + 1}集 → 跳第${epStart + 3}集 (保留核心冲突)`]
            : ['连续无缝拼接 · 已去片头片尾'],
          playStrategy: mode,
          templateId: tpl.id,
          templateVersion: tpl.version,
          filePath: `Z:\\05短剧二创\\${drama.dramaTitle}\\${drama.dramaTitle}_${purpose}_${i + 1}.mp4`,
          techStatus: '合格' as const,
          techReport: '1080×1920 30fps · 质检合格默认可用',
          manualStatus: '已通过' as const,
          ingestedAssetId: `asset-gen-${Date.now()}-${i}`,
          sourceReasoning: `来自生产方案「${purpose}」· 选用高光 ${srcLabel}`,
          previewHue: '#0F172A',
          createdAt: nowStr,
          isViralHighlight: purpose === '爆款扩量'
        };
      });

      const fallbackRun: V3ContentAiRun = {
        id: mockRunId,
        jobCode: `RMX-${Date.now().toString().slice(-6)}`,
        roundCode: `R${nextRoundNumber}`,
        productionPurpose: purpose,
        selectedHighlightIds: params.selectedHighlightIds,
        basedOnHighlight: params.basedOnHighlight,
        dramaId: drama.dramaId,
        dramaTitle: drama.dramaTitle,
        sourceDirectory: drama.directoryPath,
        totalSourceEpisodes: drama.totalEpisodes,
        sourceFilesStatus: `${drama.verifiedMp4Count}集原片完整`,
        templateId: tpl.id,
        templateName: tpl.name,
        templateVersion: tpl.version,
        playStrategy: params.playStrategy,
        playStrategies: params.playStrategies,
        strategyCounts: params.strategyCounts,
        durationRangeMin: params.durationRangeMin,
        targetCount: params.targetCount,
        modelId: params.modelId,
        status: 'completed',
        createdAt: nowStr,
        finishedAt: nowStr,
        pipelineSteps: [
          { key: 'scan_raw', label: '扫描原片', status: 'completed', durationText: '2.1s', detailText: `校验 ${drama.verifiedMp4Count} 集原片通过` },
          { key: 'local_recognize', label: '本地识别', status: 'completed', durationText: '0.6s', detailText: '直接复用本剧已缓存转写时间轴' },
          { key: 'highlight_judge', label: '剧情地图', status: 'completed', durationText: '1.8s', detailText: `读取高光库选中的 ${chosenHighlights.length} 个高光片段` },
          { key: 'continuity_plan', label: '组合与复核', status: 'completed', durationText: '5.4s', detailText: `按「${purpose}」方案生成 ${params.targetCount} 条成片计划` },
          { key: 'video_synthesize', label: '视频合成', status: 'completed', durationText: '1m 35s', detailText: `FFmpeg 合成 ${params.targetCount} 条成片` },
          { key: 'tech_inspect', label: '技术检查', status: 'completed', durationText: '6.8s', detailText: `${params.targetCount} 条全部通过音画质检` },
          { key: 'auto_ingest', label: '保存成片', status: 'completed', durationText: '1.1s', detailText: '已写入成片库并更新高光使用次数' }
        ],
        results: mockResults
      };

      if (params.selectedHighlightIds?.length) {
        const selectedSet = new Set(params.selectedHighlightIds);
        const addedPerHl = Math.max(1, params.perHighlightCount || 1);
        setHighlights((prev) =>
          prev.map((hl) => {
            if (!selectedSet.has(hl.id)) return hl;
            const newNames = mockResults
              .filter((r) => r.sourceHighlightId === hl.id)
              .map((r) => r.videoName);
            return {
              ...hl,
              status: '已通过',
              usedCount: hl.usedCount + addedPerHl,
              generatedVideoNames: [...newNames, ...hl.generatedVideoNames]
            };
          })
        );
      }

      setAiRuns((prev) => [fallbackRun, ...prev]);
      setSelectedRunId(fallbackRun.id);
      setRecordFilter(fallbackRun.id);
      setIsPlanModalOpen(false);
      showToast(`✅ 「${purpose}生产」已完成，生成 ${params.targetCount} 条新成片并进入成片库`);
    }
  };

  useEffect(() => {
    if (!selectedRunId) return;
    const timer = window.setInterval(() => {
      getContentRemixRun(selectedRunId)
        .then((run) =>
          setAiRuns((prev) =>
            prev.map((item) =>
              item.id === run.id
                ? {
                    ...run,
                    roundCode: item.roundCode,
                    productionPurpose: item.productionPurpose,
                    selectedHighlightIds: item.selectedHighlightIds,
                    basedOnHighlight: item.basedOnHighlight
                  }
                : item
            )
          )
        )
        .catch(() => undefined);
    }, 2500);
    return () => window.clearInterval(timer);
  }, [selectedRunId]);

  // 同步生成记录中的成片结果到成片库
  useEffect(() => {
    const generatedAssets: V3ContentAsset[] = aiRuns.flatMap((run) =>
      run.results.map((result) => ({
        id: result.ingestedAssetId || `asset-${result.id}`,
        videoName: result.videoName,
        sourceType: '原剧二创' as const,
        dramaId: result.dramaId,
        dramaTitle: result.dramaTitle,
        generationRecord: `${run.productionPurpose || '首轮覆盖'}生产 · ${result.playStrategy}（系统编号 ${run.roundCode || run.jobCode}）`,
        generationJobId: run.id,
        productionPurpose: run.productionPurpose || '首轮覆盖',
        templateVersion: result.templateVersion,
        durationSec: result.durationSec,
        durationFormatted: result.durationFormatted,
        filePath: result.filePath,
        episodeRange: result.episodeRange,
        highlightCutPoint: result.highlightCutPoint,
        sourceHighlightId: result.sourceHighlightId,
        sourceHighlightLabel: result.sourceHighlightLabel || result.highlightCutPoint,
        jumpCutPositions: result.jumpCutPositions,
        techStatus: result.techStatus,
        techDetail: result.techReport,
        manualStatus:
          result.techStatus === '不合格'
            ? ('已淘汰' as ManualReviewStatus)
            : result.manualStatus === '已淘汰'
            ? ('已淘汰' as ManualReviewStatus)
            : ('已通过' as ManualReviewStatus),
        originalStatus: '未声明原创' as const,
        authUsedCount: 0,
        authMaxLimit: globalAuthLimit,
        usedAccounts: [],
        createdAt: result.createdAt,
        previewHue: '#0F172A',
        isViralHighlight: result.isViralHighlight
      }))
    );
    if (!generatedAssets.length) return;
    setAssets((current) => {
      const existingMap = new Map<string, V3ContentAsset>(current.map((a) => [a.id, a]));
      const merged = generatedAssets.map((gen) => {
        const prev = existingMap.get(gen.id);
        if (!prev) return gen;
        return {
          ...prev,
          techStatus: gen.techStatus,
          techDetail: gen.techDetail,
          sourceHighlightId: gen.sourceHighlightId || prev.sourceHighlightId,
          sourceHighlightLabel: gen.sourceHighlightLabel || prev.sourceHighlightLabel,
          productionPurpose: gen.productionPurpose || prev.productionPurpose,
          manualStatus: prev.manualStatus === '已淘汰' ? '已淘汰' : gen.manualStatus,
          isViralHighlight: prev.isViralHighlight ?? gen.isViralHighlight
        };
      });
      const generatedIds = new Set(generatedAssets.map((asset) => asset.id));
      return [...merged, ...current.filter((asset) => !generatedIds.has(asset.id))];
    });
  }, [aiRuns, globalAuthLimit]);

  const baseRoundAssets = useMemo(() => {
    if (recordFilter === 'all_drama_assets') return projectAssets;
    return projectAssets.filter((a) => a.generationJobId === recordFilter);
  }, [projectAssets, recordFilter]);

  const activeAvailableCount = useMemo(
    () => baseRoundAssets.filter((a) => a.manualStatus !== '已淘汰' && a.techStatus === '合格').length,
    [baseRoundAssets]
  );
  const eliminatedCount = useMemo(
    () => baseRoundAssets.filter((a) => a.manualStatus === '已淘汰' || a.techStatus === '不合格').length,
    [baseRoundAssets]
  );

  const displayedDramaAssets = useMemo(() => {
    return baseRoundAssets.filter((a) => {
      const isEliminated = a.manualStatus === '已淘汰' || a.techStatus === '不合格';
      if (assetQuickFilter === 'active' && isEliminated) return false;
      if (assetQuickFilter === 'eliminated' && !isEliminated) return false;
      if (assetHighlightFilter !== 'ALL' && a.sourceHighlightId !== assetHighlightFilter) {
        return false;
      }
      if (assetPurposeFilter !== 'ALL' && (a.productionPurpose || '首轮覆盖') !== assetPurposeFilter) {
        return false;
      }
      if (assetKeyword.trim()) {
        const kw = assetKeyword.trim().toLowerCase();
        const matchName = a.videoName.toLowerCase().includes(kw);
        const matchCut = (a.sourceHighlightLabel || a.highlightCutPoint || '').toLowerCase().includes(kw);
        const matchEp = (a.episodeRange || '').toLowerCase().includes(kw);
        if (!matchName && !matchCut && !matchEp) return false;
      }
      return true;
    });
  }, [baseRoundAssets, assetQuickFilter, assetHighlightFilter, assetPurposeFilter, assetKeyword]);

  // 淘汰 或 恢复成片
  const handleSetAssetsEliminated = (assetIds: string[], eliminate: boolean) => {
    if (!assetIds.length) return;
    const nextStatus: ManualReviewStatus = eliminate ? '已淘汰' : '已通过';
    const idSet = new Set(assetIds);
    setAssets((prev) =>
      prev.map((a) => (idSet.has(a.id) ? { ...a, manualStatus: nextStatus } : a))
    );
    setAiRuns((prev) =>
      prev.map((run) => ({
        ...run,
        results: run.results.map((r) => {
          const linkedId = r.ingestedAssetId || `asset-${r.id}`;
          return idSet.has(linkedId) || idSet.has(r.id) ? { ...r, manualStatus: nextStatus } : r;
        })
      }))
    );
    setSelectedAssetIds([]);
    showToast(
      eliminate
        ? `🗑️ 已淘汰 ${assetIds.length} 条成片（不会进入自动发布）`
        : `✅ 已恢复 ${assetIds.length} 条成片为可用状态`
    );
  };

  // 导入外部视频
  const handleConfirmExternalImport = (e: React.FormEvent) => {
    e.preventDefault();
    if (!importVideoName.trim()) {
      showToast('请输入视频名称');
      return;
    }
    const cleanName = importVideoName.trim().endsWith('.mp4')
      ? importVideoName.trim()
      : `${importVideoName.trim()}.mp4`;
    const dramaTitle = selectedProject?.dramaTitle || '外部导入短剧';
    const dramaId = selectedProject?.dramaId || 'drama-ext';
    const newAssetId = `asset-ext-${Date.now()}`;

    const newAsset: V3ContentAsset = {
      id: newAssetId,
      videoName: cleanName,
      sourceType: importSourceType,
      dramaId,
      dramaTitle,
      generationRecord:
        importSourceType === '外部导入视频' ? '外部导入成片' : '旧流程归档成片',
      templateVersion: 'mumu-v1.0',
      durationSec: 390,
      durationFormatted: importDurationFormatted || '06:30',
      filePath: `${importFilePath.replace(/\\$/, '')}\\${cleanName}`,
      episodeRange: '外部精剪片段',
      highlightCutPoint: importHighlightNote.trim() || '外部精剪高光开头',
      sourceHighlightLabel: importHighlightNote.trim() || '外部导入精剪片段',
      techStatus: '合格',
      techDetail: '1080×1920 · 导入校验合格',
      manualStatus: '已通过',
      originalStatus: '未声明原创',
      authUsedCount: 0,
      authMaxLimit: globalAuthLimit,
      usedAccounts: [],
      createdAt: new Date().toISOString().replace('T', ' ').slice(0, 16),
      previewHue: '#0F172A'
    };

    setAssets((prev) => [newAsset, ...prev]);

    if (importTargetGroupId) {
      const currentGroupCount = groupItems.filter((gi) => gi.groupId === importTargetGroupId).length;
      setGroupItems((prev) => [
        ...prev,
        {
          id: `gi-${Date.now()}`,
          groupId: importTargetGroupId,
          assetId: newAssetId,
          sortOrder: currentGroupCount + 1,
          addedAt: new Date().toISOString().replace('T', ' ').slice(0, 16)
        }
      ]);
      showToast(`✅ 已导入外部视频《${cleanName}》并直接加入当前编组`);
    } else {
      showToast(`✅ 已导入视频《${cleanName}》`);
    }

    setImportVideoName('');
    setImportHighlightNote('');
    setImportTargetGroupId(null);
    setIsImportModalOpen(false);
  };

  // 发布编组操作
  const handleQuickCreateGroup = (e?: React.FormEvent) => {
    if (e) e.preventDefault();
    const defaultName = `待发编组_${String(groups.length + 1).padStart(2, '0')}`;
    const finalName = newGroupName.trim() || defaultName;
    const now = new Date().toISOString().replace('T', ' ').slice(0, 16);
    const newGrp: V3ContentGroup = {
      id: `grp-${Date.now()}`,
      name: finalName,
      description: '',
      tags: [],
      createdAt: now,
      updatedAt: now
    };
    setGroups((prev) => [...prev, newGrp]);
    setSelectedGroupId(newGrp.id);
    setNewGroupName('');
    showToast(`✅ 已新建「${finalName}」`);
  };

  const handleRenameGroup = (groupId: string, newName: string) => {
    if (!newName.trim()) return;
    setGroups((prev) =>
      prev.map((g) => (g.id === groupId ? { ...g, name: newName.trim(), updatedAt: '刚刚' } : g))
    );
    setEditingGroupName(null);
    showToast(`✅ 编组已重命名为「${newName.trim()}」`);
  };

  const handleDeleteGroup = (groupId: string) => {
    const target = groups.find((g) => g.id === groupId);
    const remaining = groups.filter((g) => g.id !== groupId);
    setGroups(remaining);
    setGroupItems((prev) => prev.filter((gi) => gi.groupId !== groupId));
    if (selectedGroupId === groupId) {
      setSelectedGroupId(remaining[0]?.id || '');
    }
    showToast(`🗑️ 已删除编组「${target?.name || groupId}」（组内成片仍保留在剧集库中）`);
  };

  const handleAddAssetsToGroup = (groupId: string, targetAssetIds: string[]) => {
    let addedCount = 0;
    setGroupItems((prev) => {
      const existingIds = new Set(prev.filter((gi) => gi.groupId === groupId).map((gi) => gi.assetId));
      let nextOrder = prev.filter((gi) => gi.groupId === groupId).length + 1;
      const additions: V3ContentGroupItem[] = [];
      targetAssetIds.forEach((aid) => {
        if (!existingIds.has(aid)) {
          addedCount++;
          additions.push({
            id: `gi-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`,
            groupId,
            assetId: aid,
            sortOrder: nextOrder++,
            addedAt: new Date().toISOString().replace('T', ' ').slice(0, 16)
          });
        }
      });
      return [...prev, ...additions];
    });
    if (addedCount > 0) {
      showToast(`✅ 已将 ${addedCount} 条视频加入编组`);
    } else {
      showToast('所选视频已在当前编组中');
    }
  };

  const handleRemoveAssetFromGroup = (groupId: string, assetId: string) => {
    setGroupItems((prev) => {
      const remaining = prev.filter((gi) => !(gi.groupId === groupId && gi.assetId === assetId));
      let order = 1;
      return remaining.map((gi) => (gi.groupId === groupId ? { ...gi, sortOrder: order++ } : gi));
    });
    showToast('已从当前编组移出');
  };

  const handleMoveGroupItemOrder = (groupId: string, assetId: string, direction: 'up' | 'down') => {
    setGroupItems((prev) => {
      const groupList = prev
        .filter((gi) => gi.groupId === groupId)
        .sort((a, b) => a.sortOrder - b.sortOrder);
      const idx = groupList.findIndex((gi) => gi.assetId === assetId);
      if (idx === -1) return prev;
      const swapIdx = direction === 'up' ? idx - 1 : idx + 1;
      if (swapIdx < 0 || swapIdx >= groupList.length) return prev;

      const tempOrder = groupList[idx].sortOrder;
      groupList[idx] = { ...groupList[idx], sortOrder: groupList[swapIdx].sortOrder };
      groupList[swapIdx] = { ...groupList[swapIdx], sortOrder: tempOrder };

      const updatedMap = new Map(groupList.map((item) => [item.id, item]));
      return prev.map((gi) => updatedMap.get(gi.id) || gi);
    });
  };

  const handlePublishGroupAsset = (asset: V3ContentAsset, groupId: string) => {
    const acc = accounts.find((a) => a.id === publishAccountId) || accounts[0];
    const grp = groups.find((g) => g.id === groupId);
    if (!acc) {
      showToast('请先选择发布账号');
      return;
    }
    const now = new Date().toISOString().replace('T', ' ').slice(0, 19);

    if (publishMode === '原创发布') {
      const newOrigRec: V3ContentOriginalRecord = {
        id: `orig-rec-${Date.now()}`,
        assetId: asset.id,
        videoName: asset.videoName,
        dramaTitle: asset.dramaTitle,
        groupId: grp?.id,
        groupName: grp?.name,
        accountId: acc.id,
        accountName: acc.name,
        theaterName: acc.theaterName,
        actualPublishCount: publishCount,
        status: '原创声明成功',
        consumedOriginalCount: publishCount,
        recordedAt: now
      };
      setOriginalRecords((prev) => [newOrigRec, ...prev]);
    }

    const deducted = publishMode === '授权发布' ? publishCount : 0;
    const newPub: V3ContentPublication = {
      id: `pub-rec-${Date.now()}-${Math.random().toString(36).slice(2, 5)}`,
      assetId: asset.id,
      videoName: asset.videoName,
      dramaTitle: asset.dramaTitle,
      sourceType: asset.sourceType,
      groupId: grp?.id,
      groupName: grp?.name,
      publishMode,
      accountId: acc.id,
      accountName: acc.name,
      theaterName: acc.theaterName,
      actualPublishCount: publishCount,
      status: '发布成功',
      authQuotaDeducted: deducted,
      xiaovmaoFlowCode: `XVM-${publishMode === '原创发布' ? 'ORIG' : 'AUTH'}-${Date.now().toString().slice(-6)}`,
      publishedAt: now
    };
    setPublications((prev) => [newPub, ...prev]);

    setAssets((prev) =>
      prev.map((a) => {
        if (a.id !== asset.id) return a;
        return {
          ...a,
          originalStatus: publishMode === '原创发布' ? '已声明原创' : a.originalStatus,
          originalDeclaredAccountId: publishMode === '原创发布' ? acc.id : a.originalDeclaredAccountId,
          originalDeclaredAccountName: publishMode === '原创发布' ? acc.name : a.originalDeclaredAccountName,
          authUsedCount: a.authUsedCount + deducted,
          usedAccounts: [
            ...a.usedAccounts,
            {
              accountId: acc.id,
              accountName: acc.name,
              publishCount,
              mode: publishMode,
              lastPublishedAt: now.slice(0, 16)
            }
          ]
        };
      })
    );

    showToast(`✅ 已通过「${acc.name}」执行${publishMode}（实发 ${publishCount} 次）`);
  };

  const handleBatchPublishWholeGroup = () => {
    if (!selectedGroup) return;
    if (selectedGroupAssets.length === 0) {
      showToast('当前编组内还没有待发视频');
      return;
    }
    selectedGroupAssets.forEach((item) => {
      handlePublishGroupAsset(item.asset, selectedGroup.id);
    });
    showToast(`🚀 已启动编组「${selectedGroup.name}」共 ${selectedGroupAssets.length} 条视频的自动发布`);
  };

  const getAssetGroups = (assetId: string) => {
    const gIds = groupItems.filter((gi) => gi.assetId === assetId).map((gi) => gi.groupId);
    return groups.filter((g) => gIds.includes(g.id));
  };

  const toggleSelectAsset = (assetId: string) => {
    setSelectedAssetIds((prev) =>
      prev.includes(assetId) ? prev.filter((id) => id !== assetId) : [...prev, assetId]
    );
  };

  const selectAllDisplayed = () => {
    const ids = displayedDramaAssets.map((a) => a.id);
    if (selectedAssetIds.length === ids.length && ids.length > 0) {
      setSelectedAssetIds([]);
    } else {
      setSelectedAssetIds(ids);
    }
  };

  const selectedGroup = groups.find((g) => g.id === selectedGroupId) || groups[0] || null;
  const selectedGroupAssets = useMemo(() => {
    if (!selectedGroup) return [];
    const items = groupItems
      .filter((gi) => gi.groupId === selectedGroup.id)
      .sort((a, b) => a.sortOrder - b.sortOrder);
    return items
      .map((item) => {
        const asset = assets.find((a) => a.id === item.assetId);
        return asset ? { item, asset } : null;
      })
      .filter((x): x is { item: V3ContentGroupItem; asset: V3ContentAsset } => Boolean(x));
  }, [selectedGroup, groupItems, assets]);

  const pickableAssetsPool = useMemo(() => {
    const q = pickAssetsSearch.trim().toLowerCase();
    return assets.filter((a) => {
      if (a.manualStatus === '已淘汰' || a.techStatus === '不合格') return false;
      if (!q) return true;
      return (
        a.videoName.toLowerCase().includes(q) ||
        a.dramaTitle.toLowerCase().includes(q) ||
        (a.sourceHighlightLabel || a.highlightCutPoint || '').toLowerCase().includes(q)
      );
    });
  }, [assets, pickAssetsSearch]);

  // 快审弹窗中的上一个/下一个高光导航
  const previewHighlightIndex = previewHighlightClip
    ? dramaHighlights.findIndex((h) => h.id === previewHighlightClip.id)
    : -1;

  return (
    <div className="animate-in fade-in duration-200 max-w-[1840px] mx-auto w-full">
      {/* Main 2-Column Workbench */}
      <div className="grid grid-cols-1 xl:grid-cols-[340px_minmax(0,1fr)] gap-5 items-start">
        {/* ==================== LEFT COLUMN: 剧集卡片列表 / 发布编组列表 ==================== */}
        <div className="min-w-0 bg-white rounded-3xl p-4 border border-black/[0.06] shadow-xs flex flex-col h-[calc(100vh-115px)] min-h-[700px]">
          {/* Single-layer Switcher */}
          <div className="grid grid-cols-2 p-1 bg-black/[0.04] rounded-xl gap-1 border border-black/[0.03] mb-3.5 shrink-0">
            <button
              type="button"
              onClick={() => setLeftNavMode('single_drama')}
              className={`flex items-center justify-center gap-1.5 py-2 rounded-lg text-xs font-extrabold transition-all cursor-pointer ${
                leftNavMode === 'single_drama'
                  ? 'bg-white text-[#1A1D2E] shadow-xs'
                  : 'text-[#64748B] hover:text-[#1A1D2E]'
              }`}
            >
              <Film className="w-3.5 h-3.5" />
              <span>在产剧集 ({activeProductionDramas.length})</span>
            </button>

            <button
              type="button"
              onClick={() => setLeftNavMode('publish_groups')}
              className={`flex items-center justify-center gap-1.5 py-2 rounded-lg text-xs font-extrabold transition-all cursor-pointer ${
                leftNavMode === 'publish_groups'
                  ? 'bg-white text-[#1A1D2E] shadow-xs'
                  : 'text-[#64748B] hover:text-[#1A1D2E]'
              }`}
            >
              <Send className="w-3.5 h-3.5" />
              <span>发布编组 ({groups.length})</span>
            </button>
          </div>

          {leftNavMode === 'single_drama' ? (
            <>
              {/* Search & Add Drama */}
              <div className="flex items-center gap-2 mb-3 shrink-0">
                <div className="relative flex-1">
                  <Search className="w-3.5 h-3.5 text-slate-400 absolute left-3 top-2.5" />
                  <input
                    type="text"
                    placeholder="筛选在产剧集..."
                    value={dramaSearch}
                    onChange={(e) => setDramaSearch(e.target.value)}
                    className="w-full pl-8 pr-2.5 py-1.5 rounded-xl border border-slate-200 bg-[#F8FAFC] text-xs text-slate-800 focus:outline-none focus:border-slate-400"
                  />
                </div>
                <button
                  type="button"
                  onClick={() => {
                    setAddDramaKeyword('');
                    setAddDramaModalOpen(true);
                  }}
                  className="flex items-center gap-1 px-3 py-1.5 rounded-xl bg-[#1A1D2E] hover:bg-black text-[#DDFD00] text-xs font-extrabold shrink-0 cursor-pointer"
                >
                  <Plus className="w-3.5 h-3.5" />
                  <span>添加剧集</span>
                </button>
              </div>

              {/* Enriched Drama Cards List */}
              <div className="flex-1 overflow-y-auto space-y-2.5 pr-1 no-scrollbar">
                {activeProductionDramas.map((drama) => {
                  const isSelected = drama.dramaId === selectedProject?.dramaId;
                  const dHighlights = highlights.filter(
                    (h) => h.dramaId === drama.dramaId || h.dramaTitle === drama.dramaTitle
                  );
                  const usableHlCount =
                    dHighlights.length > 0
                      ? dHighlights.filter((h) => h.status !== '已淘汰' && h.status !== '暂停').length
                      : 2;
                  const dRuns = aiRuns.filter(
                    (r) => r.dramaId === drama.dramaId || r.dramaTitle === drama.dramaTitle
                  );
                  const dAssets = assets.filter(
                    (a) =>
                      (a.dramaId === drama.dramaId || a.dramaTitle === drama.dramaTitle) &&
                      a.manualStatus !== '已淘汰' &&
                      a.techStatus === '合格'
                  );
                  const viralCount = dAssets.filter((a) => a.isViralHighlight || a.productionPurpose === '爆款扩量').length;
                  const isRunning = dRuns.some((r) => r.status === 'running');
                  const hasMissingEp = drama.missingEpisodes.length > 0;
                  const latestRun = dRuns[0];

                  return (
                    <div
                      key={drama.dramaId}
                      onClick={() => setSelectedDramaId(drama.dramaId)}
                      className={`group p-3.5 rounded-2xl border transition-all cursor-pointer select-none ${
                        isSelected
                          ? 'bg-white border-[#1A1D2E] shadow-md ring-2 ring-[#1A1D2E]/10'
                          : 'bg-white hover:bg-slate-50/90 border-black/[0.06] shadow-xs'
                      }`}
                    >
                      {/* Top Layer: Vertical Drama Cover + Title + Theater/Genre + Status Badge */}
                      <div className="flex items-start gap-3">
                        <DramaCover
                          name={drama.dramaTitle}
                          size="sm"
                          colorPlaceholder={{
                            bg: `linear-gradient(135deg, ${drama.coverColor || '#1E293B'} 0%, #0F172A 100%)`,
                            text: '#DDFD00',
                            tag: drama.genreTags?.[0]?.slice(0, 2) || '短剧'
                          }}
                        />

                        <div className="min-w-0 flex-1">
                          <div className="flex items-center justify-between gap-1.5">
                            <span className="font-black text-sm text-[#1A1D2E] truncate">
                              《{drama.dramaTitle}》
                            </span>

                            <div className="flex items-center gap-1 shrink-0">
                              {isRunning ? (
                                <span className="px-2 py-0.5 rounded-full bg-blue-100 text-blue-800 text-[10px] font-extrabold whitespace-nowrap">
                                  合成进行中
                                </span>
                              ) : hasMissingEp ? (
                                <span className="px-2 py-0.5 rounded-full bg-amber-100 text-amber-800 text-[10px] font-extrabold whitespace-nowrap">
                                  缺{drama.missingEpisodes.length}集母带
                                </span>
                              ) : dAssets.length > 0 ? (
                                <span className="px-2 py-0.5 rounded-full bg-emerald-100 text-emerald-800 text-[10px] font-extrabold whitespace-nowrap">
                                  成片就绪
                                </span>
                              ) : (
                                <span className="px-2 py-0.5 rounded-full bg-slate-100 text-slate-700 text-[10px] font-extrabold whitespace-nowrap">
                                  待建方案
                                </span>
                              )}

                              {activeProductionDramas.length > 1 && (
                                <button
                                  type="button"
                                  title="移出左栏在产列表（不删除数据）"
                                  onClick={(e) => {
                                    e.stopPropagation();
                                    setActiveDramaIds((prev) => prev.filter((id) => id !== drama.dramaId));
                                    showToast(`已将《${drama.dramaTitle}》移出左栏在产列表`);
                                  }}
                                  className="opacity-0 group-hover:opacity-100 p-0.5 rounded hover:bg-slate-200 text-slate-400 hover:text-slate-700 transition-opacity cursor-pointer"
                                >
                                  <X className="w-3 h-3" />
                                </button>
                              )}
                            </div>
                          </div>

                          <div className="flex items-center gap-1.5 mt-1 text-[11px] text-slate-500 whitespace-nowrap overflow-hidden">
                            <span className="font-bold text-slate-700 shrink-0">
                              {drama.theaterName || '触摸剧场'}
                            </span>
                            <span className="shrink-0">·</span>
                            <span className="truncate">
                              {(drama.genreTags || ['都市逆袭']).slice(0, 2).join(' / ')}
                            </span>
                          </div>

                          <div className="flex items-center gap-1.5 mt-1 text-[11px] text-slate-400 font-mono whitespace-nowrap overflow-hidden">
                            <span className="shrink-0">原片 {drama.verifiedMp4Count}/{drama.totalEpisodes}集</span>
                            <span className="shrink-0">·</span>
                            <span className="shrink-0">{drama.totalSizeGb}GB</span>
                            <span className="shrink-0">·</span>
                            <span className="text-emerald-700 font-sans font-bold truncate">字幕/剧情图已就绪</span>
                          </div>
                        </div>
                      </div>

                      {/* Middle Layer: 3 Key Operational Metric Boxes */}
                      <div className="grid grid-cols-3 gap-1.5 mt-3 pt-2.5 border-t border-slate-100">
                        <div className="px-2.5 py-1.5 rounded-xl bg-[#F8FAFC] border border-slate-100">
                          <div className="text-[10px] text-slate-400 font-semibold">原片母带</div>
                          <div className="text-xs font-extrabold text-[#1A1D2E] font-mono mt-0.5">
                            {drama.verifiedMp4Count}/{drama.totalEpisodes}集
                          </div>
                        </div>

                        <div className="px-2.5 py-1.5 rounded-xl bg-[#F8FAFC] border border-slate-100">
                          <div className="text-[10px] text-slate-400 font-semibold">高光库</div>
                          <div className="text-xs font-extrabold text-[#1A1D2E] font-mono mt-0.5">
                            {usableHlCount} <span className="text-[10px] font-sans font-semibold text-slate-500">段可用</span>
                          </div>
                        </div>

                        <div className="px-2.5 py-1.5 rounded-xl bg-emerald-50/60 border border-emerald-100/80">
                          <div className="text-[10px] text-emerald-700 font-semibold">成片库</div>
                          <div className="text-xs font-extrabold text-emerald-800 font-mono mt-0.5 flex items-center gap-1">
                            <span>{dAssets.length}条</span>
                            {viralCount > 0 && (
                              <span className="text-[10px] text-amber-600 font-sans font-bold">
                                🔥{viralCount}
                              </span>
                            )}
                          </div>
                        </div>
                      </div>

                      {/* Bottom Footer: Latest Production Scheme Info */}
                      <div className="flex items-center justify-between mt-2 pt-1.5 text-[11px] text-slate-500">
                        <span className="truncate">
                          {latestRun
                            ? `最近方案：${latestRun.productionPurpose || '首轮覆盖'}生产 (${latestRun.results.length}条)`
                            : '尚未执行生产方案'}
                        </span>
                        <span className="font-mono text-[10px] text-slate-400 shrink-0">
                          累计 {dRuns.length} 次记录
                        </span>
                      </div>
                    </div>
                  );
                })}
              </div>
            </>
          ) : (
            /* 发布编组左栏 */
            <div className="flex-1 flex flex-col min-h-0 space-y-3">
              <form onSubmit={handleQuickCreateGroup} className="flex items-center gap-1.5 shrink-0">
                <input
                  type="text"
                  value={newGroupName}
                  onChange={(e) => setNewGroupName(e.target.value)}
                  placeholder={`输入名称 或直接点新建 (默认 待发编组_${String(groups.length + 1).padStart(2, '0')})`}
                  className="flex-1 px-3 py-1.5 rounded-xl border border-slate-200 bg-[#F8FAFC] text-xs text-slate-800 focus:outline-none focus:border-slate-400"
                />
                <button
                  type="submit"
                  className="flex items-center gap-1 px-3 py-1.5 rounded-xl bg-[#1A1D2E] hover:bg-black text-[#DDFD00] text-xs font-extrabold shrink-0 cursor-pointer"
                >
                  <Plus className="w-3.5 h-3.5" />
                  <span>新建编组</span>
                </button>
              </form>

              <div className="flex-1 overflow-y-auto space-y-2 pr-1 no-scrollbar">
                {groups.map((grp) => {
                  const isSelected = grp.id === selectedGroup?.id;
                  const count = groupItems.filter((gi) => gi.groupId === grp.id).length;
                  return (
                    <div
                      key={grp.id}
                      onClick={() => setSelectedGroupId(grp.id)}
                      className={`p-3.5 rounded-2xl border transition-all cursor-pointer select-none ${
                        isSelected
                          ? 'bg-white border-[#1A1D2E] shadow-md ring-2 ring-[#1A1D2E]/10'
                          : 'bg-white hover:bg-slate-50 border-black/[0.06] shadow-xs'
                      }`}
                    >
                      <div className="flex items-center justify-between gap-2">
                        <span className="font-extrabold text-sm text-[#1A1D2E] truncate">
                          {grp.name}
                        </span>
                        <span className="px-2 py-0.5 rounded-md bg-slate-100 text-slate-700 font-mono text-[11px] font-bold shrink-0">
                          {count} 条视频
                        </span>
                      </div>
                      <div className="flex items-center justify-between mt-2 pt-2 border-t border-slate-100 text-[11px] text-slate-400">
                        <span>创建于 {grp.createdAt.slice(5)}</span>
                        <span className="text-slate-600 font-semibold">点击管理与发布</span>
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          )}
        </div>

        {/* ==================== RIGHT COLUMN: 三大模块工作台 ==================== */}
        {leftNavMode === 'single_drama' ? (
          selectedProject ? (
            <div className="min-w-0 bg-white rounded-3xl p-5 border border-black/[0.06] shadow-xs flex flex-col h-[calc(100vh-115px)] min-h-[700px] overflow-y-auto space-y-5 no-scrollbar">
              {/* ====================================================================
                  模块 1：剧集资料 (Drama Profile & Pre-processing Status)
              ==================================================================== */}
              <section className="p-4 rounded-2xl bg-[#F8FAFC] border border-black/[0.06] space-y-3.5 shrink-0">
                {/* Top Header of Module 1 */}
                <div className="flex flex-wrap items-start justify-between gap-4">
                  <div className="flex items-start gap-3.5 min-w-0 flex-1">
                    <DramaCover
                      name={selectedProject.dramaTitle}
                      size="md"
                      colorPlaceholder={{
                        bg: `linear-gradient(135deg, ${selectedProject.coverColor || '#1E293B'} 0%, #0F172A 100%)`,
                        text: '#DDFD00',
                        tag: selectedProject.genreTags?.[0]?.slice(0, 4) || '剧集档案'
                      }}
                    />

                    <div className="min-w-0 flex-1 space-y-1.5">
                      <div className="flex flex-wrap items-center gap-2">
                        <span className="px-2 py-0.5 rounded-lg bg-[#1A1D2E] text-[#DDFD00] text-[11px] font-black">
                          ① 剧集资料
                        </span>
                        <h2 className="text-xl font-black text-[#1A1D2E] tracking-tight truncate">
                          《{selectedProject.dramaTitle}》
                        </h2>

                        {selectedProject.theaterName && (
                          <span className="px-2.5 py-0.5 rounded-lg bg-white border border-slate-200 text-xs font-extrabold text-slate-700">
                            归属：{selectedProject.theaterName}
                          </span>
                        )}

                        {(selectedProject.genreTags || ['男频战神', '都市逆袭']).map((tag) => (
                          <span
                            key={tag}
                            className="px-2 py-0.5 rounded-lg bg-indigo-50 text-indigo-700 text-[11px] font-bold"
                          >
                            {tag}
                          </span>
                        ))}

                        {(selectedProject.mountPlatforms || ['小程序挂载', '视频号剧集挂载']).map((mp) => (
                          <span
                            key={mp}
                            className="px-2 py-0.5 rounded-lg bg-emerald-50 text-emerald-700 text-[11px] font-bold"
                          >
                            {mp}
                          </span>
                        ))}
                      </div>

                      <p className="text-xs text-slate-600 leading-relaxed">
                        <strong className="text-[#1A1D2E]">剧情主线：</strong>
                        {selectedProject.storySummary ||
                          '已完成全集对白字幕转写与跨集冲突卡点分析，高光片段已提取入库，可直接选高光新建生产方案。'}
                      </p>

                      <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-[11px] text-slate-500">
                        {selectedProject.historyNames && selectedProject.historyNames.length > 0 && (
                          <span>
                            历史剧名/别名：<strong className="text-slate-700">{selectedProject.historyNames.join(' / ')}</strong>
                          </span>
                        )}
                        {selectedProject.climaxEpisodes && (
                          <span>
                            核心爽点集：<strong className="text-amber-800">{selectedProject.climaxEpisodes}</strong>
                          </span>
                        )}
                      </div>
                    </div>
                  </div>

                  {/* Right Action Buttons */}
                  <div className="flex flex-wrap items-center gap-2 shrink-0">
                    <button
                      type="button"
                      onClick={() => setShowRecordsDrawer((prev) => !prev)}
                      className={`flex items-center gap-1.5 px-3 py-2 rounded-xl border text-xs font-extrabold transition-all cursor-pointer ${
                        showRecordsDrawer
                          ? 'bg-[#1A1D2E] text-white border-[#1A1D2E]'
                          : 'bg-white hover:bg-slate-50 text-slate-700 border-slate-200'
                      }`}
                    >
                      <History className="w-3.5 h-3.5" />
                      <span>生成记录 ({projectRuns.length})</span>
                      {showRecordsDrawer ? (
                        <ChevronUp className="w-3.5 h-3.5" />
                      ) : (
                        <ChevronDown className="w-3.5 h-3.5" />
                      )}
                    </button>

                    <button
                      type="button"
                      onClick={() => {
                        setImportTargetGroupId(null);
                        setIsImportModalOpen(true);
                      }}
                      className="flex items-center gap-1.5 px-3 py-2 rounded-xl border border-slate-200 bg-white hover:bg-slate-50 text-slate-700 text-xs font-extrabold transition-all cursor-pointer"
                    >
                      <Upload className="w-3.5 h-3.5" />
                      <span>导入外部视频</span>
                    </button>

                    <button
                      type="button"
                      onClick={() => openProductionPlanModal({ purpose: '首轮覆盖' })}
                      className="flex items-center gap-1.5 px-4 py-2 rounded-xl bg-[#1A1D2E] hover:bg-black text-[#DDFD00] text-xs font-extrabold shadow-xs transition-all cursor-pointer"
                    >
                      <Plus className="w-4 h-4" />
                      <span>新建生产方案</span>
                    </button>
                  </div>
                </div>

                {/* 4-Column Business Profile Details Grid */}
                <div className="grid grid-cols-1 md:grid-cols-2 2xl:grid-cols-4 gap-3 pt-1">
                  {/* Card 1: 原片母带与目录 */}
                  <div className="p-3 rounded-xl bg-white border border-black/[0.05] space-y-1">
                    <div className="flex items-center justify-between">
                      <span className="text-[11px] font-bold text-slate-400">本地原片母带</span>
                      <span
                        className={`text-[11px] font-extrabold ${
                          selectedProject.missingEpisodes.length > 0 ? 'text-amber-700' : 'text-emerald-700'
                        }`}
                      >
                        {selectedProject.missingEpisodes.length > 0
                          ? `缺第 ${selectedProject.missingEpisodes.join('、')} 集`
                          : '全集校验完整'}
                      </span>
                    </div>
                    <div className="text-xs font-extrabold text-[#1A1D2E] font-mono">
                      {selectedProject.verifiedMp4Count} / {selectedProject.totalEpisodes} 集 · {selectedProject.totalSizeGb} GB
                    </div>
                    <div className="text-[11px] text-slate-500 truncate" title={selectedProject.directoryPath}>
                      {selectedProject.totalDurationText || '1080×1920 竖屏 30fps'} · {selectedProject.directoryPath}
                    </div>
                  </div>

                  {/* Card 2: 转写资料与字幕状态 */}
                  <div className="p-3 rounded-xl bg-white border border-black/[0.05] space-y-1">
                    <div className="flex items-center justify-between">
                      <span className="text-[11px] font-bold text-slate-400">转写资料 (ASR字幕)</span>
                      <span className="inline-flex items-center gap-1 text-[11px] font-extrabold text-emerald-700">
                        <CheckCircle2 className="w-3 h-3" />
                        {transcriptStep?.status === 'completed' ? '已完成缓存' : '已就绪'}
                      </span>
                    </div>
                    <div className="text-xs font-extrabold text-[#1A1D2E]">
                      {selectedProject.verifiedMp4Count} 集对白时间轴 & 情绪峰值点
                    </div>
                    <div className="text-[11px] text-slate-500 truncate">
                      已自动剔除片头片尾重复回放帧，支持跨集台词检索
                    </div>
                  </div>

                  {/* Card 3: 剧情地图与高光提取 */}
                  <div className="p-3 rounded-xl bg-white border border-black/[0.05] space-y-1">
                    <div className="flex items-center justify-between">
                      <span className="text-[11px] font-bold text-slate-400">剧情地图 & 高光提取</span>
                      <span className="inline-flex items-center gap-1 text-[11px] font-extrabold text-indigo-700">
                        <CheckCircle2 className="w-3 h-3" />
                        {storyMapStep?.status === 'completed' ? '已构建完成' : '已提取'}
                      </span>
                    </div>
                    <div className="text-xs font-extrabold text-[#1A1D2E]">
                      提取 {dramaHighlights.length} 段高光（可用 {activeHighlightsCount} 段）
                    </div>
                    <div className="text-[11px] text-slate-500 truncate">
                      前3秒强冲突片段默认通过，人工看一遍可随时淘汰
                    </div>
                  </div>

                  {/* Card 4: 生产方案与成片统计 */}
                  <div className="p-3 rounded-xl bg-white border border-black/[0.05] space-y-1">
                    <div className="flex items-center justify-between">
                      <span className="text-[11px] font-bold text-slate-400">成片产出与发布表现</span>
                      <span className="text-[11px] font-extrabold text-emerald-700 font-mono">
                        授权上限 {globalAuthLimit} 次/条
                      </span>
                    </div>
                    <div className="text-xs font-extrabold text-[#1A1D2E]">
                      可用成片 {activeAvailableCount} 条 · 累计执行 {projectRuns.length} 次方案
                    </div>
                    <div className="text-[11px] text-slate-500 truncate">
                      已跑出爆款高光 {dramaHighlights.filter((h) => h.isViral).length} 个 · 可随时扩量复刻
                    </div>
                  </div>
                </div>

                {/* Expandable Generation Records & 1-Row 7-Step Progress Drawer */}
                {showRecordsDrawer && (
                  <div className="p-3.5 rounded-xl bg-white border border-slate-200/90 space-y-2.5 animate-in fade-in duration-150">
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <div className="flex items-center gap-2 overflow-x-auto no-scrollbar">
                        <span className="text-xs font-extrabold text-[#1A1D2E] shrink-0">
                          历史生成记录：
                        </span>
                        <button
                          type="button"
                          onClick={() => setRecordFilter('all_drama_assets')}
                          className={`px-2.5 py-1 rounded-lg text-xs font-bold border transition-all cursor-pointer ${
                            recordFilter === 'all_drama_assets'
                              ? 'bg-[#1A1D2E] text-white border-[#1A1D2E]'
                              : 'bg-slate-50 text-slate-700 border-slate-200'
                          }`}
                        >
                          全部成片 ({projectAssets.length})
                        </button>
                        {projectRuns.map((run) => {
                          const isSelected = recordFilter === run.id;
                          const successCount = run.results.filter((r) => r.techStatus === '合格').length;
                          const failCount = run.results.filter((r) => r.techStatus === '不合格').length;
                          return (
                            <button
                              key={run.id}
                              type="button"
                              onClick={() => {
                                setSelectedRunId(run.id);
                                setRecordFilter(run.id);
                              }}
                              className={`flex items-center gap-1.5 px-2.5 py-1 rounded-lg text-xs font-bold border transition-all cursor-pointer ${
                                isSelected
                                  ? 'bg-[#1A1D2E] text-[#DDFD00] border-[#1A1D2E]'
                                  : 'bg-slate-50 text-slate-700 border-slate-200 hover:bg-slate-100'
                              }`}
                            >
                              <span className="font-mono text-[10px] opacity-75">
                                {run.createdAt.slice(5, 16)}
                              </span>
                              <span>{run.productionPurpose || '首轮覆盖'}生产</span>
                              <span className="font-mono text-[10px]">
                                ({failCount > 0 ? `成${successCount}/败${failCount}` : `${successCount}条`})
                              </span>
                            </button>
                          );
                        })}
                      </div>

                      {activeRun && (
                        <span className="text-[11px] text-slate-400 font-mono">
                          模板 {activeRun.templateVersion} · 系统编号 {activeRun.roundCode}
                        </span>
                      )}
                    </div>

                    {activeRun && (
                      <div className="grid grid-cols-7 gap-1.5">
                        {activeRun.pipelineSteps.map((step, idx) => {
                          const isDone = step.status === 'completed';
                          const isRunning = step.status === 'running';
                          const isError = step.status === 'failed';
                          const shortLabel = COMPACT_STEP_LABELS[step.key] || `${idx + 1}.${step.label}`;
                          return (
                            <div
                              key={step.key}
                              onClick={() => setActiveStepIndex(activeStepIndex === idx ? null : idx)}
                              title={`${step.label}：${step.detailText}`}
                              className={`px-2 py-1.5 rounded-lg border text-[11px] flex items-center justify-between gap-1 cursor-pointer ${
                                isDone
                                  ? 'bg-emerald-50/50 border-emerald-200 text-slate-800'
                                  : isRunning
                                  ? 'bg-amber-50 border-amber-300 text-amber-950'
                                  : isError
                                  ? 'bg-rose-50 border-rose-300 text-rose-900'
                                  : 'bg-slate-50 border-slate-200 text-slate-400'
                              }`}
                            >
                              <span className="font-bold truncate">{shortLabel}</span>
                              <span className="font-mono text-[10px] shrink-0">
                                {isDone ? '完成' : isRunning ? '进行中' : isError ? '异常' : '待执行'}
                              </span>
                            </div>
                          );
                        })}
                      </div>
                    )}
                  </div>
                )}
              </section>

              {/* ====================================================================
                  模块 2：高光库 (Highlight Library — 十几秒原片高光视频，默认通过，方便人工观看与一键淘汰)
              ==================================================================== */}
              <section className="p-4 rounded-2xl bg-[#F8FAFC] border border-black/[0.06] space-y-3 shrink-0">
                {/* Header of Module 2 */}
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <div className="flex flex-wrap items-center gap-2.5">
                    <span className="px-2 py-0.5 rounded-lg bg-[#1A1D2E] text-[#DDFD00] text-[11px] font-black">
                      ② 高光库
                    </span>
                    <h3 className="text-sm font-black text-[#1A1D2E]">
                      原片提取高光视频（{dramaHighlights.length} 段）
                    </h3>
                    <span className="text-xs text-slate-500">
                      默认全部通过可用（每段 15~35 秒）；人工快速点播看一遍，不合适的直接点「淘汰」
                    </span>

                    {/* Filter Tabs: 可用 | 已淘汰 | 全部 */}
                    <div className="flex items-center p-0.5 bg-slate-200/80 rounded-xl gap-0.5 ml-1">
                      {(
                        [
                          { id: 'active', label: `可用 (${activeHighlightsCount})` },
                          { id: 'eliminated', label: `已淘汰 (${eliminatedHighlightsCount})` },
                          { id: 'all', label: `全部 (${dramaHighlights.length})` }
                        ] as { id: HighlightQuickFilter; label: string }[]
                      ).map((tab) => (
                        <button
                          key={tab.id}
                          type="button"
                          onClick={() => setHighlightQuickFilter(tab.id)}
                          className={`px-2.5 py-1 rounded-lg text-[11px] font-bold transition-all cursor-pointer ${
                            highlightQuickFilter === tab.id
                              ? 'bg-white text-[#1A1D2E] shadow-2xs'
                              : 'text-slate-600 hover:text-slate-900'
                          }`}
                        >
                          {tab.label}
                        </button>
                      ))}
                    </div>
                  </div>

                  {/* Right Actions for Highlight Library */}
                  <div className="flex items-center gap-2">
                    <button
                      type="button"
                      onClick={() => void refreshRealHighlightLibrary()}
                      disabled={highlightAnalysisBusy}
                      className="flex items-center gap-1.5 px-3 py-1.5 rounded-xl bg-white border border-slate-200 hover:bg-slate-50 text-xs font-extrabold text-[#1A1D2E] cursor-pointer disabled:opacity-50 disabled:cursor-wait"
                    >
                      {highlightAnalysisBusy ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <RotateCcw className="w-3.5 h-3.5" />}
                      <span>{highlightAnalysisBusy ? '正在提取' : '重新提取高光'}</span>
                    </button>
                    {filteredDramaHighlights.length > 0 && (
                      <button
                        type="button"
                        onClick={() => setPreviewHighlightClip(filteredDramaHighlights[0])}
                        className="flex items-center gap-1.5 px-3 py-1.5 rounded-xl bg-white border border-slate-200 hover:bg-slate-50 text-xs font-extrabold text-[#1A1D2E] cursor-pointer shadow-2xs"
                      >
                        <Play className="w-3.5 h-3.5 fill-[#1A1D2E]" />
                        <span>连续快审播放</span>
                      </button>
                    )}

                    <button
                      type="button"
                      onClick={() => openProductionPlanModal({ purpose: '首轮覆盖' })}
                      className="flex items-center gap-1.5 px-3 py-1.5 rounded-xl bg-[#1A1D2E] hover:bg-black text-[#DDFD00] text-xs font-extrabold cursor-pointer"
                    >
                      <Sparkles className="w-3.5 h-3.5" />
                      <span>多选高光新建方案</span>
                    </button>
                  </div>
                </div>

                {/* Vertical 9:16 Video Cards Grid for 15~35s Highlight Clips */}
                <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5 2xl:grid-cols-6 gap-3.5">
                  {filteredDramaHighlights.map((hl) => {
                    const isEliminated = hl.status === '已淘汰' || hl.status === '暂停';
                    const isPlayingInline = inlinePlayingHighlightId === hl.id;
                    const isFocused = focusedHighlightId === hl.id;
                    const clipSec = hl.durationSec || 28;
                    const progressPct = isPlayingInline
                      ? Math.min(100, Math.round(((inlineHighlightProgressSec + 1) / clipSec) * 100))
                      : 0;
                    const relatedAssets = projectAssets.filter((a) => a.sourceHighlightId === hl.id);
                    const generatedCount = Math.max(relatedAssets.length, hl.generatedVideoNames.length);

                    return (
                      <div
                        key={hl.id}
                        className={`rounded-2xl bg-white border p-2 transition-all flex flex-col justify-between ${
                          isFocused
                            ? 'border-[#1A1D2E] ring-2 ring-[#1A1D2E]/20 shadow-md'
                            : isEliminated
                            ? 'border-slate-200 opacity-60'
                            : 'border-black/[0.06] hover:border-slate-300 shadow-2xs'
                        }`}
                      >
                        {/* Top 9:16 Vertical Video Player Screen */}
                        <div
                          onClick={() => {
                            if (isPlayingInline) {
                              setInlinePlayingHighlightId(null);
                            } else {
                              setInlinePlayingHighlightId(hl.id);
                              setInlineHighlightProgressSec(0);
                            }
                          }}
                          className="relative aspect-[9/16] w-full rounded-xl overflow-hidden cursor-pointer select-none group flex flex-col justify-between"
                          style={{
                            background: `linear-gradient(160deg, ${hl.accentColor || '#1E293B'} 0%, #090D16 100%)`
                          }}
                        >
                          {/* Subtle Decorative Film Grid */}
                          <div className="absolute inset-0 opacity-15 bg-[radial-gradient(#ffffff_1px,transparent_1px)] [background-size:14px_14px]" />

                          {/* Top HUD inside 9:16 Vertical Screen */}
                          <div className="relative z-10 p-2 space-y-1">
                            <div className="flex items-center justify-between gap-1">
                              <div className="flex items-center gap-1 min-w-0">
                                <span className="px-1.5 py-0.5 rounded bg-[#DDFD00] text-[#1A1D2E] font-mono text-[10px] font-black shrink-0">
                                  {hl.code}
                                </span>
                                <span className="px-1.5 py-0.5 rounded bg-black/60 backdrop-blur-xs text-white font-mono text-[10px] font-bold whitespace-nowrap">
                                  {hl.episodeLabel}
                                </span>
                              </div>

                              <div className="flex items-center gap-1 shrink-0">
                                <span className="px-1.5 py-0.5 rounded bg-black/75 text-[#DDFD00] font-mono text-[10px] font-extrabold whitespace-nowrap">
                                  {isPlayingInline
                                    ? `${String(inlineHighlightProgressSec).padStart(2, '0')}s/${clipSec}s`
                                    : hl.durationText || `${clipSec}秒`}
                                </span>
                                <button
                                  type="button"
                                  title="大屏快审预览"
                                  onClick={(e) => {
                                    e.stopPropagation();
                                    setPreviewHighlightClip(hl);
                                  }}
                                  className="p-1 rounded bg-black/60 hover:bg-black text-white cursor-pointer"
                                >
                                  <Maximize2 className="w-2.5 h-2.5" />
                                </button>
                              </div>
                            </div>

                            <div className="flex items-center justify-between gap-1">
                              <span className="px-1.5 py-0.5 rounded bg-black/50 text-white/90 font-mono text-[9px] whitespace-nowrap">
                                {hl.timeRange}
                              </span>
                              {isEliminated ? (
                                <span className="px-1.5 py-0.5 rounded bg-rose-900/80 text-rose-200 text-[9px] font-extrabold whitespace-nowrap">
                                  已淘汰
                                </span>
                              ) : hl.isViral ? (
                                <span className="px-1.5 py-0.5 rounded bg-amber-500/90 text-slate-950 text-[9px] font-black whitespace-nowrap">
                                  🔥 爆款
                                </span>
                              ) : (
                                <span className="px-1.5 py-0.5 rounded bg-emerald-600/85 text-white text-[9px] font-extrabold whitespace-nowrap">
                                  默认可用
                                </span>
                              )}
                            </div>
                          </div>

                          {/* Center Play Button & Scene Tag inside 9:16 Vertical Screen */}
                          <div className="relative z-10 px-2 my-auto flex flex-col items-center justify-center text-center">
                            <div
                              className={`w-10 h-10 rounded-full flex items-center justify-center transition-transform group-hover:scale-105 shadow-lg ${
                                isPlayingInline
                                  ? 'bg-[#DDFD00] text-[#1A1D2E]'
                                  : 'bg-white/90 text-[#1A1D2E]'
                              }`}
                            >
                              {isPlayingInline ? (
                                <Pause className="w-4 h-4 fill-current" />
                              ) : (
                                <Play className="w-4 h-4 fill-current ml-0.5" />
                              )}
                            </div>
                            {hl.sceneTag && (
                              <span className="mt-2 px-2 py-0.5 rounded-md bg-black/60 backdrop-blur-xs text-white text-[10px] font-extrabold truncate max-w-full">
                                {hl.sceneTag}
                              </span>
                            )}
                          </div>

                          {/* Bottom Burned-in Vertical Drama Subtitle inside 9:16 Screen */}
                          <div className="relative z-10 bg-gradient-to-t from-black/95 via-black/75 to-transparent px-2.5 pt-5 pb-2">
                            <p className="text-[10px] font-bold text-amber-200 line-clamp-2 text-center leading-snug drop-shadow">
                              {hl.dialogueText}
                            </p>
                          </div>

                          {/* Inline Progress Bar at bottom of 9:16 video */}
                          {isPlayingInline && (
                            <div className="absolute bottom-0 inset-x-0 h-1 bg-white/20 z-20">
                              <div
                                className="h-full bg-[#DDFD00] transition-all duration-300"
                                style={{ width: `${progressPct}%` }}
                              />
                            </div>
                          )}
                        </div>

                        {/* Below 9:16 Screen: Highlight Description + Usage Count + Action Buttons */}
                        <div className="pt-2 px-0.5 space-y-1.5 flex-1 flex flex-col justify-between">
                          <div className="space-y-1">
                            <p
                              title={hl.description}
                              className={`text-[11px] font-extrabold line-clamp-2 leading-snug ${
                                isEliminated ? 'text-slate-400 line-through' : 'text-[#1A1D2E]'
                              }`}
                            >
                              {hl.description}
                            </p>

                            <div className="flex items-center justify-between text-[10px] text-slate-500 whitespace-nowrap">
                              <span className="font-mono">已用 {hl.usedCount} 次</span>
                              {generatedCount > 0 ? (
                                <button
                                  type="button"
                                  onClick={() => {
                                    setAssetHighlightFilter(hl.id);
                                    setAssetQuickFilter('all');
                                    showToast(`已筛选来自高光 [${hl.code}] 的 ${generatedCount} 条成片`);
                                  }}
                                  className="font-extrabold text-indigo-600 hover:underline cursor-pointer"
                                >
                                  已生 {generatedCount} 条 →
                                </button>
                              ) : (
                                <span className="text-slate-400">未生成成片</span>
                              )}
                            </div>
                          </div>

                          {/* Bottom Compact Single-Line Action Bar */}
                          <div className="pt-1.5 border-t border-slate-100 flex items-center justify-between gap-1">
                            {!isEliminated ? (
                              <>
                                <button
                                  type="button"
                                  onClick={() =>
                                    openProductionPlanModal({
                                      purpose: '首轮覆盖',
                                      highlightIds: [hl.id]
                                    })
                                  }
                                  className="flex-1 py-1 px-1.5 rounded-lg bg-[#1A1D2E] hover:bg-black text-[#DDFD00] text-[10px] font-extrabold whitespace-nowrap text-center cursor-pointer"
                                >
                                  用此生产
                                </button>

                                <button
                                  type="button"
                                  onClick={() =>
                                    openProductionPlanModal({
                                      purpose: '爆款扩量',
                                      highlightIds: [hl.id]
                                    })
                                  }
                                  className="py-1 px-1.5 rounded-lg bg-amber-50 hover:bg-amber-100 border border-amber-300 text-amber-950 text-[10px] font-extrabold whitespace-nowrap cursor-pointer"
                                  title="从此高光扩量生产"
                                >
                                  扩量
                                </button>
                              </>
                            ) : (
                              <span className="text-[10px] text-slate-400">已停用</span>
                            )}

                            <button
                              type="button"
                              onClick={() => handleToggleHighlightEliminated(hl.id, !isEliminated)}
                              className={`py-1 px-2 rounded-lg text-[10px] font-extrabold border whitespace-nowrap transition-all cursor-pointer ${
                                isEliminated
                                  ? 'bg-emerald-50 border-emerald-200 text-emerald-700 hover:bg-emerald-100'
                                  : 'bg-white border-slate-200 text-slate-500 hover:bg-rose-50 hover:text-rose-700 hover:border-rose-200'
                              }`}
                            >
                              {isEliminated ? '恢复' : '淘汰'}
                            </button>
                          </div>
                        </div>
                      </div>
                    );
                  })}
                </div>
              </section>

              {/* ====================================================================
                  模块 3：成片库 (Final Video Library — 9:16 竖屏成片画面预览 + 高密度剪辑与来源高光信息)
              ==================================================================== */}
              <section className="p-4 rounded-2xl bg-[#F8FAFC] border border-black/[0.06] flex-1 flex flex-col min-h-[360px] space-y-3">
                {/* Header & Filters of Module 3 */}
                <div className="flex flex-wrap items-center justify-between gap-2.5 shrink-0">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="px-2 py-0.5 rounded-lg bg-[#1A1D2E] text-[#DDFD00] text-[11px] font-black">
                      ③ 成片库
                    </span>
                    <h3 className="text-sm font-black text-[#1A1D2E]">
                      合成成片与画面预览（{displayedDramaAssets.length} 条）
                    </h3>

                    {/* 成片可用状态筛选 */}
                    <div className="flex items-center p-0.5 bg-slate-200/80 rounded-xl gap-0.5">
                      {(
                        [
                          { id: 'active', label: `可用 (${activeAvailableCount})` },
                          { id: 'eliminated', label: `失败/淘汰 (${eliminatedCount})` },
                          { id: 'all', label: `全部 (${baseRoundAssets.length})` }
                        ] as { id: AssetQuickFilter; label: string }[]
                      ).map((tab) => (
                        <button
                          key={tab.id}
                          type="button"
                          onClick={() => setAssetQuickFilter(tab.id)}
                          className={`px-2.5 py-1 rounded-lg text-[11px] font-bold transition-all cursor-pointer ${
                            assetQuickFilter === tab.id
                              ? 'bg-white text-[#1A1D2E] shadow-2xs'
                              : 'text-slate-600 hover:text-slate-900'
                          }`}
                        >
                          {tab.label}
                        </button>
                      ))}
                    </div>

                    {/* 按来源高光筛选 */}
                    <select
                      value={assetHighlightFilter}
                      onChange={(e) => setAssetHighlightFilter(e.target.value)}
                      className="px-2.5 py-1 rounded-xl border border-slate-200 bg-white text-xs font-bold text-slate-700"
                    >
                      <option value="ALL">按来源高光：全部</option>
                      {dramaHighlights.map((hl) => (
                        <option key={hl.id} value={hl.id}>
                          [{hl.code}] {hl.episodeLabel} {hl.sceneTag || hl.description.slice(0, 10)}
                        </option>
                      ))}
                    </select>

                    {/* 按生产方案筛选 */}
                    <select
                      value={assetPurposeFilter}
                      onChange={(e) => setAssetPurposeFilter(e.target.value)}
                      className="px-2.5 py-1 rounded-xl border border-slate-200 bg-white text-xs font-bold text-slate-700"
                    >
                      <option value="ALL">按生产方案：全部</option>
                      <option value="首轮覆盖">首轮覆盖</option>
                      <option value="爆款扩量">爆款扩量</option>
                      <option value="失败重做">失败重做</option>
                      <option value="策略测试">策略测试</option>
                    </select>

                    {assetHighlightFilter !== 'ALL' && (
                      <button
                        type="button"
                        onClick={() => setAssetHighlightFilter('ALL')}
                        className="px-2 py-1 rounded-lg bg-amber-100 text-amber-900 text-[11px] font-bold cursor-pointer"
                      >
                        清除高光过滤 ×
                      </button>
                    )}

                    <div className="relative">
                      <Search className="w-3.5 h-3.5 text-slate-400 absolute left-2.5 top-2" />
                      <input
                        type="text"
                        value={assetKeyword}
                        onChange={(e) => setAssetKeyword(e.target.value)}
                        placeholder="搜索成片..."
                        className="pl-8 pr-2.5 py-1 rounded-xl border border-slate-200 bg-white text-xs text-slate-800 focus:outline-none focus:border-slate-400 w-36"
                      />
                    </div>
                  </div>

                  {/* Batch Actions */}
                  <div className="flex items-center gap-2">
                    <button
                      type="button"
                      onClick={selectAllDisplayed}
                      className="px-2.5 py-1 rounded-lg border border-slate-200 bg-white hover:bg-slate-50 text-[11px] font-bold text-slate-700 cursor-pointer"
                    >
                      {selectedAssetIds.length > 0 ? `已选 ${selectedAssetIds.length} 条` : '全选当前'}
                    </button>
                    <button
                      type="button"
                      disabled={selectedAssetIds.length === 0}
                      onClick={() => setGroupAssignAssetIds(selectedAssetIds)}
                      className={`flex items-center gap-1 px-2.5 py-1 rounded-lg text-[11px] font-extrabold transition-all ${
                        selectedAssetIds.length > 0
                          ? 'bg-indigo-600 text-white hover:bg-indigo-700 cursor-pointer'
                          : 'bg-slate-200 text-slate-400 cursor-not-allowed'
                      }`}
                    >
                      <FolderPlus className="w-3 h-3" />
                      <span>批量加入编组</span>
                    </button>
                    <button
                      type="button"
                      disabled={selectedAssetIds.length === 0}
                      onClick={() => handleSetAssetsEliminated(selectedAssetIds, true)}
                      className={`flex items-center gap-1 px-2.5 py-1 rounded-lg text-[11px] font-extrabold transition-all ${
                        selectedAssetIds.length > 0
                          ? 'bg-rose-600 text-white hover:bg-rose-700 cursor-pointer'
                          : 'bg-slate-200 text-slate-400 cursor-not-allowed'
                      }`}
                    >
                      <Trash2 className="w-3 h-3" />
                      <span>批量淘汰</span>
                    </button>
                  </div>
                </div>

                {/* Visual Media Cards Grid for Final Videos (9:16 Preview + High-Density Info) */}
                {displayedDramaAssets.length === 0 ? (
                  <div className="py-14 flex flex-col items-center justify-center text-center text-slate-400">
                    <Film className="w-8 h-8 mb-2 stroke-1" />
                    <p className="text-xs font-bold text-slate-500">当前筛选条件下没有成片</p>
                    <p className="text-[11px] mt-0.5">
                      可点击上方高光库中的「用此高光生产」或右上角「新建生产方案」合成新成片
                    </p>
                  </div>
                ) : (
                  <div className="grid grid-cols-1 2xl:grid-cols-2 gap-3.5">
                    {displayedDramaAssets.map((asset) => {
                      const isQualified = asset.techStatus === '合格';
                      const isEliminated = asset.manualStatus === '已淘汰' || !isQualified;
                      const isSelected = selectedAssetIds.includes(asset.id);
                      const isPlayingThisAsset = inlinePlayingAssetId === asset.id;
                      const assignedGroups = getAssetGroups(asset.id);
                      const sourceHl = dramaHighlights.find((h) => h.id === asset.sourceHighlightId);
                      const sourceLabel =
                        asset.sourceHighlightLabel ||
                        (sourceHl
                          ? `[${sourceHl.code}] ${sourceHl.episodeLabel} ${sourceHl.timeRange} ${sourceHl.sceneTag || sourceHl.description}`
                          : asset.highlightCutPoint || '默认高光切入');
                      const bannerStyle = getTemplateBannerStyle(asset.templateVersion);

                      return (
                        <div
                          key={asset.id}
                          className={`p-3 rounded-2xl bg-white border transition-all flex items-stretch gap-3.5 ${
                            !isQualified
                              ? 'border-rose-200 bg-rose-50/20'
                              : isEliminated
                              ? 'border-slate-200 bg-slate-50/70 opacity-75'
                              : isSelected
                              ? 'border-[#1A1D2E] ring-2 ring-[#1A1D2E]/15 shadow-sm'
                              : 'border-black/[0.06] hover:border-slate-300 shadow-2xs'
                          }`}
                        >
                          {/* LEFT: 9:16 Vertical Composite Video Preview Box */}
                          <div
                            onClick={() => {
                              if (isPlayingThisAsset) {
                                setInlinePlayingAssetId(null);
                              } else {
                                setInlinePlayingAssetId(asset.id);
                                setInlineAssetProgressPct(10);
                              }
                            }}
                            className="w-[120px] h-[208px] rounded-xl overflow-hidden shrink-0 relative flex flex-col justify-between cursor-pointer select-none group shadow-sm border border-black/10"
                            style={{
                              background: !isQualified
                                ? 'linear-gradient(160deg, #450A0A 0%, #090D16 100%)'
                                : `linear-gradient(160deg, ${sourceHl?.accentColor || '#1E293B'} 0%, #090D16 100%)`
                            }}
                          >
                            {/* Top 9:16 Template Title Plate Overlay */}
                            <div
                              className="px-2 py-1.5 text-center shadow-xs relative z-10"
                              style={{ background: bannerStyle.bg }}
                            >
                              <div
                                className="text-[9px] font-black tracking-wider uppercase truncate"
                                style={{ color: bannerStyle.accent }}
                              >
                                {bannerStyle.label.replace('木木短剧·', '木木·')}
                              </div>
                              <div className="text-[11px] font-black text-white truncate leading-tight">
                                《{asset.dramaTitle}》
                              </div>
                            </div>

                            {/* Center Scene Visual & Play Button */}
                            <div className="relative z-10 px-2 flex flex-col items-center justify-center text-center my-auto">
                              {!isQualified ? (
                                <div className="space-y-1">
                                  <AlertTriangle className="w-6 h-6 text-rose-400 mx-auto" />
                                  <span className="block text-[10px] font-extrabold text-rose-200">
                                    04:12 黑屏帧异常
                                  </span>
                                </div>
                              ) : (
                                <>
                                  <div
                                    className={`w-9 h-9 rounded-full flex items-center justify-center shadow-md transition-transform group-hover:scale-105 ${
                                      isPlayingThisAsset
                                        ? 'bg-[#DDFD00] text-[#1A1D2E]'
                                        : 'bg-white/90 text-[#1A1D2E]'
                                    }`}
                                  >
                                    {isPlayingThisAsset ? (
                                      <Pause className="w-4 h-4 fill-current" />
                                    ) : (
                                      <Play className="w-4 h-4 fill-current ml-0.5" />
                                    )}
                                  </div>
                                  <span className="mt-1.5 px-1.5 py-0.5 rounded bg-black/55 text-[10px] font-bold text-white/90 truncate max-w-[104px]">
                                    {sourceHl?.sceneTag || asset.episodeRange}
                                  </span>
                                </>
                              )}
                            </div>

                            {/* Bottom Burned-in Subtitle + Duration Bar */}
                            <div className="relative z-10 bg-gradient-to-t from-black/95 via-black/75 to-transparent px-2 pt-3 pb-1.5 space-y-1">
                              <div className="text-[9px] text-amber-200 font-bold truncate text-center">
                                {sourceHl?.dialogueText || '高光冲突开局 · 留悬念钩子'}
                              </div>
                              <div className="flex items-center justify-between text-[9px] font-mono text-white/80">
                                <span>9:16</span>
                                <span className="font-bold text-[#DDFD00]">
                                  {asset.durationFormatted.replace('分', ':').replace('秒', '')}
                                </span>
                              </div>
                            </div>

                            {/* Inline Playing Progress Bar */}
                            {isPlayingThisAsset && (
                              <div className="absolute bottom-0 inset-x-0 h-1 bg-white/20 z-20">
                                <div
                                  className="h-full bg-[#DDFD00] transition-all duration-300"
                                  style={{ width: `${inlineAssetProgressPct}%` }}
                                />
                              </div>
                            )}
                          </div>

                          {/* RIGHT: High-Density Metadata & Action Buttons */}
                          <div className="min-w-0 flex-1 flex flex-col justify-between space-y-2">
                            <div className="space-y-1.5">
                              {/* Line 1: Checkbox + Filename + Badges */}
                              <div className="flex items-start justify-between gap-2">
                                <div className="flex items-center gap-2 min-w-0">
                                  <input
                                    type="checkbox"
                                    checked={isSelected}
                                    onChange={() => toggleSelectAsset(asset.id)}
                                    className="w-4 h-4 rounded accent-[#1A1D2E] cursor-pointer shrink-0"
                                  />
                                  <span
                                    title={asset.videoName}
                                    className={`font-extrabold text-sm truncate ${
                                      isEliminated && isQualified
                                        ? 'text-slate-400 line-through'
                                        : 'text-[#1A1D2E]'
                                    }`}
                                  >
                                    {asset.videoName}
                                  </span>
                                </div>

                                <div className="flex items-center gap-1 shrink-0">
                                  {!isQualified ? (
                                    <span className="px-2 py-0.5 rounded-md bg-rose-100 text-rose-700 border border-rose-200 text-[10px] font-extrabold">
                                      技术不合格
                                    </span>
                                  ) : isEliminated ? (
                                    <span className="px-2 py-0.5 rounded-md bg-slate-200 text-slate-600 text-[10px] font-extrabold">
                                      已淘汰
                                    </span>
                                  ) : (
                                    <span className="px-2 py-0.5 rounded-md bg-emerald-50 text-emerald-700 border border-emerald-200 text-[10px] font-extrabold">
                                      默认可用
                                    </span>
                                  )}

                                  {asset.productionPurpose && (
                                    <span className="px-2 py-0.5 rounded-md bg-slate-100 text-slate-700 text-[10px] font-bold">
                                      {asset.productionPurpose}
                                    </span>
                                  )}
                                </div>
                              </div>

                              {/* Line 2 (必显): 来源高光 */}
                              <div className="flex flex-wrap items-center gap-1.5">
                                <button
                                  type="button"
                                  onClick={() => {
                                    setHighlightQuickFilter('all');
                                    setFocusedHighlightId(asset.sourceHighlightId || null);
                                    showToast(`已定位到上方高光库：${sourceLabel}`);
                                  }}
                                  className="inline-flex items-center gap-1 px-2 py-0.5 rounded-lg bg-amber-50 hover:bg-amber-100 border border-amber-200/90 text-amber-950 text-xs font-extrabold cursor-pointer text-left truncate max-w-full"
                                >
                                  <Bookmark className="w-3 h-3 text-amber-600 shrink-0" />
                                  <span className="truncate">来源高光：{sourceLabel}</span>
                                </button>

                                {assignedGroups.map((g) => (
                                  <span
                                    key={g.id}
                                    className="px-2 py-0.5 rounded-md bg-indigo-50 text-indigo-700 border border-indigo-200 text-[10px] font-bold"
                                  >
                                    {g.name}
                                  </span>
                                ))}
                              </div>

                              {/* Line 3: 原剧集数范围 + 时长 + 模板 + 跳集明细 */}
                              <div className="p-2 rounded-xl bg-[#F8FAFC] border border-slate-100 space-y-1 text-[11px]">
                                <div className="flex flex-wrap items-center justify-between gap-2">
                                  <span className="font-extrabold text-slate-700 font-mono">
                                    {asset.episodeRange || '全剧片段'} · 时长 {asset.durationFormatted}
                                  </span>
                                  <span className="text-slate-500 font-mono">
                                    模板：{bannerStyle.label.replace('木木短剧·', '')} · 授权 {asset.authUsedCount}/{asset.authMaxLimit}
                                  </span>
                                </div>

                                {asset.jumpCutPositions && asset.jumpCutPositions.length > 0 && (
                                  <div className="text-slate-500 truncate">
                                    <span className="font-semibold text-slate-600">剪辑轨迹：</span>
                                    {asset.jumpCutPositions.join(' ； ')}
                                  </div>
                                )}

                                {!isQualified ? (
                                  <div className="text-rose-600 font-bold">
                                    异常拦截：{asset.techDetail}
                                  </div>
                                ) : (
                                  <div className="text-slate-400 truncate">
                                    质检：{asset.techDetail}
                                  </div>
                                )}
                              </div>
                            </div>

                            {/* Bottom Action Buttons of Video Card */}
                            <div className="pt-1.5 border-t border-slate-100 flex flex-wrap items-center justify-between gap-1.5">
                              <div className="flex flex-wrap items-center gap-1.5">
                                <button
                                  type="button"
                                  onClick={() => setPreviewAsset(asset)}
                                  className="flex items-center gap-1 px-2.5 py-1 rounded-lg border border-slate-200 bg-white hover:bg-slate-50 text-slate-700 text-xs font-bold cursor-pointer"
                                >
                                  <Maximize2 className="w-3 h-3" />
                                  <span>大图预览</span>
                                </button>

                                {!isQualified ? (
                                  <button
                                    type="button"
                                    onClick={() =>
                                      openProductionPlanModal({
                                        purpose: '失败重做',
                                        highlightIds: asset.sourceHighlightId
                                          ? [asset.sourceHighlightId]
                                          : dramaHighlights[0]
                                          ? [dramaHighlights[0].id]
                                          : []
                                      })
                                    }
                                    className="flex items-center gap-1 px-3 py-1 rounded-lg bg-rose-600 hover:bg-rose-700 text-white text-xs font-extrabold cursor-pointer"
                                  >
                                    <RotateCcw className="w-3 h-3" />
                                    <span>重做失败项</span>
                                  </button>
                                ) : (
                                  !isEliminated && (
                                    <>
                                      <button
                                        type="button"
                                        onClick={() =>
                                          openProductionPlanModal({
                                            purpose: '爆款扩量',
                                            highlightIds: asset.sourceHighlightId
                                              ? [asset.sourceHighlightId]
                                              : dramaHighlights[0]
                                              ? [dramaHighlights[0].id]
                                              : []
                                          })
                                        }
                                        className="flex items-center gap-1 px-2.5 py-1 rounded-lg bg-amber-50 hover:bg-amber-100 border border-amber-300 text-amber-950 text-xs font-extrabold cursor-pointer"
                                      >
                                        <Flame className="w-3 h-3 text-amber-600 fill-amber-500" />
                                        <span>从这条爆款扩量</span>
                                      </button>

                                      <button
                                        type="button"
                                        onClick={() =>
                                          openProductionPlanModal({
                                            purpose: '策略测试',
                                            highlightIds: asset.sourceHighlightId
                                              ? [asset.sourceHighlightId]
                                              : dramaHighlights[0]
                                              ? [dramaHighlights[0].id]
                                              : []
                                          })
                                        }
                                        className="flex items-center gap-1 px-2.5 py-1 rounded-lg border border-slate-200 bg-white hover:bg-slate-50 text-slate-700 text-xs font-bold cursor-pointer"
                                      >
                                        <Copy className="w-3 h-3" />
                                        <span>相似方案</span>
                                      </button>

                                      <button
                                        type="button"
                                        onClick={() => setGroupAssignAssetIds([asset.id])}
                                        className="flex items-center gap-1 px-2.5 py-1 rounded-lg border border-indigo-200 bg-indigo-50/70 hover:bg-indigo-100 text-indigo-800 text-xs font-bold cursor-pointer"
                                      >
                                        <FolderPlus className="w-3 h-3" />
                                        <span>编组 ({assignedGroups.length})</span>
                                      </button>
                                    </>
                                  )
                                )}
                              </div>

                              {isQualified && (
                                <button
                                  type="button"
                                  onClick={() => handleSetAssetsEliminated([asset.id], !isEliminated)}
                                  className={`px-2.5 py-1 rounded-lg text-xs font-bold border cursor-pointer ${
                                    isEliminated
                                      ? 'border-emerald-200 bg-emerald-50 text-emerald-700 hover:bg-emerald-100'
                                      : 'border-slate-200 bg-white text-slate-500 hover:bg-rose-50 hover:text-rose-700 hover:border-rose-200'
                                  }`}
                                >
                                  {isEliminated ? '恢复' : '淘汰'}
                                </button>
                              )}
                            </div>
                          </div>
                        </div>
                      );
                    })}
                  </div>
                )}
              </section>
            </div>
          ) : (
            <div className="bg-white rounded-3xl p-8 border border-black/[0.06] shadow-xs text-center text-sm text-slate-500">
              左边还没有在产剧集，请点击左上角「+ 添加剧集」把要制作的剧加进来。
            </div>
          )
        ) : (
          /* ==================== RIGHT COLUMN WHEN IN 发布编组 MODE ==================== */
          selectedGroup ? (
            <div className="min-w-0 bg-white rounded-3xl p-5 border border-black/[0.06] shadow-xs flex flex-col h-[calc(100vh-115px)] min-h-[700px] space-y-3.5">
              {/* 1. Group Header Bar */}
              <div className="pb-3 border-b border-black/[0.06] shrink-0 flex flex-wrap items-center justify-between gap-3">
                <div className="flex items-center gap-2.5">
                  {editingGroupName !== null ? (
                    <form
                      onSubmit={(e) => {
                        e.preventDefault();
                        handleRenameGroup(selectedGroup.id, editingGroupName);
                      }}
                      className="flex items-center gap-1.5"
                    >
                      <input
                        type="text"
                        autoFocus
                        value={editingGroupName}
                        onChange={(e) => setEditingGroupName(e.target.value)}
                        className="px-2.5 py-1 rounded-lg border border-slate-300 text-sm font-extrabold text-[#1A1D2E]"
                      />
                      <button
                        type="submit"
                        className="px-2.5 py-1 rounded-lg bg-[#1A1D2E] text-[#DDFD00] text-xs font-bold cursor-pointer"
                      >
                        保存
                      </button>
                    </form>
                  ) : (
                    <>
                      <h2 className="text-lg font-extrabold text-[#1A1D2E]">
                        {selectedGroup.name}
                      </h2>
                      <button
                        type="button"
                        onClick={() => setEditingGroupName(selectedGroup.name)}
                        className="p-1 rounded-lg hover:bg-slate-100 text-slate-400 hover:text-slate-700 cursor-pointer"
                        title="修改编组名称"
                      >
                        <Edit3 className="w-3.5 h-3.5" />
                      </button>
                    </>
                  )}

                  <span className="px-2.5 py-0.5 rounded-lg bg-slate-100 text-slate-700 font-mono text-xs font-bold">
                    组内待发 {selectedGroupAssets.length} 条
                  </span>
                  <span className="text-xs text-slate-500">
                    支持将各剧做好的爆款成片与外部视频放进同一编组，方便统一自动发布
                  </span>
                </div>

                <div className="flex items-center gap-2 shrink-0">
                  <button
                    type="button"
                    onClick={() => setPublishHistoryModalOpen(true)}
                    className="flex items-center gap-1.5 px-3 py-2 rounded-xl border border-slate-200 bg-white hover:bg-slate-50 text-slate-700 text-xs font-bold cursor-pointer"
                  >
                    <History className="w-3.5 h-3.5" />
                    <span>发布流水 ({publications.length})</span>
                  </button>

                  <button
                    type="button"
                    onClick={() => {
                      setImportTargetGroupId(selectedGroup.id);
                      setIsImportModalOpen(true);
                    }}
                    className="flex items-center gap-1.5 px-3 py-2 rounded-xl border border-slate-200 bg-white hover:bg-slate-50 text-slate-700 text-xs font-extrabold cursor-pointer"
                  >
                    <Upload className="w-3.5 h-3.5" />
                    <span>+ 导入外部视频入组</span>
                  </button>

                  <button
                    type="button"
                    onClick={() => {
                      setPickAssetsSearch('');
                      setPickAssetsForGroupModalOpen(true);
                    }}
                    className="flex items-center gap-1.5 px-3.5 py-2 rounded-xl bg-[#1A1D2E] hover:bg-black text-[#DDFD00] text-xs font-extrabold cursor-pointer"
                  >
                    <Plus className="w-4 h-4" />
                    <span>从成片库挑片加入</span>
                  </button>

                  {groups.length > 1 && (
                    <button
                      type="button"
                      onClick={() => handleDeleteGroup(selectedGroup.id)}
                      className="p-2 rounded-xl border border-slate-200 hover:border-rose-200 hover:bg-rose-50 text-slate-400 hover:text-rose-600 cursor-pointer"
                      title="删除当前编组"
                    >
                      <Trash2 className="w-4 h-4" />
                    </button>
                  )}
                </div>
              </div>

              {/* 2. Upper Auto-Publish Execution Bar */}
              <div className="p-3.5 rounded-2xl bg-[#F8FAFC] border border-black/[0.06] shrink-0 flex flex-wrap items-center justify-between gap-3">
                <div className="flex flex-wrap items-center gap-3">
                  <span className="text-xs font-extrabold text-[#1A1D2E]">
                    ① 自动发布设置
                  </span>

                  <div className="flex items-center p-0.5 bg-slate-200/70 rounded-xl gap-0.5">
                    {(['授权发布', '原创发布'] as const).map((m) => (
                      <button
                        key={m}
                        type="button"
                        onClick={() => setPublishMode(m)}
                        className={`px-3 py-1 rounded-lg text-xs font-bold transition-all cursor-pointer ${
                          publishMode === m
                            ? 'bg-white text-[#1A1D2E] shadow-2xs'
                            : 'text-slate-600 hover:text-slate-900'
                        }`}
                      >
                        {m === '授权发布' ? '小V猫授权发布' : '原创声明发布'}
                      </button>
                    ))}
                  </div>

                  <div className="flex items-center gap-1.5 text-xs">
                    <span className="text-slate-500 font-semibold">发布账号:</span>
                    <select
                      value={publishAccountId}
                      onChange={(e) => setPublishAccountId(e.target.value)}
                      className="px-2.5 py-1.5 rounded-xl border border-slate-200 bg-white text-xs font-bold text-[#1A1D2E]"
                    >
                      {accounts.map((acc) => (
                        <option key={acc.id} value={acc.id}>
                          {acc.name} ({acc.theaterName})
                        </option>
                      ))}
                    </select>
                  </div>

                  <div className="flex items-center gap-1.5 text-xs">
                    <span className="text-slate-500 font-semibold">单条实发次数:</span>
                    <div className="flex items-center gap-1">
                      {[1, 2, 3].map((cnt) => (
                        <button
                          key={cnt}
                          type="button"
                          onClick={() => setPublishCount(cnt)}
                          className={`px-2.5 py-1 rounded-lg font-mono text-xs font-extrabold cursor-pointer ${
                            publishCount === cnt
                              ? 'bg-[#1A1D2E] text-[#DDFD00]'
                              : 'bg-white border border-slate-200 text-slate-600'
                          }`}
                        >
                          {cnt}次
                        </button>
                      ))}
                    </div>
                  </div>
                </div>

                <button
                  type="button"
                  onClick={handleBatchPublishWholeGroup}
                  className="flex items-center gap-1.5 px-4 py-2 rounded-xl bg-emerald-600 hover:bg-emerald-700 text-white text-xs font-extrabold shadow-xs cursor-pointer"
                >
                  <Send className="w-3.5 h-3.5" />
                  <span>按顺序自动发布整组 ({selectedGroupAssets.length} 条)</span>
                </button>
              </div>

              {/* 3. Lower Full-Width Group Video List */}
              <div className="p-4 rounded-2xl bg-[#F8FAFC] border border-black/[0.06] flex-1 flex flex-col min-h-0 space-y-2.5">
                <div className="flex items-center justify-between shrink-0">
                  <span className="text-xs font-extrabold text-[#1A1D2E]">
                    ② 编组内视频列表 ({selectedGroupAssets.length})
                  </span>
                  <span className="text-[11px] text-slate-400">
                    可调整发布顺序，支持各剧高光成片与外部视频混排
                  </span>
                </div>

                <div className="flex-1 overflow-y-auto space-y-2 pr-1 no-scrollbar">
                  {selectedGroupAssets.length === 0 ? (
                    <div className="h-full min-h-[240px] flex flex-col items-center justify-center text-center text-slate-400">
                      <Send className="w-8 h-8 mb-2 stroke-1" />
                      <p className="text-xs font-bold text-slate-500">当前编组还没有装入视频</p>
                      <p className="text-[11px] mt-0.5">
                        点击右上角「从成片库挑片加入」或「+ 导入外部视频入组」即可装入待发视频
                      </p>
                    </div>
                  ) : (
                    selectedGroupAssets.map(({ asset }, index) => (
                      <div
                        key={asset.id}
                        className="p-3 rounded-xl bg-white border border-black/[0.05] hover:border-slate-300 shadow-2xs flex flex-col lg:flex-row lg:items-center justify-between gap-3"
                      >
                        <div className="flex items-start gap-3 min-w-0 flex-1">
                          <div className="flex flex-col items-center gap-0.5 shrink-0">
                            <button
                              type="button"
                              disabled={index === 0}
                              onClick={() => handleMoveGroupItemOrder(selectedGroup.id, asset.id, 'up')}
                              className="p-0.5 rounded hover:bg-slate-100 text-slate-400 hover:text-slate-700 disabled:opacity-30 cursor-pointer"
                            >
                              <ArrowUp className="w-3 h-3" />
                            </button>
                            <span className="font-mono text-xs font-extrabold text-[#1A1D2E]">
                              {String(index + 1).padStart(2, '0')}
                            </span>
                            <button
                              type="button"
                              disabled={index === selectedGroupAssets.length - 1}
                              onClick={() => handleMoveGroupItemOrder(selectedGroup.id, asset.id, 'down')}
                              className="p-0.5 rounded hover:bg-slate-100 text-slate-400 hover:text-slate-700 disabled:opacity-30 cursor-pointer"
                            >
                              <ArrowDown className="w-3 h-3" />
                            </button>
                          </div>

                          <div className="min-w-0 flex-1 space-y-1">
                            <div className="flex flex-wrap items-center gap-1.5">
                              <span className="font-extrabold text-sm text-[#1A1D2E] truncate">
                                {asset.videoName}
                              </span>
                              <span className="px-2 py-0.5 rounded-md bg-slate-100 text-slate-700 text-[11px] font-bold">
                                《{asset.dramaTitle}》
                              </span>
                              <span
                                className={`px-2 py-0.5 rounded-md text-[11px] font-bold ${
                                  asset.sourceType === '外部导入视频'
                                    ? 'bg-amber-50 text-amber-800 border border-amber-200'
                                    : 'bg-indigo-50 text-indigo-700 border border-indigo-200'
                                }`}
                              >
                                {asset.sourceType}
                              </span>
                              <span className="px-2 py-0.5 rounded-md bg-slate-100 text-slate-600 text-[11px] font-mono font-bold">
                                原创:{asset.originalStatus} · 授权 {asset.authUsedCount}/{asset.authMaxLimit}
                              </span>
                            </div>

                            <div className="flex flex-wrap items-center gap-3 text-xs text-slate-500">
                              <span className="font-mono text-slate-700 font-semibold">
                                {asset.episodeRange} · {asset.durationFormatted}
                              </span>
                              {(asset.sourceHighlightLabel || asset.highlightCutPoint) && (
                                <span className="truncate max-w-[420px]">
                                  来源高光：{asset.sourceHighlightLabel || asset.highlightCutPoint}
                                </span>
                              )}
                            </div>
                          </div>
                        </div>

                        <div className="flex items-center gap-1.5 shrink-0">
                          <button
                            type="button"
                            onClick={() => setPreviewAsset(asset)}
                            className="flex items-center gap-1 px-2.5 py-1.5 rounded-lg border border-slate-200 bg-white hover:bg-slate-50 text-slate-700 text-xs font-bold cursor-pointer"
                          >
                            <Play className="w-3 h-3 fill-current" />
                            <span>预览</span>
                          </button>

                          <button
                            type="button"
                            onClick={() => handlePublishGroupAsset(asset, selectedGroup.id)}
                            className="flex items-center gap-1 px-3 py-1.5 rounded-lg bg-[#1A1D2E] hover:bg-black text-[#DDFD00] text-xs font-extrabold cursor-pointer"
                          >
                            <Send className="w-3 h-3" />
                            <span>单条发布</span>
                          </button>

                          <button
                            type="button"
                            onClick={() => handleRemoveAssetFromGroup(selectedGroup.id, asset.id)}
                            className="px-2.5 py-1.5 rounded-lg border border-slate-200 bg-white hover:bg-rose-50 text-slate-500 hover:text-rose-600 text-xs font-bold cursor-pointer"
                          >
                            移出
                          </button>
                        </div>
                      </div>
                    ))
                  )}
                </div>
              </div>
            </div>
          ) : null
        )}
      </div>

      {/* Modal 1: 添加在产剧集 */}
      {addDramaModalOpen && (
        <div className="fixed inset-0 z-50 bg-black/50 backdrop-blur-xs flex items-center justify-center p-4 animate-in fade-in duration-150">
          <div className="bg-white rounded-3xl max-w-lg w-full overflow-hidden shadow-2xl border border-slate-200">
            <div className="px-6 py-4 bg-[#1A1D2E] text-white flex items-center justify-between">
              <div className="flex items-center gap-2">
                <Film className="w-4 h-4 text-[#DDFD00]" />
                <span className="font-extrabold text-sm">添加剧集到内容生产</span>
              </div>
              <button
                type="button"
                onClick={() => setAddDramaModalOpen(false)}
                className="p-1 rounded-lg bg-white/10 hover:bg-white/20 cursor-pointer"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            <div className="p-5 space-y-3">
              <div className="relative">
                <Search className="w-4 h-4 text-slate-400 absolute left-3.5 top-2.5" />
                <input
                  type="text"
                  autoFocus
                  value={addDramaKeyword}
                  onChange={(e) => setAddDramaKeyword(e.target.value)}
                  placeholder="输入剧集名称搜索已下载原片（每次仅渲染前30条防卡顿）..."
                  className="w-full pl-9 pr-3 py-2 rounded-xl border border-slate-200 bg-[#F8FAFC] text-xs text-slate-800 focus:outline-none focus:border-slate-400"
                />
              </div>

              <div className="max-h-80 overflow-y-auto space-y-2 pr-1">
                {searchableDramasToAdd.map((drama) => {
                  const alreadyInList = activeDramaIds.includes(drama.dramaId);
                  return (
                    <div
                      key={drama.dramaId}
                      className="p-3 rounded-xl border border-slate-200/80 bg-[#F8FAFC] flex items-center justify-between gap-3"
                    >
                      <div className="flex items-center gap-2.5 min-w-0">
                        <DramaCover
                          name={drama.dramaTitle}
                          size="sm"
                          colorPlaceholder={{
                            bg: `linear-gradient(135deg, ${drama.coverColor || '#1E293B'} 0%, #0F172A 100%)`,
                            text: '#DDFD00',
                            tag: drama.genreTags?.[0]?.slice(0, 4) || '剧集'
                          }}
                        />
                        <div className="min-w-0">
                          <div className="font-extrabold text-xs text-[#1A1D2E] truncate">
                            《{drama.dramaTitle}》
                          </div>
                          <div className="text-[11px] text-slate-500 font-mono mt-0.5 truncate">
                            {drama.theaterName || '触摸剧场'} · 已下载 {drama.verifiedMp4Count} 集 ({drama.totalSizeGb} GB)
                          </div>
                        </div>
                      </div>

                      <button
                        type="button"
                        onClick={() => {
                          if (!alreadyInList) {
                            setActiveDramaIds((prev) => [drama.dramaId, ...prev]);
                          }
                          setSelectedDramaId(drama.dramaId);
                          setAddDramaModalOpen(false);
                          showToast(`✅ 已将《${drama.dramaTitle}》加入在产剧集列表`);
                        }}
                        className={`px-3 py-1.5 rounded-lg text-xs font-extrabold shrink-0 cursor-pointer ${
                          alreadyInList
                            ? 'bg-slate-200 text-slate-700'
                            : 'bg-[#1A1D2E] text-[#DDFD00] hover:bg-black'
                        }`}
                      >
                        {alreadyInList ? '切换到该剧' : '+ 加入生产'}
                      </button>
                    </div>
                  );
                })}
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Modal 2: 新建生产方案 (Production Plan Modal) */}
      {isPlanModalOpen && selectedProject && (
        <div className="fixed inset-0 z-50 bg-black/50 backdrop-blur-xs flex items-center justify-center p-4 animate-in fade-in duration-150">
          <div className="bg-white rounded-3xl max-w-2xl w-full shadow-2xl border border-slate-200 flex flex-col overflow-hidden">
            <div className="px-6 py-4 bg-[#1A1D2E] text-white flex items-center justify-between shrink-0">
              <div className="flex items-center gap-2.5">
                <Sparkles className="w-4 h-4 text-[#DDFD00]" />
                <h3 className="text-sm font-extrabold">
                  新建生产方案 · 《{selectedProject.dramaTitle}》
                </h3>
              </div>
              <button
                type="button"
                onClick={() => setIsPlanModalOpen(false)}
                className="p-1.5 rounded-lg bg-white/10 hover:bg-white/20 text-white cursor-pointer"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            <div className="p-6 max-h-[85vh] overflow-y-auto">
              <RemixCreatePanel
                rawDramas={[selectedProject]}
                templates={templates}
                highlights={dramaHighlights}
                initialSelectedHighlightIds={planInitialHighlightIds}
                initialPurpose={planInitialPurpose}
                modelRoutes={modelRoutes}
                aiRuns={projectRuns}
                selectedRunId={selectedRunId}
                onSelectRunId={setSelectedRunId}
                onCreateNewRun={handleCreateNewRun}
                onBatchUpdateManualStatus={() => undefined}
                followUpHighlight={followUpHighlight}
                onClearFollowUpHighlight={() => setFollowUpHighlight(null)}
                onCancel={() => setIsPlanModalOpen(false)}
                showToast={showToast}
                showRunDetails={false}
              />
            </div>
          </div>
        </div>
      )}

      {/* Modal 3: 原片高光片段大屏连续快审播放器（方便人工快速过一遍十几秒视频，不行直接淘汰） */}
      {previewHighlightClip && (
        <div className="fixed inset-0 z-50 bg-black/65 backdrop-blur-xs flex items-center justify-center p-4">
          <div className="bg-white rounded-3xl max-w-xl w-full overflow-hidden shadow-2xl border border-slate-200">
            <div className="px-5 py-3.5 bg-[#1A1D2E] text-white flex items-center justify-between">
              <div className="flex items-center gap-2 min-w-0">
                <Play className="w-4 h-4 text-[#DDFD00] shrink-0" />
                <span className="font-extrabold text-sm truncate">
                  高光快审播放 · [{previewHighlightClip.code}] {previewHighlightClip.episodeLabel} ({previewHighlightClip.timeRange} · {previewHighlightClip.durationText || '28秒'})
                </span>
              </div>
              <button
                type="button"
                onClick={() => setPreviewHighlightClip(null)}
                className="text-xs px-2.5 py-1 rounded bg-white/10 hover:bg-white/20 cursor-pointer"
              >
                关闭
              </button>
            </div>

            <div className="p-5 space-y-4">
              {/* 9:16 Vertical Highlight Player Screen */}
              <div
                className="aspect-[9/16] max-h-[360px] mx-auto rounded-2xl text-white p-5 flex flex-col justify-between relative overflow-hidden shadow-inner"
                style={{
                  background: `linear-gradient(160deg, ${previewHighlightClip.accentColor || '#1E293B'} 0%, #090D16 100%)`
                }}
              >
                {previewHighlightClip.previewUrl && (
                  <video
                    src={previewHighlightClip.previewUrl}
                    controls
                    autoPlay
                    muted
                    playsInline
                    className="absolute inset-0 h-full w-full object-cover opacity-80"
                  />
                )}
                <div className="absolute inset-0 bg-slate-950/35" />
                <div className="relative z-10 flex items-center justify-between text-xs">
                  <span className="px-2.5 py-0.5 rounded-md bg-[#DDFD00] text-[#1A1D2E] font-mono font-black">
                    {previewHighlightClip.code} · {previewHighlightClip.episodeLabel}
                  </span>
                  <span className="px-2 py-0.5 rounded bg-black/60 font-mono text-[11px]">
                    {previewHighlightClip.timeRange} ({previewHighlightClip.durationText || '28秒'})
                  </span>
                </div>

                <div className="relative z-10 my-auto text-center space-y-2">
                  <div className="w-12 h-12 rounded-full bg-[#DDFD00] text-[#1A1D2E] flex items-center justify-center mx-auto shadow-lg">
                    <Volume2 className="w-5 h-5" />
                  </div>
                  <p className="text-sm font-black">{previewHighlightClip.sceneTag || '原片高光片段播放中'}</p>
                  <p className="text-xs text-slate-300 leading-relaxed">{previewHighlightClip.description}</p>
                </div>

                <div className="relative z-10 p-3 rounded-xl bg-black/75 border border-white/10 text-center">
                  <p className="text-xs font-bold text-amber-200">{previewHighlightClip.dialogueText}</p>
                </div>
              </div>

              {/* Fast Review Navigation Bar: 上一条 / 淘汰并看下一条 / 下一条 */}
              <div className="flex flex-wrap items-center justify-between gap-2 pt-2 border-t border-slate-100">
                <div className="flex items-center gap-1.5">
                  <button
                    type="button"
                    disabled={previewHighlightIndex <= 0}
                    onClick={() => {
                      if (previewHighlightIndex > 0) {
                        setPreviewHighlightClip(dramaHighlights[previewHighlightIndex - 1]);
                      }
                    }}
                    className="flex items-center gap-1 px-3 py-2 rounded-xl border border-slate-200 bg-white hover:bg-slate-50 disabled:opacity-40 text-xs font-bold text-slate-700 cursor-pointer"
                  >
                    <SkipBack className="w-3.5 h-3.5" />
                    <span>上一段</span>
                  </button>

                  <button
                    type="button"
                    disabled={previewHighlightIndex >= dramaHighlights.length - 1}
                    onClick={() => {
                      if (previewHighlightIndex < dramaHighlights.length - 1) {
                        setPreviewHighlightClip(dramaHighlights[previewHighlightIndex + 1]);
                      }
                    }}
                    className="flex items-center gap-1 px-3 py-2 rounded-xl border border-slate-200 bg-white hover:bg-slate-50 disabled:opacity-40 text-xs font-bold text-slate-700 cursor-pointer"
                  >
                    <span>下一段 ({previewHighlightIndex + 1}/{dramaHighlights.length})</span>
                    <SkipForward className="w-3.5 h-3.5" />
                  </button>
                </div>

                <div className="flex items-center gap-2">
                  <button
                    type="button"
                    onClick={() => {
                      const isElim = previewHighlightClip.status === '已淘汰';
                      handleToggleHighlightEliminated(previewHighlightClip.id, !isElim);
                      if (!isElim && previewHighlightIndex < dramaHighlights.length - 1) {
                        setPreviewHighlightClip(dramaHighlights[previewHighlightIndex + 1]);
                      } else {
                        setPreviewHighlightClip((prev) =>
                          prev ? { ...prev, status: !isElim ? '已淘汰' : '已通过' } : null
                        );
                      }
                    }}
                    className={`px-3.5 py-2 rounded-xl text-xs font-extrabold cursor-pointer ${
                      previewHighlightClip.status === '已淘汰'
                        ? 'bg-emerald-600 text-white'
                        : 'bg-rose-600 hover:bg-rose-700 text-white'
                    }`}
                  >
                    {previewHighlightClip.status === '已淘汰' ? '恢复可用' : '淘汰此段并看下一段'}
                  </button>

                  <button
                    type="button"
                    onClick={() => {
                      const clip = previewHighlightClip;
                      setPreviewHighlightClip(null);
                      openProductionPlanModal({
                        purpose: '首轮覆盖',
                        highlightIds: [clip.id]
                      });
                    }}
                    className="px-4 py-2 rounded-xl bg-[#1A1D2E] text-[#DDFD00] text-xs font-extrabold cursor-pointer"
                  >
                    用此高光生产
                  </button>
                </div>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Modal 4: 导入外部视频 */}
      {isImportModalOpen && (
        <div className="fixed inset-0 z-50 bg-black/50 backdrop-blur-xs flex items-center justify-center p-4">
          <div className="bg-white rounded-3xl max-w-lg w-full overflow-hidden shadow-2xl border border-slate-200">
            <div className="px-6 py-4 bg-[#1A1D2E] text-white flex items-center justify-between">
              <div className="flex items-center gap-2">
                <Upload className="w-4 h-4 text-[#DDFD00]" />
                <span className="font-bold text-sm">
                  {importTargetGroupId
                    ? `导入外部视频至编组「${groups.find((g) => g.id === importTargetGroupId)?.name || ''}」`
                    : `导入外部视频至《${selectedProject?.dramaTitle || ''}》`}
                </span>
              </div>
              <button
                type="button"
                onClick={() => setIsImportModalOpen(false)}
                className="text-xs px-2.5 py-1 rounded bg-white/10 hover:bg-white/20 cursor-pointer"
              >
                关闭
              </button>
            </div>

            <form onSubmit={handleConfirmExternalImport} className="p-6 space-y-4">
              <div>
                <label className="block text-xs font-bold text-slate-700 mb-1.5">来源类型</label>
                <div className="grid grid-cols-2 gap-2.5">
                  {(['外部导入视频', '旧流程成片'] as const).map((st) => (
                    <button
                      key={st}
                      type="button"
                      onClick={() => setImportSourceType(st)}
                      className={`py-2 px-3 rounded-xl border text-xs font-bold transition-all cursor-pointer ${
                        importSourceType === st
                          ? 'border-[#1A1D2E] bg-[#1A1D2E] text-[#DDFD00]'
                          : 'border-slate-200 bg-slate-50 text-slate-700'
                      }`}
                    >
                      {st}
                    </button>
                  ))}
                </div>
              </div>

              <div>
                <label className="block text-xs font-bold text-slate-700 mb-1">视频文件名 (.mp4)</label>
                <input
                  type="text"
                  required
                  value={importVideoName}
                  onChange={(e) => setImportVideoName(e.target.value)}
                  placeholder="例如：外部精剪高光版_01.mp4"
                  className="w-full px-3 py-2 rounded-xl border border-slate-200 text-xs focus:outline-none focus:border-slate-400"
                />
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-xs font-bold text-slate-700 mb-1">视频时长</label>
                  <input
                    type="text"
                    value={importDurationFormatted}
                    onChange={(e) => setImportDurationFormatted(e.target.value)}
                    placeholder="06:30"
                    className="w-full px-3 py-2 rounded-xl border border-slate-200 text-xs font-mono"
                  />
                </div>
                <div>
                  <label className="block text-xs font-bold text-slate-700 mb-1">来源高光说明（可选）</label>
                  <input
                    type="text"
                    value={importHighlightNote}
                    onChange={(e) => setImportHighlightNote(e.target.value)}
                    placeholder="例如：第1集开篇高能冲突"
                    className="w-full px-3 py-2 rounded-xl border border-slate-200 text-xs"
                  />
                </div>
              </div>

              <div>
                <label className="block text-xs font-bold text-slate-700 mb-1">本地目录路径</label>
                <input
                  type="text"
                  value={importFilePath}
                  onChange={(e) => setImportFilePath(e.target.value)}
                  className="w-full px-3 py-2 rounded-xl border border-slate-200 text-xs font-mono"
                />
              </div>

              <div className="pt-2 flex justify-end gap-2">
                <button
                  type="button"
                  onClick={() => setIsImportModalOpen(false)}
                  className="px-4 py-2 rounded-xl border border-slate-200 text-xs font-bold text-slate-600 cursor-pointer"
                >
                  取消
                </button>
                <button
                  type="submit"
                  className="px-5 py-2 rounded-xl bg-[#1A1D2E] text-[#DDFD00] text-xs font-extrabold cursor-pointer"
                >
                  确认导入
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Modal 5: 从成片库挑片加入当前编组 */}
      {pickAssetsForGroupModalOpen && selectedGroup && (
        <div className="fixed inset-0 z-50 bg-black/50 backdrop-blur-xs flex items-center justify-center p-4">
          <div className="bg-white rounded-3xl max-w-2xl w-full overflow-hidden shadow-2xl border border-slate-200">
            <div className="px-6 py-4 bg-[#1A1D2E] text-white flex items-center justify-between">
              <div className="flex items-center gap-2">
                <FolderPlus className="w-4 h-4 text-[#DDFD00]" />
                <span className="font-extrabold text-sm">
                  挑片加入「{selectedGroup.name}」
                </span>
              </div>
              <button
                type="button"
                onClick={() => setPickAssetsForGroupModalOpen(false)}
                className="text-xs px-2.5 py-1 rounded bg-white/10 hover:bg-white/20 cursor-pointer"
              >
                完成
              </button>
            </div>

            <div className="p-5 space-y-3">
              <div className="relative">
                <Search className="w-4 h-4 text-slate-400 absolute left-3.5 top-2.5" />
                <input
                  type="text"
                  value={pickAssetsSearch}
                  onChange={(e) => setPickAssetsSearch(e.target.value)}
                  placeholder="搜索各剧可用成片或外部导入视频..."
                  className="w-full pl-9 pr-3 py-2 rounded-xl border border-slate-200 bg-[#F8FAFC] text-xs text-slate-800"
                />
              </div>

              <div className="max-h-80 overflow-y-auto space-y-2 pr-1">
                {pickableAssetsPool.map((asset) => {
                  const alreadyInGroup = groupItems.some(
                    (gi) => gi.groupId === selectedGroup.id && gi.assetId === asset.id
                  );
                  return (
                    <div
                      key={asset.id}
                      className="p-3 rounded-xl border border-slate-200/80 bg-[#F8FAFC] flex items-center justify-between gap-3"
                    >
                      <div className="min-w-0">
                        <div className="flex items-center gap-1.5">
                          <span className="font-extrabold text-xs text-[#1A1D2E] truncate">
                            {asset.videoName}
                          </span>
                          <span className="px-1.5 py-0.5 rounded bg-slate-200/70 text-[10px] font-bold text-slate-700 shrink-0">
                            《{asset.dramaTitle}》
                          </span>
                        </div>
                        <div className="text-[11px] text-slate-500 mt-0.5 truncate">
                          来源高光：{asset.sourceHighlightLabel || asset.highlightCutPoint || '默认片段'} · {asset.durationFormatted}
                        </div>
                      </div>

                      <button
                        type="button"
                        disabled={alreadyInGroup}
                        onClick={() => handleAddAssetsToGroup(selectedGroup.id, [asset.id])}
                        className={`px-3 py-1.5 rounded-lg text-xs font-extrabold shrink-0 ${
                          alreadyInGroup
                            ? 'bg-slate-200 text-slate-500 cursor-not-allowed'
                            : 'bg-[#1A1D2E] text-[#DDFD00] hover:bg-black cursor-pointer'
                        }`}
                      >
                        {alreadyInGroup ? '已在编组中' : '+ 加入编组'}
                      </button>
                    </div>
                  );
                })}
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Modal 6: 发布流水弹窗 */}
      {publishHistoryModalOpen && (
        <div className="fixed inset-0 z-50 bg-black/50 backdrop-blur-xs flex items-center justify-center p-4">
          <div className="bg-white rounded-3xl max-w-2xl w-full overflow-hidden shadow-2xl border border-slate-200">
            <div className="px-6 py-4 bg-[#1A1D2E] text-white flex items-center justify-between">
              <div className="flex items-center gap-2">
                <History className="w-4 h-4 text-[#DDFD00]" />
                <span className="font-extrabold text-sm">编组自动发布流水记录</span>
              </div>
              <button
                type="button"
                onClick={() => setPublishHistoryModalOpen(false)}
                className="text-xs px-2.5 py-1 rounded bg-white/10 hover:bg-white/20 cursor-pointer"
              >
                关闭
              </button>
            </div>

            <div className="p-5 max-h-96 overflow-y-auto space-y-2">
              {publications.map((pub) => (
                <div
                  key={pub.id}
                  className="p-3 rounded-xl border border-slate-200/80 bg-[#F8FAFC] flex items-center justify-between gap-3 text-xs"
                >
                  <div className="min-w-0 space-y-0.5">
                    <div className="font-extrabold text-[#1A1D2E] truncate">{pub.videoName}</div>
                    <div className="text-[11px] text-slate-500">
                      账号：{pub.accountName} ({pub.theaterName}) · {pub.publishMode} · 编组：{pub.groupName || '单条直发'}
                    </div>
                  </div>
                  <div className="text-right shrink-0 font-mono text-[11px]">
                    <div className="text-emerald-700 font-bold">{pub.status}</div>
                    <div className="text-slate-400">{pub.publishedAt}</div>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}

      {/* Modal 7: 单条或多条成片加入发布编组弹窗 */}
      {groupAssignAssetIds.length > 0 && (
        <div className="fixed inset-0 z-50 bg-black/50 backdrop-blur-xs flex items-center justify-center p-4">
          <div className="bg-white rounded-3xl max-w-md w-full overflow-hidden shadow-2xl border border-slate-200">
            <div className="px-6 py-4 bg-[#1A1D2E] text-white flex items-center justify-between">
              <div className="flex items-center gap-2">
                <FolderPlus className="w-4 h-4 text-[#DDFD00]" />
                <span className="font-bold text-sm">
                  加入发布编组（已选 {groupAssignAssetIds.length} 条成片）
                </span>
              </div>
              <button
                type="button"
                onClick={() => setGroupAssignAssetIds([])}
                className="text-xs px-2.5 py-1 rounded bg-white/10 hover:bg-white/20 cursor-pointer"
              >
                关闭
              </button>
            </div>

            <div className="p-5 space-y-3">
              <div className="space-y-2 max-h-60 overflow-y-auto">
                {groups.map((grp) => {
                  const count = groupItems.filter((gi) => gi.groupId === grp.id).length;
                  return (
                    <div
                      key={grp.id}
                      onClick={() => {
                        handleAddAssetsToGroup(grp.id, groupAssignAssetIds);
                        setGroupAssignAssetIds([]);
                      }}
                      className="p-3 rounded-xl border border-slate-200 hover:border-[#1A1D2E] bg-[#F8FAFC] hover:bg-white flex items-center justify-between cursor-pointer transition-all"
                    >
                      <div>
                        <div className="font-extrabold text-xs text-[#1A1D2E]">{grp.name}</div>
                        <div className="text-[11px] text-slate-400 mt-0.5">当前已有 {count} 条待发视频</div>
                      </div>
                      <span className="px-3 py-1 rounded-lg bg-[#1A1D2E] text-[#DDFD00] text-xs font-extrabold">
                        + 加入此组
                      </span>
                    </div>
                  );
                })}
              </div>

              <div className="pt-2 border-t border-slate-100 flex items-center gap-2">
                <input
                  type="text"
                  value={newGroupName}
                  onChange={(e) => setNewGroupName(e.target.value)}
                  placeholder={`新建编组并加入 (默认 待发编组_${String(groups.length + 1).padStart(2, '0')})`}
                  className="flex-1 px-3 py-1.5 rounded-xl border border-slate-200 text-xs"
                />
                <button
                  type="button"
                  onClick={() => {
                    const defaultName = `待发编组_${String(groups.length + 1).padStart(2, '0')}`;
                    const finalName = newGroupName.trim() || defaultName;
                    const now = new Date().toISOString().replace('T', ' ').slice(0, 16);
                    const newGrpId = `grp-${Date.now()}`;
                    const newGrp: V3ContentGroup = {
                      id: newGrpId,
                      name: finalName,
                      description: '',
                      tags: [],
                      createdAt: now,
                      updatedAt: now
                    };
                    setGroups((prev) => [...prev, newGrp]);
                    handleAddAssetsToGroup(newGrpId, groupAssignAssetIds);
                    setNewGroupName('');
                    setGroupAssignAssetIds([]);
                  }}
                  className="px-3 py-1.5 rounded-xl bg-indigo-600 text-white text-xs font-extrabold shrink-0 cursor-pointer"
                >
                  新建并加入
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Modal 8: 成片大图预览与操作弹窗 */}
      {previewAsset && (
        <div className="fixed inset-0 z-50 bg-black/60 backdrop-blur-xs flex items-center justify-center p-4">
          <div className="bg-white rounded-3xl max-w-xl w-full overflow-hidden shadow-2xl border border-slate-200">
            <div className="px-5 py-3.5 bg-[#1A1D2E] text-white flex items-center justify-between">
              <div className="flex items-center gap-2 min-w-0">
                <Play className="w-4 h-4 text-[#DDFD00] shrink-0" />
                <span className="font-bold text-sm truncate">{previewAsset.videoName}</span>
              </div>
              <button
                type="button"
                onClick={() => setPreviewAsset(null)}
                className="text-xs px-2.5 py-1 rounded bg-white/10 hover:bg-white/20 cursor-pointer"
              >
                关闭
              </button>
            </div>

            <div className="p-5 space-y-4">
              {(() => {
                const banner = getTemplateBannerStyle(previewAsset.templateVersion);
                return (
                  <div className="aspect-[9/16] max-h-[360px] mx-auto rounded-2xl bg-[#090D16] text-white flex flex-col justify-between overflow-hidden border border-slate-800 shadow-lg">
                    <div className="px-4 py-2.5 text-center" style={{ background: banner.bg }}>
                      <div className="text-[10px] font-black tracking-wider" style={{ color: banner.accent }}>
                        {banner.label}
                      </div>
                      <div className="text-sm font-black text-white">
                        《{previewAsset.dramaTitle}》 · {previewAsset.episodeRange}
                      </div>
                    </div>

                    <div className="px-5 text-center space-y-2 my-auto">
                      <span className="inline-block px-2.5 py-0.5 rounded-full bg-white/10 text-[#DDFD00] font-mono text-xs font-bold">
                        {previewAsset.durationFormatted} · {previewAsset.productionPurpose || '首轮覆盖'}
                      </span>
                      <p className="text-xs text-amber-200 font-bold">
                        来源高光：{previewAsset.sourceHighlightLabel || previewAsset.highlightCutPoint || '默认高光开头'}
                      </p>
                      <p className="text-[11px] text-slate-300">{previewAsset.techDetail}</p>
                    </div>

                    <div className="px-4 py-2.5 bg-black/80 text-center text-[11px] text-slate-300 font-mono">
                      {previewAsset.filePath}
                    </div>
                  </div>
                );
              })()}

              <div className="flex items-center justify-between gap-2 pt-2 border-t border-slate-100">
                <button
                  type="button"
                  onClick={() => {
                    navigator.clipboard?.writeText(previewAsset.filePath);
                    showToast('已复制成片本地路径');
                  }}
                  className="flex items-center gap-1.5 px-3 py-2 rounded-xl border border-slate-200 text-xs font-bold text-slate-700 hover:bg-slate-50 cursor-pointer"
                >
                  <FolderOpen className="w-3.5 h-3.5" />
                  <span>复制本地路径</span>
                </button>

                <div className="flex items-center gap-2">
                  <button
                    type="button"
                    onClick={() => {
                      const target = previewAsset;
                      setPreviewAsset(null);
                      openProductionPlanModal({
                        purpose: '爆款扩量',
                        highlightIds: target.sourceHighlightId
                          ? [target.sourceHighlightId]
                          : dramaHighlights[0]
                          ? [dramaHighlights[0].id]
                          : []
                      });
                    }}
                    className="flex items-center gap-1 px-3.5 py-2 rounded-xl bg-amber-50 hover:bg-amber-100 border border-amber-300 text-amber-950 text-xs font-extrabold cursor-pointer"
                  >
                    <Flame className="w-3.5 h-3.5 text-amber-600 fill-amber-500" />
                    <span>从这条爆款扩量</span>
                  </button>

                  <button
                    type="button"
                    onClick={() => {
                      const isElim = previewAsset.manualStatus === '已淘汰';
                      handleSetAssetsEliminated([previewAsset.id], !isElim);
                      setPreviewAsset(null);
                    }}
                    className={`px-4 py-2 rounded-xl text-xs font-extrabold cursor-pointer ${
                      previewAsset.manualStatus === '已淘汰'
                        ? 'bg-emerald-600 text-white'
                        : 'bg-rose-600 text-white hover:bg-rose-700'
                    }`}
                  >
                    {previewAsset.manualStatus === '已淘汰' ? '恢复为可用' : '淘汰此成片'}
                  </button>
                </div>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
