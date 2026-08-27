import React from 'react';
import { AccountItem, ManualAccountStatus } from '../types';
import { Plus, TrendingUp } from 'lucide-react';

interface YesterdayAccountsSectionProps {
  accounts: AccountItem[];
  arrangedAccountIds: string[];
  onScheduleAccount: (account: AccountItem) => void;
}

export const YesterdayAccountsSection: React.FC<YesterdayAccountsSectionProps> = ({
  accounts,
  arrangedAccountIds,
  onScheduleAccount,
}) => {
  const totalYesterdayRevenue = accounts.reduce((acc, curr) => acc + curr.yesterdayRevenue, 0);

  const getManualStatusStyle = (status: ManualAccountStatus) => {
    switch (status) {
      case '正常':
        return 'text-emerald-700 bg-emerald-50 border border-emerald-200/50';
      case '观察':
        return 'text-amber-800 bg-amber-50 border border-amber-200/50';
      case '暂停':
        return 'text-slate-500 bg-slate-100 border border-slate-200/50';
      case '实名':
        return 'text-blue-700 bg-blue-50 border border-blue-200/50';
      case '封号':
        return 'text-rose-700 bg-rose-50 border border-rose-200/50';
      default:
        return 'text-slate-600 bg-slate-100 border border-slate-200/50';
    }
  };

  return (
    <section className="glass-sub-panel rounded-3xl p-5 sm:p-6 flex flex-col justify-between transition-all">
      <div>
        {/* Section Header: Clean Desktop Software style */}
        <div className="flex items-center justify-between pb-3.5 border-b border-black/[0.05]">
          <div className="flex items-center gap-2">
            <h3 className="font-extrabold text-sm sm:text-[15px] text-[#1A1D2E] tracking-tight">
              昨日账号表现
            </h3>
            <span className="text-[11px] font-semibold text-[#64748B] bg-black/[0.03] px-2 py-0.5 rounded-md">
              {accounts.length} 个运营号
            </span>
          </div>

          {/* Revenue Highlight in Header */}
          <div className="flex items-center gap-1.5 text-right">
            <span className="text-[11px] text-[#64748B] font-medium">昨日总计</span>
            <span className="text-sm font-extrabold text-[#1A1D2E] tracking-tight">
              ¥{totalYesterdayRevenue.toFixed(2)}
            </span>
          </div>
        </div>

        {/* Desktop List: Column headers for quick scanning */}
        <div className="grid grid-cols-12 text-[10px] font-bold text-[#64748B] uppercase tracking-wider px-2 py-2 border-b border-black/[0.03]">
          <div className="col-span-5">账号 / 状态</div>
          <div className="col-span-4 text-right">昨日 / 本月收益</div>
          <div className="col-span-3 text-right">今日状态</div>
        </div>

        {/* Desktop List Items */}
        <div className="divide-y divide-black/[0.04]">
          {accounts.map((account) => {
            const isArranged = arrangedAccountIds.includes(account.id);

            return (
              <div
                key={account.id}
                className="py-2.5 px-2 hover:bg-white/80 rounded-xl transition-all grid grid-cols-12 items-center gap-2 group"
              >
                {/* Account Name & Status (Col 5) */}
                <div className="col-span-5 min-w-0 pr-1">
                  <div className="flex items-center gap-1.5">
                    <span className="font-bold text-xs text-[#1A1D2E] truncate block">
                      {account.name}
                    </span>
                  </div>
                  <div className="mt-0.5">
                    <span className={`inline-block text-[9px] px-1.5 py-0.2 rounded font-semibold ${getManualStatusStyle(account.manualStatus)}`}>
                      {account.manualStatus}
                    </span>
                  </div>
                </div>

                {/* Financial figures with strong visual weight (Col 4) */}
                <div className="col-span-4 text-right min-w-0">
                  <div className="font-extrabold text-xs text-[#1A1D2E] tracking-tight">
                    ¥{account.yesterdayRevenue.toFixed(2)}
                  </div>
                  <div className="text-[10px] text-[#64748B] font-medium truncate">
                    本月 ¥{account.monthRevenue.toFixed(0)}
                  </div>
                </div>

                {/* Status Pill & Hover Action Button (Col 3) */}
                <div className="col-span-3 flex items-center justify-end gap-1.5 shrink-0">
                  {/* Default status tag */}
                  <span className={`text-[10px] font-bold px-2 py-0.5 rounded-md ${
                    isArranged 
                      ? 'text-emerald-700 bg-emerald-50 border border-emerald-200/50' 
                      : 'text-amber-700 bg-amber-50 border border-amber-200/50'
                  } group-hover:hidden`}>
                    {isArranged ? '已安排' : '未安排'}
                  </span>

                  {/* Hover action button */}
                  <button
                    id={`btn-schedule-account-${account.id}`}
                    onClick={() => onScheduleAccount(account)}
                    className="hidden group-hover:flex items-center gap-1 px-2 py-0.5 rounded-lg bg-[#1A1D2E] hover:bg-black text-[#DDFD00] text-[10px] font-bold transition-all active:scale-95 shadow-xs cursor-pointer"
                  >
                    <Plus className="w-2.5 h-2.5 text-[#DDFD00]" />
                    <span>安排</span>
                  </button>
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </section>
  );
};
