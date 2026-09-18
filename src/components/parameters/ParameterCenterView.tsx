import React, { useEffect, useMemo, useState } from 'react';
import { AlertTriangle, CheckCircle2, Film, RefreshCw, Sliders, SlidersHorizontal, Type, X } from 'lucide-react';
import {
  getV2EngineParameters,
  updateV2EngineParameters,
  type V2EngineParameters,
  type V2InsertionSlot,
} from '../../api/v2EngineParameters';
import { getV2ProductionResources } from '../../api/v2Catalog';
import type { ProductionResourceItem } from '../../assetsTypes';
import { naturalCompare } from '../../utils/naturalCompare';
import { CopyPoolEditor } from './CopyPoolEditor';
import { useDataArea } from '../../hooks/useDataArea';
import { refreshArea } from '../../services/dataHub';

interface ParameterCenterViewProps {
  showToast: (message: string) => void;
}

type InsertionSlotKey = 'midroll' | 'endroll';

/** 一个插片位在界面上的完整状态。 */
interface SlotDraft extends V2InsertionSlot {}

const SLOT_LABEL: Record<InsertionSlotKey, string> = { midroll: '中插', endroll: '尾插' };
const SLOT_PREFIX: Record<InsertionSlotKey, string> = { midroll: '中插', endroll: '尾插' };
const SLOT_HINT: Record<InsertionSlotKey, string> = {
  midroll: '插在爆款视频第 120 秒处（素材太短会自动跳过）。',
  endroll: '接在爆款视频最后。',
};

function formatDuration(seconds?: number): string {
  if (seconds === undefined || seconds === null || !Number.isFinite(seconds) || seconds <= 0) return '时长待探测';
  return `${seconds.toFixed(1)} 秒`;
}

/**
 * 参数中心：只放**用户经常要调的生产参数**。
 * 装完机就不动的系统设置仍留在系统设置页；见 docs/V2参数中心规则.md。
 */
