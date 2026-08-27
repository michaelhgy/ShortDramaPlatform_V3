import React, { useState } from 'react';
import { 
  ScheduleTask, 
  AccountItem, 
  DramaItem, 
  ProductionSummary 
} from '../../types';
import { 
  DailyInsight, 
  ExploreAccount, 
  ExploreDrama 
} from '../../exploreTypes';
import { 
  EXPLORE_INSIGHTS, 
  EXPLORE_DRAMAS, 
  EXPLORE_ACCOUNTS 
} from '../../exploreMockData';
import { DecisionBriefing } from './DecisionBriefing';
import { HeatRadarDramaSection } from './HeatRadarDramaSection';
import { AccountMatrixRadar } from './AccountMatrixRadar';
import { PipelineCanvasSection } from './PipelineCanvasSection';
import { Sparkles, Layers, Zap, Info } from 'lucide-react';

interface WorkbenchExploreProps {
  tasks: ScheduleTask[];
  accounts: AccountItem[];
  dramas: DramaItem[];
  onAddDramaToAccount: (accountId: string, accountName: string) => void;
  onAddNewAccountSchedule: () => void;
  onEditTime: (task: ScheduleTask) => void;
  onDeleteTask: (taskId: string) => void;
  onOpenProduction: (task?: ScheduleTask) => void;
  onSaveNewSchedule: (newTasks: Omit<ScheduleTask, 'id'>[]) => void;
  showToast: (msg: string) => void;
  onScheduleFromDramaModal: (dramaId: string, accountId?: string) => void;
}

