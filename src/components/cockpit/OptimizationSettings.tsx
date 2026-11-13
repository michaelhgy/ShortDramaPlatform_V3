import { OptimizationAnalysisSettings } from './OptimizationAnalysisSettings';
import React, { useCallback, useEffect, useRef, useState } from 'react';
import { Settings2, X } from 'lucide-react';
import { loadOptimizationActionRecords, saveOptimizationActions, type OptimizationActionSettings, type OptimizationActionRecords } from '../../api/operationsDashboard';

const defaults: OptimizationActionSettings = {enabled:false,action:'hide',scope:'software',min_play_count:null,exclude_sticky:true,post_publish_hours:10};

export function OptimizationSettings({settings,onSaved}:{settings?:OptimizationActionSettings;onSaved:()=>void}) {
  const [open,setOpen]=useState(false);
  const [tab,setTab]=useState<'settings'|'analysis'|'records'>('settings');
  const [form,setForm]=useState({...defaults,...settings});
  const [threshold,setThreshold]=useState('');
  const [hours,setHours]=useState('10');
  const [busy,setBusy]=useState(false);
  const [analysisBusy,setAnalysisBusy]=useState(false);
  const locked=busy||analysisBusy;
  const [error,setError]=useState('');
  const [records,setRecords]=useState<OptimizationActionRecords|null>(null);
  const [recordError,setRecordError]=useState('');
  const [loading,setLoading]=useState(false);
  const request=useRef(0);
  const body=useRef<HTMLDivElement>(null);
  const readRecords=useCallback(async(page:number,snapshot?:number)=>{
    const current=++request.current;
    setLoading(true);setRecordError('');
    try {const result=await loadOptimizationActionRecords(page,snapshot);if(current===request.current)setRecords(result);}
    catch(e){if(current===request.current)setRecordError(e instanceof Error?e.message:'处理记录读取失败');}
    finally{if(current===request.current)setLoading(false);}
  },[]);
  useEffect(()=>{
    if(open&&tab==='records')void readRecords(1);
    return ()=>{++request.current;};
  },[open,tab,readRecords]);
  useEffect(()=>{body.current?.scrollTo({top:0});},[tab,records?.page]);
  const close=()=>{if(!locked){++request.current;setOpen(false);}};
  useEffect(()=>{
    if(!open)return;
    const escape=(e:KeyboardEvent)=>{if(e.key==='Escape'&&!locked)setOpen(false);};
    document.addEventListener('keydown',escape);
    return()=>document.removeEventListener('keydown',escape);
  },[open,locked]);
  const show=()=>{
    const saved={...defaults,...settings};
    setForm(saved);setThreshold(saved.min_play_count?.toString()||'');setHours(String(saved.post_publish_hours));
    setError('');setRecordError('');setRecords(null);setTab('settings');setOpen(true);
  };
  const save=async()=>{
    const n=threshold.trim()==='' ? null : Number(threshold);
    const limit=Number(hours);
    if(!hours.trim()||!Number.isFinite(limit)||limit<=0){setError('发布后处理时限必须是大于0的小时数。');return;}
    if((n!==null&&(!Number.isSafeInteger(n)||n<=0))||(form.enabled&&n===null)){setError('请填写正整数播放保护门槛；达到该值的作品会保留。');return;}
    setBusy(true);setError('');
    try{await saveOptimizationActions({...form,min_play_count:n,post_publish_hours:limit});setOpen(false);onSaved();}
    catch(e){setError(e instanceof Error?e.message:'保存失败');}
    finally{setBusy(false);}
  };
  const page=records?.page||1, pages=records?.page_count||1;
  const flip=(to:number)=>{void readRecords(to,records?.snapshot);};
  return <>
    <button type="button" onClick={show} className="inline-flex items-center gap-2 rounded-xl border border-slate-200 bg-white px-3 py-2 text-xs font-semibold text-slate-700 hover:bg-slate-50"><Settings2 className="h-4 w-4"/>优化设置</button>
    {open&&<div className="fixed inset-0 z-[100] flex items-center justify-center bg-slate-950/40 p-4" onClick={close}>
      <section role="dialog" aria-modal="true" aria-labelledby="optimization-settings-title" className={`flex max-h-[90dvh] w-full max-w-3xl flex-col overflow-hidden rounded-2xl bg-white shadow-xl ${tab==='analysis'?'h-[90dvh]':''}`} onClick={e=>e.stopPropagation()}>
        <div className="flex shrink-0 items-center justify-between border-b border-slate-100 px-6 py-4"><h3 id="optimization-settings-title" className="text-lg font-bold">优化设置</h3><button type="button" aria-label="关闭优化设置" disabled={locked} onClick={close}><X className="h-5 w-5"/></button></div>
        <div role="tablist" aria-label="优化设置内容" className="flex shrink-0 gap-5 border-b border-slate-100 px-6">
          {([['settings','处理设置'],['analysis','作品分析'],['records','处理记录']] as const).map(([id,label])=><button type="button" key={id} role="tab" id={`optimization-tab-${id}`} aria-controls={`optimization-panel-${id}`} aria-selected={tab===id} disabled={locked} onClick={()=>setTab(id)} className={`border-b-2 py-3 text-sm font-semibold ${tab===id?'border-indigo-600 text-indigo-600':'border-transparent text-slate-500'}`}>{label}</button>)}
        </div>
        <div ref={body} data-optimization-scroll-body className={`min-h-0 flex-1 text-sm text-slate-700 ${tab==='analysis'?'flex flex-col overflow-hidden':'overflow-y-auto p-6'}`}>
          {tab==='settings'?<div role="tabpanel" id="optimization-panel-settings" aria-labelledby="optimization-tab-settings" className="space-y-5">
            <label className="flex items-center justify-between font-semibold">自动处理已优化作品<input aria-label="自动处理已优化作品" type="checkbox" checked={form.enabled} onChange={e=>setForm({...form,enabled:e.target.checked})}/></label>
            <p className="rounded-xl bg-slate-50 p-3 text-xs leading-5">默认关闭。启用后，在成功检测优化记录并重新读取作品播放量后处理。无法唯一对应、缺少播放量或数据过期的作品会跳过；置顶作品默认保留。</p>
            <label className="block">处理范围<select aria-label="处理范围" value={form.scope} onChange={e=>setForm({...form,scope:e.target.value as 'all'|'software'})} className="mt-2 w-full rounded-lg border border-slate-200 p-2"><option value="software">仅软件发布的作品</option><option value="all">账号全部作品</option></select><span className="mt-1 block text-xs text-slate-500">此设置单独保存，不随看板“全部作品／仅看软件”切换。</span></label>
            <label className="block">处理方式<select aria-label="处理方式" value={form.action} onChange={e=>setForm({...form,action:e.target.value as 'hide'|'delete'})} className="mt-2 w-full rounded-lg border border-slate-200 p-2"><option value="hide">隐藏（仅自己可见）</option><option value="delete">删除作品（不可恢复）</option></select></label>
            {form.action==='delete'&&<p role="note" className="rounded-lg bg-amber-50 p-3 text-xs text-amber-800">保存并启用后，会删除符合条件的优化作品，平台视频不可恢复。本地发布历史与优化证据继续保留。关闭自动处理即可停止后续请求，已发出的请求无法撤回。</p>}
            <label className="block">发布后处理时限（小时）<input aria-label="发布后处理时限（小时）" type="number" min="0" step="any" value={hours} onChange={e=>setHours(e.target.value)} className="mt-2 w-full rounded-lg border border-slate-200 p-2"/><span className="mt-1 block text-xs leading-5 text-slate-500">例如填10：仅处理发布后10小时内的优化作品。执行时已超过10小时的作品跳过；统计和优化记录继续保留。支持小数小时。</span></label>
            <label className="block">播放保护门槛<input aria-label="播放保护门槛" type="number" min="1" step="1" value={threshold} onChange={e=>setThreshold(e.target.value)} placeholder="启用前请填写" className="mt-2 w-full rounded-lg border border-slate-200 p-2"/><span className="mt-1 block text-xs text-slate-500">播放量达到或超过该值时保留，仅处理低于门槛的作品。</span></label>
            <label className="flex items-center gap-2"><input type="checkbox" checked={form.exclude_sticky} onChange={e=>setForm({...form,exclude_sticky:e.target.checked})}/>保留置顶作品</label>
            {error&&<p role="alert" className="text-red-600">{error}</p>}
          </div>:tab==='analysis'?<OptimizationAnalysisSettings onSaved={onSaved} onBusyChange={setAnalysisBusy}/>:<div role="tabpanel" id="optimization-panel-records" aria-labelledby="optimization-tab-records" aria-busy={loading}>
            <div className="flex items-start justify-between gap-4"><div><h4 className="font-semibold">处理记录</h4><p className="mt-1 text-xs leading-5 text-slate-500">记录已发起的隐藏／删除请求，每页10条，历史记录不因分页而删除。保护跳过的作品不会产生处理请求记录。</p></div><button type="button" disabled={loading} onClick={()=>void readRecords(1)} className="shrink-0 rounded-lg border px-3 py-1.5 text-xs disabled:opacity-40">刷新记录</button></div>
            <p className="mt-3 rounded-lg bg-amber-50 p-3 text-xs leading-5 text-amber-800">接口返回后仍需核实平台最终状态；结果未确认的请求不会自动重复发送。</p>
            {recordError&&<div role="alert" className="mt-4 text-xs text-red-600">{recordError}<button type="button" className="ml-3 underline" onClick={()=>void readRecords(page,records?.snapshot)}>重试读取</button></div>}
            {loading&&<p role="status" className="mt-4 text-xs text-slate-500">正在读取处理记录…</p>}
            {!!records?.records.length&&<ol aria-label="处理记录列表" className="mt-4 space-y-3">{records.records.map(log=><li key={`${log.uid}:${log.post_id}`} className="min-w-0 rounded-xl border border-slate-200 p-4 text-xs leading-5">
              <div className="flex flex-wrap items-center justify-between gap-2"><strong className="break-all">{log.account_name||log.uid}</strong><span className={`rounded-md px-2 py-0.5 ${log.state==='submitted'?'bg-amber-50 text-amber-800':'bg-rose-50 text-rose-700'}`}>{log.state==='submitted'?'接口已返回 · 待核实':'结果未确认'}</span></div>
              <p title={log.title} className="mt-2 line-clamp-2 break-all font-semibold">{log.title||`作品 ${log.post_id}`}</p>
              <p className="break-all text-slate-500">作品ID：{log.post_id} · 账号UID：{log.uid}</p>
              <p className="mt-1">发布时间：{log.publish_time||'未取得'}</p>
              <p>处理时间：{log.at} · {log.action==='hide'?'隐藏':'删除'} · 处理前播放：{Number.isFinite(log.views)?log.views.toLocaleString('zh-CN'):'未取得'}</p>
              {log.analysis&&<details className="mt-1 text-slate-500"><summary className="cursor-pointer">查看优化原因</summary><p className="mt-1 break-all">{log.analysis}</p></details>}
              <p className="mt-1 break-all text-slate-500">{log.message}</p>
            </li>)}</ol>}
            {records&&!records.records.length&&!loading&&!recordError&&<p className="mt-4 text-xs text-slate-400">暂无处理记录</p>}
          </div>}
        </div>
        {tab!=='analysis'&&<div data-optimization-footer className="shrink-0 border-t border-slate-100 bg-white px-6 py-4">
          {tab==='settings'?<div className="flex justify-end gap-3"><button disabled={locked} type="button" onClick={close} className="rounded-lg border px-4 py-2">取消</button><button disabled={locked} type="button" onClick={()=>void save()} className="rounded-lg bg-indigo-600 px-4 py-2 font-semibold text-white disabled:opacity-50">{busy?'保存中…':'保存设置'}</button></div>:<div className="flex flex-wrap items-center justify-between gap-3 text-xs">
            <span aria-live="polite">共 {records?.total??'—'} 条 · 每页10条 · 第 {page} / {pages} 页</span>
            <nav aria-label="处理记录分页" className="flex items-center gap-2">{([['首页',1],['上一页',page-1],['下一页',page+1],['末页',pages]] as const).map(([label,to])=><button key={label} type="button" disabled={loading||!records||to<1||to>pages||to===page} onClick={()=>flip(to)} className="rounded-lg border px-2.5 py-1.5 disabled:opacity-35">{label}</button>)}</nav>
          </div>}
        </div>}
      </section>
    </div>}
  </>;
}
