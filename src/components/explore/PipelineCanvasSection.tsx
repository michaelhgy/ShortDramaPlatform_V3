import React from 'react';
import { ScheduleTask, DramaProductionStatus } from '../../types';
import { DramaCover } from '../DramaCover';
import { 
  Clock, 
  Trash2, 
  ChevronRight, 
  Sparkles, 
  Send, 
  Film, 
  CheckCircle2, 
  Layers, 
  Plus, 
  ArrowUpRight,
  ExternalLink
} from 'lucide-react';

interface PipelineCanvasSectionProps {
  tasks: ScheduleTask[];
  onAddDramaToAccount: (accountId: string, accountName: string) => void;
  onAddNewAccountSchedule: () => void;
  onEditTime: (task: ScheduleTask) => void;
  onDeleteTask: (taskId: string) => void;
  onOpenProduction: (task?: ScheduleTask) => void;
  onBatchPushToCapCut: () => void;
}

export const PipelineCanvasSection: React.FC<PipelineCanvasSectionProps> = ({
  tasks,
  onAddDramaToAccount,
  onAddNewAccountSchedule,
  onEditTime,
  onDeleteTask,
  onOpenProduction,
  onBatchPushToCapCut,
}) => {
  // Group by time windows
  const noonTasks = tasks.filter(t => t.publishTime.includes('12:') || t.publishTime.includes('09:'));
  const primeTasks = tasks.filter(t => t.publishTime.includes('18:') || t.publishTime.includes('19:') || t.publishTime.includes('20:'));
  const lateTasks = tasks.filter(t => t.publishTime.includes('21:') || t.publishTime.includes('22:') || t.publishTime.includes('23:'));

  const getStatusBadge = (status: DramaProductionStatus) => {
    switch (status) {
      case '制作中':
        return (
          <span className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full text-[10px] font-semibold bg-blue-50 text-blue-700 border border-blue-200/60 shadow-2xs">
            <span className="w-1.5 h-1.5 rounded-full bg-blue-600 animate-pulse" />
            剪映切片渲染中
          </span>
        );
      case '已完成':
        return (
          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-semibold bg-emerald-50 text-emerald-700 border border-emerald-200/60 shadow-2xs">
            <CheckCircle2 className="w-2.5 h-2.5" />
            小V猫推送就绪
          </span>
        );
      case '异常':
        return (
          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-semibold bg-rose-50 text-rose-700 border border-rose-200/60 shadow-2xs">
            渲染异常
          </span>
        );
      default:
        return (
          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-semibold bg-slate-100 text-slate-600 border border-slate-200/50">
            待生产排队
          </span>
        );
    }
  };

  // Group by account for structured view
  const accountGroups: Record<string, { accountName: string; tasks: ScheduleTask[] }> = {};
  tasks.forEach((task) => {
    if (!accountGroups[task.accountId]) {
      accountGroups[task.accountId] = {
        accountName: task.accountName,
        tasks: [],
      };
    }
    accountGroups[task.accountId].tasks.push(task);
  });

  const groupKeys = Object.keys(accountGroups);

  return (
    <section className="rounded-3xl bg-white/90 border border-white/90 p-5 sm:p-6 shadow-[0_12px_32px_-4px_rgba(26,29,46,0.05)] backdrop-blur-xl flex flex-col justify-between">
      <div>
        {/* Header with quick batch actions */}
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 pb-4 border-b border-black/[0.05]">
          <div>
            <div className="flex items-center gap-3">
              <div className="w-2.5 h-4 rounded-full bg-[#1A1D2E]" />
              <h3 className="font-extrabold text-base sm:text-lg text-[#1A1D2E] tracking-tight">
                今日制作与发布流水线
              </h3>
              <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full bg-[#1A1D2E]/[0.06] text-[#1A1D2E] text-xs font-bold">
                <Layers className="w-3 h-3 text-[#1A1D2E]/70" />
                <span>{tasks.length} 项排期</span>
                <span className="text-[#64748B]">· {groupKeys.length} 个账号</span>
              </span>
            </div>
            <p className="text-xs text-[#64748B] font-medium mt-0.5">
              一键贯通「自动生成 → 剪映工程渲染 → 小V猫定时发布」全链路
            </p>
          </div>

          {/* Action buttons */}
          <div className="flex items-center gap-2">
            <button
              onClick={onBatchPushToCapCut}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-xl bg-blue-50 hover:bg-blue-100 text-blue-700 border border-blue-200/60 text-xs font-bold transition-all cursor-pointer"
            >
              <Film className="w-3.5 h-3.5 text-blue-600" />
              <span>一键推送到剪映</span>
            </button>

            <button
              id="btn-explore-add-schedule"
              onClick={onAddNewAccountSchedule}
              className="flex items-center gap-1.5 px-3.5 py-1.5 rounded-xl bg-[#1A1D2E] hover:bg-black text-[#DDFD00] text-xs font-bold transition-all shadow-xs active:scale-98 cursor-pointer"
            >
              <Plus className="w-4 h-4 stroke-[2.5]" />
              <span>添加排期</span>
            </button>
          </div>
        </div>

        {/* Time Windows Distribution Bar */}
        <div className="grid grid-cols-3 gap-2.5 mt-4">
          <div className="p-2.5 rounded-xl bg-[#F8FAFC] border border-black/[0.04] flex items-center justify-between">
            <div>
              <span className="text-[10px] font-bold text-slate-500 block">午间轻娱档 (12:00)</span>
              <span className="text-xs font-black text-[#1A1D2E]">{noonTasks.length} 条已排</span>
            </div>
            <span className="text-[10px] font-semibold text-emerald-700 bg-emerald-50 px-1.5 py-0.5 rounded">热度高</span>
          </div>

          <div className="p-2.5 rounded-xl bg-gradient-to-r from-amber-50/60 to-white border border-amber-200/60 flex items-center justify-between">
            <div>
              <span className="text-[10px] font-extrabold text-amber-900 block">晚黄金峰值 (18:30-21:00)</span>
              <span className="text-xs font-black text-[#1A1D2E]">{primeTasks.length} 条已排 (主攻)</span>
            </div>
            <span className="text-[10px] font-black text-rose-700 bg-rose-100 px-1.5 py-0.5 rounded animate-pulse">峰值流量</span>
          </div>

          <div className="p-2.5 rounded-xl bg-[#F8FAFC] border border-black/[0.04] flex items-center justify-between">
            <div>
              <span className="text-[10px] font-bold text-slate-500 block">深夜长尾档 (21:30+)</span>
              <span className="text-xs font-black text-[#1A1D2E]">{lateTasks.length} 条已排</span>
            </div>
            <span className="text-[10px] font-semibold text-blue-700 bg-blue-50 px-1.5 py-0.5 rounded">情感长尾</span>
          </div>
        </div>

        {/* Grouped Account Task Cards */}
        <div className="mt-4 space-y-4">
          {groupKeys.length === 0 ? (
            <div className="py-12 text-center rounded-2xl border border-dashed border-black/[0.1] bg-white/40">
              <Sparkles className="w-7 h-7 mx-auto text-slate-400 mb-2" />
              <p className="text-xs font-bold text-slate-700">今日暂无制作排期</p>
              <button
                onClick={onAddNewAccountSchedule}
                className="mt-3 px-3 py-1.5 rounded-xl bg-[#1A1D2E] text-[#DDFD00] text-xs font-bold"
              >
                安排今天任务
              </button>
            </div>
          ) : (
            groupKeys.map((accId) => {
              const group = accountGroups[accId];
              return (
                <div
                  key={accId}
                  className="rounded-2xl p-4 bg-gradient-to-b from-white to-white/70 border border-black/[0.05] shadow-[0_2px_10px_rgba(26,29,46,0.02)]"
                >
                  {/* Account Line */}
                  <div className="flex items-center justify-between pb-2.5 mb-3 border-b border-black/[0.04]">
                    <div className="flex items-center gap-2">
                      <span className="font-extrabold text-xs sm:text-[13px] text-[#1A1D2E]">
                        {group.accountName}
                      </span>
                      <span className="text-[10px] font-semibold text-[#64748B] bg-black/[0.03] px-1.5 py-0.2 rounded">
                        视频号
                      </span>
                      <span className="text-[10px] text-slate-400">
                        ({group.tasks.length} 项排期)
                      </span>
                    </div>

                    <button
                      onClick={() => onAddDramaToAccount(accId, group.accountName)}
                      className="flex items-center gap-1 text-[11px] font-bold text-[#64748B] hover:text-[#1A1D2E] hover:bg-black/[0.04] px-2 py-0.5 rounded-lg transition-colors cursor-pointer"
                    >
                      <Plus className="w-3 h-3" />
                      <span>添加剧集</span>
                    </button>
                  </div>

                  {/* Tasks List */}
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-2.5">
                    {group.tasks.map((task) => (
                      <div
                        key={task.id}
                        className="group relative p-2.5 rounded-xl bg-white border border-black/[0.05] hover:border-black/[0.12] hover:shadow-sm transition-all flex items-center gap-3"
                      >
                        <DramaCover
                          name={task.dramaName}
                          coverUrl={task.coverUrl}
                          colorPlaceholder={task.colorPlaceholder}
                          size="sm"
                          className="w-11 h-15 rounded-lg shrink-0"
                        />

                        <div className="flex-1 min-w-0">
                          <div className="flex items-start justify-between gap-1">
                            <h4 className="font-bold text-xs text-[#1A1D2E] truncate">
                              《{task.dramaName}》
                            </h4>
                            <button
                              onClick={() => onDeleteTask(task.id)}
                              className="text-slate-300 hover:text-rose-600 p-0.5 rounded opacity-0 group-hover:opacity-100 transition-colors cursor-pointer"
                            >
                              <Trash2 className="w-3 h-3" />
                            </button>
                          </div>

                          <div className="mt-1.5 flex items-center gap-1.5 flex-wrap">
                            <button
                              onClick={() => onEditTime(task)}
                              title="点击修改发布时间"
                              className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded bg-[#F8FAFC] hover:bg-slate-200 text-[#1A1D2E] text-[10px] font-bold border border-black/[0.06] cursor-pointer"
                            >
                              <Clock className="w-2.5 h-2.5 text-[#64748B]" />
                              <span>{task.publishTime}</span>
                            </button>
                            {getStatusBadge(task.status)}
                          </div>

                          <div className="mt-1.5 flex items-center justify-end">
                            <button
                              onClick={() => onOpenProduction(task)}
                              className="text-[10px] font-bold text-[#64748B] hover:text-[#1A1D2E] flex items-center gap-0.5 cursor-pointer"
                            >
                              <span>生产看板</span>
                              <ChevronRight className="w-2.5 h-2.5" />
                            </button>
                          </div>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              );
            })
          )}
        </div>
      </div>

      {/* Footer Info */}
      <div className="mt-4 pt-3 border-t border-black/[0.04] flex items-center justify-between text-[11px] text-[#64748B]">
        <div className="flex items-center gap-2">
          <span className="w-2 h-2 rounded-full bg-emerald-500" />
          <span>小V猫定时发布通道就绪 · 剪映工程模板自动匹配</span>
        </div>
        <span className="text-slate-400">已启用自动化排期校验</span>
      </div>
    </section>
  );
};
