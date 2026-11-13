import { OptimizationSettings } from './OptimizationSettings';
import { useCockpitData } from './CockpitDataContext';
import { formatOptimizationRate, formatWorkMetric } from '../../services/optimizationHealth';
import { getOptimizationAppearance, optimizationAnalysisBody } from '../../types/optimizationNotices';
import { AccountRatingBadge } from './AccountRatingBadge';
import { VideoTrafficTags } from './VideoTrafficTags';
import { summarizeAccountOptimization } from '../../services/accountOptimizationSummary';
import { CockpitDateFilter } from './CockpitDateFilter';
import type { CockpitDateRange } from '../../services/cockpitDateRange';
import React, { useState, useMemo, useEffect } from 'react';
import { AccountAvatar } from '../AccountAvatar';
import { 
  AccountOptimizationStat, 
  SimplifiedOptimizationReason, 
  VideoTrafficItem,
  AccountInfo
} from '../../types/shortDramaOps';
import { 
  ShieldAlert, 
  CheckCircle2, 
  AlertTriangle, 
  Search, 
  ChevronDown, 
  ChevronRight, 
  Play, 
  FileText, 
  ExternalLink,
  Layers,
  Sparkles,
  Info
} from 'lucide-react';

interface AccountOptimizationViewProps {
  onSettingsSaved: () => void;
  optimizationStats: AccountOptimizationStat[];
  allVideos: VideoTrafficItem[];
  theaters: Array<{ name: string; id: string }>;
  accounts: AccountInfo[];
  dateRange: CockpitDateRange;
  onDateRangeChange: (range: CockpitDateRange) => void;
  onOpenVideoDrawer?: (video: VideoTrafficItem) => void;
  onOpenAccountDrawer?: (account: AccountInfo) => void;
  reasonFilter: SimplifiedOptimizationReason | null;
  onReasonFilterChange: (reason:SimplifiedOptimizationReason|null) => void;
}

