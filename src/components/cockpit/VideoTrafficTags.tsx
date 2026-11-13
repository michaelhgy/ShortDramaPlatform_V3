import { getOptimizationAppearance } from '../../types/optimizationNotices';
import { useEffect, useState } from 'react';
import { AlertTriangle, ArrowDownRight, Crown, Eye, Flame, PlayCircle, RefreshCw, Clock, Sparkles, TrendingUp, Zap } from 'lucide-react';
import type { VideoTrafficItem } from '../../types/shortDramaOps';
import { rateVideoTraffic, VIDEO_TRAFFIC_RULES, type VideoTrafficStatus } from '../../services/videoTrafficRating';
import { formatRevenueQueryTime } from '../../services/accountRevenueRating';
import { StatusBadgePopover, StatusBadgeRulesDialog } from './StatusBadgePopover';

// Only the archive's visual language is adopted; V3's date/data rules remain authoritative.
const visuals = {
  大爆: { icon: Crown, iconColor: 'text-amber-200 fill-amber-300', tag: 'bg-gradient-to-r from-purple-600 via-fuchsia-600 to-rose-600 text-white font-black shadow-xs shadow-purple-500/20', pill: 'bg-purple-50/90 hover:bg-purple-100/90 border-purple-200/90 text-purple-950', dot: 'bg-emerald-500 ring-2 ring-emerald-200/60', advice: '重点复盘有效片段，评估同剧后续作品的表现。' },
  爆款: { icon: Flame, iconColor: 'text-amber-100 fill-amber-300', tag: 'bg-gradient-to-r from-amber-500 to-orange-500 text-white font-black shadow-xs shadow-orange-500/20', pill: 'bg-amber-50/90 hover:bg-amber-100/90 border-amber-200/90 text-amber-950', dot: 'bg-emerald-500 ring-2 ring-emerald-200/60', advice: '关注收益转化，并参考同剧其他作品判断延续性。' },
  小爆: { icon: Zap, iconColor: 'text-indigo-100 fill-indigo-200', tag: 'bg-gradient-to-r from-indigo-500 to-violet-600 text-white font-bold shadow-xs shadow-indigo-500/20', pill: 'bg-indigo-50/90 hover:bg-indigo-100/90 border-indigo-200/90 text-indigo-950', dot: 'bg-emerald-500 ring-2 ring-emerald-200/60', advice: '继续观察增长，结合收益和互动判断后续投入。' },
  常规: { icon: PlayCircle, iconColor: 'text-emerald-100', tag: 'bg-emerald-600 text-white font-bold shadow-xs', pill: 'bg-emerald-50/90 hover:bg-emerald-100/90 border-emerald-200/90 text-emerald-950', dot: 'bg-emerald-500 ring-2 ring-emerald-200/60', advice: '保持观察，结合收益和完播率复盘内容。' },
  观察中: { icon: Eye, iconColor: 'text-sky-100', tag: 'bg-gradient-to-r from-sky-500 to-cyan-600 text-white font-bold shadow-xs', pill: 'bg-sky-50/90 hover:bg-sky-100/90 border-sky-200/90 text-sky-950', dot: 'bg-amber-500 ring-2 ring-amber-200/60', advice: '发布不足12小时，等待更多有效数据。' },
  待起量: { icon: TrendingUp, iconColor: 'text-blue-100', tag: 'bg-gradient-to-r from-blue-500 to-indigo-500 text-white font-bold shadow-xs', pill: 'bg-blue-50/90 hover:bg-blue-100/90 border-blue-200/90 text-blue-950', dot: 'bg-amber-500 ring-2 ring-amber-200/60', advice: '发布已满12小时、不足24小时，继续观察。' },
  低播: { icon: ArrowDownRight, iconColor: 'text-slate-200', tag: 'bg-slate-500 text-white font-semibold shadow-xs', pill: 'bg-slate-100 hover:bg-slate-200/80 border-slate-200 text-slate-800', dot: 'bg-slate-400 ring-slate-200/60', advice: '复盘选段与封面；低播本身不代表平台限流。' },
  待采集: { icon: RefreshCw, iconColor: 'text-amber-200', tag: 'bg-stone-500 text-white font-semibold shadow-xs', pill: 'bg-stone-50 hover:bg-stone-100 border-stone-200 text-stone-800', dot: 'bg-amber-500 ring-2 ring-amber-200/60', advice: '等待有效采集，缺失或失败不作为零播放。' },
} satisfies Record<VideoTrafficStatus, unknown>;

