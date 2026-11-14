import React, { useEffect, useState } from 'react';
import {
  V3ContentTemplate,
  RawDramaDirectoryInfo,
  V3ContentAiRun,
  PlayContinuityMode,
  StrategyCounts,
  ManualReviewStatus,
  V3DramaHighlightClip,
  ProductionPurpose
} from '../../api/contentProduction';
import { renderContentTemplatePreview, ContentTemplatePreviewResponse } from '../../api/contentTemplates';
import {
  Sparkles,
  Flame,
  Check,
  Minus,
  Plus,
  Film,
  Clock,
  Layers,
  RotateCcw,
  Sliders
} from 'lucide-react';

interface RemixCreatePanelProps {
  rawDramas: RawDramaDirectoryInfo[];
  templates: V3ContentTemplate[];
  highlights?: V3DramaHighlightClip[];
  initialSelectedHighlightIds?: string[];
  initialPurpose?: ProductionPurpose;
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
    productionPurpose?: ProductionPurpose;
    selectedHighlightIds?: string[];
    perHighlightCount?: number;
    basedOnHighlight?: string;
  }) => void;
  onBatchUpdateManualStatus: (runId: string, resultIds: string[], status: ManualReviewStatus) => void;
  onToggleViralHighlight?: (runId: string, resultId: string) => void;
  followUpHighlight?: string | null;
  onClearFollowUpHighlight?: () => void;
  onCancel?: () => void;
  showToast: (msg: string) => void;
  showRunDetails?: boolean;
}

const PURPOSE_OPTIONS: {
  id: ProductionPurpose;
  label: string;
  desc: string;
}[] = [
  { id: '首轮覆盖', label: '首轮覆盖', desc: '勾选多个高光片段批量生成，测试哪条故事线跑得最好' },
  { id: '爆款扩量', label: '爆款扩量', desc: '围绕已跑出的爆款高光，生成更多不同集数/剪法的视频' },
  { id: '失败重做', label: '失败重做', desc: '针对合成异常或技术不合格的高光片段重新生成' },
  { id: '策略测试', label: '策略测试', desc: '更换画面模板、时长区间或跳集/连续策略对比测试' }
];

