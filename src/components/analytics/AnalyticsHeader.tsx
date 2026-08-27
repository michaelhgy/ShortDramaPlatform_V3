import React, { useState } from 'react';
import { 
  AnalyticsTopTab, 
  TimeRangeFilter, 
  TheaterFilter 
} from '../../analyticsTypes';
import { 
  DollarSign, 
  Users, 
  Tv2, 
  Film, 
  Grid3X3, 
  DownloadCloud, 
  Layers, 
  Info,
  Calendar,
  ChevronDown
} from 'lucide-react';
import { DateRangeModal } from './common/DateRangeModal';

interface AnalyticsHeaderProps {
  activeTab: AnalyticsTopTab;
  onTabChange: (tab: AnalyticsTopTab) => void;
  timeRange: TimeRangeFilter;
  onTimeRangeChange: (range: TimeRangeFilter) => void;
  customStartDate?: string;
  customEndDate?: string;
  onCustomDateChange?: (start: string, end: string) => void;
  selectedTheater: TheaterFilter;
  onTheaterChange: (theater: TheaterFilter) => void;
  onOpenCollectionDrawer: () => void;
  // Dynamic badge and status values
  activeAccountsCount: number;
  activeDramasCount: number;
  collectionStatusText: string;
  isFullyComplete: boolean;
}

