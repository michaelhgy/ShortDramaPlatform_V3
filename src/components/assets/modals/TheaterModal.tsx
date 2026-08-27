import React, { useState, useEffect } from 'react';
import { TheaterBusinessItem } from '../../../assetsTypes';
import { X, Building2, Save, Trash2, AlertCircle } from 'lucide-react';

interface TheaterModalProps {
  isOpen: boolean;
  onClose: () => void;
  theater: TheaterBusinessItem | null;
  onSave: (theaterData: Omit<TheaterBusinessItem, 'id'>, id?: string) => void;
  onDelete?: (id: string, name: string) => void;
}

export const TheaterModal: React.FC<TheaterModalProps> = ({
  isOpen,
  onClose,
  theater,
  onSave,
  onDelete,
}) => {
  const [name, setName] = useState('');
  const [defaultCommissionRate, setDefaultCommissionRate] = useState(70);
  const [defaultTaxRate, setDefaultTaxRate] = useState(6);
  const [status, setStatus] = useState<'启用' | '停用'>('启用');

  useEffect(() => {
    if (theater) {
      setName(theater.name);
      setDefaultCommissionRate(theater.defaultCommissionRate);
      setDefaultTaxRate(theater.defaultTaxRate);
      setStatus(theater.status);
    } else {
      setName('');
      setDefaultCommissionRate(70);
      setDefaultTaxRate(6);
      setStatus('启用');
    }
  }, [theater, isOpen]);

  if (!isOpen) return null;

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!name.trim()) return;

    onSave({
      name: name.trim(),
      defaultCommissionRate: Number(defaultCommissionRate),
      defaultTaxRate: Number(defaultTaxRate),
      status,
      subTheatersCount: theater?.subTheatersCount || 0,
      dramasCount: theater?.dramasCount || 0,
      isUsedInBusiness: theater ? theater.isUsedInBusiness : false,
    }, theater ? theater.id : undefined);

    onClose();
  };

  const isDeletable = theater && !theater.isUsedInBusiness && (theater.subTheatersCount || 0) === 0 && (theater.dramasCount || 0) === 0;

  const handleDelete = () => {
    if (!theater || !onDelete) return;
    if (!isDeletable) return;
    onDelete(theater.id, theater.name);
    onClose();
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/40 backdrop-blur-xs animate-in fade-in duration-150">
      <div className="bg-white w-full max-w-md rounded-2xl shadow-2xl border border-black/[0.08] overflow-hidden flex flex-col">
        <div className="px-6 py-4 border-b border-black/[0.06] flex items-center justify-between bg-slate-50/80">
          <div className="flex items-center gap-2.5">
            <div className="w-8 h-8 rounded-xl bg-[#1A1D2E] text-[#DDFD00] flex items-center justify-center">
              <Building2 className="w-4 h-4" />
            </div>
            <div>
              <h3 className="font-bold text-sm text-[#1A1D2E]">
                {theater ? '编辑剧场' : '新增剧场档案'}
              </h3>
              <p className="text-xs text-[#64748B]">
                配置剧场基础信息及默认分成税率
              </p>
            </div>
          </div>
          <button onClick={onClose} className="p-1.5 rounded-lg text-slate-400 hover:text-slate-700 hover:bg-black/5 transition-colors cursor-pointer">
            <X className="w-4 h-4" />
          </button>
        </div>

        <form onSubmit={handleSubmit} className="p-6 space-y-4 text-xs">
          <div>
            <label className="block font-semibold text-[#1A1D2E] mb-1.5">
              剧场名称 <span className="text-rose-500">*</span>
            </label>
            <input
              type="text"
              required
              placeholder="例如：九州剧场 / 点众剧场"
              value={name}
              onChange={e => setName(e.target.value)}
              className="w-full px-3 py-2 rounded-xl border border-black/[0.1] bg-slate-50/50 focus:bg-white focus:outline-none focus:ring-2 focus:ring-[#1A1D2E]/20 text-xs font-semibold text-[#1A1D2E]"
            />
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block font-semibold text-[#1A1D2E] mb-1.5">
                默认分成比例 (%) <span className="text-rose-500">*</span>
              </label>
              <div className="relative">
                <input
                  type="number"
                  min={0}
                  max={100}
                  required
                  value={defaultCommissionRate}
                  onChange={e => setDefaultCommissionRate(Number(e.target.value))}
                  className="w-full px-3 py-2 rounded-xl border border-black/[0.1] bg-slate-50/50 focus:bg-white focus:outline-none focus:ring-2 focus:ring-[#1A1D2E]/20 text-xs font-mono font-bold text-[#1A1D2E]"
                />
                <span className="absolute right-3 top-2 text-slate-400 font-mono">%</span>
              </div>
              <p className="text-[10px] text-[#64748B] mt-1">子剧场默认继承此比例</p>
            </div>

            <div>
              <label className="block font-semibold text-[#1A1D2E] mb-1.5">
                默认税率 (%) <span className="text-rose-500">*</span>
              </label>
              <div className="relative">
                <input
                  type="number"
                  min={0}
                  max={100}
                  required
                  value={defaultTaxRate}
                  onChange={e => setDefaultTaxRate(Number(e.target.value))}
                  className="w-full px-3 py-2 rounded-xl border border-black/[0.1] bg-slate-50/50 focus:bg-white focus:outline-none focus:ring-2 focus:ring-[#1A1D2E]/20 text-xs font-mono font-bold text-[#1A1D2E]"
                />
                <span className="absolute right-3 top-2 text-slate-400 font-mono">%</span>
              </div>
            </div>
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

          {/* Validation note for theater */}
          {theater && (
            <div className="pt-2">
              {!isDeletable ? (
                <div className="p-2.5 rounded-xl bg-slate-50 border border-black/[0.06] flex items-center gap-2 text-[11px] text-[#64748B]">
                  <AlertCircle className="w-4 h-4 text-slate-400 shrink-0" />
                  <span>
                    该剧场已有下属子剧场 ({theater.subTheatersCount || 0}) 或关联剧集 ({theater.dramasCount || 0})，禁止删除。
                  </span>
                </div>
              ) : (
                <div className="p-2.5 rounded-xl bg-rose-50/60 border border-rose-100 flex items-center gap-2 text-[11px] text-rose-700">
                  <AlertCircle className="w-4 h-4 text-rose-500 shrink-0" />
                  <span>当前剧场暂无下属子剧场和剧集关联，支持安全删除。</span>
                </div>
              )}
            </div>
          )}

          <div className="pt-3 border-t border-black/[0.06] flex items-center justify-between gap-2.5">
            <div>
              {theater && onDelete && (
                <button
                  type="button"
                  disabled={!isDeletable}
                  onClick={handleDelete}
                  className={`flex items-center gap-1 px-3 py-2 rounded-xl text-xs font-semibold transition-all cursor-pointer ${
                    isDeletable
                      ? 'text-rose-600 hover:bg-rose-50 active:scale-95'
                      : 'text-slate-300 cursor-not-allowed opacity-60'
                  }`}
                  title={!isDeletable ? '已关联业务，不可删除' : '删除该剧场'}
                >
                  <Trash2 className="w-3.5 h-3.5" />
                  <span>删除剧场</span>
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
                <span>{theater ? '保存修改' : '确认新增'}</span>
              </button>
            </div>
          </div>
        </form>
      </div>
    </div>
  );
};
