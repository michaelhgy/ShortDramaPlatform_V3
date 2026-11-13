import { createOptimizationReasonCounts, getOptimizationAppearance } from '../../types/optimizationNotices';
import { CockpitDateFilter } from './CockpitDateFilter';
import type { CockpitDateRange } from '../../services/cockpitDateRange';
import { useCockpitData } from './CockpitDataContext';
import React, { useState, useMemo } from 'react';
import { 
  OptimizationRecord, 
  SimplifiedOptimizationReason, 
  VideoTrafficItem,
  OFFICIAL_OPTIMIZATION_DEFINITIONS,
  TheaterInfo,
  AccountInfo
} from '../../types/shortDramaOps';
import { 
  ShieldAlert, 
  Search, 
  Filter, 
  AlertTriangle, 
  Calendar, 
  ExternalLink,
  ChevronDown,
  ChevronUp,
  BarChart3,
  Layers,
  Sparkles,
  Info
} from 'lucide-react';

interface OptimizationCommandViewProps {
  optimizationRecords: OptimizationRecord[];
  allVideos: VideoTrafficItem[];
  theaters: TheaterInfo[];
  accounts: AccountInfo[];
  dateRange: CockpitDateRange;
  onDateRangeChange: (range: CockpitDateRange) => void;
  onOpenVideoDrawer?: (video: VideoTrafficItem) => void;
  onOpenAccountDrawer?: (account: AccountInfo) => void;
  showToast?: (msg: string) => void;
}

