import React, { useEffect, useState } from 'react';
import { RefreshCw, SlidersHorizontal } from 'lucide-react';
import { getGenerationConfig, saveGenerationConfig, type TemplateConfig, type GenerationConfigResponse } from '../../api/templateGeneration';
const groups: { title: string; fields: [string, string][] }[] = [
  { title: '全局与风景', fields: [['duration_seconds','模板时长（秒）'],['duration_jitter','时长正负误差（秒）'],['scenery_count','上下合计风景候选条数'],['scenery_count_jitter','条数正负误差'],['scenery_usage_limit','每条风景使用上限'],['template_usage_limit','每个模板使用上限（剧集数）'],['scenery_group_gap_percent','两组初始时长差（占长组 %）']] },
  { title: '风景区域与融合', fields: [['height_large_percent','大区域高度（画面 %）'],['height_small_percent','小区域高度（画面 %）'],['mask_percent','蒙版位置（本区域 %）'],['feather_percent','羽化宽度（本区域 %）']] },
  { title: '贴纸、特效与边条', fields: [['sticker_alpha_percent','贴纸整体透明度系数（%）'],['effect_count','每模板特效类型数'],['effect_segment_seconds','单段特效时长（秒）'],['effect_strength_percent','特效基准强度（%）'],['effect_pair_percent','双特效时长占比（%）'],['effect_transition_seconds','特效切换过渡（秒）'],['border_width','左右边条宽度（像素）']] },
  { title: '全屏贴纸叠层（独立素材库）', fields: [['overlay_sticker_enabled','启用全屏贴纸叠层'],['overlay_sticker_count','每模板叠层贴纸数量'],['overlay_sticker_opacity_percent','贴纸叠层可见程度（%，越小越淡）']] },
  { title: '真人图片叠层', fields: [['photo_layer_enabled','启用真人图片叠层'],['photo_layer_count','每模板真人图片数量'],['photo_layer_opacity_percent','真人叠层可见程度（%，越小越淡）'],['photo_usage_limit','每张真人图片使用上限（成功模板数）']] },
];
export const TemplateParameters: React.FC<{showToast: (s:string)=>void}> = ({ showToast }) => {
  const [response,setResponse]=useState<GenerationConfigResponse|null>(null),[value,setValue]=useState<TemplateConfig|null>(null);
  const [error,setError]=useState(''),[busy,setBusy]=useState(false),[saved,setSaved]=useState(false);
  const load=async()=>{setBusy(true);try{const r=await getGenerationConfig();setResponse(r);setValue(r.config);setError('');setSaved(false);}catch(e){setError(String(e instanceof Error?e.message:e));}finally{setBusy(false);}};
  useEffect(()=>{void load();},[]);
  const save=async()=>{if(!value)return;setBusy(true);try{const r=await saveGenerationConfig(value);setValue(r.config);setSaved(true);setError('');showToast('模板参数已保存，新建批次使用新参数');}catch(e){setError(String(e instanceof Error?e.message:e));}finally{setBusy(false);}};
  return <section className="rounded-3xl border border-black/[0.06] bg-white p-6 shadow-xs space-y-5" aria-label="模板生成参数">
    <div className="flex flex-wrap items-center justify-between gap-3"><div><h3 className="flex items-center gap-2 font-black text-lg text-[#1A1D2E]"><SlidersHorizontal className="h-5 w-5"/>模板生成参数</h3><p className="text-xs text-slate-500 mt-1">1080 × 2400 · 30帧。每个模板重新随机；已创建批次保留当时参数。</p></div><div className="flex gap-2"><button type="button" onClick={()=>void load()} disabled={busy} className="rounded-xl bg-slate-100 px-3 py-2 text-xs font-bold disabled:opacity-40"><RefreshCw className="inline h-3 w-3 mr-1"/>重新读取模板参数</button><button type="button" onClick={()=>void save()} disabled={busy||!value} className="rounded-xl bg-[#1A1D2E] text-[#DDFD00] px-4 py-2 text-xs font-bold disabled:opacity-40">{busy?'处理中…':'保存模板参数'}</button></div></div>
    <div className="rounded-xl bg-blue-50 p-3 text-xs leading-6 text-blue-900">“建议区间”供你参考，可以输入区间外的数值。“下限／上限”是每个模板随机抽取的范围，两者相同表示固定值。百分比、正整数、画面尺寸等基本规则写在每项下面。</div>
    {error&&<p role="alert" className="rounded-xl bg-rose-50 p-3 text-sm text-rose-700">{error}</p>}
    {saved&&<p role="status" className="text-sm text-emerald-700">已保存。素材使用上限与模板使用上限立即生效，叠层和排布规则用于新建模板批次。</p>}
    {!value&&!error&&<p>正在读取模板参数…</p>}
    {value&&response&&groups.map(group=><fieldset key={group.title} className="border-t border-slate-100 pt-3"><legend className="px-2 text-sm font-bold text-slate-700">{group.title}</legend><div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">{group.fields.map(([key,fallbackLabel])=>{
      const current=value[key],info=response.fields?.[key],label=info?.label??fallbackLabel;
      const suggested=(response.suggested_ranges??response.limits)[key],helpId=`template-${key}-help`;
      const help=<div id={helpId} className="mt-2 space-y-2 text-xs leading-5"><p className="text-slate-600">{info?.description??'重新启动源码版后，可读取这个参数的详细说明。'}</p>{info?.rule&&<p className="text-slate-500">基本规则：{info.rule}</p>}</div>;
      if(typeof current==='boolean')return <div key={key} data-parameter-key={key} className="rounded-xl bg-slate-50 p-4"><label className="flex items-center gap-3 text-sm font-bold text-slate-700"><input type="checkbox" aria-label={label} aria-describedby={helpId} checked={current} disabled={busy} onChange={e=>{setSaved(false);setValue({...value,[key]:e.target.checked});}}/>{label}</label>{help}</div>;
      const numbers=Array.isArray(current)?current:[current];
      const outside=suggested&&numbers.some(n=>n<suggested[0]||n>suggested[1]);
      return <div key={key} data-parameter-key={key} className="rounded-xl bg-slate-50 p-4">
        <label className="text-xs font-bold text-slate-700" htmlFor={`template-${key}`}>{label}</label>
        {suggested&&<p className="mt-1 text-[11px] text-slate-500">建议区间：{suggested[0]}—{suggested[1]} {info?.unit}（可自行调整）</p>}
        <div className="mt-2 flex items-start gap-2">{numbers.map((n,i)=><div key={i} className="min-w-0 flex-1">
          {Array.isArray(current)&&<span className="mb-1 block text-[11px] text-slate-500">{i===0?'下限':'上限'}</span>}
          <input id={i===0?`template-${key}`:undefined} aria-label={`${label}${Array.isArray(current)?i===0?'下限':'上限':''}`} aria-describedby={helpId} type="number" step={1} value={n} disabled={busy}
            onChange={e=>{const next=Number(e.target.value);setSaved(false);setValue({...value,[key]:Array.isArray(current)?current.map((v,j)=>i===j?next:v) as [number,number]:next});}}
            className="w-full min-w-0 rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm"/>
        </div>)}</div>
        {outside&&<p className="mt-2 text-[11px] text-slate-500">当前值在建议区间外，符合基本规则即可保存。</p>}{help}
      </div>;
    })}</div></fieldset>)}
    <p className="text-xs text-slate-500">上下装饰贴纸保持原有16个及动画规则；全屏叠层使用独立贴纸库（{response?.library.fullscreen_stickers ?? '—'}个）。新叠层默认关闭，启用后按数量范围随机抽取，6—6表示固定6张。两种叠层均为静态铺排，制作模板时合入缓存，成片直接复用。</p>
    <p className="text-xs text-slate-500">风景只对实际排进播放时间轴的素材预留，成功后计次；没播到的候选不占次数，同一素材循环或只播一部分均计1次。真人图片按所选图片计成功模板次数。失败或取消不计次；用满且无任务占用后自动删除素材文件，已完成模板继续可用。删除模板不返还次数，调低使用上限可能立即清理已用满素材。</p>
  </section>;
};
