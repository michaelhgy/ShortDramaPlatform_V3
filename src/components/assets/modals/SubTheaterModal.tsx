import React, { useState, useEffect } from 'react';
import { SubTheaterBusinessItem, TheaterBusinessItem } from '../../../assetsTypes';
import { X, GitFork, Save, Trash2, AlertCircle, Lock } from 'lucide-react';

interface SubTheaterModalProps {
  isOpen: boolean;
  onClose: () => void;
  subTheater: SubTheaterBusinessItem | null;
  theaters: TheaterBusinessItem[];
  defaultTheaterId?: string;
  onSave: (subTheaterData: Omit<SubTheaterBusinessItem, 'id'>, id?: string) => void;
  onDelete?: (id: string, name: string) => void;
}

export const SubTheaterModal: React.FC<SubTheaterModalProps> = ({
  isOpen,
  onClose,
  subTheater,
  theaters,
  defaultTheaterId,
  onSave,
  onDelete,
}) => {
  const [name, setName] = useState('');
  const [theaterId, setTheaterId] = useState(defaultTheaterId || theaters[0]?.id || 'th-01');
  const [isCommissionOverridden, setIsCommissionOverridden] = useState(false);
  const [customCommissionRate, setCustomCommissionRate] = useState(70);
  const [status, setStatus] = useState<'启用' | '停用'>('启用');

  const selectedTheater = theaters.find(t => t.id === theaterId) || theaters[0];
  const isTheaterLocked = subTheater && (subTheater.boundAccountsCount || 0) > 0;

  useEffect(() => {
    if (subTheater) {
      setName(subTheater.name);
      setTheaterId(subTheater.theaterId);
      setIsCommissionOverridden(subTheater.isCommissionOverridden);
      setCustomCommissionRate(subTheater.commissionRate);
      setStatus(subTheater.status);
    } else {
      setName('');
      setTheaterId(defaultTheaterId || theaters[0]?.id || 'th-01');
      setIsCommissionOverridden(false);
      setCustomCommissionRate(selectedTheater?.defaultCommissionRate || 70);
      setStatus('启用');
    }
  }, [subTheater, defaultTheaterId, theaters, isOpen]);

  if (!isOpen) return null;

  const currentEffectiveRate = isCommissionOverridden
    ? customCommissionRate
    : (selectedTheater?.defaultCommissionRate || 70);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!name.trim()) return;

    onSave({
      name: name.trim(),
      theaterId: selectedTheater.id,
      theaterName: selectedTheater.name,
      commissionRate: Number(currentEffectiveRate),
      isCommissionOverridden,
      status,
      boundAccountsCount: subTheater?.boundAccountsCount || 0,
      isUsedInBusiness: subTheater ? subTheater.isUsedInBusiness : false,
    }, subTheater ? subTheater.id : undefined);

    onClose();
  };

  const isDeletable = subTheater && !subTheater.isUsedInBusiness && (subTheater.boundAccountsCount || 0) === 0;

  const handleDelete = () => {
    if (!subTheater || !onDelete) return;
    if (!isDeletable) return;
    onDelete(subTheater.id, subTheater.name);
    onClose();
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/40 backdrop-blur-xs animate-in fade-in duration-150">
      <div className="bg-white w-full max-w-md rounded-2xl shadow-2xl border border-black/[0.08] overflow-hidden flex flex-col">
        <div className="px-6 py-4 border-b border-black/[0.06] flex items-center justify-between bg-slate-50/80">
          <div className="flex items-center gap-2.5">
            <div className="w-8 h-8 rounded-xl bg-[#1A1D2E] text-[#DDFD00] flex items-center justify-center">
              <GitFork className="w-4 h-4" />
            </div>
            <div>
              <h3 className="font-bold text-sm text-[#1A1D2E]">
                {subTheater ? '编辑子剧场' : '新增子剧场'}
              </h3>
              <p className="text-xs text-[#64748B]">
                配置子剧场名称及分成继承策略
              </p>
            </div>
          </div>
          <button onClick={onClose} className="p-1.5 rounded-lg text-slate-400 hover:text-slate-700 hover:bg-black/5 transition-colors cursor-pointer">
            <X className="w-4 h-4" />
          </button>
        </div>

        <form onSubmit={handleSubmit} className="p-6 space-y-4 text-xs">
          {/* Theater Selection (with locking rule) */}
          <div>
            <label className="block font-semibold text-[#1A1D2E] mb-1.5 flex items-center justify-between">
              <span>所属剧场 <span className="text-rose-500">*</span></span>
              {isTheaterLocked && (
                <span className="text-[10px] text-amber-700 font-semibold flex items-center gap-1">
                  <Lock className="w-3 h-3" /> 已锁定所属剧场
                </span>
              )}
            </label>
            <select
              value={theaterId}
              disabled={isTheaterLocked}
              onChange={e => setTheaterId(e.target.value)}
              className={`w-full px-3 py-2 rounded-xl border text-xs font-semibold ${
                isTheaterLocked
                  ? 'bg-slate-100/90 text-slate-500 border-black/[0.06] cursor-not-allowed'
                  : 'bg-slate-50/50 text-[#1A1D2E] border-black/[0.1] focus:bg-white focus:outline-none focus:ring-2 focus:ring-[#1A1D2E]/20'
              }`}
            >
              {theaters.map(t => (
                <option key={t.id} value={t.id}>
                  {t.name} (默认分成 {t.defaultCommissionRate}%)
                </option>
              ))}
            </select>
            {isTheaterLocked && (
              <p className="text-[10px] text-amber-800 bg-amber-50 border border-amber-200/60 p-1.5 rounded-lg mt-1.5 leading-relaxed">
                提示：已有 {subTheater.boundAccountsCount} 个账号使用该子剧场，因此不能改变所属剧场。其他字段仍可正常修改。
              </p>
            )}
          </div>

          <div>
            <label className="block font-semibold text-[#1A1D2E] mb-1.5">
              子剧场名称 <span className="text-rose-500">*</span>
            </label>
            <input
              type="text"
              required
              placeholder="例如：云展品读 / 碧空短剧"
              value={name}
              onChange={e => setName(e.target.value)}
              className="w-full px-3 py-2 rounded-xl border border-black/[0.1] bg-slate-50/50 focus:bg-white focus:outline-none focus:ring-2 focus:ring-[#1A1D2E]/20 text-xs font-semibold text-[#1A1D2E]"
            />
          </div>

          {/* Commission Inheritance vs Override */}
          <div className="p-3 rounded-xl bg-slate-50 border border-black/[0.06] space-y-2.5">
            <div className="flex items-center justify-between">
              <span className="font-semibold text-[#1A1D2E]">分成比例策略</span>
              <span className="font-mono font-bold text-emerald-700 text-xs">
                当前生效: {currentEffectiveRate}%
              </span>
            </div>

            <div className="space-y-2">
              <label className="flex items-center gap-2 cursor-pointer">
                <input
                  type="radio"
                  name="commissionMode"
                  checked={!isCommissionOverridden}
                  onChange={() => setIsCommissionOverridden(false)}
                  className="w-3.5 h-3.5 text-[#1A1D2E]"
                />
                <span className="text-slate-700">
                  继承所属剧场默认分成 ({selectedTheater?.defaultCommissionRate || 70}%)
                </span>
              </label>

              <label className="flex items-center gap-2 cursor-pointer">
                <input
                  type="radio"
                  name="commissionMode"
                  checked={isCommissionOverridden}
                  onChange={() => setIsCommissionOverridden(true)}
                  className="w-3.5 h-3.5 text-[#1A1D2E]"
                />
                <span className="text-slate-700 font-medium">
                  特殊独立分成 (手动修改覆盖)
                </span>
              </label>
            </div>

            {isCommissionOverridden && (
              <div className="pt-2 pl-5 flex items-center gap-2 animate-in fade-in">
                <span className="text-slate-600 font-medium">自定义分成:</span>
                <div className="relative w-24">
                  <input
                    type="number"
                    min={0}
                    max={100}
                    value={customCommissionRate}
                    onChange={e => setCustomCommissionRate(Number(e.target.value))}
                    className="w-full px-2.5 py-1 rounded-lg border border-black/[0.1] bg-white text-xs font-mono font-bold text-[#1A1D2E]"
                  />
                  <span className="absolute right-2 top-1 text-slate-400 font-mono">%</span>
                </div>
              </div>
            )}
          </div>

          <div>
            <label className="block font-semibold text-[#1A1D2E] mb-1.5">
              启用状态
            </label>
            <div className="flex items-center gap-2">
              <button
                type="button"
                onClick={() => setStatus('启用')}
                className={`flex-1 py-1.5 rounded-xl text-center text-xs font-semibold border transition-all cursor-pointer ${
                  status === '启用'
                    ? 'bg-emerald-600 text-white font-bold border-emerald-600 shadow-2xs'
                    : 'bg-slate-50 text-slate-600 border-black/[0.06] hover:bg-slate-100'
                }`}
              >
                启用
              </button>
              <button
                type="button"
                onClick={() => setStatus('停用')}
                className={`flex-1 py-1.5 rounded-xl text-center text-xs font-semibold border transition-all cursor-pointer ${
                  status === '停用'
                    ? 'bg-slate-600 text-white font-bold border-slate-600 shadow-2xs'
                    : 'bg-slate-50 text-slate-600 border-black/[0.06] hover:bg-slate-100'
                }`}
              >
                停用
              </button>
            </div>
          </div>

          {/* Validation note for subtheater */}
          {subTheater && (
            <div className="pt-1">
              {!isDeletable ? (
                <div className="p-2.5 rounded-xl bg-slate-50 border border-black/[0.06] flex items-center gap-2 text-[11px] text-[#64748B]">
                  <AlertCircle className="w-4 h-4 text-slate-400 shrink-0" />
                  <span>
                    已有 {subTheater.boundAccountsCount || 0} 个账号绑定此子剧场，系统保护锁定，禁止删除。
                  </span>
                </div>
              ) : (
                <div className="p-2.5 rounded-xl bg-rose-50/60 border border-rose-100 flex items-center gap-2 text-[11px] text-rose-700">
                  <AlertCircle className="w-4 h-4 text-rose-500 shrink-0" />
                  <span>当前子剧场暂无账号绑定，支持安全删除。</span>
                </div>
              )}
            </div>
          )}

          <div className="pt-3 border-t border-black/[0.06] flex items-center justify-between gap-2.5">
            <div>
              {subTheater && onDelete && (
                <button
                  type="button"
                  disabled={!isDeletable}
                  onClick={handleDelete}
                  className={`flex items-center gap-1 px-3 py-2 rounded-xl text-xs font-semibold transition-all cursor-pointer ${
                    isDeletable
                      ? 'text-rose-600 hover:bg-rose-50 active:scale-95'
                      : 'text-slate-300 cursor-not-allowed opacity-60'
                  }`}
                  title={!isDeletable ? '已有账号绑定，不可删除' : '删除该子剧场'}
                >
                  <Trash2 className="w-3.5 h-3.5" />
                  <span>删除子剧场</span>
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
                <span>{subTheater ? '保存修改' : '确认新增'}</span>
              </button>
            </div>
          </div>
        </form>
      </div>
    </div>
  );
};
