import { useEffect, useMemo, useRef, useState } from 'react';
import { ChevronDown, RefreshCw, Search, Square } from 'lucide-react';
import { loadCollectionRecords, type CollectionCategory, type CollectionRecord, type CollectionState } from '../../api/operationsDashboard';
import type { AccountCollectionProfile } from './DataCollectionModal';
import { AccountAvatar } from '../AccountAvatar';
import { AccountLoginBadge } from './AccountLoginBadge';
import { BusinessAccountStatusBadge } from './BusinessAccountStatusBadge';
import { AccountProfileTotals } from './AccountProfileTotals';
import { collectionStatusRows } from './geminiCollectionModel';
import { latestAccountRecords, recordCategories, recordSource, recordScope, recordStatus, recordStartedAt, recordRevenueSummary } from './collectionRecordsModel';

const toneClass={muted:'text-slate-500',ready:'text-emerald-700',warning:'text-amber-700',danger:'text-rose-600',active:'text-indigo-600'};
function time(value:string){const d=new Date(value);return Number.isFinite(d.getTime())?new Intl.DateTimeFormat('zh-CN',{timeZone:'Asia/Shanghai',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',hour12:false}).format(d):'时间未记录';}
export function AccountCollectionRecords({profiles,state,busy,progress,onStop,onRetry}: {
 profiles:AccountCollectionProfile[];state:CollectionState|null;busy:boolean;progress:string;onStop:()=>void;
 onRetry:(accountId:string,category:CollectionCategory,jobId:string)=>Promise<void>;
}) {
 const [search,setSearch]=useState(''),[theater,setTheater]=useState('ALL'),[filter,setFilter]=useState<'all'|'active'|'attention'>('all');
 const [expanded,setExpanded]=useState<{accountId:string;category:CollectionCategory}|null>(null);
 const [records,setRecords]=useState<CollectionRecord[]>([]),[loading,setLoading]=useState(false),[error,setError]=useState('');
 const [reload,setReload]=useState(0),[attemptBusy,setAttemptBusy]=useState(false);
 const historyKey=useRef('');
 const latest=useMemo(()=>latestAccountRecords(state),[state]);
 const active=!!state?.job&&['running','stopping'].includes(state.job.state);
 const selectedLatest=expanded?latest.get(expanded.accountId+':'+expanded.category):null;
 const revision=selectedLatest?JSON.stringify(selectedLatest):'';
 useEffect(()=>{
  let disposed=false;
  const key=expanded?expanded.accountId+':'+expanded.category:'';
  if(historyKey.current!==key){historyKey.current=key;setRecords([]);}
  if(!expanded){setRecords([]);return;}
  setLoading(true);setError('');
  loadCollectionRecords(expanded.accountId,expanded.category).then(result=>{
   if(!disposed){setRecords(result.records);}
  }).catch(e=>{if(!disposed)setError(e instanceof Error?e.message:'记录读取失败');}).finally(()=>{if(!disposed)setLoading(false);});
  return()=>{disposed=true;};
 },[expanded?.accountId,expanded?.category,reload,revision]);
 const kinds=(id:string)=>recordCategories.map(c=>latest.get(id+':'+c.key)).filter(Boolean).map(r=>recordStatus(r!));
 const inProgress=(id:string)=>kinds(id).some(s=>s.tone==='active');
 const attention=(id:string)=>kinds(id).some(s=>['danger','warning'].includes(s.tone));
 const visible=profiles.filter(p=>(theater==='ALL'||p.account.theaterName===theater)&&(!search.trim()||(p.account.name+' '+p.account.theaterName).toLowerCase().includes(search.trim().toLowerCase()))&&(filter==='all'||filter==='active'&&inProgress(p.account.id)||filter==='attention'&&attention(p.account.id)));
 const counts={all:profiles.length,active:profiles.filter(p=>inProgress(p.account.id)).length,attention:profiles.filter(p=>attention(p.account.id)).length};
 const handled=state?.job?.items.filter(i=>!['waiting','running'].includes(i.status)).length||0,total=state?.job?.items.length||0;
 return <div data-account-records className="flex-1 min-h-0 overflow-y-auto p-6 space-y-4">
  <div className={`flex flex-wrap items-center justify-between gap-3 rounded-xl border p-3 ${active?'bg-indigo-50 border-indigo-200':'bg-white border-slate-200'}`}>
   <div className="min-w-0"><div className="flex items-center gap-2 text-xs font-bold text-slate-900"><RefreshCw className={`h-3.5 w-3.5 text-indigo-600 ${active?'animate-spin':''}`}/>{active?'正在采集':'当前没有采集任务运行'}{active&&<span className="font-normal text-slate-500">已处理 {handled}/{total} 项</span>}</div>{active&&<p className="mt-1 text-xs text-slate-600" role="status">{progress}</p>}</div>
   {active&&<button type="button" onClick={onStop} disabled={busy||state?.job?.state==='stopping'} className="inline-flex shrink-0 items-center gap-1 rounded-lg border border-rose-200 bg-white px-3 py-1.5 text-xs font-bold text-rose-600 disabled:opacity-40"><Square className="h-3 w-3"/>{state?.job?.state==='stopping'?'等待当前请求返回':'停止后续请求'}</button>}
  </div>
  <div className="flex flex-wrap items-center gap-2">
   <div className="flex rounded-xl border border-slate-200 bg-slate-100 p-1 text-xs">{([{key:'all',label:'全部'},{key:'active',label:'进行中'},{key:'attention',label:'需处理'}] as const).map(f=><button key={f.key} type="button" onClick={()=>setFilter(f.key)} className={`rounded-lg px-3 py-1.5 font-bold ${filter===f.key?'bg-white text-indigo-700 shadow-xs':'text-slate-500'}`}>{f.label} ({counts[f.key]})</button>)}</div>
   <select aria-label="任务记录剧场" value={theater} onChange={e=>setTheater(e.target.value)} className="rounded-xl border border-slate-200 bg-white px-2 py-2 text-xs"><option value="ALL">全部剧场</option>{[...new Set(profiles.map(p=>p.account.theaterName))].sort().map(t=><option key={t}>{t}</option>)}</select>
   <div className="relative min-w-[160px] flex-1"><Search className="absolute left-2.5 top-2.5 h-3.5 w-3.5 text-slate-400"/><input aria-label="搜索任务记录账号" value={search} onChange={e=>setSearch(e.target.value)} placeholder="搜索账号或剧场" className="w-full rounded-xl border border-slate-200 bg-white py-2 pl-8 pr-3 text-xs"/></div>
  </div>
  <div className="overflow-hidden rounded-2xl border border-slate-200 bg-white">
   <div className="hidden grid-cols-[minmax(180px,1.15fr)_repeat(4,minmax(0,1fr))] gap-3 border-b border-slate-100 bg-slate-50 px-4 py-3 text-xs font-bold text-slate-500 md:grid"><span>账号</span>{recordCategories.map(c=><span key={c.key}>{c.label}</span>)}</div>
   {!visible.length&&<p className="p-8 text-center text-xs text-slate-400">没有符合条件的账号</p>}
   {visible.map(p=>{const a={...p.account,videoTotal:p.videoTotalCount,followerTotal:p.followerCount},fallback=collectionStatusRows(p,state);return <div key={a.id} data-record-account={a.id} className="border-b border-slate-100 last:border-0">
    <div className="grid grid-cols-1 items-center gap-3 px-4 py-3 md:grid-cols-[minmax(180px,1.15fr)_repeat(4,minmax(0,1fr))]">
     <div className="min-w-0"><div className="flex items-center gap-2"><span className="relative inline-flex h-9 w-9 shrink-0"><AccountAvatar name={a.name} url={a.avatarUrl} className="h-9 w-9"/><AccountLoginBadge account={a}/></span><div className="min-w-0"><div className="flex items-center gap-1.5"><span className="truncate text-xs font-extrabold text-slate-900" title={a.name}>{a.name}</span><span className="shrink-0"><BusinessAccountStatusBadge status={a.businessStatus}/></span></div><p className="mt-0.5 truncate text-[10px] text-slate-400">{a.theaterName}</p></div></div><AccountProfileTotals account={a}/></div>
     {recordCategories.map((c,n)=>{const r=latest.get(a.id+':'+c.key),badge=r?recordStatus(r):null,open=expanded?.accountId===a.id&&expanded.category===c.key;return <button key={c.key} type="button" data-record-category={c.key} aria-label={`${a.name} ${c.label}记录`} aria-expanded={open} onClick={()=>{setRecords([]);setExpanded(open?null:{accountId:a.id,category:c.key});}} title={r?.item.message||fallback[n].detail} className={`min-w-0 rounded-lg border px-2 py-2 text-left transition-colors ${open?'border-indigo-200 bg-indigo-50':'border-transparent hover:border-slate-200 hover:bg-slate-50'}`}>
      <div className="flex items-center justify-between gap-1"><span className={`truncate text-[11px] font-bold ${badge?toneClass[badge.tone]:'text-slate-500'}`}>{badge?.label||fallback[n].text}</span><ChevronDown className={`h-3 w-3 shrink-0 text-slate-400 ${open?'rotate-180':''}`}/></div>
      <p className="mt-1 truncate text-[10px] text-slate-400">{r?time(r.item.updated_at||r.started_at):'暂无任务记录'}</p>
     </button>;})}
    </div>
    {expanded?.accountId===a.id&&<div data-record-history className="border-t border-indigo-100 bg-indigo-50/30 px-4 py-3">
     <div className="mb-3 flex items-center justify-between"><span className="text-xs font-bold text-slate-800">{recordCategories.find(c=>c.key===expanded.category)?.label} · 详细记录（仅保留最近3条）</span><button type="button" onClick={()=>setReload(v=>v+1)} className="text-[11px] text-indigo-600">刷新记录</button></div>
     {error&&<p role="alert" className="mb-2 text-xs text-rose-600">{error}</p>}
     {!records.length&&<p className="py-3 text-xs text-slate-400">{loading?'正在读取记录…':'暂无保存的任务记录；已有数据状态仍在账号行显示。'}</p>}
     <div className="space-y-2">{records.map(r=>{const badge=recordStatus(r),newest=latest.get(a.id+':'+expanded.category)?.job_id===r.job_id,canRetry=newest&&['failed','partial','stopped'].includes(r.item.status),pending=badge.label==='来源待更新';return <div key={r.job_id} data-record-attempt={r.job_id} className="rounded-xl border border-slate-200 bg-white p-3">
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-[11px]"><span className="font-mono text-slate-500">{r.item.started_at?'开始于 ':'任务创建于 '}{time(recordStartedAt(r))}</span><span className={toneClass[badge.tone]+' font-bold'}>{badge.label}</span><span className="text-slate-400">{recordSource(r.source)}</span><span className="text-slate-500">{recordScope(r.options,r.item.category)}</span>
       {canRetry&&<button type="button" disabled={active||busy||attemptBusy} onClick={async()=>{setAttemptBusy(true);try{await onRetry(a.id,expanded.category,r.job_id);setReload(v=>v+1);}finally{setAttemptBusy(false);}}} className="ml-auto rounded-lg border border-indigo-200 px-2 py-1 font-bold text-indigo-600 disabled:opacity-40">{pending?'重新查询':badge.label==='查询失败'?'重试此项':'继续此项'}</button>}
      </div>
      {recordRevenueSummary(r)&&<p className="mt-2 text-xs font-semibold leading-5 text-slate-700">{recordRevenueSummary(r)}</p>}
      <p className="mt-2 text-xs leading-5 text-slate-600">{r.item.message}</p>
      {r.parent_job_id&&<p className="mt-1 text-[10px] text-slate-400">由上次未完成记录重试／续采，原始记录保留。</p>}
      <details className="mt-2 text-[11px] text-slate-500"><summary className="cursor-pointer text-slate-400">查看执行过程</summary><ol className="mt-2 space-y-1 border-l border-slate-200 pl-3">{r.events.map((e,i)=><li key={i}><span className="mr-2 font-mono text-slate-400">{time(e.time)}</span>{e.message}</li>)}</ol><p className="mt-2 text-[10px] text-slate-400">{r.item.events_truncated?'本项过程较长，仅保留最近120条步骤；入账明细不受影响。':'按本账号、本类型展示已保存的过程；较早任务可能未保留全部步骤。'}</p></details>
     </div>;})}</div>

    </div>}
   </div>;})}
  </div>
 </div>;
}
