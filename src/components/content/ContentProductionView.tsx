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

export type ContentSubTab = 'remix_create' | 'remix_jobs' | 'content_library' | 'group_publish';

interface ContentProductionViewProps {
  showToast: (msg: string) => void;
}

export const ContentProductionView: React.FC<ContentProductionViewProps> = ({
  showToast
}) => {
  // 二级标签状态：二创制作 | 生成任务 | 成片库 | 编组发布
  const [activeSubTab, setActiveSubTab] = useState<ContentSubTab>('remix_create');

  // 核心数据状态
  const [rawDramas, setRawDramas] = useState<RawDramaDirectoryInfo[]>([]);
  const [templates] = useState(INITIAL_V3_TEMPLATES);
  const [aiRuns, setAiRuns] = useState<V3ContentAiRun[]>([]);
  const [selectedRunId, setSelectedRunId] = useState<string>('');

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
  const [contentAssetRoot, setContentAssetRoot] = useState('内容资产\\成片库');
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
              const configuredRoot = String(settingsResult.value.data_root_dir || '').replace(/[\\]+$/, '');
              if (configuredRoot) setContentAssetRoot(`${configuredRoot}\\内容资产\\成片库`);
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

  return (
    <main className="max-w-[1720px] mx-auto w-full px-4 sm:px-6 lg:px-8 py-6 space-y-6 animate-in fade-in duration-200">
      {/* 顶部工作区标题与二级导航栏 */}
      <div className="bg-white rounded-2xl border border-slate-200/90 p-4 sm:p-5 shadow-xs flex flex-wrap items-center justify-between gap-4">
        <div className="flex items-center gap-3.5">
          <div className="w-10 h-10 rounded-2xl bg-[#1A1D2E] text-[#DDFD00] flex items-center justify-center shadow-sm">
            <Sparkles className="w-5 h-5 fill-current" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h2 className="text-base sm:text-lg font-extrabold text-slate-900">
                内容生产工作区 (原剧二创 · 独立成片库 · 编组发布)
              </h2>
              <span className="px-2.5 py-0.5 rounded-md bg-emerald-50 text-emerald-700 border border-emerald-200 text-[11px] font-bold">
                与旧生产中心并行运行
              </span>
            </div>
            <p className="text-xs text-slate-500 mt-0.5">
              原片只读扫描 → 模型高光判断与连续/跳集规划 → 通版模板合成 → 技术质检入库 → 多对多编组与小V猫原创/授权分发
            </p>
          </div>
        </div>

        {/* 二级标签：二创制作 | 生成任务 | 成片库 | 编组发布 */}
        <div className="flex items-center p-1 bg-slate-100 rounded-xl border border-slate-200/70 gap-1">
          <button
            type="button"
            onClick={() => setActiveSubTab('remix_create')}
            className={`flex items-center gap-1.5 px-4 py-2 rounded-lg text-xs font-extrabold transition-all cursor-pointer ${
              activeSubTab === 'remix_create'
                ? 'bg-[#1A1D2E] text-[#DDFD00] shadow-xs'
                : 'text-slate-600 hover:text-slate-900'
            }`}
          >
            <Sparkles className="w-3.5 h-3.5" />
            <span>二创制作</span>
          </button>

          <button
            type="button"
            onClick={() => setActiveSubTab('remix_jobs')}
            className={`flex items-center gap-1.5 px-4 py-2 rounded-lg text-xs font-extrabold transition-all cursor-pointer ${
              activeSubTab === 'remix_jobs'
                ? 'bg-[#1A1D2E] text-[#DDFD00] shadow-xs'
                : 'text-slate-600 hover:text-slate-900'
            }`}
          >
            <Cpu className="w-3.5 h-3.5" />
            <span>生成任务 ({aiRuns.length})</span>
          </button>

          <button
            type="button"
            onClick={() => setActiveSubTab('content_library')}
            className={`flex items-center gap-1.5 px-4 py-2 rounded-lg text-xs font-extrabold transition-all cursor-pointer ${
              activeSubTab === 'content_library'
                ? 'bg-[#1A1D2E] text-[#DDFD00] shadow-xs'
                : 'text-slate-600 hover:text-slate-900'
            }`}
          >
            <Film className="w-3.5 h-3.5" />
            <span>成片库 ({assets.length})</span>
          </button>

          <button
            type="button"
            onClick={() => setActiveSubTab('group_publish')}
            className={`flex items-center gap-1.5 px-4 py-2 rounded-lg text-xs font-extrabold transition-all cursor-pointer ${
              activeSubTab === 'group_publish'
                ? 'bg-[#1A1D2E] text-[#DDFD00] shadow-xs'
                : 'text-slate-600 hover:text-slate-900'
            }`}
          >
            <Layers className="w-3.5 h-3.5" />
            <span>编组发布 ({groups.length})</span>
          </button>
        </div>
      </div>

      <div className="rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-xs text-amber-900">
        {catalogLoading
          ? '正在查找已下载的原片（网络盘较慢时可能要等一会儿）……'
          : `成片库正式目录：${contentAssetRoot}。剧集、账号、中转模型和二创生产任务读取V3真实数据。`}
      </div>

      {/* 二级标签内容视图 */}
      {activeSubTab === 'remix_create' && (
        <RemixCreatePanel
          rawDramas={rawDramas}
          templates={templates}
          modelRoutes={modelRoutes}
          aiRuns={aiRuns}
          selectedRunId={selectedRunId}
          onSelectRunId={setSelectedRunId}
          onCreateNewRun={handleCreateNewRun}
          onBatchUpdateManualStatus={handleBatchUpdateManualStatus}
          showToast={showToast}
        />
      )}

      {activeSubTab === 'remix_jobs' && (
        <RemixJobList
          aiRuns={aiRuns}
          onInspectRunInCreateTab={(runId) => {
            setSelectedRunId(runId);
            setActiveSubTab('remix_create');
          }}
          showToast={showToast}
        />
      )}

      {activeSubTab === 'content_library' && (
        <ContentLibraryPanel
          assets={assets}
          groups={groups}
          groupItems={groupItems}
          globalAuthLimit={globalAuthLimit}
          onUpdateGlobalAuthLimit={(limit) => {
            setGlobalAuthLimit(limit);
            showToast(`✅ 已更新单条成片授权次数上限为 ${limit} 次`);
          }}
          onUpdateAssetManualStatus={handleUpdateAssetManualStatus}
          onImportExternalAsset={handleImportExternalAsset}
          onToggleAssetInGroup={handleToggleAssetInGroup}
          showToast={showToast}
        />
      )}

      {activeSubTab === 'group_publish' && (
        <ContentGroupsPanel
          assets={assets}
          groups={groups}
          groupItems={groupItems}
          originalRecords={originalRecords}
          publications={publications}
          accounts={accounts}
          globalAuthLimit={globalAuthLimit}
          onCreateGroup={handleCreateGroup}
          onRenameGroup={handleRenameGroup}
          onDeleteGroup={handleDeleteGroup}
          onAddAssetToGroup={handleAddAssetToGroup}
          onRemoveAssetFromGroup={handleRemoveAssetFromGroup}
          onMoveGroupItemOrder={handleMoveGroupItemOrder}
          onExecuteOriginalPublish={handleExecuteOriginalPublish}
          onExecuteAuthorizedPublish={handleExecuteAuthorizedPublish}
          showToast={showToast}
        />
      )}
    </main>
  );
};
