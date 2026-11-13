import React, { useState, useEffect } from 'react';
import { TheaterBusinessItem } from '../../../assetsTypes';
import type { RevenueCollectorDefinition } from '../../../api/v2Catalog';
import { suggestRevenueCollectors } from '../../../utils/revenueCollectors';
import { X, Building2, Save, Trash2, AlertCircle, Search, Info } from 'lucide-react';

interface TheaterModalProps {
  isOpen: boolean;
  onClose: () => void;
  theater: TheaterBusinessItem | null;
  collectorDefinitions: RevenueCollectorDefinition[];
  collectorError?: string;
  onManageQueryLinks?: () => void;
  onSave: (theaterData: Omit<TheaterBusinessItem, 'id'>, id?: string) => void;
  onDelete?: (id: string, name: string) => void;
}

export const TheaterModal: React.FC<TheaterModalProps> = ({
  isOpen,
  onClose,
  theater,
  collectorDefinitions,
  collectorError,
  onManageQueryLinks,
  onSave,
  onDelete,
}) => {
  const [name, setName] = useState('');
  const [showQueryLinkWarning, setShowQueryLinkWarning] = useState(false);
  const [defaultCommissionRate, setDefaultCommissionRate] = useState(40);
  const [defaultTaxRate, setDefaultTaxRate] = useState(6);
  const [status, setStatus] = useState<'启用' | '停用'>('启用');

  const [collectorIds, setCollectorIds] = useState<string[]>([]);
  const [collectorTouched, setCollectorTouched] = useState(false);
  const [collectorSearch, setCollectorSearch] = useState('');
  const [collectorDetailId, setCollectorDetailId] = useState('');
  const suggestions = suggestRevenueCollectors(name, collectorDefinitions);
  const selectedIds = collectorTouched ? collectorIds : suggestions;
  const search = collectorSearch.trim().toLocaleLowerCase();
  const visibleCollectors = collectorDefinitions.filter(item =>
    !search || [item.name, item.id, ...item.aliases].some(value => value.toLocaleLowerCase().includes(search))
  );
  const collectorDetail = collectorDefinitions.find(item => item.id === collectorDetailId);

  useEffect(() => {
    setShowQueryLinkWarning(false);
    setCollectorSearch('');
    setCollectorDetailId('');
    setCollectorIds(theater?.revenueCollectorIds || []);
    setCollectorTouched(Boolean(theater?.revenueCollectorsConfirmed || theater?.revenueCollectorIds?.length));
    if (theater) {
      setName(theater.name);
      setDefaultCommissionRate(theater.defaultCommissionRate);
      setDefaultTaxRate(theater.defaultTaxRate);
      setStatus(theater.status);
    } else {
      setName('');
      setDefaultCommissionRate(40);
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
      revenueCollectorIds: selectedIds,
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
      <div role="dialog" aria-modal="true" aria-label={theater ? '编辑剧场' : '新增剧场档案'} className="bg-white w-full max-w-xl max-h-[90dvh] rounded-2xl shadow-2xl border border-black/[0.08] overflow-hidden flex flex-col">
        <div className="px-6 py-4 shrink-0 border-b border-black/[0.06] flex items-center justify-between bg-slate-50/80">
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
          <button type="button" aria-label="关闭剧场编辑" onClick={onClose} className="p-1.5 rounded-lg text-slate-400 hover:text-slate-700 hover:bg-black/5 transition-colors cursor-pointer">
            <X className="w-4 h-4" />
          </button>
        </div>

        <form onSubmit={handleSubmit} className="flex min-h-0 flex-1 flex-col text-xs">
          <div className="min-h-0 overflow-y-auto px-6 py-4 space-y-3">
          <div>
            <label htmlFor="theater-name" className="block font-semibold text-[#1A1D2E] mb-1.5">
              剧场名称 <span className="text-rose-500">*</span>
            </label>
            <input
              id="theater-name"
              type="text"
              required
              placeholder="例如：九州剧场 / 点众剧场"
              value={name}
              onChange={e => setName(e.target.value)}
              className="w-full px-3 py-2 rounded-xl border border-black/[0.1] bg-slate-50/50 focus:bg-white focus:outline-none focus:ring-2 focus:ring-[#1A1D2E]/20 text-xs font-semibold text-[#1A1D2E]"
            />
          </div>

          <fieldset className="min-w-0 space-y-2">
            <legend className="sr-only">收益采集器</legend>
            <div className="flex items-center justify-between gap-3">
              <div className="flex items-center gap-2"><span className="font-semibold text-[#1A1D2E]">收益采集器</span><span className="text-[10px] text-slate-400">已选 {selectedIds.length} 个</span></div>
              {onManageQueryLinks && <button type="button" className="shrink-0 text-[11px] font-semibold text-slate-600 underline underline-offset-2 hover:text-[#1A1D2E]" onClick={() => setShowQueryLinkWarning(true)}>管理查单链接</button>}
            </div>
            {showQueryLinkWarning && <div role="alert" className="rounded-xl bg-amber-50 p-3 text-[11px] leading-5 text-amber-800"><p>前往查单管理会关闭当前编辑，未保存的剧场修改不会保留。</p><div className="mt-2 flex gap-3"><button type="button" className="font-bold underline underline-offset-2" onClick={onManageQueryLinks}>继续前往</button><button type="button" className="text-slate-500" onClick={() => setShowQueryLinkWarning(false)}>留在这里</button></div></div>}
            <p className="text-[11px] leading-5 text-slate-500">按名称推荐，复核后保存；未接入的剧场可留空。</p>
            {collectorError && <p role="alert" className="text-rose-600">{collectorError}，请重新打开资料中心后再试。</p>}
            {!collectorError && collectorDefinitions.length === 0 && <p className="text-slate-500">正在读取软件内置采集器…</p>}
            <div className="relative">
              <Search className="pointer-events-none absolute left-3 top-2.5 h-3.5 w-3.5 text-slate-400" />
              <input type="search" aria-label="搜索收益采集器" placeholder="搜索采集器名称" value={collectorSearch} onChange={event => setCollectorSearch(event.target.value)} className="w-full rounded-xl border border-black/[0.08] bg-slate-50/60 py-2 pl-8 pr-3 text-xs outline-none focus:border-slate-400 focus:bg-white" />
            </div>
            <div aria-label="可选收益采集器" className="grid max-h-36 grid-cols-1 gap-2 overflow-y-auto overscroll-contain rounded-xl border border-black/[0.06] bg-slate-50/40 p-2 min-[480px]:grid-cols-2">
              {visibleCollectors.map(item => <div key={item.id} className={`flex min-w-0 items-center rounded-lg border ${selectedIds.includes(item.id) ? 'border-slate-400 bg-white' : 'border-black/[0.06] bg-white/80'}`}>
                <label className="flex min-w-0 flex-1 cursor-pointer items-center gap-2 px-2.5 py-2">
                  <input type="checkbox" className="shrink-0 accent-[#1A1D2E]" checked={selectedIds.includes(item.id)} onChange={event => {
                    setCollectorIds(event.target.checked ? [...selectedIds, item.id] : selectedIds.filter(id => id !== item.id));
                    setCollectorTouched(true);
                  }} />
                  <span className="truncate font-semibold text-[#1A1D2E]" title={item.name}>{item.name}</span>
                  {suggestions.includes(item.id) && <span className="shrink-0 text-[10px] text-emerald-700">推荐</span>}
                </label>
                <button type="button" aria-label={`查看${item.name}说明`} aria-expanded={collectorDetailId === item.id} onClick={() => setCollectorDetailId(collectorDetailId === item.id ? '' : item.id)} className="mr-1.5 shrink-0 rounded-md p-1.5 text-slate-400 hover:bg-slate-100 hover:text-slate-700"><Info className="h-3.5 w-3.5" /></button>
              </div>)}
              {collectorDefinitions.length > 0 && visibleCollectors.length === 0 && <p className="col-span-full py-3 text-center text-[11px] text-slate-400">没有匹配的采集器</p>}
            </div>
            {collectorDetail && <div className="flex items-start gap-2 rounded-lg bg-slate-100/80 px-3 py-2 text-[11px] leading-5 text-slate-500"><p className="max-h-20 min-w-0 flex-1 overflow-y-auto"><span className="font-semibold text-slate-700">{collectorDetail.name}：</span>{collectorDetail.notes || '暂无补充说明'}</p><button type="button" aria-label="收起采集器说明" onClick={() => setCollectorDetailId('')} className="shrink-0 p-0.5 text-slate-400 hover:text-slate-700"><X className="h-3.5 w-3.5" /></button></div>}
          </fieldset>

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

          <div className="flex items-center justify-between gap-3">
            <span className="font-semibold text-[#1A1D2E]">启用状态</span>
            <div className="flex w-52 items-center gap-2">
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
            <div>
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

          </div>
          <div className="shrink-0 border-t border-black/[0.06] bg-slate-50/80 px-6 py-3 flex items-center justify-between gap-2.5">
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
                disabled={collectorDefinitions.length === 0}
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
