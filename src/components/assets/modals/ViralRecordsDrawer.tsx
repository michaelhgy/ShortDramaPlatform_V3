import React, { useState } from 'react';
import { ViralAssetItem, ViralRecordItem } from '../../../assetsTypes';
import {
  X,
  Sparkles,
  Film,
  Calendar,
  User,
  Tv,
  Coins,
  TrendingUp,
  FolderOpen,
  Copy,
  Check,
  Play,
  Hash,
  Clock,
  Layers,
  ArrowRight,
  Database,
  FileVideo,
  Send,
} from 'lucide-react';

interface ViralRecordsDrawerProps {
  isOpen: boolean;
  onClose: () => void;
  asset: ViralAssetItem | null;
  onOpenFolder: (path: string) => void;
  onPreview: (asset: ViralAssetItem) => void;
  onApplyToProduction?: (asset: ViralAssetItem) => void;
  onShowToast: (msg: string) => void;
}

export const ViralRecordsDrawer: React.FC<ViralRecordsDrawerProps> = ({
  isOpen,
  onClose,
  asset,
  onOpenFolder,
  onPreview,
  onApplyToProduction,
  onShowToast,
}) => {
  const [copiedMd5, setCopiedMd5] = useState(false);
  const [copiedPath, setCopiedPath] = useState(false);

  if (!isOpen || !asset) return null;

  const records = asset.records || [];

  const handleCopyMd5 = () => {
    navigator.clipboard.writeText(asset.md5);
    setCopiedMd5(true);
    onShowToast('已复制 MD5 指纹');
    setTimeout(() => setCopiedMd5(false), 2000);
  };

  const handleCopyPath = () => {
    navigator.clipboard.writeText(asset.filePath);
    setCopiedPath(true);
    onShowToast('已复制本地源文件路径');
    setTimeout(() => setCopiedPath(false), 2000);
  };

  return (
    <div className="fixed inset-0 z-50 flex justify-end bg-black/40 backdrop-blur-xs animate-in fade-in duration-200">
      {/* Backdrop click */}
      <div className="absolute inset-0" onClick={onClose} />

      {/* Drawer Panel */}
      <div className="relative w-full max-w-2xl bg-white h-full shadow-2xl border-l border-black/[0.08] flex flex-col z-10 animate-in slide-in-from-right duration-200">
        {/* Top Header */}
        <div className="px-6 py-5 border-b border-black/[0.06] bg-slate-50/80 flex items-start justify-between gap-4 shrink-0">
          <div className="space-y-1 min-w-0">
            <div className="flex items-center gap-2 flex-wrap">
              <span className="px-2 py-0.5 rounded-md bg-[#1A1D2E] text-[#DDFD00] text-[11px] font-bold">
                爆款源素材资产
              </span>
              <span className="px-2 py-0.5 rounded-md bg-indigo-50 text-indigo-700 text-[11px] font-bold border border-indigo-200/60">
                爆款 {asset.viralCount || records.length} 次
              </span>
              {asset.sourceTheaterName && (
                <span className="px-2 py-0.5 rounded-md bg-slate-100 text-slate-600 text-[11px] font-medium">
                  {asset.sourceTheaterName}
                </span>
              )}
            </div>
            <h3 className="font-bold text-sm sm:text-base text-[#1A1D2E] truncate" title={asset.materialName}>
              {asset.materialName}
            </h3>
            <p className="text-xs text-[#64748B]">
              原始来源剧集：<span className="font-semibold text-[#1A1D2E]">《{asset.sourceDramaName}》</span>
            </p>
          </div>

          <button
            onClick={onClose}
            className="p-1.5 rounded-xl text-slate-400 hover:text-slate-700 hover:bg-black/5 transition-colors cursor-pointer shrink-0"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Scrollable Content */}
        <div className="flex-1 overflow-y-auto p-6 space-y-6 text-xs">
          {/* 1. Source Video Overview & Technical Specs */}
          <div className="p-4 rounded-2xl bg-slate-50 border border-black/[0.06] space-y-3">
            <div className="flex items-center justify-between">
              <span className="font-bold text-xs text-[#1A1D2E] flex items-center gap-1.5">
                <FileVideo className="w-4 h-4 text-slate-600" />
                物理源文件档案 (系统仅存1份)
              </span>
              <div className="flex items-center gap-2">
                <button
                  type="button"
                  onClick={() => onPreview(asset)}
                  className="flex items-center gap-1 px-2.5 py-1 rounded-lg bg-white border border-black/[0.08] hover:bg-slate-100 text-slate-700 font-semibold text-[11px] cursor-pointer shadow-2xs"
                >
                  <Play className="w-3 h-3 text-[#1A1D2E]" />
                  <span>预览素材</span>
                </button>
                <button
                  type="button"
                  onClick={() => onOpenFolder(asset.filePath)}
                  className="p-1 rounded-lg bg-white border border-black/[0.08] hover:bg-slate-100 text-slate-700 cursor-pointer shadow-2xs"
                  title="在资源管理器中打开"
                >
                  <FolderOpen className="w-3.5 h-3.5" />
                </button>
              </div>
            </div>

            <div className="grid grid-cols-2 sm:grid-cols-4 gap-2.5 text-[11px]">
              <div className="p-2 bg-white rounded-xl border border-black/[0.04]">
                <span className="text-slate-400 block text-[10px]">首次爆款时间</span>
                <span className="font-semibold text-slate-800 font-mono">{asset.firstViralDate}</span>
              </div>
              <div className="p-2 bg-white rounded-xl border border-black/[0.04]">
                <span className="text-slate-400 block text-[10px]">最近一次爆款</span>
                <span className="font-semibold text-slate-800 font-mono">{asset.latestViralDate}</span>
              </div>
              <div className="p-2 bg-white rounded-xl border border-black/[0.04]">
                <span className="text-slate-400 block text-[10px]">视频时长</span>
                <span className="font-semibold text-slate-800 font-mono">{asset.durationSeconds}s</span>
              </div>
              <div className="p-2 bg-white rounded-xl border border-black/[0.04]">
                <span className="text-slate-400 block text-[10px]">文件大小</span>
                <span className="font-semibold text-slate-800 font-mono">{asset.fileSizeMb} MB</span>
              </div>
            </div>

            {/* Path & MD5 */}
            <div className="space-y-1.5 pt-1 text-[11px]">
              <div className="flex items-center justify-between p-2 rounded-xl bg-white border border-black/[0.04]">
                <div className="flex items-center gap-1.5 min-w-0 text-slate-600">
                  <span className="text-slate-400 shrink-0">文件路径:</span>
                  <span className="truncate font-mono text-[10px]" title={asset.filePath}>
                    {asset.filePath}
                  </span>
                </div>
                <button
                  type="button"
                  onClick={handleCopyPath}
                  className="shrink-0 flex items-center gap-1 text-[10px] text-slate-500 hover:text-slate-900 font-medium ml-2 cursor-pointer"
                >
                  {copiedPath ? <Check className="w-3 h-3 text-emerald-600" /> : <Copy className="w-3 h-3" />}
                  <span>{copiedPath ? '已复制' : '复制'}</span>
                </button>
              </div>

              <div className="flex items-center justify-between p-2 rounded-xl bg-white border border-black/[0.04]">
                <div className="flex items-center gap-1.5 min-w-0 text-slate-600">
                  <span className="text-slate-400 shrink-0">去重指纹 MD5:</span>
                  <span className="truncate font-mono text-[10px]" title={asset.md5}>
                    {asset.md5}
                  </span>
                </div>
                <button
                  type="button"
                  onClick={handleCopyMd5}
                  className="shrink-0 flex items-center gap-1 text-[10px] text-slate-500 hover:text-slate-900 font-medium ml-2 cursor-pointer"
                >
                  {copiedMd5 ? <Check className="w-3 h-3 text-emerald-600" /> : <Copy className="w-3 h-3" />}
                  <span>{copiedMd5 ? '已复制' : '复制'}</span>
                </button>
              </div>
            </div>
          </div>

          {/* 2. Aggregate Performance Summary */}
          <div className="space-y-2">
            <span className="font-bold text-xs text-[#1A1D2E] block">
              已知数据累计汇总
            </span>
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
              <div className="p-3.5 rounded-2xl bg-slate-50 border border-black/[0.05]">
                <span className="text-[10px] text-[#64748B] block font-medium">累计视频播放</span>
                <div className="text-base font-black text-[#1A1D2E] font-mono mt-0.5">
                  {asset.totalVideoPlaysText || (asset.totalVideoPlays ? `${(asset.totalVideoPlays / 10000).toFixed(1)}万` : '—')}
                </div>
                <span className="text-[10px] text-slate-400 block mt-0.5">汇总各记录播放</span>
              </div>

              <div className="p-3.5 rounded-2xl bg-slate-50 border border-black/[0.05]">
                <span className="text-[10px] text-[#64748B] block font-medium">累计剧集播放</span>
                <div className="text-base font-black text-[#1A1D2E] font-mono mt-0.5">
                  {asset.hasDramaPlayData && asset.totalDramaPlaysText
                    ? asset.totalDramaPlaysText
                    : '—'}
                </div>
                <span className="text-[10px] text-slate-400 block mt-0.5">
                  {asset.isPartialDramaPlays ? '已有数据累计 (部分记录)' : asset.hasDramaPlayData ? '平台完整数据' : '无剧集播放数据'}
                </span>
              </div>

              {asset.hasRevenueData && asset.totalRevenue ? (
                <div className="p-3.5 rounded-2xl bg-emerald-50/80 border border-emerald-200">
                  <span className="text-[10px] text-emerald-800 block font-medium">已记录累计收益</span>
                  <div className="text-base font-black text-emerald-900 font-mono mt-0.5">
                    ¥{asset.totalRevenue.toLocaleString()}
                  </div>
                  <span className="text-[10px] text-emerald-700 block mt-0.5">真实视频级收益</span>
                </div>
              ) : (
                <div className="p-3.5 rounded-2xl bg-slate-50 border border-black/[0.05]">
                  <span className="text-[10px] text-[#64748B] block font-medium">收益数据</span>
                  <div className="text-sm font-semibold text-slate-400 font-mono mt-0.5">
                    未记录
                  </div>
                  <span className="text-[10px] text-slate-400 block mt-0.5">平台无视频级收益接口</span>
                </div>
              )}
            </div>
          </div>

          {/* 3. Chronological Records Timeline */}
          <div className="space-y-3">
            <div className="flex items-center justify-between">
              <span className="font-bold text-xs text-[#1A1D2E] flex items-center gap-1.5">
                <Layers className="w-4 h-4 text-slate-600" />
                爆款投放实战记录 ({records.length} 次)
              </span>
              <span className="text-[11px] text-slate-400">按发布时间倒序排列</span>
            </div>

            <div className="space-y-3">
              {records.map((rec, index) => {
                const isCrossDrama = rec.dramaName !== asset.sourceDramaName;
                const isQingning = rec.dataSource.includes('青柠');

                return (
                  <div
                    key={rec.id || index}
                    className="p-4 rounded-2xl bg-white border border-black/[0.08] shadow-xs space-y-3 relative hover:border-black/20 transition-all"
                  >
                    {/* Record Header */}
                    <div className="flex items-start justify-between gap-3">
                      <div className="space-y-1">
                        <div className="flex items-center gap-2 flex-wrap">
                          <span className="px-2 py-0.5 rounded-md bg-slate-900 text-white font-mono text-[10px] font-bold">
                            记录 #{records.length - index}
                          </span>
                          <span className="font-semibold text-xs text-[#1A1D2E]">
                            {rec.accountName}
                          </span>
                          <span className="text-slate-400 text-xs">·</span>
                          <span className="font-bold text-xs text-[#1A1D2E]">
                            《{rec.dramaName}》
                          </span>
                          {isCrossDrama && (
                            <span className="px-1.5 py-0.2 rounded bg-purple-100 text-purple-800 text-[10px] font-bold border border-purple-200">
                              跨剧复用
                            </span>
                          )}
                        </div>

                        <div className="flex items-center gap-2 text-[11px] text-slate-500 font-mono">
                          <span>{rec.date || rec.viralDate}</span>
                          {rec.publishTime && <span>{rec.publishTime} 发布</span>}
                          {rec.publishInfo && !rec.publishTime && <span>{rec.publishInfo}</span>}
                        </div>
                      </div>

                      {/* Data Source Badge */}
                      <span
                        className={`px-2 py-0.5 rounded-lg text-[10px] font-bold shrink-0 border ${
                          isQingning
                            ? 'bg-teal-50 text-teal-800 border-teal-200'
                            : 'bg-slate-100 text-slate-600 border-slate-200'
                        }`}
                      >
                        {rec.dataSource}
                      </span>
                    </div>

                    {/* Record Data Metrics */}
                    <div className="p-3 rounded-xl bg-slate-50 border border-black/[0.03] grid grid-cols-2 sm:grid-cols-3 gap-3 text-xs">
                      <div>
                        <span className="text-[10px] text-slate-400 block font-medium">视频播放</span>
                        <span className="font-mono font-bold text-[#1A1D2E] text-xs">
                          {rec.videoPlayCountText || rec.playCountText || (rec.videoPlayCount ? `${(rec.videoPlayCount / 10000).toFixed(1)}万` : '—')}
                        </span>
                      </div>

                      {rec.dramaPlayCount ? (
                        <div>
                          <span className="text-[10px] text-slate-400 block font-medium">剧集播放</span>
                          <span className="font-mono font-bold text-[#1A1D2E] text-xs">
                            {rec.dramaPlayCountText || `${(rec.dramaPlayCount / 10000).toFixed(1)}万`}
                          </span>
                        </div>
                      ) : (
                        <div>
                          <span className="text-[10px] text-slate-400 block font-medium">剧集播放</span>
                          <span className="text-slate-400 font-mono text-xs">—</span>
                        </div>
                      )}

                      {rec.revenue ? (
                        <div>
                          <span className="text-[10px] text-emerald-700 block font-medium">带来收益</span>
                          <span className="font-mono font-black text-emerald-800 text-xs">
                            ¥{rec.revenue.toLocaleString()}
                          </span>
                        </div>
                      ) : null}
                    </div>

                    {/* Operational Notes */}
                    {rec.notes && (
                      <div className="p-2.5 rounded-xl bg-amber-50/60 border border-amber-200/50 text-[11px] text-amber-900 leading-relaxed">
                        <span className="font-bold text-amber-950">运营亮点：</span>
                        {rec.notes}
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          </div>
        </div>

        {/* Bottom Actions Bar */}
        <div className="px-6 py-4 border-t border-black/[0.06] bg-slate-50/80 flex items-center justify-between gap-3 shrink-0">
          <button
            type="button"
            onClick={handleCopyPath}
            className="flex items-center gap-1.5 px-3 py-2 rounded-xl text-xs font-semibold text-slate-600 hover:bg-slate-200/70 cursor-pointer"
          >
            {copiedPath ? <Check className="w-3.5 h-3.5 text-emerald-600" /> : <Copy className="w-3.5 h-3.5" />}
            <span>{copiedPath ? '已复制源文件路径' : '复制源文件路径'}</span>
          </button>

          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={onClose}
              className="px-4 py-2 rounded-xl text-xs font-semibold text-slate-600 hover:bg-slate-200/70 cursor-pointer"
            >
              关闭
            </button>
            <button
              type="button"
              onClick={() => {
                if (onApplyToProduction) {
                  onApplyToProduction(asset);
                } else {
                  onShowToast(`已将源素材「${asset.materialName}」加入当前生产管线候选池`);
                }
              }}
              className="flex items-center gap-1.5 px-4 py-2 rounded-xl bg-[#1A1D2E] text-[#DDFD00] hover:bg-black/90 active:scale-[0.98] text-xs font-bold shadow-xs transition-all cursor-pointer"
            >
              <Send className="w-3.5 h-3.5" />
              <span>用于生产 / 加入生产候选</span>
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};
