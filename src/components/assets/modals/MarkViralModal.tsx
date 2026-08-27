import React, { useState, useMemo } from 'react';
import {
  ViralAssetItem,
  ViralRecordItem,
  AccountBusinessItem,
  DramaBusinessItem,
  ProductionBatchCandidateMaterial,
} from '../../../assetsTypes';
import { MOCK_CANDIDATE_PRODUCTION_MATERIALS } from '../../../assetsMockData';
import {
  X,
  Sparkles,
  Search,
  Check,
  Film,
  Calendar,
  Layers,
  Info,
  Clock,
  Play,
  AlertCircle,
  FileVideo,
} from 'lucide-react';

interface MarkViralModalProps {
  isOpen: boolean;
  onClose: () => void;
  accounts: AccountBusinessItem[];
  dramas: DramaBusinessItem[];
  viralAssets: ViralAssetItem[];
  onConfirmMarkViral: (
    candidate: ProductionBatchCandidateMaterial,
    recordData: {
      date: string;
      publishTime: string;
      videoPlayCountText: string;
      dramaPlayCountText?: string;
      revenue?: number;
      dataSource: '青柠平台数据' | '人工录入';
      notes?: string;
    },
    isExistingAsset: boolean
  ) => void;
}

export const MarkViralModal: React.FC<MarkViralModalProps> = ({
  isOpen,
  onClose,
  accounts,
  dramas,
  viralAssets,
  onConfirmMarkViral,
}) => {
  const [selectedDramaName, setSelectedDramaName] = useState<string>('ALL');
  const [selectedAccountName, setSelectedAccountName] = useState<string>('ALL');
  const [materialSearch, setMaterialSearch] = useState('');
  const [selectedCandidate, setSelectedCandidate] = useState<ProductionBatchCandidateMaterial | null>(
    MOCK_CANDIDATE_PRODUCTION_MATERIALS[0] || null
  );

  // Record Form state
  const [recordDate, setRecordDate] = useState<string>(() => new Date().toISOString().slice(0, 10));
  const [publishTime, setPublishTime] = useState<string>('18:30');
  const [videoPlayCountText, setVideoPlayCountText] = useState<string>('38.6万');
  const [hasDramaPlayInput, setHasDramaPlayInput] = useState<boolean>(false);
  const [dramaPlayCountText, setDramaPlayCountText] = useState<string>('72.4万');
  const [hasRevenueInput, setHasRevenueInput] = useState<boolean>(false);
  const [revenueInput, setRevenueInput] = useState<string>('14200');
  const [dataSource, setDataSource] = useState<'青柠平台数据' | '人工录入'>('人工录入');
  const [notes, setNotes] = useState<string>('开篇冲突强烈，黄金前3秒完播留存显著');

  // Check if chosen candidate already exists in viral library by MD5
  const existingAsset = useMemo(() => {
    if (!selectedCandidate) return null;
    return viralAssets.find(v => v.md5 === selectedCandidate.md5) || null;
  }, [selectedCandidate, viralAssets]);

  // Filter candidates
  const filteredCandidates = useMemo(() => {
    return MOCK_CANDIDATE_PRODUCTION_MATERIALS.filter(c => {
      const matchDrama = selectedDramaName === 'ALL' || c.dramaName === selectedDramaName;
      const matchAccount = selectedAccountName === 'ALL' || c.accountName === selectedAccountName;
      const matchSearch =
        !materialSearch ||
        (c.filename || c.name).toLowerCase().includes(materialSearch.toLowerCase()) ||
        c.dramaName.toLowerCase().includes(materialSearch.toLowerCase()) ||
        c.accountName.toLowerCase().includes(materialSearch.toLowerCase()) ||
        c.md5.toLowerCase().includes(materialSearch.toLowerCase());
      return matchDrama && matchAccount && matchSearch;
    });
  }, [selectedDramaName, selectedAccountName, materialSearch]);

  if (!isOpen) return null;

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedCandidate) return;

    const parsedRevenue = hasRevenueInput && revenueInput ? Number(revenueInput) : undefined;

    onConfirmMarkViral(
      selectedCandidate,
      {
        date: recordDate,
        publishTime,
        videoPlayCountText: videoPlayCountText.trim(),
        dramaPlayCountText: hasDramaPlayInput && dramaPlayCountText ? dramaPlayCountText.trim() : undefined,
        revenue: parsedRevenue,
        dataSource,
        notes: notes.trim() || undefined,
      },
      !!existingAsset
    );

    onClose();
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/40 backdrop-blur-xs animate-in fade-in duration-150">
      <div className="bg-white w-full max-w-3xl rounded-2xl shadow-2xl border border-black/[0.08] overflow-hidden flex flex-col max-h-[90vh]">
        {/* Modal Header */}
        <div className="px-6 py-4 border-b border-black/[0.06] flex items-center justify-between bg-slate-50/80 shrink-0">
          <div className="flex items-center gap-2.5">
            <div className="w-8 h-8 rounded-xl bg-[#1A1D2E] text-[#DDFD00] flex items-center justify-center font-bold">
              <Sparkles className="w-4 h-4" />
            </div>
            <div>
              <h3 className="font-bold text-sm text-[#1A1D2E]">标记 / 录入爆款素材</h3>
              <p className="text-xs text-[#64748B]">
                定位产生爆款结果的原始素材视频，将其沉淀至爆款资产库
              </p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="p-1.5 rounded-lg text-slate-400 hover:text-slate-700 hover:bg-black/5 transition-colors cursor-pointer"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Form Body */}
        <form onSubmit={handleSubmit} className="p-6 overflow-y-auto space-y-6 text-xs flex-1">
          {/* Step 1: Select Candidate Raw Video */}
          <div className="space-y-3">
            <div className="flex items-center justify-between">
              <span className="font-bold text-xs text-[#1A1D2E] flex items-center gap-1.5">
                <span className="w-4 h-4 rounded-full bg-[#1A1D2E] text-white text-[10px] flex items-center justify-center font-mono">1</span>
                选择对应的原始素材视频 (支持剧集/账号筛选)
              </span>
              <span className="text-[11px] text-slate-400">
                找到 {filteredCandidates.length} 个候选源视频
              </span>
            </div>

            {/* Filter controls */}
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-2 p-2.5 bg-slate-50 rounded-xl border border-black/[0.04]">
              <div>
                <select
                  value={selectedDramaName}
                  onChange={e => setSelectedDramaName(e.target.value)}
                  className="w-full px-2.5 py-1.5 rounded-lg border border-black/[0.08] bg-white text-xs text-[#1A1D2E] focus:outline-none focus:ring-1 focus:ring-[#1A1D2E]"
                >
                  <option value="ALL">全部剧集</option>
                  {dramas.map(d => (
                    <option key={d.id} value={d.currentName}>
                      {d.currentName}
                    </option>
                  ))}
                </select>
              </div>

              <div>
                <select
                  value={selectedAccountName}
                  onChange={e => setSelectedAccountName(e.target.value)}
                  className="w-full px-2.5 py-1.5 rounded-lg border border-black/[0.08] bg-white text-xs text-[#1A1D2E] focus:outline-none focus:ring-1 focus:ring-[#1A1D2E]"
                >
                  <option value="ALL">全部账号</option>
                  {accounts.map(a => (
                    <option key={a.id} value={a.nickname}>
                      {a.nickname}
                    </option>
                  ))}
                </select>
              </div>

              <div className="relative">
                <Search className="w-3 h-3 text-slate-400 absolute left-2.5 top-2" />
                <input
                  type="text"
                  placeholder="搜索文件名 / MD5..."
                  value={materialSearch}
                  onChange={e => setMaterialSearch(e.target.value)}
                  className="w-full pl-7 pr-2 py-1.5 rounded-lg border border-black/[0.08] bg-white text-xs text-[#1A1D2E] focus:outline-none focus:ring-1 focus:ring-[#1A1D2E]"
                />
              </div>
            </div>

            {/* Candidate Raw Material Cards */}
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-2.5 max-h-48 overflow-y-auto pr-1">
              {filteredCandidates.map(mat => {
                const isChosen = selectedCandidate?.id === mat.id;
                const isAlreadyInLib = viralAssets.some(v => v.md5 === mat.md5);

                return (
                  <div
                    key={mat.id}
                    onClick={() => setSelectedCandidate(mat)}
                    className={`p-3 rounded-xl border transition-all cursor-pointer flex items-center justify-between gap-2 ${
                      isChosen
                        ? 'bg-[#1A1D2E] text-white border-[#1A1D2E] shadow-sm'
                        : 'bg-slate-50/70 hover:bg-slate-100 text-slate-800 border-black/[0.05]'
                    }`}
                  >
                    <div className="space-y-1 min-w-0 pr-2">
                      <div className="flex items-center gap-1.5">
                        <span className="font-bold text-xs truncate" title={mat.filename || mat.name}>
                          {mat.filename || mat.name}
                        </span>
                        {isAlreadyInLib && (
                          <span className={`px-1.5 py-0.2 rounded text-[9px] font-bold shrink-0 ${
                            isChosen ? 'bg-amber-400 text-black' : 'bg-amber-100 text-amber-900'
                          }`}>
                            已在库
                          </span>
                        )}
                      </div>
                      <div className="flex items-center gap-2 text-[10px] opacity-75 font-mono">
                        <span>《{mat.dramaName}》</span>
                        <span>·</span>
                        <span>{mat.durationSeconds}s</span>
                        <span>·</span>
                        <span>{mat.fileSizeMb}MB</span>
                      </div>
                    </div>

                    <div className="shrink-0">
                      {isChosen ? (
                        <div className="w-5 h-5 rounded-full bg-[#DDFD00] text-black flex items-center justify-center">
                          <Check className="w-3.5 h-3.5" />
                        </div>
                      ) : (
                        <div className="w-5 h-5 rounded-full border border-black/20" />
                      )}
                    </div>
                  </div>
                );
              })}
            </div>

            {/* Repeat Material Alert Banner */}
            {existingAsset && (
              <div className="p-3.5 rounded-xl bg-indigo-50/90 border border-indigo-200 text-indigo-900 flex items-start gap-2.5 animate-in fade-in duration-150">
                <Info className="w-4 h-4 text-indigo-600 shrink-0 mt-0.5" />
                <div className="space-y-0.5 text-xs">
                  <div className="font-bold">
                    该素材物理文件已存在于爆款资产库（已有 {existingAsset.viralCount} 次爆款记录）
                  </div>
                  <p className="text-[11px] text-indigo-700 leading-relaxed">
                    系统不会重复复制源文件，本次提交将直接为该素材追加一条新的投放爆款记录。
                  </p>
                </div>
              </div>
            )}
          </div>

          {/* Step 2: Fill in Performance & Record Info */}
          <div className="space-y-3 pt-3 border-t border-black/[0.06]">
            <span className="font-bold text-xs text-[#1A1D2E] flex items-center gap-1.5">
              <span className="w-4 h-4 rounded-full bg-[#1A1D2E] text-white text-[10px] flex items-center justify-center font-mono">2</span>
              填写本次爆款实战投放数据
            </span>

            <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
              <div>
                <label className="block font-semibold text-[#1A1D2E] mb-1">
                  爆款日期 <span className="text-rose-500">*</span>
                </label>
                <input
                  type="date"
                  required
                  value={recordDate}
                  onChange={e => setRecordDate(e.target.value)}
                  className="w-full px-3 py-2 rounded-xl border border-black/[0.1] bg-slate-50/50 font-mono text-xs text-[#1A1D2E]"
                />
              </div>

              <div>
                <label className="block font-semibold text-[#1A1D2E] mb-1">
                  发布时间
                </label>
                <input
                  type="text"
                  value={publishTime}
                  onChange={e => setPublishTime(e.target.value)}
                  placeholder="如：18:30"
                  className="w-full px-3 py-2 rounded-xl border border-black/[0.1] bg-slate-50/50 font-mono text-xs text-[#1A1D2E]"
                />
              </div>

              <div>
                <label className="block font-semibold text-[#1A1D2E] mb-1">
                  数据来源 <span className="text-rose-500">*</span>
                </label>
                <select
                  value={dataSource}
                  onChange={e => setDataSource(e.target.value as any)}
                  className="w-full px-3 py-2 rounded-xl border border-black/[0.1] bg-slate-50/50 text-xs font-semibold text-[#1A1D2E]"
                >
                  <option value="人工录入">人工录入</option>
                  <option value="青柠平台数据">青柠平台数据</option>
                </select>
              </div>
            </div>

            {/* Video Play Count (Required) */}
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              <div>
                <label className="block font-semibold text-[#1A1D2E] mb-1">
                  视频播放量 <span className="text-rose-500">*</span>
                </label>
                <input
                  type="text"
                  required
                  value={videoPlayCountText}
                  onChange={e => setVideoPlayCountText(e.target.value)}
                  placeholder="如：38.6万 或 386000"
                  className="w-full px-3 py-2 rounded-xl border border-black/[0.1] bg-slate-50/50 font-mono font-bold text-[#1A1D2E]"
                />
                <span className="text-[10px] text-slate-400 block mt-1">
                  支持填写万级单位或具体数字
                </span>
              </div>

              {/* Drama Play Count (Optional) */}
              <div>
                <div className="flex items-center justify-between mb-1">
                  <label className="font-semibold text-[#1A1D2E]">
                    剧集播放量 (选填)
                  </label>
                  <label className="flex items-center gap-1 text-[10px] text-slate-500 cursor-pointer">
                    <input
                      type="checkbox"
                      checked={hasDramaPlayInput}
                      onChange={e => setHasDramaPlayInput(e.target.checked)}
                      className="rounded border-slate-300"
                    />
                    <span>有剧集播放数据</span>
                  </label>
                </div>
                <input
                  type="text"
                  disabled={!hasDramaPlayInput}
                  value={dramaPlayCountText}
                  onChange={e => setDramaPlayCountText(e.target.value)}
                  placeholder="如：72.4万"
                  className="w-full px-3 py-2 rounded-xl border border-black/[0.1] bg-slate-50/50 font-mono text-xs text-[#1A1D2E] disabled:opacity-40 disabled:bg-slate-100"
                />
                <span className="text-[10px] text-slate-400 block mt-1">
                  通常青柠等平台具备剧集级播放接口
                </span>
              </div>
            </div>

            {/* Revenue Input (Optional) */}
            <div>
              <div className="flex items-center justify-between mb-1">
                <label className="font-semibold text-[#1A1D2E]">
                  带来真实收益金额 (¥ 选填)
                </label>
                <label className="flex items-center gap-1 text-[10px] text-slate-500 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={hasRevenueInput}
                    onChange={e => setHasRevenueInput(e.target.checked)}
                    className="rounded border-slate-300"
                  />
                  <span>有真实收益数据</span>
                </label>
              </div>
              <input
                type="number"
                disabled={!hasRevenueInput}
                value={revenueInput}
                onChange={e => setRevenueInput(e.target.value)}
                placeholder="若平台无视频级收益，请勿勾选虚构"
                className="w-full px-3 py-2 rounded-xl border border-black/[0.1] bg-slate-50/50 font-mono font-bold text-[#1A1D2E] disabled:opacity-40 disabled:bg-slate-100"
              />
              <span className="text-[10px] text-slate-400 block mt-1">
                若该剧场无视频级收益数据，请留空，系统不会错误显示 ¥0
              </span>
            </div>

            {/* Notes */}
            <div>
              <label className="block font-semibold text-[#1A1D2E] mb-1">
                爆款亮点说明 / 调优经验 (选填)
              </label>
              <textarea
                rows={2}
                value={notes}
                onChange={e => setNotes(e.target.value)}
                placeholder="记录剪辑点、受众反馈或复用建议..."
                className="w-full px-3 py-2 rounded-xl border border-black/[0.1] bg-slate-50/50 text-[#1A1D2E] resize-none text-xs"
              />
            </div>
          </div>

          {/* Modal Footer */}
          <div className="pt-3 border-t border-black/[0.06] flex items-center justify-end gap-2.5 shrink-0">
            <button
              type="button"
              onClick={onClose}
              className="px-4 py-2 rounded-xl text-xs font-semibold text-[#64748B] hover:bg-slate-100 cursor-pointer"
            >
              取消
            </button>
            <button
              type="submit"
              disabled={!selectedCandidate}
              className="flex items-center gap-1.5 px-5 py-2 rounded-xl bg-[#1A1D2E] text-[#DDFD00] text-xs font-bold hover:bg-black/90 active:scale-[0.98] transition-all shadow-xs cursor-pointer disabled:opacity-50"
            >
              <Sparkles className="w-3.5 h-3.5" />
              <span>{existingAsset ? '追加爆款记录' : '确认沉淀为爆款素材'}</span>
            </button>
          </div>
        </form>
      </div>
    </div>
  );
};
