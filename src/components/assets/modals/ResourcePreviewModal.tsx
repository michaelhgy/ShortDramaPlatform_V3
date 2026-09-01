import React, { useState } from 'react';
import { X, Play, Pause, Volume2, Copy, Check, FolderOpen, Video, Image as ImageIcon, Music, Sparkles } from 'lucide-react';

export interface PreviewResourceData {
  title: string;
  categoryName: string;
  type: 'video' | 'image' | 'audio';
  filePath: string;
  fileSizeMb?: number;
  durationText?: string;
  resolution?: string;
  tags?: string[];
  metrics?: {
    playCountText?: string;
    revenue?: number;
    roiText?: string;
  };
  sourceDramaName?: string;
  sourceAccountName?: string;
  thumbnailUrl?: string;
  mediaUrl?: string;
}

interface ResourcePreviewModalProps {
  isOpen: boolean;
  onClose: () => void;
  resource: PreviewResourceData | null;
  onOpenFolder?: (path: string) => void;
}

export const ResourcePreviewModal: React.FC<ResourcePreviewModalProps> = ({
  isOpen,
  onClose,
  resource,
  onOpenFolder,
}) => {
  const [copied, setCopied] = useState(false);
  const [isPlaying, setIsPlaying] = useState(true);

  if (!isOpen || !resource) return null;

  const handleCopyPath = () => {
    navigator.clipboard.writeText(resource.filePath);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const getFolderDirectory = (filePath: string) => {
    const lastSlash = filePath.lastIndexOf('\\') !== -1 ? filePath.lastIndexOf('\\') : filePath.lastIndexOf('/');
    return lastSlash !== -1 ? filePath.substring(0, lastSlash) : filePath;
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/50 backdrop-blur-xs animate-in fade-in duration-150" onClick={onClose}>
      <div className="bg-white w-full max-w-2xl rounded-2xl shadow-2xl border border-black/[0.08] overflow-hidden flex flex-col max-h-[90vh]" onClick={(event) => event.stopPropagation()}>
        {/* Header */}
        <div className="px-6 py-4 border-b border-black/[0.06] flex items-center justify-between bg-slate-50/80">
          <div className="flex items-center gap-2.5">
            <div className="w-8 h-8 rounded-xl bg-[#1A1D2E] text-[#DDFD00] flex items-center justify-center">
              {resource.type === 'video' ? (
                <Video className="w-4 h-4" />
              ) : resource.type === 'image' ? (
                <ImageIcon className="w-4 h-4" />
              ) : (
                <Music className="w-4 h-4" />
              )}
            </div>
            <div>
              <h3 className="font-bold text-sm text-[#1A1D2E] line-clamp-1">{resource.title}</h3>
              <p className="text-xs text-[#64748B] flex items-center gap-2">
                <span>时长：{resource.durationText || '—'}</span>
                {resource.fileSizeMb != null && <span>· 大小: {resource.fileSizeMb}MB</span>}
                <span>· 分辨率: {resource.resolution || '—'}</span>
              </p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="p-1.5 rounded-lg text-slate-400 hover:text-slate-700 hover:bg-black/5 transition-colors cursor-pointer"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Media Preview Canvas */}
        <div className="p-6 overflow-y-auto space-y-4 text-xs">
          {/* Main Visual Display */}
          <div className="relative rounded-2xl overflow-hidden bg-slate-900 flex items-center justify-center min-h-[260px] border border-black/[0.08] shadow-inner">
            {resource.type === 'video' ? (
                resource.mediaUrl ? <video src={resource.mediaUrl} poster={resource.thumbnailUrl} controls autoPlay muted playsInline className="w-full max-h-[560px] object-contain" /> : <div className="w-full flex flex-col items-center justify-center p-8 text-center text-white">
                <div className="w-16 h-16 rounded-full bg-white/20 backdrop-blur-md flex items-center justify-center text-[#DDFD00] shadow-lg mb-3">
                  <Video className="w-8 h-8" />
                </div>
                <p className="font-bold text-sm text-white mb-1">{resource.title}</p>
                <p className="text-xs text-slate-300 font-mono">
                  {resource.resolution || '1080x1920 60fps'} · {resource.durationText || '00:15'}
                </p>
                <div className="mt-4 flex items-center gap-2 px-3 py-1.5 rounded-full bg-white/10 text-[11px] text-slate-200 backdrop-blur-xs">
                  <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse" />
                  <span>本地视频媒体流通道已挂载</span>
                </div>
                </div>
            ) : resource.type === 'image' ? (
              <div className="w-full h-72 flex items-center justify-center relative overflow-hidden bg-slate-950">
                <img
                  src={resource.mediaUrl || resource.thumbnailUrl}
                  alt={resource.title}
                  className="max-h-full max-w-full object-contain"
                />
              </div>
            ) : (
              <div className="w-full p-8 flex flex-col items-center justify-center text-white">
                <div className="w-16 h-16 rounded-full bg-emerald-500/20 border border-emerald-500/40 text-emerald-300 flex items-center justify-center shadow-lg mb-4">
                  <Music className="w-8 h-8" />
                </div>
                <p className="font-bold text-base text-white mb-1">{resource.title}</p>
                <p className="text-xs text-slate-300 font-mono mb-4">
                  音频时长: {resource.durationText || '01:35'} · 高保真 320kbps
                </p>

                {/* Animated simulated waveform */}
                <div className="w-full max-w-md flex items-center gap-1 h-10 px-4 py-2 bg-white/5 rounded-xl border border-white/10">
                  <button
                    onClick={() => setIsPlaying(!isPlaying)}
                    className="p-1.5 rounded-lg bg-[#DDFD00] text-[#1A1D2E] font-bold mr-2 hover:scale-105 transition-transform cursor-pointer"
                  >
                    {isPlaying ? <Pause className="w-3.5 h-3.5" /> : <Play className="w-3.5 h-3.5" />}
                  </button>
                  {Array.from({ length: 28 }).map((_, i) => (
                    <div
                      key={i}
                      className="flex-1 bg-emerald-400 rounded-full transition-all duration-300"
                      style={{
                        height: isPlaying ? `${Math.max(15, (Math.sin(i * 0.8) * 0.5 + 0.5) * 100)}%` : '20%',
                        opacity: isPlaying ? 0.9 : 0.4,
                      }}
                    />
                  ))}
                  <Volume2 className="w-4 h-4 text-slate-400 ml-2" />
                </div>
              </div>
            )}
          </div>

          {/* Performance Badge if Viral Asset */}
          {resource.metrics && (
            <div className="p-3.5 rounded-xl bg-emerald-50 border border-emerald-200/80 flex items-center justify-between">
              <div className="flex items-center gap-2">
                <Sparkles className="w-4 h-4 text-emerald-700" />
                <div>
                  <span className="font-bold text-emerald-950 text-xs">爆款业务战报</span>
                  <span className="text-emerald-700 text-[11px] ml-2">
                    {resource.sourceDramaName ? `来源: 《${resource.sourceDramaName}》` : ''}
                    {resource.sourceAccountName ? ` · ${resource.sourceAccountName}` : ''}
                  </span>
                </div>
              </div>
              <div className="flex items-center gap-3 font-mono text-xs">
                <span className="text-emerald-900 font-semibold">{resource.metrics.playCountText}</span>
                {resource.metrics.revenue && (
                  <span className="px-2 py-0.5 rounded bg-emerald-600 text-white font-bold">
                    ¥{resource.metrics.revenue.toLocaleString()}
                  </span>
                )}
                {resource.metrics.roiText && (
                  <span className="px-2 py-0.5 rounded bg-white text-emerald-800 font-bold border border-emerald-200">
                    {resource.metrics.roiText}
                  </span>
                )}
              </div>
            </div>
          )}

          {/* Tags */}
          {resource.tags && resource.tags.length > 0 && (
            <div className="flex flex-wrap items-center gap-1.5">
              <span className="text-slate-400 font-medium mr-1">特征标签:</span>
              {resource.tags.map(t => (
                <span key={t} className="px-2 py-0.5 rounded-md bg-slate-100 text-slate-700 text-[11px] font-medium">
                  #{t}
                </span>
              ))}
            </div>
          )}

          {/* Windows Local File Path Bar */}
          <div className="p-3.5 rounded-xl bg-slate-50 border border-black/[0.06] space-y-2">
            <div className="flex items-center justify-between">
              <span className="font-bold text-[#1A1D2E] flex items-center gap-1.5">
                <FolderOpen className="w-3.5 h-3.5 text-slate-500" />
                Windows 本地文件路径
              </span>
              <div className="flex items-center gap-2">
                <button
                  type="button"
                  onClick={handleCopyPath}
                  className="flex items-center gap-1 px-2.5 py-1 rounded-lg bg-white border border-black/[0.08] hover:bg-slate-50 text-slate-700 font-medium transition-colors cursor-pointer text-[11px]"
                >
                  {copied ? <Check className="w-3 h-3 text-emerald-600" /> : <Copy className="w-3 h-3" />}
                  <span>{copied ? '已复制路径' : '复制路径'}</span>
                </button>
                {onOpenFolder && (
                  <button
                    type="button"
                    onClick={() => onOpenFolder(getFolderDirectory(resource.filePath))}
                    className="flex items-center gap-1 px-2.5 py-1 rounded-lg bg-[#1A1D2E] hover:bg-black text-[#DDFD00] font-bold transition-colors cursor-pointer text-[11px]"
                  >
                    <FolderOpen className="w-3 h-3" />
                    <span>打开所在文件夹</span>
                  </button>
                )}
              </div>
            </div>
            <div className="p-2 rounded-lg bg-white border border-black/[0.06] font-mono text-[11px] text-slate-600 break-all select-all">
              {resource.filePath}
            </div>
          </div>
        </div>

        {/* Footer */}
        <div className="px-6 py-4 border-t border-black/[0.06] flex items-center justify-end bg-slate-50/60">
          <button
            type="button"
            onClick={onClose}
            className="px-5 py-2 rounded-xl bg-[#1A1D2E] text-white text-xs font-bold hover:bg-black/90 active:scale-[0.98] transition-all cursor-pointer"
          >
            关闭预览
          </button>
        </div>
      </div>
    </div>
  );
};