type BadgeSize = 'sm' | 'md' | 'lg';
const sizes = {
  sm: { pill: 'text-[10px] pl-1 pr-1.5 py-0.5 gap-1 rounded-md leading-[1.5]', tag: 'px-1 py-[0.8px] rounded text-[10px]', dot: 'h-1.5 w-1.5' },
  md: { pill: 'text-xs pl-1.5 pr-2 py-0.5 gap-1.5 rounded-lg leading-[1.333333]', tag: 'px-1.5 py-0.5 rounded-md text-xs', dot: 'h-2 w-2' },
  lg: { pill: 'text-sm pl-2 pr-2.5 py-1 gap-2 rounded-xl leading-[1.428571]', tag: 'px-2 py-0.5 rounded-lg text-sm', dot: 'h-2.5 w-2.5' },
};

/** The same colored mark is used by work badges and the flat toolbar filter. */
export function VideoTrafficStatusMark({ status, size = 'sm' }: { status: VideoTrafficStatus; size?: BadgeSize }) {
  const visual = visuals[status], Icon = visual.icon;
  return <span data-video-status-mark={status} className={`inline-flex flex-none items-center gap-1 tracking-tight ${visual.tag} ${sizes[size].tag}`}>
    <Icon aria-hidden="true" className={`h-3.5 w-3.5 flex-none ${visual.iconColor}`} /><span>{status}</span>
  </span>;
}
const thresholds: Record<VideoTrafficStatus, string> = { 大爆: '累计播放 ≥ 100,000 次', 爆款: '50,000 ≤ 播放 < 100,000 次', 小爆: '30,000 ≤ 播放 < 50,000 次', 常规: '1,000 ≤ 播放 < 30,000 次', 观察中: '累计播放 < 1,000 次', 待起量: '累计播放 < 1,000 次', 低播: '累计播放仍 < 1,000 次', 待采集: '暂无有效回传数据' };
const windows: Record<VideoTrafficStatus, string> = { 大爆: '全周期考核', 爆款: '全周期考核', 小爆: '全周期考核', 常规: '全周期考核', 观察中: '发布不足12小时', 待起量: '发布满12小时、不足24小时', 低播: '满24小时后有效采集', 待采集: '等待有效采集回传' };
function elapsedHours(video: VideoTrafficItem): number | null {
  const value = video.publishTime;
  const published = Date.parse(/([zZ]|[+-]\d{2}:?\d{2})$/.test(value) ? value : value.replace(' ', 'T') + '+08:00');
  return Number.isFinite(published) && published <= Date.now() ? Math.round(((Date.now() - published) / 3600000) * 10) / 10 : null;
}
function metric(video: VideoTrafficItem, status: VideoTrafficStatus): string {
  if (status === '待采集') return '待回传';
  if (['观察中', '待起量', '低播'].includes(status)) {
    const hours = elapsedHours(video);
    if (hours !== null) return `${hours}h${status === '低播' ? '+' : ''}`;
  }
  return video.views >= 10000 ? `${(video.views / 10000).toFixed(1)}w` : video.views >= 1000 ? `${(video.views / 1000).toFixed(1)}k` : video.views.toLocaleString();
}