export const ParameterCenterView: React.FC<ParameterCenterViewProps> = ({ showToast }) => {
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [savingCopy, setSavingCopy] = useState(false);
  const [savingInsertion, setSavingInsertion] = useState(false);

  const [blessing, setBlessing] = useState<string[]>([]);
  const [dramaPrompt, setDramaPrompt] = useState<string[]>([]);
  const [copyConfigured, setCopyConfigured] = useState(false);

  const [strategy, setStrategy] = useState<Record<InsertionSlotKey, SlotDraft>>({
    midroll: { enabled: true, mode: 'latest', file: '' },
    endroll: { enabled: true, mode: 'latest', file: '' },
  });
  const [insertionConfigured, setInsertionConfigured] = useState(false);

  const [promotionVideos, setPromotionVideos] = useState<ProductionResourceItem[]>([]);
  const [videosLoading, setVideosLoading] = useState(true);

  const [toastMessage, setToastMessage] = useState<string | null>(null);

  const notify = (message: string) => {
    setToastMessage(message);
    showToast(message);
  };

  const applyParameters = (parameters: V2EngineParameters) => {
    setBlessing(parameters.template_copy.blessing);
    setDramaPrompt(parameters.template_copy.drama_prompt);
    setCopyConfigured(parameters.template_copy.configured);
    setStrategy({
      midroll: { ...parameters.midroll_endroll.strategy.midroll },
      endroll: { ...parameters.midroll_endroll.strategy.endroll },
    });
    setInsertionConfigured(parameters.midroll_endroll.configured);
  };

  // ── 统一数据层接入（刷新大修 · 第 4 步）────────────────────────────
  // 参数中心属于"设一次就不动"的配置类：**打开读一次 + 改完立刻刷**（间隔 0）。
  // 素材清单与资料中心**共用 resourceIndex 区域** —— 同一份数据，30 秒节奏，
  // 绝不因为参数中心而多扫一次素材盘。
  const parametersArea = useDataArea<Awaited<ReturnType<typeof getV2EngineParameters>>>(
    'engineParameters',
    () => getV2EngineParameters(),
  );
  const videosArea = useDataArea<ProductionResourceItem[]>(
    'resourceIndex',
    async () => (await getV2ProductionResources()).items as ProductionResourceItem[],
  );

  useEffect(() => {
    if (!parametersArea.data) {
      if (parametersArea.error) setLoadError(parametersArea.error);
      setLoading(parametersArea.loading);
      return;
    }
    applyParameters(parametersArea.data);
    setLoadError(parametersArea.error);
    setLoading(false);
  }, [parametersArea.data, parametersArea.error, parametersArea.loading]);

  useEffect(() => {
    setVideosLoading(videosArea.loading);
    if (!videosArea.data) return;
    setPromotionVideos(videosArea.data.filter((item) => item.category === 'lead_video'));
  }, [videosArea.data, videosArea.loading]);

  useEffect(() => {
    if (!toastMessage) return;
    const timer = window.setTimeout(() => setToastMessage(null), 3200);
    return () => window.clearTimeout(timer);
  }, [toastMessage]);

  /** 某个插片位可选的素材清单（按序号自然排序）。 */
  const slotVideos = useMemo(() => {
    const grouped: Record<InsertionSlotKey, ProductionResourceItem[]> = { midroll: [], endroll: [] };
    (['midroll', 'endroll'] as InsertionSlotKey[]).forEach((key) => {
      grouped[key] = promotionVideos
        .filter((item) => item.name.startsWith(SLOT_PREFIX[key]))
        .sort((left, right) => naturalCompare(left.name, right.name));
    });
    return grouped;
  }, [promotionVideos]);

  const latestName = (key: InsertionSlotKey): string => {
    const candidates = slotVideos[key];
    return candidates.length ? candidates[candidates.length - 1].name : '';
  };

  const slotFileExists = (key: InsertionSlotKey, file: string): boolean =>
    slotVideos[key].some((item) => item.name === file);

  /** 生成时的成片主轨结构预览。 */
  const structurePreview = useMemo(() => {
    const mid = strategy.midroll.enabled;
    const end = strategy.endroll.enabled;
    const describe = (key: InsertionSlotKey): string => {
      if (strategy[key].mode === 'locked') return strategy[key].file || `${SLOT_LABEL[key]}（尚未选择）`;
      const latest = latestName(key);
      return latest ? `${latest}（最新序号）` : `${SLOT_LABEL[key]}（目录里还没有素材）`;
    };
    if (mid && end) return ['爆款 0–120 秒', describe('midroll'), '爆款剩余部分', describe('endroll')];
    if (mid) return ['爆款 0–120 秒', describe('midroll'), '爆款剩余部分'];
    if (end) return ['爆款整条（不拆段）', describe('endroll')];
    return ['爆款整条（不拆段）', '模板视频循环铺满整条成片'];
  }, [strategy, slotVideos]);

  const blockedReason = useMemo(() => {
    for (const key of ['midroll', 'endroll'] as InsertionSlotKey[]) {
      const slot = strategy[key];
      if (!slot.enabled || slot.mode !== 'locked') continue;
      if (!slot.file) return `${SLOT_LABEL[key]}已选择「指定某一条」，但还没有选具体文件。`;
      if (!slotFileExists(key, slot.file)) {
        return `${SLOT_LABEL[key]}指定的素材「${slot.file}」已经不在引流视频目录里了，请重新选择。`;
      }
    }
    return null;
  }, [strategy, slotVideos]);

  const handleSaveCopy = async () => {
    setSavingCopy(true);
    try {
      applyParameters(await updateV2EngineParameters({ template_copy: { blessing, drama_prompt: dramaPrompt } }));
      notify('文案参数已保存并生效');
    } catch (error) {
      notify(error instanceof Error && error.message ? error.message : '文案参数保存失败。');
    } finally {
      setSavingCopy(false);
    }
  };

  const handleSaveInsertion = async () => {
    if (blockedReason) {
      notify(blockedReason);
      return;
    }
    setSavingInsertion(true);
    try {
      applyParameters(await updateV2EngineParameters({ midroll_endroll: strategy }));
      notify('成片插片参数已保存并生效');
    } catch (error) {
      notify(error instanceof Error && error.message ? error.message : '成片插片参数保存失败。');
    } finally {
      setSavingInsertion(false);
    }
  };

  const updateSlot = (key: InsertionSlotKey, patch: Partial<SlotDraft>) => {
    setStrategy((previous) => ({ ...previous, [key]: { ...previous[key], ...patch } }));
  };

  return (
    <div className="min-h-screen bg-[#F8F9FA] pb-20 text-[#1A1D2E]">
      {/* 顶部标题 */}
      <div className="bg-white border-b border-black/[0.06] sticky top-0 z-30 shadow-2xs">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-3.5">
          <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 rounded-2xl bg-[#1A1D2E] text-[#DDFD00] flex items-center justify-center shadow-xs">
                <SlidersHorizontal className="w-5 h-5" />
              </div>
              <div>
                <div className="flex items-center gap-2">
                  <h1 className="text-base font-black text-[#1A1D2E] tracking-tight">参数中心</h1>
                  <span className="px-2 py-0.5 rounded-full bg-slate-100 text-slate-700 text-[10px] font-bold">
                    常用生产参数
                  </span>
                </div>
                <p className="text-xs text-[#64748B] mt-0.5">
                  这里只放经常要调的生产参数；装完机就不再改动的系统设置仍在「系统设置」页
                </p>
              </div>
            </div>
            <button
              type="button"
              onClick={() => { void refreshArea('engineParameters'); void refreshArea('resourceIndex'); }}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-xl bg-slate-100 hover:bg-slate-200 text-xs font-bold text-[#1A1D2E] transition-colors cursor-pointer"
            >
              <RefreshCw className={`w-3.5 h-3.5 ${loading || videosLoading ? 'animate-spin' : ''}`} />
              <span>重新读取</span>
            </button>
          </div>
        </div>
      </div>

      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 pt-6 space-y-6">
        {loadError && (
          <div className="rounded-2xl bg-rose-50 border border-rose-200/70 px-4 py-3 text-xs text-rose-800 flex items-start gap-2">
            <AlertTriangle className="w-4 h-4 shrink-0 mt-0.5" />
            <div>
              <p className="font-bold">参数读取失败</p>
              <p className="mt-0.5">{loadError}</p>
            </div>
          </div>
        )}

        {/* =====================================================================
            参数组 1：文案
            ===================================================================== */}
        <section className="bg-white rounded-3xl p-6 border border-black/[0.06] shadow-xs space-y-4">
          <div className="flex flex-wrap items-center justify-between gap-3 pb-3 border-b border-black/[0.04]">
            <div className="flex items-center gap-2">
              <Type className="w-4 h-4 text-[#1A1D2E]" />
              <div>
                <h3 className="font-extrabold text-base text-[#1A1D2E]">文案</h3>
                <p className="text-[11px] text-[#64748B] mt-0.5">
                  模板里的两条文字轨道。把某个池清空 = 模板里不要那条轨道。
                </p>
              </div>
            </div>
            <div className="flex items-center gap-2">
              {copyConfigured ? (
                <span className="px-2 py-0.5 rounded-full bg-emerald-50 text-emerald-700 text-[10px] font-bold border border-emerald-200/60">
                  已自定义
                </span>
              ) : (
                <span className="px-2 py-0.5 rounded-full bg-slate-100 text-slate-600 text-[10px] font-bold">
                  正在使用内置默认文案
                </span>
              )}
              <button
                type="button"
                disabled={savingCopy || loading}
                onClick={() => void handleSaveCopy()}
                className="px-3.5 py-1.5 rounded-xl bg-[#1A1D2E] text-[#DDFD00] hover:bg-black disabled:opacity-40 disabled:cursor-not-allowed text-xs font-extrabold transition-colors cursor-pointer"
              >
                {savingCopy ? '保存中…' : '保存并生效'}
              </button>
            </div>
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
            <div className="space-y-3">
              <div className="flex items-center gap-2">
                <span className="font-bold text-xs text-[#1A1D2E]">祝福语</span>
                <span className="text-[10px] text-[#64748B] font-mono">T10_TEXT_BLESSING</span>
                <button
                  type="button"
                  onClick={() => setBlessing([])}
                  className="ml-auto text-[11px] text-[#64748B] hover:text-rose-600 font-bold cursor-pointer"
                >
                  清空（不要这条轨道）
                </button>
              </div>
              <CopyPoolEditor
                items={blessing}
                onChange={setBlessing}
                addLabel="新增祝福语"
                addPlaceholder="例如：愿您平安喜乐"
                emptyHint="现在是空池：模板生成时不会写入祝福语文案轨道。"
                onNotify={notify}
              />
            </div>

            <div className="space-y-3">
              <div className="flex items-center gap-2">
                <span className="font-bold text-xs text-[#1A1D2E]">引导语</span>
                <span className="text-[10px] text-[#64748B] font-mono">T11_TEXT_DRAMA_PROMPT</span>
                <button
                  type="button"
                  onClick={() => setDramaPrompt([])}
                  className="ml-auto text-[11px] text-[#64748B] hover:text-rose-600 font-bold cursor-pointer"
                >
                  清空（不要这条轨道）
                </button>
              </div>
              <CopyPoolEditor
                items={dramaPrompt}
                onChange={setDramaPrompt}
                addLabel="新增引导语"
                addPlaceholder="例如：左下角免费看全集"
                emptyHint="现在是空池：模板生成时不会写入引导语文案轨道。"
                onNotify={notify}
              />
            </div>
          </div>
        </section>

        {/* =====================================================================
            参数组 2：成片插片（中插 / 尾插）
            ===================================================================== */}
        <section className="bg-white rounded-3xl p-6 border border-black/[0.06] shadow-xs space-y-4">
          <div className="flex flex-wrap items-center justify-between gap-3 pb-3 border-b border-black/[0.04]">
            <div className="flex items-center gap-2">
              <Film className="w-4 h-4 text-[#1A1D2E]" />
              <div>
                <h3 className="font-extrabold text-base text-[#1A1D2E]">成片插片（中插 / 尾插）</h3>
                <p className="text-[11px] text-[#64748B] mt-0.5">
                  素材取自「生成资源 / 引流视频」。这里设的是**全局默认**，生产任务上可以单独覆盖。
                </p>
              </div>
            </div>
            <div className="flex items-center gap-2">
              {insertionConfigured ? (
                <span className="px-2 py-0.5 rounded-full bg-emerald-50 text-emerald-700 text-[10px] font-bold border border-emerald-200/60">
                  已自定义
                </span>
              ) : (
                <span className="px-2 py-0.5 rounded-full bg-slate-100 text-slate-600 text-[10px] font-bold">
                  正在使用默认：两条都要
                </span>
              )}
              <button
                type="button"
                disabled={savingInsertion || loading || Boolean(blockedReason)}
                onClick={() => void handleSaveInsertion()}
                className="px-3.5 py-1.5 rounded-xl bg-[#1A1D2E] text-[#DDFD00] hover:bg-black disabled:opacity-40 disabled:cursor-not-allowed text-xs font-extrabold transition-colors cursor-pointer"
              >
                {savingInsertion ? '保存中…' : '保存并生效'}
              </button>
            </div>
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
            {(['midroll', 'endroll'] as InsertionSlotKey[]).map((key) => {
              const slot = strategy[key];
              const videos = slotVideos[key];
              const latest = latestName(key);
              return (
                <div key={key} className="rounded-2xl border border-black/[0.06] bg-[#F8FAFC] p-4 space-y-3">
                  <div className="flex items-center gap-2">
                    <span className="font-extrabold text-sm text-[#1A1D2E]">{SLOT_LABEL[key]}</span>
                    <span className="text-[11px] text-[#64748B]">{SLOT_HINT[key]}</span>
                    <label className="ml-auto flex items-center gap-1.5 cursor-pointer select-none">
                      <input
                        type="checkbox"
                        checked={slot.enabled}
                        onChange={(event) => updateSlot(key, { enabled: event.target.checked })}
                        className="w-3.5 h-3.5 accent-[#1A1D2E] cursor-pointer"
                      />
                      <span className="text-xs font-bold text-[#1A1D2E]">{slot.enabled ? '要' : '不要'}</span>
                    </label>
                  </div>

                  {slot.enabled && (
                    <>
                      <div className="flex flex-wrap items-center gap-3 text-xs">
                        <label className="flex items-center gap-1.5 cursor-pointer">
                          <input
                            type="radio"
                            name={`${key}-mode`}
                            checked={slot.mode === 'latest'}
                            onChange={() => updateSlot(key, { mode: 'latest', file: '' })}
                            className="w-3.5 h-3.5 accent-[#1A1D2E] cursor-pointer"
                          />
                          <span className="font-bold text-[#1A1D2E]">跟随最新序号</span>
                        </label>
                        <label className="flex items-center gap-1.5 cursor-pointer">
                          <input
                            type="radio"
                            name={`${key}-mode`}
                            checked={slot.mode === 'locked'}
                            onChange={() => updateSlot(key, { mode: 'locked', file: slot.file || latest })}
                            className="w-3.5 h-3.5 accent-[#1A1D2E] cursor-pointer"
                          />
                          <span className="font-bold text-[#1A1D2E]">指定某一条</span>
                        </label>
                      </div>

                      {slot.mode === 'latest' ? (
                        <p className="text-[11px] text-[#64748B]">
                          每次生成时重新挑目录里序号最大的一条。当前会用到：
                          <strong className="text-[#1A1D2E]">
                            {videosLoading ? '读取中…' : latest || '目录里还没有素材'}
                          </strong>
                        </p>
                      ) : (
                        <div className="space-y-1.5">
                          <select
                            value={slotFileExists(key, slot.file) ? slot.file : ''}
                            onChange={(event) => updateSlot(key, { file: event.target.value })}
                            className="w-full px-2.5 py-1.5 bg-white border border-black/[0.08] rounded-xl text-xs font-semibold focus:outline-none cursor-pointer"
                          >
                            <option value="">请选择一条素材</option>
                            {videos.map((item) => (
                              <option key={item.id} value={item.name}>
                                {item.name} · {formatDuration(item.durationSeconds)} · {item.fileSizeMb} MB
                              </option>
                            ))}
                          </select>
                          {!videosLoading && videos.length === 0 && (
                            <p className="text-[11px] text-amber-700">
                              引流视频目录里没有以「{SLOT_PREFIX[key]}」开头的素材。
                            </p>
                          )}
                          {slot.file && !slotFileExists(key, slot.file) && (
                            <p className="text-[11px] text-rose-700">
                              之前指定的「{slot.file}」已经不在了，请重新选择。
                            </p>
                          )}
                        </div>
                      )}
                    </>
                  )}

                  {!slot.enabled && (
                    <p className="rounded-xl bg-white border border-black/[0.06] px-3 py-2.5 text-[11px] text-[#64748B]">
                      {key === 'midroll'
                        ? '成片里不插中插：爆款视频整条保留，不拆成两段。'
                        : '成片结尾不接尾插。'}
                    </p>
                  )}
                </div>
              );
            })}
          </div>

          {blockedReason && (
            <div className="rounded-2xl bg-rose-50 border border-rose-200/70 px-4 py-3 text-xs text-rose-800 flex items-start gap-2">
              <AlertTriangle className="w-4 h-4 shrink-0 mt-0.5" />
              <span>{blockedReason}</span>
            </div>
          )}

          <div className="rounded-2xl bg-[#1A1D2E] px-4 py-3 text-white space-y-1.5">
            <p className="text-[11px] font-bold text-[#DDFD00]">按当前设置，成片主轨会是：</p>
            <div className="flex flex-wrap items-center gap-1.5 text-xs">
              {structurePreview.map((step, index) => (
                <React.Fragment key={`${step}-${index}`}>
                  {index > 0 && <span className="text-slate-500">→</span>}
                  <span className="px-2.5 py-1 rounded-lg bg-white/10 border border-white/10 font-bold break-all">{step}</span>
                </React.Fragment>
              ))}
            </div>
            {!strategy.midroll.enabled && !strategy.endroll.enabled && (
              <p className="text-[11px] text-amber-300">
                ⚠️ 中插和尾插都不要时，成片主轨只剩爆款视频一条；模板视频会循环铺满整条成片，最终画面效果尚未实机确认。
              </p>
            )}
            {strategy.midroll.enabled && slotVideos.midroll.length > 0 && (
              <p className="text-[11px] text-slate-400">
                中插插在爆款第 120 秒处；爆款素材短于 120 秒时系统会自动跳过中插。
              </p>
            )}
          </div>
        </section>

        {/* =====================================================================
            后续参数位（先占位，说明"还没做"，不摆假控件）
            ===================================================================== */}
        <section className="rounded-3xl border border-dashed border-black/[0.12] bg-white/60 px-6 py-5">
          <div className="flex items-center gap-2">
            <Sliders className="w-4 h-4 text-[#64748B]" />
            <h3 className="font-extrabold text-sm text-[#64748B]">后续参数（还没做）</h3>
          </div>
          <p className="mt-1.5 text-[11px] text-[#64748B] leading-relaxed">
            超时时间、清理保留期、画面参数、剪映素材更新入口等，都要先确认"到底要不要可调"再往这里加。
            每确认一个就加一栏，不做提前搭建。
          </p>
        </section>
      </main>

      {toastMessage && (
        <div className="fixed bottom-6 right-6 z-50 animate-in fade-in slide-in-from-bottom-3 duration-200">
          <div className="bg-[#1A1D2E] text-white px-4 py-3 rounded-2xl shadow-2xl border border-white/10 flex items-center gap-3 text-xs max-w-md">
            <CheckCircle2 className="w-4 h-4 text-[#DDFD00] shrink-0" />
            <span className="font-medium">{toastMessage}</span>
            <button
              type="button"
              onClick={() => setToastMessage(null)}
              className="text-slate-400 hover:text-white p-1 ml-auto cursor-pointer"
            >
              <X className="w-3.5 h-3.5" />
            </button>
          </div>
        </div>
      )}
    </div>
  );
};
