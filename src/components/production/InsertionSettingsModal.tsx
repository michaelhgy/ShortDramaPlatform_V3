import React, { useEffect, useState } from 'react';
import { X } from 'lucide-react';
import { createPortal } from 'react-dom';
import { getV2EngineParameters, type V2InsertionSlot, type V2MidrollEndrollStrategy } from '../../api/v2EngineParameters';
import { getV2ProductionResources } from '../../api/v2Catalog';
import type { MaterialInsertionOverride } from '../../productionTypes';
import type { ProductionResourceItem } from '../../assetsTypes';
import { naturalCompare } from '../../utils/naturalCompare';
import { InsertionTimingFields, insertionTime, insertionTimingError } from '../parameters/InsertionTimingFields';

type SlotKey = 'midroll' | 'endroll';
export function overrideSummary(value?: MaterialInsertionOverride | null): string {
  const slots = Object.values(value || {}).filter(slot => slot && Object.keys(slot).length);
  return !slots.length ? '跟随全局' : slots.length === 1 ? '部分覆盖' : '已覆盖';
}
export function materialInsertionSummary(value?: MaterialInsertionOverride | null): string {
  if (!Object.values(value || {}).some(slot => slot && Object.keys(slot).length)) return '跟随剧集';
  if (value?.midroll?.enabled === false && value?.endroll?.enabled === false) return '本片中尾插均不要';
  if (value?.midroll?.enabled === false) return '本片不插中插';
  if (value?.endroll?.enabled === false) return '本片不接尾插';
  return '本片已覆盖';
}
function merge(base: V2MidrollEndrollStrategy, value?: MaterialInsertionOverride | null): V2MidrollEndrollStrategy {
  return { midroll: { ...base.midroll, ...value?.midroll }, endroll: { ...base.endroll, ...value?.endroll } };
}
function describe(slot: V2InsertionSlot, key: SlotKey): string {
  if (!slot.enabled) return '不插入';
  const file = slot.mode === 'locked' ? slot.file : '跟随最新序号';
  return key === 'endroll' ? file : `短于 ${insertionTime(slot.min_source_duration_seconds ?? 120)} 不插；位置 ${insertionTime(slot.position_start_seconds ?? 120)}–${insertionTime(slot.position_end_seconds ?? 120)}；${file}`;
}

