import React, { useEffect, useRef } from 'react';
import { X } from 'lucide-react';
import { publishV2DataChange } from '../services/dataChangeEvents';
import { refreshArea } from '../services/dataHub';
import type { CoverKind } from './model';

export function CoverEditorModal({ dramaId, name, kind, onClose }: { dramaId: string; name: string; kind: CoverKind; onClose: () => void }) {
  const frame = useRef<HTMLIFrameElement>(null), previousFocus = useRef(document.activeElement as HTMLElement | null);
  const close = useRef(onClose); close.current = onClose;
  useEffect(() => {
    const listener = (event: MessageEvent) => {
      if (event.origin !== location.origin || event.source !== frame.current?.contentWindow) return;
      if (event.data?.type === 'v3-cover-close-allowed') close.current();
      if (event.data?.type === 'v3-cover-save-request') {
        const requestId = String(event.data.requestId || '');
        const reply = (result: Record<string, unknown>) => frame.current?.contentWindow?.postMessage({ type: 'v3-cover-save-result', requestId, ...result }, location.origin);
        const savePng = (window as any).pywebview?.api?.save_png;
        if (typeof savePng !== 'function') { reply({ native: false }); return; }
        void savePng(String(event.data.dataUrl || ''), String(event.data.filename || '封面.png')).then(reply).catch((error: unknown) => reply({ error: error instanceof Error ? error.message : '封面保存失败。' }));
      }
      if (event.data?.type === 'v3-cover-saved' && event.data.dramaId === dramaId) {
        publishV2DataChange({ changeType: 'profile_changed', dramaId, origin: 'client' }); void refreshArea('catalog');
      }
    };
    window.addEventListener('message', listener);
    return () => { window.removeEventListener('message', listener); previousFocus.current?.focus(); };
  }, [dramaId]);
  return <div className="fixed inset-0 z-[100] flex items-center justify-center bg-slate-950/45 p-3" role="dialog" aria-modal="true" aria-label="封面编辑" onKeyDown={event=>{if(event.key==='Escape'){event.preventDefault();event.stopPropagation();frame.current?.contentWindow?.postMessage({type:'v3-cover-close-request'},location.origin);}}}>
    <div className="flex h-[92vh] w-full max-w-[1160px] flex-col overflow-hidden rounded-2xl bg-white shadow-2xl">
      <div className="flex shrink-0 items-center justify-between border-b border-slate-100 px-5 py-3"><div><strong className="text-sm">编辑封面 · {name}</strong><p className="mt-1 text-[11px] text-slate-400">本剧共用 · 两套各保留原图和3张修改版 · 通用模板最多5个</p></div>
        <button autoFocus aria-label="关闭封面编辑" className="rounded-lg p-2 text-slate-500 hover:bg-slate-100" onClick={() => frame.current?.contentWindow?.postMessage({ type: 'v3-cover-close-request' }, location.origin)}><X size={18} /></button></div>
      <iframe ref={frame} title="封面文字编辑器" src={`/cover-editor.html?dramaId=${encodeURIComponent(dramaId)}&kind=${kind}`} className="min-h-0 w-full flex-1 border-0" />
    </div>
  </div>;
}