export const OptimizationCommandView: React.FC<OptimizationCommandViewProps> = ({
  optimizationRecords,
  allVideos,
  theaters,
  accounts,
  dateRange,
  onDateRangeChange,
  onOpenVideoDrawer,
  onOpenAccountDrawer,
  showToast = (_msg: string) => {}
}) => {
  const model = useCockpitData();
  const { isDateInRange } = model;
  const [selectedTheater, setSelectedTheater] = useState<string>('ALL');
  const [selectedAccountId, setSelectedAccountId] = useState<string>('ALL');
  const [selectedReason, setSelectedReason] = useState<SimplifiedOptimizationReason | null>(null);
  const [searchQuery, setSearchQuery] = useState<string>('');
  const [expandedNoticeId, setExpandedNoticeId] = useState<string | null>(null);

  // 级联可用账号
  const availableAccounts = useMemo(() => {
    if (selectedTheater === 'ALL') return accounts;
    return accounts.filter(a => a.theaterName === selectedTheater);
  }, [selectedTheater, accounts]);

  const handleTheaterChange = (theater: string) => {
    setSelectedTheater(theater);
    if (theater !== 'ALL') {
      const match = accounts.find(a => a.id === selectedAccountId && a.theaterName === theater);
      if (!match) setSelectedAccountId('ALL');
    }
  };

  // 1. 过滤优化记录
  const filteredRecords = useMemo(() => {
    return optimizationRecords.filter(r => {
      if (selectedTheater !== 'ALL' && r.theater !== selectedTheater) return false;
      if (selectedAccountId !== 'ALL' && r.accountId !== selectedAccountId) return false;
      if (selectedReason !== null && r.simplifiedReason !== selectedReason) return false;

      // 日期过滤
      const rDate = r.publishTime.slice(0, 10);
      if (!isDateInRange(rDate, dateRange)) return false;

      if (searchQuery.trim()) {
        const q = searchQuery.toLowerCase();
        const matchFile = r.fileName.toLowerCase().includes(q);
        const matchDrama = r.dramaTitle.toLowerCase().includes(q);
        const matchAccount = r.accountName.toLowerCase().includes(q);
        if (!matchFile && !matchDrama && !matchAccount) return false;
      }

      return true;
    });
  }, [optimizationRecords, selectedTheater, selectedAccountId, selectedReason, dateRange, searchQuery, isDateInRange]);

  // 2. 对应周期的全部视频总数（用于计算优化率）
  const periodTotalVideos = useMemo(() => {
    return allVideos.filter(v => {
      if (selectedTheater !== 'ALL' && v.theater !== selectedTheater) return false;
      if (selectedAccountId !== 'ALL' && v.accountId !== selectedAccountId) return false;
      const vDate = v.publishTime.slice(0, 10);
      return isDateInRange(vDate, dateRange);
    }).length;
  }, [allVideos, selectedTheater, selectedAccountId, dateRange, isDateInRange]);

  // 3. 统计指标
  const metrics = useMemo(() => {
    const totalOptimized = filteredRecords.length;
    const optRate = periodTotalVideos > 0 
      ? Number(((totalOptimized / periodTotalVideos) * 100).toFixed(1)) 
      : 0;

    // 涉及账号
    const uniqueAccounts = new Set(filteredRecords.map(r => r.accountId)).size;

    // 各类型分类统计
    const reasonCounts = createOptimizationReasonCounts(Object.keys(model.optimizationDefinitions));

    filteredRecords.forEach(r => {
      if (reasonCounts[r.simplifiedReason] !== undefined) {
        reasonCounts[r.simplifiedReason]++;
      }
    });

    return {
      totalOptimized,
      optRate,
      uniqueAccounts,
      reasonCounts
    };
  }, [filteredRecords, periodTotalVideos, model.optimizationDefinitions]);

  const getReasonColor = (reason: SimplifiedOptimizationReason) => getOptimizationAppearance(reason).pill;

  return (
    <div className="space-y-6">
      {/* 1. 顶部控制栏与统计卡片 */}
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
                  按已保存的归类查看作品分析和标签
                </p>
              </div>
            </div>
          </div>

          <CockpitDateFilter value={dateRange} onChange={onDateRangeChange} />
        </div>

        {/* 核心指标统计 */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mt-5">
          <div className="p-4 bg-slate-50 rounded-xl border border-slate-100">
            <div className="text-xs text-slate-500 font-medium">周期发片总量</div>
            <div className="text-2xl font-black text-slate-900 font-mono mt-1.5">
              {periodTotalVideos} <span className="text-xs font-normal text-slate-400">条</span>
            </div>
            <div className="text-[11px] text-slate-400 mt-1">选定范围内所有已发布视频</div>
          </div>

          <div className="p-4 bg-rose-50/60 rounded-xl border border-rose-100">
            <div className="text-xs text-rose-700 font-medium">被优化视频数</div>
            <div className="text-2xl font-black text-rose-600 font-mono mt-1.5">
              {metrics.totalOptimized} <span className="text-xs font-normal text-rose-400">条</span>
            </div>
            <div className="text-[11px] text-rose-500 mt-1">收到微信视频号官方优化提醒</div>
          </div>

          <div className="p-4 bg-amber-50/60 rounded-xl border border-amber-100">
            <div className="text-xs text-amber-700 font-medium">矩阵整体优化率</div>
            <div className="text-2xl font-black text-amber-600 font-mono mt-1.5">
              {metrics.optRate}%
            </div>
            <div className="text-[11px] text-amber-500 mt-1">被优化视频 / 总发片量</div>
          </div>

          <div className="p-4 bg-indigo-50/60 rounded-xl border border-indigo-100">
            <div className="text-xs text-indigo-700 font-medium">涉及账号数</div>
            <div className="text-2xl font-black text-indigo-700 font-mono mt-1.5">
              {metrics.uniqueAccounts} <span className="text-xs font-normal text-indigo-400">/ {availableAccounts.length}</span>
            </div>
            <div className="text-[11px] text-indigo-500 mt-1">产生平台优化记录的矩阵账号</div>
          </div>
        </div>

        {/* 暂行标签筛选栏 */}
        <div className="mt-6 pt-5 border-t border-slate-100">
          <div className="text-xs font-bold text-slate-800 mb-3 flex items-center justify-between">
            <span>作品分析标签</span>
            {selectedReason !== null && (
              <button
                onClick={() => setSelectedReason(null)}
                className="text-indigo-600 hover:text-indigo-800 text-xs font-medium"
              >
                显示全部类型
              </button>
            )}
          </div>

          <div className="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-7 gap-2">
            {(Object.keys(model.optimizationDefinitions) as SimplifiedOptimizationReason[]).map(reason => {
              const def = model.optimizationDefinitions[reason];
              const count = metrics.reasonCounts[reason] || 0;
              const isSelected = selectedReason === reason;

              return (
                <button
                  key={reason}
                  onClick={() => setSelectedReason(isSelected ? 'ALL' : reason)}
                  className={`p-2.5 rounded-xl border text-left transition-all ${
                    isSelected
                      ? 'bg-rose-50 border-rose-400 ring-2 ring-rose-500/20'
                      : 'bg-slate-50 hover:bg-slate-100/70 border-slate-200/80'
                  }`}
                >
                  <div className="text-xs font-bold text-slate-800 truncate">{reason}</div>
                  <div className="flex items-baseline justify-between mt-1">
                    <span className="text-xs font-mono font-bold text-slate-900">{count} 条</span>
                    <span className="text-[10px] text-slate-400">
                      {metrics.totalOptimized > 0 ? `${Math.round((count / metrics.totalOptimized) * 100)}%` : '0%'}
                    </span>
                  </div>
                </button>
              );
            })}
          </div>
        </div>
      </div>

      {/* 2. 筛选器与搜索 */}
      <div className="bg-white rounded-2xl p-4 border border-slate-200/80 shadow-xs flex flex-wrap items-center justify-between gap-3">
        <div className="flex flex-wrap items-center gap-3">
          {/* 剧场下拉 */}
          <div className="flex items-center gap-2">
            <span className="text-xs text-slate-400 font-medium">剧场:</span>
            <select
              value={selectedTheater}
              onChange={e => handleTheaterChange(e.target.value)}
              className="text-xs bg-slate-50 border border-slate-200 rounded-lg px-2.5 py-1.5 font-medium text-slate-800 focus:outline-none focus:ring-2 focus:ring-indigo-500/20"
            >
              <option value="ALL">全部剧场 ({theaters.length}个)</option>
              {theaters.map(t => (
                <option key={t.id} value={t.name}>{t.name}</option>
              ))}
            </select>
          </div>

          {/* 账号下拉 */}
          <div className="flex items-center gap-2">
            <span className="text-xs text-slate-400 font-medium">账号:</span>
            <select
              value={selectedAccountId}
              onChange={e => setSelectedAccountId(e.target.value)}
              className="text-xs bg-slate-50 border border-slate-200 rounded-lg px-2.5 py-1.5 font-medium text-slate-800 focus:outline-none focus:ring-2 focus:ring-indigo-500/20"
            >
              <option value="ALL">全部账号 ({availableAccounts.length}个)</option>
              {availableAccounts.map(a => (
                <option key={a.id} value={a.id}>{a.name}</option>
              ))}
            </select>
          </div>
        </div>

        {/* 搜索 */}
        <div className="relative min-w-[240px]">
          <Search className="w-3.5 h-3.5 absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
          <input
            type="text"
            placeholder="搜切片文件名(剧名-n)、账号..."
            value={searchQuery}
            onChange={e => setSearchQuery(e.target.value)}
            className="w-full text-xs pl-8 pr-3 py-1.5 bg-slate-50 border border-slate-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-indigo-500/20"
          />
        </div>
      </div>

      {/* 3. 被优化视频明细清单 (带官方文案展开卡片) */}
      <div className="space-y-3">
        <div className="flex items-center justify-between text-xs text-slate-500 px-1">
          <span>共找到 <strong className="text-slate-900 font-mono">{filteredRecords.length}</strong> 条被优化视频</span>
          <span>按发布时间倒序排列</span>
        </div>

        {filteredRecords.length === 0 ? (
          <div className="bg-white rounded-2xl p-12 text-center border border-slate-200/80">
            <p className="text-slate-700 font-bold">暂无符合条件的优化视频</p>
            <p className="text-xs text-slate-400 mt-1">当前所选区间与账号下未发现平台优化通知</p>
          </div>
        ) : (
          filteredRecords.map(record => {
            const isNoticeOpen = expandedNoticeId === record.id;
            const def = model.optimizationDefinitions[record.simplifiedReason];
            const matchedVideo = allVideos.find(v => v.fileName === record.fileName && v.accountId === record.accountId);

            return (
              <div 
                key={record.id}
                className="bg-white rounded-2xl border border-slate-200/80 shadow-xs overflow-hidden"
              >
                <div className="p-5 flex flex-col lg:flex-row lg:items-center justify-between gap-4">
                  {/* 左侧：视频文件与账号 */}
                  <div className="space-y-1.5">
                    <div className="flex items-center gap-2 flex-wrap">
                      <span className="font-bold text-sm text-slate-900 font-mono">
                        {record.fileName}
                      </span>
                      <span className={`text-[10px] px-2 py-0.5 rounded-md font-bold border ${getReasonColor(record.simplifiedReason)}`}>
                        {record.simplifiedReason}
                      </span>
                      <span className="text-[10px] px-2 py-0.5 rounded-md bg-indigo-50 text-indigo-700 font-semibold border border-indigo-100">
                        {record.theater}
                      </span>
                      <span className="text-xs text-slate-500 font-medium">
                        {record.accountName}
                      </span>
                    </div>

                    <div className="text-xs text-slate-400 flex items-center gap-4">
                      <span>发布时间: <strong className="text-slate-700 font-mono">{record.publishTime}</strong></span>
                      {matchedVideo && (
                        <span>当前播放量: <strong className="text-slate-700 font-mono">{matchedVideo.views.toLocaleString()}</strong></span>
                      )}
                      {matchedVideo && (
                        <span>完播率: <strong className="text-slate-700 font-mono">{matchedVideo.completionRate}%</strong></span>
                      )}
                    </div>
                  </div>

                  {/* 右侧：官方文案切换与详情查看 */}
                  <div className="flex items-center gap-3 shrink-0">
                    <button
                      onClick={() => setExpandedNoticeId(isNoticeOpen ? null : record.id)}
                      className={`text-xs px-3 py-1.5 rounded-lg border font-semibold flex items-center gap-1.5 transition-all ${
                        isNoticeOpen 
                          ? 'bg-rose-50 text-rose-700 border-rose-200' 
                          : 'bg-slate-50 hover:bg-slate-100 text-slate-700 border-slate-200'
                      }`}
                    >
                      <span>{isNoticeOpen ? '收起官方通知' : '查看官方通知原件'}</span>
                      {isNoticeOpen ? <ChevronUp className="w-3.5 h-3.5" /> : <ChevronDown className="w-3.5 h-3.5" />}
                    </button>

                    {matchedVideo && onOpenVideoDrawer && (
                      <button
                        onClick={() => onOpenVideoDrawer(matchedVideo)}
                        className="text-xs text-indigo-600 hover:text-indigo-800 font-semibold px-2.5 py-1.5 rounded-lg hover:bg-indigo-50 transition-colors flex items-center gap-1"
                      >
                        <span>切片详情</span>
                        <ExternalLink className="w-3.5 h-3.5" />
                      </button>
                    )}
                  </div>
                </div>

                {/* 展开查看真实官方固定文案 */}
                {isNoticeOpen && (
                  <div className="bg-slate-50/80 p-5 border-t border-slate-200/80 space-y-3">
                    <div className="bg-white p-4 rounded-xl border border-rose-200/80 shadow-xs">
                      <div className="flex items-center justify-between pb-2 border-b border-rose-100">
                        <div className="flex items-center gap-2">
                          <span className="w-2 h-2 rounded-full bg-rose-500 animate-pulse" />
                          <span className="text-xs font-bold text-rose-800">
                            微信视频号平台违规与优化正式通知
                          </span>
                        </div>
                        <span className="text-[11px] text-slate-400">
                          监测识别日期: {record.detectedDate}
                        </span>
                      </div>

                      <div className="mt-3 space-y-2">
                        <p className="text-xs text-slate-800 font-medium leading-relaxed">
                          “{record.officialNotice || def?.officialNotice}”
                        </p>
                        <div className="p-2.5 bg-rose-50/60 rounded-lg text-[11px] text-rose-700 font-medium flex items-center gap-2">
                          <AlertTriangle className="w-3.5 h-3.5 shrink-0" />
                          <span>处理措施: {record.impactNotice || def?.impactNotice}</span>
                        </div>
                      </div>
                    </div>
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
