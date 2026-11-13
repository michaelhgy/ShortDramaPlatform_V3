import { formatPlannedDate, plannedDate, plannedSortTimestamp } from '../../utils/plannedDate';
import React, { useState } from 'react';
import { 
  Sparkles, 
  Flame, 
  HelpCircle, 
  ChevronDown, 
  ChevronUp, 
  Clock, 
  CheckCircle2, 
  ListOrdered, 
  ShieldCheck, 
  Zap,
  Info
} from 'lucide-react';
import { DramaSchedulePriority } from './taskCenterTypes';

interface DramaPriorityBannerProps {
  dramaPriorities: DramaSchedulePriority[];
}

export const DramaPriorityBanner: React.FC<DramaPriorityBannerProps> = ({
  dramaPriorities,
}) => {
  const [isRuleExpanded, setIsRuleExpanded] = useState(false);

  return (
    <div className="rounded-2xl border border-black/[0.06] bg-gradient-to-r from-slate-50 via-white to-slate-50 p-4 shadow-2xs">
      <div className="flex flex-wrap items-center justify-between gap-3">
        {/* Left Title & Key Dynamic Status */}
        <div className="flex items-center gap-3">
          <div className="w-8 h-8 rounded-xl bg-[#1A1D2E] text-[#DDFD00] flex items-center justify-center font-bold text-xs shadow-xs">
            <ListOrdered className="w-4 h-4" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h4 className="font-extrabold text-xs text-[#1A1D2E]">
                今日账号×剧集动态生产优先级调度
              </h4>
              <span className="text-[10px] px-2 py-0.5 rounded-full bg-emerald-100 text-emerald-800 font-bold">
                动态保障最高优先级整剧交付
              </span>
            </div>
            <p className="text-[11px] text-[#64748B] mt-0.5">
              每张卡对应一个账号×剧集发布计划；计划发布日期越早优先级越高，同一计划日期按开工时间优先。
            </p>
          </div>
        </div>

        {/* Toggle Rule Explanation Button */}
        <button
          onClick={() => setIsRuleExpanded(!isRuleExpanded)}
          className="flex items-center gap-1 text-xs font-bold text-[#1A1D2E] px-2.5 py-1 rounded-lg bg-black/[0.04] hover:bg-black/[0.08] transition-colors cursor-pointer"
        >
          <Info className="w-3.5 h-3.5 text-[#64748B]" />
          <span>{isRuleExpanded ? '收起调度规则' : '查看调度与插队机制'}</span>
          {isRuleExpanded ? <ChevronUp className="w-3.5 h-3.5" /> : <ChevronDown className="w-3.5 h-3.5" />}
        </button>
      </div>

      {/* Drama Priority Rank Chips */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 mt-3 pt-3 border-t border-black/[0.04]">
        {dramaPriorities.map((item) => {
          const isComplete = item.completedTasks >= item.totalTasks;
          const progressPct = Math.round((item.completedTasks / item.totalTasks) * 100);

          return (
            <div
              key={item.productionTaskId}
              className={`p-2.5 rounded-xl border transition-all ${
                item.priorityRank === 1
                  ? 'bg-amber-500/10 border-amber-500/30 shadow-2xs'
                  : 'bg-white border-black/[0.05]'
              }`}
            >
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-1.5">
                  <span
                    className={`w-4 h-4 rounded-full flex items-center justify-center text-[10px] font-extrabold ${
                      item.priorityRank === 1
                        ? 'bg-[#1A1D2E] text-[#DDFD00]'
                        : item.priorityRank === 2
                        ? 'bg-slate-700 text-white'
                        : 'bg-slate-200 text-slate-700'
                    }`}
                  >
                    #{item.priorityRank}
                  </span>
                  <div className="min-w-0 leading-tight">
                    <span className="block font-extrabold text-xs text-[#1A1D2E] truncate max-w-[110px]" title={item.dramaName}>
                      {item.dramaName}
                    </span>
                    <span className="block text-[9px] text-[#64748B] truncate max-w-[110px]" title={item.accountName}>
                      {item.accountName}
                    </span>
                  </div>
                </div>

                <span className="text-[10px] font-mono text-[#64748B]">
                  {formatPlannedDate(item.scheduledPublishTime)}
                </span>
              </div>

              {/* Progress & Supplementary Tag */}
              <div className="mt-2 flex items-center justify-between text-[10px] text-[#64748B]">
                <div className="flex items-center gap-1">
                  <span>进度:</span>
                  <strong className="font-mono text-[#1A1D2E]">
                    {item.completedTasks}/{item.totalTasks}
                  </strong>
                </div>

                {item.isSupplementing ? (
                  <span className="text-[9px] px-1.5 py-0.5 rounded bg-sky-100 text-sky-800 font-bold">
                    后补插回
                  </span>
                ) : isComplete ? (
                  <span className="text-emerald-700 font-bold flex items-center gap-0.5">
                    <CheckCircle2 className="w-2.5 h-2.5" /> 已就绪
                  </span>
                ) : (
                  <span className="font-mono">{progressPct}%</span>
                )}
              </div>

              <div className="mt-1.5 w-full h-1 bg-black/[0.06] rounded-full overflow-hidden">
                <div
                  className={`h-full rounded-full transition-all ${
                    item.priorityRank === 1 ? 'bg-amber-600' : 'bg-[#1A1D2E]'
                  }`}
                  style={{ width: `${progressPct}%` }}
                />
              </div>
            </div>
          );
        })}
      </div>

      {/* Expanded Scheduling Rules Detail */}
      {isRuleExpanded && (
        <div className="mt-3 p-3.5 bg-white rounded-xl border border-black/[0.06] space-y-2.5 text-xs text-[#64748B] animate-in fade-in duration-150">
          <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
            <div className="p-2.5 rounded-lg bg-slate-50 border border-slate-100">
              <strong className="text-[#1A1D2E] block mb-1">🎯 1. 账号×剧集优先级调度</strong>
              <p className="text-[11px] leading-relaxed">
                每个账号发布同一剧集都独立计算。按照【计划发布日期早 &gt; 进场生产早】排序，成片生成器优先保障高优先级发布计划尽快全量就绪。
              </p>
            </div>

            <div className="p-2.5 rounded-lg bg-slate-50 border border-slate-100">
              <strong className="text-[#1A1D2E] block mb-1">🔄 2. 高优先级后补任务动态插回</strong>
              <p className="text-[11px] leading-relaxed">
                若高优先级剧后续任务延迟提交，系统先执行次级剧集；当高优先级任务就绪时，<strong>不强制中断当前正在运行的任务</strong>，当前任务完成后立即优先处理。
              </p>
            </div>

            <div className="p-2.5 rounded-lg bg-amber-500/10 border border-amber-500/20 text-amber-950">
              <strong className="text-[#1A1D2E] block mb-1">⭐ 3. 模板最高导出优先权</strong>
              <p className="text-[11px] leading-relaxed">
                模板是后续批量成片的前置条件。模板草稿生成后进入导出队列时，享有最高导出优先权——当前导出完成后，<strong>下一条优先导出模板</strong>。
              </p>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
