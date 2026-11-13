import React, { useEffect, useMemo, useState } from 'react';
import { ArrowRight, CircleDollarSign, Eye, Film, Users } from 'lucide-react';
import type { V2RevenuePayload } from '../../adapters/revenue';
import { loadAccountDataOverview, type AccountDataOverview } from '../../api/accountData';
import type { AnalyticsTopTab } from '../../analyticsTypes';
import type { VideoAnalysisResult } from '../../utils/videoEngine';

export const AnalyticsOverview: React.FC<{
  revenue: V2RevenuePayload | null;
  videoAnalysis: VideoAnalysisResult | null;
  revenueError: string;
  onNavigate: (tab: AnalyticsTopTab) => void;
}> = ({ revenue, videoAnalysis, revenueError, onNavigate }) => {
  const [accountData, setAccountData] = useState<AccountDataOverview | null>(null);
  const [accountError, setAccountError] = useState('');

  useEffect(() => {
    let active = true;
    const end = new Date();
    end.setDate(end.getDate() - 1);
    const start = new Date(end);
    start.setDate(start.getDate() - 6);
    const iso = (date: Date) => `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')}`;
    void loadAccountDataOverview(iso(start), iso(end))
      .then((result) => { if (active) setAccountData(result); })
      .catch((error: unknown) => { if (active) setAccountError(error instanceof Error ? error.message : '账号快照读取失败'); });
    return () => { active = false; };
  }, []);

  const accountDaily = useMemo(() => {
    const totals = new Map<string, { views: number; accounts: number }>();
    for (const snapshot of accountData?.snapshots || []) {
      if (snapshot.status !== 'success' || snapshot.data_state !== 'record') continue;
      const dailyRows = (snapshot.payload as { daily?: unknown[] } | null)?.daily;
      const row = dailyRows?.find((item) => item && typeof item === 'object' && (item as { date?: string }).date === snapshot.collection_day) as Record<string, unknown> | undefined;
      if (!row) continue;
      const raw = row.view ?? row.views ?? row.playCount ?? row['播放量'];
      const views = typeof raw === 'number' ? raw : Number(raw) || 0;
      const point = totals.get(snapshot.collection_day) || { views: 0, accounts: 0 };
      point.views += views;
      point.accounts += 1;
      totals.set(snapshot.collection_day, point);
    }
    return [...totals.entries()].sort(([a], [b]) => a.localeCompare(b)).map(([date, value]) => ({ date, ...value }));
  }, [accountData]);

  const topVideo = [...(videoAnalysis?.videos || [])].sort((a, b) => b.periodVideoViews - a.periodVideoViews)[0];
  const revenueSeries = revenue?.trendPoints || [];
  const accountMax = Math.max(...accountDaily.map((item) => item.views), 1);
  const revenueMax = Math.max(...revenueSeries.map((item) => item.totalRevenue), 1);

  return <div className="space-y-6 pb-10">
    <header className="flex flex-wrap items-end justify-between gap-4 border-b border-slate-200 pb-4">
      <div><p className="text-xs font-medium text-teal-700">运营数据工作台</p><h2 className="mt-1 text-2xl font-semibold text-slate-900">数据总览</h2><p className="mt-1 text-sm text-slate-500">不同数据源分开统计，点击区块进入明细分析。</p></div>
      <span className="text-xs text-slate-500">收益与账号流量口径独立</span>
    </header>

    <section aria-label="关键指标" className="grid grid-cols-2 gap-x-6 gap-y-4 border-b border-slate-200 pb-5 lg:grid-cols-4">
      <Kpi icon={<CircleDollarSign className="h-4 w-4" />} label="当前收益范围" value={revenue ? `¥${format(revenue.summary.currentPeriodRevenue)}` : revenueError || '读取中'} detail={revenue?.dataCompleteness.statusText || '剧场站点结算数据'} accent="text-emerald-700" onClick={() => onNavigate('revenue')} />
      <Kpi icon={<Users className="h-4 w-4" />} label="账号每日播放" value={accountDaily.length ? format(accountDaily[accountDaily.length - 1]?.views || 0) : accountError ? '读取失败' : '暂无记录'} detail={accountError || `${accountDaily[accountDaily.length - 1]?.date || '最近日期'} · ${accountDaily[accountDaily.length - 1]?.accounts || 0} 个有记录账号`} accent="text-teal-700" onClick={() => onNavigate('accounts')} />
      <Kpi icon={<Eye className="h-4 w-4" />} label="范围内青柠视频播放" value={revenue ? format(revenueSeries.reduce((sum, item) => sum + (item.videoViews || 0), 0)) : '读取中'} detail="青柠视频明细汇总，不与账号播放相加" accent="text-cyan-700" onClick={() => onNavigate('videos')} />
      <Kpi icon={<Film className="h-4 w-4" />} label="最高播放作品" value={topVideo ? format(topVideo.periodVideoViews) : '暂无作品明细'} detail={topVideo?.dramaName || '当前范围未匹配到视频数据'} accent="text-amber-700" onClick={() => onNavigate('videos')} />
    </section>

    <section className="grid gap-7 xl:grid-cols-2">
      <Trend title="每日收益" description="来自剧场站点的当前筛选范围收益，按现有结算口径统计。" color="bg-emerald-600" points={revenueSeries.map((item) => ({ date: item.date, value: item.totalRevenue, count: undefined }))} max={revenueMax} valueLabel={(value) => `¥${format(value)}`} onClick={() => onNavigate('revenue')} />
      <Trend title="账号每日播放" description="V3 保存的账号统计快照；无每日记录的账号不作为 0 参与合计。" color="bg-teal-600" points={accountDaily.map((item) => ({ date: item.date, value: item.views, count: item.accounts }))} max={accountMax} valueLabel={format} onClick={() => onNavigate('accounts')} />
    </section>

    <section className="grid gap-3 border-t border-slate-200 pt-4 sm:grid-cols-3">
      <SourceButton title="账号流量" detail="播放、粉丝变化与互动，基于已保存快照" icon={<Users className="h-4 w-4" />} onClick={() => onNavigate('accounts')} />
      <SourceButton title="作品表现" detail="剧集与青柠视频明细及排行" icon={<Film className="h-4 w-4" />} onClick={() => onNavigate('videos')} />
      <SourceButton title="剧场收益" detail="剧场独立来源的收益和采集完整度" icon={<CircleDollarSign className="h-4 w-4" />} onClick={() => onNavigate('revenue')} />
    </section>
  </div>;
};

