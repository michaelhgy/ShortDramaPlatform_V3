import {ChevronLeft,ChevronRight} from 'lucide-react';

export function DramaPagination({total,page,pageSize,onPageChange,onPageSizeChange,disabled}:{
  total:number;page:number;pageSize:number;onPageChange:(page:number)=>void;onPageSizeChange:(size:number)=>void;disabled?:boolean;
}) {
  const pages=Math.max(1,Math.ceil(total/pageSize));
  const start=Math.max(1,Math.min(page-2,pages-4));
  const numbers=[...new Set([1,...Array.from({length:Math.min(5,pages)},(_,i)=>start+i),pages])].sort((a,b)=>a-b);
  const button='inline-flex h-7 min-w-7 items-center justify-center rounded-lg border px-2 text-xs font-medium transition-colors disabled:cursor-default disabled:opacity-40';
  return <nav aria-label={'剧集分页'} className="flex flex-wrap items-center justify-between gap-3 text-xs">
    <span className="text-slate-400">共 <strong className="font-mono font-semibold text-slate-700">{total}</strong> 部{total>0&&<> · 当前 {(page-1)*pageSize+1}—{Math.min(page*pageSize,total)} 部</>}</span>
    <div className="flex flex-wrap items-center gap-1.5">
      <label className="mr-1 inline-flex items-center gap-1.5 text-slate-400">每页
        <select aria-label="每页剧集数" disabled={disabled} value={pageSize} onChange={event=>onPageSizeChange(Number(event.target.value))}
          className="rounded-lg border border-slate-200 bg-white px-2 py-1 text-xs font-medium text-slate-700 outline-none focus-visible:ring-2 focus-visible:ring-indigo-200">
          {[24,48,96].map(size=><option key={size} value={size}>{size}部</option>)}
        </select>
      </label>
      <button type="button" aria-label="上一页" disabled={disabled || page<=1} onClick={()=>onPageChange(page-1)} className={`${button} border-slate-200 bg-white text-slate-600 hover:bg-slate-50`}><ChevronLeft aria-hidden="true" className="h-3.5 w-3.5"/></button>
      {numbers.map((number,index)=><span key={number} className="inline-flex items-center gap-1.5">
        {index>0&&number>numbers[index-1]+1&&<span aria-hidden="true" className="px-1 text-slate-400">…</span>}
        <button type="button" aria-label={`第${number}页`} aria-current={page===number?'page':undefined} onClick={()=>{ if(number!==page) onPageChange(number); }} disabled={disabled || total===0}
          className={`${button} ${page===number?'border-indigo-100 bg-indigo-50 font-semibold text-indigo-600':'border-slate-200 bg-white text-slate-500 hover:bg-slate-50'}`}>{number}</button>
      </span>)}
      <button type="button" aria-label="下一页" disabled={disabled || page>=pages} onClick={()=>onPageChange(page+1)} className={`${button} border-slate-200 bg-white text-slate-600 hover:bg-slate-50`}><ChevronRight aria-hidden="true" className="h-3.5 w-3.5"/></button>
    </div>
  </nav>;
}
