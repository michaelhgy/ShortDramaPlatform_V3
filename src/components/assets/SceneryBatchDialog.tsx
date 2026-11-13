import { useEffect, useRef, useState } from 'react';
import { X } from 'lucide-react';
import { createSceneryBatch, getSceneryDetail, type CropRect, type SceneryBatchItem, type SceneryDetail, type SceneryOriginal } from '../../api/scenery';
import { CropEditor } from './SceneryCropEditor';
import { initialCrops, validCrops, sceneryOutputCount, sceneryTimeSummary, type CropLayout } from './sceneryCrops';

type Entry = { original: SceneryOriginal; detail?: SceneryDetail; crops: CropRect[]; requestId: string; error?: string; custom?: boolean };
const button = 'rounded-xl border border-slate-200 px-3 py-2 text-xs font-bold disabled:opacity-40 disabled:cursor-not-allowed';
const message = (error: unknown) => error instanceof Error ? error.message : String(error);

function CropOverview({ entry }: { entry: Entry }) {
  const d = entry.detail!;
  return <div className="relative bg-slate-950 rounded-lg overflow-hidden mx-auto" style={{ aspectRatio: `${d.width}/${d.height}`, height: 160, maxWidth: '100%' }}>
    <video muted preload="metadata" src={`${d.media_url}#t=0.1`} className="h-full w-full object-contain" />
    {entry.crops.map((c, index) => <div key={index} className="absolute border border-yellow-300 bg-yellow-300/10 text-yellow-200 text-xs" style={{ left: `${c.x/d.width*100}%`, top: `${c.y/d.height*100}%`, width: `${c.width/d.width*100}%`, height: `${c.height/d.height*100}%` }}><span className="bg-black/70 px-1">{index+1}</span></div>)}
  </div>;
}

