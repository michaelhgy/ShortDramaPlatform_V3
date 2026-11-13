import { PublishingCoverControl } from './PublishingCoverControl';
import React, { useEffect, useMemo, useRef, useState } from 'react';
import { AlertCircle, CheckCircle2, ChevronDown, Copy, FileCheck2, Film, LoaderCircle, MapPin, Pause, Play, Plus, RefreshCw, Search, Square, Trash2, X } from 'lucide-react';
import { getPublishing, getPublishingAddressBook, getDraftExecution, getPublication, publishingAction, savePublishing, type PublishingData, type PublishingAddressBook, type PublishGroup, type LocationValue, type MountDrama, type MountBinding, type DramaSearchResult, type ProfileLibrary, type PublishSettings } from '../../api/publishing';
import { expandedPreview, expandedTimeline, effectiveGroups, coverForVideo, moveVideo } from './publishingModel';
import { DramaTaskCover } from './DramaTaskCover';
import { formatElapsedSeconds } from '../../utils/duration';
import { intervalMinutes, intervalLabel, declarationOptions } from './publishingOptions';
import { PublishingHistoryField as HistoryField } from './PublishingHistoryField';
import { usePublishingConfirm } from './PublishingConfirm';
import { eventDetail } from '../../services/dataChangeEvents';
import { PublishingProfileManager } from './PublishingProfileManager';
import { PublishingProfileApply } from './PublishingProfileApply';
import { taskProfileState, profileMatchesSettings } from './publishingProfileModel';
import type { MountSource } from '../../api/dramaCatalog';
import { beijingDateString } from '../../utils/beijingTime';

const field = 'w-full rounded-xl border border-slate-200 bg-white px-2.5 py-1.5 text-xs outline-none focus:border-slate-500 focus:ring-2 focus:ring-slate-100 disabled:bg-slate-100';
const button = 'inline-flex shrink-0 whitespace-nowrap items-center justify-center gap-1.5 rounded-lg border border-slate-200 bg-white px-3 py-2 text-xs font-bold text-slate-700 hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-50';
const section = 'rounded-xl border border-slate-200 bg-white p-3 space-y-2.5';
const labels: Record<string, string> = { pending: '待处理', creating: '正在创建', checking: '正在核对', ready: '草稿已就绪', needs_help: '需要处理', uncertain: '结果待核对',submitting:'正在提交',submitted:'已加入发布队列',publishing:'小V猫正在处理',success:'发布提交成功',failed:'发布失败',rejected:'提交未完成',canceled:'已取消',paused:'小V猫已暂停',localTiming:'等待本机定时',abandoned:'已作废' };
type ScheduleRetryPlan = { keys: string[]; start_time: string; interval: number; items: { key: string; name: string; copy: number; status?: string; remote_state?: string; old_time: string; new_time: string; selected?: boolean }[] };
type RepublishResetItem = { key: string; name: string; copy: number; status?: string; remote_state?: string; reason?: string };
type RepublishResetPlan = { ready: boolean; success: RepublishResetItem[]; cancelled: RepublishResetItem[]; terminal: RepublishResetItem[]; pending: RepublishResetItem[]; blocked: RepublishResetItem[] };

