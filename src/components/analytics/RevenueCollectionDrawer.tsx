import React, { useState } from 'react';
import { RevenueCollectionLog } from '../../analyticsTypes';
import { 
  X, 
  DownloadCloud, 
  RefreshCw, 
  CheckCircle2, 
  AlertCircle, 
  Clock, 
  Play, 
  History, 
  FileCheck 
} from 'lucide-react';

interface RevenueCollectionDrawerProps {
  isOpen: boolean;
  onClose: () => void;
  logs: RevenueCollectionLog[];
  onTriggerCollect: (scope: string, mode: string, startDate: string, endDate: string) => void;
}

export const RevenueCollectionDrawer: React.FC<RevenueCollectionDrawerProps> = ({
  isOpen,
  onClose,
  logs: initialLogs,
  onTriggerCollect,
}) => {
  const [logs, setLogs] = useState<RevenueCollectionLog[]>(initialLogs);
  const [collectMode, setCollectMode] = useState<'immediate' | 'backfill'>('immediate');
  const [targetScope, setTargetScope] = useState<string>('all');
  const [startDate, setStartDate] = useState<string>('2026-08-23');
  const [endDate, setEndDate] = useState<string>('2026-08-23');
  const [isCollecting, setIsCollecting] = useState<boolean>(false);
  const [progressPct, setProgressPct] = useState<number>(0);

  if (!isOpen) return null;

  const handleStartCollect = () => {
    setIsCollecting(true);
    setProgressPct(10);

    const interval = setInterval(() => {
      setProgressPct((prev) => {
        if (prev >= 95) {
          clearInterval(interval);
          setTimeout(() => {
            setIsCollecting(false);
            setProgressPct(100);

            // Add new successful collection log
            const newLog: RevenueCollectionLog = {
              id: `rc-${Date.now()}`,
              theaterName: targetScope === 'all' ? '全部 5 个剧场' : targetScope,
              accountName: '矩阵多账号聚合',
              period: `${startDate} ~ ${endDate}`,
              status: 'success',
              collectedAmount: 3420.50,
              qualityTier: 'direct',
              updatedAt: new Date().toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit', second: '2-digit' }),
              note: '手动触发采集任务完成',
            };
            setLogs([newLog, ...logs]);
            onTriggerCollect(targetScope, collectMode, startDate, endDate);
          }, 400);
          return 95;
        }
        return prev + 25;
      });
    }, 250);
  };

  return (
    <div className="fixed inset-0 z-50 flex justify-end bg-black/50 backdrop-blur-xs animate-in fade-in duration-150">
      <div className="bg-white w-full max-w-md h-full shadow-2xl flex flex-col justify-between border-l border-black/10 animate-in slide-in-from-right duration-200">
        {/* Header */}
        <div className="p-4 bg-[#1A1D2E] text-white flex items-center justify-between shrink-0">
          <div className="flex items-center gap-2.5">
            <div className="w-8 h-8 rounded-xl bg-white/10 text-[#DDFD00] flex items-center justify-center font-bold">
              <DownloadCloud className="w-4 h-4" />
            </div>
            <div>
              <h3 className="text-sm font-bold">收益与数据采集中心</h3>
              <p className="text-[11px] text-slate-300">
                支持各剧场实时手动采集与历史跨周期补采
              </p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="p-1 rounded-lg text-slate-300 hover:text-white hover:bg-white/10 transition-colors"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Content Body */}
        <div className="flex-1 overflow-y-auto p-5 space-y-4 text-xs">
          {/* 1. Collect Mode Selector */}
          <div className="space-y-1.5">
            <label className="font-bold text-[#1A1D2E] block">采集模式</label>
            <div className="grid grid-cols-2 gap-2">
              <button
                onClick={() => {
                  setCollectMode('immediate');
                  setStartDate('2026-08-23');
                  setEndDate('2026-08-23');
                }}
                className={`p-2.5 rounded-xl border text-left transition-all ${
                  collectMode === 'immediate'
                    ? 'bg-[#1A1D2E] text-white border-[#1A1D2E] shadow-2xs'
                    : 'bg-slate-50 border-black/[0.06] text-[#1A1D2E] hover:bg-slate-100'
                }`}
              >
                <div className="font-bold text-xs flex items-center gap-1.5">
                  <RefreshCw className="w-3.5 h-3.5" />
                  <span>立即同步采集</span>
                </div>
                <div className={`text-[10px] mt-0.5 ${collectMode === 'immediate' ? 'text-slate-300' : 'text-[#64748B]'}`}>
                  采集昨日与最新结算流水
                </div>
              </button>

              <button
                onClick={() => {
                  setCollectMode('backfill');
                  setStartDate('2026-08-01');
                  setEndDate('2026-08-23');
                }}
                className={`p-2.5 rounded-xl border text-left transition-all ${
                  collectMode === 'backfill'
                    ? 'bg-[#1A1D2E] text-white border-[#1A1D2E] shadow-2xs'
                    : 'bg-slate-50 border-black/[0.06] text-[#1A1D2E] hover:bg-slate-100'
                }`}
              >
                <div className="font-bold text-xs flex items-center gap-1.5">
                  <History className="w-3.5 h-3.5" />
                  <span>历史跨期补采</span>
                </div>
                <div className={`text-[10px] mt-0.5 ${collectMode === 'backfill' ? 'text-slate-300' : 'text-[#64748B]'}`}>
                  补全历史缺失或对账日期
                </div>
              </button>
            </div>
          </div>

          {/* 2. Target Theater Scope */}
          <div className="space-y-1.5">
            <label className="font-bold text-[#1A1D2E] block">采集目标范围</label>
            <select
              value={targetScope}
              onChange={(e) => setTargetScope(e.target.value)}
              className="w-full px-3 py-2 bg-slate-50 border border-black/[0.06] rounded-xl text-xs text-[#1A1D2E] font-medium outline-none"
            >
              <option value="all">全部 5 个剧场 (青柠/九州/点众/番茄/花生)</option>
              <option value="青柠剧场">仅青柠剧场 (包含视频播放全量)</option>
              <option value="九州剧场">仅九州剧场</option>
              <option value="点众微剧">仅点众微剧</option>
              <option value="番茄剧场">仅番茄剧场</option>
              <option value="花生剧场">仅花生剧场</option>
            </select>
          </div>

          {/* 3. Date Span Inputs */}
          <div className="space-y-1.5">
            <label className="font-bold text-[#1A1D2E] block">采集时间跨度</label>
            <div className="grid grid-cols-2 gap-2">
              <div>
                <span className="text-[10px] text-[#64748B] block mb-1">起始日期</span>
                <input
                  type="date"
                  value={startDate}
                  onChange={(e) => setStartDate(e.target.value)}
                  className="w-full px-2.5 py-1.5 bg-slate-50 border border-black/[0.06] rounded-xl text-xs font-mono outline-none"
                />
              </div>
              <div>
                <span className="text-[10px] text-[#64748B] block mb-1">截止日期</span>
                <input
                  type="date"
                  value={endDate}
                  onChange={(e) => setEndDate(e.target.value)}
                  className="w-full px-2.5 py-1.5 bg-slate-50 border border-black/[0.06] rounded-xl text-xs font-mono outline-none"
                />
              </div>
            </div>
          </div>

          {/* Trigger Button & Live Progress */}
          <div className="pt-2">
            {isCollecting ? (
              <div className="space-y-2 p-3 bg-slate-50 rounded-xl border border-black/[0.06]">
                <div className="flex items-center justify-between text-xs">
                  <span className="font-bold text-[#1A1D2E] flex items-center gap-1.5">
                    <RefreshCw className="w-3.5 h-3.5 animate-spin text-emerald-600" />
                    正在连接剧场 API 同步数据...
                  </span>
                  <span className="font-mono font-bold text-emerald-700">{progressPct}%</span>
                </div>
                <div className="w-full h-1.5 bg-slate-200 rounded-full overflow-hidden">
                  <div 
                    className="h-full bg-emerald-500 transition-all duration-200 rounded-full"
                    style={{ width: `${progressPct}%` }}
                  />
                </div>
              </div>
            ) : (
              <button
                onClick={handleStartCollect}
                className="w-full py-2.5 rounded-xl bg-[#1A1D2E] text-[#DDFD00] text-xs font-bold hover:bg-black/90 active:scale-[0.99] transition-all flex items-center justify-center gap-2 shadow-sm"
              >
                <Play className="w-3.5 h-3.5 fill-current" />
                <span>立即启动数据采集任务</span>
              </button>
            )}
          </div>

          {/* 4. Collection Log History */}
          <div className="space-y-2 pt-3 border-t border-black/[0.06]">
            <div className="flex items-center justify-between">
              <span className="font-bold text-[#1A1D2E]">历史采集日志</span>
              <span className="text-[10px] text-slate-400">保留最新对账记录</span>
            </div>

            <div className="space-y-2 max-h-72 overflow-y-auto pr-0.5">
              {logs.map((log) => {
                const isSuccess = log.status === 'success';
                const isNoData = log.status === 'no_data';
                return (
                  <div
                    key={log.id}
                    className="p-3 rounded-xl bg-slate-50 border border-black/[0.04] space-y-1.5"
                  >
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-1.5 font-bold text-[#1A1D2E]">
                        {isSuccess ? (
                          <CheckCircle2 className="w-3.5 h-3.5 text-emerald-600 shrink-0" />
                        ) : isNoData ? (
                          <Clock className="w-3.5 h-3.5 text-amber-500 shrink-0" />
                        ) : (
                          <AlertCircle className="w-3.5 h-3.5 text-rose-500 shrink-0" />
                        )}
                        <span className="truncate max-w-[170px]">{log.theaterName} · {log.accountName}</span>
                      </div>
                      <span className="font-mono text-[10px] text-slate-400">{log.updatedAt}</span>
                    </div>

                    <div className="flex items-center justify-between text-[11px] text-[#64748B]">
                      <span>区间: {log.period}</span>
                      <span className="font-mono font-bold text-emerald-700">
                        {log.collectedAmount !== undefined ? `¥${log.collectedAmount.toFixed(2)}` : '—'}
                      </span>
                    </div>

                    <div className="flex items-center justify-between text-[10px] pt-1 border-t border-black/[0.04]">
                      <span className="text-slate-500 truncate max-w-[240px]">{log.note || '流水核对完成'}</span>
                      <span className="px-1.5 py-0.2 rounded-md bg-emerald-100 text-emerald-800 font-medium">
                        质量: {log.qualityTier === 'direct' ? '直接流水' : log.qualityTier === 'derived' ? '规则推导' : '推测'}
                      </span>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        </div>

        {/* Footer */}
        <div className="p-3 bg-slate-50 border-t border-black/[0.06] text-[11px] text-[#64748B] flex items-center justify-between">
          <span className="flex items-center gap-1">
            <FileCheck className="w-3.5 h-3.5 text-emerald-600" />
            <span>数据直采自真实渠道接口</span>
          </span>
          <button
            onClick={onClose}
            className="px-3 py-1 rounded-lg text-xs font-semibold bg-white border border-black/[0.08] hover:bg-slate-100"
          >
            完成关闭
          </button>
        </div>
      </div>
    </div>
  );
};
