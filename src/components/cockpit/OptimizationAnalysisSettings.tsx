import React, {useCallback, useEffect, useMemo, useRef, useState} from 'react';
import {loadOptimizationAnalysis, saveOptimizationAnalysis, type OptimizationAnalysisData} from '../../api/operationsDashboard';
import {matchOptimizationAnalysis, normalizeOptimizationAnalysis, optimizationAnalysisBody, OPTIMIZATION_REASONS, getOptimizationAppearance} from '../../types/optimizationNotices';

export function OptimizationAnalysisSettings({onSaved,onBusyChange}:{onSaved:()=>void;onBusyChange:(busy:boolean)=>void}) {
  const [data,setData]=useState<OptimizationAnalysisData|null>(null);
  const [loading,setLoading]=useState(false),[saving,setSaving]=useState(false);
  const [error,setError]=useState(''),[notice,setNotice]=useState('');
  const [query,setQuery]=useState(''),[filter,setFilter]=useState<'all'|'pending'|'labeled'>('all'),[page,setPage]=useState(1);
  const [drafts,setDrafts]=useState<Record<string,string>>({});
  const request=useRef(0),scroll=useRef<HTMLDivElement>(null);
  const load=useCallback(async()=>{
    const current=++request.current;setLoading(true);setError('');
    try{const result=await loadOptimizationAnalysis();if(current===request.current){setData(result);setDrafts({});}}
    catch(e){if(current===request.current)setError(e instanceof Error?e.message:'作品分析读取失败');}
    finally{if(current===request.current)setLoading(false);}
  },[]);
  useEffect(()=>{void load();return()=>{++request.current;};},[load]);
  const mappings=data?.configuration.mappings||[];
  const rows=useMemo(()=>{
    const search=query.trim().toLowerCase();
    return (data?.groups||[]).map(group=>{
      const tag=matchOptimizationAnalysis(group.analysis,mappings);
      const saved=mappings.some(m=>normalizeOptimizationAnalysis(m.analysis)===normalizeOptimizationAnalysis(group.analysis));
      return {...group,tag,saved};
    }).filter(g=>(filter==='all'||(filter==='pending'?g.tag==='待归类':g.tag!=='待归类'))&&(!search||[...g.variants,g.tag].some(text=>text.toLowerCase().includes(search))))
      .sort((a,b)=>Number(b.tag==='待归类')-Number(a.tag==='待归类')||b.record_count-a.record_count||a.key.localeCompare(b.key));
  },[data,query,filter]);
  const pages=Math.max(1,Math.ceil(rows.length/10)),currentPage=Math.min(page,pages);
  const labels=[...new Set([...OPTIMIZATION_REASONS.filter(t=>t!=='待归类'),...mappings.map(m=>m.tag).filter(t=>t!=='待归类')])];
  useEffect(()=>{scroll.current?.scrollTo({top:0});},[currentPage,query,filter]);
  const save=async(key:string,tag:string|null)=>{
    if(saving||!data)return;
    setSaving(true);onBusyChange(true);setError('');setNotice('');
    try{
      const result=await saveOptimizationAnalysis(key,tag,data.configuration.version);
      setData(result);setDrafts(previous=>{const next={...previous};delete next[key];return next;});
      setNotice(tag===null?'已恢复默认匹配，相关显示和统计已重新读取。':'标签已保存，相同分析的历史及后续记录统一应用此标签。');
      onSaved();
    }catch(e){setError(e instanceof Error?e.message:'标签保存失败');}
    finally{setSaving(false);onBusyChange(false);}
  };
  return <div role="tabpanel" id="optimization-panel-analysis" aria-labelledby="optimization-tab-analysis" className="flex min-h-0 flex-1 flex-col text-sm text-slate-700">
    <div className="shrink-0 space-y-3 border-b border-slate-100 px-6 py-4">
      <div className="flex items-start justify-between gap-3"><div><h4 className="font-semibold">作品分析与标签</h4><p className="mt-1 text-xs leading-5 text-slate-500">相同分析内容合并为一组，可以自行填写标签。保存后应用于相同分析的历史及后续记录，分析原文保留。</p></div><button type="button" disabled={loading||saving} onClick={()=>void load()} className="shrink-0 rounded-lg border px-3 py-1.5 text-xs disabled:opacity-40">刷新分析</button></div>
      <div className="flex flex-wrap gap-2"><input aria-label="搜索作品分析或标签" value={query} onChange={e=>{setQuery(e.target.value);setPage(1);}} placeholder="搜索分析原文或标签" className="min-w-0 flex-1 rounded-lg border border-slate-200 px-3 py-2 text-xs"/><select aria-label="作品分析归类状态" value={filter} onChange={e=>{setFilter(e.target.value as typeof filter);setPage(1);}} className="rounded-lg border border-slate-200 px-2 py-2 text-xs"><option value="all">全部分析</option><option value="pending">待归类</option><option value="labeled">已归类</option></select></div>
      {error&&<p role="alert" className="break-words text-xs text-red-600">{error}<button disabled={loading||saving} type="button" onClick={()=>void load()} className="ml-2 underline">重新读取</button></p>}
      {notice&&<p role="status" className="text-xs text-emerald-700">{notice}</p>}
    </div>
    <div ref={scroll} data-analysis-scroll-body className="min-h-0 flex-1 overflow-y-auto px-6 py-4" aria-busy={loading}>
      <datalist id="optimization-analysis-labels">{labels.map(tag=><option key={tag} value={tag}/>)}</datalist>
      {loading&&<p role="status" className="text-xs text-slate-500">正在读取作品分析…</p>}
      {!loading&&data&&!rows.length&&<p className="text-xs text-slate-500">{data.groups.length?'没有符合筛选条件的作品分析':'尚未收集到作品分析；采集优化记录后会在这里自动归类相同内容。'}</p>}
      <ol aria-label="作品分析分组" className="space-y-3">{rows.slice((currentPage-1)*10,currentPage*10).map(group=>{
        const value=Object.hasOwn(drafts,group.key)?drafts[group.key]:group.tag==='待归类'?'':group.tag;
        const appearance=getOptimizationAppearance(group.tag);
        return <li key={group.key} data-analysis-key={group.key} className="min-w-0 rounded-xl border border-slate-200 p-3">
          <div className="flex flex-wrap items-center justify-between gap-2 text-xs"><span className="text-slate-500">{group.record_count} 条优化记录 · {group.account_count} 个账号</span><span className={`max-w-full break-all rounded border px-2 py-0.5 ${appearance.pill}`}>{group.tag} · {group.saved?'已设置':group.tag==='待归类'?'未设置':'默认匹配'}</span></div>
          <p className="mt-2 whitespace-pre-wrap break-words rounded-lg bg-slate-50 p-3 text-xs leading-5">{optimizationAnalysisBody(group.analysis)}</p>
          {group.variants.length>1&&<details className="mt-2 text-xs text-slate-500"><summary className="cursor-pointer">查看 {group.variants.length} 种原文格式</summary>{group.variants.map(text=><p key={text} className="mt-2 whitespace-pre-wrap break-words">{text}</p>)}</details>}
          <div className="mt-3 flex flex-wrap items-center gap-2"><label className="flex min-w-0 flex-1 items-center gap-2 text-xs"><span className="shrink-0">优化标签</span><input aria-label={`优化标签 ${group.key}`} list="optimization-analysis-labels" maxLength={80} value={value} disabled={loading||saving} onChange={e=>setDrafts(previous=>({...previous,[group.key]:e.target.value}))} placeholder="自行填写，也可选用已有标签" className="min-w-0 flex-1 rounded-lg border border-slate-200 px-2 py-1.5"/></label><button type="button" disabled={loading||saving} onClick={()=>void save(group.key,value.trim()||'待归类')} className="rounded-lg bg-indigo-600 px-3 py-1.5 text-xs font-semibold text-white disabled:opacity-40">保存标签</button>{group.saved&&<button type="button" disabled={loading||saving} onClick={()=>void save(group.key,null)} className="rounded-lg border px-2 py-1.5 text-xs disabled:opacity-40">恢复默认</button>}</div>
        </li>;
      })}</ol>
    </div>
    <div data-analysis-footer className="flex shrink-0 flex-wrap items-center justify-between gap-3 border-t border-slate-100 px-6 py-4 text-xs"><span aria-live="polite">共 {rows.length} 组 · 每页10组 · 第 {currentPage} / {pages} 页</span><nav aria-label="作品分析分页" className="flex gap-2">{([['首页',1],['上一页',currentPage-1],['下一页',currentPage+1],['末页',pages]] as const).map(([label,to])=><button type="button" key={label} disabled={loading||saving||!data||to<1||to>pages||to===currentPage} onClick={()=>setPage(to)} className="rounded-lg border px-2.5 py-1.5 disabled:opacity-35">{label}</button>)}</nav></div>
  </div>;
}
