import { AccountRatingBadge, AccountRatingDetails } from './AccountRatingBadge';
import { VideoTrafficTags } from './VideoTrafficTags';
import { BusinessAccountStatusBadge } from './BusinessAccountStatusBadge';
import { getOptimizationAppearance, optimizationAnalysisBody } from '../../types/optimizationNotices';
import type { CockpitDateRange } from '../../services/cockpitDateRange';
import { CockpitModal } from './CockpitModal';
import React, { useEffect, useState } from 'react';
import { AccountAvatar } from '../AccountAvatar';
import { WorkVideoCover } from './WorkVideoCover';
import { AccountInfo, VideoTrafficItem } from '../../types/shortDramaOps';
import { useCockpitData } from './CockpitDataContext';
import { X, Play, TrendingUp, AlertTriangle, CheckCircle, Film, Sparkles, DollarSign, Heart, MessageSquare } from 'lucide-react';
import { DualTrendChart } from './InteractiveCharts';

interface AccountDetailDrawerProps {
  account: AccountInfo | null;
  dateRange: CockpitDateRange;
  onClose: () => void;
  onSelectVideo: (video: VideoTrafficItem) => void;
  onUpdateData?: () => void;
}

export const AccountDetailDrawer: React.FC<AccountDetailDrawerProps> = ({
  account, dateRange,
  onClose,
  onSelectVideo, onUpdateData,
}) => {
  const { filterVideos, filterRevenue, filterTraffic, isDateInRange, getDateBounds, OPTIMIZATION_RECORDS } = useCockpitData();
  const [activeTab, setActiveTab] = useState<'videos' | 'trend' | 'optimizations'>('trend');
  useEffect(() => { if (account) setActiveTab('trend'); }, [account?.id]);

  if (!account) return null;

  // 1. 找该账号的所有视频 (硬约束：文件名必须为 剧名-n)
  const accountVideos = filterVideos('ALL', account.id, dateRange);
  accountVideos.sort((a, b) => b.views - a.views);

  // 2. 找该账号的所有优化记录
  const accountOptimizations = OPTIMIZATION_RECORDS.filter(o => o.accountId === account.id && isDateInRange(o.publishTime.slice(0, 10), dateRange));

  // 3. 找该账号所选日期的收益与流量趋势
  const accountRevenueList = filterRevenue('ALL', account.id, dateRange);
  const accountTrafficList = filterTraffic('ALL', account.id, dateRange);

  const totalRevenue = accountRevenueList.reduce((sum, r) => sum + r.amount, 0);
  const totalViews = accountTrafficList.reduce((sum, t) => sum + t.views, 0);
  const totalFollows = accountTrafficList.reduce((sum, t) => sum + t.follows, 0);
  const historicalRevenue = account.rating?.recordedTotal ?? null;
  const historicalTraffic = filterTraffic('ALL', account.id, 'all').filter(row => Number.isFinite(row.views) && row.views >= 0);
  const historicalViews = historicalTraffic.length ? historicalTraffic.reduce((sum, row) => sum + row.views, 0) : null;

  // 整理所选区间内的日收益与流量，不截断为固定天数
  const dailyRevenues = accountRevenueList.filter(r => r.periodType !== 'month_cumulative');

  return (
    <CockpitModal label="账号详情" onClose={onClose} width="max-w-5xl" testId="account-detail-backdrop">
        
        {/* Header */}
        <div className="shrink-0 px-6 py-5 border-b border-slate-100 flex items-center justify-between bg-slate-50/80">
          <div className="flex min-w-0 items-center gap-3">
            <AccountAvatar name={account.name} url={account.avatarUrl} className="w-12 h-12" />
            <div className="min-w-0">
              <div className="flex flex-wrap items-center gap-2">
                <h3 className="min-w-0 break-all text-base font-extrabold text-[#1E1644]">{account.name}</h3>
                <BusinessAccountStatusBadge status={account.businessStatus} />
                {/* 剧场绑定标识 - 严格1:1 */}
                <span className="text-[11px] font-bold px-2 py-0.5 rounded bg-indigo-50 text-indigo-700 border border-indigo-200">
                  {account.theaterName}
                </span>
                <AccountRatingBadge account={account} />
              </div>
              <p className="mt-1 flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-slate-500">
                <span className="break-all font-mono text-[11px]">{account.channelId || account.id}</span>
                <span>{getDateBounds(dateRange).start} 至 {getDateBounds(dateRange).end}</span>
              </p>
            </div>
          </div>
          <div className="flex items-center gap-2">
          {onUpdateData && <button onClick={onUpdateData} className="rounded-xl border border-slate-200 bg-white px-3 py-2 text-xs font-semibold text-indigo-600 hover:bg-indigo-50">更新此账号</button>}
          <button
            aria-label="关闭账号详情"
            onClick={onClose}
            className="w-8 h-8 rounded-lg hover:bg-slate-200/70 text-slate-400 hover:text-slate-700 flex items-center justify-center transition-colors"
          >
            <X className="w-4 h-4" />
          </button>
          </div>
        </div>

        {/* Account Quick Metrics Banner */}
        <div data-account-quick-metrics role="group" aria-label="账号收益与流量摘要" className="shrink-0 px-6 py-3.5 bg-indigo-50/40 border-b border-indigo-100/60 grid grid-cols-2 gap-3 text-xs sm:grid-cols-3 lg:grid-cols-6">
          <div>
            <div className="text-slate-500 text-[11px]">历史收益</div>
            <div className="text-sm font-extrabold text-emerald-700 font-mono tabular-nums mt-0.5">
              {historicalRevenue === null ? '—' : `¥${historicalRevenue.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`}
            </div>
          </div>
          <div>
            <div className="text-slate-500 text-[11px]">历史播放</div>
            <div className="text-sm font-extrabold text-[#1E1644] font-mono tabular-nums mt-0.5">
              {historicalViews === null ? '—' : `${historicalViews.toLocaleString('zh-CN')} 次`}
            </div>
          </div>
          <div>
            <div className="text-slate-500 text-[11px]">区间收益</div>
            <div className="text-sm font-extrabold text-emerald-600 font-mono tabular-nums mt-0.5">
              {accountRevenueList.length ? `¥${totalRevenue.toLocaleString()}` : '—'}
            </div>
          </div>
          <div>
            <div className="text-slate-500 text-[11px]">区间播放</div>
            <div className="text-sm font-extrabold text-[#1E1644] font-mono tabular-nums mt-0.5">
              {accountTrafficList.length ? `${(totalViews / 10000).toFixed(1)}w 次` : '—'}
            </div>
          </div>
          <div>
            <div className="text-slate-500 text-[11px]">累计新增关注</div>
            <div className="text-sm font-extrabold text-indigo-600 font-mono tabular-nums mt-0.5">
              {accountTrafficList.length ? `${totalFollows >= 0 ? '+' : ''}${totalFollows.toLocaleString()}` : '—'}
            </div>
          </div>
          <div>
            <div className="text-slate-500 text-[11px]">受限优化记录</div>
            <div className="text-sm font-extrabold font-mono tabular-nums mt-0.5 flex items-center gap-1">
              {accountOptimizations.length > 0 ? (
                <span className="text-rose-600 font-bold flex items-center gap-1">
                  <AlertTriangle className="w-3.5 h-3.5" />
                  {accountOptimizations.length} 处
                </span>
              ) : (
                <span className="text-emerald-600 font-bold flex items-center gap-1">
                  <CheckCircle className="w-3.5 h-3.5" />
                  正常
                </span>
              )}
            </div>
          </div>
        </div>

        <div data-account-detail-scroll className="min-h-0 flex-1 overflow-y-auto">
        <div key={account.id} className="border-b border-slate-200/80 bg-slate-50/80 px-6 py-3"><AccountRatingDetails account={account} /></div>
        {/* Tab Switcher */}
        <div role="group" aria-label="账号详情页签" className="sticky top-0 z-10 flex items-center gap-4 overflow-x-auto whitespace-nowrap border-b border-slate-100 bg-white px-6 pt-3 text-xs font-bold [&>button]:shrink-0">
          <button
            onClick={() => setActiveTab('trend')}
            aria-pressed={activeTab === 'trend'}
            className={`pb-2.5 transition-colors border-b-2 flex items-center gap-1.5 ${
              activeTab === 'trend'
                ? 'border-indigo-600 text-indigo-600'
                : 'border-transparent text-slate-500 hover:text-slate-800'
            }`}
          >
            <TrendingUp className="w-3.5 h-3.5" />
            <span>播放与收益走势</span>
          </button>
          <button
            onClick={() => setActiveTab('videos')}
            aria-pressed={activeTab === 'videos'}
            className={`pb-2.5 transition-colors border-b-2 flex items-center gap-1.5 ${
              activeTab === 'videos'
                ? 'border-indigo-600 text-indigo-600'
                : 'border-transparent text-slate-500 hover:text-slate-800'
            }`}
          >
            <Film className="w-3.5 h-3.5" />
            <span>已发视频明细 ({accountVideos.length})</span>
          </button>
          <button
            onClick={() => setActiveTab('optimizations')}
            aria-pressed={activeTab === 'optimizations'}
            className={`pb-2.5 transition-colors border-b-2 flex items-center gap-1.5 ${
              activeTab === 'optimizations'
                ? 'border-indigo-600 text-indigo-600'
                : 'border-transparent text-slate-500 hover:text-slate-800'
            }`}
          >
            <AlertTriangle className="w-3.5 h-3.5" />
            <span>作品优化分析 ({accountOptimizations.length})</span>
          </button>
        </div>

        {/* Drawer Scrollable Content */}
        <div className="p-6 space-y-4">
          {activeTab === 'videos' ? (
            <div className="space-y-3">
              <div className="text-xs text-slate-400 flex items-center justify-between">
                <span>按播放量高低排序 · 点击可打开作品全维诊断</span>
                <span>文件名规范：剧名-n</span>
              </div>
              {accountVideos.length === 0 ? (
                <div className="py-12 text-center text-slate-400 text-xs">暂无视频记录</div>
              ) : (
                accountVideos.map((video) => (
                  <div
                    key={video.id}
                    onClick={() => onSelectVideo(video)}
                    className="p-3.5 rounded-xl border border-slate-100 hover:border-indigo-200 hover:bg-indigo-50/30 transition-all cursor-pointer group bg-white shadow-xs"
                  >
                    <div className="flex items-center gap-3">
                      <WorkVideoCover key={`${video.accountId}:${video.id}`} video={video} size="sm" />
                      <div className="min-w-0 flex-1 space-y-2">
                        <div className="flex flex-wrap items-center justify-between gap-3">
                          <div className="flex min-w-0 flex-1 flex-wrap items-center gap-2">
                            <span className="max-w-full truncate font-extrabold text-sm text-slate-900 group-hover:text-indigo-600 transition-colors">
                              {video.fileName}
                            </span>
                            <VideoTrafficTags video={video} />
                          </div>
                          <span className="text-[11px] text-slate-400 font-mono shrink-0">
                            {video.publishTime}
                          </span>
                        </div>
                        <div role="group" aria-label="作品播放与互动数据" className="flex flex-nowrap items-center gap-x-5 overflow-x-auto whitespace-nowrap pb-0.5 text-[11px]">
                          <span className="inline-flex shrink-0 items-center gap-1.5">
                            <span className="text-slate-400">播放量</span>
                            <span className="font-mono font-bold tabular-nums text-slate-800">
                              {video.views >= 10000 ? `${(video.views / 10000).toFixed(1)}w` : video.views.toLocaleString()}
                            </span>
                          </span>
                          <span className="inline-flex shrink-0 items-center gap-1.5">
                            <span className="text-slate-400">完播率</span>
                            <span className={`font-mono font-bold tabular-nums ${video.completionRate >= 25 ? 'text-emerald-600' : video.completionRate < 10 ? 'text-rose-500' : 'text-slate-800'}`}>
                              {video.completionRate}%
                            </span>
                          </span>
                          <span className="inline-flex shrink-0 items-center gap-1.5">
                            <span className="text-slate-400">爱心</span><span className="font-mono tabular-nums text-slate-700">{video.hearts.toLocaleString()}</span>
                          </span>
                          <span className="inline-flex shrink-0 items-center gap-1.5">
                            <span className="text-slate-400">评论</span><span className="font-mono tabular-nums text-slate-700">{video.comments.toLocaleString()}</span>
                          </span>
                          <span className="inline-flex shrink-0 items-center gap-1.5">
                            <span className="text-slate-400">转发/点赞</span><span className="font-mono tabular-nums text-slate-700">{video.shares}/{video.thumbsUp}</span>
                          </span>
                        </div>
                      </div>
                    </div>
                  </div>
                ))
              )}
            </div>
          ) : activeTab === 'trend' ? (
            <div className="space-y-4">
              <div className="p-4 rounded-2xl bg-slate-50 border border-slate-100">
                <div className="flex items-center justify-between mb-3 text-xs">
                  <span className="font-bold text-slate-800">所选区间日播放与日收益联动</span>
                  <div className="flex items-center gap-3 text-[11px]">
                    <span className="flex items-center gap-1 text-indigo-600">
                      <span className="w-2.5 h-2.5 rounded-full bg-indigo-500" /> 播放量 (左轴)
                    </span>
                    <span className="flex items-center gap-1 text-emerald-600">
                      <span className="w-2.5 h-2.5 rounded-full bg-emerald-500" /> 收益金额 (右轴)
                    </span>
                  </div>
                </div>
                <DualTrendChart dateBounds={getDateBounds(dateRange)} revenueData={dailyRevenues} trafficData={accountTrafficList} height={240} />
              </div>
            </div>
          ) : (
            <div className="space-y-3">
              {accountOptimizations.length === 0 ? (
                <div className="py-12 text-center text-slate-400 text-xs">
                  🎉 该账号目前健康良好，暂无作品优化记录
                </div>
              ) : (
                accountOptimizations.map(opt => (
                  <div key={opt.id} className="p-4 rounded-xl border border-rose-100 bg-rose-50/30 space-y-2">
                    <div className="flex items-center justify-between text-xs">
                      <div className="flex items-center gap-2">
                        <span className="font-bold text-rose-700 text-sm">
                          {opt.fileName}
                        </span>
                        <span className={`text-[10px] px-1.5 py-0.5 rounded border font-bold ${getOptimizationAppearance(opt.reasonType).pill}`}>
                          {opt.reasonType}
                        </span>
                        {opt.severity !== '未判定' && <span className="text-[10px] px-1.5 py-0.5 rounded bg-white text-rose-600 border border-rose-200">
                          {opt.severity}
                        </span>}
                      </div>
                      <span className="text-[11px] text-slate-400 font-mono">
                        发布时间: {opt.publishTime}
                      </span>
                    </div>

                    <div className="text-xs text-slate-700 leading-relaxed bg-white/70 p-2.5 rounded-lg border border-rose-100/60">
                      <span className="font-bold text-rose-900 block mb-1">作品分析原文：</span>
                      <p className="whitespace-pre-wrap break-words">{opt.officialNotice?.trim() ? optimizationAnalysisBody(opt.officialNotice) : '暂无作品分析原文'}</p>
                    </div>

                    {opt.impactNotice && <div className="text-xs text-slate-600 bg-amber-50/60 p-2.5 rounded-lg border border-amber-100">
                      <span className="font-bold text-amber-900 block mb-1">平台记录状态：</span>
                      {opt.impactNotice}
                    </div>}

                    <div className="flex items-center justify-between pt-1 text-[11px] text-slate-400 font-mono">
                      <span>检测识别日期: {opt.detectedDate}</span>
                      <span className="font-bold text-rose-600">类型：{opt.simplifiedReason}</span>
                    </div>
                  </div>
                ))
              )}
            </div>
          )}
        </div>

        </div>
        {/* Footer */}
        <div className="shrink-0 p-4 border-t border-slate-100 bg-slate-50 flex items-center justify-between text-xs text-slate-500">
          <span>所属剧场：{account.theaterName} · 严格单向归属</span>
          <button
            onClick={onClose}
            className="px-4 py-1.5 rounded-lg bg-slate-900 text-white font-semibold hover:bg-slate-800 transition-colors"
          >
            关闭面板
          </button>
        </div>
    </CockpitModal>
  );
};
