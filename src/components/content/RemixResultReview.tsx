import React, { useState } from 'react';
import {
  V3RemixBatchResultItem,
  ManualReviewStatus
} from '../../api/contentProduction';
import {
  Play,
  FolderOpen,
  FileSearch,
  CheckCircle2,
  XCircle,
  Clock,
  Film,
  Sparkles,
  Scissors,
  Layers,
  ShieldCheck,
  AlertTriangle,
  Trash2,
  X,
  CheckSquare,
  Square
} from 'lucide-react';

interface RemixResultReviewProps {
  jobCode: string;
  dramaTitle: string;
  results: V3RemixBatchResultItem[];
  onBatchUpdateManualStatus: (resultIds: string[], status: ManualReviewStatus) => void;
  onTriggerBatchGenerateMore?: () => void;
  showToast: (msg: string) => void;
}

export const RemixResultReview: React.FC<RemixResultReviewProps> = ({
  jobCode,
  dramaTitle,
  results,
  onBatchUpdateManualStatus,
  onTriggerBatchGenerateMore,
  showToast
}) => {
  const [selectedIds, setSelectedIds] = useState<string[]>([]);
  const [previewItem, setPreviewItem] = useState<V3RemixBatchResultItem | null>(null);
  const [sourceModalItem, setSourceModalItem] = useState<V3RemixBatchResultItem | null>(null);

  const toggleSelect = (id: string) => {
    setSelectedIds((prev) =>
      prev.includes(id) ? prev.filter((item) => item !== id) : [...prev, id]
    );
  };

  const toggleSelectAll = () => {
    if (selectedIds.length === results.length && results.length > 0) {
      setSelectedIds([]);
    } else {
      setSelectedIds(results.map((r) => r.id));
    }
  };

  const handleBatchEliminate = () => {
    if (selectedIds.length === 0) {
      showToast('请先勾选需要淘汰的批量结果');
      return;
    }
    onBatchUpdateManualStatus(selectedIds, '已淘汰');
    setSelectedIds([]);
  };

  const handleBatchApprove = () => {
    if (selectedIds.length === 0) {
      showToast('请先勾选需要审核通过的结果');
      return;
    }
    onBatchUpdateManualStatus(selectedIds, '已通过');
    setSelectedIds([]);
  };

  return (
    <div className="bg-white rounded-2xl border border-slate-200/90 shadow-xs overflow-hidden">
      {/* Header Bar */}
      <div className="px-5 py-4 border-b border-slate-100 bg-slate-50/70 flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-3">
          <div className="w-8 h-8 rounded-xl bg-[#1A1D2E] text-[#DDFD00] flex items-center justify-center font-bold text-xs">
            3
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h3 className="text-sm font-extrabold text-slate-900">
                批量结果审核与抽检
              </h3>
              <span className="px-2 py-0.5 rounded-md bg-slate-200/70 text-slate-700 font-mono text-[11px] font-semibold">
                {jobCode}
              </span>
              <span className="text-xs text-slate-500 font-medium">
                《{dramaTitle}》· 共 {results.length} 条结果
              </span>
            </div>
            <p className="text-[11px] text-slate-500 mt-0.5">
              全自动合成与技术质检，无需人工逐条参与时间线剪辑；可抽检预览或一键批量淘汰残次品
            </p>
          </div>
        </div>

        {/* Batch Action Toolbar */}
        <div className="flex flex-wrap items-center gap-2">
          <button
            type="button"
            onClick={toggleSelectAll}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-xl border border-slate-200 bg-white hover:bg-slate-50 text-xs font-semibold text-slate-700 transition-colors cursor-pointer"
          >
            {selectedIds.length === results.length && results.length > 0 ? (
              <CheckSquare className="w-3.5 h-3.5 text-indigo-600" />
            ) : (
              <Square className="w-3.5 h-3.5 text-slate-400" />
            )}
            <span>全选 ({selectedIds.length}/{results.length})</span>
          </button>

          {onTriggerBatchGenerateMore && (
            <button
              type="button"
              onClick={onTriggerBatchGenerateMore}
              className="flex items-center gap-1.5 px-3.5 py-1.5 rounded-xl bg-indigo-50 hover:bg-indigo-100 text-indigo-700 border border-indigo-200/80 text-xs font-bold transition-colors cursor-pointer"
            >
              <Sparkles className="w-3.5 h-3.5" />
              <span>追加生成记录</span>
            </button>
          )}

          <button
            type="button"
            onClick={handleBatchApprove}
            disabled={selectedIds.length === 0}
            className={`flex items-center gap-1.5 px-3.5 py-1.5 rounded-xl text-xs font-bold transition-all cursor-pointer ${
              selectedIds.length > 0
                ? 'bg-emerald-600 hover:bg-emerald-700 text-white shadow-xs'
                : 'bg-slate-100 text-slate-400 cursor-not-allowed'
            }`}
          >
            <CheckCircle2 className="w-3.5 h-3.5" />
            <span>批量通过并入库</span>
          </button>

          <button
            type="button"
            onClick={handleBatchEliminate}
            disabled={selectedIds.length === 0}
            className={`flex items-center gap-1.5 px-3.5 py-1.5 rounded-xl text-xs font-bold transition-all cursor-pointer ${
              selectedIds.length > 0
                ? 'bg-rose-600 hover:bg-rose-700 text-white shadow-xs'
                : 'bg-slate-100 text-slate-400 cursor-not-allowed'
            }`}
          >
            <Trash2 className="w-3.5 h-3.5" />
            <span>批量淘汰</span>
          </button>
        </div>
      </div>

      {/* Results List */}
      {results.length === 0 ? (
        <div className="py-14 text-center text-slate-400 text-xs">
          当前制作记录尚无已产出的视频成片结果，请等待自动流程执行至「视频合成」阶段
        </div>
      ) : (
        <div className="divide-y divide-slate-100">
          {results.map((item) => {
            const isSelected = selectedIds.includes(item.id);
            const isEliminated = item.manualStatus === '已淘汰';

            return (
              <div
                key={item.id}
                className={`p-4 sm:p-5 transition-colors flex flex-col xl:flex-row gap-4 items-start xl:items-center justify-between ${
                  isSelected
                    ? 'bg-indigo-50/40'
                    : isEliminated
                    ? 'bg-slate-50/60 opacity-75'
                    : 'hover:bg-slate-50/60'
                }`}
              >
                {/* Left: Checkbox + Video Preview Thumbnail + Core Info */}
                <div className="flex items-start gap-3.5 flex-1 min-w-0 w-full">
                  <button
                    type="button"
                    onClick={() => toggleSelect(item.id)}
                    className="mt-1 text-slate-400 hover:text-indigo-600 cursor-pointer flex-shrink-0"
                  >
                    {isSelected ? (
                      <CheckSquare className="w-4 h-4 text-indigo-600" />
                    ) : (
                      <Square className="w-4 h-4" />
                    )}
                  </button>

                  {/* Video Preview Box (9:16 styled thumbnail) */}
                  <div
                    onClick={() => setPreviewItem(item)}
                    className={`relative w-20 h-28 rounded-xl bg-gradient-to-br ${item.previewHue} flex-shrink-0 overflow-hidden border border-slate-800/20 shadow-xs group cursor-pointer flex flex-col justify-between p-2 text-white`}
                  >
                    <div className="flex items-center justify-between text-[9px] font-mono opacity-80">
                      <span>9:16</span>
                      <span>{item.playStrategy === '跳集播放' ? '跳集' : '连续'}</span>
                    </div>
                    <div className="self-center w-8 h-8 rounded-full bg-black/50 backdrop-blur-xs border border-white/30 flex items-center justify-center group-hover:scale-110 group-hover:bg-[#DDFD00] group-hover:text-slate-950 transition-all">
                      <Play className="w-3.5 h-3.5 fill-current ml-0.5" />
                    </div>
                    <div className="text-[10px] font-mono font-bold bg-black/60 px-1.5 py-0.5 rounded text-center truncate">
                      {item.durationFormatted}
                    </div>
                  </div>

                  {/* Metadata Grid */}
                  <div className="flex-1 min-w-0 space-y-2">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="font-extrabold text-sm text-slate-900 truncate">
                        {item.videoName}
                      </span>

                      {/* 技术检查结果 Badge */}
                      {item.techStatus === '合格' && (
                        <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-md bg-emerald-50 text-emerald-700 border border-emerald-200 text-[11px] font-bold">
                          <ShieldCheck className="w-3 h-3" />
                          技术检查：合格
                        </span>
                      )}
                      {item.techStatus === '不合格' && (
                        <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-md bg-rose-50 text-rose-700 border border-rose-200 text-[11px] font-bold">
                          <AlertTriangle className="w-3 h-3" />
                          技术检查：不合格
                        </span>
                      )}
                      {item.techStatus === '待检查' && (
                        <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-md bg-amber-50 text-amber-700 border border-amber-200 text-[11px] font-bold">
                          <Clock className="w-3 h-3" />
                          技术检查：待检查
                        </span>
                      )}

                      {/* 人工审核状态 Badge */}
                      {item.manualStatus === '已通过' && (
                        <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-md bg-indigo-50 text-indigo-700 border border-indigo-200 text-[11px] font-bold">
                          <CheckCircle2 className="w-3 h-3" />
                          人工审核：已通过
                        </span>
                      )}
                      {item.manualStatus === '待审核' && (
                        <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-md bg-slate-100 text-slate-700 border border-slate-200 text-[11px] font-bold">
                          <Clock className="w-3 h-3" />
                          人工审核：待审核
                        </span>
                      )}
                      {item.manualStatus === '已淘汰' && (
                        <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-md bg-rose-100/80 text-rose-800 border border-rose-200 text-[11px] font-bold">
                          <XCircle className="w-3 h-3" />
                          人工审核：已淘汰
                        </span>
                      )}
                    </div>

                    {/* Key Structural Attributes: 时长、原剧范围、模板版本、高光切入点 */}
                    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-2 text-xs">
                      <div className="bg-slate-50 rounded-lg px-2.5 py-1.5 border border-slate-200/60">
                        <span className="text-slate-400 text-[11px] block">原剧范围 & 时长</span>
                        <span className="font-bold text-slate-800">
                          {item.episodeRange} · {item.durationFormatted}
                        </span>
                      </div>

                      <div className="bg-slate-50 rounded-lg px-2.5 py-1.5 border border-slate-200/60">
                        <span className="text-slate-400 text-[11px] block">通版模板版本</span>
                        <span className="font-bold text-slate-800 font-mono">
                          {item.templateVersion}
                        </span>
                      </div>

                      <div className="bg-amber-50/60 rounded-lg px-2.5 py-1.5 border border-amber-200/60 md:col-span-2">
                        <span className="text-amber-700/80 text-[11px] flex items-center gap-1 font-semibold">
                          <Sparkles className="w-3 h-3" /> 高光切入点
                        </span>
                        <span className="font-bold text-amber-950 block truncate" title={item.highlightCutPoint}>
                          {item.highlightCutPoint}
                        </span>
                      </div>
                    </div>

                    {/* 跳集位置 & 技术检查详情 */}
                    <div className="flex flex-wrap items-center gap-x-4 gap-y-1.5 text-[11px]">
                      <div className="flex items-center gap-1.5 text-slate-600">
                        <Scissors className="w-3.5 h-3.5 text-indigo-600 flex-shrink-0" />
                        <span className="font-semibold text-slate-700">跳集位置：</span>
                        <div className="flex flex-wrap gap-1">
                          {item.jumpCutPositions.map((pos, idx) => (
                            <span
                              key={idx}
                              className="px-2 py-0.5 rounded bg-indigo-50/80 text-indigo-900 border border-indigo-200/60 font-mono"
                            >
                              {pos}
                            </span>
                          ))}
                        </div>
                      </div>

                      <div className="text-slate-500">
                        <span className="font-semibold text-slate-600">质检报告：</span>
                        <span className={item.techStatus === '不合格' ? 'text-rose-600 font-semibold' : ''}>
                          {item.techReport}
                        </span>
                      </div>
                    </div>
                  </div>
                </div>

                {/* Right: Single Item Quick Actions */}
                <div className="flex flex-wrap items-center gap-2 self-end xl:self-center flex-shrink-0">
                  <button
                    type="button"
                    onClick={() => setPreviewItem(item)}
                    className="flex items-center gap-1 px-2.5 py-1.5 rounded-lg bg-slate-900 hover:bg-slate-800 text-[#DDFD00] text-xs font-bold transition-colors cursor-pointer"
                  >
                    <Play className="w-3.5 h-3.5 fill-current" />
                    <span>播放预览</span>
                  </button>

                  <button
                    type="button"
                    onClick={() => setSourceModalItem(item)}
                    className="flex items-center gap-1 px-2.5 py-1.5 rounded-lg bg-white hover:bg-slate-50 text-slate-700 border border-slate-200 text-xs font-semibold transition-colors cursor-pointer"
                  >
                    <FileSearch className="w-3.5 h-3.5 text-indigo-600" />
                    <span>查看来源</span>
                  </button>

                  <button
                    type="button"
                    onClick={() =>
                      showToast(`📂 已调用本地文件服务定位：${item.filePath}`)
                    }
                    className="flex items-center gap-1 px-2.5 py-1.5 rounded-lg bg-white hover:bg-slate-50 text-slate-700 border border-slate-200 text-xs font-semibold transition-colors cursor-pointer"
                  >
                    <FolderOpen className="w-3.5 h-3.5 text-amber-600" />
                    <span>打开文件</span>
                  </button>

                  {item.manualStatus !== '已淘汰' ? (
                    <button
                      type="button"
                      onClick={() => onBatchUpdateManualStatus([item.id], '已淘汰')}
                      className="flex items-center gap-1 px-2.5 py-1.5 rounded-lg bg-rose-50 hover:bg-rose-100 text-rose-700 border border-rose-200 text-xs font-bold transition-colors cursor-pointer"
                    >
                      <Trash2 className="w-3.5 h-3.5" />
                      <span>淘汰</span>
                    </button>
                  ) : (
                    <button
                      type="button"
                      onClick={() => onBatchUpdateManualStatus([item.id], '已通过')}
                      className="flex items-center gap-1 px-2.5 py-1.5 rounded-lg bg-emerald-50 hover:bg-emerald-100 text-emerald-700 border border-emerald-200 text-xs font-bold transition-colors cursor-pointer"
                    >
                      <CheckCircle2 className="w-3.5 h-3.5" />
                      <span>恢复通过</span>
                    </button>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      )}

      {/* Modal 1: 播放预览 (Play Preview Modal) */}
      {previewItem && (
        <div className="fixed inset-0 z-50 bg-slate-950/75 backdrop-blur-xs flex items-center justify-center p-4">
          <div className="bg-slate-900 text-white rounded-2xl max-w-2xl w-full border border-slate-700/80 shadow-2xl overflow-hidden animate-in zoom-in-95 duration-150">
            <div className="px-5 py-3.5 border-b border-slate-800 flex items-center justify-between">
              <div className="flex items-center gap-2">
                <Film className="w-4 h-4 text-[#DDFD00]" />
                <span className="font-bold text-sm truncate">{previewItem.videoName}</span>
              </div>
              <button
                type="button"
                onClick={() => setPreviewItem(null)}
                className="p-1 rounded-lg text-slate-400 hover:text-white hover:bg-slate-800 cursor-pointer"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            <div className="p-5 grid grid-cols-1 md:grid-cols-12 gap-5 items-center">
              {/* Simulated 9:16 Player */}
              <div
                className={`md:col-span-5 aspect-[9/16] max-h-[380px] mx-auto w-full rounded-xl bg-gradient-to-br ${previewItem.previewHue} border border-white/15 p-4 flex flex-col justify-between relative overflow-hidden`}
              >
                <div className="flex items-center justify-between text-[11px] font-mono bg-black/40 px-2.5 py-1 rounded-lg">
                  <span>{previewItem.dramaTitle}</span>
                  <span className="text-[#DDFD00]">{previewItem.templateVersion}</span>
                </div>

                <div className="my-auto text-center space-y-2 px-2">
                  <div className="w-12 h-12 rounded-full bg-[#DDFD00] text-slate-950 flex items-center justify-center mx-auto shadow-lg">
                    <Play className="w-5 h-5 fill-current ml-0.5" />
                  </div>
                  <p className="text-xs font-bold text-white/90">
                    {previewItem.highlightCutPoint}
                  </p>
                  <p className="text-[11px] text-slate-300">
                    正在抽检成片时间轴 · {previewItem.durationFormatted}
                  </p>
                </div>

                {/* Fake Subtitle & Progress Bar */}
                <div className="space-y-2">
                  <div className="bg-black/70 text-amber-300 font-extrabold text-xs text-center py-1 px-2 rounded border border-amber-400/30">
                    “三年之期已到，恭迎龙帅归位！”
                  </div>
                  <div className="h-1.5 bg-white/20 rounded-full overflow-hidden">
                    <div className="h-full w-2/5 bg-[#DDFD00] rounded-full" />
                  </div>
                </div>
              </div>

              {/* Right Inspection Details */}
              <div className="md:col-span-7 space-y-3 text-xs">
                <div className="p-3 rounded-xl bg-slate-800/90 border border-slate-700 space-y-1.5">
                  <div className="text-slate-400 text-[11px]">原剧范围与播放模式</div>
                  <div className="font-bold text-sm text-white">
                    {previewItem.episodeRange} · {previewItem.playStrategy} ({previewItem.durationFormatted})
                  </div>
                </div>

                <div className="p-3 rounded-xl bg-slate-800/90 border border-slate-700 space-y-1.5">
                  <div className="text-amber-400 text-[11px] font-semibold">高光切入点</div>
                  <div className="font-semibold text-white">{previewItem.highlightCutPoint}</div>
                </div>

                <div className="p-3 rounded-xl bg-slate-800/90 border border-slate-700 space-y-1.5">
                  <div className="text-indigo-300 text-[11px] font-semibold">跳集衔接点时间轴</div>
                  <ul className="space-y-1 text-slate-200 font-mono text-[11px]">
                    {previewItem.jumpCutPositions.map((p, i) => (
                      <li key={i}>• {p}</li>
                    ))}
                  </ul>
                </div>

                <div className="p-3 rounded-xl bg-slate-800/90 border border-slate-700 space-y-1">
                  <div className="text-slate-400 text-[11px]">技术检查报告 ({previewItem.techStatus})</div>
                  <div className="text-slate-200">{previewItem.techReport}</div>
                  <div className="text-[11px] font-mono text-slate-400 truncate pt-1">
                    路径: {previewItem.filePath}
                  </div>
                </div>

                <div className="flex items-center justify-end gap-2 pt-2">
                  <button
                    type="button"
                    onClick={() => {
                      onBatchUpdateManualStatus([previewItem.id], '已淘汰');
                      setPreviewItem(null);
                    }}
                    className="px-3.5 py-2 rounded-xl bg-rose-600 hover:bg-rose-700 text-white font-bold cursor-pointer"
                  >
                    标记淘汰
                  </button>
                  <button
                    type="button"
                    onClick={() => {
                      onBatchUpdateManualStatus([previewItem.id], '已通过');
                      setPreviewItem(null);
                    }}
                    className="px-3.5 py-2 rounded-xl bg-emerald-600 hover:bg-emerald-700 text-white font-bold cursor-pointer"
                  >
                    审核通过
                  </button>
                </div>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Modal 2: 查看来源 (View Source & AI Reasoning Modal) */}
      {sourceModalItem && (
        <div className="fixed inset-0 z-50 bg-slate-950/60 backdrop-blur-xs flex items-center justify-center p-4">
          <div className="bg-white rounded-2xl max-w-lg w-full border border-slate-200 shadow-2xl overflow-hidden animate-in zoom-in-95 duration-150">
            <div className="px-5 py-4 border-b border-slate-100 flex items-center justify-between bg-slate-50">
              <div className="flex items-center gap-2">
                <Layers className="w-4 h-4 text-indigo-600" />
                <h4 className="font-extrabold text-sm text-slate-900">
                  成片来源与跳集规划溯源
                </h4>
              </div>
              <button
                type="button"
                onClick={() => setSourceModalItem(null)}
                className="p-1 rounded-lg text-slate-400 hover:text-slate-700 cursor-pointer"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            <div className="p-5 space-y-3.5 text-xs">
              <div>
                <div className="text-slate-400 text-[11px]">成片文件名</div>
                <div className="font-bold text-slate-900 text-sm mt-0.5">
                  {sourceModalItem.videoName}
                </div>
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div className="p-3 rounded-xl bg-slate-50 border border-slate-200/70">
                  <div className="text-slate-400 text-[11px]">所属原剧与集数范围</div>
                  <div className="font-bold text-slate-800 mt-0.5">
                    《{sourceModalItem.dramaTitle}》 {sourceModalItem.episodeRange}
                  </div>
                </div>
                <div className="p-3 rounded-xl bg-slate-50 border border-slate-200/70">
                  <div className="text-slate-400 text-[11px]">套用通版模板</div>
                  <div className="font-bold text-slate-800 font-mono mt-0.5">
                    {sourceModalItem.templateVersion}
                  </div>
                </div>
              </div>

              <div className="p-3.5 rounded-xl bg-indigo-50/70 border border-indigo-200/80 space-y-1.5">
                <div className="font-bold text-indigo-950 flex items-center gap-1.5">
                  <Sparkles className="w-3.5 h-3.5 text-indigo-600" />
                  <span>AI 剧情高光与跳集规划依据</span>
                </div>
                <p className="text-indigo-900/90 leading-relaxed">
                  {sourceModalItem.sourceReasoning}
                </p>
              </div>

              <div className="p-3 rounded-xl bg-slate-50 border border-slate-200/70 space-y-1">
                <div className="text-slate-500 font-semibold">本地成片物理路径（只读引用原剧合成，未覆盖原片）</div>
                <div className="font-mono text-[11px] text-slate-700 break-all">
                  {sourceModalItem.filePath}
                </div>
              </div>
            </div>

            <div className="px-5 py-3 bg-slate-50 border-t border-slate-100 flex justify-end">
              <button
                type="button"
                onClick={() => setSourceModalItem(null)}
                className="px-4 py-1.5 rounded-xl bg-slate-900 text-white text-xs font-bold cursor-pointer"
              >
                关闭
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