export const AccountOptimizationView: React.FC<AccountOptimizationViewProps> = ({
  optimizationStats,
  onSettingsSaved,
  allVideos,
  theaters,
  accounts,
  dateRange,
  onDateRangeChange,
  onOpenVideoDrawer,
  onOpenAccountDrawer,
  reasonFilter,
  onReasonFilterChange
}) => {
  const model = useCockpitData();
  const [selectedTheater, setSelectedTheater] = useState<string>('ALL');
  const pending = model.pendingOptimizations.filter(p => (!p.publish_time || model.isDateInRange(p.publish_time.slice(0,10),dateRange)) && (selectedTheater==='ALL' || accounts.some(a=>a.id===p.account_id && a.theaterName===selectedTheater)));
  const [searchQuery, setSearchQuery] = useState<string>('');
  const [healthFilter, setHealthFilter] = useState<'ALL' | 'healthy' | 'warning' | 'critical'>('ALL');
  const selectedReasonFilter=reasonFilter;
  const setSelectedReasonFilter=(reason:SimplifiedOptimizationReason|null)=>onReasonFilterChange(reason);
  const [expandedAccountId, setExpandedAccountId] = useState<string | null>(null);
  const [inspectingNotice, setInspectingNotice] = useState<SimplifiedOptimizationReason | null>(reasonFilter);
  useEffect(() => {
    if (inspectingNotice !== null && !Object.hasOwn(model.optimizationDefinitions, inspectingNotice)) setInspectingNotice(null);
  }, [model.optimizationDefinitions, inspectingNotice]);

  useEffect(() => {
    if (selectedTheater !== 'ALL' && !theaters.some(theater => theater.name === selectedTheater)) {
      setSelectedTheater('ALL');
    }
  }, [theaters, selectedTheater]);

  // Scope first; a reason filter narrows the list without changing rate denominators.
  const scopedStats = useMemo(() => {
    return optimizationStats.filter(stat => {
      if (selectedTheater !== 'ALL' && stat.theater !== selectedTheater) return false;
      if (healthFilter !== 'ALL' && stat.healthLevel !== healthFilter) return false;
      if (searchQuery.trim()) {
        const q = searchQuery.toLowerCase();
        const matchName = stat.accountName.toLowerCase().includes(q);
        const matchTheater = stat.theater.toLowerCase().includes(q);
        if (!matchName && !matchTheater) return false;
      }
      return true;
    });
  }, [optimizationStats, selectedTheater, healthFilter, searchQuery]);
  const filteredStats=useMemo(()=>scopedStats.filter(stat=>selectedReasonFilter===null||(stat.reasonCounts[selectedReasonFilter]||0)>0),[scopedStats,selectedReasonFilter]);

  const summaryMetrics=useMemo(()=>summarizeAccountOptimization(scopedStats),[scopedStats]);

  // 获取某个账号被优化的视频切片明细
  const getAccountOptimizedVideos = (accountId: string) => {
    return allVideos.filter(v => v.accountId === accountId && v.hasOptimization
      && (selectedReasonFilter===null||v.optimization?.simplifiedReason===selectedReasonFilter));
  };

  const getReasonColorClass = (reason: SimplifiedOptimizationReason) => getOptimizationAppearance(reason).pill;

  return (
    <div className="space-y-6">
      {/* 1. 顶部指标面板与说明 */}
      <div className="bg-white rounded-2xl p-6 border border-slate-200/80 shadow-xs">
        <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-4 pb-5 border-b border-slate-100">
          <div>
            <div className="flex items-center gap-2">
              <span className="p-2 bg-rose-50 text-rose-600 rounded-xl">
                <ShieldAlert className="w-5 h-5" />
              </span>
              <div>
                <h3 className="text-lg font-bold text-slate-900">平台算法优化监控中心</h3>
                <p className="text-xs text-slate-500 mt-0.5">
                  按作品分析原文归类，查看账号优化比例与具体作品
                </p>
              </div>
            </div>
          </div>

          <div className="flex items-center gap-3"><OptimizationSettings settings={model.optimizationActionSettings} onSaved={onSettingsSaved}/><CockpitDateFilter value={dateRange} onChange={onDateRangeChange} /></div>
        </div>

        <p className="mt-4 text-xs text-slate-500">{model.workScope==='all'?'统计账号全部已收录作品':'统计已确认由软件发布的作品'}；按实际发布时间计数，删除或隐藏后保留已收录历史。自动处理：{model.optimizationActionSettings?.enabled ? '已启用' : '关闭'}。</p>
        {pending.length>0 && <details className="mt-4 rounded-xl border border-amber-200 bg-amber-50 p-4 text-xs text-amber-900">
          <summary className="cursor-pointer font-semibold">{pending.length} 条优化通知待自动补查，尚未计入作品优化数</summary>
          <p className="mt-2 leading-5">通知已保留。下次优化采集会自动补查作品和官方详情；同秒存在多个候选或时间冲突时保持待查。相关优化比例显示待补齐。</p>
          <ul className="mt-3 space-y-3">{pending.map(p=><li key={p.id} className="border-t border-amber-200 pt-2"><strong>{accounts.find(a=>a.id===p.account_id)?.name || p.uid}</strong> · {p.publish_time || '发布时间待补查'} · {p.match_state==='ambiguous'?'同秒候选不唯一':p.match_state==='conflict'?'时间或身份冲突':'作品或详情待补查'}<p className="mt-1 break-all">{p.analysis || '官方分析尚未取得'}</p></li>)}</ul>
        </details>}
        {/* One shared summary for account optimization and platform notices. */}
        <div aria-label="账号优化统计" className="grid grid-cols-2 lg:grid-cols-5 gap-3 mt-5">
          <div className="p-4 bg-slate-50/70 rounded-xl border border-slate-100">
            <div className="text-xs text-slate-500 font-medium">周期发片总量</div>
            <div className="flex items-baseline gap-2 mt-1.5"><span className="text-2xl font-black text-slate-900 font-mono">{summaryMetrics.totalPublished}</span><span className="text-xs text-slate-400">条</span></div>
            <div className="text-[11px] text-slate-400 mt-1">当前范围内全部已发布视频</div>
          </div>
          <div className="p-4 bg-rose-50/50 rounded-xl border border-rose-100/60">
            <div className="text-xs text-rose-700 font-medium">被优化视频数</div>
            <div className="flex items-baseline gap-2 mt-1.5"><span className="text-2xl font-black text-rose-600 font-mono">{summaryMetrics.totalOptimized}</span><span className="text-xs text-rose-400">条</span></div>
            <div className="text-[11px] text-rose-400 mt-1">已记录平台优化提醒的视频</div>
          </div>
          <div className="p-4 bg-amber-50/50 rounded-xl border border-amber-100/60">
            <div className="text-xs text-amber-700 font-medium">整体优化率</div>
            <div className="text-2xl font-black text-amber-600 font-mono mt-1.5">{formatOptimizationRate(summaryMetrics.avgOptRate)}</div>
            <div className="text-[11px] text-amber-500 mt-1">被优化视频 / 总发片量</div>
          </div>
          <div className="min-w-0 p-4 bg-purple-50/50 rounded-xl border border-purple-100/60">
            <div className="text-xs text-purple-700 font-medium">最高频优化类型</div>
            <div className="flex items-baseline gap-1.5 mt-1.5">
              <span className="text-sm font-bold text-purple-900 truncate">{summaryMetrics.topReason||(summaryMetrics.totalOptimized?'待归类':'暂无')}</span>
              {summaryMetrics.topReasonCount>0&&<span className="shrink-0 text-xs font-mono text-purple-600 font-bold">{summaryMetrics.topReasonCount} 条</span>}
            </div>
            <div className="text-[11px] text-purple-400 mt-1 truncate">{summaryMetrics.topReason?model.optimizationDefinitions[summaryMetrics.topReason].shortTag:'暂无已归类优化记录'}</div>
          </div>
          <div className="p-4 bg-indigo-50/50 rounded-xl border border-indigo-100/60">
            <div className="text-xs text-indigo-700 font-medium">原创优化率</div>
            <div className="text-2xl font-black text-indigo-600 font-mono mt-1.5">{formatOptimizationRate(summaryMetrics.homogeneousRate)}</div>
            <div className="text-[11px] text-indigo-400 mt-1">原创优化 {summaryMetrics.homogeneousCount} / 总发片 {summaryMetrics.totalPublished}</div>
          </div>
        </div>

        {/* 当前暂行作品分析标签 */}
        <div className="mt-6 pt-5 border-t border-slate-100">
          <div className="flex items-center justify-between mb-3">
            <div className="flex items-center gap-2">
              <Info className="w-4 h-4 text-slate-400" />
              <span className="text-xs font-bold text-slate-800">作品分析标签</span>
              <span className="text-[11px] text-slate-400">点击标签筛选账号；在优化设置的“作品分析”中维护标签</span>
            </div>
          </div>

          <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 xl:grid-cols-6">
            {(Object.keys(model.optimizationDefinitions) as SimplifiedOptimizationReason[]).map(reason => {
              const def = model.optimizationDefinitions[reason];
              const count = summaryMetrics.reasonTotals[reason] || 0;
              const isSelected = selectedReasonFilter === reason;

              return (
                <button
                  key={reason}
                  onClick={() => {
                    const next=selectedReasonFilter===reason?null:reason;
                    setSelectedReasonFilter(next);
                    setInspectingNotice(next);
                  }}
                  className={`p-2.5 rounded-xl border text-left transition-all relative ${
                    isSelected
                      ? 'bg-indigo-50/90 border-indigo-400 ring-2 ring-indigo-500/20'
                      : 'bg-slate-50 hover:bg-slate-100/80 border-slate-200/80'
                  }`}
                >
                  <div className="flex min-w-0 items-start justify-between gap-1">
                    <span className="min-w-0 break-all text-xs font-bold text-slate-800">{reason}</span>
                    <span className={`max-w-[55%] break-all text-[10px] px-1.5 py-[0.8px] rounded border font-bold ${def.pill}`}>
                      {def.shortTag}
                    </span>
                  </div>
                  <div className="flex items-baseline justify-between mt-1.5">
                    <span className="text-xs font-mono font-bold text-slate-900">{count} 条</span>
                    <span className="text-[10px] text-slate-400">
                      占优化 {summaryMetrics.totalOptimized > 0 ? `${Math.round((count / summaryMetrics.totalOptimized) * 100)}%` : '0%'}
                    </span>
                  </div>
                </button>
              );
            })}
          </div>

          {/* 当点击某个分类时展开的官方原版文案视窗 */}
          {inspectingNotice && (
            <div className="mt-3 p-4 bg-indigo-50/60 rounded-xl border border-indigo-200/80 text-xs">
              <div className="flex items-start justify-between gap-4">
                <div>
                  <div className="flex items-center gap-2 mb-1.5">
                    <span className="px-2 py-0.5 rounded-md bg-indigo-600 text-white font-bold text-[10px]">
                      当前标签对应的作品分析
                    </span>
                    <span className="font-bold text-slate-900">
                      【{inspectingNotice}】
                    </span>

                  </div>
                  <div className="max-h-64 space-y-2 overflow-y-auto">
                    {model.getOptimizationAnalysisTexts(inspectingNotice).map(text=><p key={text} className="whitespace-pre-wrap break-words rounded-lg border border-indigo-100 bg-white/80 p-3 leading-relaxed text-slate-700">{optimizationAnalysisBody(text)}</p>)}
                    {!model.getOptimizationAnalysisTexts(inspectingNotice).length&&<p className="text-slate-500">暂无对应的作品分析原文。</p>}
                  </div>
                </div>
                <button
                  onClick={() => setInspectingNotice(null)}
                  className="text-slate-400 hover:text-slate-600 text-xs shrink-0 px-2 py-1"
                >
                  收起
                </button>
              </div>
            </div>
          )}
        </div>
      </div>

      {/* 2. 账号筛选与搜索工具条 */}
      <div className="bg-white rounded-2xl p-4 border border-slate-200/80 shadow-xs flex flex-wrap items-center justify-between gap-3">
        <div className="flex flex-wrap items-center gap-3">
          {/* 剧场筛选 */}
          <div className="flex items-center gap-2">
            <span className="text-xs text-slate-400 font-medium">剧场:</span>
            <select
              value={selectedTheater}
              onChange={e => setSelectedTheater(e.target.value)}
              className="text-xs bg-slate-50 border border-slate-200 rounded-lg px-2.5 py-1.5 font-medium text-slate-800 focus:outline-none focus:ring-2 focus:ring-indigo-500/20"
            >
              <option value="ALL">全部剧场 ({theaters.length}个)</option>
              {theaters.map(t => (
                <option key={t.id} value={t.name}>{t.name}</option>
              ))}
            </select>
          </div>

          {/* 健康等级筛选 */}
          <div className="flex items-center gap-2">
            <span className="text-xs text-slate-400 font-medium">风控状态:</span>
            <div className="inline-flex p-0.5 bg-slate-100 rounded-lg text-xs">
              <button
                onClick={() => setHealthFilter('ALL')}
                className={`px-2.5 py-1 rounded-md transition-all ${
                  healthFilter === 'ALL' ? 'bg-white font-bold text-slate-800 shadow-xs' : 'text-slate-600'
                }`}
              >
                全部
              </button>
              <button
                onClick={() => setHealthFilter('critical')}
                className={`px-2.5 py-1 rounded-md transition-all ${
                  healthFilter === 'critical' ? 'bg-white font-bold text-red-600 shadow-xs' : 'text-slate-600'
                }`}
              >
                高危（≥50%）
              </button>
              <button
                onClick={() => setHealthFilter('warning')}
                className={`px-2.5 py-1 rounded-md transition-all ${
                  healthFilter === 'warning' ? 'bg-white font-bold text-amber-600 shadow-xs' : 'text-slate-600'
                }`}
              >
                关注（20-50%）
              </button>
              <button
                onClick={() => setHealthFilter('healthy')}
                className={`px-2.5 py-1 rounded-md transition-all ${
                  healthFilter === 'healthy' ? 'bg-white font-bold text-emerald-600 shadow-xs' : 'text-slate-600'
                }`}
              >
                健康（≤20%）
              </button>
            </div>
          </div>

          {/* 优化原因快速过滤 */}
          {selectedReasonFilter !== null && (
            <div className="flex items-center gap-1.5 bg-purple-50 text-purple-700 px-2.5 py-1 rounded-lg text-xs font-medium border border-purple-200">
              <span>仅看: {selectedReasonFilter}</span>
              <button 
                onClick={() => setSelectedReasonFilter(null)}
                className="hover:text-purple-900 font-bold ml-1"
              >
                ×
              </button>
            </div>
          )}
        </div>

        {/* 搜索框 */}
        <div className="relative min-w-[220px]">
          <Search className="w-3.5 h-3.5 absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
          <input
            type="text"
            placeholder="搜索账号名、剧场..."
            value={searchQuery}
            onChange={e => setSearchQuery(e.target.value)}
            className="w-full text-xs pl-8 pr-3 py-1.5 bg-slate-50 border border-slate-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-indigo-500/20"
          />
        </div>
      </div>

      {/* 3. 账号发视频优化分析列表 (核心卡片与折叠明细) */}
      <div className="space-y-3">
        {filteredStats.length === 0 ? (
          <div className="bg-white rounded-2xl p-12 text-center border border-slate-200/80">
            <CheckCircle2 className="w-10 h-10 text-emerald-500 mx-auto mb-3" />
            <p className="text-slate-700 font-bold">未找到符合当前条件的账号优化记录</p>
            <p className="text-xs text-slate-400 mt-1">请尝试清除筛选条件或扩大日期区间</p>
          </div>
        ) : (
          filteredStats.map(stat => {
            const isExpanded = expandedAccountId === stat.accountId;
            const optVideos = isExpanded ? getAccountOptimizedVideos(stat.accountId) : [];
            const accountObj = accounts.find(a => a.id === stat.accountId);
            const { homogeneousRate, homogeneousCount } = summarizeAccountOptimization([stat]);
            const reasonItems=Object.entries<number>(stat.reasonCounts).filter(([,count])=>count>0).map(([name,count])=>({name,count}));
            const unclassified=Math.max(0,stat.optimizedVideos-reasonItems.reduce((sum,item)=>sum+item.count,0));
            if(unclassified>0)reasonItems.push({name:'待归类',count:unclassified});
            reasonItems.sort((a,b)=>b.count-a.count);

            return (
              <div 
                key={stat.accountId}
                className="bg-white rounded-2xl border border-slate-200/80 shadow-xs overflow-hidden transition-all"
              >
                {/* 账号主卡片 Header */}
                <div 
                  onClick={() => setExpandedAccountId(isExpanded ? null : stat.accountId)}
                  className="grid grid-cols-1 gap-4 p-5 hover:bg-slate-50/50 cursor-pointer lg:grid-cols-[minmax(0,0.9fr)_minmax(380px,1.1fr)_auto] lg:items-center"
                >
                  {/* 左侧：账号身份与剧场 */}
                  <div className="flex min-w-0 items-center gap-3.5">
                    <AccountAvatar name={accountObj?.name || stat.accountName} url={accountObj?.avatarUrl} className="w-10 h-10" />
                    <div className="min-w-0">
                      <div className="flex flex-wrap items-center gap-2">
                        <span className="truncate font-bold text-slate-900 text-sm hover:text-indigo-600 transition-colors">
                          {stat.accountName}
                        </span>
                        <span className="text-[10px] px-2 py-0.5 rounded-md bg-indigo-50 text-indigo-700 font-semibold border border-indigo-100">
                          {stat.theater}
                        </span>
                        {accountObj ? <AccountRatingBadge account={accountObj} compact /> : <span>待评</span>}
                      </div>
                      <div className="text-xs text-slate-400 mt-1 flex flex-wrap items-center gap-x-3 gap-y-1">
                        <span>总发片: <strong className="text-slate-700 font-mono">{stat.totalVideos}</strong> 条</span>
                        <span>总播放: <strong className="text-slate-700 font-mono">{stat.hasTraffic === false ? '—' : `${(stat.totalViews / 10000).toFixed(1)}w`}</strong></span>
                        {stat.latestOptimizedDate && (
                          <span>最近预警: <strong className="text-slate-700 font-mono">{stat.latestOptimizedDate}</strong></span>
                        )}
                      </div>
                    </div>
                  </div>

                  {/* 中间：优化率与健康等级 */}
                  <div aria-label={`${stat.accountName}优化表现`} className="grid min-w-0 grid-cols-1 items-start gap-4 sm:grid-cols-[180px_minmax(0,1fr)]">
                    <div>
                      <div className="text-[11px] text-slate-400 font-medium">优化量/优化率/原创优化</div>
                      <div className="mt-0.5 flex flex-wrap items-baseline gap-2">
                        <span className="text-lg font-black text-slate-900 font-mono">
                          {stat.optimizedVideos} <span className="text-xs text-slate-400 font-normal">条</span>
                        </span>
                        <span aria-label={`优化率：${formatOptimizationRate(stat.optimizationRate)}`} className={`text-xs px-2 py-0.5 rounded-md font-bold font-mono ${
                          stat.healthLevel === 'critical'
                            ? 'bg-red-100 text-red-700'
                            : stat.healthLevel === 'warning'
                            ? 'bg-amber-100 text-amber-700'
                              : 'bg-emerald-100 text-emerald-700'
                        }`}>
                          {formatOptimizationRate(stat.optimizationRate)}
                        </span>
                        <span aria-label={`原创优化率：${formatOptimizationRate(homogeneousRate)}（${homogeneousCount}/${stat.totalVideos}）`}
                          className="rounded-md bg-indigo-100 px-2 py-0.5 font-mono text-xs font-bold text-indigo-600">
                          {formatOptimizationRate(homogeneousRate)}
                        </span>
                      </div>
                    </div>

                    <div role="group" aria-label={`${stat.accountName}优化原因`} className="min-w-0">
                      <div className="text-[11px] font-medium text-slate-400">优化原因</div>
                      <div className="mt-1 flex flex-wrap items-start gap-1.5">
                        {reasonItems.map(item=><span key={item.name} aria-label={`${item.name}：${item.count}条`}
                          className={`inline-flex max-w-full items-center whitespace-normal break-all rounded-md border px-2 py-0.5 text-[10px] font-medium ${getReasonColorClass(item.name as SimplifiedOptimizationReason)}`}>
                          {item.name}: {item.count}
                        </span>)}
                      </div>
                      {reasonItems.length===0&&<span className="mt-1 inline-flex items-center gap-1 py-1 text-[11px] text-emerald-600"><CheckCircle2 className="h-3 w-3"/>暂无优化记录</span>}
                    </div>
                  </div>

                  {/* 右侧：动作与展开 */}
                  <div className="flex items-center gap-2 justify-end shrink-0">
                    {accountObj && onOpenAccountDrawer && (
                      <button
                        onClick={(e) => {
                          e.stopPropagation();
                          onOpenAccountDrawer(accountObj);
                        }}
                        className="text-xs text-indigo-600 hover:text-indigo-800 font-semibold px-2.5 py-1 rounded-lg hover:bg-indigo-50 transition-colors"
                      >
                        账号档案
                      </button>
                    )}

                    <div className="flex items-center gap-1 text-xs text-slate-500 font-medium">
                      <span>{isExpanded ? '收起视频明细' : '查看被优化视频'}</span>
                      {isExpanded ? <ChevronDown className="w-4 h-4 text-slate-400" /> : <ChevronRight className="w-4 h-4 text-slate-400" />}
                    </div>
                  </div>
                </div>

                {/* 折叠区：该账号被优化的具体视频列表 (剧名-n 格式、官方通知说明) */}
                {isExpanded && (
                  <div className="bg-slate-50/70 p-5 border-t border-slate-200/80 space-y-3">
                    <div className="flex items-center justify-between pb-2">
                      <div className="flex items-center gap-2">
                        <span className="font-bold text-xs text-slate-800">
                          {stat.accountName} 的被优化视频清单 ({optVideos.length} 条)
                        </span>
                        <span className="text-[11px] text-slate-400">
                          仅展示平台已下发优化提醒的真实切片条目
                        </span>
                      </div>
                    </div>

                    {optVideos.length === 0 ? (
                      <div className="p-4 bg-white rounded-xl border border-slate-200 text-center text-xs text-slate-400">
                        该账号在选定统计周期内发片正常，未触发平台优化限制
                      </div>
                    ) : (
                      <div className="space-y-2.5">
                        {optVideos.map(video => {
                          const opt = video.optimization;
                          const officialText = opt?.officialNotice?.trim() ? optimizationAnalysisBody(opt.officialNotice) : '暂无作品分析原文';

                          return (
                            <div 
                              key={video.id}
                              className="bg-white rounded-xl p-4 border border-slate-200/80 shadow-xs flex flex-col lg:flex-row lg:items-start justify-between gap-4"
                            >
                              {/* 视频核心信息 */}
                              <div className="min-w-0 flex-1 space-y-1.5">
                                <div className="flex flex-wrap items-center gap-2">
                                  <span className="max-w-full break-words font-bold text-sm text-slate-900 font-mono">
                                    {video.fileName}
                                  </span>
                                  <VideoTrafficTags video={video} />
                                  <span className="text-[11px] text-slate-400 font-mono">
                                    发布于 {video.publishTime}
                                  </span>
                                </div>

                                {/* Preserve this work's stored analysis text rather than substituting a category template. */}
                                <section aria-label="作品分析原文" className="p-3 bg-rose-50/40 rounded-lg border border-rose-100 text-xs text-slate-700">
                                  <div className="flex items-center gap-1.5 text-rose-700 font-bold mb-1">
                                    <AlertTriangle className="w-3.5 h-3.5" />
                                    <span>作品分析：</span>
                                  </div>
                                  <p className="whitespace-pre-wrap break-words text-[11px] text-slate-600 leading-relaxed font-normal">
                                    {officialText}
                                  </p>
                                </section>
                              </div>

                              {/* 视频流量与数据 */}
                              <div className="flex min-w-0 max-w-full items-start gap-3 lg:shrink-0 lg:pt-1">
                                <div role="group" aria-label={`${video.fileName}流量数据`} className="grid min-w-0 grid-cols-[repeat(5,max-content)] gap-x-4 overflow-x-auto pb-1 text-right">
                                <div>
                                  <div className="text-[10px] text-slate-400">播放量</div>
                                  <div className="font-bold font-mono text-sm text-slate-900">
                                    {formatWorkMetric(video.views)}
                                  </div>
                                </div>
                                <div>
                                  <div className="text-[10px] text-slate-400">完播率</div>
                                  <div className="font-bold font-mono text-sm text-slate-900">
                                    {Number.isFinite(video.completionRate) ? `${video.completionRate}%` : '—'}
                                  </div>
                                </div>
                                <div>
                                  <div className="text-[10px] text-slate-400">爱心</div>
                                  <div className="font-bold font-mono text-sm text-slate-900">
                                    {formatWorkMetric(video.hearts)}
                                  </div>
                                </div>
                                <div>
                                  <div className="text-[10px] text-slate-400">转发</div>
                                  <div className="font-bold font-mono text-sm text-slate-900">{formatWorkMetric(video.shares)}</div>
                                </div>
                                <div>
                                  <div className="text-[10px] text-slate-400">点赞</div>
                                  <div className="font-bold font-mono text-sm text-slate-900">{formatWorkMetric(video.thumbsUp)}</div>
                                </div>
                                </div>

                                {onOpenVideoDrawer && (
                                  <button
                                    onClick={() => onOpenVideoDrawer(video)}
                                    className="shrink-0 p-1.5 text-slate-400 hover:text-indigo-600 hover:bg-indigo-50 rounded-lg transition-colors"
                                    title="查看视频详情"
                                  >
                                    <ExternalLink className="w-4 h-4" />
                                  </button>
                                )}
                              </div>
                            </div>
                          );
                        })}
                      </div>
                    )}
                  </div>
                )}
              </div>
            );
          })
        )}
      </div>
    </div>
  );
};
