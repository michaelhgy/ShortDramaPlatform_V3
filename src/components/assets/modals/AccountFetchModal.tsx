import { observeAvatarSync } from '../../../services/accountAvatarSync';
import React, { useEffect, useMemo, useRef, useState } from 'react';
import { Download, X, Search, RefreshCw, Plus, Building2, Loader2, AlertCircle, CheckCircle2, ChevronLeft, ChevronRight } from 'lucide-react';
import { AccountAvatar } from '../../AccountAvatar';
import type { TheaterBusinessItem } from '../../../assetsTypes';
import { accountImportStatus, previewRemoteAccounts, startAccountImport, syncExistingAccountAvatars, type AccountImportRun, type AccountPreview } from '../../../api/accountImport';
import { createBusinessTheater } from '../../../services/assetsCenterService';
import { refreshArea } from '../../../services/dataHub';
import { publishV2DataChange } from '../../../services/dataChangeEvents';

interface Props {
  theaters: TheaterBusinessItem[]; onClose: () => void;
  onTheaterCreated: (theater: TheaterBusinessItem) => void;
  onImported: () => Promise<void>;
}
const field = 'rounded-xl border border-slate-200 bg-white px-3 py-2 text-xs text-slate-700 outline-none focus:border-slate-400 disabled:bg-slate-50';
const button = 'inline-flex items-center justify-center gap-1.5 rounded-xl border border-slate-200 bg-white px-3 py-2 text-xs font-bold text-slate-600 hover:border-slate-400 disabled:opacity-40 disabled:cursor-not-allowed';

