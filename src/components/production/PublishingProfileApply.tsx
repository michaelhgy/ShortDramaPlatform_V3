import { useEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { LoaderCircle, X } from 'lucide-react';
import { publishingAction, type ProfilePreview, type ProfileScope, type PublishProfile, type PublishSettings } from '../../api/publishing';
import { profileScopes } from './publishingProfileModel';

export function PublishingProfileApply({ taskId, profile, settings, onClose, onApply }: {
  taskId: string; profile: PublishProfile; settings: PublishSettings; onClose: () => void; onApply: (settings: PublishSettings) => Promise<void>;
}) {
  const [mode, setMode] = useState<'all' | 'timing' | 'custom'>('all');
  const [scopes, setScopes] = useState<ProfileScope[]>(profileScopes.map(s => s.key));
  const [preview, setPreview] = useState<ProfilePreview | null>(null), [loading, setLoading] = useState(true), [saving, setSaving] = useState(false), [error, setError] = useState('');
  const panel = useRef<HTMLDivElement>(null), cancel = useRef<HTMLButtonElement>(null);
  const actual = mode === 'all' ? profileScopes.map(s => s.key) : mode === 'timing' ? ['schedule', 'copies'] as ProfileScope[] : scopes;
  const key = actual.join(',');
  useEffect(() => {
    let active = true; setLoading(true); setPreview(null); setError('');
    if (!actual.length) { setLoading(false); return; }
    publishingAction<ProfilePreview>(taskId, 'profile-preview', { id: profile.id, settings, scopes: actual })
      .then(value => { if (active) setPreview(value); }).catch(e => { if (active) setError(e.message); }).finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [taskId, profile.id, key]);
  useEffect(() => { const previous = document.activeElement as HTMLElement | null; cancel.current?.focus(); return () => { if (previous?.isConnected) previous.focus({ preventScroll: true }); }; }, []);
  useEffect(() => {
    const escape = (e: KeyboardEvent) => { if (e.key !== 'Escape' || e.repeat || e.defaultPrevented) return; e.preventDefault(); e.stopPropagation(); if (!saving) onClose(); };
    window.addEventListener('keydown', escape); return () => window.removeEventListener('keydown', escape);
  }, [saving, onClose]);
  return createPortal(<div data-publishing-profile-apply className="fixed inset-0 z-[125] flex items-center justify-center bg-slate-950/40 p-4 backdrop-blur-sm" onKeyDown={e => {
    if (e.key === 'Escape') { e.stopPropagation(); if (!saving) onClose(); }
    if (e.key === 'Tab') { const controls = [...panel.current!.querySelectorAll<HTMLElement>('button:not(:disabled),input:not(:disabled)')]; const first = controls[0], last = controls.at(-1); if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last?.focus(); } else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first?.focus(); } }
  }}><div ref={panel} role="dialog" aria-modal="true" aria-label="应用发布方案" className="flex max-h-[90vh] w-full max-w-2xl flex-col overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-2xl">
    <header className="flex items-center justify-between border-b border-slate-100 px-5 py-4"><div><h3 className="text-base font-black">应用“{profile.name}”</h3><p className="mt-1 text-xs text-slate-500">只影响当前任务；开始日期时间、视频归属和已有草稿保留。</p></div><button aria-label="关闭应用方案" disabled={saving} className="rounded-lg p-1.5 text-slate-400 hover:bg-slate-100" onClick={onClose}><X size={17} /></button></header>
    <div className="min-h-0 space-y-3 overflow-y-auto p-5"><div className="flex flex-wrap gap-2">{([['all', '应用全部配置'], ['timing', '仅排期与份数'], ['custom', '自选范围']] as const).map(([value, label]) => <button key={value} disabled={saving} aria-pressed={mode === value} className={`rounded-xl px-3 py-2 text-xs font-bold ${mode === value ? 'bg-[#1A1D2E] text-[#DDFD00]' : 'bg-slate-100 text-slate-600'}`} onClick={() => setMode(value)}>{label}</button>)}</div>
      {mode === 'custom' && <div className="flex flex-wrap gap-3 rounded-xl bg-slate-50 p-3">{profileScopes.map(scope => <label key={scope.key} className="flex items-center gap-1.5 text-xs"><input disabled={saving} type="checkbox" checked={scopes.includes(scope.key)} onChange={e => setScopes(values => e.target.checked ? [...values, scope.key] : values.filter(v => v !== scope.key))} />{scope.label}</label>)}</div>}
      <div className="min-h-28 overflow-hidden rounded-xl border border-slate-200">{loading ? <p className="flex items-center gap-2 p-4 text-xs text-slate-500"><LoaderCircle size={14} className="animate-spin" />正在核对变化…</p> : preview?.changes.length ? <table className="w-full table-fixed text-xs"><thead className="bg-slate-50 text-left text-slate-500"><tr><th className="w-1/4 p-2.5">设置项</th><th className="p-2.5">当前内容</th><th className="p-2.5">应用后</th></tr></thead><tbody>{preview.changes.map((change, i) => <tr key={i} className="border-t border-slate-100"><td className="p-2.5 font-bold">{change.label}</td><td title={change.before} className="break-words p-2.5 text-slate-500"><span className="line-clamp-3 whitespace-pre-wrap">{change.before}</span></td><td title={change.after} className={`break-words p-2.5 ${change.after === '空' ? 'text-rose-700' : 'text-slate-900'}`}><span className="line-clamp-3 whitespace-pre-wrap">{change.after === '空' ? '清空' : change.after}</span></td></tr>)}</tbody></table> : <p className="p-4 text-xs leading-6 text-slate-500">{actual.length ? '所选参数与当前一致，应用后会记录当前使用的方案。' : '请至少选择一个应用范围。'}</p>}</div>
      {preview?.has_special_groups && <p className="text-xs leading-5 text-amber-700">人工特殊组保留原文案、份数、地址等设置；整批排期仍按组顺序连续计算。</p>}
      <p className="text-[11px] leading-5 text-slate-400">未选范围保持当前内容。确认后会保存当前任务的准备设置，不会覆盖小V猫已有草稿。</p>
    </div>
    <footer className="border-t border-slate-100 px-5 py-3"><p role={error ? 'alert' : 'status'} className="mb-2 min-h-4 text-xs text-rose-700">{error}</p><div className="flex justify-end gap-2"><button ref={cancel} disabled={saving} className="rounded-xl border border-slate-200 px-4 py-2 text-xs font-bold" onClick={onClose}>取消</button><button disabled={saving || loading || !preview || !actual.length} className="rounded-xl bg-[#1A1D2E] px-4 py-2 text-xs font-black text-[#DDFD00] disabled:opacity-40" onClick={() => { if (!preview) return; setSaving(true); setError(''); void onApply(preview.settings).catch(e => setError(e.message)).finally(() => setSaving(false)); }}>{saving ? '正在应用…' : '应用并保存当前任务'}</button></div></footer>
  </div></div>, document.body);
}
