import React, { useState } from 'react';
import { ExploreDrama } from '../../exploreTypes';
import { DramaCover } from '../DramaCover';
import { 
  Flame, 
  Sparkles, 
  TrendingUp, 
  Plus, 
  Zap, 
  ChevronRight, 
  Film, 
  Target, 
  BarChart2, 
  Layers
} from 'lucide-react';

interface HeatRadarDramaSectionProps {
  dramas: ExploreDrama[];
  onScheduleDrama: (drama: ExploreDrama, targetTime?: string, targetAccountId?: string) => void;
  onMatrixSchedule: (drama: ExploreDrama) => void;
}

export const HeatRadarDramaSection: React.FC<HeatRadarDramaSectionProps> = ({
  dramas,
  onScheduleDrama,
  onMatrixSchedule,
}) => {
  const [selectedCategory, setSelectedCategory] = useState<string>('all');

  const heroDrama = (dramas || []).find(d => d.isHeroOpportunity) || (dramas || [])[0];
  const candidateDramas = (dramas || []).filter(d => !heroDrama || d.id !== heroDrama.id);

  const categories = ['all', '都市逆袭', '家庭伦理', '时代穿越', '女频爽剧'];

  const filteredCandidates = selectedCategory === 'all' 
    ? candidateDramas 
    : candidateDramas.filter(d => d.category?.includes(selectedCategory));

  return (
    <section className="rounded-3xl bg-white/85 border border-white/90 p-5 sm:p-6 shadow-[0_12px_32px_-4px_rgba(26,29,46,0.04)] backdrop-blur-xl flex flex-col justify-between">
      <div>
        {/* Section Header */}
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 pb-4 border-b border-black/[0.05]">
          <div>
            <div className="flex items-center gap-2.5">
              <div className="w-2.5 h-4 rounded-full bg-[#1A1D2E]" />
              <h3 className="font-extrabold text-base text-[#1A1D2E] tracking-tight">
                剧集热度雷达 & 选剧机会榜
              </h3>
              <span className="text-[11px] font-extrabold px-2 py-0.5 rounded-full bg-rose-50 text-rose-700 border border-rose-200/60 flex items-center gap-1">
                <Flame className="w-3 h-3 fill-rose-600 text-rose-600" />
                全网实时热度
              </span>
            </div>
            <p className="text-xs text-[#64748B] font-medium mt-0.5">
              基于大盘完播曲线与同行转化分析，精准推荐最适宜今天冲刺排期的剧目
            </p>
          </div>

          {/* Category Filter Chips */}
          <div className="flex items-center gap-1 overflow-x-auto pb-1 sm:pb-0">
            {categories.map((cat) => (
              <button
                key={cat}
                onClick={() => setSelectedCategory(cat)}
                className={`px-2.5 py-1 rounded-lg text-xs font-semibold transition-all cursor-pointer whitespace-nowrap ${
                  selectedCategory === cat
                    ? 'bg-[#1A1D2E] text-[#DDFD00]'
                    : 'bg-black/[0.03] text-[#64748B] hover:bg-black/[0.06] hover:text-[#1A1D2E]'
                }`}
              >
                {cat === 'all' ? '全部题材' : cat}
              </button>
            ))}
          </div>
        </div>

        {/* HERO EXPLOSIVE DRAMA SPOTLIGHT (100K-Level Feature Card) */}
        {heroDrama && (
          <div className="mt-4 p-4 sm:p-5 rounded-2xl bg-gradient-to-br from-[#1A1D2E] via-[#24283E] to-[#121420] text-white shadow-xl relative overflow-hidden group">
            {/* Ambient Lime Light Bloom */}
            <div className="absolute top-0 right-0 w-64 h-64 bg-[#DDFD00]/10 rounded-full blur-3xl pointer-events-none" />

            <div className="flex flex-col md:flex-row items-start gap-4 sm:gap-5 relative z-10">
              {/* High-Impact Vertical Poster */}
              <div className="relative shrink-0 mx-auto md:mx-0">
                <DramaCover
                  name={heroDrama.name}
                  coverUrl={heroDrama.coverUrl}
                  colorPlaceholder={heroDrama.colorPlaceholder}
                  size="lg"
                  className="w-28 h-38 sm:w-32 sm:h-44 rounded-xl shadow-2xl border border-white/20"
                />
                <div className="absolute -top-2 -left-2 px-2 py-0.5 rounded-full bg-[#DDFD00] text-[#1A1D2E] font-black text-[10px] shadow-md flex items-center gap-0.5">
                  <Flame className="w-3 h-3 fill-[#1A1D2E]" />
                  TOP 1 热度
                </div>
              </div>

              {/* Core Content & Metrics */}
              <div className="flex-1 min-w-0 flex flex-col justify-between w-full">
                <div>
                  {/* Top tags row */}
                  <div className="flex items-center gap-2 flex-wrap">
                    <span className="text-[11px] font-bold px-2.5 py-0.5 rounded-full bg-white/15 text-[#DDFD00] border border-white/10">
                      {heroDrama.category}
                    </span>
                    <span className="text-[11px] font-medium text-slate-300">
                      共 {heroDrama.totalEpisodes} 集
                    </span>
                    <span className="text-[11px] font-bold text-emerald-400 bg-emerald-950/60 px-2 py-0.5 rounded-md border border-emerald-500/30">
                      {heroDrama.completionRateEstimate}
                    </span>
                  </div>

                  {/* Title & Hook */}
                  <div className="mt-2 flex flex-col sm:flex-row sm:items-baseline gap-2">
                    <h4 className="text-lg sm:text-xl font-extrabold text-white tracking-tight leading-snug">
                      《{heroDrama.name}》
                    </h4>
                    <span className="text-xs text-[#DDFD00] font-semibold">
                      前3集钩子评分 {heroDrama.hookScore} 分 · {heroDrama.hookType}
                    </span>
                  </div>

                  {/* Estimation & Audience Banner */}
                  <div className="mt-3 grid grid-cols-1 sm:grid-cols-2 gap-2 text-xs">
                    <div className="p-2 rounded-xl bg-white/10 border border-white/10">
                      <span className="text-slate-400 block text-[10px]">推测单号收益</span>
                      <span className="text-sm font-extrabold text-[#DDFD00]">
                        {heroDrama.estimatedRevenueRange}
                      </span>
                    </div>

                    <div className="p-2 rounded-xl bg-white/10 border border-white/10">
                      <span className="text-slate-400 block text-[10px]">最佳匹配画像</span>
                      <span className="text-xs font-semibold text-white truncate block">
                        {heroDrama.targetAudience}
                      </span>
                    </div>
                  </div>

                  {/* Recommendation bullet points */}
                  <div className="mt-3 space-y-1">
                    {(heroDrama.reasons || []).map((r, i) => (
                      <div key={i} className="flex items-center gap-1.5 text-[11px] text-slate-300">
                        <span className="w-1 h-1 rounded-full bg-[#DDFD00]" />
                        <span className="truncate">{r}</span>
                      </div>
                    ))}
                  </div>
                </div>

                {/* Actions Footer */}
                <div className="mt-4 pt-3 border-t border-white/10 flex flex-wrap items-center justify-between gap-3">
                  <div className="text-xs text-slate-300 flex items-center gap-1.5">
                    <Target className="w-3.5 h-3.5 text-[#DDFD00]" />
                    <span>推荐主发账号：<strong className="text-white">{heroDrama.bestFitAccountName}</strong></span>
                  </div>

                  <div className="flex items-center gap-2">
                    <button
                      id="btn-schedule-hero-matrix"
                      onClick={() => onMatrixSchedule(heroDrama)}
                      className="px-3 py-1.5 rounded-xl bg-white/15 hover:bg-white/25 text-white text-xs font-bold transition-all cursor-pointer"
                    >
                      矩阵批量排期
                    </button>
                    <button
                      id="btn-schedule-hero-direct"
                      onClick={() => onScheduleDrama(heroDrama, '今天 18:30', heroDrama.bestFitAccountId)}
                      className="flex items-center gap-1.5 px-4 py-1.5 rounded-xl bg-[#DDFD00] hover:bg-[#CCEA00] text-[#1A1D2E] text-xs font-black transition-all shadow-md active:scale-98 cursor-pointer"
                    >
                      <Zap className="w-3.5 h-3.5 fill-[#1A1D2E]" />
                      <span>安排今天晚高峰 (18:30)</span>
                    </button>
                  </div>
                </div>
              </div>
            </div>
          </div>
        )}

        {/* CANDIDATE DRAMAS LIST (Enhanced Desktop Rows) */}
        <div className="mt-5">
          <div className="flex items-center justify-between pb-2">
            <span className="text-[11px] font-extrabold text-[#64748B] uppercase tracking-wider">
              其他热度候选剧目 ({filteredCandidates.length})
            </span>
            <span className="text-[11px] text-slate-400">
              支持一键配对对应主攻账号
            </span>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-2.5">
            {filteredCandidates.map((drama) => (
              <div
                key={drama.id}
                className="p-3 rounded-2xl bg-white/70 border border-black/[0.05] hover:border-[#1A1D2E] hover:bg-white hover:shadow-md transition-all flex items-start gap-3 group"
              >
                <DramaCover
                  name={drama.name}
                  coverUrl={drama.coverUrl}
                  colorPlaceholder={drama.colorPlaceholder}
                  size="md"
                  className="w-16 h-22 rounded-xl shrink-0"
                />

                <div className="flex-1 min-w-0 flex flex-col justify-between h-full">
                  <div>
                    <div className="flex items-center justify-between gap-1">
                      <span className="text-[10px] font-bold px-1.5 py-0.2 rounded bg-black/[0.04] text-[#64748B]">
                        {drama.category?.split('·')[0] || '短剧'}
                      </span>
                      <span className="text-[10px] font-extrabold text-rose-600 flex items-center gap-0.5">
                        <Flame className="w-2.5 h-2.5 fill-rose-600" />
                        热度 {drama.heatScore}
                      </span>
                    </div>

                    <h4 className="font-extrabold text-xs text-[#1A1D2E] mt-1 truncate">
                      《{drama.name}》
                    </h4>

                    <div className="text-[10px] text-[#64748B] mt-0.5 flex items-center gap-1.5 flex-wrap">
                      <span className="text-amber-800 font-bold">推测 {drama.estimatedRevenueRange}</span>
                      <span>·</span>
                      <span>{drama.completionRateEstimate}</span>
                    </div>

                    <div className="mt-1 text-[10px] text-slate-500 truncate">
                      适配：<strong className="text-[#1A1D2E]">{drama.bestFitAccountName}</strong>
                    </div>
                  </div>

                  <div className="mt-2 pt-1.5 border-t border-black/[0.04] flex items-center justify-between">
                    <span className="text-[10px] text-slate-400 font-medium truncate max-w-[110px]">
                      {drama.recommendedTime}
                    </span>
                    <button
                      onClick={() => onScheduleDrama(drama, drama.recommendedTime.split(' ')[0] + ' ' + drama.recommendedTime.split(' ')[1], drama.bestFitAccountId)}
                      className="flex items-center gap-1 px-2.5 py-1 rounded-lg bg-[#1A1D2E] hover:bg-black text-[#DDFD00] text-[10px] font-bold transition-all active:scale-95 cursor-pointer shadow-2xs"
                    >
                      <Plus className="w-3 h-3 text-[#DDFD00]" />
                      <span>安排</span>
                    </button>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </section>
  );
};
