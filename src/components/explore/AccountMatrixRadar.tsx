import { AccountAvatar } from '../AccountAvatar';
import React, { useState } from 'react';
import { ExploreAccount } from '../../exploreTypes';
import { ManualAccountStatus } from '../../types';
import { 
  TrendingUp, 
  TrendingDown, 
  AlertCircle, 
  Plus, 
  Sparkles, 
  ShieldCheck, 
  Zap, 
  CheckCircle2, 
  Layers
} from 'lucide-react';

interface AccountMatrixRadarProps {
  accounts: ExploreAccount[];
  arrangedAccountIds: string[];
  onScheduleAccount: (account: ExploreAccount, dramaId?: string) => void;
  onQuickPair: (account: ExploreAccount) => void;
}

export const AccountMatrixRadar: React.FC<AccountMatrixRadarProps> = ({
  accounts,
  arrangedAccountIds,
  onScheduleAccount,
  onQuickPair,
}) => {
  const [filterTag, setFilterTag] = useState<string>('all');

  const getHealthTagBadge = (tag: ExploreAccount['healthTag']) => {
    switch (tag) {
      case '爆发主攻':
        return (
          <span className="inline-flex items-center gap-1 text-[10px] px-2 py-0.5 rounded-full bg-purple-100 text-purple-800 font-extrabold border border-purple-200/60 shadow-2xs">
            <Sparkles className="w-2.5 h-2.5 fill-purple-700" />
            爆发主攻
          </span>
        );
      case '流量爬坡':
        return (
          <span className="inline-flex items-center gap-1 text-[10px] px-2 py-0.5 rounded-full bg-emerald-100 text-emerald-800 font-extrabold border border-emerald-200/60">
            <TrendingUp className="w-2.5 h-2.5" />
            流量爬坡
          </span>
        );
      case '未排期预警':
        return (
          <span className="inline-flex items-center gap-1 text-[10px] px-2 py-0.5 rounded-full bg-amber-100 text-amber-900 font-extrabold border border-amber-200/80 animate-pulse">
            <AlertCircle className="w-2.5 h-2.5 text-amber-700" />
            未排期预警
          </span>
        );
      case '防限流观察':
        return (
          <span className="inline-flex items-center gap-1 text-[10px] px-2 py-0.5 rounded-full bg-slate-100 text-slate-700 font-bold border border-slate-200">
            <ShieldCheck className="w-2.5 h-2.5" />
            防限流观察
          </span>
        );
      default:
        return (
          <span className="text-[10px] px-2 py-0.5 rounded-full bg-slate-100 text-slate-600 font-medium">
            稳定长尾
          </span>
        );
    }
  };

  const getManualStatusStyle = (status: ManualAccountStatus) => {
    switch (status) {
      case '正常':
        return 'text-emerald-700 bg-emerald-50';
      case '观察':
        return 'text-amber-800 bg-amber-50';
      case '暂停':
        return 'text-slate-500 bg-slate-100';
      case '实名':
        return 'text-blue-700 bg-blue-50';
      case '封号':
        return 'text-rose-700 bg-rose-50';
      default:
        return 'text-slate-600 bg-slate-100';
    }
  };

  // Sparkline simple SVG renderer
  const renderSparkline = (points: number[]) => {
    const min = Math.min(...points);
    const max = Math.max(...points) || 1;
    const range = max - min || 1;
    const height = 18;
    const width = 64;

    const coords = points.map((val, idx) => {
      const x = (idx / (points.length - 1)) * width;
      const y = height - ((val - min) / range) * (height - 4) - 2;
      return `${x},${y}`;
    }).join(' ');

    return (
      <svg width={width} height={height} className="overflow-visible">
        <polyline
          fill="none"
          stroke="#1A1D2E"
          strokeWidth="1.8"
          strokeLinecap="round"
          strokeLinejoin="round"
          points={coords}
        />
      </svg>
    );
  };

  const filteredAccounts = accounts.filter(acc => {
    if (filterTag === 'all') return true;
    if (filterTag === 'unassigned') return !arrangedAccountIds.includes(acc.id) && acc.manualStatus !== '暂停';
    if (filterTag === 'boost') return acc.healthTag === '爆发主攻' || acc.healthTag === '流量爬坡';
    if (filterTag === 'warning') return acc.healthTag === '未排期预警';
    return true;
  });

  return (
    <section className="rounded-3xl bg-white/85 border border-white/90 p-5 sm:p-6 shadow-[0_12px_32px_-4px_rgba(26,29,46,0.04)] backdrop-blur-xl flex flex-col justify-between">
      <div>
        {/* Section Header */}
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 pb-4 border-b border-black/[0.05]">
          <div>
            <div className="flex items-center gap-2">
              <div className="w-2.5 h-4 rounded-full bg-[#1A1D2E]" />
              <h3 className="font-extrabold text-base text-[#1A1D2E] tracking-tight">
                账号矩阵动态与机会雷达
              </h3>
              <span className="text-[11px] font-bold text-[#64748B] bg-black/[0.03] px-2 py-0.5 rounded-md">
                {accounts.length} 个运营号
              </span>
            </div>
            <p className="text-xs text-[#64748B] font-medium mt-0.5">
              监控账号流量爬坡趋势，识别空转风险，智能配对最佳短剧题材
            </p>
          </div>

          {/* Filter tabs */}
          <div className="flex items-center gap-1">
            <button
              onClick={() => setFilterTag('all')}
              className={`px-2.5 py-1 rounded-lg text-xs font-semibold transition-all cursor-pointer ${
                filterTag === 'all'
                  ? 'bg-[#1A1D2E] text-[#DDFD00]'
                  : 'bg-black/[0.03] text-[#64748B] hover:bg-black/[0.06]'
              }`}
            >
              全部
            </button>
            <button
              onClick={() => setFilterTag('unassigned')}
              className={`px-2.5 py-1 rounded-lg text-xs font-semibold transition-all cursor-pointer flex items-center gap-1 ${
                filterTag === 'unassigned'
                  ? 'bg-[#1A1D2E] text-[#DDFD00]'
                  : 'bg-amber-50 text-amber-800 hover:bg-amber-100'
              }`}
            >
              <AlertCircle className="w-3 h-3 text-amber-600" />
              <span>待安排</span>
            </button>
            <button
              onClick={() => setFilterTag('boost')}
              className={`px-2.5 py-1 rounded-lg text-xs font-semibold transition-all cursor-pointer ${
                filterTag === 'boost'
                  ? 'bg-[#1A1D2E] text-[#DDFD00]'
                  : 'bg-black/[0.03] text-[#64748B] hover:bg-black/[0.06]'
              }`}
            >
              爆发 / 爬坡
            </button>
          </div>
        </div>

        {/* Account Table / Grid Cards */}
        <div className="mt-4 space-y-2.5">
          {filteredAccounts.map((account) => {
            const isArranged = arrangedAccountIds.includes(account.id);

            return (
              <div
                key={account.id}
                className="p-3.5 rounded-2xl bg-white/70 border border-black/[0.05] hover:border-black/[0.14] hover:bg-white hover:shadow-md transition-all flex flex-col sm:flex-row sm:items-center justify-between gap-3 group"
              >
                {/* Account info + Health tag */}
                <div className="flex items-center gap-3 min-w-0">
                  <AccountAvatar name={account.name} url={account.avatarUrl} className="w-10 h-10" />

                  <div className="min-w-0">
                    <div className="flex items-center gap-2 flex-wrap">
                      <span className="font-extrabold text-xs sm:text-[13px] text-[#1A1D2E] truncate">
                        {account.name}
                      </span>
                      {getHealthTagBadge(account.healthTag)}
                      <span className={`text-[9px] px-1.5 py-0.2 rounded font-semibold ${getManualStatusStyle(account.manualStatus)}`}>
                        {account.manualStatus}
                      </span>
                    </div>

                    <div className="text-[10px] text-[#64748B] mt-1 flex items-center gap-2 flex-wrap">
                      <span>粉丝 {account.fanCount}</span>
                      <span>·</span>
                      <span>本月 ¥{account.monthRevenue.toFixed(0)}</span>
                      {account.riskNote && (
                        <span className="text-amber-800 font-semibold truncate max-w-[220px]">
                          ⚠️ {account.riskNote}
                        </span>
                      )}
                    </div>
                  </div>
                </div>

                {/* Performance numbers + Sparkline + Smart Pairing */}
                <div className="flex items-center gap-4 shrink-0 justify-between sm:justify-end border-t sm:border-t-0 pt-2 sm:pt-0 border-black/[0.04]">
                  {/* Revenue & Growth */}
                  <div className="text-right">
                    <div className="flex items-center justify-end gap-1.5">
                      <span className="text-xs font-black text-[#1A1D2E] tracking-tight">
                        ¥{account.yesterdayRevenue.toFixed(2)}
                      </span>
                      {account.revenueChangePercent > 0 ? (
                        <span className="text-[10px] font-bold text-emerald-700 flex items-center">
                          +{account.revenueChangePercent}%
                        </span>
                      ) : account.revenueChangePercent < 0 ? (
                        <span className="text-[10px] font-bold text-rose-700 flex items-center">
                          {account.revenueChangePercent}%
                        </span>
                      ) : null}
                    </div>
                    <div className="mt-0.5 flex justify-end">
                      {renderSparkline(account.revenueTrend)}
                    </div>
                  </div>

                  {/* Smart Drama Match Pill & Actions */}
                  <div className="flex items-center gap-2">
                    <div className="hidden md:block text-right">
                      <span className="text-[10px] text-slate-400 block">推荐配对剧目</span>
                      <span className="text-xs font-bold text-[#1A1D2E] truncate max-w-[130px] block">
                        《{account.recommendedDramaName}》
                      </span>
                    </div>

                    {isArranged ? (
                      <div className="flex items-center gap-1.5">
                        <span className="inline-flex items-center gap-1 text-[10px] font-extrabold text-emerald-700 bg-emerald-50 border border-emerald-200/60 px-2 py-1 rounded-lg">
                          <CheckCircle2 className="w-3 h-3" />
                          <span>已安排 ({account.todayTaskCount})</span>
                        </span>
                        <button
                          onClick={() => onScheduleAccount(account)}
                          title="追加安排新剧目"
                          className="p-1 rounded-lg hover:bg-black/[0.05] text-[#64748B] hover:text-[#1A1D2E] transition-colors cursor-pointer"
                        >
                          <Plus className="w-3.5 h-3.5" />
                        </button>
                      </div>
                    ) : (
                      <button
                        onClick={() => onQuickPair(account)}
                        className="flex items-center gap-1.5 px-3 py-1.5 rounded-xl bg-[#1A1D2E] hover:bg-black text-[#DDFD00] text-xs font-extrabold transition-all active:scale-95 shadow-xs cursor-pointer"
                      >
                        <Zap className="w-3 h-3 fill-[#DDFD00]" />
                        <span>配对安排</span>
                      </button>
                    )}
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </section>
  );
};