export function SceneryBatchDialog({ originals, onClose, onQueued }: { originals: SceneryOriginal[]; onClose: () => void; onQueued: (ids: string[]) => void }) {
  const [entries, setEntries] = useState<Entry[]>(() => originals.map(original => ({ original, crops: [], requestId: crypto.randomUUID() })));
  const [loading, setLoading] = useState(true), [busy, setBusy] = useState(false), [error, setError] = useState('');
  const [layout, setLayout] = useState<CropLayout>('auto'), [editing, setEditing] = useState<string|null>(null), [uncertain, setUncertain] = useState(false);
  const pending = useRef<SceneryBatchItem[]|null>(null);
  const submitting = useRef(false);
  useEffect(() => {
    let cancelled = false, next = 0;
    // Bound probing requests; browsing a large selection must not launch hundreds at once.
    const worker = async () => {
      while (!cancelled && next < originals.length) {
        const original = originals[next++];
        try {
          const detail = await getSceneryDetail(original.id);
          if (!cancelled) setEntries(items => items.map(item => item.original.id === original.id ? { ...item, detail, crops: initialCrops(detail.width, detail.height, 'auto') } : item));
        } catch (e) {
          if (!cancelled) setEntries(items => items.map(item => item.original.id === original.id ? { ...item, error: message(e) } : item));
        }
      }
    };
    void Promise.all(Array.from({ length: Math.min(4, originals.length) }, worker)).then(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [originals]);
  const ready = entries.filter(item => item.detail && validCrops(item.crops, item.detail));
  const count = ready.reduce((total, item) => total + sceneryOutputCount(item.detail!,item.crops), 0);
  const locked = loading || busy || uncertain;
  const applyLayout = () => {
    setEntries(items => items.map(item => item.detail ? { ...item, crops: initialCrops(item.detail.width, item.detail.height, layout), custom: false, error: undefined, requestId: crypto.randomUUID() } : item));
    setError('');
  };
  const submit = async () => {
    if (submitting.current) return;
    submitting.current = true; setBusy(true); setEditing(null); setError('');
    // Keep the exact same request IDs after a lost response, including when originals were already deleted.
    const items = pending.current || ready.map(item => ({ source_id: item.original.id, crops: item.crops, request_id: item.requestId }));
    pending.current = items;
    try {
      const { results } = await createSceneryBatch(items);
      if (results.length !== items.length || items.some(item => !results.some(result => result.source_id === item.source_id && (result.id || result.error)))) throw new Error('提交结果不完整');
      const accepted = results.filter(result => result.id).map(result => result.source_id);
      pending.current = null; setUncertain(false);
      setEntries(previous => previous.filter(item => !accepted.includes(item.original.id)).map(item => ({ ...item, error: results.find(result => result.source_id === item.original.id)?.error || item.error })));
      if (accepted.length) onQueued(accepted);
      if (accepted.length === entries.length) onClose();
      else setError(`已加入 ${accepted.length} 条，剩余 ${entries.length-accepted.length} 条未提交成功。原片保留，可调整后重试或移出本批。`);
    } catch (e) {
      setUncertain(true); setError(`暂未确认提交结果：${message(e)}。请点击“确认提交结果”重新获取；已入队的任务不会重复创建。`);
    } finally {
      submitting.current = false; setBusy(false);
    }
  };
  const active = entries.find(item => item.original.id === editing);
  return <div className="fixed inset-0 z-[100] bg-black/60 p-4 flex justify-center items-center">
    <div role="dialog" aria-modal="true" aria-label="批量裁切风景" className="bg-white rounded-3xl w-full max-w-6xl max-h-[94vh] flex flex-col">
      <header className="p-5 border-b border-slate-100 flex justify-between gap-4"><div><h3 className="font-black">批量裁切风景</h3><p className="text-xs text-slate-500 mt-1">默认竖版三块取景，横版保留完整画面；超过30秒随机切段，主要15—28秒。全部无声，提交后后台逐条处理。</p></div><button aria-label="关闭批量裁切" disabled={busy} onClick={onClose}><X className="w-5 h-5" /></button></header>
      <div className="p-5 overflow-y-auto space-y-4">
        <div className="flex items-center gap-2 flex-wrap"><select aria-label="批量裁切布局" className={`${button} bg-white`} disabled={locked} value={layout} onChange={e=>setLayout(e.target.value === 'auto' ? 'auto' : Number(e.target.value) as CropLayout)}><option value="auto">竖版三块、横版完整画面</option><option value="1">每条一块画面</option><option value="2">每条两块画面</option><option value="3">每条三块画面</option></select><button className={button} disabled={locked} onClick={applyLayout}>应用到本批全部</button><span className="text-xs text-slate-500">画面布局与时间切段分别计算；重新应用会覆盖单独调整</span></div>
        {loading && <p role="status" className="text-xs text-slate-500">正在读取视频尺寸（{entries.filter(item=>item.detail||item.error).length}/{entries.length}）…</p>}
        <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-3">
          {entries.map(item=><article key={item.original.id} aria-label={`批量原片 ${item.original.name}`} className="rounded-xl border border-slate-200 p-3 space-y-2">
            <h4 title={item.original.name} className="text-sm font-bold truncate">{item.original.name}</h4>
            {item.detail ? <>{!busy&&!uncertain&&<CropOverview entry={item}/>}<p className="text-xs text-slate-500">{item.detail.width}×{item.detail.height} · {item.detail.duration.toFixed(1)}秒 · <strong>{item.crops.length} 块取景 → {sceneryOutputCount(item.detail,item.crops)} 份短片</strong>{item.custom?' · 已单独调整':''}</p><p className="text-xs text-slate-500">{sceneryTimeSummary(item.detail)}</p>{!validCrops(item.crops,item.detail)&&<p className="text-xs text-rose-700">默认区域不适合这条视频，请单独调整或移出本批。</p>}</> : <p className="text-xs text-slate-500">{item.error?'视频读取失败':'读取中…'}</p>}
            {item.error&&<p role="alert" className="text-xs text-rose-700 break-words">{item.error}</p>}
            <div className="flex gap-2"><button className={button} disabled={locked||!item.detail} onClick={()=>setEditing(item.original.id)}>预览并单独调整</button><button className={button} disabled={locked} onClick={()=>setEntries(previous=>previous.filter(entry=>entry.original.id!==item.original.id))}>移出本批</button></div>
          </article>)}
        </div>
      </div>
      <footer className="border-t border-slate-100 p-5 space-y-3">
        <p className="text-xs text-amber-900 bg-amber-50 rounded-xl p-3">每条原片对应的结果全部成功入库后，才删除这条原片。失败的保留，其他继续；移出本批不会删除文件。</p>
        {error&&<p role="alert" className="text-sm text-rose-700">{error}</p>}
        {!loading&&ready.length<entries.length&&<p className="text-xs text-slate-500">{entries.length-ready.length} 条无法提交，请单独调整或移出；其余可正常提交。</p>}
        <div className="flex justify-between items-center gap-4"><span className="text-sm font-bold">可提交 {ready.length} 条原片，生成 {count} 份素材</span><button className={`${button} bg-slate-900 text-[#DDFD00]`} disabled={busy||loading||(!uncertain&&!ready.length)||ready.length>200} onClick={()=>void submit()}>{busy?'正在提交队列…':uncertain?'确认提交结果':`提交 ${ready.length} 条到队列`}</button></div>
        {ready.length>200&&<p role="alert" className="text-xs text-rose-700">每批最多200条，请移出部分视频后提交。</p>}
      </footer>
    </div>
    {active?.detail&&<CropEditor source={active.detail} initial={active.crops} onClose={()=>setEditing(null)} onSave={crops=>{setEntries(items=>items.map(item=>item.original.id===active.original.id?{...item,crops,custom:true,error:undefined,requestId:crypto.randomUUID()}:item));setEditing(null);}}/>}
  </div>;
}
