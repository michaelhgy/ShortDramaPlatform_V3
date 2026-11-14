import React, { useEffect, useState } from 'react';
import {
  INITIAL_V3_TEMPLATES,
  RawDramaDirectoryInfo,
  V3ContentAiRun,
  PlayContinuityMode,
  StrategyCounts,
  ManualReviewStatus,
} from '../../api/contentProduction';
import { getContentRemixRun, getContentRemixRuns, getContentRemixSourceDramas, startContentRemixRun } from '../../api/contentRemix';
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
import { ContentAccountOption } from './contentTypes';
import { RemixCreatePanel } from './RemixCreatePanel';
import { RemixJobList } from './RemixJobList';
import { ContentLibraryPanel } from './ContentLibraryPanel';
import { ContentGroupsPanel } from './ContentGroupsPanel';
import {
  Sparkles,
  Cpu,
  Film,
  Layers,
  ShieldCheck
} from 'lucide-react';

export type ContentSubTab = 'project_overview' | 'remix_create' | 'remix_jobs' | 'content_library' | 'group_publish';

interface ContentProductionViewProps {
  showToast: (msg: string) => void;
}

export const ContentProductionView: React.FC<ContentProductionViewProps> = ({
  showToast
}) => {
  // 二级标签状态：项目总览 | 制作记录 | 成片预览 | 编组发布
  const [activeSubTab, setActiveSubTab] = useState<ContentSubTab>('project_overview');

  // 核心数据状态
  const [rawDramas, setRawDramas] = useState<RawDramaDirectoryInfo[]>([]);
  const [templates] = useState(INITIAL_V3_TEMPLATES);
  const [aiRuns, setAiRuns] = useState<V3ContentAiRun[]>([]);
  const [selectedRunId, setSelectedRunId] = useState<string>('');
  const [selectedDramaId, setSelectedDramaId] = useState<string>('');

  // 成片库与授权上限状态 (默认 9，可配置)
  const [assets, setAssets] = useState<V3ContentAsset[]>(INITIAL_V3_CONTENT_ASSETS);
  const [globalAuthLimit, setGlobalAuthLimit] = useState<number>(9);

  // 编组与发布记录状态
  const [groups, setGroups] = useState<V3ContentGroup[]>(INITIAL_V3_CONTENT_GROUPS);
  const [groupItems, setGroupItems] = useState<V3ContentGroupItem[]>(INITIAL_V3_GROUP_ITEMS);
  const [originalRecords, setOriginalRecords] = useState<V3ContentOriginalRecord[]>(
    INITIAL_V3_ORIGINAL_RECORDS
  );
  const [publications, setPublications] = useState<V3ContentPublication[]>(
    INITIAL_V3_PUBLICATIONS
  );
  const [accounts, setAccounts] = useState<ContentAccountOption[]>([]);
  const [modelRoutes, setModelRoutes] = useState<Record<'highlight' | 'continuous' | 'jump' | 'review', string>>({
    highlight: '',
    continuous: '',
    jump: '',
    review: ''
  });
  const [contentAssetRoot, setContentAssetRoot] = useState('Z:\\05短剧二创');
  const [catalogLoading, setCatalogLoading] = useState(true);

  useEffect(() => {
    let active = true;
    getV2Dramas()
      .then((dramaResponse) => {
        if (!active) return;
        getContentRemixSourceDramas()
          .then((sourceResponse) => {
            if (!active) return;
            setCatalogLoading(false);
            const sources = new Map(sourceResponse.items.map((item) => [item.drama_id, item]));
            setRawDramas(dramaResponse.items.map((drama) => {
              const source = sources.get(drama.id);
              const count = source?.mp4_count || 0;
              return {
                dramaId: drama.id,
                dramaTitle: drama.current_name,
                directoryPath: source?.directory || '',
                totalEpisodes: Number(drama.official_total_episodes || count || 0),
                verifiedMp4Count: count,
                missingEpisodes: [],
                corruptedFiles: [],
                totalSizeGb: source?.size_gb || 0,
                scanStatus: count > 0 ? 'ready' : 'unscanned',
                statusSummary: count > 0 ? `找到 ${count} 集原片` : '没有找到原片',
              };
            }));
            if (!sourceResponse.download_root_ok) {
              showToast(`原片根目录无法访问：${sourceResponse.download_root || '未设置'}。请检查网络盘是否连接，或到系统设置修改原片目录。`);
            }
          })
          .catch((error) => {
            if (!active) return;
            setCatalogLoading(false);
            showToast(`读取原片目录失败：${error instanceof Error ? error.message : '未知错误'}`);
          });

        Promise.allSettled([getV2Accounts(), getGptRelayConfig(), getV2Settings(), getContentRemixRuns()])
          .then(([accountsResult, relayResult, settingsResult, runsResult]) => {
            if (!active) return;
            if (accountsResult.status === 'fulfilled') {
              setAccounts(accountsResult.value.items.map((account) => ({
                id: account.id,
                name: account.nickname,
                theaterName: account.theater_name,
                tier: account.status,
              })));
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
              const configuredRoot = String(settingsResult.value.content_remix_output_root || '').replace(/[\\]+$/, '');
              if (configuredRoot) setContentAssetRoot(configuredRoot);
            }
            if (runsResult.status === 'fulfilled') {
              setAiRuns(runsResult.value.items || []);
              setSelectedRunId(runsResult.value.items?.[0]?.id || '');
            }
          });
      })
      .catch(() => {
        if (active) {
          setCatalogLoading(false);
          showToast('内容生产的剧集读取失败，请先检查V3服务。');
        }
      });
    return () => { active = false; };
  }, []);

  const availableProjectDramas = rawDramas
    .filter((drama) => drama.verifiedMp4Count > 0 && drama.directoryPath)
    .sort((a, b) => b.verifiedMp4Count - a.verifiedMp4Count || a.dramaTitle.localeCompare(b.dramaTitle, 'zh-CN'));

  useEffect(() => {
    if (selectedDramaId && availableProjectDramas.some((drama) => drama.dramaId === selectedDramaId)) return;
    if (availableProjectDramas[0]) setSelectedDramaId(availableProjectDramas[0].dramaId);
  }, [rawDramas, selectedDramaId]);

  const selectedProject = availableProjectDramas.find((drama) => drama.dramaId === selectedDramaId) || availableProjectDramas[0];
  const projectRuns = selectedProject
    ? aiRuns.filter((run) => run.dramaId === selectedProject.dramaId || run.dramaTitle === selectedProject.dramaTitle)
    : [];
  const projectAssets = selectedProject
    ? assets.filter((asset) => asset.dramaId === selectedProject.dramaId || asset.dramaTitle === selectedProject.dramaTitle)
    : [];
  const latestProjectRun = projectRuns[0];
  const transcriptStep = latestProjectRun?.pipelineSteps.find((step) => step.key === 'local_recognize');
  const storyMapStep = latestProjectRun?.pipelineSteps.find((step) => step.key === 'highlight_judge');

  useEffect(() => {
    if (!selectedProject) return;
    setSelectedRunId((current) => projectRuns.some((run) => run.id === current) ? current : (projectRuns[0]?.id || ''));
  }, [selectedProject?.dramaId, projectRuns.length]);

  // 真实后台任务：扫描原片、本地识别、模型规划、FFmpeg 合成并入库。
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
  }) => {
    const drama = rawDramas.find((item) => item.dramaId === params.dramaId) || rawDramas[0];
    const tpl = templates.find((item) => item.id === params.templateId) || templates[0];
    if (!drama || !drama.directoryPath) {
      showToast('当前剧集没有可用原片目录。');
      return;
    }
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
      });
      setAiRuns((prev) => [run, ...prev.filter((item) => item.id !== run.id)]);
      setSelectedRunId(run.id);
      showToast(`已启动真实二创任务 ${run.jobCode}`);
    } catch (error) {
      showToast(error instanceof Error ? error.message : '真实二创任务启动失败');
    }
  };

  useEffect(() => {
    if (!selectedRunId) return;
    const timer = window.setInterval(() => {
      getContentRemixRun(selectedRunId)
        .then((run) => setAiRuns((prev) => prev.map((item) => item.id === run.id ? run : item)))
        .catch(() => undefined);
    }, 2500);
    return () => window.clearInterval(timer);
  }, [selectedRunId]);

  useEffect(() => {
    const generatedAssets: V3ContentAsset[] = aiRuns.flatMap((run) => run.results
      .filter((result) => result.techStatus === '合格')
      .map((result) => ({
        id: `asset-${result.id}`,
        videoName: result.videoName,
        sourceType: '原剧二创' as const,
        dramaId: result.dramaId,
        dramaTitle: result.dramaTitle,
        generationRecord: `${run.jobCode} · ${run.modelId} · ${result.playStrategy}`,
        generationJobId: run.id,
        templateVersion: result.templateVersion,
        durationSec: result.durationSec,
        durationFormatted: result.durationFormatted,
        filePath: result.filePath,
        episodeRange: result.episodeRange,
        highlightCutPoint: result.highlightCutPoint,
        jumpCutPositions: result.jumpCutPositions,
        techStatus: result.techStatus,
        techDetail: result.techReport,
        manualStatus: result.manualStatus,
        originalStatus: '未声明原创' as const,
        authUsedCount: 0,
        authMaxLimit: globalAuthLimit,
        usedAccounts: [],
        createdAt: result.createdAt,
        previewHue: result.previewHue,
      })));
    if (!generatedAssets.length) return;
    setAssets((current) => {
      const generatedIds = new Set(generatedAssets.map((asset) => asset.id));
      return [...generatedAssets, ...current.filter((asset) => !generatedIds.has(asset.id))];
    });
  }, [aiRuns, globalAuthLimit]);

  // 3. 批量审核/淘汰结果
  const handleBatchUpdateManualStatus = (
    runId: string,
    resultIds: string[],
    status: ManualReviewStatus
  ) => {
    setAiRuns((prev) =>
      prev.map((run) => {
        if (run.id !== runId) return run;
        return {
          ...run,
          results: run.results.map((r) =>
            resultIds.includes(r.id) ? { ...r, manualStatus: status } : r
          )
        };
      })
    );

    // 同步更新已入库成片的人工状态
    const targetRun = aiRuns.find((r) => r.id === runId);
    if (targetRun) {
      const linkedAssetIds = targetRun.results
        .filter((r) => resultIds.includes(r.id) && r.ingestedAssetId)
        .map((r) => r.ingestedAssetId as string);

      if (linkedAssetIds.length > 0) {
        setAssets((prev) =>
          prev.map((a) =>
            linkedAssetIds.includes(a.id) ? { ...a, manualStatus: status } : a
          )
        );
      }
    }

    showToast(`✅ 已批量更新 ${resultIds.length} 条结果的人工审核状态为「${status}」`);
  };

  // 4. 成片库人工状态修改
  const handleUpdateAssetManualStatus = (assetId: string, status: ManualReviewStatus) => {
    setAssets((prev) =>
      prev.map((a) => (a.id === assetId ? { ...a, manualStatus: status } : a))
    );
    showToast(`已将成片状态更新为「${status}」`);
  };

  // 5. 导入外部视频或归档旧流程成片
  const handleImportExternalAsset = (newAssetData: Omit<V3ContentAsset, 'id' | 'createdAt'>) => {
    const newAsset: V3ContentAsset = {
      ...newAssetData,
      id: `asset-ext-${Date.now()}`,
      createdAt: new Date().toISOString().replace('T', ' ').slice(0, 16)
    };
    setAssets((prev) => [newAsset, ...prev]);
    showToast(`✅ 已成功导入「${newAsset.sourceType}」：《${newAsset.videoName}》`);
  };

  // 6. 编组操作：新建、重命名、删除、添加/移除成片、调整顺序
  const handleCreateGroup = (name: string, description: string, tags: string[]) => {
    const now = new Date().toISOString().replace('T', ' ').slice(0, 16);
    const newGrp: V3ContentGroup = {
      id: `grp-${Date.now()}`,
      name,
      description,
      tags,
      createdAt: now,
      updatedAt: now
    };
    setGroups((prev) => [...prev, newGrp]);
    showToast(`✅ 已新建发布编组「${name}」`);
  };

  const handleRenameGroup = (groupId: string, newName: string, newDesc: string) => {
    setGroups((prev) =>
      prev.map((g) =>
        g.id === groupId
          ? { ...g, name: newName, description: newDesc, updatedAt: '刚刚' }
          : g
      )
    );
    showToast(`✅ 已更新编组信息：「${newName}」`);
  };

  const handleDeleteGroup = (groupId: string) => {
    const target = groups.find((g) => g.id === groupId);
    setGroups((prev) => prev.filter((g) => g.id !== groupId));
    setGroupItems((prev) => prev.filter((gi) => gi.groupId !== groupId));
    if (target) {
      showToast(`🗑️ 已删除编组「${target.name}」（未影响成片库原文件）`);
    }
  };

  const handleAddAssetToGroup = (groupId: string, assetId: string) => {
    const exists = groupItems.some((gi) => gi.groupId === groupId && gi.assetId === assetId);
    if (exists) return;
    const currentGroupItems = groupItems.filter((gi) => gi.groupId === groupId);
    const maxOrder = currentGroupItems.reduce((m, i) => Math.max(m, i.sortOrder), 0);
    const newItem: V3ContentGroupItem = {
      id: `gi-${Date.now()}`,
      groupId,
      assetId,
      sortOrder: maxOrder + 1,
      addedAt: '刚刚'
    };
    setGroupItems((prev) => [...prev, newItem]);
    showToast('✅ 已将成片加入编组');
  };

  const handleRemoveAssetFromGroup = (groupId: string, assetId: string) => {
    setGroupItems((prev) =>
      prev.filter((gi) => !(gi.groupId === groupId && gi.assetId === assetId))
    );
    showToast('已从当前编组移除该成片');
  };

  const handleToggleAssetInGroup = (assetId: string, groupId: string) => {
    const exists = groupItems.some((gi) => gi.groupId === groupId && gi.assetId === assetId);
    if (exists) {
      handleRemoveAssetFromGroup(groupId, assetId);
    } else {
      handleAddAssetToGroup(groupId, assetId);
    }
  };

  const handleMoveGroupItemOrder = (
    groupId: string,
    assetId: string,
    direction: 'up' | 'down'
  ) => {
    const items = groupItems
      .filter((gi) => gi.groupId === groupId)
      .sort((a, b) => a.sortOrder - b.sortOrder);

    const idx = items.findIndex((i) => i.assetId === assetId);
    if (idx === -1) return;
    const swapIdx = direction === 'up' ? idx - 1 : idx + 1;
    if (swapIdx < 0 || swapIdx >= items.length) return;

    const currentItem = items[idx];
    const targetItem = items[swapIdx];

    setGroupItems((prev) =>
      prev.map((gi) => {
        if (gi.id === currentItem.id) return { ...gi, sortOrder: targetItem.sortOrder };
        if (gi.id === targetItem.id) return { ...gi, sortOrder: currentItem.sortOrder };
        return gi;
      })
    );
  };

  // 7. 原创发布逻辑（失败不算原创成功，不记有效消耗）
  const handleExecuteOriginalPublish = (params: {
    groupId: string;
    assetId: string;
    accountId: string;
    actualPublishCount: number;
    simulateResult: 'success' | 'fail';
  }) => {
    const asset = assets.find((a) => a.id === params.assetId);
    const acc = accounts.find((a) => a.id === params.accountId);
    const grp = groups.find((g) => g.id === params.groupId);
    if (!asset || !acc) return;

    const now = new Date().toISOString().replace('T', ' ').slice(0, 19);
    const isSuccess = params.simulateResult === 'success';

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
      actualPublishCount: params.actualPublishCount,
      status: isSuccess ? '原创声明成功' : '原创声明失败',
      consumedOriginalCount: isSuccess ? params.actualPublishCount : 0,
      failureReason: isSuccess
        ? undefined
        : '平台校验未通过：原创声明被驳回（根据规则：失败不算原创成功，消耗次数记为 0）',
      recordedAt: now
    };

    setOriginalRecords((prev) => [newOrigRec, ...prev]);

    if (isSuccess) {
      setAssets((prev) =>
        prev.map((a) => {
          if (a.id !== asset.id) return a;
          return {
            ...a,
            originalStatus: '已声明原创',
            originalDeclaredAccountId: acc.id,
            originalDeclaredAccountName: acc.name,
            originalDeclaredAt: now.slice(0, 16),
            usedAccounts: [
              ...a.usedAccounts,
              {
                accountId: acc.id,
                accountName: acc.name,
                publishCount: params.actualPublishCount,
                mode: '原创发布',
                lastPublishedAt: now.slice(0, 16)
              }
            ]
          };
        })
      );

      setPublications((prev) => [
        {
          id: `pub-rec-${Date.now()}`,
          assetId: asset.id,
          videoName: asset.videoName,
          dramaTitle: asset.dramaTitle,
          sourceType: asset.sourceType,
          groupId: grp?.id,
          groupName: grp?.name,
          publishMode: '原创发布',
          accountId: acc.id,
          accountName: acc.name,
          theaterName: acc.theaterName,
          actualPublishCount: params.actualPublishCount,
          status: '发布成功',
          authQuotaDeducted: 0,
          xiaovmaoFlowCode: `XVM-ORIG-${Date.now().toString().slice(-6)}`,
          publishedAt: now
        },
        ...prev
      ]);
      showToast(
        `✅ 原创发布成功！账号「${acc.name}」实发 ${params.actualPublishCount} 次已记录`
      );
    } else {
      setAssets((prev) =>
        prev.map((a) => {
          if (a.id !== asset.id) return a;
          // 如果之前已经成功声明过原创，保留原状态；否则标为声明失败
          return {
            ...a,
            originalStatus:
              a.originalStatus === '已声明原创' ? '已声明原创' : '声明失败'
          };
        })
      );
      showToast('⚠️ 原创声明失败！已记录失败原因，本次不算原创成功且不计消耗次数');
    }
  };

  // 8. 授权发布逻辑（调用小V猫，仅成功发布后才扣次数）
  const handleExecuteAuthorizedPublish = (params: {
    groupId: string;
    assetId: string;
    accountId: string;
    actualPublishCount: number;
    simulateResult: 'success' | 'fail';
  }) => {
    const asset = assets.find((a) => a.id === params.assetId);
    const acc = accounts.find((a) => a.id === params.accountId);
    const grp = groups.find((g) => g.id === params.groupId);
    if (!asset || !acc) return;

    const now = new Date().toISOString().replace('T', ' ').slice(0, 19);
    const isSuccess = params.simulateResult === 'success';
    const deducted = isSuccess ? params.actualPublishCount : 0;

    const newPub: V3ContentPublication = {
      id: `pub-rec-${Date.now()}`,
      assetId: asset.id,
      videoName: asset.videoName,
      dramaTitle: asset.dramaTitle,
      sourceType: asset.sourceType,
      groupId: grp?.id,
      groupName: grp?.name,
      publishMode: '授权发布',
      accountId: acc.id,
      accountName: acc.name,
      theaterName: acc.theaterName,
      actualPublishCount: params.actualPublishCount,
      status: isSuccess ? '发布成功' : '发布失败',
      authQuotaDeducted: deducted,
      xiaovmaoFlowCode: `XVM-AUTH-${Date.now().toString().slice(-6)}`,
      failureReason: isSuccess
        ? undefined
        : '小V猫回传：账号授权链路超时，本次发布未生效（未扣减授权次数）',
      publishedAt: now
    };

    setPublications((prev) => [newPub, ...prev]);

    if (isSuccess) {
      setAssets((prev) =>
        prev.map((a) => {
          if (a.id !== asset.id) return a;
          return {
            ...a,
            authUsedCount: a.authUsedCount + deducted,
            usedAccounts: [
              ...a.usedAccounts,
              {
                accountId: acc.id,
                accountName: acc.name,
                publishCount: params.actualPublishCount,
                mode: '授权发布',
                lastPublishedAt: now.slice(0, 16)
              }
            ]
          };
        })
      );
      showToast(
        `✅ 小V猫授权发布成功！已扣减 ${deducted} 次授权额度，记录账号「${acc.name}」实发 ${params.actualPublishCount} 次`
      );
    } else {
      showToast('⚠️ 小V猫授权发布失败！已记录异常流水，本次未扣减授权次数');
    }
  };

  const renderWorkspace = () => (
    <main className="min-h-[calc(100vh-72px)] bg-[#EEF2F6] px-4 py-5 sm:px-6">
      <div className="mx-auto grid max-w-[1780px] grid-cols-1 gap-4 lg:grid-cols-[240px_minmax(0,1fr)]">
        <aside className="overflow-hidden rounded-xl bg-[#111827] text-white shadow-sm">
          <div className="border-b border-white/10 px-4 py-4"><div className="text-[10px] uppercase tracking-[0.2em] text-slate-400">Content Studio</div><h1 className="mt-1 text-xl font-extrabold">剧集项目</h1><p className="mt-2 text-[11px] leading-relaxed text-slate-300">从分析资料到成片发布，当前工作只围绕一部剧。</p></div>
          <div className="p-2">{availableProjectDramas.map((drama) => { const active=drama.dramaId===selectedProject?.dramaId; const count=assets.filter((asset)=>asset.dramaId===drama.dramaId||asset.dramaTitle===drama.dramaTitle).length; return <button key={drama.dramaId} type="button" onClick={()=>{setSelectedDramaId(drama.dramaId);setActiveSubTab('project_overview');}} className={`w-full border-l-2 px-3 py-3 text-left transition-colors ${active?'border-[#DDFD00] bg-white/10':'border-transparent hover:bg-white/5'}`}><div className="truncate text-sm font-bold">《{drama.dramaTitle}》</div><div className="mt-1 text-[11px] text-slate-400">{drama.verifiedMp4Count}/{drama.totalEpisodes} 集 <span className="mx-1 text-slate-600">·</span> {count} 条成片</div></button>;})}</div>
        </aside>

        {selectedProject ? <section className="min-w-0 overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm">
          <header className="border-b border-slate-200 bg-white px-5 py-4 sm:px-6"><div className="flex flex-wrap items-end justify-between gap-4"><div><div className="text-[11px] font-bold text-slate-500">当前剧集</div><h2 className="mt-1 text-2xl font-extrabold tracking-tight text-slate-950">《{selectedProject.dramaTitle}》</h2><div className="mt-2 flex flex-wrap gap-2 text-[11px] text-slate-500"><span>{selectedProject.verifiedMp4Count}/{selectedProject.totalEpisodes} 集原片</span><span>转写 {transcriptStep?.status==='completed'?'已完成':'未完成'}</span><span>剧情地图 {storyMapStep?.status==='completed'?'已完成':'未完成'}</span></div></div><button type="button" onClick={()=>setActiveSubTab('remix_create')} className="rounded-lg bg-[#111827] px-4 py-2 text-xs font-extrabold text-[#DDFD00] hover:bg-black">新建制作</button></div><nav className="mt-4 flex flex-wrap gap-1 border-t border-slate-100 pt-3" aria-label="剧集工作区">{([['project_overview','总览'],['remix_create','新建制作'],['remix_jobs','制作记录'],['content_library','成片审核'],['group_publish','发布编组']] as [ContentSubTab,string][]).map(([key,label])=><button key={key} type="button" onClick={()=>setActiveSubTab(key)} className={`rounded-md px-3 py-2 text-xs font-bold ${activeSubTab===key?'bg-[#111827] text-white':'text-slate-600 hover:bg-slate-100'}`}>{label}{key==='remix_jobs'?` · ${projectRuns.length}`:key==='content_library'?` · ${projectAssets.length}`:''}</button>)}</nav></header>

          {activeSubTab==='project_overview' && <div className="space-y-5 p-5 sm:p-6"><section className="grid grid-cols-1 gap-3 md:grid-cols-[1.15fr_0.85fr]"><div className="border-l-4 border-[#DDFD00] bg-[#111827] px-5 py-4 text-white"><div className="text-[11px] text-slate-300">下一步</div><div className="mt-1 text-lg font-extrabold">{projectAssets.some((asset)=>asset.manualStatus==='待审核')?'先审核当前成片，再决定是否追加制作':'先完成本剧的首次制作'}</div><div className="mt-2 text-xs text-slate-300">{projectAssets.some((asset)=>asset.manualStatus==='待审核')?`当前有 ${projectAssets.filter((asset)=>asset.manualStatus==='待审核').length} 条成片等待人工审核。`: '资料准备完成后，可以直接新建一次制作记录。'}</div><button type="button" onClick={()=>setActiveSubTab(projectAssets.some((asset)=>asset.manualStatus==='待审核')?'content_library':'remix_create')} className="mt-4 rounded-md bg-[#DDFD00] px-3 py-2 text-xs font-extrabold text-[#111827]">{projectAssets.some((asset)=>asset.manualStatus==='待审核')?'进入成片审核':'开始新建制作'}</button></div><div className="grid grid-cols-3 divide-x divide-slate-200 border border-slate-200 bg-slate-50"><div className="px-3 py-4"><div className="text-[11px] text-slate-500">制作记录</div><div className="mt-2 text-2xl font-extrabold tabular-nums text-slate-950">{projectRuns.length}</div></div><div className="px-3 py-4"><div className="text-[11px] text-slate-500">待审核</div><div className="mt-2 text-2xl font-extrabold tabular-nums text-amber-700">{projectAssets.filter((asset)=>asset.manualStatus==='待审核').length}</div></div><div className="px-3 py-4"><div className="text-[11px] text-slate-500">已通过</div><div className="mt-2 text-2xl font-extrabold tabular-nums text-emerald-700">{projectAssets.filter((asset)=>asset.manualStatus==='已通过').length}</div></div></div></section><div className="grid grid-cols-1 gap-5 xl:grid-cols-[0.9fr_1.1fr]"><section className="border border-slate-200"><div className="border-b border-slate-200 px-4 py-3"><h3 className="text-sm font-extrabold text-slate-950">分析资料</h3><p className="mt-1 text-xs text-slate-500">制作记录会复用这里的资料。</p></div><div className="divide-y divide-slate-200"><div className="flex items-start justify-between gap-4 px-4 py-4"><div><div className="text-xs font-bold text-slate-700">转写资料</div><div className="mt-1 text-[11px] text-slate-500">{transcriptStep?.detailText||'尚未生成'}</div></div><span className="text-xs font-bold text-emerald-700">{transcriptStep?.status==='completed'?'已完成':'未完成'}</span></div><div className="flex items-start justify-between gap-4 px-4 py-4"><div><div className="text-xs font-bold text-slate-700">剧情地图</div><div className="mt-1 text-[11px] text-slate-500">{storyMapStep?.detailText||'尚未生成'}</div></div><span className="text-xs font-bold text-indigo-700">{storyMapStep?.status==='completed'?'已完成':'未完成'}</span></div></div></section><section className="border border-slate-200"><div className="flex items-center justify-between border-b border-slate-200 px-4 py-3"><div><h3 className="text-sm font-extrabold text-slate-950">最近制作记录</h3><p className="mt-1 text-xs text-slate-500">只显示当前剧的历史记录。</p></div><button type="button" onClick={()=>setActiveSubTab('remix_jobs')} className="text-xs font-bold text-indigo-700 hover:underline">查看全部</button></div><div className="divide-y divide-slate-200">{projectRuns.slice(0,5).map((run,index)=><button key={run.id} type="button" onClick={()=>{setSelectedRunId(run.id);setActiveSubTab('remix_jobs');}} className="flex w-full items-center justify-between gap-3 px-4 py-3 text-left hover:bg-slate-50"><div className="min-w-0"><div className="truncate text-xs font-bold text-slate-900">R{projectRuns.length-index} · {run.jobCode}</div><div className="mt-1 text-[11px] text-slate-500">目标 {run.targetCount} 条 · 合格 {run.results.filter((result)=>result.techStatus==='合格').length} 条</div></div><span className={`shrink-0 text-[11px] font-bold ${run.status==='completed'?'text-emerald-700':run.status==='running'?'text-indigo-700':'text-rose-700'}`}>{run.status==='completed'?'已完成':run.status}</span></button>)}</div></section></div></div>}

          {activeSubTab === 'remix_create' && <RemixCreatePanel rawDramas={[selectedProject]} templates={templates} modelRoutes={modelRoutes} aiRuns={projectRuns} selectedRunId={selectedRunId} onSelectRunId={setSelectedRunId} onCreateNewRun={handleCreateNewRun} onBatchUpdateManualStatus={handleBatchUpdateManualStatus} showToast={showToast} showRunDetails={false} />}
          {activeSubTab === 'remix_jobs' && <RemixJobList aiRuns={projectRuns} selectedRunId={selectedRunId} onSelectRunId={setSelectedRunId} showToast={showToast} />}
          {activeSubTab === 'content_library' && <ContentLibraryPanel contentAssetRoot={contentAssetRoot} assets={projectAssets} groups={groups} groupItems={groupItems} globalAuthLimit={globalAuthLimit} onUpdateGlobalAuthLimit={(limit) => { setGlobalAuthLimit(limit); showToast(`已更新单条成片授权次数上限为 ${limit} 次`); }} onUpdateAssetManualStatus={handleUpdateAssetManualStatus} onImportExternalAsset={handleImportExternalAsset} onToggleAssetInGroup={handleToggleAssetInGroup} showToast={showToast} />}
          {activeSubTab === 'group_publish' && <ContentGroupsPanel assets={assets} groups={groups} groupItems={groupItems} originalRecords={originalRecords} publications={publications} accounts={accounts} globalAuthLimit={globalAuthLimit} onCreateGroup={handleCreateGroup} onRenameGroup={handleRenameGroup} onDeleteGroup={handleDeleteGroup} onAddAssetToGroup={handleAddAssetToGroup} onRemoveAssetFromGroup={handleRemoveAssetFromGroup} onMoveGroupItemOrder={handleMoveGroupItemOrder} onExecuteOriginalPublish={handleExecuteOriginalPublish} onExecuteAuthorizedPublish={handleExecuteAuthorizedPublish} showToast={showToast} />}
        </section> : <div className="rounded-2xl border border-dashed border-slate-300 bg-white p-10 text-center text-sm text-slate-500">正在读取可制作的剧集…</div>}
      </div>
    </main>
  );

  return renderWorkspace();
};
