import React, { useState } from 'react';
import { V3ContentAiRun, PlayContinuityMode } from '../../api/contentProduction';
import {
  Cpu,
  Clock,
  CheckCircle2,
  AlertTriangle,
  Loader2,
  Film,
  FolderOpen,
  ArrowUpRight,
  Layers
} from 'lucide-react';

interface RemixJobListProps {
  aiRuns: V3ContentAiRun[];
  onInspectRunInCreateTab: (runId: string) => void;
  showToast: (msg: string) => void;
}

export const RemixJobList: React.FC<RemixJobListProps> = ({
  aiRuns,
  onInspectRunInCreateTab,
  showToast
}) => {
  const [statusFilter, setStatusFilter] = useState<string>('ALL');
  const [strategyFilter, setStrategyFilter] = useState<'ALL' | PlayContinuityMode>('ALL');

  const filteredRuns = aiRuns.filter((run) => {
    if (statusFilter !== 'ALL' && run.status !== statusFilter) return false;
    if (strategyFilter !== 'ALL' && run.playStrategy !== strategyFilter) return false;
    return true;
  });

  return (
    <div className="space-y-5">
      {/* Filter Header */}
      <div className="bg-white rounded-2xl border border-slate-200/90 p-4 sm:p-5 shadow-xs flex flex-wrap items-center justify-between gap-4">
        <div>
          <h3 className="text-sm font-extrabold text-slate-900">
            二创生成任务队列 (v3_content_ai_runs)
          </h3>
          <p className="text-xs text-slate-500 mt-0.5">
            显示原剧扫描、高光判断、连续/跳集规划、FFmpeg合成与技术质检的真实任务状态
          </p>
        </div>

        <div className="flex flex-wrap items-center gap-2.5 text-xs">
          <select
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value)}
            className="px-3 py-1.5 rounded-xl border border-slate-200 bg-slate-50 font-semibold text-slate-800"
          >
            <option value="ALL">全部任务状态 ({aiRuns.length})</option>
            <option value="running">执行中</option>
            <option value="completed">全部完成</option>
            <option value="partial_failed">部分质检异常</option>
            <option value="failed">执行失败</option>
          </select>

          <select
            value={strategyFilter}
            onChange={(e) => setStrategyFilter(e.target.value as 'ALL' | PlayContinuityMode)}
            className="px-3 py-1.5 rounded-xl border border-slate-200 bg-slate-50 font-semibold text-slate-800"
          >
            <option value="ALL">全部播放策略</option>
            <option value="跳集播放">跳集播放</option>
            <option value="连续播放">连续播放</option>
          </select>
        </div>
      </div>

      {/* Job Cards */}
      <div className="space-y-4">
        {filteredRuns.map((run) => {
          const qualifiedCount = run.results.filter((r) => r.techStatus === '合格').length;
          const failedCount = run.results.filter((r) => r.techStatus === '不合格').length;

          return (
            <div
              key={run.id}
              className="bg-white rounded-2xl border border-slate-200/90 shadow-xs overflow-hidden"
            >
              <div className="px-5 py-4 border-b border-slate-100 bg-slate-50/60 flex flex-wrap items-center justify-between gap-3">
                <div className="flex flex-wrap items-center gap-2.5">
                  <span className="px-2.5 py-1 rounded-lg bg-[#1A1D2E] text-[#DDFD00] font-mono text-xs font-extrabold">
                    {run.jobCode}
                  </span>
                  <span className="text-sm font-extrabold text-slate-900">
                    《{run.dramaTitle}》
                  </span>
                  <span className="px-2 py-0.5 rounded-md bg-indigo-50 text-indigo-700 border border-indigo-200 text-xs font-bold">
                    {run.playStrategies?.join(' + ') || run.playStrategy}
                  </span>
                  <span className="text-xs text-slate-500 font-mono">
                    时长范围: {run.durationRangeMin[0]}—{run.durationRangeMin[1]}分钟 · 目标 {run.targetCount} 条
                  </span>

                  {run.status === 'running' && (
                    <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-md bg-indigo-600 text-white text-xs font-bold">
                      <Loader2 className="w-3 h-3 animate-spin" /> 流水线执行中
                    </span>
                  )}
                  {run.status === 'partial_failed' && (
                    <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-md bg-amber-100 text-amber-900 border border-amber-300 text-xs font-bold">
                      <AlertTriangle className="w-3 h-3 text-amber-600" /> 部分质检拦截 ({qualifiedCount}合格 / {failedCount}异常)
                    </span>
                  )}
                  {run.status === 'completed' && (
                    <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-md bg-emerald-100 text-emerald-800 text-xs font-bold">
                      <CheckCircle2 className="w-3 h-3" /> 已完成 {run.results.length}/{run.targetCount} 条
                    </span>
                  )}
                  {run.status === 'failed' && (
                    <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-md bg-rose-100 text-rose-800 text-xs font-bold">
                      <AlertTriangle className="w-3 h-3" /> 执行失败
                    </span>
                  )}
                </div>

                <div className="flex items-center gap-2">
                  <button
                    type="button"
                    onClick={() => onInspectRunInCreateTab(run.id)}
                    className="px-3.5 py-1.5 rounded-xl bg-[#1A1D2E] hover:bg-black text-white text-xs font-bold flex items-center gap-1.5 cursor-pointer"
                  >
                    <span>查看流水线与批量结果 ({run.results.length})</span>
                    <ArrowUpRight className="w-3.5 h-3.5 text-[#DDFD00]" />
                  </button>
                </div>
              </div>

              <div className="p-5 space-y-4">
                {/* Metadata Row */}
                <div className="grid grid-cols-1 md:grid-cols-4 gap-3 text-xs">
                  <div className="p-2.5 rounded-xl bg-slate-50 border border-slate-200/70">
                    <span className="text-slate-400 text-[11px] block">原片目录与状态</span>
                    <span className="font-bold text-slate-800 block truncate" title={run.sourceDirectory}>
                      {run.sourceFilesStatus} · {run.sourceDirectory}
                    </span>
                  </div>
                  <div className="p-2.5 rounded-xl bg-slate-50 border border-slate-200/70">
                    <span className="text-slate-400 text-[11px] block">套用通版模板</span>
                    <span className="font-bold text-slate-800">
                      {run.templateName} ({run.templateVersion})
                    </span>
                  </div>
                  <div className="p-2.5 rounded-xl bg-slate-50 border border-slate-200/70">
                    <span className="text-slate-400 text-[11px] block">规划模型标识 (Model ID)</span>
                    <span className="font-mono font-bold text-indigo-700">
                      {run.modelId}
                    </span>
                  </div>
                  <div className="p-2.5 rounded-xl bg-slate-50 border border-slate-200/70">
                    <span className="text-slate-400 text-[11px] block">任务创建时间</span>
                    <span className="font-mono font-bold text-slate-800">
                      {run.createdAt}
                    </span>
                  </div>
                </div>

                {/* 7-Step Compact Strip */}
                <div className="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-7 gap-2">
                  {run.pipelineSteps.map((step, idx) => {
                    const badgeStyle =
                      step.status === 'completed'
                        ? 'bg-emerald-50 border-emerald-200 text-emerald-900'
                        : step.status === 'running'
                        ? 'bg-indigo-50 border-indigo-300 text-indigo-950 ring-1 ring-indigo-400'
                        : step.status === 'failed'
                        ? 'bg-rose-50 border-rose-300 text-rose-900'
                        : 'bg-slate-50 border-slate-200 text-slate-400';

                    return (
                      <div
                        key={step.key}
                        className={`p-2.5 rounded-xl border text-xs flex flex-col justify-between ${badgeStyle}`}
                      >
                        <div className="flex items-center justify-between font-bold">
                          <span>{idx + 1}. {step.label}</span>
                        </div>
                        <div className="mt-1.5 text-[11px] font-mono opacity-85">
                          {step.durationText}
                        </div>
                        {(step.status === 'running' || step.status === 'failed' || step.status === 'completed') && step.detailText && (
                          <div className="mt-1 text-[11px] leading-snug opacity-90 break-all">
                            {step.status === 'failed' && step.errorReason ? step.errorReason : step.detailText}
                          </div>
                        )}
                      </div>
                    );
                  })}
                </div>

                {run.error && (
                  <div className="p-3 rounded-xl bg-rose-50 border border-rose-200 text-xs text-rose-900 break-all">
                    <span className="font-bold">失败原因：</span>{run.error}
                  </div>
                )}
                {((run.planNotes?.length ?? 0) > 0 || (run.synthFailures?.length ?? 0) > 0) && (
                  <div className="p-3 rounded-xl bg-amber-50 border border-amber-200 text-xs text-amber-900 space-y-1">
                    {run.planNotes?.map((note) => <div key={note}>{note}</div>)}
                    {run.synthFailures?.map((note) => <div key={note} className="break-all">合成失败 · {note}</div>)}
                  </div>
                )}
                {(run.modelCalls?.length ?? 0) > 0 && (() => {
                  const sum = (key: string) => (run.modelCalls ?? []).reduce((total, call) => total + (Number(call.usage?.[key]) || 0), 0);
                  return (
                    <div className="text-[11px] text-slate-500 font-mono">
                      模型调用 {run.modelCalls!.length} 次 · 输入 {sum('input_tokens').toLocaleString()} tokens · 输出 {sum('output_tokens').toLocaleString()} tokens
                      {run.methodVersion ? ` · 方法版本 ${run.methodVersion}` : ''}
                    </div>
                  );
                })()}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
};
