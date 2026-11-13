import { useRef, useState } from 'react';
import { ImageOff } from 'lucide-react';
import { publishingAction, type PublishGroup } from '../../api/publishing';

type CoverValue = Pick<PublishGroup, 'cover_mode' | 'cover_source' | 'custom_cover_id'>;
export function PublishingCoverControl({ taskId, value, onChange, automatic = [], disabled = false, label = '本组', onBusy }: {
  key?: string; taskId: string; value: Partial<CoverValue>; onChange: (patch: CoverValue) => void;
  automatic?: { url: string; exists: boolean; label: string }[]; disabled?: boolean; label?: string; onBusy?: (busy: boolean) => void;
}) {
  const input = useRef<HTMLInputElement>(null);
  const [loading, setLoading] = useState(false), [error, setError] = useState('');
  const enabled = value.cover_mode !== 'none';
  const source = value.cover_mode === 'custom' ? 'custom' : value.cover_source || 'auto';
  const locked = disabled || loading;
  function change(use: boolean, nextSource = source, id = value.custom_cover_id || '') {
    onChange({ cover_mode: use ? nextSource : 'none', cover_source: nextSource, custom_cover_id: id });
  }
  async function upload(file: File) {
    if (file.size > 15 * 1024 * 1024) { setError('封面图片最大15MB'); return; }
    setLoading(true); onBusy?.(true); setError('');
    try {
      const data_url = await new Promise<string>((resolve, reject) => {
        const reader = new FileReader(); reader.onload = () => resolve(String(reader.result)); reader.onerror = () => reject(Error('图片读取失败')); reader.readAsDataURL(file);
      });
      const image = await publishingAction<{ id: string }>(taskId, 'cover-import', { data_url });
      change(true, 'custom', image.id);
    } catch (e) { setError(e instanceof Error ? e.message : '封面保存失败，请重试'); }
    finally { setLoading(false); onBusy?.(false); }
  }
  const custom = source === 'custom';
  const images = custom ? [{ url: value.custom_cover_id ? `/api/v2/publishing/covers/${value.custom_cover_id}.jpg` : '', exists: Boolean(value.custom_cover_id), label: '自定义封面' }] : automatic;
  return <div className="space-y-2" aria-label={`${label}封面设置`}>
    <input ref={input} hidden type="file" accept="image/jpeg,image/png,image/webp" aria-label={`${label}选择封面图片`} disabled={locked} onChange={e => { const file = e.target.files?.[0]; e.target.value = ''; if (file) void upload(file); }} />
    <div className="flex items-start gap-3">
      <button type="button" aria-label={`${label}替换封面`} title="点击选择自定义封面图片" disabled={locked} onClick={() => input.current?.click()} className="group relative flex min-h-20 min-w-14 shrink-0 gap-1 overflow-hidden rounded-lg bg-slate-100 disabled:opacity-50">
        {images.length ? images.map((image, i) => image.exists ? <img key={image.url} src={image.url} alt={image.label} className={`${images.length > 1 ? 'h-20 w-12' : 'h-24 w-16'} object-cover`} /> : <span key={i} className="flex h-24 w-16 items-center justify-center"><ImageOff size={22} className="text-slate-400" /></span>) : <span className="flex h-24 w-16 items-center justify-center"><ImageOff size={22} className="text-slate-400" /></span>}
        <span className="absolute inset-x-0 bottom-0 bg-slate-950/60 py-0.5 text-[10px] text-white">{loading ? '保存中…' : '点击替换'}</span>
      </button>
      <div className="space-y-2 text-[11px] text-slate-600">
        <label className="flex items-center gap-1.5 font-bold"><input type="checkbox" aria-label={`${label}使用封面`} disabled={locked} checked={enabled} onChange={e => change(e.target.checked)} />使用封面</label>
        <div className={`space-y-1 ${enabled ? '' : 'opacity-50'}`}>
          <label className="flex items-center gap-1.5"><input type="radio" aria-label={`${label}使用自带`} disabled={locked || !enabled} checked={!custom} onChange={() => change(true, 'auto')} />使用自带</label>
          <label className="flex items-center gap-1.5"><input type="radio" aria-label={`${label}使用自定义`} disabled={locked || !enabled} checked={custom} onChange={() => value.custom_cover_id ? change(true, 'custom') : input.current?.click()} />使用自定义</label>
        </div>
        <p className="text-[10px] leading-4 text-slate-400">{!enabled ? '本组不使用封面' : custom ? '自定义图片已保存' : automatic.some(i => i.exists) ? '已自动带入对应封面' : '按当前剧集自动带入'}</p>
      </div>
    </div>
    {error && <p role="alert" className="text-[11px] text-rose-600">{error}</p>}
  </div>;
}