export function VideoTrafficBadge({ video, size = 'sm' }: { video: VideoTrafficItem; size?: BadgeSize }) {
  const [revision, tick] = useState(0), [rulesOpen, setRulesOpen] = useState(false);
  const rating = rateVideoTraffic(video), visual = visuals[rating.status], Icon = visual.icon, sz = sizes[size];
  const failed = video.statsState === 'failed', hours = elapsedHours(video);
  useEffect(() => {
    if (!rating.nextEvaluationAt) return;
    const clock = setTimeout(() => tick(n => n + 1), Math.max(1000, rating.nextEvaluationAt - Date.now() + 50));
    return () => clearTimeout(clock);
  }, [rating.nextEvaluationAt, revision]);
  const dot = failed ? 'bg-rose-500 ring-2 ring-rose-200/60' : visual.dot;
  return <>
    <StatusBadgePopover kind="video" status={rating.status} label={`视频流量：${rating.status}`}
      className={`${sz.pill} ${visual.pill}`} onRules={() => setRulesOpen(true)}
      badge={<>
        <VideoTrafficStatusMark status={rating.status} size={size} />
        <span className="inline-flex flex-none items-center gap-1"><span aria-hidden="true" className={`flex-none rounded-full ${dot} ${sz.dot}`} /><span className="flex-none font-mono text-[11px] font-bold tabular-nums opacity-90">{metric(video, rating.status)}</span></span>
      </>}
      heading={<div className="flex min-w-0 flex-wrap items-center gap-2"><span className={`inline-flex flex-none items-center gap-1 rounded-lg px-2 py-0.5 text-xs font-bold ${visual.tag}`}><Icon className={`h-3.5 w-3.5 flex-none ${visual.iconColor}`} />{rating.status}</span><span className="font-mono text-xs font-bold text-slate-900">{thresholds[rating.status]}</span></div>}>
      {video.fileName && <div className="mt-2.5 flex items-center justify-between gap-1 rounded-lg border border-slate-200/70 bg-slate-50 px-2.5 py-1.5 text-xs"><span className="truncate font-mono font-bold text-slate-900">{video.fileName}</span>{video.dramaTitle && <span className="max-w-[45%] flex-none truncate text-[11px] text-slate-500">《{video.dramaTitle}》</span>}</div>}
      <div className="mt-2.5 space-y-2 text-xs">
        <div className="flex items-center justify-between gap-2 rounded-lg bg-slate-50/70 px-2 py-1"><span className="text-[11px] text-slate-500">累计播放量</span><span className="font-mono font-bold text-slate-900">{Number.isFinite(video.views) && video.views >= 0 ? `${video.views.toLocaleString()} 次` : '无有效回传'}</span></div>
        <div className="flex items-center justify-between gap-2 rounded-lg bg-slate-50/70 px-2 py-1"><span className="flex-none text-[11px] text-slate-500">已发布时长</span><span className="flex flex-wrap items-center justify-end gap-1 font-mono font-bold text-slate-900"><Clock className="h-3 w-3 flex-none text-indigo-500" /><span>{hours === null ? '未知' : `${hours} 小时`}</span>{hours !== null && <span className={`rounded px-1 py-[0.8px] font-sans text-[10px] ${hours < 24 ? 'bg-sky-100 text-sky-700' : 'bg-slate-200 text-slate-700'}`}>{hours < 12 ? '不足12h' : hours < 24 ? '12—24h' : '满24h'}</span>}</span></div>
        <div className="flex items-start justify-between gap-2 rounded-lg bg-slate-50/70 px-2 py-1"><span className="flex-none text-[11px] text-slate-500">数据采集状态</span><span className="inline-flex max-w-[70%] items-start gap-1.5 text-right font-medium text-slate-800"><span className={`mt-1 h-2 w-2 flex-none rounded-full ${dot}`} /><span>{failed ? '本次采集失败，等待有效回传' : rating.reason}</span></span></div>
        <div className="space-y-1 rounded-xl border border-indigo-100/80 bg-indigo-50/60 p-2.5 text-[11px]"><div className="flex items-center gap-1 font-bold text-indigo-900"><Sparkles className="h-3.5 w-3.5 flex-none text-indigo-600" />运营策略指引:</div><p className="font-normal leading-relaxed text-indigo-800/90">{visual.advice}</p></div>
      </div>
    </StatusBadgePopover>
    {rulesOpen && <StatusBadgeRulesDialog kind="video" title="视频标签规则" onClose={() => setRulesOpen(false)}>
      <div className="flex items-center gap-2 rounded-2xl border border-indigo-100 bg-indigo-50/60 p-3 text-xs text-indigo-900"><Sparkles className="h-4 w-4 flex-none text-indigo-600" /><span><strong>业务判定逻辑：</strong>无有效采集为待采集；不足1000播放时，12小时内观察、12—24小时待起量，满24小时后须有有效采集才判低播。其余按1千/3万/5万/10万分级。</span></div>
      <div className="divide-y divide-slate-100 overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-2xs">{(['大爆', '爆款', '小爆', '常规', '观察中', '待起量', '低播', '待采集'] as const).map(status => {
        const theme = visuals[status], RuleIcon = theme.icon, rule = VIDEO_TRAFFIC_RULES.find(item => item.status === status)!;
        return <div key={status} className={`flex flex-col justify-between gap-3 p-4 transition-colors hover:bg-slate-50/70 sm:flex-row sm:items-center ${status === rating.status ? 'bg-indigo-50/30 ring-1 ring-inset ring-indigo-200' : ''}`}><div className="flex min-w-0 items-start gap-3 sm:min-w-[210px]"><span className={`inline-flex flex-none items-center gap-1.5 rounded-xl px-2.5 py-1 text-xs font-bold ${theme.tag}`}><RuleIcon className={`h-3.5 w-3.5 flex-none ${theme.iconColor}`} />{status}</span><div><div className="font-mono text-xs font-bold text-slate-900">{rule.rule}</div><div className="mt-0.5 flex items-center gap-1.5 text-[11px] text-slate-400"><span className={`h-1.5 w-1.5 flex-none rounded-full ${theme.dot}`} />{windows[status]}</div></div></div><div className="flex-1 space-y-1 text-xs"><div className="font-medium leading-relaxed text-slate-600">{thresholds[status]}</div><div className="text-[11px] font-semibold text-indigo-600">策略：{theme.advice}</div></div></div>;
      })}</div>
      <p className="text-[11px] text-slate-400">达到播放门槛立即升级；完播率不决定等级，低播不代表限流。平台优化独立保留。当前采集：{rating.asOf ? formatRevenueQueryTime(rating.asOf) : '时间未知'}。</p>
    </StatusBadgeRulesDialog>}
  </>;
}

