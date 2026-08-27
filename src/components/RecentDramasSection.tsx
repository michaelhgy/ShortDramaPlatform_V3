import React from 'react';
import { DramaPrediction } from '../types';
import { DramaCover } from './DramaCover';
import { Plus, Sparkles, Zap, ChevronRight } from 'lucide-react';

interface RecentDramasSectionProps {
  predictions: DramaPrediction[];
  onScheduleDrama: (drama: DramaPrediction) => void;
}

export const RecentDramasSection: React.FC<RecentDramasSectionProps> = ({
  predictions,
  onScheduleDrama,
}) => {
  // Designated 1 Featured Opportunity Drama (Top item), and remaining candidates
  const featuredDrama = predictions.find(d => d.isFeatured) || predictions[0];
  const candidateDramas = predictions.filter(d => d.id !== featuredDrama?.id);

  const getPerformanceBadge = (perf: DramaPrediction['performance']) => {
    switch (perf) {
      case '爆发起量':
        return 'text-purple-800 bg-purple-100/80 border border-purple-200/60 font-bold';
      case '表现较好':
        return 'text-emerald-800 bg-emerald-100/80 border border-emerald-200/60 font-semibold';
      case '持续稳定':
        return 'text-blue-800 bg-blue-100/80 border border-blue-200/60 font-medium';
      case '潜力观察':
        return 'text-amber-800 bg-amber-100/80 border border-amber-200/60 font-medium';
      default:
        return 'text-slate-600 bg-slate-100 border border-slate-200/50';
    }
  };

  return (
    <section className="glass-sub-panel rounded-3xl p-5 sm:p-6 flex flex-col justify-between transition-all">
      <div>
        {/* Section Header */}
        <div className="flex items-center justify-between pb-3.5 border-b border-black/[0.05]">
          <div className="flex items-center gap-2">
            <h3 className="font-extrabold text-sm sm:text-[15px] text-[#1A1D2E] tracking-tight">
              近期剧集表现
            </h3>
            <span className="text-[11px] font-semibold text-[#64748B] bg-black/[0.03] px-2 py-0.5 rounded-md">
              选剧与收益推测
            </span>
          </div>
        </div>

        {/* 1. HERO FEATURED OPPORTUNITY DRAMA (1 个重点机会剧更突出) */}
        {featuredDrama && (
          <div className="mt-4 p-4 rounded-2xl bg-gradient-to-br from-white via-[#FCFDFE] to-[#F5F8FC] border border-black/[0.08] shadow-[0_4px_16px_rgba(26,29,46,0.04)] relative overflow-hidden group">
            {/* Ambient accent light highlight */}
            <div className="absolute top-0 right-0 w-32 h-32 bg-gradient-to-bl from-[#DDFD00]/15 to-transparent rounded-bl-full pointer-events-none" />

            <div className="flex items-start gap-3.5 relative z-10">
              {/* Large Drama Cover */}
              <div className="shrink-0">
                <DramaCover
                  name={featuredDrama.name}
                  coverUrl={featuredDrama.coverUrl}
                  colorPlaceholder={featuredDrama.colorPlaceholder}
                  size="lg"
                  className="w-20 h-28 sm:w-22 sm:h-30 rounded-xl shadow-md border border-black/[0.08]"
                />
              </div>

              {/* Drama Core Content & Actions */}
              <div className="flex-1 min-w-0 flex flex-col justify-between h-full">
                <div>
                  {/* Badge Header */}
                  <div className="flex items-center gap-1.5 flex-wrap">
                    <span className="inline-flex items-center gap-1 text-[10px] px-2 py-0.5 rounded-full bg-purple-600 text-white font-extrabold shadow-2xs">
                      <Sparkles className="w-2.5 h-2.5 fill-white" />
                      重点机会
                    </span>
                    <span className={`text-[10px] px-2 py-0.5 rounded-full ${getPerformanceBadge(featuredDrama.performance)}`}>
                      {featuredDrama.performance}
                    </span>
                    <span className="text-[10px] font-bold text-[#64748B]">
                      置信度 · {featuredDrama.confidence}
                    </span>
                  </div>

                  {/* Drama Title */}
                  <h4 className="font-extrabold text-sm sm:text-[15px] text-[#1A1D2E] mt-1.5 tracking-tight leading-snug">
                    《{featuredDrama.name}》
                  </h4>

                  {/* Revenue Estimation Box: Highlighted with clear 推测 label */}
                  <div className="mt-2 inline-flex items-center gap-1.5 bg-black/[0.03] px-2.5 py-1 rounded-lg border border-black/[0.04]">
                    <span className="text-[10px] text-amber-800 bg-amber-100/90 px-1 py-0.2 rounded font-bold">
                      推测
                    </span>
                    <span className="text-[11px] text-[#64748B] font-medium">推测收益:</span>
                    <span className="text-xs font-black text-[#1A1D2E]">
                      ¥{featuredDrama.estimatedRevenueMin} ～ ¥{featuredDrama.estimatedRevenueMax}
                    </span>
                  </div>

                  {/* Short Reason Quote */}
                  <p className="text-[11px] text-[#64748B] mt-2 leading-relaxed line-clamp-2">
                    {featuredDrama.reason}
                  </p>
                </div>

                {/* Prominent Action Button */}
                <div className="mt-3.5 pt-2.5 border-t border-black/[0.04] flex items-center justify-between">
                  <span className="text-[10px] text-slate-400 font-medium">适合今日晚间黄金档</span>
                  <button
                    id={`btn-schedule-featured-${featuredDrama.id}`}
                    onClick={() => onScheduleDrama(featuredDrama)}
                    className="flex items-center gap-1.5 px-3.5 py-1.5 rounded-xl bg-[#1A1D2E] hover:bg-black text-[#DDFD00] text-xs font-bold transition-all active:scale-98 shadow-xs cursor-pointer"
                  >
                    <Zap className="w-3.5 h-3.5 fill-[#DDFD00]" />
                    <span>安排今天</span>
                  </button>
                </div>
              </div>
            </div>
          </div>
        )}

        {/* 2. COMPACT CANDIDATE DRAMAS LIST (其他候选剧小型列表) */}
        <div className="mt-4 pt-3 border-t border-black/[0.05]">
          <div className="flex items-center justify-between pb-2">
            <span className="text-[11px] font-bold text-[#64748B] uppercase tracking-wider">
              其他候选剧目 ({candidateDramas.length})
            </span>
          </div>

          <div className="space-y-1.5">
            {candidateDramas.map((drama) => (
              <div
                key={drama.id}
                className="p-2 rounded-xl hover:bg-white/90 bg-white/40 border border-black/[0.03] hover:border-black/[0.08] transition-all flex items-center justify-between gap-3 group"
              >
                {/* Mini Poster Cover + Title Info */}
                <div className="flex items-center gap-2.5 min-w-0">
                  <DramaCover
                    name={drama.name}
                    coverUrl={drama.coverUrl}
                    colorPlaceholder={drama.colorPlaceholder}
                    size="sm"
                  />
                  <div className="min-w-0">
                    <div className="flex items-center gap-1.5">
                      <span className="font-bold text-xs text-[#1A1D2E] truncate">
                        《{drama.name}》
                      </span>
                      <span className={`text-[9px] px-1.5 py-0.2 rounded-md ${getPerformanceBadge(drama.performance)}`}>
                        {drama.performance}
                      </span>
                    </div>
                    <div className="text-[10px] text-[#64748B] font-medium mt-0.5 flex items-center gap-1.5">
                      <span>推测 ¥{drama.estimatedRevenueMin}～¥{drama.estimatedRevenueMax}</span>
                      <span>·</span>
                      <span>置信度 {drama.confidence}</span>
                    </div>
                  </div>
                </div>

                {/* Quick Add Button */}
                <button
                  id={`btn-schedule-drama-${drama.id}`}
                  onClick={() => onScheduleDrama(drama)}
                  className="opacity-0 group-hover:opacity-100 flex items-center gap-1 px-2 py-1 rounded-lg bg-[#1A1D2E] hover:bg-black text-[#DDFD00] text-[10px] font-bold transition-all active:scale-95 shrink-0 cursor-pointer shadow-xs"
                >
                  <Plus className="w-3 h-3 text-[#DDFD00]" />
                  <span>安排</span>
                </button>
              </div>
            ))}
          </div>
        </div>
      </div>
    </section>
  );
};
