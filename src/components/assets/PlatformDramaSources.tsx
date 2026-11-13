import React from 'react';
import type { PlatformDrama } from '../../api/dramaCatalog';

export function PlatformDramaSources({ sources = [], conflict = false }: { sources?: PlatformDrama[]; conflict?: boolean }) {
  if (!sources.length) return null;
  return <section className="rounded-2xl border border-slate-200 bg-white p-4 space-y-3">
    <div className="flex items-center justify-between"><h4 className="font-extrabold text-sm text-[#1A1D2E]">平台挂载资料</h4><span className="text-[11px] text-slate-400">获取时自动更新 · 保留全部来源</span></div>
    {conflict && <p className="text-xs text-amber-700 bg-amber-50 rounded-lg p-2">不同来源返回的官方集数有差异，以下分别保留，请核对具体版本。</p>}
    <div className="space-y-2">{sources.map(s => <div key={`${s.source}:${s.external_id}`} className="p-3 rounded-xl bg-slate-50 border border-slate-100 text-xs space-y-1.5">
      <div className="flex items-center gap-2"><span className="font-bold text-slate-600 bg-white border border-slate-200 px-2 py-0.5 rounded-md">{s.source === 'mini_drama' ? '小程序短剧' : '视频号剧集'}</span>{s.miniAppIconUrl && <img src={s.miniAppIconUrl} alt="" loading="lazy" className="w-5 h-5 rounded" />}<strong className="flex-1">{s.miniAppName || ''}</strong><span className="font-bold text-slate-700">官方 {s.mediaCount ?? '—'} 集</span></div>
      <p className="text-slate-700">挂载剧名：{s.name}</p>
      {s.srcMiniAppName && <p className="text-slate-500">原始平台：{s.srcMiniAppName}</p>}
      <p className="text-[10px] text-slate-400 break-all">挂载编号：{s.external_id}</p>
      {s.updated_at && <p className="text-[10px] text-slate-400">最近资料更新：{new Date(s.updated_at).toLocaleString('zh-CN')}</p>}
    </div>)}</div>
  </section>;
}
