import React, { useEffect, useMemo, useRef, useState } from 'react';
import { X, Check, Plus, Search, Download, Loader2, Smartphone, Tv, Puzzle, Square, AlertCircle } from 'lucide-react';
import { AccountItem, DramaItem, ScheduleTask } from '../types';
import { DramaCover } from './DramaCover';
import { DramaPagination } from './DramaPagination';
import { AccountAvatar } from './AccountAvatar';
import { DramaRenameModal } from './assets/modals/DramaRenameModal';
import { plannedDate, planningDayOffset, formatPlannedDate } from '../utils/plannedDate';
import { getV2Dramas, getV2DramaProfiles } from '../api/v2Catalog';
import { getCataloguePage, getCatalogueJob, latestCatalogueJob, startCatalogueSync, stopCatalogueJob, getMountChoices, linkCatalogueDrama, type CatalogueItem, type CatalogueJob, type MountChoice, type MountSource, type OnlineSource } from '../api/dramaCatalog';
import { refreshArea } from '../services/dataHub';

interface ScheduleModalProps {
  isOpen: boolean; onClose: () => void; accounts: AccountItem[]; dramas: DramaItem[];
  initialAccountId?: string; initialDramaId?: string; publishDateOffsetDays: number;
  theaters: { id: string; name: string }[];
  onCreateDrama: (data: { currentName: string; historyNames: string[]; theaterName: string; theaterId: string }) => Promise<DramaItem>;
  onSaveSchedule: (tasks: Omit<ScheduleTask, 'id'>[]) => void | boolean | Promise<void | boolean>;
}
const methods = [
  { id: 'mini_drama', label: '小程序', detail: '小程序短剧挂载', icon: Smartphone },
  { id: 'channels_drama', label: '视频号', detail: '视频号剧集挂载', icon: Tv },
  { id: 'plugin', label: '插件', detail: '使用现有剧集资料', icon: Puzzle },
] as const;
const activeJob = (job: CatalogueJob | null) => Boolean(job && ['queued', 'running', 'stopping'].includes(job.status));
const button = 'px-3 py-2 rounded-xl border border-slate-200 bg-white text-xs font-bold hover:border-slate-400 disabled:opacity-40 disabled:cursor-not-allowed';