export const RemixCreatePanel: React.FC<RemixCreatePanelProps> = ({
  rawDramas,
  templates,
  highlights = [],
  initialSelectedHighlightIds = [],
  initialPurpose = '首轮覆盖',
  modelRoutes,
  onCreateNewRun,
  followUpHighlight,
  onCancel,
  showToast
}) => {
  const [selectedDramaId, setSelectedDramaId] = useState<string>('');
  const [purpose, setPurpose] = useState<ProductionPurpose>(initialPurpose);
  const [selectedHighlightIds, setSelectedHighlightIds] = useState<string[]>(initialSelectedHighlightIds);
  const [selectedTemplateId, setSelectedTemplateId] = useState<string>(templates[0]?.id || '');

  // 每个高光生成几条（跳集播放条数 + 连续播放条数）
  const [perHighlightStrategyCounts, setPerHighlightStrategyCounts] = useState<StrategyCounts>({
    '跳集播放': 1,
    '连续播放': 1
  });
  const [minDuration, setMinDuration] = useState<number>(5);
  const [maxDuration, setMaxDuration] = useState<number>(10);
  const [templatePreview, setTemplatePreview] = useState<ContentTemplatePreviewResponse | null>(null);
  const [templatePreviewLoading, setTemplatePreviewLoading] = useState<boolean>(false);

  useEffect(() => {
    setPurpose(initialPurpose);
  }, [initialPurpose]);

  useEffect(() => {
    if (initialSelectedHighlightIds.length > 0) {
      setSelectedHighlightIds(initialSelectedHighlightIds);
      return;
    }
    const defaultSelectable = highlights
      .filter((h) => h.status !== '已淘汰' && h.status !== '暂停')
      .slice(0, 2)
      .map((h) => h.id);
    setSelectedHighlightIds(defaultSelectable);
  }, [highlights, initialSelectedHighlightIds]);

  useEffect(() => {
    const existing = rawDramas.find((drama) => drama.dramaId === selectedDramaId);
    if (existing) return;
    const firstAvailable =
      rawDramas
        .filter((drama) => drama.verifiedMp4Count > 0 && drama.directoryPath)
        .sort((a, b) => b.verifiedMp4Count - a.verifiedMp4Count)[0] || rawDramas[0];
    if (firstAvailable) {
      setSelectedDramaId(firstAvailable.dramaId);
    }
  }, [rawDramas, selectedDramaId]);

  const availableDramas = rawDramas
    .filter((drama) => drama.verifiedMp4Count > 0 && drama.directoryPath)
    .sort((a, b) => b.verifiedMp4Count - a.verifiedMp4Count || a.dramaTitle.localeCompare(b.dramaTitle, 'zh-CN'));

  const currentDrama = availableDramas.find((d) => d.dramaId === selectedDramaId) || availableDramas[0];
  const currentTemplate = templates.find((t) => t.id === selectedTemplateId) || templates[0];

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

  const selectedHighlights = highlights.filter((h) => selectedHighlightIds.includes(h.id));
  const highlightMultiplier = Math.max(1, selectedHighlights.length);
  const perHighlightTotal =
    perHighlightStrategyCounts['跳集播放'] + perHighlightStrategyCounts['连续播放'];
  const totalStrategyCounts: StrategyCounts = {
    '跳集播放': perHighlightStrategyCounts['跳集播放'] * highlightMultiplier,
    '连续播放': perHighlightStrategyCounts['连续播放'] * highlightMultiplier
  };
  const selectedStrategies = (['跳集播放', '连续播放'] as PlayContinuityMode[]).filter(
    (mode) => totalStrategyCounts[mode] > 0
  );
  const targetCount = totalStrategyCounts['跳集播放'] + totalStrategyCounts['连续播放'];

  const toggleHighlightSelection = (id: string) => {
    setSelectedHighlightIds((prev) =>
      prev.includes(id) ? prev.filter((item) => item !== id) : [...prev, id]
    );
  };

  const selectAllActiveHighlights = () => {
    const activeIds = highlights
      .filter((h) => h.status !== '已淘汰' && h.status !== '暂停')
      .map((h) => h.id);
    if (selectedHighlightIds.length === activeIds.length) {
      setSelectedHighlightIds([]);
    } else {
      setSelectedHighlightIds(activeIds);
    }
  };

  const updatePerHighlightCount = (mode: PlayContinuityMode, deltaOrVal: number, isDelta = true) => {
    setPerHighlightStrategyCounts((prev) => {
      const next = isDelta
        ? Math.max(0, Math.min(20, prev[mode] + deltaOrVal))
        : Math.max(0, Math.min(20, deltaOrVal));
      return { ...prev, [mode]: next };
    });
  };

  const handleStartProductionPlan = (e: React.FormEvent) => {
    e.preventDefault();
    if (highlights.length > 0 && selectedHighlights.length === 0) {
      showToast('⚠️ 请至少勾选 1 个高光片段');
      return;
    }
    if (minDuration <= 0 || maxDuration < minDuration) {
      showToast('⚠️ 请设置合理的时长范围（例如 5—10 分钟）');
      return;
    }
    if (!selectedDramaId || !currentDrama) {
      showToast('⚠️ 当前没有可用原剧资料，请先确认原片目录已就绪。');
      return;
    }
    if (!selectedStrategies.length || targetCount <= 0) {
      showToast('⚠️ 请至少设置 1 条生成数量（跳集播放或连续播放）。');
      return;
    }

    const highlightSummaryText =
      selectedHighlights.length === 1
        ? `[${selectedHighlights[0].code}] ${selectedHighlights[0].episodeLabel} ${selectedHighlights[0].timeRange} ${selectedHighlights[0].description.slice(0, 14)}`
        : selectedHighlights.length > 1
        ? `选中 ${selectedHighlights.length} 个高光 (${selectedHighlights.map((h) => h.code).join('、')})`
        : followUpHighlight || undefined;

    onCreateNewRun({
      dramaId: selectedDramaId,
      templateId: selectedTemplateId,
      rendererTemplateId: currentTemplate?.rendererTemplateId,
      playStrategy: selectedStrategies[0],
      playStrategies: selectedStrategies,
      strategyCounts: totalStrategyCounts,
      durationRangeMin: [minDuration, maxDuration],
      targetCount,
      modelId:
        (selectedStrategies.includes('跳集播放') ? modelRoutes.jump : modelRoutes.continuous) ||
        'gemini-2.5-pro-drama-planner',
      productionPurpose: purpose,
      selectedHighlightIds: selectedHighlights.map((h) => h.id),
      perHighlightCount: perHighlightTotal,
      basedOnHighlight: highlightSummaryText
    });
  };

  const durationPresets: [number, number][] = [
    [3, 6],
    [5, 10],
    [8, 15]
  ];

  return (
    <form onSubmit={handleStartProductionPlan} className="space-y-4 text-xs">
      {/* 1. 生产目的选择 */}
      <div className="space-y-1.5">
        <div className="flex items-center justify-between">
          <label className="text-xs font-extrabold text-[#1A1D2E] flex items-center gap-1.5">
            <Sliders className="w-3.5 h-3.5 text-slate-500" />
            <span>1. 生产目的</span>
          </label>
          {currentDrama && (
            <span className="text-[11px] text-slate-500 font-mono">
              《{currentDrama.dramaTitle}》 · 原片 {currentDrama.verifiedMp4Count} 集
            </span>
          )}
        </div>

        <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
          {PURPOSE_OPTIONS.map((opt) => {
            const active = purpose === opt.id;
            return (
              <button
                key={opt.id}
                type="button"
                onClick={() => setPurpose(opt.id)}
                className={`p-2.5 rounded-xl border text-left transition-all cursor-pointer ${
                  active
                    ? 'bg-[#1A1D2E] text-white border-[#1A1D2E] shadow-xs'
                    : 'bg-[#F8FAFC] text-slate-700 border-slate-200/80 hover:bg-white'
                }`}
              >
                <div className="flex items-center justify-between">
                  <span className="font-extrabold text-xs">
                    {opt.id === '爆款扩量' && (
                      <Flame className="w-3 h-3 text-amber-400 fill-amber-400 inline mr-1 -mt-0.5" />
                    )}
                    {opt.id === '失败重做' && (
                      <RotateCcw className="w-3 h-3 text-rose-400 inline mr-1 -mt-0.5" />
                    )}
                    {opt.label}
                  </span>
                  {active && (
                    <span className="w-2 h-2 rounded-full bg-[#DDFD00]" />
                  )}
                </div>
                <p className={`text-[10px] mt-1 line-clamp-2 ${active ? 'text-slate-300' : 'text-slate-500'}`}>
                  {opt.desc}
                </p>
              </button>
            );
          })}
        </div>
      </div>

      {/* 2. 选择一个或多个高光片段 */}
      <div className="space-y-1.5">
        <div className="flex items-center justify-between">
          <label className="text-xs font-extrabold text-[#1A1D2E] flex items-center gap-1.5">
            <Layers className="w-3.5 h-3.5 text-slate-500" />
            <span>2. 选择高光片段（已选 {selectedHighlights.length} 个）</span>
          </label>
          <button
            type="button"
            onClick={selectAllActiveHighlights}
            className="text-[11px] font-bold text-indigo-600 hover:underline cursor-pointer"
          >
            {selectedHighlightIds.length ===
            highlights.filter((h) => h.status !== '已淘汰' && h.status !== '暂停').length
              ? '清空选择'
              : '全选可用高光'}
          </button>
        </div>

        <div className="max-h-44 overflow-y-auto space-y-1.5 p-2 rounded-2xl bg-[#F8FAFC] border border-slate-200/80">
          {highlights.map((hl) => {
            const isSelected = selectedHighlightIds.includes(hl.id);
            const isEliminated = hl.status === '已淘汰' || hl.status === '暂停';
            return (
              <div
                key={hl.id}
                onClick={() => toggleHighlightSelection(hl.id)}
                className={`p-2.5 rounded-xl border transition-all cursor-pointer flex items-start justify-between gap-2.5 ${
                  isSelected
                    ? 'bg-white border-[#1A1D2E] shadow-2xs ring-1 ring-[#1A1D2E]/10'
                    : isEliminated
                    ? 'bg-slate-100/70 border-slate-200 opacity-60'
                    : 'bg-white border-slate-200/70 hover:border-slate-300'
                }`}
              >
                <div className="flex items-start gap-2.5 min-w-0 flex-1">
                  <input
                    type="checkbox"
                    checked={isSelected}
                    onChange={() => undefined}
                    className="mt-0.5 w-3.5 h-3.5 rounded accent-[#1A1D2E] cursor-pointer"
                  />
                  <div className="min-w-0 flex-1">
                    <div className="flex flex-wrap items-center gap-1.5">
                      <span className="px-1.5 py-0.5 rounded bg-slate-100 text-[#1A1D2E] font-mono text-[10px] font-extrabold">
                        {hl.code}
                      </span>
                      <span className="font-extrabold text-xs text-[#1A1D2E]">
                        {hl.episodeLabel} · {hl.timeRange} ({hl.durationText || '30秒'})
                      </span>
                      <span
                        className={`px-1.5 py-0.5 rounded text-[10px] font-bold ${
                          isEliminated
                            ? 'bg-slate-200 text-slate-500'
                            : hl.isViral
                            ? 'bg-amber-100 text-amber-900'
                            : 'bg-emerald-50 text-emerald-700'
                        }`}
                      >
                        {isEliminated ? '已淘汰' : hl.isViral ? '🔥 爆款高光' : '可用'}
                      </span>
                      <span className="text-[10px] font-mono text-slate-400">
                        已生成 {hl.usedCount} 条
                      </span>
                    </div>
                    <p className="text-[11px] text-slate-700 font-semibold truncate mt-0.5">
                      {hl.description}
                    </p>
                    <p className="text-[10px] text-slate-400 truncate">
                      台词：{hl.dialogueText}
                    </p>
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {/* 3. 每个高光生成几条 & 播放方式（跳集 / 连续） */}
      <div className="space-y-1.5">
        <div className="flex items-center justify-between">
          <label className="text-xs font-extrabold text-[#1A1D2E]">
            3. 每个高光生成数量与方式
          </label>
          <span className="px-2.5 py-0.5 rounded-full bg-[#1A1D2E] text-[#DDFD00] font-extrabold text-[11px]">
            选中 {selectedHighlights.length} 个高光 × 每个 {perHighlightTotal} 条 = 计划生成 {targetCount} 条
          </span>
        </div>

        <div className="grid grid-cols-2 gap-3">
          {(
            [
              {
                mode: '跳集播放' as PlayContinuityMode,
                desc: '高光切入 + 跨集剔除过场水词留钩子'
              },
              {
                mode: '连续播放' as PlayContinuityMode,
                desc: '去片头片尾重复帧 + 多集无缝连播'
              }
            ]
          ).map(({ mode, desc }) => {
            const count = perHighlightStrategyCounts[mode];
            const isActive = count > 0;
            return (
              <div
                key={mode}
                className={`p-3 rounded-2xl border transition-all flex flex-col justify-between gap-2.5 ${
                  isActive
                    ? 'bg-white border-[#1A1D2E] shadow-xs ring-1 ring-[#1A1D2E]/10'
                    : 'bg-[#F8FAFC] border-slate-200/80 opacity-75'
                }`}
              >
                <div>
                  <div className="flex items-center justify-between">
                    <span className="font-extrabold text-xs text-[#1A1D2E]">{mode}</span>
                    <span
                      className={`text-[10px] font-bold px-2 py-0.5 rounded-md ${
                        isActive ? 'bg-emerald-50 text-emerald-700' : 'bg-slate-200/70 text-slate-500'
                      }`}
                    >
                      {isActive ? `每个高光 ${count} 条` : '不启用'}
                    </span>
                  </div>
                  <p className="text-[10px] text-slate-500 mt-0.5">{desc}</p>
                </div>

                <div className="flex items-center justify-between pt-2 border-t border-slate-100">
                  <span className="text-[11px] font-bold text-slate-500">每个高光生几条</span>
                  <div className="flex items-center gap-1.5">
                    <button
                      type="button"
                      onClick={() => updatePerHighlightCount(mode, -1, true)}
                      className="w-6 h-6 rounded-lg border border-slate-200 bg-slate-50 hover:bg-slate-100 flex items-center justify-center text-slate-700 cursor-pointer"
                    >
                      <Minus className="w-3 h-3" />
                    </button>
                    <input
                      type="number"
                      min={0}
                      max={20}
                      value={count}
                      onChange={(e) => updatePerHighlightCount(mode, Number(e.target.value), false)}
                      className="w-10 h-6 rounded-lg border border-slate-200 bg-white text-center font-mono font-extrabold text-xs text-[#1A1D2E]"
                    />
                    <button
                      type="button"
                      onClick={() => updatePerHighlightCount(mode, 1, true)}
                      className="w-6 h-6 rounded-lg border border-slate-200 bg-slate-50 hover:bg-slate-100 flex items-center justify-center text-slate-700 cursor-pointer"
                    >
                      <Plus className="w-3 h-3" />
                    </button>
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {/* 4. 视频时长 & 5. 模板选择 */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
        {/* 时长范围 */}
        <div className="space-y-1.5">
          <div className="flex items-center justify-between">
            <label className="text-xs font-extrabold text-[#1A1D2E] flex items-center gap-1">
              <Clock className="w-3.5 h-3.5 text-slate-500" />
              <span>4. 视频时长 (分钟)</span>
            </label>
            <div className="flex items-center gap-1">
              {durationPresets.map(([minP, maxP]) => {
                const isPresetActive = minDuration === minP && maxDuration === maxP;
                return (
                  <button
                    key={`${minP}-${maxP}`}
                    type="button"
                    onClick={() => {
                      setMinDuration(minP);
                      setMaxDuration(maxP);
                    }}
                    className={`px-1.5 py-0.5 rounded text-[10px] font-bold cursor-pointer ${
                      isPresetActive
                        ? 'bg-[#1A1D2E] text-[#DDFD00]'
                        : 'bg-slate-100 text-slate-600'
                    }`}
                  >
                    {minP}-{maxP}m
                  </button>
                );
              })}
            </div>
          </div>

          <div className="p-2.5 rounded-2xl bg-[#F8FAFC] border border-slate-200/80 flex items-center justify-center gap-2">
            <input
              type="number"
              min={1}
              max={30}
              value={minDuration}
              onChange={(e) => setMinDuration(Number(e.target.value))}
              className="w-16 px-2 py-1 rounded-xl border border-slate-200 bg-white font-mono font-extrabold text-center text-[#1A1D2E]"
            />
            <span className="text-slate-400 font-bold">至</span>
            <input
              type="number"
              min={1}
              max={60}
              value={maxDuration}
              onChange={(e) => setMaxDuration(Number(e.target.value))}
              className="w-16 px-2 py-1 rounded-xl border border-slate-200 bg-white font-mono font-extrabold text-center text-[#1A1D2E]"
            />
            <span className="text-slate-500 font-semibold">分钟</span>
          </div>
        </div>

        {/* 模板选择 */}
        <div className="space-y-1.5">
          <div className="flex items-center justify-between">
            <label className="text-xs font-extrabold text-[#1A1D2E] flex items-center gap-1">
              <Film className="w-3.5 h-3.5 text-slate-500" />
              <span>5. 画面模板</span>
            </label>
            <span className="font-mono text-[10px] text-slate-400">
              {templatePreviewLoading ? '预览渲染中…' : currentTemplate?.version}
            </span>
          </div>

          <div className="grid grid-cols-2 gap-1.5">
            {templates.map((tpl) => {
              const isSelected = tpl.id === selectedTemplateId;
              return (
                <button
                  key={tpl.id}
                  type="button"
                  onClick={() => setSelectedTemplateId(tpl.id)}
                  className={`p-2 rounded-xl border text-left transition-all cursor-pointer flex items-center justify-between gap-1.5 ${
                    isSelected
                      ? 'bg-white border-[#1A1D2E] shadow-2xs ring-1 ring-[#1A1D2E]/10'
                      : 'bg-[#F8FAFC] border-slate-200/80 hover:bg-white'
                  }`}
                >
                  <div className="flex items-center gap-1.5 min-w-0">
                    <span
                      className="w-2.5 h-2.5 rounded-full shrink-0"
                      style={{ backgroundColor: tpl.previewColor }}
                    />
                    <span className="font-extrabold text-[11px] text-[#1A1D2E] truncate">
                      {tpl.name.replace('木木短剧·', '')}
                    </span>
                  </div>
                  {isSelected && <Check className="w-3 h-3 text-[#1A1D2E] shrink-0" />}
                </button>
              );
            })}
          </div>
        </div>
      </div>

      {templatePreview && (
        <div className="rounded-xl bg-[#F8FAFC] border border-slate-200/80 p-1.5 flex items-center justify-center">
          <div className="relative w-full max-w-[300px] aspect-[4/1] overflow-hidden rounded bg-white">
            <img
              src={templatePreview.overlay_image_data_url || templatePreview.image_data_url}
              alt="模板预览"
              className="absolute inset-x-0 top-0 h-auto w-full"
            />
          </div>
        </div>
      )}

      {/* 底部操作栏 */}
      <div className="pt-2 flex items-center justify-end gap-2.5 border-t border-slate-100">
        {onCancel && (
          <button
            type="button"
            onClick={onCancel}
            className="px-4 py-2.5 rounded-xl border border-slate-200 bg-white hover:bg-slate-50 text-slate-600 font-bold text-xs cursor-pointer"
          >
            取消
          </button>
        )}
        <button
          type="submit"
          disabled={targetCount <= 0 || (highlights.length > 0 && selectedHighlights.length === 0)}
          className={`flex-1 py-2.5 px-5 rounded-xl font-extrabold text-xs flex items-center justify-center gap-2 shadow-xs transition-all ${
            targetCount > 0 && (highlights.length === 0 || selectedHighlights.length > 0)
              ? 'bg-[#1A1D2E] hover:bg-black text-[#DDFD00] cursor-pointer'
              : 'bg-slate-200 text-slate-400 cursor-not-allowed'
          }`}
        >
          <Sparkles className="w-4 h-4 fill-current" />
          <span>
            提交生产方案并开始生成（{purpose} · 选中 {selectedHighlights.length} 个高光 · 计划生成 {targetCount} 条）
          </span>
        </button>
      </div>
    </form>
  );
};