export function AccountFetchModal({ theaters, onClose, onTheaterCreated, onImported }: Props) {
  const [preview, setPreview] = useState<AccountPreview | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [selected, setSelected] = useState<string[]>([]);
  const [drafts, setDrafts] = useState<Record<string,{nickname: string; theater_id: string}>>({});
  const [query, setQuery] = useState('');
  const [filter, setFilter] = useState('pending');
  const [loginFilter, setLoginFilter] = useState('all');
  const [groupFilter, setGroupFilter] = useState('');
  const [page, setPage] = useState(1);
  const [bulkTheater, setBulkTheater] = useState('');
  const [localTheaters, setLocalTheaters] = useState(theaters);
  const [newTheater, setNewTheater] = useState(false);
  const [theaterName, setTheaterName] = useState('');
  const [commission, setCommission] = useState('40');
  const [tax, setTax] = useState('6');
  const [theaterError, setTheaterError] = useState('');
  const [savingTheater, setSavingTheater] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [run, setRun] = useState<AccountImportRun | null>(null);
  const mounted = useRef(true);
  const requestVersion = useRef(0);
  const finalRun = useRef('');
  const running = submitting || Boolean(run && ['queued','running'].includes(run.status));
  const enabledTheaters = localTheaters.filter(t => t.status === '启用');

  useEffect(() => { setLocalTheaters(current => [...theaters,...current.filter(t => !theaters.some(p => p.id === t.id))]); }, [theaters]);
  async function load() {
    const request = ++requestVersion.current;
    setLoading(true); setError('');
    try {
      const result = await previewRemoteAccounts();
      if (!mounted.current || request !== requestVersion.current) return;
      setPreview(result);
      setGroupFilter(current => result.items.some(a => a.groupName?.trim() === current) ? current : '');
      setDrafts(current => Object.fromEntries(result.items.map(a => [a.uid,current[a.uid] || {nickname:a.nickname,theater_id:''}])));
      setSelected(current => current.filter(uid => result.items.some(a => a.uid === uid && a.match !== 'existing')));
    } catch (e) { if (mounted.current) setError(e instanceof Error ? e.message : '获取账号失败，请检查小V猫连接'); }
    finally { if (mounted.current && request === requestVersion.current) setLoading(false); }
  }
  useEffect(() => { mounted.current = true; void load(); return () => { mounted.current = false; requestVersion.current += 1; }; }, []);
  useEffect(() => {
    const previous = document.body.style.overflow; document.body.style.overflow = 'hidden';
    const escape = (event: KeyboardEvent) => {
      if (event.key !== 'Escape') return;
      event.preventDefault(); event.stopPropagation();
      if (newTheater) { if (!savingTheater) setNewTheater(false); } else onClose();
    };
    document.addEventListener('keydown',escape,true);
    return () => { document.body.style.overflow = previous; document.removeEventListener('keydown',escape,true); };
  }, [newTheater,savingTheater,onClose]);
  useEffect(() => { setPage(1); }, [query,filter,loginFilter,groupFilter]);
  useEffect(() => {
    if (!run || !['queued','running'].includes(run.status)) return;
    if (run.kind === 'avatars') return observeAvatarSync(run, setRun);
    let cancelled = false;
    const timer = window.setTimeout(() => {
      void accountImportStatus(run.id).then(async result => {
        if (cancelled) return;
        setRun(result);
      }).catch(e => { if (!cancelled) { setError(e.message); setRun(current => current ? {...current,status:'error'} : null); } });
    },700);
    return () => { cancelled = true; window.clearTimeout(timer); };
  }, [run]);

  useEffect(() => {
    if (!run || !['completed','error'].includes(run.status) || finalRun.current === run.id) return;
    finalRun.current = run.id;
    if (run.status === 'completed' && run.kind !== 'avatars') setSelected(run.results.filter(r => r.status === 'failed').map(r => r.uid));
    setPreview(current => current ? {...current,token:''} : current);
    void onImported().then(async () => {
      void refreshArea('catalog');
      for (const changed of run.results.filter(row => row.status === 'created' && row.account_id)) {
        publishV2DataChange({ changeType:'account_changed', accountId:changed.account_id, origin:'client' });
      }
      if (mounted.current) await load();
    }).catch(e => { if (mounted.current) setError(e.message || '账号已保存，列表刷新失败，请重新获取'); });
  }, [run]);

  const items = preview?.items || [];
  const groupNames = useMemo(() => [...new Set<string>(items.map(a => a.groupName?.trim()).filter((name): name is string => Boolean(name)))].sort((a,b) => a.localeCompare(b,'zh-CN')), [preview]);
  const filtered = useMemo(() => items.filter(a => {
    const match = filter === 'all' || (filter === 'existing' ? a.match === 'existing' : a.match !== 'existing');
    return match && (!groupFilter || a.groupName?.trim() === groupFilter) && (loginFilter === 'all' || a.loginStatus === loginFilter) && `${a.nickname} ${a.uid} ${a.groupName || ''}`.toLowerCase().includes(query.toLowerCase().trim());
  }), [preview,filter,loginFilter,groupFilter,query]);
  const visiblePending = filtered.filter(a => a.match !== 'existing');
  const pages = Math.max(1,Math.ceil(filtered.length/20));
  const rows = filtered.slice((Math.min(page,pages)-1)*20,Math.min(page,pages)*20);
  const selectedItems = items.filter(a => selected.includes(a.uid) && a.match !== 'existing');
  const missingTheater = selectedItems.filter(a => !enabledTheaters.some(t => t.id === drafts[a.uid]?.theater_id)).length;
  const nicknameConflict = (uid: string) => {
    const name = drafts[uid]?.nickname.trim();
    return !name || Boolean(preview?.local_nicknames.includes(name)) || items.some(a => a.uid !== uid && (a.match === 'existing' ? a.local_nickname || a.nickname : selected.includes(a.uid) ? drafts[a.uid]?.nickname.trim() : '') === name);
  };
  const invalidNames = selectedItems.filter(a => nicknameConflict(a.uid)).length;
  const patch = (uid: string, value: Partial<{nickname: string; theater_id: string}>) => setDrafts(current => ({...current,[uid]:{...current[uid],...value}}));
  const applyTheater = (id: string) => {
    setBulkTheater(id);
    if (id) setDrafts(current => ({...current,...Object.fromEntries(selectedItems.map(a => [a.uid,{...current[a.uid],theater_id:id}]))}));
  };
  async function saveTheater(event: React.FormEvent) {
    event.preventDefault(); if (savingTheater) return;
    setSavingTheater(true); setTheaterError('');
    try {
      const theater = await createBusinessTheater({name:theaterName.trim(),defaultCommissionRate:Number(commission),defaultTaxRate:Number(tax),status:'启用'});
      setLocalTheaters(current => [...current.filter(t => t.id !== theater.id),theater]);
      onTheaterCreated(theater); applyTheater(theater.id); setNewTheater(false);
    } catch (e) { setTheaterError(e instanceof Error ? e.message : '剧场创建失败'); }
    finally { setSavingTheater(false); }
  }
  async function submit() {
    if (!preview?.token || !selectedItems.length || missingTheater || invalidNames || running) return;
    setSubmitting(true); setError('');
    try { setRun(await startAccountImport(preview.token,selectedItems.map(a => ({uid:a.uid,...drafts[a.uid],nickname:drafts[a.uid].nickname.trim()})))); }
    catch (e) { setError(e instanceof Error ? e.message : '提交失败'); }
    finally { setSubmitting(false); }
  }

  async function syncAvatars() {
    if (!preview?.token || running) return;
    setSubmitting(true); setError('');
    try {
      const result = await syncExistingAccountAvatars(preview.token);
      observeAvatarSync(result);
      if (mounted.current) setRun(result);
    }
    catch (e) { setError(e instanceof Error ? e.message : '头像同步失败'); }
    finally { setSubmitting(false); }
  }

  return <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-xs p-4" onMouseDown={e => {if (e.target===e.currentTarget) onClose();}}>
    <div role="dialog" aria-modal="true" aria-label="从小V猫获取账号" className="w-full max-w-[1120px] max-h-[90vh] bg-[#F8FAFC] rounded-3xl shadow-2xl border border-white/80 overflow-hidden flex flex-col">
      <header className="px-6 py-5 bg-white border-b border-slate-100 flex items-center justify-between shrink-0"><div className="flex items-center gap-3"><span className="p-2.5 bg-[#1A1D2E] text-[#DDFD00] rounded-xl"><Download size={20}/></span><div><h3 className="font-extrabold text-base text-[#1A1D2E]">从小V猫获取账号</h3><p className="text-xs text-slate-500 mt-1">按平台ID匹配 · 已有账号跳过 · 为新账号选择所属剧场</p></div></div><button aria-label="关闭获取账号窗口" onClick={onClose} className="rounded-xl p-2 hover:bg-slate-100 text-slate-400"><X size={20}/></button></header>
      <main className="p-5 space-y-4 overflow-y-auto min-h-0">
        <div className="flex items-center justify-between gap-3"><div className="flex gap-2 text-xs"><span className="px-3 py-2 bg-white rounded-xl border border-slate-200">共 <b>{preview?.total || 0}</b> 个</span><span className="px-3 py-2 bg-[#F5F9E8] rounded-xl text-[#687F24]">待新增 <b>{preview?.new_count || 0}</b></span><span className="px-3 py-2 bg-slate-100 rounded-xl text-slate-500">已存在 <b>{preview?.existing_count || 0}</b></span></div><div className="flex gap-2 flex-wrap justify-end"><button title="更新本次获取结果中已存在账号的头像，保留其他资料" disabled={loading || running || !preview?.token || !preview.existing_count} onClick={() => void syncAvatars()} className={button}>同步已有头像</button><button disabled={loading || running} onClick={() => void load()} className={button}><RefreshCw size={13} className={loading?'animate-spin':''}/>重新获取</button></div></div>
        <div className="flex items-center gap-2 flex-wrap"><div className="relative flex-1 min-w-48"><Search size={14} className="absolute top-2.5 left-3 text-slate-400"/><input aria-label="搜索小V账号" value={query} onChange={e=>setQuery(e.target.value)} placeholder="搜索昵称、平台ID或小V分组" className={`${field} w-full pl-9`}/></div><select aria-label="小V分组筛选" value={groupFilter} onChange={e=>setGroupFilter(e.target.value)} className={`${field} max-w-48`}><option value="">全部小V分组</option>{groupNames.map(name=><option key={name} value={name}>{name}</option>)}</select><select aria-label="匹配筛选" value={filter} onChange={e=>setFilter(e.target.value)} className={field}><option value="pending">待新增</option><option value="existing">已存在</option><option value="all">全部账号</option></select><select aria-label="登录状态筛选" value={loginFilter} onChange={e=>setLoginFilter(e.target.value)} className={field}><option value="all">全部登录状态</option><option value="登录有效">登录有效</option><option value="登录失效">登录失效</option></select></div>
        <div className="flex items-center gap-3 flex-wrap rounded-2xl border border-slate-200 bg-white p-3"><label className="flex items-center gap-2 text-xs font-bold text-slate-600"><input type="checkbox" aria-label="全选筛选后的待新增账号" disabled={running || !visiblePending.length} checked={visiblePending.length>0 && visiblePending.every(a=>selected.includes(a.uid))} onChange={e=>setSelected(current=>e.target.checked?[...new Set([...current,...visiblePending.map(a=>a.uid)])]:current.filter(uid=>!visiblePending.some(a=>a.uid===uid)))}/>全选筛选结果</label><span className="text-xs text-slate-400">已选 {selectedItems.length} 个</span><div className="ml-auto flex gap-2"><select aria-label="批量设置所属剧场" disabled={running || !selectedItems.length} value={bulkTheater} onChange={e=>applyTheater(e.target.value)} className={`${field} max-w-52`}><option value="">批量设置剧场</option>{enabledTheaters.map(t=><option key={t.id} value={t.id}>{t.name}</option>)}</select><button disabled={running} onClick={()=>{setTheaterName('');setTheaterError('');setNewTheater(true);}} className={button}><Plus size={13}/>新增剧场</button></div></div>
        <div className="rounded-2xl border border-slate-200 bg-white overflow-hidden"><div className="overflow-x-auto"><table className="w-full text-xs"><thead className="bg-slate-50 text-slate-500 text-left"><tr><th className="p-3 w-9"/><th className="p-3">账号／平台ID</th><th className="p-3">登录状态</th><th className="p-3">小V分组／粉丝</th><th className="p-3 min-w-44">所属剧场</th><th className="p-3">匹配结果</th></tr></thead><tbody className="divide-y divide-slate-100">{rows.map(a=><tr key={a.uid} className={a.match==='existing'?'bg-slate-50/70 text-slate-400':''}><td className="p-3"><input aria-label={`选择账号 ${a.nickname}`} type="checkbox" disabled={running || a.match==='existing'} checked={selected.includes(a.uid)} onChange={e=>setSelected(current=>e.target.checked?[...current,a.uid]:current.filter(id=>id!==a.uid))}/></td><td className="p-3"><div className="flex items-center gap-2.5"><AccountAvatar name={a.nickname} url={a.localAvatar || a.avatar}/><div className="min-w-0"><input aria-label={`${a.uid}的本地昵称`} disabled={running || a.match==='existing'} value={drafts[a.uid]?.nickname || ''} onChange={e=>patch(a.uid,{nickname:e.target.value})} className={`w-40 rounded-lg border px-2 py-1 font-bold bg-transparent ${a.match==='existing'?'border-transparent':selected.includes(a.uid)&&nicknameConflict(a.uid)?'border-rose-300':'border-slate-200'}`}/><span className="block mt-1 text-[10px] font-mono text-slate-400 pl-2">{a.uid}</span></div></div></td><td className="p-3"><span className={`whitespace-nowrap text-[11px] px-2 py-1 rounded-full ${a.loginStatus==='登录有效'?'text-emerald-700 bg-emerald-50':'text-amber-700 bg-amber-50'}`}>{a.loginStatus}</span></td><td className="p-3"><span className="block text-slate-600">{a.groupName || '—'}</span><span className="text-[10px] text-slate-400">粉丝 {a.fansTotal ?? '未获取'}</span></td><td className="p-3">{a.match==='existing'?<span>保留原有关联</span>:<select aria-label={`${a.uid}的所属剧场`} disabled={running} value={drafts[a.uid]?.theater_id || ''} onChange={e=>patch(a.uid,{theater_id:e.target.value})} className={`${field} w-full max-w-52`}><option value="">请选择剧场</option>{enabledTheaters.map(t=><option key={t.id} value={t.id}>{t.name}</option>)}</select>}</td><td className="p-3"><span className={`whitespace-nowrap text-[11px] font-bold ${a.match==='existing'?'text-slate-400':nicknameConflict(a.uid)?'text-rose-600':'text-[#829630]'}`}>{a.match==='existing'?'已存在 · 跳过':nicknameConflict(a.uid)?'请修改同名昵称':a.match==='nickname_conflict' && drafts[a.uid]?.nickname===a.nickname?'昵称冲突':'待新增'}</span></td></tr>)}</tbody></table></div>{loading && !preview ? <p className="p-10 flex justify-center items-center gap-2 text-xs text-slate-400"><Loader2 size={15} className="animate-spin"/>正在读取小V猫账号…</p>:!rows.length&&<p className="p-10 text-center text-xs text-slate-400">{preview?'当前筛选下没有账号':'暂未取得账号，请确认小V猫已打开且MCP可连接'}</p>}<div className="border-t border-slate-100 p-3 flex items-center justify-between text-[11px] text-slate-400"><span>共 {filtered.length} 个 · 每页20个</span><div className="flex items-center gap-2"><button aria-label="上一页账号" disabled={page<=1} onClick={()=>setPage(p=>p-1)} className={button}><ChevronLeft size={12}/></button>{Math.min(page,pages)} / {pages}<button aria-label="下一页账号" disabled={page>=pages} onClick={()=>setPage(p=>p+1)} className={button}><ChevronRight size={12}/></button></div></div></div>
        <p className="text-[11px] text-slate-400">登录失效的账号也可添加，后续在小V猫重新登录。小V分组不自动关联剧场；子剧场、报白日期、注册日期和备注留空，业务状态默认正常。</p>
        {run && <div role="status" className="rounded-xl bg-white border border-slate-200 p-3 text-xs space-y-1.5"><p className="font-bold text-slate-700 flex items-center gap-2">{running?<Loader2 size={14} className="animate-spin"/>:<CheckCircle2 size={14}/>} {run.message}</p><p className="text-slate-500">{run.kind === 'avatars' ? '更新头像' : '新增'} {run.kind === 'avatars' ? run.avatars : run.created} · 跳过 {run.skipped} · 失败 {run.failed} · 已缓存头像 {run.avatars}</p>{run.avatar_failed>0&&<p className="text-amber-700">{run.avatar_failed} 张头像暂未下载成功，原头像和账号资料保留，可重新获取后再同步。</p>}{run.results.filter(r=>r.status==='failed').map(r=><p key={r.uid} className="text-rose-600">{r.nickname}：{r.message}</p>)}{running&&<p className="text-slate-400">关闭窗口不会取消已提交的{run.kind === 'avatars' ? '头像同步' : '新增操作'}，完成后可重新获取查看。</p>}</div>}
        {error&&<p role="alert" className="text-xs text-rose-700 bg-rose-50 border border-rose-100 rounded-xl p-3 flex gap-2"><AlertCircle size={15} className="shrink-0"/>{error}</p>}
      </main>
      <footer className="bg-white border-t border-slate-100 px-6 py-4 flex items-center justify-between shrink-0"><p className="text-xs text-slate-500">已选 <b>{selectedItems.length}</b> 个{missingTheater>0&&<span className="text-amber-700 ml-2">待选剧场 {missingTheater} 个</span>}{invalidNames>0&&<span className="text-rose-600 ml-2">待处理昵称 {invalidNames} 个</span>}</p><div className="flex gap-2"><button onClick={onClose} className={button}>关闭</button><button disabled={loading || running || !preview?.token || !selectedItems.length || missingTheater>0 || invalidNames>0} onClick={()=>void submit()} className="rounded-xl bg-[#DDFD00] px-5 py-2.5 text-sm font-extrabold text-[#1A1D2E] disabled:opacity-40 disabled:cursor-not-allowed">{running?(run?.kind === 'avatars'?'正在同步头像…':'正在新增…'):`新增所选账号（${selectedItems.length}）`}</button></div></footer>
    </div>
    {newTheater&&<div className="fixed inset-0 z-60 flex items-center justify-center bg-black/40 p-4"><form onSubmit={e=>void saveTheater(e)} role="dialog" aria-modal="true" aria-label="获取账号时新增剧场" className="w-full max-w-md rounded-3xl bg-white shadow-2xl p-6 space-y-4"><div className="flex items-center justify-between"><h4 className="font-extrabold text-base flex items-center gap-2"><Building2 size={18}/>新增剧场</h4><button type="button" aria-label="关闭新增剧场" disabled={savingTheater} onClick={()=>setNewTheater(false)}><X size={18}/></button></div><label className="block text-xs font-bold text-slate-600">剧场名称<input autoFocus required value={theaterName} onChange={e=>setTheaterName(e.target.value)} className={`${field} block w-full mt-2`} placeholder="输入剧场名称"/></label><div className="grid grid-cols-2 gap-3"><label className="text-xs text-slate-500">默认分成 %<input required type="number" min="0" max="100" step="0.01" value={commission} onChange={e=>setCommission(e.target.value)} className={`${field} block w-full mt-2`}/></label><label className="text-xs text-slate-500">默认税率 %<input required type="number" min="0" max="100" step="0.01" value={tax} onChange={e=>setTax(e.target.value)} className={`${field} block w-full mt-2`}/></label></div><p className="text-[11px] text-slate-400">保存后立即可选；当前已勾选账号会使用这个剧场，仍可逐行调整。</p>{theaterError&&<p role="alert" className="text-xs text-rose-600">{theaterError}</p>}<button disabled={savingTheater} className="w-full rounded-xl bg-[#1A1D2E] text-[#DDFD00] py-2.5 font-bold text-sm">{savingTheater?'正在保存…':'保存剧场并返回'}</button></form></div>}
  </div>;
}