export const AnalyticsHeader: React.FC<AnalyticsHeaderProps> = ({
  activeTab,
  onTabChange,
  timeRange,
  onTimeRangeChange,
  customStartDate = '2026-08-03',
  customEndDate = '2026-08-17',
  onCustomDateChange,
  selectedTheater,
  onTheaterChange,
  onOpenCollectionDrawer,
  activeAccountsCount,
  activeDramasCount,
  collectionStatusText,
  isFullyComplete,
}) => {
  const [isDatePickerOpen, setIsDatePickerOpen] = useState(false);

  // 1. Dynamic Data Capability Hint
  const dataCapabilityHint = React.useMemo(() => {
    switch (selectedTheater) {
      case 'all':
        return '收益覆盖全部 5 个剧场 · 视频级指标由青柠剧场提供';
      case 'qingning':
        return '青柠剧场 · 支持收益、视频播放、剧集播放数据';
      case 'jiuzhou':
        return '九州剧场 · 当前剧场支持收益数据 · 暂无平台视频级数据';
      case 'dianzhong':
        return '点众微剧 · 当前剧场支持收益数据 · 暂无平台视频级数据';
      case 'fanqie':
        return '番茄剧场 · 当前剧场支持收益数据 · 暂无平台视频级数据';
      case 'huasheng':
        return '花生剧场 · 当前剧场支持推测收益 · 暂无平台视频级数据';
      default:
        return '当前剧场支持收益数据';
    }
  }, [selectedTheater]);

  const hasVideoDataInTheater = selectedTheater === 'all' || selectedTheater === 'qingning';

  const tabs: { key: AnalyticsTopTab; label: string; icon: React.ReactNode; countLabel?: string }[] = [
    { key: 'revenue', label: '收益', icon: <DollarSign className="w-4 h-4" /> },
    { key: 'accounts', label: '账号', icon: <Users className="w-4 h-4" />, countLabel: `${activeAccountsCount}` },
    { key: 'dramas', label: '剧集', icon: <Tv2 className="w-4 h-4" />, countLabel: `${activeDramasCount}` },
    { 
      key: 'videos', 
      label: '视频', 
      icon: <Film className="w-4 h-4" />, 
      countLabel: hasVideoDataInTheater ? '青柠' : '暂无' 
    },
    { key: 'combinations', label: '组合', icon: <Grid3X3 className="w-4 h-4" />, countLabel: '矩阵' },
  ];

  const timeRanges: { key: TimeRangeFilter; label: string }[] = [
    { key: 'yesterday', label: '昨日' },
    { key: '7days', label: '近7日' },
    { key: '30days', label: '近30日' },
    { key: 'this_month', label: '本月' },
    { 
      key: 'custom', 
      label: timeRange === 'custom' && customStartDate && customEndDate
        ? `自定义 · ${customStartDate.slice(5)}～${customEndDate.slice(5)}`
        : '自定义' 
    },
  ];

  const theaters: { key: TheaterFilter; label: string }[] = [
    { key: 'all', label: '全部剧场' },
    { key: 'qingning', label: '青柠剧场' },
    { key: 'jiuzhou', label: '九州剧场' },
    { key: 'dianzhong', label: '点众微剧' },
    { key: 'fanqie', label: '番茄剧场' },
    { key: 'huasheng', label: '花生剧场' },
  ];

  const handleTimeRangeClick = (key: TimeRangeFilter) => {
    if (key === 'custom') {
      onTimeRangeChange('custom');
      setIsDatePickerOpen(true);
    } else {
      onTimeRangeChange(key);
    }
  };

  return (
    <>
      <div className="bg-white rounded-2xl p-4 border border-black/[0.06] shadow-xs space-y-3.5">
        {/* Upper Tier: 5 Top-level Navigation Modules & Action Button */}
        <div className="flex flex-wrap items-center justify-between gap-3">
          {/* Five Core Modules Tab Bar */}
          <div className="flex items-center gap-1.5 p-1 bg-slate-100/80 rounded-xl border border-black/[0.04]">
            {tabs.map((tab) => {
              const isActive = activeTab === tab.key;
              return (
                <button
                  key={tab.key}
                  onClick={() => onTabChange(tab.key)}
                  className={`flex items-center gap-2 px-3.5 py-1.5 rounded-lg text-xs font-medium transition-all ${
                    isActive
                      ? 'bg-[#1A1D2E] text-white shadow-xs font-semibold'
                      : 'text-[#64748B] hover:text-[#1A1D2E] hover:bg-black/[0.04]'
                  }`}
                >
                  <span className={isActive ? 'text-[#DDFD00]' : 'text-[#64748B]'}>
                    {tab.icon}
                  </span>
                  <span>{tab.label}</span>
                  {tab.countLabel && (
                    <span
                      className={`text-[10px] px-1.5 py-0.2 rounded-full font-mono ${
                        isActive
                          ? 'bg-white/20 text-[#DDFD00]'
                          : 'bg-black/[0.06] text-[#64748B]'
                      }`}
                    >
                      {tab.countLabel}
                    </span>
                  )}
                </button>
              );
            })}
          </div>

          {/* Right Action: Data completeness status (昨日采集情况) & 采集收益 */}
          <div className="flex items-center gap-2">
            <div 
              className="hidden sm:flex items-center gap-1.5 px-2.5 py-1.5 rounded-xl bg-slate-50 border border-black/[0.04] text-[11px] text-[#64748B]"
              title="表示昨日收益数据采集与核对情况，采集失败或待补采不按0收益处理"
            >
              <span className={`w-2 h-2 rounded-full ${isFullyComplete ? 'bg-emerald-500' : 'bg-amber-500 animate-pulse'}`} />
              <span className="font-medium">{collectionStatusText}</span>
            </div>
            <button
              onClick={onOpenCollectionDrawer}
              className="flex items-center gap-2 px-3.5 py-1.5 rounded-xl bg-[#1A1D2E] text-[#DDFD00] text-xs font-semibold hover:bg-black/90 active:scale-[0.98] transition-all shadow-xs"
            >
              <DownloadCloud className="w-4 h-4" />
              <span>采集收益</span>
            </button>
          </div>
        </div>

        {/* Lower Tier: Global Scope Filters & Data Coverage Badge */}
        <div className="flex flex-wrap items-center justify-between gap-3 pt-2 border-t border-black/[0.04] text-xs">
          {/* Left: Time Range & Theater Filter */}
          <div className="flex flex-wrap items-center gap-3">
            {/* Time Range Pills */}
            <div className="flex items-center gap-1 bg-slate-50 p-0.5 rounded-lg border border-black/[0.04]">
              <span className="text-[11px] text-[#64748B] px-2 font-medium flex items-center gap-1">
                <Calendar className="w-3 h-3" />
                时间:
              </span>
              {timeRanges.map((r) => {
                const isSelected = timeRange === r.key;
                return (
                  <button
                    key={r.key}
                    onClick={() => handleTimeRangeClick(r.key)}
                    className={`px-2.5 py-1 rounded-md text-[11px] font-medium transition-all flex items-center gap-1 ${
                      isSelected
                        ? 'bg-white text-[#1A1D2E] shadow-2xs font-semibold border border-black/[0.04]'
                        : 'text-[#64748B] hover:text-[#1A1D2E]'
                    }`}
                  >
                    <span>{r.label}</span>
                    {r.key === 'custom' && isSelected && (
                      <ChevronDown className="w-3 h-3 text-slate-400" />
                    )}
                  </button>
                );
              })}
            </div>

            {/* Theater Filter Select */}
            <div className="flex items-center gap-1 bg-slate-50 px-2 py-0.5 rounded-lg border border-black/[0.04]">
              <span className="text-[11px] text-[#64748B] font-medium flex items-center gap-1">
                <Layers className="w-3 h-3" />
                剧场:
              </span>
              <select
                value={selectedTheater}
                onChange={(e) => onTheaterChange(e.target.value as TheaterFilter)}
                className="bg-transparent text-xs font-semibold text-[#1A1D2E] py-1 pl-1 pr-2 outline-none cursor-pointer"
              >
                {theaters.map((t) => (
                  <option key={t.key} value={t.key}>
                    {t.label}
                  </option>
                ))}
              </select>
            </div>
          </div>

          {/* Right: Data Coverage Badge (Dynamic capability indication) */}
          <div 
            className={`flex items-center gap-1.5 px-2.5 py-1 rounded-lg text-[11px] ${
              selectedTheater === 'qingning'
                ? 'bg-emerald-50 text-emerald-800 border border-emerald-200/60'
                : selectedTheater === 'all'
                ? 'bg-slate-50 text-slate-700 border border-black/[0.06]'
                : 'bg-amber-50 text-amber-800 border border-amber-200/60'
            }`}
          >
            <Info className={`w-3.5 h-3.5 shrink-0 ${
              selectedTheater === 'qingning' ? 'text-emerald-600' : selectedTheater === 'all' ? 'text-slate-500' : 'text-amber-600'
            }`} />
            <span>{dataCapabilityHint}</span>
          </div>
        </div>
      </div>

      {/* Date Range Modal */}
      <DateRangeModal
        isOpen={isDatePickerOpen}
        onClose={() => setIsDatePickerOpen(false)}
        startDate={customStartDate}
        endDate={customEndDate}
        onApply={(start, end) => {
          if (onCustomDateChange) {
            onCustomDateChange(start, end);
          }
        }}
      />
    </>
  );
};
