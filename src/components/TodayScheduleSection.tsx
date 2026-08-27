import React from 'react';
import { ScheduleTask, DramaProductionStatus } from '../types';
import { DramaCover } from './DramaCover';
import { 
  Plus, 
  Clock, 
  Trash2, 
  ChevronRight,
  Sparkles,
  Layers,
  CheckCircle2
} from 'lucide-react';

interface TodayScheduleSectionProps {
  tasks: ScheduleTask[];
  onAddDramaToAccount: (accountId: string, accountName: string) => void;
  onAddNewAccountSchedule: () => void;
  onEditTime: (task: ScheduleTask) => void;
  onDeleteTask: (taskId: string) => void;
  onOpenProduction: (task?: ScheduleTask) => void;
}

export const TodayScheduleSection: React.FC<TodayScheduleSectionProps> = ({
  tasks,
  onAddDramaToAccount,
  onAddNewAccountSchedule,
  onEditTime,
  onDeleteTask,
  onOpenProduction,
}) => {
  // Group tasks by account
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

  const getStatusBadge = (status: DramaProductionStatus) => {
    switch (status) {
      case '制作中':
        return (
          <span className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full text-[10px] font-semibold bg-blue-50/90 text-blue-700 border border-blue-200/60 shadow-2xs">
            <span className="w-1.5 h-1.5 rounded-full bg-blue-600 animate-pulse" />
            制作中
          </span>
        );
      case '已完成':
        return (
          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-semibold bg-emerald-50/90 text-emerald-700 border border-emerald-200/60 shadow-2xs">
            <CheckCircle2 className="w-2.5 h-2.5" />
            剪映就绪
          </span>
        );
      case '异常':
        return (
          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-semibold bg-rose-50/90 text-rose-700 border border-rose-200/60 shadow-2xs">
            异常
          </span>
        );
      default:
        return (
          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-semibold bg-slate-100 text-slate-600 border border-slate-200/50">
            待制作
          </span>
        );
    }
  };

  return (
    <section className="glass-panel rounded-3xl p-6 sm:p-7 transition-all flex flex-col justify-between min-h-[580px]">
      <div>
        {/* Main Section Header with Strong Typography and Clear Metrics */}
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 pb-5 border-b border-black/[0.05]">
          <div>
            <div className="flex items-center gap-3">
              <h2 className="text-xl font-extrabold text-[#1A1D2E] tracking-tight">
                今日安排
              </h2>
              <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full bg-[#1A1D2E]/[0.06] text-[#1A1D2E] text-xs font-bold">
                <Layers className="w-3 h-3 text-[#1A1D2E]/70" />
                <span>{tasks.length} 项制作安排</span>
                <span className="text-[#64748B] font-medium">· {groupKeys.length} 个账号</span>
              </span>
            </div>
            <p className="text-xs text-[#64748B] mt-1 font-medium leading-relaxed">
              按账号组织今日短剧制作任务与发布时间，一键流水线流转至剪映与小V猫
            </p>
          </div>

          {/* Primary Section Action */}
          <button
            id="btn-add-account-schedule"
            onClick={onAddNewAccountSchedule}
            className="flex items-center gap-1.5 px-4 py-2 rounded-xl bg-[#1A1D2E] hover:bg-black text-[#DDFD00] text-xs font-bold transition-all shadow-xs active:scale-98 shrink-0 cursor-pointer"
          >
            <Plus className="w-4 h-4 stroke-[2.5]" />
            <span>安排账号</span>
          </button>
        </div>

        {/* Account Groups Container */}
        <div className="mt-5 space-y-5">
          {groupKeys.length === 0 ? (
            <div className="py-16 text-center rounded-2xl border border-dashed border-black/[0.1] bg-white/40">
              <Sparkles className="w-8 h-8 mx-auto text-slate-400 mb-2" />
              <p className="text-sm font-bold text-slate-700">今天尚未安排任何账号与剧集</p>
              <p className="text-xs text-slate-500 mt-1">可从右侧「昨日账号」或「近期剧集」一键发起今日排期</p>
              <button
                onClick={onAddNewAccountSchedule}
                className="mt-4 px-4 py-2 rounded-xl bg-[#1A1D2E] text-[#DDFD00] text-xs font-bold hover:bg-black"
              >
                立即安排今天
              </button>
            </div>
          ) : (
            groupKeys.map((accId) => {
              const group = accountGroups[accId];
              return (
                <div
                  key={accId}
                  className="rounded-2xl p-4 sm:p-5 bg-gradient-to-b from-white/90 to-white/60 border border-black/[0.05] shadow-[0_2px_12px_-2px_rgba(26,29,46,0.03)] hover:border-black/[0.09] transition-all"
                >
                  {/* Account Header Line: Strong visual hierarchy */}
                  <div className="flex items-center justify-between pb-3 mb-3.5 border-b border-black/[0.04]">
                    <div className="flex items-center gap-2.5">
                      <div className="w-2 h-4 rounded-full bg-[#1A1D2E]" />
                      <span className="font-extrabold text-[15px] text-[#1A1D2E] tracking-tight">
                        {group.accountName}
                      </span>
                      <span className="text-[11px] font-semibold text-[#64748B] bg-black/[0.03] px-2 py-0.5 rounded-md">
                        微信视频号
                      </span>
                      <span className="text-[11px] text-[#64748B]">
                        ({group.tasks.length} 部排期)
                      </span>
                    </div>

                    {/* Quick Add Drama to this Account */}
                    <button
                      onClick={() => onAddDramaToAccount(accId, group.accountName)}
                      className="flex items-center gap-1 px-2.5 py-1 rounded-lg text-xs font-semibold text-[#64748B] hover:text-[#1A1D2E] hover:bg-black/[0.04] transition-colors cursor-pointer"
                    >
                      <Plus className="w-3.5 h-3.5" />
                      <span>添加剧集</span>
                    </button>
                  </div>

                  {/* Drama Tasks Grid for this Account */}
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                    {group.tasks.map((task) => (
                      <div
                        key={task.id}
                        className="group relative p-3 rounded-xl bg-white/95 border border-black/[0.06] hover:border-black/[0.14] hover:shadow-md transition-all flex items-center gap-3.5"
                      >
                        {/* Vertical Poster Cover */}
                        <DramaCover
                          name={task.dramaName}
                          coverUrl={task.coverUrl}
                          colorPlaceholder={task.colorPlaceholder}
                          size="md"
                        />

                        {/* Details */}
                        <div className="flex-1 min-w-0">
                          <div className="flex items-start justify-between gap-1.5">
                            <h4 className="font-bold text-xs text-[#1A1D2E] truncate leading-tight group-hover:text-black">
                              《{task.dramaName}》
                            </h4>
                            {/* Delete action button */}
                            <button
                              onClick={() => onDeleteTask(task.id)}
                              title="删除此项今日安排"
                              className="text-slate-300 hover:text-rose-600 p-0.5 rounded transition-colors opacity-0 group-hover:opacity-100 cursor-pointer"
                            >
                              <Trash2 className="w-3.5 h-3.5" />
                            </button>
                          </div>

                          {/* Time & Status line */}
                          <div className="mt-2 flex items-center gap-2 flex-wrap">
                            <button
                              onClick={() => onEditTime(task)}
                              title="点击修改发布时间"
                              className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded-lg bg-[#F8FAFC] hover:bg-[#EEF2F6] text-[#1A1D2E] text-[11px] font-bold transition-all border border-black/[0.07] cursor-pointer"
                            >
                              <Clock className="w-3 h-3 text-[#64748B]" />
                              <span>{task.publishTime}</span>
                            </button>

                            <div>
                              {getStatusBadge(task.status)}
                            </div>
                          </div>

                          {/* Action Footer */}
                          <div className="mt-2 flex items-center justify-end">
                            <button
                              onClick={() => onOpenProduction(task)}
                              className="text-[11px] font-bold text-[#64748B] hover:text-[#1A1D2E] inline-flex items-center gap-0.5 transition-colors cursor-pointer"
                            >
                              <span>去生产</span>
                              <ChevronRight className="w-3 h-3" />
                            </button>
                          </div>
                        </div>
                      </div>
                    ))}

                    {/* Add Drama Empty Slot */}
                    <button
                      onClick={() => onAddDramaToAccount(accId, group.accountName)}
                      className="p-3 rounded-xl border border-dashed border-black/[0.12] hover:border-black/[0.28] hover:bg-white/80 flex items-center justify-center gap-2 text-xs font-semibold text-[#64748B] hover:text-[#1A1D2E] transition-all min-h-[76px] cursor-pointer"
                    >
                      <Plus className="w-4 h-4" />
                      <span>为该账号添加剧集</span>
                    </button>
                  </div>
                </div>
              );
            })
          )}
        </div>
      </div>

      {/* Subtle workspace footer info bar */}
      <div className="pt-5 mt-4 border-t border-black/[0.04] flex items-center justify-between text-xs text-[#64748B]">
        <div className="flex items-center gap-2">
          <span className="w-2 h-2 rounded-full bg-emerald-500" />
          <span>剪映自动化桥接已连接 · 视频号定时发布就绪</span>
        </div>
        <span className="text-[11px] text-slate-400">今日工作流自动保存</span>
      </div>
    </section>
  );
};
