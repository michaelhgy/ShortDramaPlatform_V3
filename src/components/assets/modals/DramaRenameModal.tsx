import React, { useState, useEffect } from 'react';
import { DramaBusinessItem } from '../../../assetsTypes';
import { X, Film, History, Plus, Trash2, Save, ArrowRight, RotateCcw, AlertCircle, Check } from 'lucide-react';

interface DramaRenameModalProps {
  isOpen: boolean;
  onClose: () => void;
  drama: DramaBusinessItem | null;
  theaters: { id: string; name: string }[];
  lockedTheaterName?: string;
  onSave: (
    updated: {
      currentName: string;
      historyNames: string[];
      theaterName: string;
      theaterId: string;
      isUsedInBusiness?: boolean;
    },
    id?: string
  ) => void;
  onDelete?: (id: string, name: string) => void;
}

export const DramaRenameModal: React.FC<DramaRenameModalProps> = ({
  isOpen,
  onClose,
  drama,
  theaters,
  lockedTheaterName,
  onSave,
  onDelete,
}) => {
  const [newCurrentName, setNewCurrentName] = useState('');
  const [theaterName, setTheaterName] = useState('九州剧场');
  const [historyNamesList, setHistoryNamesList] = useState<string[]>([]);
  const [manualHistoryInput, setManualHistoryInput] = useState('');

  useEffect(() => {
    if (drama) {
      setNewCurrentName(drama.currentName);
      setTheaterName(drama.theaterName);
      setHistoryNamesList([...drama.historyNames]);
      setManualHistoryInput('');
    } else {
      setNewCurrentName('');
      setTheaterName(lockedTheaterName || theaters[0]?.name || '九州剧场');
      setHistoryNamesList([]);
      setManualHistoryInput('');
    }
  }, [drama, theaters, isOpen, lockedTheaterName]);

  if (!isOpen) return null;

  const handleAddManualHistoryName = () => {
    if (!manualHistoryInput.trim()) return;
    const name = manualHistoryInput.trim();
    if (!historyNamesList.includes(name) && name !== newCurrentName) {
      setHistoryNamesList(prev => [...prev, name]);
    }
    setManualHistoryInput('');
  };

  const handleRemoveHistoryName = (indexToRemove: number) => {
    setHistoryNamesList(prev => prev.filter((_, idx) => idx !== indexToRemove));
  };

  // Switch a history name to become the current active drama name
  const handleSwitchHistoryToCurrent = (histName: string) => {
    const prevCurrent = newCurrentName.trim();
    // New current is the chosen history name
    setNewCurrentName(histName);
    // Replace chosen history name with previous current name in list if prevCurrent is valid
    setHistoryNamesList(prev => {
      const filtered = prev.filter(h => h !== histName);
      if (prevCurrent && !filtered.includes(prevCurrent)) {
        return [prevCurrent, ...filtered];
      }
      return filtered;
    });
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!newCurrentName.trim()) return;

    const trimmedNew = newCurrentName.trim();
    let finalHistoryList = [...historyNamesList];

    // If editing an existing drama and currentName changed:
    if (drama && drama.currentName !== trimmedNew) {
      // Old current name automatically enters historyNames
      if (!finalHistoryList.includes(drama.currentName)) {
        finalHistoryList.unshift(drama.currentName);
      }
    }

    // Remove duplicates and ensure new currentName is not in historyNames
    finalHistoryList = finalHistoryList.filter(h => h !== trimmedNew);

    const matchedTheater = theaters.find(t => t.name === theaterName) || theaters[0];

    onSave({
      currentName: trimmedNew,
      historyNames: finalHistoryList,
      theaterName,
      theaterId: matchedTheater?.id || 'th-01',
      isUsedInBusiness: drama ? drama.isUsedInBusiness : false,
    }, drama ? drama.id : undefined);

    onClose();
  };

  const isNameChanged = drama && drama.currentName !== newCurrentName.trim() && newCurrentName.trim().length > 0;
  const isDeletable = drama && !drama.isUsedInBusiness;

  const handleDelete = () => {
    if (!drama || !onDelete) return;
    if (!isDeletable) return;
    onDelete(drama.id, drama.currentName);
    onClose();
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/40 backdrop-blur-xs animate-in fade-in duration-150">
      <div className="bg-white w-full max-w-lg rounded-2xl shadow-2xl border border-black/[0.08] overflow-hidden flex flex-col max-h-[90vh]">
        {/* Header */}
        <div className="px-6 py-4 border-b border-black/[0.06] flex items-center justify-between bg-slate-50/80">
          <div className="flex items-center gap-2.5">
            <div className="w-8 h-8 rounded-xl bg-[#1A1D2E] text-[#DDFD00] flex items-center justify-center">
              <Film className="w-4 h-4" />
            </div>
            <div>
              <h3 className="font-bold text-sm text-[#1A1D2E]">
                {drama ? '剧名维护与历史剧名管理' : '新增剧集档案'}
              </h3>
              <p className="text-xs text-[#64748B]">
                {drama ? '修改剧名将自动沉淀历史剧名，支持将历史剧名一键切换为当前生效剧名' : '录入新剧集基础名称及所属剧场'}
              </p>
            </div>
          </div>
          <button onClick={onClose} className="p-1.5 rounded-lg text-slate-400 hover:text-slate-700 hover:bg-black/5 transition-colors cursor-pointer">
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Body */}
        <form onSubmit={handleSubmit} className="p-6 overflow-y-auto space-y-4 text-xs">
          {/* Theater */}
          <div>
            <label className="block font-semibold text-[#1A1D2E] mb-1.5">
              所属剧场 <span className="text-rose-500">*</span>
            </label>
            <select
              value={theaterName}
              onChange={e => setTheaterName(e.target.value)}
              disabled={Boolean(lockedTheaterName)}
              className="w-full px-3 py-2 rounded-xl border border-black/[0.1] bg-slate-50/50 focus:bg-white focus:outline-none focus:ring-2 focus:ring-[#1A1D2E]/20 text-xs font-semibold text-[#1A1D2E]"
            >
              {theaters.map(t => (
                <option key={t.id} value={t.name}>
                  {t.name}
                </option>
              ))}
            </select>
          </div>

          {/* Current Drama Name */}
          <div>
            <label className="block font-semibold text-[#1A1D2E] mb-1.5 flex items-center justify-between">
              <span>当前生效剧名 <span className="text-rose-500">*</span></span>
              <span className="text-[10px] text-slate-400 font-normal">全系统统一展示此名称</span>
            </label>
            <input
              type="text"
              required
              placeholder="例如：重返八零：我成了首富"
              value={newCurrentName}
              onChange={e => setNewCurrentName(e.target.value)}
              className="w-full px-3.5 py-2.5 rounded-xl border border-black/[0.1] bg-slate-50/50 focus:bg-white focus:outline-none focus:ring-2 focus:ring-[#1A1D2E]/20 text-xs font-bold text-[#1A1D2E]"
            />
          </div>

          {/* Auto Rename Flow Notice */}
          {isNameChanged && (
            <div className="p-3 rounded-xl bg-amber-50/80 border border-amber-200/80 flex items-start gap-2.5">
              <History className="w-4 h-4 text-amber-700 mt-0.5 shrink-0" />
              <div className="text-[11px] text-amber-900 leading-relaxed">
                <span className="font-semibold">改名自动沉淀提示：</span>
                保存后，原剧名 <code className="px-1.5 py-0.5 rounded bg-amber-100/90 font-bold text-amber-900">{drama.currentName}</code> 将自动转入历史剧名列表，支持通过历史名搜索召回。
              </div>
            </div>
          )}

          {/* History Drama Names Management */}
          <div className="p-3.5 rounded-xl bg-slate-50 border border-black/[0.06] space-y-3">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-1.5">
                <History className="w-3.5 h-3.5 text-slate-500" />
                <span className="font-bold text-[#1A1D2E]">历史剧名记录 ({historyNamesList.length})</span>
              </div>
              <span className="text-[10px] text-[#64748B]">可一键设为当前剧名，或删除错误历史名</span>
            </div>

            {/* List of history names */}
            {historyNamesList.length > 0 ? (
              <div className="space-y-1.5 max-h-40 overflow-y-auto pr-1">
                {historyNamesList.map((hist, idx) => (
                  <div
                    key={idx}
                    className="flex items-center justify-between p-2 rounded-lg bg-white border border-black/[0.04] group hover:border-black/10 transition-colors"
                  >
                    <span className="text-slate-700 font-medium truncate pr-2">{hist}</span>
                    <div className="flex items-center gap-1 shrink-0">
                      <button
                        type="button"
                        onClick={() => handleSwitchHistoryToCurrent(hist)}
                        className="flex items-center gap-1 px-2 py-0.5 rounded bg-slate-100 hover:bg-slate-200 text-slate-700 text-[10px] font-semibold transition-colors cursor-pointer"
                        title="将此历史剧名重新设为当前生效剧名"
                      >
                        <RotateCcw className="w-3 h-3 text-slate-500" />
                        <span>设为当前</span>
                      </button>
                      <button
                        type="button"
                        onClick={() => handleRemoveHistoryName(idx)}
                        className="p-1 rounded-md text-slate-400 hover:text-rose-600 hover:bg-rose-50 transition-colors cursor-pointer"
                        title="删除此项错误历史剧名"
                      >
                        <Trash2 className="w-3.5 h-3.5" />
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <div className="py-3 text-center text-slate-400 text-[11px]">
                暂无历史剧名记录
              </div>
            )}

            {/* Add manual history name */}
            <div className="flex items-center gap-2 pt-1 border-t border-black/[0.04]">
              <input
                type="text"
                placeholder="手动补充历史剧名/别名..."
                value={manualHistoryInput}
                onChange={e => setManualHistoryInput(e.target.value)}
                onKeyDown={e => {
                  if (e.key === 'Enter') {
                    e.preventDefault();
                    handleAddManualHistoryName();
                  }
                }}
                className="flex-1 px-3 py-1.5 rounded-lg border border-black/[0.08] bg-white text-xs text-[#1A1D2E]"
              />
              <button
                type="button"
                onClick={handleAddManualHistoryName}
                className="px-3 py-1.5 rounded-lg bg-slate-200 hover:bg-slate-300 text-[#1A1D2E] font-semibold text-xs transition-colors cursor-pointer"
              >
                添加
              </button>
            </div>
          </div>

          {/* Validation note for drama deletion */}
          {drama && (
            <div className="pt-1">
              {!isDeletable ? (
                <div className="p-2.5 rounded-xl bg-slate-50 border border-black/[0.06] flex items-center gap-2 text-[11px] text-[#64748B]">
                  <AlertCircle className="w-4 h-4 text-slate-400 shrink-0" />
                  <span>该剧集已关联生产物料、原片库或投放记录，系统保护锁定，禁止删除。</span>
                </div>
              ) : (
                <div className="p-2.5 rounded-xl bg-rose-50/60 border border-rose-100 flex items-center gap-2 text-[11px] text-rose-700">
                  <AlertCircle className="w-4 h-4 text-rose-500 shrink-0" />
                  <span>当前剧集暂无真实业务关联，支持安全删除。</span>
                </div>
              )}
            </div>
          )}

          <div className="pt-3 border-t border-black/[0.06] flex items-center justify-between gap-2.5">
            <div>
              {drama && onDelete && (
                <button
                  type="button"
                  disabled={!isDeletable}
                  onClick={handleDelete}
                  className={`flex items-center gap-1 px-3 py-2 rounded-xl text-xs font-semibold transition-all cursor-pointer ${
                    isDeletable
                      ? 'text-rose-600 hover:bg-rose-50 active:scale-95'
                      : 'text-slate-300 cursor-not-allowed opacity-60'
                  }`}
                  title={!isDeletable ? '已关联业务，不可删除' : '删除该剧集档案'}
                >
                  <Trash2 className="w-3.5 h-3.5" />
                  <span>删除剧集</span>
                </button>
              )}
            </div>

            <div className="flex items-center gap-2.5">
              <button
                type="button"
                onClick={onClose}
                className="px-4 py-2 rounded-xl text-xs font-semibold text-[#64748B] hover:bg-slate-100 cursor-pointer"
              >
                取消
              </button>
              <button
                type="submit"
                className="flex items-center gap-1.5 px-5 py-2 rounded-xl bg-[#1A1D2E] text-[#DDFD00] text-xs font-bold hover:bg-black/90 active:scale-[0.98] transition-all shadow-xs cursor-pointer"
              >
                <Save className="w-3.5 h-3.5" />
                <span>{drama ? '保存剧名配置' : '确认新增'}</span>
              </button>
            </div>
          </div>
        </form>
      </div>
    </div>
  );
};