export const ScheduleModal: React.FC<ScheduleModalProps> = ({ isOpen, onClose, accounts, dramas, initialAccountId, initialDramaId, publishDateOffsetDays, theaters, onCreateDrama, onSaveSchedule }) => {
  const [mountSource, setMountSource] = useState<MountSource | ''>('');
  const [accountIds, setAccountIds] = useState<string[]>([]);
  const [dramaIds, setDramaIds] = useState<string[]>([]);
  const [localDramas, setLocalDramas] = useState<DramaItem[]>(dramas);
  const [tab, setTab] = useState<'local' | OnlineSource>('local');
  const [query, setQuery] = useState('');
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(24);
  const [catalogueError, setCatalogueError] = useState('');
  const [online, setOnline] = useState<{ items: CatalogueItem[]; total: number; page: number; scope: string }>({ items: [], total: 0, page: 1, scope: '' });
  const [queryAccount, setQueryAccount] = useState('');
  const [choices, setChoices] = useState<MountChoice[]>([]);
  const [chosen, setChosen] = useState<Record<string, string>>({});
  const [dates, setDates] = useState<Record<string, string>>({});
  const [uniformDate, setUniformDate] = useState(() => planningDayOffset(publishDateOffsetDays));
  const [mode, setMode] = useState<'usable' | 'all'>('usable');
  const [job, setJob] = useState<CatalogueJob | null>(null);
  const [refreshKey, setRefreshKey] = useState(0);
  const [loading, setLoading] = useState(false);
  const [choicesLoading, setChoicesLoading] = useState(false);
  const [copied, setCopied] = useState('');
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const [adding, setAdding] = useState(false);
  const [linking, setLinking] = useState<CatalogueItem | null>(null);
  const [linkDrama, setLinkDrama] = useState('');
  const initialized = useRef(false);
  const initialDramaApplied = useRef(false);
  const loadCounter = useRef(0);
  const lastRefresh = useRef(0);
  const selectedAccounts = accounts.filter(a => accountIds.includes(a.id));
  const theaterId = selectedAccounts[0]?.theaterId;
  const theaterName = selectedAccounts[0]?.theaterName;
  const accountKey = accountIds.join(',');
  const onlineScope = JSON.stringify([queryAccount, tab, query, mode, pageSize]);
  const visibleOnline = online.scope === onlineScope ? online : { items: [], total: 0, page: 1 };
  useEffect(() => { if (!copied) return; const timer = window.setTimeout(() => setCopied(''), 2200); return () => window.clearTimeout(timer); }, [copied]);
  const selectedDramas = dramaIds.map(id => localDramas.find(d => d.id === id)).filter((d): d is DramaItem => Boolean(d));

  useEffect(() => { setLocalDramas(previous => [...dramas, ...previous.filter(d => !dramas.some(p => p.id === d.id))]); }, [dramas]);
  useEffect(() => {
    if (!isOpen) { initialized.current = false; return; }
    if (initialized.current) return;
    initialized.current = true; initialDramaApplied.current = false;
    setMountSource(''); setTab('local'); setDramaIds([]); setChosen({}); setDates({}); setUniformDate(planningDayOffset(publishDateOffsetDays));
    setAccountIds(initialAccountId ? [initialAccountId] : []); setQuery(''); setPage(1); setError('');
    void latestCatalogueJob().then(latest => { setJob(latest); if (latest && !activeJob(latest)) { void refreshLocal().catch(() => undefined); void refreshArea('catalog'); } }).catch(() => undefined);
  }, [isOpen, initialAccountId]);
  useEffect(() => {
    if (!isOpen) return;
    const handler = (event: KeyboardEvent) => {
      if (event.key !== 'Escape') return;
      event.preventDefault(); event.stopPropagation();
      if (linking) setLinking(null); else if (adding) setAdding(false); else if (!saving) onClose();
    };
    document.addEventListener('keydown', handler, true);
    const previous = document.body.style.overflow; document.body.style.overflow = 'hidden';
    return () => { document.removeEventListener('keydown', handler, true); document.body.style.overflow = previous; };
  }, [isOpen, adding, linking, saving, onClose]);
  useEffect(() => {
    if (!accountIds.includes(queryAccount)) setQueryAccount(accountIds[0] || '');
    setDramaIds(previous => previous.filter(id => localDramas.some(d => d.id === id && d.theaterId === theaterId)));
  }, [accountKey, theaterId]);
  useEffect(() => { setPage(1); }, [query, tab, queryAccount, mode, pageSize]);
  useEffect(() => {
    if (!isOpen || !accountIds.length || !mountSource || mountSource === 'plugin') { setChoices([]); setChoicesLoading(false); return; }
    let cancelled = false; setChoicesLoading(true);
    void getMountChoices(accountIds, mountSource).then(r => {
      if (cancelled) return;
      setChoices(r.items);
      setDramaIds(previous => previous.filter(id => accountIds.every(accountId => r.items.some(choice => choice.account_id === accountId && choice.drama_id === id))));
    }).catch(e => { if (!cancelled) { setChoices([]); setError(e.message); } }).finally(() => { if (!cancelled) setChoicesLoading(false); });
    return () => { cancelled = true; };
  }, [isOpen, accountKey, mountSource, refreshKey]);
  useEffect(() => {
    if (!isOpen || !queryAccount || tab === 'local') { setLoading(false); setCatalogueError(''); return; }
    let cancelled = false; setLoading(true); setCatalogueError('');
    const timer = window.setTimeout(() => {
      void getCataloguePage(queryAccount, tab, query, page, mode === 'usable', pageSize).then(r => { if (!cancelled) { setOnline({ ...r, scope: onlineScope }); if (r.page !== page) setPage(r.page); } }).catch(e => { if (!cancelled) setCatalogueError(e.message || '读取目录失败，请重试'); }).finally(() => { if (!cancelled) setLoading(false); });
    }, 120);
    return () => { cancelled = true; window.clearTimeout(timer); };
  }, [isOpen, queryAccount, tab, query, page, refreshKey, mode, pageSize]);

  const refreshLocal = async () => {
    const sequence = ++loadCounter.current;
    const [rows, profiles] = await Promise.all([getV2Dramas(), getV2DramaProfiles()]);
    if (sequence !== loadCounter.current) return;
    const covers = new Map(profiles.items.map(p => [p.drama_id, p.cover_path ? `/api/v2/dramas/${p.drama_id}/cover?v=${encodeURIComponent(p.updated_at)}` : '']));
    setLocalDramas(rows.items.map(d => ({ id: d.id, name: d.current_name, theaterId: d.theater_id, theaterName: d.theater_name, totalEpisodes: d.official_total_episodes, coverUrl: covers.get(d.id), productionCount: d.production_count, lastScheduledAt: d.last_scheduled_at, activeProductionCount: d.active_production_count })));
    setRefreshKey(k => k + 1);
  };
  useEffect(() => {
    if (!isOpen || !job || !activeJob(job)) return;
    let cancelled = false;
    const timer = window.setTimeout(() => {
      void getCatalogueJob(job.id).then(async next => {
        if (cancelled) return;
        setJob(next);
        if (!activeJob(next) || next.fetched !== job.fetched || Date.now() - lastRefresh.current > 8000) {
          lastRefresh.current = Date.now();
          await refreshLocal();
          if (!activeJob(next)) {
            void refreshArea('catalog');
            window.dispatchEvent(new CustomEvent('v2-data-changed', { detail: { changeType: 'account_changed', accountId: 'catalog-sync' } }));
          }
        }
      }).catch(e => { if (!cancelled) { setError(e.message); setJob(current => current ? { ...current, status: 'error' } : null); } });
    }, 1500);
    return () => { cancelled = true; window.clearTimeout(timer); };
  }, [isOpen, job]);

  const choicesByTask = useMemo(() => { const result = new Map<string, MountChoice[]>(); for (const choice of choices) { const key = `${choice.account_id}:${choice.drama_id}`; const rows = result.get(key) || []; rows.push(choice); result.set(key,rows); } return result; }, [choices]);
  const mountChoices = (accountId: string, dramaId: string) => choicesByTask.get(`${accountId}:${dramaId}`) || [];
  useEffect(() => {
    if (!isOpen || !initialDramaId || initialDramaApplied.current || !mountSource || !accountIds.length) return;
    const drama = localDramas.find(d => d.id === initialDramaId && d.theaterId === theaterId);
    if (drama && (mountSource === 'plugin' || accountIds.every(id => (choicesByTask.get(`${id}:${drama.id}`) || []).length > 0))) {
      initialDramaApplied.current = true; setDramaIds([drama.id]);
    }
  }, [isOpen, initialDramaId, mountSource, accountKey, theaterId, choicesByTask, localDramas]);

  const allowed = (dramaId: string) => mountSource === 'plugin' || selectedAccounts.every(a => mountChoices(a.id, dramaId).length > 0);
  const localFiltered = useMemo(() => localDramas.filter(d => d.theaterId === theaterId && d.name.toLowerCase().includes(query.trim().toLowerCase())).sort((a, b) => (b.activeProductionCount || 0) - (a.activeProductionCount || 0) || (b.lastScheduledAt || '').localeCompare(a.lastScheduledAt || '') || (b.productionCount || 0) - (a.productionCount || 0) || a.name.localeCompare(b.name, 'zh-CN')), [localDramas, theaterId, query]);
  const total = tab === 'local' ? localFiltered.length : visibleOnline.total;
  const pages = Math.max(1, Math.ceil(total / pageSize));
  const currentPage = tab === 'local' ? Math.min(page, pages) : visibleOnline.page;
  useEffect(() => { if (tab === 'local' && page > pages) setPage(pages); }, [tab, page, pages]);
  const combinations = selectedAccounts.flatMap(account => selectedDramas.filter(d => d.theaterId === account.theaterId).map(drama => {
    const key = `${account.id}:${drama.id}`;
    const available = mountChoices(account.id, drama.id);
    const externalId = available.some(c => c.external_id === chosen[key]) ? chosen[key] : available.length === 1 ? available[0].external_id : '';
    return { account, drama, key, available, externalId };
  }));
  const ready = mountSource && combinations.length > 0 && combinations.every(c => (mountSource === 'plugin' || c.externalId) && plannedDate(dates[c.key] ?? uniformDate));
  const changeMethod = (source: MountSource) => {
    setMountSource(source); setDramaIds([]); setChosen({}); setChoices([]); setError('');
    setTab(source === 'plugin' ? 'local' : source);

  };
  const toggleAccount = (account: AccountItem) => {
    if (accountIds.includes(account.id)) setAccountIds(ids => ids.filter(id => id !== account.id));
    else if (!theaterId || theaterId === account.theaterId) setAccountIds(ids => [...ids, account.id]);
    setError('');
  };
  const toggleDrama = (id: string) => setDramaIds(ids => ids.includes(id) ? ids.filter(value => value !== id) : [...ids, id]);
  const selectOnline = (item: CatalogueItem) => {
    if (!item.drama_id || item.usable !== 1 || mountSource !== tab || !allowed(item.drama_id)) return;
    if (!localDramas.some(d => d.id === item.drama_id)) setLocalDramas(previous => [...previous, { id: item.drama_id!, name: item.current_name || item.name, theaterId, theaterName, coverUrl: item.coverUrl, totalEpisodes: item.mediaCount }]);
    setChosen(previous => ({ ...previous, [`${queryAccount}:${item.drama_id}`]: item.external_id }));
    if (!dramaIds.includes(item.drama_id)) setDramaIds(previous => [...previous, item.drama_id!]);
    else if (chosen[`${queryAccount}:${item.drama_id}`] === item.external_id) toggleDrama(item.drama_id);
  };
  const startSync = async () => {
    const source = tab === 'local' ? mountSource : tab;
    if (!source || source === 'plugin') return;
    setError('');
    try { setJob(await startCatalogueSync(accountIds, [source], mode)); }
    catch (e) { setError(e instanceof Error ? e.message : '获取失败'); }
  };
  const save = async () => {
    if (!ready || saving) return;
    setSaving(true); setError('');
    try {
      const result = await onSaveSchedule(combinations.map(c => ({ accountId: c.account.id, accountName: c.account.name, dramaId: c.drama.id, dramaName: c.drama.name, coverUrl: c.drama.coverUrl, colorPlaceholder: c.drama.colorPlaceholder, theaterName: c.account.theaterName, status: '待制作', publishTime: formatPlannedDate(dates[c.key] ?? uniformDate), plannedPublishAt: plannedDate(dates[c.key] ?? uniformDate), mountSource: mountSource as MountSource, mountExternalId: c.externalId })));
      if (result !== false) onClose(); else setError('有任务未能创建，请核对提示后重试；已成功创建的任务不会重复创建。');
    } catch (e) { setError(e instanceof Error ? e.message : '保存失败，请重试'); }
    finally { setSaving(false); }
  };
  const copyDramaName = async (name: string) => {
    try {
      if (navigator.clipboard?.writeText) await navigator.clipboard.writeText(name);
      else {
        const input = document.createElement('textarea');
        input.value = name; input.style.position = 'fixed'; input.style.opacity = '0';
        document.body.appendChild(input);
        try { input.select(); if (!document.execCommand('copy')) throw new Error('复制失败'); }
        finally { input.remove(); }
      }
      setCopied(`已复制剧名：${name}`);
    } catch { setError('复制失败，请重试。'); }
  };
  if (!isOpen) return null;
  return <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-xs p-4" onMouseDown={e => { if (e.target === e.currentTarget && !saving) onClose(); }}>
    <div id="schedule-side-panel" role="dialog" aria-modal="true" aria-label="安排制作任务" className="w-full max-w-[1280px] max-h-[92vh] rounded-3xl bg-[#F8FAFC] shadow-2xl border border-white/80 flex flex-col overflow-hidden">
      <header className="px-7 py-5 bg-white border-b border-slate-100 flex items-center justify-between shrink-0">
        <div><h3 className="font-extrabold text-lg text-[#1A1D2E]">安排今日制作与发布</h3><p className="text-xs text-slate-500 mt-1">选择挂载方式 → 运营账号 → 剧集 → 生成独立制作任务 {theaterName && <span className="ml-2 font-bold text-slate-700">· {theaterName}</span>}</p></div>
        <button onClick={onClose} disabled={saving} aria-label="关闭安排窗口" className="p-2 rounded-xl hover:bg-slate-100 text-slate-400"><X size={20} /></button>
      </header>
      <main className="p-6 space-y-5 overflow-y-auto min-h-0" style={{ overflowAnchor: 'none', scrollbarGutter: 'stable' }}>
        <section className="bg-white rounded-2xl border border-slate-200/70 p-5">
          <h4 className="font-extrabold text-sm mb-3">1　选择挂载方式</h4>
          <div className="grid grid-cols-3 gap-3">{methods.map(({ id, label, detail, icon: Icon }) => <button key={id} onClick={() => changeMethod(id)} aria-pressed={mountSource === id} className={`flex items-center gap-3 p-3.5 rounded-xl border text-left transition-all ${mountSource === id ? 'border-[#1A1D2E] bg-[#F8FBE8] ring-1 ring-[#1A1D2E]/10' : 'border-slate-200 hover:border-slate-400'}`}><span className={`p-2 rounded-xl ${mountSource === id ? 'bg-[#1A1D2E] text-[#DDFD00]' : 'bg-slate-100 text-slate-500'}`}><Icon size={19} /></span><span><strong className="block text-sm">{label}</strong><span className="block text-[11px] text-slate-500 mt-0.5">{detail}</span></span>{mountSource === id && <Check className="ml-auto" size={17} />}</button>)}</div>
        </section>
        <section className={`bg-white rounded-2xl border border-slate-200/70 p-5 ${!mountSource ? 'opacity-50' : ''}`}>
          <div className="flex items-center justify-between mb-3"><h4 className="font-extrabold text-sm">2　选择运营账号 <span className="text-xs font-normal text-slate-400">同一剧场可多选</span></h4><div className="flex items-center gap-3 text-xs"><button disabled={!mountSource} onClick={() => { const target = theaterId || accounts[0]?.theaterId; setAccountIds(accounts.filter(a => a.theaterId === target).map(a => a.id)); }} className="font-bold text-slate-600">全选本剧场账号</button><button onClick={() => setAccountIds([])} className="text-slate-400">清空</button><span className="bg-slate-100 rounded-lg px-2 py-1">已选 {accountIds.length} 个</span></div></div>
          <div data-testid="schedule-account-grid" aria-label="运营账号" className="grid grid-cols-2 lg:grid-cols-3 auto-rows-[64px] gap-2 max-h-[208px] overflow-y-auto pr-1" style={{ scrollbarGutter: 'stable' }}>{accounts.map(account => <button key={account.id} aria-label={`${account.name} ${account.theaterName || ''}`} disabled={!mountSource || Boolean(theaterId && account.theaterId !== theaterId)} onClick={() => toggleAccount(account)} className={`flex items-center gap-2.5 h-16 min-w-0 p-3 rounded-xl border text-left disabled:opacity-35 ${accountIds.includes(account.id) ? 'bg-[#F8FBE8] border-[#A6B751]' : 'bg-slate-50 border-slate-100 hover:border-slate-300'}`}><AccountAvatar name={account.name} url={account.avatarUrl} /><span className="min-w-0 flex-1"><strong className="text-xs block truncate">{account.name}</strong><span className="block truncate text-[10px] text-slate-500">{account.theaterName}</span></span><span className={`w-5 h-5 rounded-md border flex items-center justify-center ${accountIds.includes(account.id) ? 'bg-[#1A1D2E] text-[#DDFD00] border-[#1A1D2E]' : 'bg-white border-slate-300'}`}>{accountIds.includes(account.id) && <Check size={13} />}</span></button>)}</div>
        </section>
        <section className="bg-white rounded-2xl border border-slate-200/70 p-5 space-y-3">
          <div className="flex items-center justify-between"><h4 className="font-extrabold text-sm">3　选择剧集 <span className="text-xs font-normal text-slate-400">已选 {dramaIds.length} 部</span></h4><button disabled={!accountIds.length || !mountSource} onClick={() => setAdding(true)} className={button}><Plus className="inline mr-1" size={13} />新增剧集</button></div>
          <div className="flex items-center gap-2 flex-wrap"><div className="flex bg-slate-100 rounded-xl p-1">{([['local','现有剧集'],['mini_drama','小程序短剧'],['channels_drama','视频号剧集']] as const).map(([id, label]) => <button key={id} disabled={!mountSource || !accountIds.length} onClick={() => setTab(id)} className={`px-4 py-2 rounded-lg text-xs font-bold disabled:opacity-40 ${tab === id ? 'bg-white shadow-sm text-[#1A1D2E]' : 'text-slate-500'}`}>{label}</button>)}</div>
            {tab !== 'local' && <select aria-label="查看账号" value={queryAccount} onChange={e => setQueryAccount(e.target.value)} className={button}>{selectedAccounts.map(a => <option key={a.id} value={a.id}>{a.name}</option>)}</select>}
            <div className="ml-auto flex items-center gap-2"><select aria-label="获取范围" disabled={activeJob(job)} value={mode} onChange={e => setMode(e.target.value as 'usable' | 'all')} className={button}><option value="usable">获取可挂载</option><option value="all">获取全部</option></select><button disabled={!accountIds.length || !mountSource || (tab === 'local' && mountSource === 'plugin') || activeJob(job)} onClick={() => void startSync()} className={`${button.replace('bg-white','bg-[#1A1D2E]')} text-[#DDFD00] border-[#1A1D2E]`}><Download className="inline mr-1" size={13} />从小V获取</button></div>
          </div>
          <p className="text-[11px] text-slate-400">{tab === 'local' ? '显示所选剧场的全部现有剧集；小程序、视频号任务需有对应账号的挂载资料。' : '显示当前查看账号的挂载目录；获取后自动新建或关联剧集、补齐空封面。'}{tab !== 'local' && mountSource !== tab && <span className="text-amber-700 ml-1">当前仅浏览，使用此来源请在上方切换挂载方式。</span>}</p>
          {job && <div className="rounded-xl bg-slate-50 border border-slate-200 p-3 text-xs space-y-1.5" role="status"><div className="flex items-center gap-2 font-bold">{activeJob(job) ? <Loader2 size={14} className="animate-spin" /> : job.errors.length ? <AlertCircle size={14} className="text-amber-600" /> : <Check size={14} />}<span className="flex-1">{!activeJob(job) && job.errors.length ? '获取未完成，原有目录已保留' : job.message}</span>{activeJob(job) && <button onClick={() => void stopCatalogueJob(job.id).then(setJob).catch(e => setError(e.message))} className="text-slate-500 flex items-center gap-1"><Square size={12} />停止</button>}</div><p className="text-slate-500">已获取 {job.fetched} · 新建 {job.created} · 关联 {job.linked} · 更新 {job.updated} · 补封面 {job.covers} · 移出不可挂载 {job.removed || 0} {job.total_reported > 0 && `· 当前目录报告 ${job.total_reported} 部`}</p>{job.cover_errors > 0 && <p className="text-amber-700">{job.cover_errors} 张封面下载失败，重新获取时会重试。</p>}{job.errors.map((e,i) => <p key={i} className="text-amber-700">{e}</p>)}{activeJob(job) && <p className="text-slate-400">已获取且可挂载的剧集可直接选择并创建任务；关闭窗口后继续获取。</p>}</div>}
          {selectedDramas.length > 0 && <div className="flex flex-wrap gap-2 rounded-xl bg-[#F8FBE8] p-2.5">{selectedDramas.map(d => <button key={d.id} onClick={() => toggleDrama(d.id)} className="flex items-center gap-1 bg-white px-2.5 py-1.5 rounded-lg border border-slate-200 text-xs font-bold">{d.name}<X size={12} className="text-slate-400" /></button>)}</div>}
          <div className="relative"><Search size={15} className="absolute left-3 top-2.5 text-slate-400" /><input aria-label="搜索剧集" value={query} onChange={e => setQuery(e.target.value)} placeholder={tab === 'local' ? '搜索现有剧集' : '搜索已获取的剧集'} className="w-full pl-9 pr-3 py-2 rounded-xl border border-slate-200 bg-slate-50 text-xs outline-none focus:border-slate-400" /></div>
          <div className="rounded-xl border border-slate-200 overflow-hidden">
            <div className="flex items-center justify-between gap-3 px-3 py-2 bg-slate-50 rounded-t-xl border-b border-slate-100 text-[11px] text-slate-500">
              <span>点击选择 · 右键直接复制剧名 · 悬停查看全名</span>
              <span role="status" className="flex h-4 items-center gap-1.5 text-slate-400">{loading && <><Loader2 size={12} className="animate-spin" />正在读取第 {page} 页…</>}</span>
            </div>
            <div data-testid="schedule-drama-viewport" aria-label="可选剧集" aria-busy={loading} className="p-3" style={{ minHeight: total > 0 ? Math.ceil(pageSize / 4) * 130 + 12 : undefined, overflowAnchor: 'none' }} onContextMenu={event => {
              const card = (event.target as HTMLElement).closest<HTMLElement>('[data-drama-name]');
              if (!card?.dataset.dramaName) return;
              event.preventDefault(); void copyDramaName(card.dataset.dramaName);
            }}>
              {catalogueError && <div role="alert" className="mb-3 flex items-center justify-between gap-3 rounded-xl border border-amber-200 bg-amber-50 p-3 text-xs text-amber-800"><span>读取剧集失败：{catalogueError}。已有资料未清除。</span><button disabled={loading} className={button} onClick={() => setRefreshKey(key => key+1)}>重新读取</button></div>}
              {!accountIds.length ? <p className="p-10 text-center text-xs text-slate-400">请先选择挂载方式和运营账号</p> : <div data-testid="schedule-drama-grid" className="grid grid-cols-4 gap-3">
                {tab === 'local' ? localFiltered.slice((currentPage-1)*pageSize,currentPage*pageSize).map(drama => <div key={drama.id} data-drama-name={drama.name} className={`relative min-w-0 rounded-xl border p-2 ${dramaIds.includes(drama.id) ? 'border-[#A6B751] bg-[#F8FBE8]' : 'border-slate-200 bg-slate-50 hover:border-slate-400'}`}>
                  <button disabled={!allowed(drama.id)} onClick={() => toggleDrama(drama.id)} title={drama.name} className="flex w-full items-center gap-2.5 text-left">
                    <DramaCover name={drama.name} coverUrl={drama.coverUrl} size="lg" className="!w-[72px] !h-[100px] !rounded-lg" />
                    <span className="min-w-0 flex-1 h-[72px]"><strong className="h-8 line-clamp-2 break-all text-xs leading-4">{drama.name}</strong>
                    <span className="block h-4 truncate text-[10px] leading-4 text-slate-500 mt-1">生产 {drama.productionCount || 0} 次{drama.totalEpisodes ? ` · 官方 ${drama.totalEpisodes} 集` : ''}</span>
                    {mountSource !== 'plugin' && <span className={`block h-4 truncate text-[10px] leading-4 mt-1 ${choicesLoading && !allowed(drama.id) ? 'text-slate-400' : allowed(drama.id) ? 'text-emerald-700' : 'text-amber-700'}`} title={choicesLoading && !allowed(drama.id) ? '正在核对挂载资料' : allowed(drama.id) ? '所选账号均有可用挂载资料' : accountIds.length > 1 ? '部分所选账号暂无挂载资料' : '当前账号暂无挂载资料'}>{choicesLoading && !allowed(drama.id) ? '正在核对挂载资料…' : allowed(drama.id) ? '可挂载' : accountIds.length > 1 ? '部分所选账号暂无挂载资料' : '当前账号暂无挂载资料'}</span>}</span>
                  </button>{dramaIds.includes(drama.id) && <Check size={20} className="absolute right-3 top-3 p-0.5 rounded-full bg-[#DDFD00] text-[#1A1D2E] pointer-events-none" />}
                </div>) : visibleOnline.items.map(item => <div key={item.external_id} data-drama-name={item.name} className={`relative min-w-0 rounded-xl border p-2 ${item.drama_id && dramaIds.includes(item.drama_id) && chosen[`${queryAccount}:${item.drama_id}`] === item.external_id ? 'border-[#A6B751] bg-[#F8FBE8]' : 'border-slate-200 bg-slate-50 hover:border-slate-400'}`}>
                  <button aria-label={`选择挂载剧集 ${item.name}`} onClick={() => selectOnline(item)} title={item.name} disabled={loading || item.usable !== 1 || !item.drama_id || mountSource !== tab || !allowed(item.drama_id)} className="flex w-full items-center gap-2.5 text-left disabled:opacity-50">
                    <DramaCover name={item.name} coverUrl={item.coverUrl} size="lg" className="!w-[72px] !h-[100px] !rounded-lg" />
                    <span className="min-w-0 flex-1 h-[72px]"><strong className="h-8 line-clamp-2 break-all text-xs leading-4">{item.name}</strong>
                    <span className="block h-4 truncate text-[10px] leading-4 text-slate-500 mt-1" title={item.miniAppName}>{item.mediaCount || '—'} 集 {item.miniAppName && `· ${item.miniAppName}`}</span>
                    <span title={item.reason} className={`block h-4 truncate text-[10px] leading-4 mt-1 ${item.usable === 1 ? 'text-emerald-700' : 'text-amber-700'}`}>{item.usable === 1 ? (item.drama_id ? '可挂载 · 已入库' : '可挂载 · 待关联') : item.reason || '尚未确认可挂载'}</span></span>
                  </button>{item.drama_id && dramaIds.includes(item.drama_id) && chosen[`${queryAccount}:${item.drama_id}`] === item.external_id && <Check size={20} className="absolute right-3 top-3 p-0.5 rounded-full bg-[#DDFD00] text-[#1A1D2E] pointer-events-none" />}
                  {!item.drama_id && <button disabled={loading} onClick={() => { setLinking(item); setLinkDrama(''); }} className="text-[11px] text-indigo-700 mt-2 font-bold">{item.issue || '关联已有剧集'}</button>}
                </div>)}
              </div>}
              {accountIds.length > 0 && !loading && !catalogueError && total === 0 && <p className="p-10 text-center text-xs text-slate-400">{tab === 'local' ? '当前剧场暂无匹配的现有剧集，可新增或调整搜索条件' : '该账号当前暂无匹配的可挂载剧集，可重新获取或调整搜索条件'}</p>}
            </div>
            <div data-testid="schedule-drama-pagination" className="rounded-b-xl px-3 py-3 border-t border-slate-100 bg-white">
              <DramaPagination total={total} page={Math.min(currentPage,pages)} pageSize={pageSize} disabled={loading}
                onPageChange={setPage} onPageSizeChange={size => { setPageSize(size); setPage(1); }} />
            </div>
          </div>
        </section>
        <section className="bg-white rounded-2xl border border-slate-200/70 p-5 space-y-3">
          <div className="flex items-center justify-between"><h4 className="font-extrabold text-sm">4　制作任务清单与计划日期</h4><span className="text-xs font-bold rounded-full bg-[#1A1D2E] text-[#DDFD00] px-3 py-1.5">{accountIds.length} 账号 × {dramaIds.length} 剧集 = {combinations.length} 个任务</span></div>
          <div className="flex items-center gap-3 flex-wrap rounded-xl bg-slate-50 border border-slate-200 p-3 text-xs"><span className="text-slate-500">只安排日期，具体发布时间在自动发布中设置</span><label className="ml-auto flex items-center gap-2 font-bold text-slate-600">统一日期<input aria-label="统一计划日期" type="date" value={uniformDate} onChange={e => { setUniformDate(e.target.value); setDates({}); }} className="px-2 py-1.5 bg-white border border-slate-200 rounded-lg" /></label></div>
          <div className="max-h-72 overflow-y-auto space-y-2">{combinations.map(c => <div key={c.key} className="flex items-center gap-3 rounded-xl bg-slate-50 border border-slate-200 p-3 text-xs"><span className="min-w-0 flex-1"><strong className="block truncate">{c.drama.name}</strong><span className="text-slate-500">{c.account.name} · {methods.find(m => m.id === mountSource)?.label}</span></span>{mountSource !== 'plugin' && <select aria-label={`${c.account.name}的挂载剧集`} value={c.externalId} onChange={e => setChosen(previous => ({ ...previous,[c.key]:e.target.value }))} className={`${button} max-w-[260px]`}><option value="">请选择具体挂载剧集</option>{c.available.map(choice => <option key={choice.external_id} value={choice.external_id}>{choice.name}{choice.miniAppName ? ` · ${choice.miniAppName}` : ''}</option>)}</select>}{<input aria-label={`${c.account.name}的计划日期`} type="date" value={dates[c.key] ?? uniformDate} onChange={e => setDates(previous => ({ ...previous,[c.key]:e.target.value }))} className="border border-slate-200 rounded-xl px-2 py-2 bg-white" />}</div>)}</div>
          {combinations.length === 0 && <p className="py-6 text-xs text-slate-400 text-center">选择账号与剧集后在此核对任务</p>}
        </section>
        {error && <div role="alert" className="p-3 bg-rose-50 border border-rose-100 rounded-xl text-xs text-rose-700 flex items-start gap-2"><AlertCircle size={15} className="shrink-0" />{error}</div>}
      </main>
      <footer className="px-6 py-4 bg-white border-t border-slate-100 flex justify-between items-center shrink-0"><span className="text-xs text-slate-400">{!mountSource ? '请先选择挂载方式' : !ready && combinations.length ? '请核对每个账号的挂载剧集和计划日期' : '任务创建后保留本次挂载选择'}</span><div className="flex gap-3"><button onClick={onClose} disabled={saving} className={button}>取消</button><button id="btn-confirm-save-schedule" disabled={!ready || saving} onClick={() => void save()} className="bg-[#DDFD00] text-[#1A1D2E] px-5 py-2.5 rounded-xl font-extrabold text-sm disabled:opacity-40 disabled:cursor-not-allowed">{saving ? '正在保存…' : `保存并加入今日安排（${combinations.length}）`}</button></div></footer>
    </div>
    {copied && <div role="status" className="fixed bottom-24 left-1/2 z-[80] max-w-[80vw] -translate-x-1/2 truncate rounded-xl bg-slate-800 px-4 py-2.5 text-xs text-white shadow-lg">{copied}</div>}
    {adding && <DramaRenameModal isOpen onClose={() => setAdding(false)} drama={null} theaters={theaters.filter(t => t.id === theaterId)} lockedTheaterName={theaterName} onSave={async data => { try { const drama = await onCreateDrama(data); setLocalDramas(previous => [drama,...previous.filter(d => d.id !== drama.id)]); if (mountSource === 'plugin') setDramaIds(previous => [...previous,drama.id]); setAdding(false); setTab('local'); } catch (e) { setError(e instanceof Error ? e.message : '新建失败'); } }} />}
    {linking && <div className="fixed inset-0 z-60 bg-black/40 flex items-center justify-center p-5" onMouseDown={e => { if (e.target === e.currentTarget) setLinking(null); }}><div role="dialog" aria-modal="true" aria-label="关联已有剧集" className="bg-white rounded-3xl p-6 w-full max-w-md shadow-2xl space-y-4"><div className="flex items-center justify-between"><h4 className="font-extrabold">关联已有剧集</h4><button aria-label="关闭关联窗口" onClick={() => setLinking(null)}><X size={18} /></button></div><p className="text-xs text-slate-500">{linking.name} · {linking.issue || '选择同一剧场的对应剧集'}</p><select aria-label="对应本地剧集" value={linkDrama} onChange={e => setLinkDrama(e.target.value)} className={`${button} w-full`}><option value="">请选择</option>{localDramas.filter(d => d.theaterId === theaterId).map(d => <option key={d.id} value={d.id}>{d.name}</option>)}</select><button disabled={!linkDrama} className={`${button} w-full`} onClick={() => { if (tab !== 'local') void linkCatalogueDrama(queryAccount,tab,linking.external_id,linkDrama).then(() => { setLinking(null); void refreshLocal(); }).catch(e => setError(e.message)); }}>确认关联</button></div></div>}
  </div>;
};
