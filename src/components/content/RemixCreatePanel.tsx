import React, { useEffect, useState } from 'react';
import {
  V3ContentTemplate,
  RawDramaDirectoryInfo,
  V3ContentAiRun,
  PlayContinuityMode,
  StrategyCounts,
  ManualReviewStatus
} from '../../api/contentProduction';
import { renderContentTemplatePreview, ContentTemplatePreviewResponse } from '../../api/contentTemplates';
import { RemixResultReview } from './RemixResultReview';
import {
  FolderCheck,
  AlertTriangle,
  Sparkles,
  CheckCircle2,
  XCircle,
  Clock,
  Loader2,
  Cpu
} from 'lucide-react';

interface RemixCreatePanelProps {
  rawDramas: RawDramaDirectoryInfo[];
  templates: V3ContentTemplate[];
  modelRoutes: Record<'highlight' | 'continuous' | 'jump' | 'review', string>;
  aiRuns: V3ContentAiRun[];
  selectedRunId: string;
  onSelectRunId: (runId: string) => void;
  onCreateNewRun: (params: {
    dramaId: string;
    templateId: string;
    rendererTemplateId?: string;
    playStrategy: PlayContinuityMode;
    playStrategies: PlayContinuityMode[];
    strategyCounts: StrategyCounts;
    durationRangeMin: [number, number];
    targetCount: number;
    modelId: string;
  }) => void;
  onBatchUpdateManualStatus: (runId: string, resultIds: string[], status: ManualReviewStatus) => void;
  showToast: (msg: string) => void;
  showRunDetails?: boolean;
}