export const WorkbenchExplore: React.FC<WorkbenchExploreProps> = ({
  tasks,
  accounts,
  dramas,
  onAddDramaToAccount,
  onAddNewAccountSchedule,
  onEditTime,
  onDeleteTask,
  onOpenProduction,
  onSaveNewSchedule,
  showToast,
  onScheduleFromDramaModal,
}) => {
  const [insights, setInsights] = useState<DailyInsight[]>(EXPLORE_INSIGHTS);
  const [exploreDramas] = useState<ExploreDrama[]>(EXPLORE_DRAMAS);
  const [exploreAccounts] = useState<ExploreAccount[]>(EXPLORE_ACCOUNTS);

  const arrangedAccountIds = Array.from(new Set(tasks.map(t => t.accountId)));
  const totalYesterdayRevenue = exploreAccounts.reduce((acc, curr) => acc + curr.yesterdayRevenue, 0);
  const unassignedAccounts = exploreAccounts.filter(
    a => !arrangedAccountIds.includes(a.id) && a.manualStatus !== '暂停' && a.manualStatus !== '封号'
  );

  // 1. One-click Batch Smart Schedule
  const handleBatchAutoSchedule = () => {
    const newTasks: Omit<ScheduleTask, 'id'>[] = [];

    // Find accounts without tasks and match with top recommended dramas
    exploreAccounts.forEach((acc) => {
      if (!arrangedAccountIds.includes(acc.id) && acc.manualStatus === '正常') {
        const matchedDrama = exploreDramas.find(d => d.id === acc.recommendedDramaId) || exploreDramas[0];
        newTasks.push({
          accountId: acc.id,
          accountName: acc.name,
          dramaId: matchedDrama.id,
          dramaName: matchedDrama.name,
          coverUrl: matchedDrama.coverUrl,
          colorPlaceholder: matchedDrama.colorPlaceholder,
          publishTime: '今天 18:30',
          status: '待制作',
        });
      }
    });

    if (newTasks.length > 0) {
      onSaveNewSchedule(newTasks);
      showToast(`✨ AI 决策已生效：已为 ${newTasks.length} 个账号自动配对黄金档剧目！`);
    } else {
      showToast('当前所有活跃账号均已配置排期');
    }
  };

  // 2. Direct action trigger from insight cards
  const handleExecuteInsightAction = (insight: DailyInsight) => {
    if (insight.actionType === 'fill_unassigned') {
      handleBatchAutoSchedule();
    } else if (insight.actionType === 'schedule_drama' && insight.actionData?.dramaId) {
      onScheduleFromDramaModal(insight.actionData.dramaId, insight.actionData.accountId);
    } else {
      onAddNewAccountSchedule();
    }
  };

  // 3. Quick pair from Account card
  const handleQuickPairAccount = (account: ExploreAccount) => {
    const matchedDrama = exploreDramas.find(d => d.id === account.recommendedDramaId) || exploreDramas[0];
    onSaveNewSchedule([
      {
        accountId: account.id,
        accountName: account.name,
        dramaId: matchedDrama.id,
        dramaName: matchedDrama.name,
        coverUrl: matchedDrama.coverUrl,
        colorPlaceholder: matchedDrama.colorPlaceholder,
        publishTime: '今天 18:30',
        status: '待制作',
      },
    ]);
    showToast(`已为「${account.name}」快速安排《${matchedDrama.name}》`);
  };

  // 4. Schedule drama directly
  const handleScheduleDrama = (drama: ExploreDrama, targetTime = '今天 18:30', targetAccountId?: string) => {
    const acc = targetAccountId 
      ? exploreAccounts.find(a => a.id === targetAccountId)
      : exploreAccounts.find(a => a.id === drama.bestFitAccountId) || exploreAccounts[0];

    if (acc) {
      onSaveNewSchedule([
        {
          accountId: acc.id,
          accountName: acc.name,
          dramaId: drama.id,
          dramaName: drama.name,
          coverUrl: drama.coverUrl,
          colorPlaceholder: drama.colorPlaceholder,
          publishTime: targetTime,
          status: '待制作',
        },
      ]);
      showToast(`已将《${drama.name}》加入「${acc.name}」制作排期`);
    } else {
      onScheduleFromDramaModal(drama.id);
    }
  };

  // 5. Matrix schedule for hero drama across top 3 accounts
  const handleMatrixSchedule = (drama: ExploreDrama) => {
    const activeAccs = exploreAccounts.filter(a => a.manualStatus === '正常').slice(0, 3);
    const newTasks: Omit<ScheduleTask, 'id'>[] = activeAccs.map((acc, idx) => ({
      accountId: acc.id,
      accountName: acc.name,
      dramaId: drama.id,
      dramaName: drama.name,
      coverUrl: drama.coverUrl,
      colorPlaceholder: drama.colorPlaceholder,
      publishTime: idx === 0 ? '今天 18:30' : idx === 1 ? '今天 19:45' : '今天 21:00',
      status: '待制作',
    }));

    onSaveNewSchedule(newTasks);
    showToast(`🔥 矩阵排期成功：已为 ${newTasks.length} 个账号建立《${drama.name}》不同时间段阶梯排期！`);
  };

  const handleBatchPushToCapCut = () => {
    showToast('🚀 已向剪映工程流水线发送自动化去重与分镜渲染请求');
  };

  return (
    <div className="space-y-7 pb-12">
      {/* 1. TOP EXECUTIVE PULSE & DECISION BRIEFING */}
      <DecisionBriefing
        insights={insights}
        totalYesterdayRevenue={totalYesterdayRevenue}
        unassignedCount={unassignedAccounts.length}
        onExecuteInsightAction={handleExecuteInsightAction}
        onBatchAutoSchedule={handleBatchAutoSchedule}
      />

      {/* 2. CORE WORKBENCH SPATIAL GRID */}
      <div className="grid grid-cols-1 xl:grid-cols-12 gap-7 items-start">
        {/* Left Column (7 cols): Today's Production Pipeline + Account Matrix Radar */}
        <div className="xl:col-span-7 flex flex-col gap-7">
          {/* Today's Pipeline Canvas */}
          <PipelineCanvasSection
            tasks={tasks}
            onAddDramaToAccount={onAddDramaToAccount}
            onAddNewAccountSchedule={onAddNewAccountSchedule}
            onEditTime={onEditTime}
            onDeleteTask={onDeleteTask}
            onOpenProduction={onOpenProduction}
            onBatchPushToCapCut={handleBatchPushToCapCut}
          />

          {/* Account Matrix Radar */}
          <AccountMatrixRadar
            accounts={exploreAccounts}
            arrangedAccountIds={arrangedAccountIds}
            onScheduleAccount={(acc) => onScheduleFromDramaModal(acc.recommendedDramaId, acc.id)}
            onQuickPair={handleQuickPairAccount}
          />
        </div>

        {/* Right Column (5 cols): Heat Radar & Drama Opportunity Board */}
        <div className="xl:col-span-5 flex flex-col gap-7">
          <HeatRadarDramaSection
            dramas={exploreDramas}
            onScheduleDrama={handleScheduleDrama}
            onMatrixSchedule={handleMatrixSchedule}
          />
        </div>
      </div>
    </div>
  );
};
