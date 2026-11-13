import React, { useEffect, useRef, useState } from 'react';
import { Play, X } from 'lucide-react';
import { DramaCover } from '../DramaCover';
import { CockpitModal } from './CockpitModal';
import type { VideoTrafficItem } from '../../types/shortDramaOps';

/** Keep the existing cover footprint; only this button opens playback. */
export const WorkVideoCover: React.FC<{ video: VideoTrafficItem; size?: 'sm' | 'md' | 'lg' }> = ({ video, size = 'md' }) => {
  const [open, setOpen] = useState(false);
  const player = useRef<HTMLVideoElement>(null);
  const [failed, setFailed] = useState(false);
  const [coverFailed, setCoverFailed] = useState(false);
  useEffect(() => setFailed(false), [video.videoUrl]);
  useEffect(() => setCoverFailed(false), [video.coverUrl]);
  useEffect(() => {
    if (!open) return;
    const element = player.current;
    return () => { element?.pause(); element?.removeAttribute('src'); element?.load(); };
  }, [open, video.videoUrl]);
  const cover = coverFailed ? video.fallbackCoverUrl : video.coverUrl;
  return <>
    <button type="button" title={`播放 ${video.fileName}`} aria-label={`播放 ${video.fileName}`}
      onClick={event => { event.stopPropagation(); setFailed(false); setOpen(true); }}
      className="relative block shrink-0 rounded-lg p-0 text-left focus-visible:outline-2 focus-visible:outline-indigo-500 group/work-cover"
      onErrorCapture={() => setCoverFailed(true)}>
      <DramaCover key={cover || video.id} name={video.dramaTitle} coverUrl={cover} size={size} />
      <span aria-hidden="true" className="pointer-events-none absolute inset-0 flex items-center justify-center rounded-[inherit] bg-black/15 opacity-0 transition-opacity group-hover/work-cover:opacity-100 group-focus-visible/work-cover:opacity-100">
        <Play className="h-5 w-5 fill-white text-white drop-shadow" />
      </span>
    </button>
    {open && <CockpitModal label="播放作品" onClose={() => setOpen(false)} width="max-w-3xl" testId="work-video-player">
      <div className="flex items-center justify-between gap-3 border-b border-slate-100 px-5 py-4">
        <div className="min-w-0"><h3 className="truncate text-sm font-bold text-slate-900" title={video.fileName}>{video.fileName}</h3>
          <p className="mt-1 text-xs text-slate-500">{video.accountName} · {video.publishTime}</p></div>
        <button type="button" onClick={() => setOpen(false)} aria-label="关闭视频播放" className="rounded-lg p-2 text-slate-500 hover:bg-slate-100"><X className="h-4 w-4" /></button>
      </div>
      <div className="min-h-0 overflow-auto bg-slate-950 p-3">
        {video.videoUrl ? <video ref={player} key={video.videoUrl} src={video.videoUrl} poster={cover} controls autoPlay playsInline preload="metadata"
          onError={() => setFailed(true)} className="mx-auto block max-h-[70dvh] max-w-full" />
          : <p role="status" className="p-8 text-center text-sm text-slate-200">暂无视频地址，请更新作品数据后再试。</p>}
        {failed && <p role="status" className="p-3 text-center text-sm text-amber-200">视频无法播放，链接可能已失效。请更新作品数据后再试。</p>}
      </div>
    </CockpitModal>}
  </>;
};
