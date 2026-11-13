import React, { useEffect, useRef, useState } from 'react';
import { ImagePlus, LoaderCircle } from 'lucide-react';
import { getTaskCoverContext } from '../../api/covers';
import { uploadV2DramaCover } from '../../api/v2Catalog';
import { eventDetail } from '../../services/dataChangeEvents';
import { CoverEditorModal } from '../../coverEditor/CoverEditorModal';
import type { CoverKind } from '../../coverEditor/model';

export function DramaTaskCover({ taskId, name, showToast }: { key?: string; taskId: string; name: string; showToast: (text: string) => void }) {
  const [cover, setCover] = useState({ dramaId: '', url: '', sheepUrl: '', sheepVisible: false });
  const [busy, setBusy] = useState<CoverKind | ''>('');
  const [broken, setBroken] = useState({ drama: false, sheep: false });
  const [editing, setEditing] = useState<CoverKind | null>(null);
  const [loadError, setLoadError] = useState('');
  const target = useRef<CoverKind>('drama');
  const input = useRef<HTMLInputElement>(null);
  useEffect(() => {
    let active = true;
    setCover({ dramaId: '', url: '', sheepUrl: '', sheepVisible: false }); setEditing(null);
    const load = () => getTaskCoverContext(taskId).then(data => {
      if (active) { setCover({ dramaId: data.drama.id, url: data.cover.exists ? data.cover.url : '', sheepUrl: data.sheep_cover?.exists ? data.sheep_cover.url : '', sheepVisible: !!data.sheep_cover_visible }); setBroken({ drama: false, sheep: false }); setLoadError(''); }
    }).catch(error => { if (active) setLoadError(error.message); });
    void load();
    const changed = (event: Event) => { if (eventDetail(event).changeType === 'profile_changed') void load(); };
    window.addEventListener('v2-data-changed', changed);
    return () => { active = false; window.removeEventListener('v2-data-changed', changed); };
  }, [taskId]);
  async function replace(file?: File) {
    if (!file || !cover.dramaId) return;
    const kind = target.current; setBusy(kind);
    try {
      const content = await new Promise<string>((resolve, reject) => {
        const reader = new FileReader(); reader.onload = () => resolve(String(reader.result)); reader.onerror = reject; reader.readAsDataURL(file);
      });
      await uploadV2DramaCover(cover.dramaId, { filename: file.name, content_base64: content, kind });
      const data = await getTaskCoverContext(taskId);
      setCover({ dramaId: data.drama.id, url: data.cover.url, sheepUrl: data.sheep_cover?.url || '', sheepVisible: !!data.sheep_cover_visible }); setBroken({ drama: false, sheep: false });
      showToast(`${kind === 'drama' ? '剧集' : '羊头'}封面已保存，同一部剧的其他任务同步使用。`);
    } catch (error) { showToast(error instanceof Error ? error.message : '封面保存失败'); }
    finally { setBusy(''); }
  }
  return <>
    <input ref={input} type="file" className="hidden" accept=".jpg,.jpeg,.png,.webp,.gif" aria-label="替换剧集封面文件" onChange={e => { void replace(e.target.files?.[0]); e.target.value = ''; }} />
    <div className="flex shrink-0 items-start gap-2" data-testid="task-cover-pair">{(['drama', ...(cover.sheepVisible ? ['sheep'] : [])] as CoverKind[]).map(kind => {
      const url = kind === 'drama' ? cover.url : cover.sheepUrl, title = kind === 'drama' ? '剧集' : '羊头';
      return <button key={kind} type="button" data-testid={`task-${kind}-cover`} data-drama-id={cover.dramaId} disabled={!!busy} onClick={() => { if (!cover.dramaId) return showToast(loadError || '封面正在加载，请稍候'); target.current = kind; if (input.current) input.current.setAttribute('aria-label', `替换${title}封面文件`); input.current?.click(); }}
      onContextMenu={event => { event.preventDefault(); if (!cover.dramaId) return showToast(loadError || '封面正在加载，请稍候'); if (!url || broken[kind]) return showToast(!url ? `还没有${title}封面，请先左键点击上传图片。` : `${title}封面文件无法读取，请左键重新选择图片。`); setEditing(kind); }}
      title={`${title}封面 · 左键替换原图 · 右键编辑文字与版本`}
      className="group relative h-[88px] w-[60px] shrink-0 overflow-hidden rounded-xl bg-[#172033] text-white shadow-sm disabled:opacity-60">
      {url && !broken[kind] ? <img src={url} alt={`${name}${title}封面`} className="h-full w-full object-cover" onError={() => setBroken(current => ({ ...current, [kind]: true }))} /> :
        <span className="flex h-full flex-col items-start justify-center gap-1 px-2 text-left"><span className="rounded bg-white/15 px-1.5 py-1 text-[10px] font-black text-[#DDFD00]">{title}</span><span className="line-clamp-2 text-[11px] font-bold leading-4">{name}</span></span>}
      {url && <span className="absolute bottom-0 left-0 right-0 bg-black/55 py-0.5 text-[9px] font-bold">{title}</span>}
      <span className="absolute inset-0 flex flex-col items-center justify-center gap-1 bg-black/60 text-[10px] opacity-0 transition-opacity group-hover:opacity-100 group-focus-visible:opacity-100">
        {busy === kind ? <LoaderCircle size={16} className="animate-spin" /> : <ImagePlus size={16} />}左换 · 右编
      </span>
    </button>; })}</div>
    {editing && <CoverEditorModal dramaId={cover.dramaId} name={name} kind={editing} onClose={() => setEditing(null)} />}
  </>;
}
