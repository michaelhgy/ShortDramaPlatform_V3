import { PublishingCoverControl } from './PublishingCoverControl';
import { useEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { Copy, Plus, Save, Trash2, X } from 'lucide-react';
import { getPublishingAddressBook, getPublishingHistory, getPublishingProfiles, publishingAction, type LocationValue, type ProfileGroup, type ProfileLibrary, type PublishProfile, type PublishProfileConfig, type PublishSettings, type ShootRegion } from '../../api/publishing';
import { cloneProfile, newPublishProfile, sharedProfileKeys } from './publishingProfileModel';
import { declarationOptions, intervalLabel, intervalMinutes } from './publishingOptions';
import { usePublishingConfirm } from './PublishingConfirm';
import { PublishingHistoryField as HistoryField } from './PublishingHistoryField';

const field = 'mt-1 w-full rounded-xl border border-slate-200 bg-white px-3 py-2 text-xs outline-none focus:border-slate-500 disabled:bg-slate-100';
const button = 'inline-flex items-center justify-center gap-1.5 whitespace-nowrap rounded-xl border border-slate-200 bg-white px-3 py-2 text-xs font-bold text-slate-700 hover:bg-slate-50 disabled:opacity-40';
const block = 'space-y-3 rounded-xl border border-slate-200 bg-white p-4';

export function PublishingProfileManager({ taskId, settings, library: initialLibrary, accountName, addresses, regions, onLibrary, onHistory, onClose, onSavedApply }: {
  taskId: string; settings: PublishSettings; library: ProfileLibrary; accountName: string; addresses: LocationValue[]; regions: ShootRegion[];
  onLibrary: (value: ProfileLibrary) => void; onHistory: (value: Record<string, string[]>) => void; onClose: () => void; onSavedApply: (id: string) => void;
}) {
  const { confirm, confirmation } = usePublishingConfirm();
  const [library, setLibrary] = useState(initialLibrary);
  const [addressRows, setAddressRows] = useState(addresses);
  const [history, setHistory] = useState<Record<string, string[]>>({});
  const initial = initialLibrary.items.find(p => p.id === settings.profile_ref?.id) || initialLibrary.items[0] || newPublishProfile();
  const [draft, setDraft] = useState<PublishProfile>(() => cloneProfile(initial));
  const [software, setSoftware] = useState(initialLibrary.software_default_id === initial.id);
  const [account, setAccount] = useState(initialLibrary.account_default_id === initial.id);
  const [kind, setKind] = useState<'normal' | 'sheep'>('normal');
  const [tagsText, setTagsText] = useState((initial.config.groups.normal.tags || []).join(' '));
  const [customInterval, setCustomInterval] = useState(false);
  const [busy, setBusy] = useState('读取方案'), [error, setError] = useState(''), [notice, setNotice] = useState('');
  const baseline = useRef(JSON.stringify([initial, initialLibrary.software_default_id === initial.id, initialLibrary.account_default_id === initial.id]));
  const dirty = JSON.stringify([draft, software, account]) !== baseline.current;
  const panel = useRef<HTMLDivElement>(null), closeButton = useRef<HTMLButtonElement>(null), alive = useRef(true);
  const inherited = kind === 'sheep' && draft.config.sheep_inherit;
  const group = draft.config.groups[inherited ? 'normal' : kind];
  function choose(value: PublishProfile, book = library, changed = false) {
    const sw = Boolean(value.id && book.software_default_id === value.id), ac = Boolean(value.id && book.account_default_id === value.id);
    setDraft(cloneProfile(value)); setSoftware(sw); setAccount(ac); setError(''); setNotice(''); setKind('normal'); setCustomInterval(false); setTagsText((value.config.groups.normal.tags || []).join(' '));
    baseline.current = changed ? '' : JSON.stringify([value, sw, ac]);
  }
  useEffect(() => { setTagsText((draft.config.groups[inherited ? 'normal' : kind].tags || []).join(' ')); }, [kind, inherited]);
  useEffect(() => {
    alive.current = true;
    Promise.all([getPublishingProfiles(taskId), getPublishingAddressBook(taskId), getPublishingHistory(taskId)]).then(([book, addressBook, records]) => {
      if (!alive.current) return;
      setLibrary(book); onLibrary(book); setAddressRows(addressBook.public_addresses); setHistory(records); onHistory(records);
      choose(book.items.find(p => p.id === settings.profile_ref?.id) || book.items[0] || newPublishProfile(), book);
    }).catch(e => { if (alive.current) setError(e.message); }).finally(() => { if (alive.current) setBusy(''); });
    const previous = document.activeElement as HTMLElement | null; closeButton.current?.focus();
    return () => { alive.current = false; if (previous?.isConnected) previous.focus({ preventScroll: true }); };
  }, [taskId]);
  async function discard() {
    return !dirty || await confirm({ title: '有未保存的方案修改', message: '继续后会放弃当前方案中尚未保存的修改。当前发布任务不受影响。', confirmText: '放弃修改' });
  }
  async function close() { if ((!busy || busy === '读取方案') && await discard()) onClose(); }
  useEffect(() => {
    const escape = (e: KeyboardEvent) => {
      if (e.key !== 'Escape' || e.repeat || e.defaultPrevented || document.querySelector('[role="alertdialog"], [data-publishing-history]')) return;
      e.preventDefault(); e.stopPropagation(); void close();
    };
    window.addEventListener('keydown', escape); return () => window.removeEventListener('keydown', escape);
  }, [dirty, busy]);
  async function perform(label: string, action: () => Promise<void>) {
    setBusy(label); setError(''); setNotice('');
    try { await action(); } catch (e) { if (alive.current) setError(e instanceof Error ? e.message : '操作未完成'); }
    finally { if (alive.current) setBusy(''); }
  }
  function config(patch: Partial<PublishProfileConfig>) { setDraft(value => ({ ...value, config: { ...value.config, ...patch } })); }
  function updateGroup(patch: Partial<ProfileGroup>) { config({ groups: { ...draft.config.groups, [kind]: { ...draft.config.groups[kind], ...patch } } }); }
  function uniqueName(base: string) {
    let value = base, suffix = 2;
    while (library.items.some(p => p.name.toLocaleLowerCase() === value.toLocaleLowerCase())) value = `${base} ${suffix++}`;
    return value;
  }
  async function save(apply: boolean) {
    const result = await publishingAction<{ profile: PublishProfile; library: ProfileLibrary; history: Record<string, string[]> }>(taskId, 'profile-save', { ...draft, software_default: software, account_default: account });
    if (!alive.current) return;
    setLibrary(result.library); onLibrary(result.library); setHistory(result.history); onHistory(result.history); choose(result.profile, result.library); setNotice('方案已保存；已有任务的设置保持原样。');
    if (apply) onSavedApply(result.profile.id);
  }
  function deleteHistory(key: string, value: string) {
    void perform('删除历史', async () => {
      await publishingAction(taskId, 'history-delete', { key, value });
      const records = { ...history, [key]: (history[key] || []).filter(text => text !== value) };
      setHistory(records); onHistory(records);
    });
  }
  const cfg = draft.config;
  return createPortal(<div data-publishing-profiles className="fixed inset-0 z-[120] flex items-center justify-center bg-slate-950/40 p-4 backdrop-blur-sm" onKeyDown={e => {
    if (document.querySelector('[role="alertdialog"], [data-publishing-history]')) return;
    if (e.key === 'Escape') { e.stopPropagation(); e.preventDefault(); void close(); }
    if (e.key === 'Tab') {
      const controls = [...panel.current!.querySelectorAll<HTMLElement>('button:not(:disabled),input:not(:disabled),select:not(:disabled),textarea:not(:disabled),summary')].filter(el => el.getClientRects().length);
      const first = controls[0], last = controls[controls.length - 1];
      if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last?.focus(); }
      else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first?.focus(); }
    }
  }}><div ref={panel} role="dialog" aria-modal="true" aria-label="自动发布默认配置" className="flex h-[min(850px,92vh)] w-full max-w-6xl flex-col overflow-hidden rounded-2xl bg-[#F5F7FA] shadow-2xl">
    <header className="flex shrink-0 items-center justify-between border-b border-slate-200 bg-white px-5 py-3"><div><h3 className="text-base font-black">自动发布默认配置</h3><p className="mt-1 text-xs text-slate-500">管理多套发布方案 · 当前账号：{accountName}</p></div><button ref={closeButton} aria-label="关闭默认配置" disabled={!!busy && busy !== '读取方案'} className="rounded-lg p-1.5 text-slate-400 hover:bg-slate-100 disabled:opacity-40" onClick={() => void close()}><X size={18} /></button></header>
    <div className="grid min-h-0 flex-1 grid-cols-[190px_minmax(0,1fr)] lg:grid-cols-[220px_minmax(0,1fr)]">
      <aside className="flex min-h-0 flex-col gap-2 border-r border-slate-200 bg-white p-3"><button className={button} disabled={!!busy} onClick={() => void (async () => { if (await discard()) choose({ ...newPublishProfile(), name: uniqueName('新方案') }); })()}><Plus size={13} />新建方案</button><button className={button} disabled={!!busy} onClick={() => void (async () => {
        if (!await discard()) return;
        await perform('读取当前设置', async () => { const result = await publishingAction<{ config: PublishProfileConfig }>(taskId, 'profile-capture', { settings }); choose({ id: '', revision: 0, name: uniqueName('当前任务方案'), config: result.config }, library, true); });
      })()}>从当前设置另存</button><div className="mt-1 min-h-0 flex-1 space-y-1 overflow-y-auto">{library.items.map(p => <button key={p.id} disabled={!!busy} aria-pressed={draft.id === p.id} className={`w-full rounded-xl border p-3 text-left ${draft.id === p.id ? 'border-slate-900 bg-slate-900 text-white' : 'border-transparent hover:bg-slate-50'}`} onClick={() => void (async () => { if (await discard()) choose(p); })()}><span className="block break-words text-xs font-bold">{p.name}</span><span className="mt-1 flex flex-wrap gap-1 text-[10px]">{library.software_default_id === p.id && <span className="rounded bg-lime-100 px-1 text-lime-800">软件默认</span>}{library.account_default_id === p.id && <span className="rounded bg-blue-100 px-1 text-blue-800">本账号默认</span>}</span></button>)}</div><p className="text-[10px] leading-5 text-slate-400">新任务优先使用账号默认，其次软件默认。已保存任务保留原设置。</p></aside>
      <fieldset disabled={!!busy} className="min-h-0 min-w-0 space-y-3 overflow-y-auto p-4">
        <section className={block}><div className="flex items-end gap-2"><label className="min-w-0 flex-1 text-xs font-bold text-slate-600">方案名称<input aria-label="方案名称" maxLength={50} className={field} value={draft.name} onChange={e => setDraft({ ...draft, name: e.target.value })} /></label><button className={button} onClick={() => choose({ ...cloneProfile(draft), id: '', revision: 0, name: uniqueName(`${draft.name.slice(0, 40)} 副本`) }, library, true)}><Copy size={13} />复制</button><button className={`${button} text-rose-600`} disabled={!draft.id} onClick={() => void (async () => {
          if (!await confirm({ title: '删除发布方案', message: `删除“${draft.name}”后，使用它的软件和账号默认关联会取消。已保存任务和已有草稿会保留。`, confirmText: '删除方案' })) return;
          await perform('删除方案', async () => { const result = await publishingAction<{ library: ProfileLibrary }>(taskId, 'profile-delete', { id: draft.id, revision: draft.revision }); setLibrary(result.library); onLibrary(result.library); choose(result.library.items[0] || newPublishProfile(), result.library); setNotice('方案已删除，已有任务未改变。'); });
        })()}><Trash2 size={13} />删除</button></div><div className="flex flex-wrap gap-x-5 gap-y-2 text-xs text-slate-600"><label className="flex items-center gap-2"><input type="checkbox" checked={software} onChange={e => setSoftware(e.target.checked)} />设为软件默认</label><label className="flex items-center gap-2"><input type="checkbox" checked={account} onChange={e => setAccount(e.target.checked)} />设为当前账号默认</label></div></section>
        <section className={block}><h4 className="text-xs font-black">排期与份数</h4><div className="grid grid-cols-3 gap-3"><label className="text-xs text-slate-500">时间方式<select aria-label="方案时间方式" className={field} value={cfg.schedule.schedule_type} onChange={e => config({ schedule: { ...cfg.schedule, schedule_type: e.target.value as typeof cfg.schedule.schedule_type } })}><option value="now">立即模式</option><option value="timing">平台定时</option><option value="localTiming">本机定时</option></select></label><label className="text-xs text-slate-500">作品间隔<select aria-label="方案作品间隔" className={field} value={customInterval || !intervalMinutes.includes(cfg.schedule.interval) ? 'custom' : String(cfg.schedule.interval)} onChange={e => { setCustomInterval(e.target.value === 'custom'); if (e.target.value !== 'custom') config({ schedule: { ...cfg.schedule, interval: Number(e.target.value) } }); }}>{intervalMinutes.map(n => <option key={n} value={n}>{intervalLabel(n)}</option>)}<option value="custom">自定义间隔</option></select>{(customInterval || !intervalMinutes.includes(cfg.schedule.interval)) && <input aria-label="方案自定义间隔分钟" type="number" min={0} max={10080} className={field} value={cfg.schedule.interval} onChange={e => config({ schedule: { ...cfg.schedule, interval: Number(e.target.value) } })} />}</label><label className="text-xs text-slate-500">两组顺序<select aria-label="方案两组顺序" className={field} value={cfg.group_order} onChange={e => config({ group_order: e.target.value as typeof cfg.group_order })}><option value="normal_first">正剧 → 羊</option><option value="sheep_first">羊 → 正剧</option></select></label></div><div className="grid grid-cols-2 gap-3">{(['normal', 'sheep'] as const).map(k => <div key={k} className="rounded-xl bg-slate-50 p-3"><strong className="text-xs">{k === 'normal' ? '正剧视频' : '羊视频'}</strong><div className="mt-1 grid grid-cols-[80px_1fr] gap-2"><label className="text-[11px] text-slate-500">每视频份数<input aria-label={k === 'normal' ? '方案正剧份数' : '方案羊份数'} type="number" min={1} max={100} className={field} value={cfg.groups[k].copies} onChange={e => config({ groups: { ...cfg.groups, [k]: { ...cfg.groups[k], copies: Number(e.target.value) } } })} /></label><label className="text-[11px] text-slate-500">排列<select aria-label={k === 'normal' ? '方案正剧排列' : '方案羊排列'} className={field} value={cfg.groups[k].order} onChange={e => config({ groups: { ...cfg.groups, [k]: { ...cfg.groups[k], order: e.target.value as ProfileGroup['order'] } } })}><option value="round">整组循环</option><option value="consecutive">同视频连续</option></select></label></div></div>)}</div><p className="text-[11px] text-slate-400">具体开始日期和时间每批确认，不存入方案；两组自动接续。</p></section>
        <section className={block}><h4 className="text-xs font-black">封面设置</h4><div className="grid grid-cols-2 gap-4">{(['normal', 'sheep'] as const).map(k => <div key={k} className="space-y-2 rounded-xl bg-slate-50 p-3"><strong className="text-xs">{k === 'normal' ? '正剧视频' : '羊视频'}</strong><PublishingCoverControl key={`${draft.id}-${k}`} taskId={taskId} label={k === 'normal' ? '方案正剧' : '方案羊'} value={cfg.groups[k]} disabled={!!busy} onBusy={active => setBusy(active ? '保存封面' : '')} onChange={patch => setDraft(current => ({ ...current, config: { ...current.config, groups: { ...current.config.groups, [k]: { ...current.config.groups[k], ...patch } } } }))} /></div>)}</div><p className="text-[11px] text-slate-400">使用自带时自动匹配当前剧集封面；自定义图片单独保存，应用此方案的任务将共用该图片。正剧和羊各自设置。</p></section>
        <section className={block}>
          <div className="flex flex-wrap items-center justify-between gap-2"><h4 className="text-xs font-black">文案与声明</h4><label className="flex items-center gap-2 text-xs text-slate-600"><input type="checkbox" checked={cfg.sheep_inherit} onChange={e => {
            const sheep = { ...cfg.groups.sheep }; if (!e.target.checked) for (const key of sharedProfileKeys) Object.assign(sheep, { [key]: cloneProfile(cfg.groups.normal[key]) });
            config({ sheep_inherit: e.target.checked, groups: { ...cfg.groups, sheep } });
          }} />羊沿用正剧文案与声明</label></div>
          <div className="flex gap-2">{(['normal', 'sheep'] as const).map(k => <button key={k} aria-pressed={kind === k} className={`${button} ${kind === k ? '!bg-[#1A1D2E] !text-[#DDFD00]' : ''}`} onClick={() => setKind(k)}>{k === 'normal' ? '正剧设置' : '羊设置'}</button>)}</div>
          {inherited && <p className="text-[11px] text-slate-500">以下内容沿用正剧；羊的份数、排列和挂载独立设置。</p>}
          <fieldset disabled={inherited} className="space-y-3">
            <div className="grid grid-cols-2 gap-3"><div className="space-y-3">
              <HistoryField disabled={!!busy || inherited} label="视频标题" value={group.video_title || ''} history={history.video_title || []} onChange={video_title => updateGroup({ video_title })} onDelete={value => deleteHistory('video_title', value)} />
              <HistoryField disabled={!!busy || inherited} label="话题" value={tagsText} history={history.tags || []} onChange={text => { setTagsText(text); updateGroup({ tags: text.split(/[\s,#，；;]+/).filter(Boolean) }); }} onDelete={value => deleteHistory('tags', value)} />
            </div><HistoryField disabled={!!busy || inherited} label="简介" multiline className="h-full" value={group.desc} history={history.desc || []} onChange={desc => updateGroup({ desc })} onDelete={value => deleteHistory('desc', value)} /></div>
            <div className="flex items-center gap-4"><label className="flex-1 text-xs text-slate-500">视频声明<select aria-label="方案视频声明" className={field} value={group.tag_type} onChange={e => updateGroup({ tag_type: Number(e.target.value) })}>{declarationOptions.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}</select></label><label className="flex items-center gap-2 pt-4 text-xs text-slate-600"><input type="checkbox" checked={group.original} onChange={e => updateGroup({ original: e.target.checked })} />视频为原创</label></div>
            {group.tag_type === 7 && <HistoryField disabled={!!busy || inherited} label="转载来源" multiline value={group.repost_source || ''} history={history.repost_source || []} onChange={repost_source => updateGroup({ repost_source })} onDelete={value => deleteHistory('repost_source', value)} />}
            {group.tag_type === 5 && <div className="space-y-2"><p className="text-[11px] text-slate-500">拍摄日期每批填写，可在这里预设拍摄地区。</p><div className="grid grid-cols-3 gap-2">{[0, 1, 2].map(level => { let choices = regions; for (let i = 0; i < level; i++) choices = choices.find(r => r.code === group.shoot_region_codes?.[i])?.sub || []; if (level && !choices.length) return null; return <label key={level} className="text-[11px] text-slate-500">{['国家/地区', '省份', '城市'][level]}<select aria-label={`方案拍摄地区${level}`} className={field} value={group.shoot_region_codes?.[level] ?? ''} onChange={e => updateGroup({ shoot_region_codes: [...(group.shoot_region_codes || []).slice(0, level), ...(e.target.value ? [Number(e.target.value)] : [])] })}><option value="">请选择</option>{choices.map(r => <option key={r.code} value={r.code}>{r.name}</option>)}</select></label>; })}</div></div>}
            <details><summary className="cursor-pointer text-xs text-slate-500">追评与更多设置</summary><div className="mt-3 space-y-3">
              <HistoryField disabled={!!busy || inherited} label="短标题（选填，6–16字）" value={group.short_title || ''} history={history.short_title || []} onChange={short_title => updateGroup({ short_title })} onDelete={value => deleteHistory('short_title', value)} />
              <HistoryField disabled={!!busy || inherited} label="追评" multiline value={group.comment} history={history.comment || []} onChange={comment => updateGroup({ comment })} onDelete={value => deleteHistory('comment', value)} />
              <label className="flex items-center gap-2 text-xs text-slate-500"><input type="checkbox" checked={group.comment_top} onChange={e => updateGroup({ comment_top: e.target.checked })} />置顶追评</label>
            </div></details>
          </fieldset>
        </section>
        <section className={block}><h4 className="text-xs font-black">地址与挂载</h4><label className="flex items-center gap-2 text-xs text-slate-600"><input aria-label="方案正剧与羊同步地址" type="checkbox" checked={cfg.location.sync} onChange={e => config({ location: { ...cfg.location, sync: e.target.checked } })} />正剧与羊同步地址</label><p className="text-[11px] text-slate-400">开启后，两组修改地址会一起更新；关闭后可各自更换。挂载选项仍各自独立。</p><label className="block text-xs text-slate-500">地址方式<select aria-label="方案地址方式" className={field} value={cfg.location.mode} onChange={e => config({ location: { ...cfg.location, mode: e.target.value as typeof cfg.location.mode, checksum: e.target.value === 'public' ? cfg.location.checksum : '' } })}><option value="account">使用各账号自己的默认地址</option><option value="none">不显示位置</option><option value="public">使用指定公共地址</option></select></label>{cfg.location.mode === 'public' && <label className="block text-xs text-slate-500">公共地址<select aria-label="方案公共地址" className={field} value={cfg.location.checksum} onChange={e => config({ location: { ...cfg.location, checksum: e.target.value } })}><option value="">请选择已确认的公共地址</option>{cfg.location.checksum && !addressRows.some(a => a.poiCheckSum === cfg.location.checksum) && <option value={cfg.location.checksum}>原地址已移除，请重新选择</option>}{addressRows.map(a => <option key={a.poiCheckSum} value={a.poiCheckSum}>{a.name} · {a.city || a.fullAddress || ''}</option>)}</select></label>}<div className="grid grid-cols-2 gap-3">{(['normal', 'sheep'] as const).map(k => <label key={k} className="text-xs text-slate-500">{k === 'normal' ? '正剧挂载' : '羊挂载'}<select aria-label={k === 'normal' ? '方案正剧挂载' : '方案羊挂载'} className={field} value={String(cfg.groups[k].mount_required)} onChange={e => config({ groups: { ...cfg.groups, [k]: { ...cfg.groups[k], mount_required: e.target.value === 'true' } } })}><option value="true">挂载剧集</option><option value="false">不挂载</option></select></label>)}</div><p className="text-[11px] leading-5 text-slate-400">地址使用公共库中确认过的信息；使用方案不会更改账号默认地址。具体挂载剧集仍按当前账号和剧名匹配。</p></section>
      </fieldset>
    </div>
    <footer className="flex shrink-0 items-center justify-between gap-3 border-t border-slate-200 bg-white px-5 py-3"><div className="min-w-0"><p role={error ? 'alert' : 'status'} title={error || notice} className={`h-4 truncate text-xs ${error ? 'text-rose-700' : 'text-emerald-700'}`}>{busy ? `${busy}中…` : error || notice || (dirty ? '方案有未保存的修改' : '保存方案后，新任务按默认规则带入。')}</p><p className="mt-1 text-[10px] text-slate-400">方案保存封面选项和自定义图片；账号、视频和具体发布日期时间不存入方案。</p></div><div className="flex shrink-0 gap-2"><button className={button} disabled={!!busy} onClick={() => void perform('保存方案', () => save(false))}><Save size={13} />保存方案</button><button className="rounded-xl bg-[#1A1D2E] px-4 py-2 text-xs font-black text-[#DDFD00] disabled:opacity-40" disabled={!!busy} onClick={() => void perform('保存方案', () => save(true))}>保存并应用当前任务</button></div></footer>
  </div>{confirmation}</div>, document.body);
}