export function InsertionSettingsModal({ title, subtitle, material, initial, taskOverride, onSave, onClose, embedded = false, readOnly = false, onDirtyChange, onBusyChange, actionContainer, readOnlyReason }: {
  key?: string; title: string; subtitle: string; material?: boolean; initial?: MaterialInsertionOverride | null;
  readOnlyReason?: string; actionContainer?: HTMLElement | null; embedded?: boolean; readOnly?: boolean; onDirtyChange?: (dirty: boolean) => void; onBusyChange?: (busy: boolean) => void;
  taskOverride?: MaterialInsertionOverride | null; onSave: (value: MaterialInsertionOverride | null) => Promise<void>; onClose: () => void;
}) {
  const [draft, setDraft] = useState<MaterialInsertionOverride>(() => structuredClone(initial || {}));
  const [base, setBase] = useState<V2MidrollEndrollStrategy | null>(null);
  const [resources, setResources] = useState<ProductionResourceItem[]>([]);
  const [error, setError] = useState('');
  const [saving, setSaving] = useState(false);
  const [savedDraft, setSavedDraft] = useState(() => JSON.stringify(initial || {}));
  const [notice, setNotice] = useState('');
  const dirty = JSON.stringify(draft) !== savedDraft;
  useEffect(() => { onDirtyChange?.(dirty); }, [dirty, onDirtyChange]);
  useEffect(() => { onBusyChange?.(saving); }, [saving, onBusyChange]);
  useEffect(() => {
    let active = true;
    Promise.all([getV2EngineParameters(), material ? Promise.resolve({ items: [] }) : getV2ProductionResources()])
      .then(([parameters, videos]) => {
        if (!active) return;
        const global = structuredClone(parameters.midroll_endroll.strategy);
        if (!parameters.midroll_endroll.configured) { global.midroll.enabled = false; global.endroll.enabled = false; }
        setBase(material ? merge(global, taskOverride) : global);
        setResources((videos.items as ProductionResourceItem[]).filter(item => item.category === 'lead_video').sort((a, b) => naturalCompare(a.name, b.name)));
      }).catch((reason: unknown) => { if (active) setError(reason instanceof Error ? reason.message : '读取插片规则失败'); });
    return () => { active = false; };
  }, []);
  const effective = base ? merge(base, draft) : null;
  const timingError = effective ? insertionTimingError(effective.midroll) : '';
  const selectedFileError = (['midroll', 'endroll'] as const).some(key => {
    const slot = effective?.[key];
    return slot?.enabled && slot.mode === 'locked' && !slot.file;
  }) ? '请选择指定的插片素材。' : '';
  const save = async (reset = false) => {
    if (!base || saving || readOnly) return;
    setSaving(true); setError(''); setNotice('');
    try {
      const value = Object.fromEntries(Object.entries(draft).filter(([, slot]) => slot && Object.keys(slot).length)) as MaterialInsertionOverride;
      const next = reset || !Object.keys(value).length ? null : value;
      await onSave(next);
      setDraft(structuredClone(next || {})); setSavedDraft(JSON.stringify(next || {}));
      if (embedded) setNotice('已保存，后续新提交的成片使用此设置。');
      else onClose();
    } catch (reason) { setError(reason instanceof Error ? reason.message : '保存插片规则失败'); }
    finally { setSaving(false); }
  };
  const actions = <div className="flex items-center justify-between gap-2"><button type="button" disabled={!base || saving || readOnly} onClick={() => void save(true)} className="rounded-xl bg-slate-100 px-3 py-1.5 text-xs font-bold disabled:opacity-40">{material ? '恢复跟随剧集' : '恢复跟随全局'}</button><div className="flex gap-2">{!embedded && <button type="button" disabled={saving} onClick={onClose} className="rounded-xl bg-slate-100 px-3 py-1.5 text-xs font-bold">取消</button>}<button type="button" disabled={!base || saving || readOnly || Boolean(timingError || selectedFileError)} onClick={() => void save()} className="rounded-xl bg-[#1A1D2E] px-3.5 py-1.5 text-xs font-black text-[#DDFD00] disabled:opacity-40">{saving ? '保存中…' : embedded ? '保存本片设置' : '保存'}</button></div></div>;
  return <div className={embedded ? '' : "fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4 backdrop-blur-xs"} onClick={() => { if (!embedded && !saving) onClose(); }}>
    <div role={embedded ? undefined : "dialog"} aria-modal={embedded ? undefined : true} aria-label={embedded ? undefined : title} className={embedded ? "space-y-3" : "max-h-[85vh] w-full max-w-xl space-y-4 overflow-y-auto rounded-3xl border border-black/[0.08] bg-white p-5 shadow-2xl"} onClick={event => event.stopPropagation()}>
      {!embedded && <>
      <div className="flex items-start justify-between gap-3 border-b border-black/[0.06] pb-3"><div><h3 className="text-base font-black text-[#1A1D2E]">{title}</h3><p className="mt-1 text-xs text-[#64748B]">{subtitle}</p></div><button type="button" aria-label="关闭插片设置" disabled={saving || readOnly} onClick={onClose} className="rounded-lg p-1 hover:bg-slate-100"><X className="h-4 w-4" /></button></div>
      </>}
      {!base && !error && <p className="text-xs text-slate-500">读取当前规则…</p>}
      {base && effective && (['midroll', 'endroll'] as SlotKey[]).map(key => {
        const override = draft[key]; const slot = effective[key]; const label = key === 'midroll' ? '中插' : '尾插';
        const mode = !override || !Object.keys(override).length ? 'inherit' : override.enabled === false ? 'off' : 'on';
        const setSlot = (patch: Partial<V2InsertionSlot>) => setDraft(prev => ({ ...prev, [key]: { ...prev[key], ...patch } }));
        return <div key={key} className="space-y-2 rounded-2xl border border-black/[0.06] bg-[#F8FAFC] p-3">
          <div className="flex items-center justify-between gap-2"><span className="text-sm font-extrabold text-[#1A1D2E]">{label}</span>
            <select aria-label={`${material ? '本素材' : '本剧集'}${label}规则`} value={mode} disabled={saving || readOnly} className="rounded-xl border border-black/[0.08] bg-white px-2.5 py-1.5 text-xs font-bold" onChange={event => {
              const next = event.target.value;
              setDraft(prev => { const copy = { ...prev }; if (next === 'inherit') delete copy[key]; else copy[key] = next === 'off' ? { enabled: false } : material ? { enabled: true } : { ...base[key], enabled: true }; return copy; });
            }}>
              <option value="inherit">{material ? '跟随剧集' : '跟随全局'}</option><option value="off">{material ? '本片不要' : '本剧集不要'}</option><option value="on">{material ? '本片要插' : '本剧集单独设置'}</option>
            </select>
          </div>
          <p className="break-words text-[11px] leading-relaxed text-[#64748B]">当前生效：{describe(slot, key)}</p>
          {!material && mode === 'on' && <>
            {key === 'midroll' && <InsertionTimingFields value={slot} onChange={setSlot} />}
            <div className="flex flex-wrap items-center gap-2 text-xs"><span>插片素材</span><select aria-label={`${label}取材方式`} value={slot.mode} onChange={event => setSlot({ mode: event.target.value as 'latest' | 'locked', file: event.target.value === 'latest' ? '' : slot.file })} className="rounded-lg border border-black/[0.08] bg-white px-2 py-1"><option value="latest">跟随最新序号</option><option value="locked">指定某一条</option></select></div>
            {slot.mode === 'locked' && <select aria-label={`${label}指定素材`} value={slot.file} onChange={event => setSlot({ file: event.target.value })} className="w-full rounded-lg border border-black/[0.08] bg-white px-2 py-1.5 text-xs"><option value="">请选择素材</option>{slot.file && !resources.some(item => item.name === slot.file) && <option value={slot.file}>{slot.file}（当前不可用）</option>}{resources.filter(item => item.name.startsWith(label)).map(item => <option key={item.id} value={item.name}>{item.name}</option>)}</select>}
          </>}
          {material && mode === 'on' && <p className="text-[10px] text-slate-500">本片启用，素材与时长条件继续继承剧集/全局规则。</p>}
        </div>;
      })}
      {notice && <p role="status" className="text-xs text-emerald-700">{notice}</p>}
      {readOnly && <p className="text-xs text-slate-500">{readOnlyReason || '本剧集已登记发布，插片设置只读。'}</p>}
      {(error || timingError || selectedFileError) && <p role="alert" className="text-xs text-rose-700">{error || timingError || selectedFileError}</p>}
      <p className="text-[11px] text-slate-500">仅用于后续新提交的成片。已排队、运行和已完成成片保留提交时规则；失败重试使用原配方。</p>
      {actionContainer ? createPortal(actions, actionContainer) : actions}
    </div>
  </div>;
}
