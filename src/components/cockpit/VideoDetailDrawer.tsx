import { formatWorkMetric } from '../../services/optimizationHealth';
import { CockpitModal } from './CockpitModal';
import { VideoTrafficRules, VideoTrafficTags } from './VideoTrafficTags';
import { getOptimizationAppearance, optimizationAnalysisBody } from '../../types/optimizationNotices';
import React, { useState } from 'react';
import { WorkVideoCover } from './WorkVideoCover';
import { AccountAvatar } from '../AccountAvatar';
import { VideoTrafficItem, OptimizationStatus } from '../../types/shortDramaOps';
import { 
  X, 
  Film, 
  Play, 
  Heart, 
  MessageSquare, 
  Share2, 
  ThumbsUp, 
  AlertTriangle, 
  CheckCircle2, 
  Clock, 
  Tv, 
  ShieldAlert, 
  Sparkles,
  ArrowRight
} from 'lucide-react';

interface VideoDetailDrawerProps {
  video: VideoTrafficItem | null;
  onClose: () => void;
  onUpdateOptimizationStatus?: (videoId: string, status: OptimizationStatus) => void;
  showToast?: (msg: string) => void;
}

export const VideoDetailDrawer: React.FC<VideoDetailDrawerProps> = ({
  video,
  onClose,
  onUpdateOptimizationStatus,
  showToast,
}) => {
  const [currentStatus, setCurrentStatus] = useState<OptimizationStatus>(
    video?.optimization?.status || '待处置'
  );
  if (!video) return null;

  const totalInteractions = video.hearts + video.comments + video.shares + video.thumbsUp;
  const interactionRate = video.views > 0 
    ? ((totalInteractions / video.views) * 100).toFixed(2) 
    : Number.isFinite(video.views) ? '0.00' : '—';

  const handleStatusChange = (newStatus: OptimizationStatus) => {
    setCurrentStatus(newStatus);
    if (onUpdateOptimizationStatus) {
      onUpdateOptimizationStatus(video.id, newStatus);
    }
    if (showToast) {
      showToast(`优化处置状态已更新为「${newStatus}」`);
    }
  };

  return (
    <CockpitModal label="作品详情" onClose={onClose} width="max-w-4xl">
        
        {/* Header */}
        <div className="px-6 py-5 border-b border-slate-100 flex items-center justify-between bg-slate-50/80">
          <div className="flex items-center gap-3">
            <WorkVideoCover key={`${video.accountId}:${video.id}`} video={video} size="sm" />
            <div>
              <div className="flex items-center gap-2">
                {/* 必须为 剧名-n */}
                <h3 className="text-base font-extrabold text-[#1E1644] font-mono">
                  {video.fileName}
                </h3>
                <span className="text-xs px-2 py-0.5 rounded bg-indigo-50 text-indigo-700 font-bold border border-indigo-200">
                  第 {video.episodeNumber} 集
                </span>
              </div>
              <p className="text-xs text-slate-500 mt-1 flex items-center gap-2">
                <span>剧集：《{video.dramaTitle}》</span>
                <span>·</span>
                <span>剧场：{video.theater}</span>
                <span>·</span>
                <span>发布账号：{video.accountName}</span>
              </p>
            </div>
          </div>

          <button
            aria-label="关闭作品详情"
            onClick={onClose}
            className="w-8 h-8 rounded-lg hover:bg-slate-200/70 text-slate-400 hover:text-slate-700 flex items-center justify-center transition-colors"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Content Body */}
        <div className="min-h-0 flex-1 overflow-y-auto p-6 space-y-6">
          
          {/* 1. 发布时间与账号属性卡片 */}
          <div className="p-4 rounded-2xl bg-slate-50 border border-slate-100 grid grid-cols-2 gap-4 text-xs">
            <div>
              <span className="text-slate-400 text-[11px] block">精确发布时间 (时分)</span>
              <span className="font-extrabold text-slate-800 text-sm font-mono mt-0.5 flex items-center gap-1.5">
                <Clock className="w-3.5 h-3.5 text-indigo-500" />
                {video.publishTime}
              </span>
            </div>
            <div>
              <span className="text-slate-400 text-[11px] block">所属账号与剧场</span>
              <span className="font-bold text-slate-800 text-xs mt-0.5 flex items-center gap-1.5">
                <AccountAvatar name={video.accountName} url={video.avatarUrl} className="w-6 h-6" />
                {video.accountName} ({video.theater})
              </span>
            </div>
          </div>

          {/* 2. 核心视频流量指标卡片 */}
          <div className="space-y-3">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <h4 className="text-xs font-extrabold text-[#1E1644] uppercase tracking-wider">视频流量与完播数据</h4>
              <VideoTrafficTags video={video} size="md"/>
            </div>
            
            <div className="grid grid-cols-3 gap-3">
              <div className="p-3.5 rounded-xl border border-slate-100 bg-white shadow-xs">
                <span className="text-[11px] text-slate-400 block">总播放量</span>
                <span className="text-xl font-extrabold text-indigo-600 font-mono tabular-nums mt-1 block">
                  {!Number.isFinite(video.views) ? '—' : video.views >= 10000 ? `${(video.views / 10000).toFixed(1)}w` : formatWorkMetric(video.views)}
                </span>
                <span className="text-[10px] text-slate-400 mt-1 block font-mono">
                  精确: {formatWorkMetric(video.views)} 次
                </span>
              </div>

              <div className="p-3.5 rounded-xl border border-slate-100 bg-white shadow-xs">
                <span className="text-[11px] text-slate-400 block">完播率</span>
                <span className={`text-xl font-extrabold font-mono tabular-nums mt-1 block ${
                  video.completionRate >= 25 ? 'text-emerald-600' :
                  video.completionRate < 10 ? 'text-rose-600' : 'text-slate-800'
                }`}>
                  {Number.isFinite(video.completionRate) ? `${video.completionRate}%` : '—'}
                </span>
                <span className="text-[10px] text-slate-400 mt-1 block">
                  完播率仅作参考，不作为爆款判定依据
                </span>
              </div>

              <div className="p-3.5 rounded-xl border border-slate-100 bg-white shadow-xs">
                <span className="text-[11px] text-slate-400 block">综合互动率</span>
                <span className="text-xl font-extrabold text-slate-800 font-mono tabular-nums mt-1 block">
                  {interactionRate === '—' ? interactionRate : `${interactionRate}%`}
                </span>
                <span className="text-[10px] text-slate-400 mt-1 block font-mono">
                  总量: {formatWorkMetric(totalInteractions)}
                </span>
              </div>
            </div>

            <VideoTrafficRules video={video}/>

            {/* 4类互动细分 */}
            <div className="grid grid-cols-4 gap-2 pt-2 text-xs font-mono tabular-nums">
              <div className="p-2.5 rounded-lg bg-slate-50 border border-slate-100 flex items-center justify-between">
                <span className="text-slate-500 flex items-center gap-1 text-[11px]">
                  <Heart className="w-3.5 h-3.5 text-rose-500" /> 爱心
                </span>
                <span className="font-bold text-slate-800">{formatWorkMetric(video.hearts)}</span>
              </div>

              <div className="p-2.5 rounded-lg bg-slate-50 border border-slate-100 flex items-center justify-between">
                <span className="text-slate-500 flex items-center gap-1 text-[11px]">
                  <MessageSquare className="w-3.5 h-3.5 text-blue-500" /> 评论
                </span>
                <span className="font-bold text-slate-800">{formatWorkMetric(video.comments)}</span>
              </div>

              <div className="p-2.5 rounded-lg bg-slate-50 border border-slate-100 flex items-center justify-between">
                <span className="text-slate-500 flex items-center gap-1 text-[11px]">
                  <Share2 className="w-3.5 h-3.5 text-indigo-500" /> 转发
                </span>
                <span className="font-bold text-slate-800">{formatWorkMetric(video.shares)}</span>
              </div>

              <div className="p-2.5 rounded-lg bg-slate-50 border border-slate-100 flex items-center justify-between">
                <span className="text-slate-500 flex items-center gap-1 text-[11px]">
                  <ThumbsUp className="w-3.5 h-3.5 text-emerald-500" /> 点赞
                </span>
                <span className="font-bold text-slate-800">{formatWorkMetric(video.thumbsUp)}</span>
              </div>
            </div>
          </div>

          {/* 3. 作品优化分析模块 (核心业务：持续优化排查) */}
          <div className="space-y-3 pt-2">
            <h4 className="text-xs font-extrabold text-[#1E1644] uppercase tracking-wider flex items-center justify-between">
              <span>作品优化分析 (持续跟踪)</span>
              {video.hasOptimization ? (
                <span className="text-rose-600 text-[11px] font-bold flex items-center gap-1 font-sans">
                  <AlertTriangle className="w-3.5 h-3.5" /> 存在优化诊断
                </span>
              ) : (
                <span className="text-emerald-600 text-[11px] font-bold flex items-center gap-1 font-sans">
                  <CheckCircle2 className="w-3.5 h-3.5" /> 暂无优化记录
                </span>
              )}
            </h4>

            {video.hasOptimization && video.optimization ? (
              <div className="p-4 rounded-2xl border border-rose-200 bg-rose-50/40 space-y-3">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <span className={`px-2.5 py-1 rounded-md border text-xs font-extrabold ${getOptimizationAppearance(video.optimization.simplifiedReason).pill}`}>
                      优化原因：{video.optimization.simplifiedReason || video.optimization.reasonType}
                    </span>
                    {video.optimization.severity !== '未判定' && <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-white text-rose-600 border border-rose-200">
                      等级：{video.optimization.severity}
                    </span>}
                  </div>
                  <span className="text-[11px] text-slate-500 font-mono">
                    平台通知: {video.optimization.publishTime.slice(0, 10)}
                  </span>
                </div>

                {/* 平台真实官方固定文案 */}
                <div className="p-3.5 bg-white rounded-xl border border-rose-200 text-xs leading-relaxed text-slate-700 shadow-xs">
                  <span className="font-bold text-rose-900 block mb-1.5 flex items-center gap-1.5">
                    <AlertTriangle className="w-3.5 h-3.5 text-rose-600" />
                    作品分析原文：
                  </span>
                  <p className="whitespace-pre-wrap break-words text-slate-800 leading-relaxed font-normal bg-rose-50/30 p-2.5 rounded-lg border border-rose-100">
                    {video.optimization.officialNotice?.trim() ? optimizationAnalysisBody(video.optimization.officialNotice) : '暂无作品分析原文'}
                  </p>
                </div>

                {/* 平台处置措施 */}
                {video.optimization.impactNotice && <div className="p-3 bg-amber-50/80 rounded-xl border border-amber-200/80 text-xs leading-relaxed text-slate-700 shadow-xs">
                  <span className="font-bold text-amber-900 block mb-1">平台记录状态：</span>
                  <p className="text-slate-700">
                    {video.optimization.impactNotice}
                  </p>
                </div>}
              </div>
            ) : (
              <div className="p-4 rounded-2xl border border-emerald-100 bg-emerald-50/30 text-xs text-slate-600 space-y-1">
                <div className="font-bold text-emerald-800 flex items-center gap-1.5">
                  <CheckCircle2 className="w-4 h-4 text-emerald-600" />
                  当前视频暂无优化记录
                </div>
                <p className="text-slate-500">
                  尚未取得该作品的优化分析记录。
                </p>
              </div>
            )}
          </div>
        </div>

        {/* Footer */}
        <div className="p-4 border-t border-slate-100 bg-slate-50 flex items-center justify-between text-xs text-slate-500">
          <span>{video.fileName} · 账号：{video.accountName}</span>
          <button
            onClick={onClose}
            className="px-4 py-1.5 rounded-lg bg-slate-900 text-white font-semibold hover:bg-slate-800 transition-colors"
          >
            完成
          </button>
        </div>
    </CockpitModal>
  );
};