export const RemixCreatePanel: React.FC<RemixCreatePanelProps> = ({
  rawDramas,
  templates,
  modelRoutes,
  aiRuns,
  selectedRunId,
  onSelectRunId,
  onCreateNewRun,
  onBatchUpdateManualStatus,
  showToast,
  showRunDetails = true
}) => {
  // 1. 制作输入表单状态
  const [selectedDramaId, setSelectedDramaId] = useState<string>('');
  const [customDirectory, setCustomDirectory] = useState<string>('');
  const [selectedTemplateId, setSelectedTemplateId] = useState<string>(templates[1]?.id || templates[0]?.id || '');
  const [strategyCounts, setStrategyCounts] = useState<StrategyCounts>({ '连续播放': 2, '跳集播放': 2 });
  const [minDuration, setMinDuration] = useState<number>(5);
  const [maxDuration, setMaxDuration] = useState<number>(10);
  const [dramaQuery, setDramaQuery] = useState<string>('');
  const [dramaPickerOpen, setDramaPickerOpen] = useState<boolean>(false);
  const [templatePreview, setTemplatePreview] = useState<ContentTemplatePreviewResponse | null>(null);
  const [templatePreviewLoading, setTemplatePreviewLoading] = useState<boolean>(false);

  useEffect(() => {
    if (selectedDramaId && rawDramas.some((drama) => drama.dramaId === selectedDramaId)) return;
    const firstAvailable = rawDramas
      .filter((drama) => drama.verifiedMp4Count > 0 && drama.directoryPath)
      .sort((a, b) => b.verifiedMp4Count - a.verifiedMp4Count)[0];
    if (firstAvailable) {
      setSelectedDramaId(firstAvailable.dramaId);
      setCustomDirectory(firstAvailable.directoryPath);
    }
  }, [rawDramas, selectedDramaId]);

  const availableDramas = rawDramas
    .filter((drama) => drama.verifiedMp4Count > 0 && drama.directoryPath)
    .sort((a, b) => b.verifiedMp4Count - a.verifiedMp4Count || a.dramaTitle.localeCompare(b.dramaTitle, 'zh-CN'));
  const filteredDramas = availableDramas.filter((drama) => {
    const query = dramaQuery.trim().toLowerCase();
    return !query || drama.dramaTitle.toLowerCase().includes(query) || drama.dramaId.toLowerCase().includes(query);
  });
  const currentDrama = availableDramas.find((d) => d.dramaId === selectedDramaId) || availableDramas[0];
  const currentTemplate = templates.find((t) => t.id === selectedTemplateId) || templates[0];
  const activeRun = aiRuns.find((r) => r.id === selectedRunId) || aiRuns[0];

  useEffect(() => {
    const rendererTemplateId = currentTemplate?.rendererTemplateId;
    const dramaTitle = currentDrama?.dramaTitle?.trim();
    if (!rendererTemplateId || !dramaTitle) {
      setTemplatePreview(null);
      return;
    }
    let active = true;
    setTemplatePreviewLoading(true);
    renderContentTemplatePreview(rendererTemplateId, dramaTitle)
      .then((preview) => {
        if (active) setTemplatePreview(preview);
      })
      .catch(() => {
        if (active) setTemplatePreview(null);
      })
      .finally(() => {
        if (active) setTemplatePreviewLoading(false);
      });
    return () => {
      active = false;
    };
  }, [currentDrama?.dramaTitle, currentTemplate?.rendererTemplateId]);
  const selectedStrategies = (['连续播放', '跳集播放'] as PlayContinuityMode[]).filter((mode) => strategyCounts[mode] > 0);
  const targetCount = selectedStrategies.reduce((total, mode) => total + strategyCounts[mode], 0);

  const handleDramaChange = (dramaId: string) => {
    setSelectedDramaId(dramaId);
    setDramaQuery('');
    setDramaPickerOpen(false);
    const found = rawDramas.find((d) => d.dramaId === dramaId);
    if (found) {
      setCustomDirectory(found.directoryPath);
    }
  };

  const effectiveDirectory = customDirectory || currentDrama?.directoryPath || '';
  const missingModelRoutes = selectedStrategies
    .map((mode) => mode === '跳集播放' ? modelRoutes.jump : modelRoutes.continuous)
    .filter((modelId) => !modelId);

  const handleStartBatchRemix = (e: React.FormEvent) => {
    e.preventDefault();
    if (minDuration <= 0 || maxDuration < minDuration) {
      showToast('⚠️ 请设置合理的时长范围（例如 5—10 分钟）');
      return;
    }
    if (!selectedDramaId || !currentDrama) {
      showToast('⚠️ 当前V3没有可用原剧资料，请先在剧集资料中建立原片目录。');
      return;
    }
    if (!selectedStrategies.length) {
      showToast('⚠️ 请至少保留一种生成方式，并设置对应条数。');
      return;
    }
    if (missingModelRoutes.length) {
      showToast('⚠️ 当前选中的生成方式尚未在系统设置中分配模型，请先完成任务模型分配。');
      return;
    }
    onCreateNewRun({
      dramaId: selectedDramaId,
      templateId: selectedTemplateId,
      rendererTemplateId: currentTemplate?.rendererTemplateId,
      playStrategy: selectedStrategies[0],
      playStrategies: selectedStrategies,
      strategyCounts,
      durationRangeMin: [minDuration, maxDuration],
      targetCount,
      modelId: selectedStrategies.includes('跳集播放') ? modelRoutes.jump : modelRoutes.continuous
    });
  };

  return (
    <div className="space-y-6">
      {/* Top Grid: 1. 制作输入 + 2. 自动流程进度 */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 items-start">
        {/* 块 1：制作输入 (Left 5 Columns) */}
        <form
          onSubmit={handleStartBatchRemix}
          className={`${showRunDetails ? 'lg:col-span-5' : 'lg:col-span-12'} bg-white rounded-2xl border border-slate-200/90 shadow-xs overflow-hidden`}
        >
          <div className="px-5 py-4 border-b border-slate-100 bg-slate-50/70 flex items-center justify-between">
            <div className="flex items-center gap-2.5">
              <div className="w-7 h-7 rounded-xl bg-[#1A1D2E] text-[#DDFD00] flex items-center justify-center font-bold text-xs">
                1
              </div>
              <div>
                <h3 className="text-sm font-extrabold text-slate-900">新建制作记录</h3>
                <p className="text-[11px] text-slate-500">
                  读取本地原剧母片目录，结合通版模板与模型高光判断批量生成
                </p>
              </div>
            </div>
            <span className="px-2.5 py-1 rounded-lg bg-indigo-50 text-indigo-700 text-[11px] font-bold border border-indigo-200/60">
              不覆写原片
            </span>
          </div>

          <div className="p-5 space-y-4 text-xs">
            {/* 选择原剧 */}
            <div className="space-y-1.5">
              <label className="font-bold text-slate-700 flex items-center justify-between">
                <span>选择原剧</span>
                <span className="text-[11px] font-normal text-slate-400">
                  仅显示已登记原片的 {availableDramas.length} 部剧集
                </span>
              </label>
              <div className="relative">
                <input
                  value={dramaPickerOpen ? dramaQuery : (currentDrama?.dramaTitle ? `《${currentDrama.dramaTitle}》` : '')}
                  placeholder="输入剧名关键词搜索"
                  onFocus={() => setDramaPickerOpen(true)}
                  onChange={(event) => {
                    setDramaQuery(event.target.value.replace(/[《》]/g, ''));
                    setDramaPickerOpen(true);
                  }}
                  className="w-full px-3 py-2 rounded-xl border border-slate-200 bg-slate-50/60 font-bold text-slate-900 focus:outline-none focus:border-indigo-500"
                />
                {dramaPickerOpen && (
                  <div className="absolute z-30 mt-1 w-full max-h-72 overflow-auto rounded-xl border border-slate-200 bg-white shadow-xl">
                    <div className="sticky top-0 px-3 py-2 text-[11px] text-slate-500 bg-slate-50 border-b border-slate-100">
                      按原片集数排序 · 只列出当前可用原片
                    </div>
                    {filteredDramas.length === 0 ? (
                      <div className="px-3 py-6 text-center text-xs text-slate-400">没有匹配的可用原剧</div>
                    ) : filteredDramas.map((drama) => (
                      <button
                        key={drama.dramaId}
                        type="button"
                        onMouseDown={(event) => event.preventDefault()}
                        onClick={() => handleDramaChange(drama.dramaId)}
                        className={`w-full px-3 py-2.5 text-left hover:bg-indigo-50 ${drama.dramaId === selectedDramaId ? 'bg-indigo-50 text-indigo-800' : 'text-slate-800'}`}
                      >
                        <div className="flex items-center justify-between gap-2 font-bold">
                          <span>《{drama.dramaTitle}》</span>
                          <span className="text-[11px] font-mono text-slate-500">{drama.verifiedMp4Count}/{drama.totalEpisodes}集 · {drama.totalSizeGb}GB</span>
                        </div>
                      </button>
                    ))}
                  </div>
                )}
              </div>
            </div>

            {/* 选择原片目录 & 显示集数和文件状态 */}
            <div className="space-y-1.5">
              <label className="font-bold text-slate-700 flex items-center justify-between">
                <span>原片本地目录</span>
                <button
                  type="button"
                  onClick={() =>
                    showToast(`🔍 已重新校验目录：${effectiveDirectory}`)
                  }
                  className="text-indigo-600 hover:underline font-semibold cursor-pointer"
                >
                  重新扫描目录
                </button>
              </label>
              <input
                type="text"
                value={effectiveDirectory}
                onChange={(e) => setCustomDirectory(e.target.value)}
                className="w-full px-3 py-2 rounded-xl border border-slate-200 bg-slate-50 font-mono text-[11px] text-slate-700 focus:outline-none focus:border-indigo-500"
              />

              {/* 集数和文件状态展示框 */}
              {currentDrama && (
                <div
                  className={`p-3 rounded-xl border flex items-start gap-2.5 ${
                    currentDrama.scanStatus === 'ready'
                      ? 'bg-emerald-50/60 border-emerald-200/80 text-emerald-950'
                      : 'bg-amber-50/70 border-amber-200/90 text-amber-950'
                  }`}
                >
                  {currentDrama.scanStatus === 'ready' ? (
                    <FolderCheck className="w-4 h-4 text-emerald-600 flex-shrink-0 mt-0.5" />
                  ) : (
                    <AlertTriangle className="w-4 h-4 text-amber-600 flex-shrink-0 mt-0.5" />
                  )}
                  <div className="space-y-0.5 flex-1">
                    <div className="font-bold flex items-center justify-between">
                      <span>
                        集数校验：{currentDrama.verifiedMp4Count} / {currentDrama.totalEpisodes} 集可用
                      </span>
                      <span className="font-mono text-[11px]">
                        {currentDrama.totalSizeGb} GB
                      </span>
                    </div>
                    <p className="text-[11px] opacity-85">{currentDrama.statusSummary}</p>
                  </div>
                </div>
              )}
            </div>

            {/* 选择通版模板 */}
            <div className="space-y-1.5">
              <label className="font-bold text-slate-700 flex items-center justify-between">
                <span>选择通版模板 (v3_content_templates)</span>
                <span className="font-mono text-[11px] text-indigo-600 font-semibold">
                  {currentTemplate?.version}
                </span>
              </label>
              <select
                value={selectedTemplateId}
                onChange={(e) => setSelectedTemplateId(e.target.value)}
                className="w-full px-3 py-2 rounded-xl border border-slate-200 bg-slate-50/60 font-bold text-slate-900 focus:outline-none focus:border-indigo-500"
              >
                {templates.map((tpl) => (
                  <option key={tpl.id} value={tpl.id}>
                    {tpl.name} [{tpl.version}]
                  </option>
                ))}
              </select>
              <div className="rounded-xl border border-indigo-100 bg-indigo-50/40 p-3 space-y-2">
                <div className="flex items-center justify-between text-[11px] font-bold text-indigo-900">
                  <span>当前剧名模板预览</span>
                  <span className="font-normal text-indigo-600">
                    {templatePreviewLoading ? '渲染中…' : templatePreview ? `${templatePreview.layout.font_size}px` : '等待本地服务'}
                  </span>
                </div>
                {templatePreview ? (
                  <div className="rounded-lg bg-slate-100 border border-slate-200 p-2 flex justify-center">
                    <div className="relative w-full max-w-[480px] aspect-[4/1] overflow-hidden rounded-md shadow-sm bg-white">
                    <img
                      src={templatePreview.overlay_image_data_url || templatePreview.image_data_url}
                      alt={`${currentDrama?.dramaTitle || '当前剧名'}模板预览`}
                      className="absolute inset-x-0 top-0 h-auto w-full"
                    />
                    </div>
                  </div>
                ) : (
                  <p className="text-[11px] text-slate-500">选择有原片的剧集并启动 V3 服务后，这里显示顶部剧名素材。</p>
                )}
              </div>
            </div>

            {/* 生成方式：允许同一批同时生成连续和少量跳集作品 */}
            <div className="space-y-1.5">
              <label className="font-bold text-slate-700 flex items-center justify-between">
                <span>生成方式</span>
                <span className="text-[11px] font-normal text-slate-400">可同时启用，两种方式分别计数</span>
              </label>
              <div className="grid grid-cols-2 gap-2.5">
                {(['跳集播放', '连续播放'] as PlayContinuityMode[]).map((mode) => {
                  const active = strategyCounts[mode] > 0;
                  return (
                    <div
                      key={mode}
                      className={`p-2.5 rounded-xl border text-left transition-all cursor-pointer ${
                        active
                          ? 'bg-[#1A1D2E] text-white border-[#1A1D2E] shadow-xs'
                          : 'bg-slate-50/70 text-slate-700 border-slate-200 hover:bg-slate-100'
                      }`}
                    >
                      <div className="font-extrabold flex items-center justify-between gap-2">
                        <label className="flex items-center gap-2 cursor-pointer">
                          <input
                            type="checkbox"
                            checked={active}
                            onChange={(event) => setStrategyCounts((current) => ({ ...current, [mode]: event.target.checked ? Math.max(1, current[mode]) : 0 }))}
                            className="accent-indigo-600"
                          />
                          <span>{mode}</span>
                        </label>
                        <input
                          type="number"
                          min={0}
                          max={50}
                          value={strategyCounts[mode]}
                          onChange={(event) => setStrategyCounts((current) => ({ ...current, [mode]: Math.max(0, Number(event.target.value)) }))}
                          className="w-14 px-1.5 py-1 rounded-lg border border-slate-300 bg-white text-center font-mono text-xs text-slate-900"
                          aria-label={`${mode}生成数量`}
                        />
                      </div>
                      <p className={`text-[10px] mt-0.5 ${active ? 'text-slate-300' : 'text-slate-500'}`}>
                        {mode === '跳集播放'
                          ? '高光切入 + 跨集剔除过场水词留钩子'
                          : '去片头片尾重复帧 + 多集无缝连播'}
                      </p>
                    </div>
                  );
                })}
              </div>
              <p className="text-[11px] text-slate-500">本次生成计划 {targetCount} 条。跳集播放只代表少量跨集组合，具体跳点由流程自动判断。</p>
            </div>

            {/* 设置时长范围 & 目标数量 */}
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1.5">
                <label className="font-bold text-slate-700 block">
                  单条时长范围 (分钟)
                </label>
                <div className="flex items-center gap-1.5">
                  <input
                    type="number"
                    min={1}
                    max={30}
                    value={minDuration}
                    onChange={(e) => setMinDuration(Number(e.target.value))}
                    className="w-full px-2.5 py-2 rounded-xl border border-slate-200 bg-slate-50 font-mono font-bold text-center"
                  />
                  <span className="text-slate-400 font-bold">—</span>
                  <input
                    type="number"
                    min={1}
                    max={60}
                    value={maxDuration}
                    onChange={(e) => setMaxDuration(Number(e.target.value))}
                    className="w-full px-2.5 py-2 rounded-xl border border-slate-200 bg-slate-50 font-mono font-bold text-center"
                  />
                </div>
              </div>

              <div className="space-y-1.5">
                <label className="font-bold text-slate-700 block">本次目标数量 (条)</label>
                <input
                  type="number"
                  value={targetCount}
                  readOnly
                  className="w-full px-3 py-2 rounded-xl border border-slate-200 bg-slate-100 font-mono font-bold text-slate-900"
                />
              </div>
            </div>

            {/* 任务模型由系统设置按角色自动分配 */}
            <div className="space-y-1.5">
              <div className="flex items-center justify-between gap-2">
                <label className="font-bold text-slate-700 flex items-center gap-1">
                  <Cpu className="w-3.5 h-3.5 text-indigo-600" />
                  <span>任务模型分配</span>
                </label>
                <span className="text-[11px] text-slate-400">在系统设置中统一配置</span>
              </div>
              <div className="grid grid-cols-2 gap-2">
                {[
                  ['highlight', '高光判断'],
                  ['continuous', '连续播放规划'],
                  ['jump', '跳集播放规划'],
                  ['review', '结果复核']
                ].map(([route, label]) => (
                  <div key={route} className="px-2.5 py-2 rounded-xl border border-slate-200 bg-slate-50 text-[11px]">
                    <div className="text-slate-500">{label}</div>
                    <div className={`mt-0.5 font-mono font-bold ${modelRoutes[route as keyof typeof modelRoutes] ? 'text-slate-800' : 'text-amber-600'}`}>
                      {modelRoutes[route as keyof typeof modelRoutes] || '未分配'}
                    </div>
                  </div>
                ))}
              </div>
            </div>

            <button
              type="submit"
              className="w-full py-2.5 px-4 rounded-xl bg-[#1A1D2E] hover:bg-black text-[#DDFD00] font-extrabold text-xs flex items-center justify-center gap-2 shadow-sm transition-all cursor-pointer"
            >
              <Sparkles className="w-4 h-4 fill-current" />
              <span>启动原剧二创自动流水线 (生成 {targetCount} 条)</span>
            </button>
          </div>
        </form>

        {showRunDetails && <>
        {/* 块 2：流程进度展示 (Right 7 Columns) */}
        <div className="lg:col-span-7 bg-white rounded-2xl border border-slate-200/90 shadow-xs overflow-hidden">
          <div className="px-5 py-4 border-b border-slate-100 bg-slate-50/70 flex flex-wrap items-center justify-between gap-3">
            <div className="flex items-center gap-2.5">
              <div className="w-7 h-7 rounded-xl bg-[#1A1D2E] text-[#DDFD00] flex items-center justify-center font-bold text-xs">
                2
              </div>
              <div>
                <h3 className="text-sm font-extrabold text-slate-900">
                  制作记录执行过程
                </h3>
                <p className="text-[11px] text-slate-500">
                  显示真实后台任务状态、耗时与失败原因
                </p>
              </div>
            </div>

            {/* 任务切换器 */}
            <div className="flex items-center gap-2">
              <span className="text-xs text-slate-500 font-semibold">当前制作记录:</span>
              <select
                value={activeRun?.id || ''}
                onChange={(e) => onSelectRunId(e.target.value)}
                className="px-3 py-1.5 rounded-xl border border-slate-200 bg-white text-xs font-bold text-slate-900"
              >
                {aiRuns.map((run) => (
                  <option key={run.id} value={run.id}>
                    {run.jobCode} · 《{run.dramaTitle}》 ({run.playStrategies?.join(' + ') || run.playStrategy})
                  </option>
                ))}
              </select>
            </div>
          </div>

          {activeRun && (
            <div className="p-5 space-y-4">
              {/* Run Context Banner */}
              <div className="p-3.5 rounded-xl bg-slate-900 text-white flex flex-wrap items-center justify-between gap-3 text-xs">
                <div className="space-y-0.5">
                  <div className="flex items-center gap-2">
                    <span className="font-mono font-bold text-[#DDFD00]">
                      {activeRun.jobCode}
                    </span>
                    <span className="font-extrabold">《{activeRun.dramaTitle}》</span>
                    <span className="px-2 py-0.5 rounded bg-white/10 text-[11px]">
                      {activeRun.playStrategies?.join(' + ') || activeRun.playStrategy} · {activeRun.durationRangeMin[0]}—{activeRun.durationRangeMin[1]}分钟
                    </span>
                  </div>
                  <div className="text-[11px] text-slate-300 font-mono">
                    模型: {activeRun.modelId} · 模板: {activeRun.templateVersion} · 目标: {activeRun.targetCount}条
                  </div>
                </div>

                {activeRun.status === 'running' && (
                  <span className="px-3 py-1.5 rounded-xl bg-indigo-100 text-indigo-800 font-extrabold text-xs">
                    后台自动执行中
                  </span>
                )}
              </div>

              {/* 7-Step Pipeline Visual Chain */}
              <div className="space-y-2.5">
                {activeRun.pipelineSteps.map((step, index) => {
                  const isCompleted = step.status === 'completed';
                  const isRunning = step.status === 'running';
                  const isFailed = step.status === 'failed';
                  const isPending = step.status === 'pending';

                  return (
                    <div
                      key={step.key}
                      className={`p-3.5 rounded-xl border transition-all ${
                        isFailed
                          ? 'bg-rose-50/70 border-rose-200'
                          : isRunning
                          ? 'bg-indigo-50/60 border-indigo-300 shadow-xs'
                          : isCompleted
                          ? 'bg-emerald-50/30 border-emerald-200/70'
                          : 'bg-slate-50/60 border-slate-200/60 opacity-75'
                      }`}
                    >
                      <div className="flex flex-wrap items-center justify-between gap-2">
                        <div className="flex items-center gap-2.5">
                          <span className="w-5 h-5 rounded-full bg-slate-900/10 text-slate-700 font-mono text-[11px] font-bold flex items-center justify-center">
                            {index + 1}
                          </span>
                          <span className="font-extrabold text-xs text-slate-900">
                            {step.label}
                          </span>

                          {/* Status Pill */}
                          {isCompleted && (
                            <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-md bg-emerald-100 text-emerald-800 text-[11px] font-bold">
                              <CheckCircle2 className="w-3 h-3" /> 已完成
                            </span>
                          )}
                          {isRunning && (
                            <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-md bg-indigo-600 text-white text-[11px] font-bold">
                              <Loader2 className="w-3 h-3 animate-spin" /> 执行中
                            </span>
                          )}
                          {isFailed && (
                            <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-md bg-rose-600 text-white text-[11px] font-bold">
                              <XCircle className="w-3 h-3" /> 存在异常拦截
                            </span>
                          )}
                          {isPending && (
                            <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-md bg-slate-200 text-slate-600 text-[11px] font-semibold">
                              <Clock className="w-3 h-3" /> 待执行
                            </span>
                          )}
                        </div>

                        <span className="font-mono text-[11px] font-bold text-slate-600">
                          耗时：{step.durationText}
                        </span>
                      </div>

                      <p className="text-xs text-slate-600 mt-1.5 pl-7">
                        {step.detailText}
                      </p>

                      {step.errorReason && (
                        <div className="mt-2 ml-7 p-2.5 rounded-lg bg-rose-100/80 border border-rose-200 text-rose-900 text-[11px] font-semibold flex items-start gap-2">
                          <AlertTriangle className="w-3.5 h-3.5 text-rose-600 flex-shrink-0 mt-0.5" />
                          <span>失败原因：{step.errorReason}</span>
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            </div>
          )}
        </div>
        </>}
      </div>

      {/* 块 3：批量结果 (Bottom Full Width) */}
      {showRunDetails && activeRun && (
        <RemixResultReview
          jobCode={activeRun.jobCode}
          dramaTitle={activeRun.dramaTitle}
          results={activeRun.results}
          onBatchUpdateManualStatus={(resultIds, status) =>
            onBatchUpdateManualStatus(activeRun.id, resultIds, status)
          }
          onTriggerBatchGenerateMore={() => {
            onCreateNewRun({
              dramaId: activeRun.dramaId,
              templateId: activeRun.templateId,
              rendererTemplateId: currentTemplate?.rendererTemplateId,
              playStrategy: activeRun.playStrategy,
              playStrategies: activeRun.playStrategies || [activeRun.playStrategy],
              strategyCounts: activeRun.strategyCounts || { '连续播放': 0, '跳集播放': activeRun.targetCount },
              durationRangeMin: activeRun.durationRangeMin,
              targetCount: activeRun.targetCount,
              modelId: activeRun.modelId
            });
          }}
          showToast={showToast}
        />
      )}
    </div>
  );
};