export function VideoTrafficTags({ video, size = 'sm', stacked = false }: { video: VideoTrafficItem; size?: BadgeSize; stacked?: boolean }) {
  return <span data-video-tags="true" className={`inline-flex max-w-full flex-none items-center justify-end gap-1.5 align-middle ${stacked ? 'w-max flex-col' : 'flex-wrap'}`}>
    {video.hasOptimization && <span data-video-optimization-tag="true" aria-label={`平台优化：${video.optimization?.simplifiedReason || '待归类'}`}
      className={`inline-flex w-max max-w-full flex-none items-center gap-1 whitespace-nowrap rounded-full border px-2 py-0.5 text-[10px] font-bold leading-[1.5] ${getOptimizationAppearance(video.optimization?.simplifiedReason || '待归类').pill}`}>
      <AlertTriangle aria-hidden="true" className="h-2.5 w-2.5 flex-none" /><span className="truncate">{video.optimization?.simplifiedReason || '待归类'}</span>
    </span>}
    <VideoTrafficBadge video={video} size={size} />
  </span>;
}

export function VideoTrafficRules({video}:{video:VideoTrafficItem}) {
  return <details className="text-[11px] text-slate-500">
    <summary className="w-fit cursor-pointer text-indigo-600">查看视频标签规则</summary>
    <div className="mt-3 grid gap-x-6 gap-y-2 sm:grid-cols-2">{VIDEO_TRAFFIC_RULES.map(item=><div key={item.status} className="flex gap-2 leading-5"><span className="w-12 shrink-0 font-semibold text-slate-700">{item.status}</span><span>{item.rule}</span></div>)}</div>
    <p className="mt-3 leading-5">达到播放门槛立即升级，不受观察期限制；累计表现不会因后续流量减少而降级。完播率只作参考，低播不代表限流，平台优化标记独立保留。</p>
    <p className="mt-1 leading-5">当前数据采集：{video.statsCollectedAt?formatRevenueQueryTime(video.statsCollectedAt):video.statsDate||'未知'}。没有覆盖满24小时的有效采集，不依据旧值判低播。</p>
  </details>;
}