export function PublishingWorkbench({ taskId, onClose, showToast }: { key?: string; taskId: string; onClose: () => void; showToast: (text: string) => void }) {
  const { confirm, confirmation } = usePublishingConfirm();
  const [data, setData] = useState<PublishingData | null>(null);
  const [selectedId, setSelectedId] = useState('');
  const [busy, setBusy] = useState('');
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [customInterval, setCustomInterval] = useState(false);
  useEffect(() => { if (!notice) return; const timer = setTimeout(() => setNotice(''), 4000); return () => clearTimeout(timer); }, [notice]);
  const [connection, setConnection] = useState('未检查连接');
  const [locationQuery, setLocationQuery] = useState('');
  const [tagsText, setTagsText] = useState('');
  const [locationRows, setLocationRows] = useState<LocationValue[]>([]);
  const [dramaQuery, setDramaQuery] = useState('');
  const [dramaRows, setDramaRows] = useState<MountDrama[]>([]);
  const [matchMessage, setMatchMessage] = useState('');
  const [accountOnly, setAccountOnly] = useState(false);
  const [issues, setIssues] = useState<{ group_id: string; message: string }[]>([]);
  const [showPreview, setShowPreview] = useState(false);
  const [dirty, setDirty] = useState(false);
  const [advanced, setAdvanced] = useState(false);
  const [addressEditing, setAddressEditing] = useState(false);
  const [addressLibrary, setAddressLibrary] = useState<'account' | 'public'>('public');
  const [addressFilter, setAddressFilter] = useState('');
  const [mountEditing, setMountEditing] = useState(false);
  const [showAllVideos, setShowAllVideos] = useState(false);
  const [profilesOpen, setProfilesOpen] = useState(false);
  const [applyProfileId, setApplyProfileId] = useState('');
  const [statusFilter, setStatusFilter] = useState('all');
  const [selectedTaskKeys, setSelectedTaskKeys] = useState<string[]>([]);
  const [republishMode, setRepublishMode] = useState(false);
  const [republishResetOpen, setRepublishResetOpen] = useState(false);
  const [republishResetPlan, setRepublishResetPlan] = useState<RepublishResetPlan | null>(null);
  const [scheduleRetryOpen, setScheduleRetryOpen] = useState(false);
  const [scheduleRetryPlan, setScheduleRetryPlan] = useState<ScheduleRetryPlan | null>(null);
  const [scheduleRetryStart, setScheduleRetryStart] = useState('');
  const [scheduleRetryInterval, setScheduleRetryInterval] = useState(5);
  const profileInfo = useMemo(() => data ? taskProfileState(data.settings, data.profile_library) : null, [data?.settings, data?.profile_library]);
  const matchesProfile = useMemo(() => data ? profileMatchesSettings(data.settings, data.profile_library?.items.find(p => p.id === data.settings.profile_ref?.id), data.default_address, data.public_addresses) : false, [data?.settings, data?.profile_library, data?.default_address, data?.public_addresses]);
  const pendingProfile = data?.profile_library?.items.find(p => p.id === applyProfileId);
  const generation = useRef(0);
  const autoMatched = useRef(false);
  const mounted = useRef(true);
  const isPlugin = data?.settings.mount_source === 'plugin';
  const execution = isPlugin ? data?.execution : data?.publication;
  const running = Boolean(data?.execution.running || data?.publication?.running);
  const watching = running || (!isPlugin && Boolean(execution?.items.some(i => ['submitted','publishing','localTiming'].includes(i.status))));
  const timedGroups = useMemo(() => data ? effectiveGroups(data.settings) : [], [data?.settings]);
  const group = timedGroups.find(g => g.id === selectedId) || timedGroups[0];
  useEffect(() => {
    const changed = (event: Event) => {
      if (eventDetail(event).changeType !== 'profile_changed') return;
      void getPublishing(taskId).then(value => setData(current => current ? { ...current, cover: value.cover, sheep_cover: value.sheep_cover, sheep_cover_visible: value.sheep_cover_visible } : current)).catch(e => setError(e.message));
    };
    window.addEventListener('v2-data-changed', changed); return () => window.removeEventListener('v2-data-changed', changed);
  }, [taskId]);
  useEffect(() => {
    mounted.current = true;
    getPublishing(taskId).then(value => { if (mounted.current) { setData(value); setSelectedId(value.settings.groups[0]?.id || ''); const publication=value.publication; if (publication?.reset_status==='ready') setRepublishMode(true); if (publication?.reset_plan && ['blocked','awaiting_manual_cleanup'].includes(publication.reset_status || '')) { setRepublishResetPlan(publication.reset_plan as RepublishResetPlan); setRepublishResetOpen(true); } } }).catch(e => setError(e.message));
    return () => { mounted.current = false; generation.current++; };
  }, [taskId]);
  useEffect(() => { generation.current++; setLocationRows([]); setLocationQuery(''); setAddressEditing(false); setShowAllVideos(false); setTagsText(group?.tags.join(' ') || ''); }, [group?.id]);
  useEffect(() => {
    if (!data || !watching) return;
    let active = true; let timer: ReturnType<typeof setTimeout>;
    const poll = async () => {
      try { const value = await (isPlugin ? getDraftExecution(taskId) : getPublication(taskId)); if (active) setData(current => current ? { ...current, [isPlugin ? 'execution' : 'publication']: value } : current); }
      catch (e) { if (active) setError(e instanceof Error ? e.message : '读取进度失败'); }
      if (active) timer = setTimeout(poll, isPlugin ? 1500 : 4000);
    };
    timer = setTimeout(poll, 500);
    return () => { active = false; clearTimeout(timer); };
  }, [taskId, watching, isPlugin]);
  async function perform(label: string, action: () => Promise<void>) {
    setBusy(label); setError(''); setNotice('');
    try { await action(); } catch (e) { if (mounted.current) setError(e instanceof Error ? e.message : '操作未完成，请重试'); }
    finally { if (mounted.current) setBusy(''); }
  }
  function updateGroup(id: string, patch: Partial<PublishGroup>) {
    setData(current => {
      if (!current) return current;
      const source=current.settings.groups.find(g => g.id === id);
      const sync='location' in patch && current.settings.sync_location && (source?.kind === 'normal' || source?.kind === 'sheep');
      return { ...current, settings: { ...current.settings, assignment_mode: patch.name !== undefined ? 'manual' : current.settings.assignment_mode, assignment_confirmed: patch.name !== undefined ? true : current.settings.assignment_confirmed,
        groups: current.settings.groups.map(g => g.id === id ? { ...g, ...patch } : sync && (g.kind === 'normal' || g.kind === 'sheep') ? { ...g, location: patch.location ?? null } : g) } };
    }); setDirty(true);
  }
  function setLocationSync(sync: boolean) {
    setData(current => current ? { ...current, settings: { ...current.settings, sync_location: sync,
      groups: current.settings.groups.map(g => sync && (g.kind === 'normal' || g.kind === 'sheep') ? { ...g, location: group?.location ?? null } : g) } } : current);
    setDirty(true);
  }
  async function save() {
    if (!data) throw Error('设置尚未读取');
    const result = await savePublishing(taskId, data.settings);
    if (mounted.current) { setData(result); setDirty(false); }
    return result;
  }
  async function match(query = '', prepared?: PublishingData) {
    if (!prepared) await save();
    const result = await publishingAction<DramaSearchResult>(taskId, 'dramas', { query });
    if (!mounted.current) return;
    setDramaRows(result.items); setMatchMessage(result.message || (result.status === 'auto' ? '名称一致或仅符号差异，已自动关联。' : result.status === 'bound' ? '已复用原关联，当前账号可挂载。' : '文字不同或存在多个候选，请人工确认。'));
    setMountEditing(!['auto', 'bound'].includes(result.status));
    setData(current => current ? { ...current, binding: result.binding } : current);
  }
  async function changeMountSource(source: MountSource) {
    if (!data || source === data.settings.mount_source) return;
    await perform('切换挂载方式', async () => {
      const next=await savePublishing(taskId,{...data.settings,mount_source:source});
      setData(next);setDirty(false);setDramaRows([]);setDramaQuery('');setMountEditing(false);setIssues([]);setMatchMessage('');
      if (source !== 'plugin' && next.settings.groups.some(g => g.mount_required)) await match('',next);
      setNotice('挂载方式已保存到当前任务的发布设置。');
    });
  }
  useEffect(() => {
    if (!data || autoMatched.current || running) return;
    autoMatched.current = true;
    void perform('自动匹配', async () => {
      const result = await publishingAction<{ message: string }>(taskId, 'connection');
      setConnection(result.message);
      if (data.settings.mount_source !== 'plugin' && data.settings.groups.some(g => g.mount_required)) await match();
    });
  }, [Boolean(data), running]);
  const preview = useMemo(() => group && data ? expandedPreview(group, data.videos) : [], [group, data?.videos]);
  const timeline = useMemo(() => data ? expandedTimeline(data.settings, data.videos) : [], [data?.settings, data?.videos]);
  const assignedVideos = group && data ? group.video_ids.flatMap(id => data.videos.find(v => v.id === id) || []) : [];
  const coverKinds = assignedVideos.length ? [...new Set<boolean>(assignedVideos.map(v => v.sheep))] : [group?.kind === 'sheep'];
  const schedule = data?.settings.schedule || { schedule_type: group?.schedule_type || 'now', start_time: group?.start_time || '', interval: group?.interval ?? 3 };
  function updateSchedule(patch: Partial<typeof schedule>) {
    setData(current => current ? { ...current, settings: { ...current.settings, schedule: { ...schedule, ...patch } } } : current); setDirty(true);
  }
  const count = data?.settings.groups.reduce((sum, g) => sum + g.video_ids.length * Math.max(1, Math.floor(g.copies || 1)), 0) || 0;
  const results = execution?.items || [];
  const visibleResults = results.filter(item => statusFilter === 'all' || item.status === statusFilter || item.remote_state === statusFilter);
  const hasPending = results.some(item => item.status === 'pending' && !item.local_id);
  const remoteActive = !isPlugin && results.some(item => item.local_id && (['submitted','publishing','localTiming'].includes(item.status) || ['waiting','publishing','localTiming'].includes(item.remote_state || '')));
  const ready = results.filter(item => ['ready','success'].includes(item.status)).length;
  const needsHelp = results.filter(item => ['needs_help', 'uncertain','failed','rejected','canceled'].includes(item.status)).length;
  const disabled = Boolean(busy || running || remoteActive);
  const title = '发布工作台';
  const close = async () => { if (busy) return; if (dirty && !await confirm({ title: '关闭发布工作台', message: '还有未保存的发布设置。关闭后，本次未保存的修改不会保留。', confirmText: '放弃修改并关闭' })) return; onClose(); };
  useEffect(() => {
    const escape = (event: KeyboardEvent) => {
      if (event.key !== 'Escape' || event.repeat || event.defaultPrevented) return;
      // A history picker or confirmation owns Escape until it is dismissed.
      if (document.querySelector('[role="alertdialog"], [data-publishing-history], [data-publishing-profiles], [data-publishing-profile-apply]')) return;
      event.preventDefault(); event.stopPropagation(); void close();
    };
    window.addEventListener('keydown', escape);
    return () => window.removeEventListener('keydown', escape);
  }, [dirty, confirm, onClose]);
  async function deleteHistory(key: string, value: string) {
    await perform('删除历史', async () => {
      await publishingAction(taskId, 'history-delete', { key, value });
      setData(current => current ? { ...current, history: { ...current.history, [key]: current.history[key].filter(text => text !== value) } } : current);
    });
  }
  function toggleTask(key: string, checked: boolean) {
    setSelectedTaskKeys(current => checked ? [...new Set([...current, key])] : current.filter(value => value !== key));
  }
  function selectVisible(checked: boolean) {
    const keys = visibleResults.map(item => item.key);
    setSelectedTaskKeys(current => checked ? [...new Set([...current, ...keys])] : current.filter(key => !keys.includes(key)));
  }
  async function manageTasks(operation: "pause" | "retry" | "cancel" | "continue") {
    const selected = results.filter(item => selectedTaskKeys.includes(item.key));
    if (!selected.length) { setNotice("请先选择发布任务。"); return; }
    const label = operation === "pause" ? "暂停" : operation === "retry" ? "重发" : operation === "continue" ? "继续提交" : "取消";
    if (operation === 'continue' && selected.some(item => !['pending','rejected'].includes(item.status) || item.local_id)) { setNotice("继续提交只能选择尚未进入小V猫的待处理或明确拒绝任务。"); return; }
    if (!await confirm({ title: label + "发布任务", message: "将对选中的 " + selected.length + " 条任务执行“" + label + "”。已发布任务不会被重发；正在发布任务取消后仍需以平台结果为准。", confirmText: "确认" + label })) return;
    await perform(label + "发布任务", async () => {
      const result = operation === 'continue'
        ? await publishingAction<{ accepted?: boolean; target?: string }>(taskId, 'continue', { keys: selected.map(item => item.key) })
        : await publishingAction<{ changed: string[]; skipped: { key: string; reason: string }[] }>(taskId, "task-operation", { operation, keys: selected.map(item => item.key) });
      const publication = await getPublication(taskId);
      setData(current => current ? { ...current, publication } : current);
      setSelectedTaskKeys([]);
      if (operation === 'continue') { setNotice('已继续提交尚未进入小V猫的任务。'); return; }
      const managed = result as { changed: string[]; skipped: { key: string; reason: string }[] };
      const reasons = [...new Set(managed.skipped.map(item => item.reason))].slice(0, 3);
      setNotice(label + "完成：" + managed.changed.length + " 条" + (managed.skipped.length ? "，跳过 " + managed.skipped.length + " 条。" + reasons.join('；') : "。"));
    });
  }
  async function beginRepublish() {
    if (data?.publication?.reset_status==='ready') { setRepublishMode(true); setNotice('旧批次已确认作废。现在可以修改设置并按新设置发布。'); return; }
    if (!await confirm({ title: "重新发布：整批作废重来", message: "这不是普通重发。系统会先取消小V猫中仍可取消的旧任务；你还需要人工进入官方账号后台，删除已经上传成功的视频。确认旧批次不再需要后，才能创建一批全新的发布任务。", confirmText: "准备整批作废" })) return;
    await perform('准备重新发布', async () => {
      const plan = await publishingAction<RepublishResetPlan>(taskId, 'republish-prepare', {});
      setRepublishResetPlan(plan); setRepublishResetOpen(true);
      const publication = await getPublication(taskId); setData(current => current ? { ...current, publication } : current);
    });
  }
  async function confirmRepublishReset() {
    if (!republishResetPlan?.ready) return;
    if (!await confirm({ title: '确认旧批次已作废', message: '请确认：旧任务已按提示取消；官方账号后台中已经上传成功的视频已由人工删除；旧批次不再需要。确认后才能创建新批次。', confirmText: '确认并进入重新发布' })) return;
    await perform('确认旧批次作废', async () => {
      const publication = await publishingAction<unknown>(taskId, 'republish-ready', {});
      setData(current => current ? { ...current, publication: publication as PublishingData['publication'] } : current);
      setRepublishResetOpen(false); setSelectedTaskKeys([]); setRepublishMode(true); setNotice('旧批次已标记作废。现在可以修改自动发布设置，最后点击“按新设置发布”。');
    });
  }
  async function beginScheduleRetry() {
    await perform('读取排期重发任务', async () => {
      const result = await publishingAction<ScheduleRetryPlan>(taskId, 'schedule-retry-preview', { keys: selectedTaskKeys.length ? selectedTaskKeys : undefined });
      setScheduleRetryPlan(result); setScheduleRetryStart(result.start_time); setScheduleRetryInterval(result.interval); setScheduleRetryOpen(true);
    });
  }
  async function changeScheduleRetryStart(value: string) {
    setScheduleRetryStart(value);
    if (!value || !scheduleRetryPlan) return;
    try {
      const result = await publishingAction<ScheduleRetryPlan>(taskId, 'schedule-retry-preview', { keys: scheduleRetryPlan.keys, start_time: value, interval: scheduleRetryInterval });
      setScheduleRetryPlan(result);
    } catch (e) { setError(e instanceof Error ? e.message : String(e)); }
  }
  async function changeScheduleRetryInterval(value: number) {
    const interval=Math.max(0,Math.floor(value)); setScheduleRetryInterval(interval);
    if (!scheduleRetryPlan) return;
    try {
      const result=await publishingAction<ScheduleRetryPlan>(taskId,'schedule-retry-preview',{keys:scheduleRetryPlan.keys,start_time:scheduleRetryStart,interval});
      setScheduleRetryPlan(result);
    } catch (e) { setError(e instanceof Error ? e.message : String(e)); }
  }
  async function changeScheduleRetryKeys(keys: string[]) {
    const unique=[...new Set(keys)];
    if (!unique.length) {
      setScheduleRetryPlan(current => current ? { ...current, keys: [], items: current.items.map(item => ({ ...item, new_time: '' })) } : current);
      return;
    }
    try {
      const result=await publishingAction<ScheduleRetryPlan>(taskId,'schedule-retry-preview',{keys:unique,start_time:scheduleRetryStart,interval:scheduleRetryInterval});
      setScheduleRetryPlan(result);
    } catch (e) { setError(e instanceof Error ? e.message : String(e)); }
  }
  async function confirmScheduleRetry() {
    if (!scheduleRetryPlan || !scheduleRetryStart) return;
    if (!await confirm({ title: '确认排期重发', message: `将按 ${scheduleRetryStart} 开始，重新创建 ${scheduleRetryPlan.keys.length} 条小V猫任务。原任务保留，视频参数不变，只调整发布时间。`, confirmText: '确认排期重发' })) return;
    setScheduleRetryOpen(false);
    await perform('排期重发', async () => {
      await publishingAction(taskId, 'schedule-retry', { keys: scheduleRetryPlan.keys, start_time: scheduleRetryStart, interval: scheduleRetryInterval });
      setData(current => current ? { ...current, publication: { ...(current.publication || { items: [] }), running: true, state: 'running' } } : current);
      setScheduleRetryPlan(null); setSelectedTaskKeys([]);
    });
  }
  async function useAddress(address: LocationValue, asDefault = false, select = true) {
    const book = await publishingAction<PublishingAddressBook>(taskId, 'address-save', { address, default: asDefault });
    setData(current => current ? { ...current, ...book } : current);
    if (select && group) { updateGroup(group.id, { location: address }); setAddressEditing(false); setLocationRows([]); }
    setNotice(asDefault ? '已设为当前账号默认地址，其他账号不受影响。' : '已带入地址，并保存到公共地址库。');
  }
  const libraryAddresses = data ? (addressLibrary === 'public' ? data.public_addresses || [] : data.addresses).filter(loc => `${loc.name || ''} ${loc.city || ''} ${loc.fullAddress || ''}`.toLocaleLowerCase().includes(addressFilter.trim().toLocaleLowerCase())) : [];
  function profileLibraryChanged(library: ProfileLibrary) { setData(current => current ? { ...current, profile_library: library } : current); }
  async function applyProfile(settings: PublishSettings) {
    const result = await savePublishing(taskId, settings);
    if (!mounted.current) return;
    setData(result); setDirty(false); setApplyProfileId(''); setIssues([]); setCustomInterval(false); setAddressEditing(false);
    setTagsText((result.settings.groups.find(g => g.id === selectedId) || result.settings.groups[0])?.tags.join(' ') || '');
    setNotice('方案已应用并保存到当前任务。');
  }
  return <div className="fixed inset-0 z-[100] flex items-center justify-center bg-slate-950/40 p-3 backdrop-blur-sm" role="dialog" aria-modal="true" aria-label={title}>
    <div className="flex h-[min(960px,96vh)] w-[min(1500px,98vw)] flex-col overflow-hidden rounded-2xl bg-[#F5F7FA] shadow-2xl">
      <header className="flex shrink-0 items-center justify-between gap-3 border-b border-slate-200 bg-white px-5 py-3">
        <div className="min-w-0"><div className="flex items-center gap-2"><h2 className="text-base font-black text-[#1A1D2E]">发布工作台</h2><span className="rounded bg-lime-100 px-2 py-0.5 text-[10px] font-bold text-lime-800">{isPlugin ? '插件本地草稿' : '发布'}</span></div><p className="mt-1 truncate text-xs text-slate-500">{data ? `${data.account.nickname} · ${data.account.uid} · 《${data.drama.name}》` : '正在读取任务资料…'}</p></div>
        <div className="flex shrink-0 items-center gap-2">
          <span className="hidden max-w-40 truncate text-[11px] text-slate-500 xl:block">{connection}</span><button className={button} disabled={!!busy} onClick={() => void perform('检查连接', async () => { const result = await publishingAction<{ message: string }>(taskId, 'connection'); setConnection(result.message); })}><RefreshCw size={12} />检查连接</button>
          {data && <div className="flex items-center gap-1.5" data-testid="publishing-profile-picker"><select aria-label="当前发布方案" className={`${field} !h-9 !w-auto !min-w-max !py-0`} disabled={disabled} value="" onChange={e => setApplyProfileId(e.target.value)}><option value="" disabled>{profileInfo ? `${profileInfo.name}${profileInfo.deleted ? '（已删除）' : ''}` : '选择发布方案'}</option>{data.profile_library?.items.map(p => <option key={p.id} value={p.id}>{p.name}</option>)}</select>{profileInfo && (matchesProfile ? <span className="whitespace-nowrap rounded-lg border border-emerald-100 bg-emerald-50 px-2 py-1 text-[11px] font-medium text-emerald-700">与配置一致</span> : <button type="button" disabled={disabled || profileInfo.deleted} title={profileInfo.deleted ? '原配置已删除，请选择其他配置' : '查看并应用当前配置'} className="whitespace-nowrap rounded-lg border border-amber-100 bg-amber-50 px-2 py-1 text-[11px] font-medium text-amber-800 transition-colors hover:border-amber-200 hover:bg-amber-100 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-amber-300 disabled:cursor-default disabled:hover:border-amber-100 disabled:hover:bg-amber-50" onClick={() => setApplyProfileId(profileInfo.id)}>与配置不一致</button>)}</div>}
          <button className={button} disabled={!data || disabled || remoteActive} onClick={() => setProfilesOpen(true)}>默认配置</button>
          <button className="rounded p-1.5 hover:bg-slate-100" aria-label="关闭发布工作台" onClick={close}><X size={18} /></button></div>
      </header>
      {!data ? <div className="flex flex-1 items-center justify-center text-sm text-slate-500">{error ? '请处理提示后重新打开。' : '正在读取发布资料…'}</div> : <main className="min-h-0 flex-1 space-y-3 overflow-y-auto p-4">
        {data.settings.profile_ref?.problem && <div role="alert" className="rounded-xl border border-amber-200 bg-amber-50 p-3 text-xs leading-5 text-amber-900">{data.settings.profile_ref.problem}</div>}
        {issues.length > 0 && <div className="rounded-xl border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-900"><strong>待处理 {issues.length} 项</strong>{issues.map((issue, i) => <button key={i} className="ml-3 text-left hover:underline" onClick={() => issue.group_id && setSelectedId(issue.group_id)}>{issue.message}</button>)}</div>}
        <fieldset disabled={disabled} className={`${section} !space-y-2`} aria-label="整批发布时间">
          <div className="flex flex-wrap items-center justify-between gap-2"><h3 className="text-sm font-black">整批排期</h3><span className="text-[11px] text-slate-400">设置一次，两组自动接续；份数变化后自动重算</span></div>
          <div className="grid grid-cols-2 items-end gap-3 lg:grid-cols-[150px_220px_130px_200px_1fr]">
            <label className="text-[11px] font-bold text-slate-500">时间方式<select aria-label="时间方式" className={`${field} mt-1`} value={schedule.schedule_type} onChange={e => updateSchedule({ schedule_type: e.target.value as typeof schedule.schedule_type })}><option value="now">立即模式</option><option value="timing">平台定时</option><option value="localTiming">本机定时</option></select></label>
            <label className="text-[11px] font-bold text-slate-500">整批开始时间<input aria-label="整批开始日期和时间" className={`${field} mt-1`} disabled={schedule.schedule_type === 'now'} type="datetime-local" value={schedule.start_time.replace(' ', 'T')} onChange={e => updateSchedule({ start_time: e.target.value.replace('T', ' ') })} /></label>
            <label className="text-[11px] font-bold text-slate-500">作品间隔<select aria-label="作品间隔" className={`${field} mt-1`} disabled={schedule.schedule_type === 'now'} value={customInterval || !intervalMinutes.includes(schedule.interval) ? 'custom' : String(schedule.interval)} onChange={e => { const custom = e.target.value === 'custom'; setCustomInterval(custom); if (!custom) updateSchedule({ interval: Number(e.target.value) }); }}>{intervalMinutes.map(value => <option key={value} value={value}>{intervalLabel(value)}</option>)}<option value="custom">自定义间隔</option></select>{(customInterval || !intervalMinutes.includes(schedule.interval)) && <input aria-label="整批间隔分钟" className={`${field} mt-1`} disabled={schedule.schedule_type === 'now'} type="number" min={0} max={10080} value={schedule.interval} onChange={e => updateSchedule({ interval: Number(e.target.value) })} />}</label>
            <label className="text-[11px] font-bold text-slate-500">两组顺序<select aria-label="两组发布顺序" className={`${field} mt-1`} value={data.settings.group_order || 'normal_first'} onChange={e => { setData({ ...data, settings: { ...data.settings, group_order: e.target.value as 'normal_first' | 'sheep_first' } }); setDirty(true); }}><option value="normal_first">正剧 → 羊</option><option value="sheep_first">羊 → 正剧</option></select></label>
            <button className={`${button} justify-self-end`} onClick={() => setShowPreview(!showPreview)}><ChevronDown size={12} />{showPreview ? '收起完整排期' : `查看完整排期（${count}条）`}</button>
          </div>
          {schedule.schedule_type === 'now' ? <p className="text-[11px] text-slate-400">{isPlugin ? '按两组顺序生成本地草稿。' : '立即模式将按两组顺序提交发布；需要按分钟接续请选择定时。'}</p> : <p className="text-[11px] text-slate-500">后一组从前一组最后一条之后再间隔 {schedule.interval} 分钟开始。{schedule.schedule_type === 'localTiming' ? '本机定时正式执行需保持电脑和小V猫运行。' : ''}</p>}
          {showPreview && <div className="max-h-56 overflow-y-auto rounded-lg border border-slate-100 bg-slate-50"><table className="w-full text-left text-xs"><thead className="sticky top-0 bg-slate-100 text-slate-500"><tr><th className="p-2">分组</th><th className="p-2">视频</th><th className="p-2">份数</th><th className="p-2">预计时间</th></tr></thead><tbody>{timeline.slice(0, 200).map(row => <tr key={`${row.groupId}-${row.video.id}-${row.copy}`} className="border-t border-slate-100"><td className="p-2">{row.groupName}</td><td className="p-2">{row.video.name}</td><td className="p-2">第{row.copy}份</td><td className="whitespace-nowrap p-2 font-mono">{row.time}</td></tr>)}</tbody></table>{timeline.length > 200 && <p className="p-2 text-xs text-slate-400">仅展开前200条，其余按相同规则接续。</p>}</div>}
        </fieldset>
        <div className="flex flex-wrap items-center gap-2" role="tablist" aria-label="自动识别的视频分组">
          {timedGroups.map(g => { const rows = expandedPreview(g, data.videos); return <button key={g.id} role="tab" aria-selected={g.id === group?.id} onClick={() => setSelectedId(g.id)} className={`min-w-0 flex-1 rounded-xl border px-4 py-2.5 text-left ${g.id === group?.id ? 'border-slate-900 bg-slate-900 text-white shadow-sm' : 'border-slate-200 bg-white hover:border-slate-400'}`}><span className="flex flex-wrap items-center justify-between gap-2"><strong className="text-sm">{g.name}</strong><span className={`text-xs ${g.id === group?.id ? 'text-slate-300' : 'text-slate-500'}`}>{g.video_ids.length} 个视频 · {rows.length} 条</span></span><span className={`mt-1 block text-[11px] ${g.id === group?.id ? 'text-slate-300' : 'text-slate-400'}`}>{rows.length ? schedule.schedule_type === 'now' ? '自动识别 · 立即模式' : `${rows[0].time} → ${rows[rows.length - 1].time}` : '暂无视频'}</span></button>; })}
          <button className={button} disabled={disabled} onClick={() => void perform('刷新视频', async () => { await save(); setNotice('视频与对应封面已刷新，排期已自动重算。'); })}><RefreshCw size={12} />刷新</button>
          <button className={button} onClick={() => setAdvanced(!advanced)}>{advanced ? '收起特殊调整' : '特殊调整'}</button>
        </div>
        {group ? <fieldset disabled={disabled} className="space-y-3">
          <section className={`${section} !space-y-0`} aria-label="本组视频与自动封面">
            <div className="flex flex-col gap-4 sm:flex-row">
              <div className="flex shrink-0 items-start gap-3 sm:w-48 sm:border-r sm:border-slate-100 sm:pr-3" data-testid="automatic-publish-cover">
                <PublishingCoverControl key={group.id} taskId={taskId} value={group} disabled={disabled} onBusy={active => setBusy(active ? '保存封面' : '')} onChange={patch => updateGroup(group.id, patch)} automatic={coverKinds.map(sheep => ({ url: coverForVideo(data, sheep)?.url || '', exists: Boolean(coverForVideo(data, sheep)?.exists), label: sheep ? '羊封面' : '剧集封面' }))} />
              </div>
              <div className="min-w-0 flex-1"><div className="mb-2 flex flex-wrap items-center justify-between gap-2"><h3 className="text-xs font-black">本组视频 <span className="ml-1 font-normal text-slate-400">{assignedVideos.length} 条 · {data.settings.assignment_mode === 'manual' ? '人工调整' : '已自动识别，无需勾选'}</span></h3><div className="flex items-center gap-3"><label className="flex items-center gap-1.5 text-xs text-slate-500">每视频份数<input aria-label="每个视频的份数" className={`${field} !w-16 !py-1`} type="number" min={1} max={100} value={group.copies} onChange={e => updateGroup(group.id, { copies: Number(e.target.value) })} /></label><label className="flex items-center gap-1.5 text-xs text-slate-500">排列<select aria-label="排列方式" className={`${field} !w-auto !py-1`} value={group.order} onChange={e => updateGroup(group.id, { order: e.target.value as PublishGroup['order'] })}><option value="round">整组循环</option><option value="consecutive">同视频连续</option></select></label></div></div>
                <div className="divide-y divide-slate-100">{(showAllVideos ? assignedVideos : assignedVideos.slice(0, 4)).map(v => { const times = preview.filter(row => row.video.id === v.id); return <div key={v.id} className="flex items-center gap-2 py-1.5 text-xs"><Film size={13} className="shrink-0 text-slate-400" /><span className="min-w-0 flex-1 truncate" title={v.path}>{v.name}</span><span className="shrink-0 text-[11px] text-slate-400">{formatElapsedSeconds(v.duration)}</span>{!v.exists && <span className="text-rose-600">文件缺失</span>}<span className="hidden shrink-0 text-[11px] text-slate-500 md:block">{times[0]?.time || '待设置'}{times.length > 1 ? ` 等${times.length}份` : ''}</span></div>; })}{!assignedVideos.length && <p className="py-2 text-xs text-slate-400">本组暂无视频，后续成片生成后点击刷新自动识别。</p>}</div>
                {assignedVideos.length > 4 && <button className="mt-1 text-[11px] text-slate-500 hover:underline" onClick={() => setShowAllVideos(!showAllVideos)}>{showAllVideos ? '收起列表' : `展开全部 ${assignedVideos.length} 条`}</button>}
              </div>
            </div>
          </section>
          {advanced && <section className="space-y-3 rounded-xl border border-amber-200 bg-amber-50/50 p-3" aria-label="特殊分组调整">
            <div className="flex flex-wrap items-center justify-between gap-2"><p className="text-xs text-amber-900">仅在识别不符合实际需求时调整。勾选会移动到当前组，取消则不纳入本次。</p><div className="flex flex-wrap gap-2"><button className={button} onClick={() => void perform('恢复自动识别', async () => { if (!await confirm({ title: '恢复自动分组', message: '将按正剧、羊视频重新分组，替换当前人工调整的视频归属。已生成的草稿会保留。', confirmText: '恢复自动分组' })) return; const value = await savePublishing(taskId, { ...data.settings, assignment_mode: 'auto', assignment_confirmed: false }); setData(value); setDirty(false); })}>恢复自动识别</button><button className={button} onClick={() => { const added: PublishGroup = { ...group, id: crypto.randomUUID(), kind: 'custom', name: `特殊组 ${data.settings.groups.length + 1}`, video_ids: [] }; setData({ ...data, settings: { ...data.settings, assignment_mode: 'manual', assignment_confirmed: true, groups: [...data.settings.groups, added] } }); setSelectedId(added.id); setDirty(true); }}><Plus size={12} />新增特殊组</button></div></div>
            <div className="flex flex-wrap items-center gap-2"><input aria-label="分组名称" className={`${field} !w-44`} value={group.name} onChange={e => updateGroup(group.id, { name: e.target.value })} /><select aria-label="复制其他分组设置" className={`${field} !w-auto`} value="" onChange={e => { const source = data.settings.groups.find(g => g.id === e.target.value); if (source) { const { id, name, kind, video_ids, ...settings } = source; updateGroup(group.id, settings); setTagsText(source.tags.join(' ')); } }}><option value="">复制另一组的文案与地址…</option>{timedGroups.filter(g => g.id !== group.id).map(g => <option key={g.id} value={g.id}>{g.name}</option>)}</select>{group.kind === 'custom' && <button className={button} onClick={() => { if (results.some(r => r.group_id === group.id && (r.draft_id || r.local_id))) { setError('已有发布任务或草稿的分组保留，请核对对应记录。'); return; } setData({ ...data, settings: { ...data.settings, groups: data.settings.groups.filter(g => g.id !== group.id) } }); setDirty(true); }}><Trash2 size={12} />删除特殊组</button>}</div>
            <div className="max-h-44 overflow-y-auto divide-y divide-amber-100">{data.videos.map(v => { const owner = data.settings.groups.find(g => g.video_ids.includes(v.id)); return <label key={v.id} className="flex items-center gap-2 py-1.5 text-xs"><input type="checkbox" aria-label={`调整视频 ${v.name}`} checked={group.video_ids.includes(v.id)} onChange={e => { setData({ ...data, settings: { ...data.settings, assignment_mode: 'manual', assignment_confirmed: true, groups: moveVideo(data.settings.groups, group.id, v.id, e.target.checked) } }); setDirty(true); }} /><span className="min-w-0 flex-1 truncate">{v.name}</span><span className="text-[11px] text-slate-400">{owner?.name || '未纳入'}</span></label>; })}</div>
          </section>}
          <div className="space-y-3"><div className="grid items-start gap-3 md:grid-cols-2">
            <section className={section} aria-label="发布地址"><label className="flex items-center gap-2 text-[11px] text-slate-500"><input aria-label="正剧与羊同步地址" type="checkbox" checked={data.settings.sync_location ?? true} onChange={e => setLocationSync(e.target.checked)} />正剧与羊同步地址</label><div className="flex items-center justify-between gap-2"><h3 className="flex items-center gap-1.5 text-xs font-black"><MapPin size={14} />发布地址</h3><button className={button} onClick={() => { if (addressEditing) { setAddressEditing(false); return; } void perform('读取地址库', async () => { const book = await getPublishingAddressBook(taskId); setData(current => current ? { ...current, ...book } : current); setAddressFilter(''); setAddressEditing(true); }); }}>{addressEditing ? '收起' : group.location ? '更换' : '设置'}</button></div>
              {group.location ? <div className="rounded-lg bg-slate-50 p-2"><p className="flex items-center gap-2 text-xs font-bold">{group.location.name || group.location.city}{data.default_address?.poiCheckSum === group.location.poiCheckSum && <span className="rounded bg-lime-100 px-1.5 py-0.5 text-[10px] text-lime-900">账号默认</span>}</p><p className="mt-1 text-[11px] leading-4 text-slate-500">{group.location.fullAddress}</p><div className="mt-2 flex flex-wrap gap-2"><button className="text-[11px] text-slate-500 hover:underline" onClick={() => void perform('设置账号默认地址', () => useAddress(group.location!, true, false))}>设为账号默认</button><button className="text-[11px] text-slate-400 hover:underline" onClick={() => updateGroup(group.id, { location: null })}>不显示位置</button></div></div> : <p className="text-xs text-slate-400">未设置地址，可继续</p>}
              {addressEditing && <>
                <div className="flex gap-2"><input aria-label="搜索发布地址" className={field} placeholder="搜索新增地点" value={locationQuery} onChange={e => setLocationQuery(e.target.value)} /><button className={button} onClick={() => void perform('查询地址', async () => { await save(); const token = generation.current; const result = await publishingAction<{ items: LocationValue[] }>(taskId, 'addresses', { query: locationQuery }); if (token === generation.current) setLocationRows(result.items); if (!result.items.length) setNotice('没有查到地址，请调整地点名称。'); })}><Search size={12} />搜索</button></div>
                {locationRows.length > 0 && <div className="max-h-48 overflow-y-auto rounded-lg border border-slate-200" aria-label="地址搜索候选">{locationRows.map(loc => <button key={loc.poiCheckSum} className="block w-full border-b border-slate-100 px-2 py-2 text-left hover:bg-lime-50" onClick={() => void perform('确认地址', () => useAddress(loc))}><span className="block text-xs font-bold">{loc.name || loc.city}</span><span className="block text-[11px] text-slate-500">{loc.fullAddress}</span></button>)}</div>}
                <div className="flex flex-wrap items-center gap-1 rounded-lg bg-slate-100 p-1" role="tablist" aria-label="地址库范围">{([['public', '公共地址库', data.public_addresses?.length || 0], ['account', '本账号记录', data.addresses.length]] as const).map(([key, label, count]) => <button key={key} role="tab" aria-selected={addressLibrary === key} className={`rounded-lg px-2.5 py-1.5 text-[11px] font-bold ${addressLibrary === key ? 'bg-white text-slate-900 shadow-sm' : 'text-slate-500'}`} onClick={() => { setAddressLibrary(key); setAddressFilter(''); }}>{label}（{count}）</button>)}</div>
                <input aria-label="筛选地址库" className={field} placeholder="按名称或地址筛选，无需重新查询" value={addressFilter} onChange={e => setAddressFilter(e.target.value)} />
                <div className="max-h-40 overflow-y-auto" aria-label={addressLibrary === 'public' ? '公共地址列表' : '本账号地址列表'}>{libraryAddresses.map(loc => <div key={loc.poiCheckSum} className="flex gap-2 border-b border-slate-100 py-2"><button className="min-w-0 flex-1 text-left text-xs" onClick={() => void perform('带入地址', () => useAddress(loc))}>{loc.name || loc.city}{data.default_address?.poiCheckSum === loc.poiCheckSum && <span className="ml-2 text-[10px] text-lime-700">账号默认</span>}<span className="block text-[11px] text-slate-400">{loc.fullAddress}</span></button><button aria-label={`删除${addressLibrary === 'public' ? '公共' : '账号'}地址 ${loc.name}`} title={addressLibrary === 'public' ? '仅从公共库移除，不改变各账号默认和已有任务' : '删除本账号地址记录'} className="px-1 text-slate-400 hover:text-rose-600" onClick={() => void perform('删除地址记录', async () => { const book = await publishingAction<PublishingAddressBook>(taskId, 'address-delete', { checksum: loc.poiCheckSum, scope: addressLibrary }); setData(current => current ? { ...current, ...book } : current); })}><Trash2 size={12} /></button></div>)}{!libraryAddresses.length && <p className="py-3 text-[11px] text-slate-400">{addressFilter ? '没有匹配的地址。' : addressLibrary === 'public' ? '暂无公共地址，搜索确认后会自动保存，其他账号也能选用。' : '本账号还没有地址记录，可从公共库选用。'}</p>}</div>
                <p className="text-[10px] leading-4 text-slate-400">公共库供所有账号选用；默认地址仍按账号单独保存。</p>
              </>}
            </section>
            <section className={section} aria-label="挂载剧集"><div className="flex items-center justify-between gap-2"><h3 className="text-xs font-black">挂载剧集</h3><label className="flex items-center gap-1.5 text-[11px] text-slate-500">方式<select aria-label="挂载方式" title="默认带入制作任务的选择；修改后记住当前任务的发布设置" className={`${field} !w-auto !py-1`} value={data.settings.mount_source || 'channels_drama'} onChange={e => void changeMountSource(e.target.value as MountSource)}><option value="mini_drama">小程序</option><option value="channels_drama">视频号</option><option value="plugin">插件</option></select></label>{data.settings.mount_source !== 'plugin' && <select aria-label="本组挂载方式" className={`${field} !w-auto !py-1`} value={String(group.mount_required)} onChange={e => updateGroup(group.id, { mount_required: e.target.value === 'true' })}><option value="true">挂载剧集</option><option value="false">不挂载</option></select>}{data.settings.mount_source !== 'plugin' && group.mount_required && <button className={button} onClick={() => setMountEditing(!mountEditing)}>{mountEditing ? '收起' : data.binding ? '更换' : '匹配'}</button>}</div>
              {data.settings.mount_source === 'plugin' ? <p className="rounded-lg bg-slate-50 p-2 text-xs leading-5 text-slate-500">插件方式：仅生成小V猫本地草稿，不附加原生短剧挂载；后续由插件处理。</p> : group.mount_required ? <><p className="text-[11px] text-slate-500">V3：{data.drama.name}</p>
              {data.binding ? <div className="rounded-lg bg-emerald-50 p-2"><p className="flex items-start gap-1.5 text-xs font-bold text-emerald-800"><CheckCircle2 size={13} className="mt-0.5 shrink-0" />{data.binding.drama.name}</p>{data.binding.drama.miniAppName && <p className="mt-1 text-[11px] text-emerald-700">{data.binding.drama.miniAppName}</p>}<p className="mt-1 text-[11px] text-emerald-700">已记住关联 · {data.binding.drama.mediaCount || '—'} 集</p></div> : <p className="text-xs text-amber-700">尚未关联，文字不同需确认</p>}
              <p className="text-[11px] leading-4 text-slate-400">{matchMessage || '同名及符号差异自动关联，已确认的以后复用。'}</p>
              {mountEditing && <><div className="flex gap-2"><input aria-label="搜索挂载剧集" className={field} placeholder="可用当前剧名、历史名或关键词" value={dramaQuery} onChange={e => setDramaQuery(e.target.value)} /><button className={button} onClick={() => void perform('匹配剧集', () => match(dramaQuery))}><Search size={12} />搜索</button></div><label className="flex items-center gap-2 text-[11px] text-slate-500"><input type="checkbox" checked={accountOnly} onChange={e => setAccountOnly(e.target.checked)} />这次选择仅当前账号使用</label><div className="max-h-56 overflow-y-auto divide-y divide-slate-100 rounded-lg border border-slate-100">{dramaRows.map(drama => <button key={drama.id} disabled={!drama.usable} className="flex w-full items-center gap-2 p-2 text-left hover:bg-lime-50 disabled:opacity-50" onClick={() => void perform('确认挂载', async () => { const binding = await publishingAction<MountBinding>(taskId, 'binding', { drama, confirmed: true, account_only: accountOnly, mount_source: data.settings.mount_source }); setData(current => current ? { ...current, binding } : current); setMatchMessage('关联已记住，以后自动带入。'); setMountEditing(false); setDramaRows([]); })}>{drama.coverUrl && <img src={drama.coverUrl} alt="" className="h-12 w-8 shrink-0 rounded object-cover" />}<span className="min-w-0 flex-1"><span className="block text-xs font-bold">{drama.name}</span><span className="block text-[10px] text-slate-400">{drama.miniAppName ? `${drama.miniAppName} · ` : ''}{drama.mediaCount || '—'} 集 · {drama.usable ? '可挂载' : drama.unusableReason || '不可用'} · {drama.score || 0}%</span></span><span className="text-[11px]">确认</span></button>)}</div></>}
              </> : <p className="rounded-lg bg-slate-50 p-2 text-xs text-slate-500">本组不挂载剧集；已记住的剧集关联会保留。</p>}
            </section>
            </div><section className={section} aria-label="发布文案"><div className="flex flex-wrap items-center justify-between gap-2"><h3 className="text-xs font-black">文案与声明</h3><span className="text-[10px] text-slate-400">视频号简介留空时使用视频标题，与小V猫一致</span></div>
              <div data-testid="publishing-copy-grid" className="grid gap-3 md:grid-cols-[minmax(0,0.9fr)_minmax(0,1.3fr)]">
                <div className="grid content-start gap-3">
                  <HistoryField disabled={disabled} label="视频标题（选填）" value={group.video_title || ''} history={data.history.video_title || []} onChange={video_title => updateGroup(group.id, { video_title })} onDelete={value => void deleteHistory('video_title', value)} />
                  <HistoryField disabled={disabled} label="话题（空格、逗号或 # 分隔）" value={tagsText} history={data.history.tags} onChange={text => { setTagsText(text); updateGroup(group.id, { tags: text.split(/[\s,#，；;]+/).filter(Boolean) }); }} onDelete={value => void deleteHistory('tags', value)} />
                </div>
                <HistoryField disabled={disabled} label="简介（选填）" multiline className="h-full" value={group.desc} history={data.history.desc} onChange={desc => updateGroup(group.id, { desc })} onDelete={value => void deleteHistory('desc', value)} />
              </div>
              <div className="flex flex-wrap items-center gap-3"><label className="min-w-0 flex-1 text-[11px] text-slate-500">视频声明<select aria-label="视频声明" className={`${field} mt-1`} value={group.tag_type} onChange={e => updateGroup(group.id, { tag_type: Number(e.target.value) })}>{declarationOptions.map(option => <option key={option.value} value={option.value}>{option.label}</option>)}</select></label><label className="flex items-center gap-1.5 pt-4 text-[11px] text-slate-500"><input type="checkbox" checked={group.original} onChange={e => updateGroup(group.id, { original: e.target.checked })} />视频为原创</label></div>
              {group.tag_type === 7 && <label className="block text-[11px] text-slate-500">转载来源<textarea aria-label="转载来源" className={`${field} mt-1 min-h-16`} maxLength={500} placeholder="填写转载来源，最多500字" value={group.repost_source || ''} onChange={e => updateGroup(group.id, { repost_source: e.target.value })} /></label>}
              {group.tag_type === 5 && <div className="rounded-lg bg-slate-50 p-2 space-y-2"><label className="block text-[11px] text-slate-500">拍摄日期<input aria-label="拍摄日期" className={`${field} mt-1`} type="date" max={beijingDateString()} value={group.shoot_date || ''} onChange={e => updateGroup(group.id, { shoot_date: e.target.value })} /></label><div className="grid grid-cols-3 gap-2">{[0, 1, 2].map(level => { let regions = data.shoot_regions || []; for (let i = 0; i < level; i++) regions = regions.find(r => r.code === group.shoot_region_codes?.[i])?.sub || []; if (level > 0 && !regions.length) return null; return <label key={level} className="text-[11px] text-slate-500">{['拍摄国家/地区', '拍摄省份', '拍摄城市'][level]}<select aria-label={['拍摄国家/地区', '拍摄省份', '拍摄城市'][level]} className={`${field} mt-1`} value={group.shoot_region_codes?.[level] ?? ''} onChange={e => updateGroup(group.id, { shoot_region_codes: [...(group.shoot_region_codes || []).slice(0, level), ...(e.target.value ? [Number(e.target.value)] : [])] })}><option value="">请选择</option>{regions.map(r => <option key={r.code} value={r.code}>{r.name}</option>)}</select></label>; })}</div></div>}

              <details><summary className="cursor-pointer text-[11px] text-slate-500">追评与更多设置</summary><div className="mt-2 space-y-2"><div className="max-w-xl"><HistoryField disabled={disabled} label="短标题（选填，6–16字）" value={group.short_title ?? group.title} history={data.history.short_title || []} onChange={short_title => updateGroup(group.id, { short_title })} onDelete={value => void deleteHistory('short_title', value)} /></div><HistoryField disabled={disabled} label="追评（选填）" multiline value={group.comment} history={data.history.comment} onChange={comment => updateGroup(group.id, { comment })} onDelete={value => void deleteHistory('comment', value)} /><label className="flex items-center gap-2 text-[11px] text-slate-500"><input type="checkbox" checked={group.comment_top} onChange={e => updateGroup(group.id, { comment_top: e.target.checked })} />置顶追评</label></div></details>
            </section>
          </div>
        </fieldset> : <p className="rounded-xl bg-white p-4 text-xs text-slate-400">尚无成片，生成后重新打开即可自动识别。</p>}
        <details open={running || needsHelp > 0} className="group rounded-xl border border-slate-200 bg-white"><summary className="cursor-pointer px-3 py-2 text-xs font-bold text-slate-600">{isPlugin ? '草稿结果与人工辅助' : '发布结果'} · 已完成 {ready} · 待处理 {needsHelp}</summary>          <section className={section} aria-label="草稿执行结果"><div className="flex flex-wrap items-center justify-between gap-2"><h3 className="text-sm font-black">{isPlugin ? '草稿与人工处理' : '发布提交与状态'}</h3><span className="text-xs text-slate-500">已就绪 {ready} · 待处理 {needsHelp}</span></div>
            {execution?.error && <p className="text-xs text-rose-700">{execution.error}</p>}
            <p className="text-xs text-slate-400">{isPlugin ? '插件方式保存在小V猫本地草稿箱，不提交到平台。' : '保留每条发布任务编号；结果不明确时先读取状态，不重复提交。定时作品按设置时间生效。'}</p>
            {!isPlugin && results.length > 0 && <div className="mb-2 flex flex-wrap items-center gap-2 border-b border-slate-100 pb-2"><label className="flex items-center gap-1.5 text-xs text-slate-600"><input type="checkbox" checked={visibleResults.length > 0 && visibleResults.every(item => selectedTaskKeys.includes(item.key))} onChange={e => selectVisible(e.target.checked)} />全选当前筛选</label><select aria-label="筛选发布状态" className={field + " !w-auto !py-1.5"} value={statusFilter} onChange={e => { setStatusFilter(e.target.value); setSelectedTaskKeys([]); }}><option value="all">全部状态</option><option value="waiting">待发布</option><option value="publishing">正在发布</option><option value="localTiming">本机定时等待</option><option value="paused">已暂停</option><option value="failed">失败</option><option value="canceled">已取消</option><option value="success">已发布</option><option value="uncertain">结果待核对</option><option value="needs_help">需要处理</option><option value="rejected">提交未完成</option><option value="pending">尚未提交</option></select><button className={button} disabled={!selectedTaskKeys.length || !!busy} onClick={() => void manageTasks("pause")}><Pause size={12} />暂停</button><button className={button} disabled={!selectedTaskKeys.length || !!busy} onClick={() => void manageTasks("retry")}><RefreshCw size={12} />重发</button><button className={button} disabled={!!busy || running} onClick={() => void beginScheduleRetry()}><RefreshCw size={12} />排期重发</button><button className={button} disabled={!selectedTaskKeys.length || !!busy} onClick={() => void manageTasks("continue")}><Play size={12} />继续提交</button><button className={button} disabled={!selectedTaskKeys.length || !!busy} onClick={() => void manageTasks("cancel")}><X size={12} />取消</button><span className="text-[11px] text-slate-400">已选 {selectedTaskKeys.length} 条</span></div>}
            <div className="max-h-64 space-y-2 overflow-y-auto">{visibleResults.length ? visibleResults.map(item => <div key={item.key} className={`rounded-xl border p-3 ${['ready','success'].includes(item.status) ? 'border-emerald-100 bg-emerald-50/40' : 'border-slate-200'}`}><div className="flex items-center justify-between gap-3"><label className="flex min-w-0 items-center gap-2"><input type="checkbox" checked={selectedTaskKeys.includes(item.key)} onChange={e => toggleTask(item.key, e.target.checked)} /><span className="min-w-0 truncate text-xs font-bold">{item.name} · 第{item.copy}份</span></label><span className={`shrink-0 text-xs ${['ready','success'].includes(item.status) ? 'text-emerald-700' : 'text-amber-700'}`}>{labels[item.status] || item.status}{item.draft_id ? ` · 草稿 ${item.draft_id}` : item.local_id ? ` · 任务 ${item.local_id.slice(0, 12)}` : ''}</span></div>{item.error && <p className="mt-1 text-xs text-rose-700">{item.error}</p>}{item.checks && <p className="mt-1 text-[11px] text-slate-400">账号、视频及设置核对：{Object.values(item.checks).every(Boolean) ? '一致' : '部分不一致'}{item.accepted_payload ? ' · 已采纳该条人工设置' : ''}</p>}
              {item.replaces_local_id && <p className="mt-1 text-[11px] text-slate-500">重新发布自旧任务 {item.replaces_local_id}</p>}
              {item.draft_id && <div className="mt-2 flex flex-wrap gap-2"><button className={button} disabled={disabled} onClick={() => void perform('打开小V猫草稿', async () => { await publishingAction(taskId, 'open-draft', { key: item.key }); setNotice(`已在小V猫打开草稿 ${item.draft_id}。处理后回来重新读取，或采纳该条人工设置。`); })}>打开小V猫草稿</button><button className={button} disabled={disabled} onClick={() => void perform('读取人工设置', async () => {
                const result = await publishingAction<{ summary: { address: string; drama: string; time: string; description: string } }>(taskId, 'adopt-draft', { key: item.key });
                if (!await confirm({ title: '采纳该条人工设置', message: `草稿 ${item.draft_id}，仅影响这一条。\n\n地址：${result.summary.address}\n挂载：${result.summary.drama}\n时间：${result.summary.time}\n简介：${result.summary.description}`, confirmText: '确认采纳' })) return;
                await publishingAction(taskId, 'adopt-draft', { key: item.key, confirmed: true });
                const execution = await getDraftExecution(taskId); setData(current => current ? { ...current, execution } : current); setNotice('已采纳并检查该条人工设置，其他草稿和分组设置未改变。');
              })}>采纳该条人工设置</button></div>}
            </div>) : <p className="py-2 text-xs text-slate-400">{isPlugin ? '生成后显示每条草稿和检查结果。' : '发布后显示每条作品的队列状态和处理结果。'}</p>}</div>
            {!isPlugin && Boolean(execution?.previous_items?.length) && <details className="border-t border-slate-100 pt-2"><summary className="cursor-pointer text-[11px] font-semibold text-slate-500">已替换的旧任务 · {execution?.previous_items?.length}</summary><div className="mt-2 max-h-32 space-y-1 overflow-y-auto">{execution?.previous_items?.map(item => <p key={item.key} className="truncate text-[11px] text-slate-500">{item.name} · 第{item.copy}份 · {labels[item.status] || item.status}{item.local_id ? ` · 任务 ${item.local_id}` : ''}</p>)}</div></details>}
            {isPlugin && results.length > 0 && <div className="flex flex-wrap gap-2"><button className={button} disabled={disabled} onClick={() => void perform('重新读取并检查', async () => { await save(); await publishingAction(taskId, 'drafts'); setData(current => current ? { ...current, execution: { ...current.execution, running: true } } : current); })}><RefreshCw size={13} />重新读取并检查</button><span className="self-center text-[11px] text-slate-400">调整设置前先停止；人工处理后重新检查。</span></div>}
            {!isPlugin && results.length > 0 && <button className={button} disabled={!!busy || running} onClick={() => void perform('读取发布状态', async () => { const publication=await getPublication(taskId);setData(current => current ? {...current,publication} : current); })}><RefreshCw size={13} />读取发布状态</button>}
          </section></details>
        {advanced && <details className="text-xs text-slate-400"><summary className="cursor-pointer">连接参数</summary><label className="mt-2 block max-w-48">小V猫调试端口<input aria-label="小V猫调试端口" type="number" className={`${field} mt-1`} value={data.settings.port} disabled={disabled} onChange={e => { setData({ ...data, settings: { ...data.settings, port: Number(e.target.value) } }); setDirty(true); }} /></label></details>}
      </main>}
      <footer className="grid shrink-0 grid-cols-[minmax(0,1fr)_auto] items-center gap-3 border-t border-slate-200 bg-white px-5 py-3"><div className="min-w-0"><p className="text-sm font-bold">共 {count} 条{isPlugin ? '草稿' : '作品'} <span className="ml-2 text-[11px] font-normal text-slate-400">{dirty ? '有未保存设置' : '设置已同步'}</span></p><p role={error ? 'alert' : 'status'} aria-live="polite" title={error || notice || undefined} className={`mt-0.5 flex h-4 min-w-0 items-center gap-1.5 text-[11px] ${error ? 'text-rose-700' : notice ? 'text-emerald-700' : 'text-slate-400'}`}>{busy && <LoaderCircle size={12} className="shrink-0 animate-spin" />}<span className="truncate">{busy ? `${busy}中…` : error || notice || (isPlugin ? '保存到小V猫本地草稿箱，不提交平台。' : '按当前配置提交真实发布；停止仅阻止后续提交。')}</span>{error && !busy && <button className="shrink-0 font-bold underline" aria-label="查看错误详情" onClick={() => void confirm({ title: '操作提示', message: error, confirmText: '知道了' })}>详情</button>}</p></div><div className="flex flex-wrap gap-2">
        {running ? <><button className={button} onClick={() => void perform('调整执行状态', async () => { await publishingAction(taskId, execution?.mode === 'paused' ? 'resume' : 'pause'); const value = await (isPlugin ? getDraftExecution(taskId) : getPublication(taskId)); setData(current => current ? { ...current, [isPlugin ? 'execution' : 'publication']: value } : current); })}>{execution?.mode === 'paused' ? <Play size={12} /> : <Pause size={12} />}{execution?.mode === 'paused' ? '继续' : '暂停'}</button><button className={button} onClick={() => void perform('停止后续步骤', async () => { await publishingAction(taskId, 'stop'); })}><Square size={12} />停止</button></> : <><button className={button} disabled={!data || !!busy || isPlugin || running} onClick={() => void beginRepublish()}><RefreshCw size={12} />重新发布</button><button className={button} disabled={!data || !!busy || remoteActive} onClick={() => void perform('保存设置', async () => { await save(); setNotice('发布设置已保存。'); })}>保存设置</button><button className={button} disabled={!data || !!busy || remoteActive} onClick={() => void perform('检查参数', async () => { await save(); const result = await publishingAction<{ ok: boolean; issues: typeof issues; binding: MountBinding | null }>(taskId, 'check'); setIssues(result.issues); setData(current => current ? { ...current, binding: result.binding } : current); if (result.ok) setNotice(isPlugin ? '参数检查通过，可以生成本地草稿。' : '参数检查通过，可以发布。'); })}>仅检查</button><button className="inline-flex items-center gap-2 rounded-xl bg-[#1A1D2E] px-4 py-2 text-sm font-black text-[#DDFD00] disabled:opacity-40" disabled={!data || !!busy || count === 0 || remoteActive} onClick={() => void perform(isPlugin ? '生成本地草稿' : '提交发布', async () => { await save(); await publishingAction(taskId, republishMode ? 'republish' : hasPending ? 'continue' : 'publish', {}); setData(current => current ? { ...current, [isPlugin ? 'execution' : 'publication']: { ...(isPlugin ? current.execution : current.publication || {items:[]}), running: true, state: 'running' } } : current); setRepublishMode(false); setIssues([]); })}><FileCheck2 size={15} />{isPlugin ? '发布草稿' : republishMode ? '按新设置发布' : hasPending ? '继续提交' : '发布'}</button></>}
      </div></footer>
      {scheduleRetryOpen && scheduleRetryPlan && <div className="fixed inset-0 z-[120] flex items-center justify-center bg-slate-950/40 p-4" role="dialog" aria-modal="true" aria-label="排期重发"><div className="w-[min(820px,96vw)] rounded-2xl bg-white p-5 shadow-2xl"><div className="flex items-center justify-between"><div><h3 className="text-base font-black text-[#1A1D2E]">排期重发</h3><p className="mt-1 text-xs text-slate-500">全部任务都会显示；成功任务默认不勾选。原时间只参考任务排序，新时间按第一条时间和当前间隔重新计算。</p></div><button className="rounded p-1.5 hover:bg-slate-100" aria-label="关闭排期重发" onClick={() => setScheduleRetryOpen(false)}><X size={17} /></button></div><div className="mt-4 grid grid-cols-2 gap-3"><label className="block text-xs font-bold text-slate-600">第一条新发布时间（北京时间）<input aria-label="排期重发开始时间" type="datetime-local" className={`${field} mt-1`} value={scheduleRetryStart.replace(' ', 'T')} onChange={e => void changeScheduleRetryStart(e.target.value.replace('T', ' '))} /></label><label className="block text-xs font-bold text-slate-600">任务间隔（分钟）<input aria-label="排期重发任务间隔" type="number" min={0} max={10080} className={`${field} mt-1`} value={scheduleRetryInterval} onChange={e => void changeScheduleRetryInterval(Number(e.target.value))} /></label></div><div className="mt-3 max-h-72 space-y-1 overflow-y-auto rounded-xl border border-slate-100 p-2">{scheduleRetryPlan.items.map(item => <label key={item.key} className="flex items-center gap-2 rounded-lg px-2 py-1.5 text-xs hover:bg-slate-50"><input type="checkbox" checked={scheduleRetryPlan.keys.includes(item.key)} onChange={e => { const keys=e.target.checked ? [...new Set([...scheduleRetryPlan.keys,item.key])] : scheduleRetryPlan.keys.filter(key=>key!==item.key); void changeScheduleRetryKeys(keys); }} /><span className="min-w-0 flex-1 truncate">{item.name} · 第{item.copy}份</span><span className="w-20 shrink-0 text-slate-500">{labels[item.status || item.remote_state || ''] || item.status || item.remote_state || '未知'}</span><span className="shrink-0 text-slate-400">{item.old_time || '未排期'} → {item.new_time || '—'}</span></label>)}</div><div className="mt-4 flex justify-end gap-2"><button className={button} onClick={() => setScheduleRetryOpen(false)}>取消</button><button className="rounded-xl bg-[#1A1D2E] px-4 py-2 text-xs font-black text-[#DDFD00] disabled:opacity-40" disabled={!scheduleRetryPlan.keys.length || !!busy} onClick={() => void confirmScheduleRetry()}>确认排期重发</button></div></div></div>}
      {republishResetOpen && republishResetPlan && <div className="fixed inset-0 z-[125] flex items-center justify-center bg-slate-950/40 p-4" role="dialog" aria-modal="true" aria-label="重新发布准备"><div className="w-[min(720px,96vw)] rounded-2xl bg-white p-5 shadow-2xl"><div className="flex items-center justify-between"><div><h3 className="text-base font-black text-[#1A1D2E]">重新发布：整批作废重来</h3><p className="mt-1 text-xs text-slate-500">旧批次不会继续作为当前批次。系统已处理可取消的小V猫任务；官方后台已经上传成功的视频，需要人工删除。</p></div><button className="rounded p-1.5 hover:bg-slate-100" aria-label="关闭重新发布准备" onClick={() => setRepublishResetOpen(false)}><X size={17} /></button></div><div className="mt-4 grid grid-cols-2 gap-2 text-xs"><div className="rounded-lg bg-emerald-50 p-2 text-emerald-800">已成功，需人工删除：{republishResetPlan.success.length}</div><div className="rounded-lg bg-sky-50 p-2 text-sky-800">已取消旧任务：{republishResetPlan.cancelled.length}</div><div className="rounded-lg bg-slate-50 p-2 text-slate-600">失败/暂停/取消，保留历史：{republishResetPlan.terminal.length}</div><div className="rounded-lg bg-slate-50 p-2 text-slate-600">未提交：{republishResetPlan.pending.length}</div></div>{republishResetPlan.success.length > 0 && <div className="mt-3 max-h-24 overflow-y-auto rounded-xl border border-emerald-100 bg-emerald-50/50 p-3 text-xs text-emerald-900"><strong>请在官方后台删除这些已上传视频：</strong><div className="mt-1 space-y-0.5">{republishResetPlan.success.map(item => <p key={item.key}>{item.name} · 第{item.copy}份</p>)}</div></div>}{republishResetPlan.blocked.length > 0 && <div className="mt-3 rounded-xl border border-rose-200 bg-rose-50 p-3 text-xs text-rose-800"><strong>暂不能继续</strong><div className="mt-1 space-y-1">{republishResetPlan.blocked.map(item => <p key={item.key}>{item.name} · 第{item.copy}份：{item.reason}</p>)}</div></div>}<div className="mt-4 rounded-xl border border-amber-200 bg-amber-50 p-3 text-xs leading-5 text-amber-900">请人工打开官方账号后台，删除已经上传成功的视频。小V猫MCP不能删除官方作品；旧失败任务的MCP历史也不会自动删除。</div><div className="mt-5 flex justify-end gap-2"><button className={button} onClick={() => setRepublishResetOpen(false)}>稍后处理</button><button className="rounded-xl bg-[#1A1D2E] px-4 py-2 text-xs font-black text-[#DDFD00] disabled:opacity-40" disabled={!republishResetPlan.ready || !!busy} onClick={() => void confirmRepublishReset()}>我已处理官方后台，进入重新发布</button></div></div></div>}
      {confirmation}
      {data && profilesOpen && <PublishingProfileManager taskId={taskId} settings={data.settings} library={data.profile_library || { items: [], software_default_id: null, account_default_id: null }} accountName={data.account.nickname} onHistory={history => setData(current => current ? { ...current, history } : current)} addresses={data.public_addresses || []} regions={data.shoot_regions || []} onLibrary={profileLibraryChanged} onClose={() => setProfilesOpen(false)} onSavedApply={id => { setProfilesOpen(false); setApplyProfileId(id); }} />}
      {data && pendingProfile && <PublishingProfileApply taskId={taskId} profile={pendingProfile} settings={data.settings} onClose={() => setApplyProfileId('')} onApply={applyProfile} />}
    </div>
  </div>;
}
