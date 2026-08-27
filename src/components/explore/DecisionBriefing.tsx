import React from 'react';
import { DailyInsight } from '../../exploreTypes';
import { 
  Sparkles, 
  TrendingUp, 
  AlertTriangle, 
  Zap, 
  ArrowRight, 
  CheckCircle2,
  Clock
} from 'lucide-react';

interface DecisionBriefingProps {
  insights: DailyInsight[];
  totalYesterdayRevenue: number;
  unassignedCount: number;
  onExecuteInsightAction: (insight: DailyInsight) => void;
  onBatchAutoSchedule: () => void;
}

export const DecisionBriefing: React.FC<DecisionBriefingProps> = ({
  insights,
  totalYesterdayRevenue,
  unassignedCount,
  onExecuteInsightAction,
  onBatchAutoSchedule,
}) => {
  return (
    <div className="relative overflow-hidden rounded-3xl bg-gradient-to-r from-white/90 via-white/80 to-[#F5F8FC]/90 border border-white/90 p-5 sm:p-6 shadow-[0_12px_32px_-4px_rgba(26,29,46,0.05)] backdrop-blur-xl">
      {/* Subtle ambient light gradient in top corner */}
      <div className="absolute top-0 right-0 w-80 h-36 bg-gradient-to-bl from-[#DDFD00]/20 via-blue-500/5 to-transparent rounded-bl-full pointer-events-none" />
      
      {/* Header bar: Executive pulse */}
      <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-4 pb-4 border-b border-black/[0.05] relative z-10">
        <div className="flex items-center gap-3">
          <div className="w-9 h-9 rounded-2xl bg-[#1A1D2E] text-[#DDFD00] flex items-center justify-center shadow-md">
            <Sparkles className="w-5 h-5 fill-[#DDFD00]" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h2 className="text-base sm:text-lg font-extrabold text-[#1A1D2E] tracking-tight">
                今日运营决策速报
              </h2>
              <span className="text-[11px] font-bold px-2 py-0.5 rounded-full bg-[#DDFD00] text-[#1A1D2E] shadow-2xs">
                AI 策略推荐
              </span>
            </div>
            <p className="text-xs text-[#64748B] font-medium mt-0.5">
              全网剧集热度分析与账号画像匹配完成 · 发现 <strong className="text-[#1A1D2E]">3 项重点机会</strong> 与 <strong className="text-amber-800">{unassignedCount} 个待补排期</strong>
            </p>
          </div>
        </div>

        {/* Aggregate metric & one-click action */}
        <div className="flex items-center gap-4">
          <div className="hidden sm:flex items-center gap-3 px-3.5 py-1.5 rounded-2xl bg-black/[0.03] border border-black/[0.04]">
            <div className="text-right">
              <div className="text-[10px] text-[#64748B] font-semibold">昨日总营收</div>
              <div className="text-sm font-black text-[#1A1D2E] tracking-tight">
                ¥{totalYesterdayRevenue.toFixed(2)}
              </div>
            </div>
            <div className="flex items-center gap-1 text-[11px] font-bold text-emerald-700 bg-emerald-100/80 px-2 py-0.5 rounded-md">
              <TrendingUp className="w-3 h-3" />
              <span>+18.4%</span>
            </div>
          </div>

          <button
            id="btn-auto-batch-schedule"
            onClick={onBatchAutoSchedule}
            className="flex items-center gap-2 px-4 py-2 rounded-xl bg-[#1A1D2E] hover:bg-black text-[#DDFD00] text-xs font-extrabold transition-all shadow-md active:scale-98 cursor-pointer"
          >
            <Zap className="w-3.5 h-3.5 fill-[#DDFD00]" />
            <span>采纳推荐并一键填充排期</span>
          </button>
        </div>
      </div>

      {/* 3 Insight Opportunity Cards Grid */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-3.5 mt-4 relative z-10">
        {insights.map((insight) => {
          const isLime = insight.badgeColor === 'lime';
          const isAmber = insight.badgeColor === 'amber';
          const isPurple = insight.badgeColor === 'purple';

          return (
            <div
              key={insight.id}
              className={`p-4 rounded-2xl border transition-all flex flex-col justify-between group ${
                isLime
                  ? 'bg-white/90 border-[#DDFD00]/50 hover:border-[#1A1D2E] hover:shadow-md'
                  : isAmber
                  ? 'bg-amber-50/60 border-amber-200/70 hover:border-amber-400 hover:shadow-md'
                  : 'bg-purple-50/50 border-purple-200/70 hover:border-purple-400 hover:shadow-md'
              }`}
            >
              <div>
                {/* Top Badge & Metric */}
                <div className="flex items-center justify-between gap-2">
                  <span className={`text-[10px] font-extrabold px-2 py-0.5 rounded-full ${
                    isLime
                      ? 'bg-[#1A1D2E] text-[#DDFD00]'
                      : isAmber
                      ? 'bg-amber-500 text-white'
                      : 'bg-purple-600 text-white'
                  }`}>
                    {insight.badge}
                  </span>

                  {insight.highlightValue && (
                    <span className="text-[11px] font-extrabold text-[#1A1D2E]">
                      {insight.highlightValue}
                    </span>
                  )}
                </div>

                {/* Title */}
                <h4 className="font-extrabold text-xs sm:text-[13px] text-[#1A1D2E] mt-2.5 leading-snug tracking-tight">
                  {insight.title}
                </h4>

                {/* Description */}
                <p className="text-[11px] text-[#64748B] mt-1.5 leading-relaxed">
                  {insight.desc}
                </p>
              </div>

              {/* Action Link / Button */}
              {insight.actionText && (
                <div className="mt-3.5 pt-2.5 border-t border-black/[0.05] flex items-center justify-between">
                  <span className="text-[10px] text-slate-400 font-medium">推荐行动</span>
                  <button
                    onClick={() => onExecuteInsightAction(insight)}
                    className="inline-flex items-center gap-1 text-xs font-bold text-[#1A1D2E] hover:text-black group-hover:translate-x-0.5 transition-all cursor-pointer"
                  >
                    <span>{insight.actionText}</span>
                    <ArrowRight className="w-3.5 h-3.5" />
                  </button>
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
};