function Trend({ title, description, color, points, max, valueLabel, onClick }: {
  title: string; description: string; color: string;
  points: Array<{ date: string; value: number; count?: number }>;
  max: number; valueLabel: (value: number) => string; onClick: () => void;
}) {
  return <button type="button" onClick={onClick} className="min-w-0 text-left" aria-label={`${title}，打开明细`}>
    <div className="mb-3 flex items-start justify-between gap-3"><div><h3 className="text-sm font-semibold text-slate-900">{title}</h3><p className="mt-1 text-xs text-slate-500">{description}</p></div><ArrowRight className="mt-0.5 h-4 w-4 shrink-0 text-slate-400" /></div>
    {points.length ? <div className="grid h-48 grid-flow-col auto-cols-fr items-end gap-2 border-b border-slate-200 px-1 pb-1">
      {points.map((point) => <div key={point.date} className="flex h-full min-w-0 flex-col items-center justify-end gap-1" title={`${point.date} ${valueLabel(point.value)}${point.count === undefined ? '' : `，${point.count} 个有记录账号`}`}><span className="text-[10px] tabular-nums text-slate-500">{valueLabel(point.value)}</span><div className={`w-full max-w-12 rounded-t-sm ${color}`} style={{ height: `${Math.max(4, point.value / max * 65)}%` }} /><span className="text-[10px] text-slate-500">{point.date.slice(5)}</span>{point.count !== undefined && <span className="text-[9px] text-slate-400">{point.count} 账</span>}</div>)}
    </div> : <div className="flex h-48 items-center justify-center border-y border-slate-200 text-sm text-slate-400">当前范围暂无可展示记录</div>}
  </button>;
}

function Kpi({ icon, label, value, detail, accent, onClick }: { icon: React.ReactNode; label: string; value: string; detail: string; accent: string; onClick: () => void }) {
  return <button type="button" onClick={onClick} className="min-w-0 border-r border-slate-200 pr-3 text-left last:border-0"><span className={`inline-flex items-center gap-1.5 text-xs ${accent}`}>{icon}{label}</span><strong className="mt-2 block truncate text-xl font-semibold tabular-nums text-slate-900">{value}</strong><span className="mt-1 block truncate text-xs text-slate-500">{detail}</span></button>;
}

function SourceButton({ title, detail, icon, onClick }: { title: string; detail: string; icon: React.ReactNode; onClick: () => void }) {
  return <button type="button" onClick={onClick} className="flex items-center gap-3 border-t border-slate-200 py-3 text-left hover:bg-slate-50"><span className="text-slate-500">{icon}</span><span className="min-w-0 flex-1"><strong className="block text-sm font-medium text-slate-800">{title}</strong><span className="mt-0.5 block truncate text-xs text-slate-500">{detail}</span></span><ArrowRight className="h-4 w-4 shrink-0 text-slate-400" /></button>;
}

function format(value: number): string { return Math.round(value).toLocaleString('zh-CN'); }
