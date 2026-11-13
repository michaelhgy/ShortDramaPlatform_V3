import React, { useEffect, useRef, useState } from 'react';
import { X, Play, Pause, Trash2 } from 'lucide-react';
import { createSceneryJob, type CropRect, type SceneryDetail } from '../../api/scenery';
import { initialCrops, validCrops, sceneryOutputCount, sceneryTimeSummary } from './sceneryCrops';

const button='rounded-xl border border-slate-200 px-3 py-2 text-xs font-bold disabled:opacity-40 disabled:cursor-not-allowed';
const even=(n:number)=>Math.round(n/2)*2;
const colors=['#eab308','#22d3ee','#f472b6','#a3e635'];
function CropPreview({ video, crop }: {video: React.RefObject<HTMLVideoElement|null>;crop:CropRect}) {
  const canvas=useRef<HTMLCanvasElement>(null);
  useEffect(()=>{const draw=()=>{const el=video.current,c=canvas.current;if(el&&c&&el.readyState>=2&&crop.width>0&&crop.height>0)c.getContext('2d')?.drawImage(el,crop.x,crop.y,crop.width,crop.height,0,0,c.width,c.height);};draw();const id=setInterval(draw,160);return()=>clearInterval(id);},[video,crop]);
  return <canvas ref={canvas} width={360} height={Math.max(1,Math.round(360*crop.height/crop.width))} className="w-full rounded-lg bg-slate-950"/>;
}
export function CropEditor({ source, initial, onClose, onSubmitted, onSave }: {
  source:SceneryDetail; initial?:CropRect[]; onClose:()=>void; onSubmitted?:()=>void; onSave?:(crops:CropRect[])=>void;
}) {
  const [crops,setCrops]=useState(()=>initial || initialCrops(source.width,source.height,'auto'));
  const [selected,setSelected]=useState(0),[busy,setBusy]=useState(false),[error,setError]=useState(''),[time,setTime]=useState(0),[playing,setPlaying]=useState(false);
  const video=useRef<HTMLVideoElement>(null),box=useRef<HTMLDivElement>(null),request=useRef(crypto.randomUUID());
  const drag=useRef<{index:number;mode:'move'|'resize';x:number;y:number;rect:CropRect}|null>(null);
  const change=(next:CropRect[])=>{setCrops(next);request.current=crypto.randomUUID();};
  const invalid=!validCrops(crops,source);
  const update=(key:keyof CropRect,value:number)=>change(crops.map((c,i)=>i===selected?{...c,[key]:even(Number.isFinite(value)?value:0)}:c));
  const submit=async()=>{if(onSave){video.current?.pause();onSave(crops);return;}setBusy(true);setError('');video.current?.pause();try{await createSceneryJob(source.id,crops,request.current);video.current?.removeAttribute('src');video.current?.load();onSubmitted?.();}catch(e){setError(e instanceof Error?e.message:String(e));}finally{setBusy(false);}};
  const move=(e:React.PointerEvent)=>{const d=drag.current,area=box.current;if(!d||!area||busy)return;const r=area.getBoundingClientRect();let c={...d.rect};const dx=even((e.clientX-d.x)*source.width/r.width),dy=even((e.clientY-d.y)*source.height/r.height);
    if(d.mode==='move'){c.x=even(Math.max(0,Math.min(source.width-c.width,c.x+dx)));c.y=even(Math.max(0,Math.min(source.height-c.height,c.y+dy)));}
    else {c.width=even(Math.max(32,Math.min(source.width-c.x,c.width+dx)));c.height=even(Math.max(32,Math.min(source.height-c.y,c.height+dy)));}
    change(crops.map((v,i)=>i===d.index?c:v));};
  return <div className="fixed inset-0 z-[100] bg-black/60 p-4 flex justify-center items-center"><div role="dialog" aria-modal="true" aria-label="人工裁切风景" className="bg-white rounded-3xl w-full max-w-6xl max-h-[94vh] overflow-y-auto p-5 space-y-4">
    <header className="flex justify-between gap-4"><div className="min-w-0"><h3 className="font-black">人工裁切风景</h3><p title={source.name} className="text-xs text-slate-500 truncate mt-1">{source.name} · {source.width} × {source.height} · {source.duration.toFixed(1)} 秒</p></div><button aria-label="关闭裁切" disabled={busy} onClick={onClose}><X className="w-5 h-5"/></button></header>
    <div className="grid md:grid-cols-[minmax(0,1fr)_minmax(300px,1fr)] gap-6">
      <div className="space-y-3"><div ref={box} style={{aspectRatio:`${source.width}/${source.height}`,maxHeight:'60vh',width:source.width>source.height?'100%':'auto'}} className="relative mx-auto bg-slate-950 overflow-hidden touch-none" onPointerMove={move} onPointerUp={()=>drag.current=null} onPointerCancel={()=>drag.current=null}>
        <video ref={video} src={source.media_url} muted playsInline onTimeUpdate={()=>setTime(video.current?.currentTime||0)} onPlay={()=>setPlaying(true)} onPause={()=>setPlaying(false)} className="h-full w-full"/>
        {crops.map((c,i)=><div key={i} aria-label={`裁切框${i+1}`} style={{left:`${c.x/source.width*100}%`,top:`${c.y/source.height*100}%`,width:`${c.width/source.width*100}%`,height:`${c.height/source.height*100}%`,borderColor:colors[i%colors.length],background:i===selected?'#ffffff0d':'transparent'}} className="absolute border-2 cursor-move" onPointerDown={e=>{if(busy)return;e.currentTarget.setPointerCapture(e.pointerId);setSelected(i);drag.current={index:i,mode:'move',x:e.clientX,y:e.clientY,rect:{...c}};}}>
          <span style={{background:colors[i%colors.length]}} className="text-xs text-black px-2 py-1">{i+1}</span><button aria-label={`缩放裁切框${i+1}`} className="absolute bottom-0 right-0 h-5 w-5 bg-white border border-black cursor-nwse-resize" onPointerDown={e=>{e.stopPropagation();if(busy)return;e.currentTarget.setPointerCapture(e.pointerId);setSelected(i);drag.current={index:i,mode:'resize',x:e.clientX,y:e.clientY,rect:{...c}};}}/>
        </div>)}
      </div><div className="flex items-center gap-3"><button aria-label={playing?'暂停原片':'播放原片'} onClick={()=>playing?video.current?.pause():void video.current?.play()}>{playing?<Pause className="w-4 h-4"/>:<Play className="w-4 h-4"/>}</button><input aria-label="原片时间" type="range" min={0} max={source.duration} step={.05} value={time} className="flex-1" onChange={e=>{if(video.current)video.current.currentTime=Number(e.target.value);setTime(Number(e.target.value));}}/><span className="text-xs tabular-nums">{time.toFixed(1)}秒</span></div><p className="text-xs text-slate-500">拖动框调整位置，拖右下角调整大小。播放或拖动时间，检查各时刻取景。</p></div>
      <div className="space-y-4"><div className="flex gap-2">{([1,2,3] as const).map(n=><button className={button} disabled={busy} key={n} onClick={()=>{change(initialCrops(source.width,source.height,n));setSelected(0);}}>布局 {n} 份</button>)}</div>
        <div className="flex gap-2">{crops.map((_,i)=><button key={i} className={`${button} ${selected===i?'bg-slate-900 text-white':''}`} onClick={()=>setSelected(i)}>第 {i+1} 份</button>)}<button className={button} disabled={busy||crops.length<=1} onClick={()=>{change(crops.filter((_,i)=>i!==selected));setSelected(0);}}><Trash2 className="w-3 h-3 inline mr-1"/>去掉本份</button></div>
        <div className="grid grid-cols-4 gap-2">{(['x','y','width','height'] as const).map((key,i)=><label key={key} className="text-xs text-slate-500">{['左侧','顶部','宽度','高度'][i]}<input aria-label={`裁切${key}`} type="number" step={2} disabled={busy} value={crops[selected][key]} onChange={e=>update(key,Number(e.target.value))} className="border rounded-lg px-2 py-2 mt-1 w-full text-slate-900"/></label>)}</div>
        <div className="grid grid-cols-2 gap-3 max-h-[35vh] overflow-y-auto">{crops.map((c,i)=><div key={i} className="space-y-1"><CropPreview video={video} crop={c}/><p className="text-xs text-slate-500">第{i+1}块取景 · {c.width} × {c.height}</p></div>)}</div>
        <p className="text-xs text-slate-600">{sceneryTimeSummary(source)}；{crops.length} 块取景共生成 {sceneryOutputCount(source,crops)} 份无声短片。横屏默认保留完整画面，符合规格的整段横片快速入库。</p>
        <p className="rounded-xl bg-amber-50 p-3 text-xs leading-6 text-amber-900">全部 {sceneryOutputCount(source,crops)} 份结果成功入库并核对后，才删除这条原片。分段不重叠、不遗漏；失败保留原片，重试沿用同一切法并复用已完成部分。</p>
        {invalid&&<p role="alert" className="text-xs text-rose-700">请把裁切框放在画面内，并保持宽度大于高度、尺寸至少32像素。</p>}{error&&<p role="alert" className="text-sm text-rose-700">{error}</p>}
        <button className={`${button} w-full bg-slate-900 text-[#DDFD00] py-3`} disabled={busy||invalid} onClick={()=>void submit()}>{busy?'正在提交…':onSave?'保存本条调整':`生成 ${sceneryOutputCount(source,crops)} 份，成功后删除原片`}</button>
      </div>
    </div>
  </div></div>;
}
