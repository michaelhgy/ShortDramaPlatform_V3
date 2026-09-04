import React, { useState, useEffect, useMemo, useRef } from 'react';
import { AccountItem, DramaItem, ScheduleTask } from '../types';
import { DramaCover } from './DramaCover';
import { DramaRenameModal } from './assets/modals/DramaRenameModal';
import {
  X, 
  Sparkles, 
  Check, 
  Clock, 
  Tv, 
  Film, 
  Layers, 
  ChevronRight,
  Search,
  Plus,
  Building2,
  AlertCircle,
  Calendar,
  SlidersHorizontal,
  CheckCircle2,
  Trash2,
  ArrowRight,
  Shuffle,
  Info
} from 'lucide-react';

const localDateValue = (value = new Date()) => {
  const offset = value.getTimezoneOffset() * 60_000;
  return new Date(value.getTime() - offset).toISOString().slice(0, 10);
};

const plannedDateTime = (dateValue: string, timeValue: string) => `${dateValue}T${timeValue}`;

const offsetDateValue = (days: number) => {
  const result = new Date();
  result.setDate(result.getDate() + days);
  return localDateValue(result);
};

const publishParts = (value: string) => {
  const [dateValue, timeValue = '18:30'] = value.split('T');
  return { dateValue, timeValue };
};

const publishLabel = (value: string) => {
  const { dateValue, timeValue } = publishParts(value);
  const today = localDateValue();
  const tomorrow = localDateValue(new Date(Date.now() + 24 * 60 * 60 * 1000));
  if (dateValue === today) return `今天 ${timeValue}`;
  if (dateValue === tomorrow) return `明天 ${timeValue}`;
  const [, month, day] = dateValue.split('-');
  return `${Number(month)}月${Number(day)}日 ${timeValue}`;
};

const scheduleDateLabel = (value?: string) => {
  if (!value) return '尚未安排';
  const dateValue = value.slice(0, 10);
  const [, month, day] = dateValue.split('-');
  return month && day ? `最近安排：${Number(month)}月${Number(day)}日` : '尚未安排';
};

interface ScheduleModalProps {
  isOpen: boolean;
  onClose: () => void;
  accounts: AccountItem[];
  dramas: DramaItem[];
  initialAccountId?: string;
  initialDramaId?: string;
  publishTimePresets: string[];
  publishDateOffsetDays: number;
  theaters: { id: string; name: string }[];
  onCreateDrama: (data: { currentName: string; historyNames: string[]; theaterName: string; theaterId: string }) => Promise<DramaItem>;
  onSaveSchedule: (newTasks: Omit<ScheduleTask, 'id'>[]) => void;
}

// Quick Preset Time Options
export const ScheduleModal: React.FC<ScheduleModalProps> = ({
  isOpen,
  onClose,
  accounts,
  dramas: propDramas,
  initialAccountId,
  initialDramaId,
  publishTimePresets,
  publishDateOffsetDays,
  theaters,
  onCreateDrama,
  onSaveSchedule,
}) => {
  // Local dramas state so newly created dramas in this session are immediately available
  const [dramaList, setDramaList] = useState<DramaItem[]>(propDramas);
  
  // Selection states
  const [selectedAccountIds, setSelectedAccountIds] = useState<string[]>([]);
  const [selectedDramaIds, setSelectedDramaIds] = useState<string[]>([]);

  // Search in drama selection
  const [dramaSearchTerm, setDramaSearchTerm] = useState('');

  // Combination individual publish times: map of `${accountId}_${dramaId}` -> time string
  const [combinationTimes, setCombinationTimes] = useState<Record<string, string>>({});

  // Quick Add Drama Dialog state
  const [isAddDramaOpen, setIsAddDramaOpen] = useState(false);
  const [newDramaName, setNewDramaName] = useState('');
  const [newDramaCategory, setNewDramaCategory] = useState('都市逆袭');
  const [newDramaEpisodes, setNewDramaEpisodes] = useState(80);
  const [addDramaToast, setAddDramaToast] = useState<string | null>(null);
  const initializedSession = useRef<string | null>(null);

  // Sync prop dramas
  useEffect(() => {
    setDramaList(propDramas);
  }, [propDramas]);

  // Determine current locked theater name based on the first selected account
  const lockedTheaterName = useMemo(() => {
    if (selectedAccountIds.length === 0) return null;
    const firstAcc = accounts.find(a => a.id === selectedAccountIds[0]);
    return firstAcc?.theaterName || '青柠剧场';
  }, [selectedAccountIds, accounts]);

  // Initialize or reset selections when modal opens
  useEffect(() => {
    if (!isOpen) {
      initializedSession.current = null;
      return;
    }
    const sessionKey = `${initialAccountId || ''}:${initialDramaId || ''}`;
    if (initializedSession.current !== sessionKey) {
      initializedSession.current = sessionKey;
      if (initialAccountId) {
        setSelectedAccountIds([initialAccountId]);
        const matchedAcc = accounts.find(a => a.id === initialAccountId);
        const theater = matchedAcc?.theaterName || '青柠剧场';
        
        // Match initial drama or default dramas in that theater
        if (initialDramaId) {
          setSelectedDramaIds([initialDramaId]);
        } else {
          const theaterDramas = propDramas.filter(d => (d.theaterName || '青柠剧场') === theater);
          if (theaterDramas.length > 0) {
            setSelectedDramaIds([theaterDramas[0].id]);
          } else if (propDramas.length > 0) {
            setSelectedDramaIds([propDramas[0].id]);
          }
        }
      } else {
        setSelectedAccountIds([]);
        setSelectedDramaIds([]);
      }

      setDramaSearchTerm('');
      setIsAddDramaOpen(false);
      setNewDramaName('');
    }
  }, [isOpen, initialAccountId, initialDramaId, accounts, propDramas]);

  // Account Toggle Handler with Theater Locking Rule
  const handleToggleAccount = (acc: AccountItem) => {
    const isCurrentlySelected = selectedAccountIds.includes(acc.id);

    if (isCurrentlySelected) {
      // Uncheck account
      const nextSelected = selectedAccountIds.filter(id => id !== acc.id);
      setSelectedAccountIds(nextSelected);
      // If no accounts left, drama list resets to unlinked or stays available
    } else {
      // If already has locked theater, verify match
      if (lockedTheaterName && acc.theaterName && acc.theaterName !== lockedTheaterName) {
        // Disabled item clicked
        return;
      }
      setSelectedAccountIds(prev => [...prev, acc.id]);
    }
  };

  // Quick Select All Accounts in the currently locked theater
  const handleSelectAllInTheater = () => {
    if (!lockedTheaterName) {
      // Pick first account's theater
      if (accounts.length > 0) {
        const firstTheater = accounts[0].theaterName || '青柠剧场';
        const matchingIds = accounts.filter(a => (a.theaterName || '青柠剧场') === firstTheater).map(a => a.id);
        setSelectedAccountIds(matchingIds);
      }
    } else {
      const matchingIds = accounts.filter(a => (a.theaterName || '青柠剧场') === lockedTheaterName).map(a => a.id);
      setSelectedAccountIds(matchingIds);
    }
  };

  // Drama Toggle Handler (Multi-select)
  const handleToggleDrama = (dramaId: string) => {
    if (selectedDramaIds.includes(dramaId)) {
      setSelectedDramaIds(selectedDramaIds.filter(id => id !== dramaId));
    } else {
      setSelectedDramaIds([...selectedDramaIds, dramaId]);
    }
  };

  // Filter & Sort Dramas based on locked theater, usage frequency, and fuzzy search
  const displayedDramas = useMemo(() => {
    let list = dramaList;

    // 1. Theater filter: only show dramas belonging to the locked theater
    if (lockedTheaterName) {
      list = list.filter(d => (d.theaterName || '青柠剧场') === lockedTheaterName);
    }

    // 活跃度：当前正在排队/生产优先，其次最近安排，再其次生产次数。
    list = [...list].sort((left, right) => {
      const active = (right.activeProductionCount || 0) - (left.activeProductionCount || 0);
      if (active) return active;
      const recent = Date.parse(right.lastScheduledAt || '') - Date.parse(left.lastScheduledAt || '');
      if (Number.isFinite(recent) && recent) return recent;
      const produced = (right.productionCount || 0) - (left.productionCount || 0);
      if (produced) return produced;
      return left.name.localeCompare(right.name, 'zh-CN');
    });

    // 3. Fuzzy / substring search (contains matching)
    if (dramaSearchTerm.trim()) {
      const term = dramaSearchTerm.trim().toLowerCase();
      list = list.filter(d => 
        d.name.toLowerCase().includes(term) ||
        (d.category && d.category.toLowerCase().includes(term))
      );
    }

    return list;
  }, [dramaList, lockedTheaterName, dramaSearchTerm]);

  // Selected dramas objects (preserved even if search term filters them out of candidate view)
  const selectedDramas = useMemo(() => {
    return selectedDramaIds
      .map(id => dramaList.find(d => d.id === id))
      .filter((d): d is DramaItem => Boolean(d));
  }, [selectedDramaIds, dramaList]);

  // Selected accounts objects
  const selectedAccounts = useMemo(() => {
    return selectedAccountIds
      .map(id => accounts.find(a => a.id === id))
      .filter((a): a is AccountItem => Boolean(a));
  }, [selectedAccountIds, accounts]);

  // Compute Account x Drama combinations
  const combinations = useMemo(() => {
    const list: {
      key: string;
      account: AccountItem;
      drama: DramaItem;
      defaultTime: string;
    }[] = [];

    let timeOffsetMinutes = 0;
    const [baseHour, baseMin] = (publishTimePresets[0] || '18:30').split(':').map(Number);

    selectedAccounts.forEach(acc => {
      selectedDramas.forEach(drama => {
        const key = `${acc.id}_${drama.id}`;
        
        // Calculate a sensible default staggered time
        const totalMinutes = baseHour * 60 + baseMin + timeOffsetMinutes;
        const h = Math.floor((totalMinutes % (24 * 60)) / 60);
        const m = totalMinutes % 60;
        const formattedTime = plannedDateTime(offsetDateValue(publishDateOffsetDays), `${String(h).padStart(2, '0')}:${String(m).padStart(2, '0')}`);

        list.push({
          key,
          account: acc,
          drama,
          defaultTime: formattedTime,
        });

        // Stagger by 30 mins for the next task
        timeOffsetMinutes += 30;
      });
    });

    return list;
  }, [selectedAccounts, selectedDramas, publishTimePresets, publishDateOffsetDays]);

  // Initialize combination times whenever combinations change
  useEffect(() => {
    setCombinationTimes(prev => {
      const next = { ...prev };
      combinations.forEach(c => {
        if (!next[c.key]) {
          next[c.key] = c.defaultTime;
        }
      });
      return next;
    });
  }, [combinations]);

  // Time change for a specific combination
  const handleSetTimeForCombination = (key: string, time: string) => {
    setCombinationTimes(prev => ({
      ...prev,
      [key]: time,
    }));
  };

  // Batch Tool 1: Staggered intervals (e.g. from 18:00, interval +30m or +45m)
  const handleApplyStaggeredSchedule = (startHour = 18, startMinute = 0, stepMinutes = 30) => {
    const updated: Record<string, string> = {};
    let offset = 0;

    combinations.forEach(c => {
      const totalMinutes = startHour * 60 + startMinute + offset;
      const h = Math.floor((totalMinutes % (24 * 60)) / 60);
      const m = totalMinutes % 60;
      const current = combinationTimes[c.key] || c.defaultTime;
      updated[c.key] = plannedDateTime(publishParts(current).dateValue, `${String(h).padStart(2, '0')}:${String(m).padStart(2, '0')}`);
      offset += stepMinutes;
    });

    setCombinationTimes(prev => ({ ...prev, ...updated }));
  };

  // Batch Tool 2: Unify all to one preset time
  const handleApplyUniformTime = (time: string) => {
    const updated: Record<string, string> = {};
    combinations.forEach(c => {
      const current = combinationTimes[c.key] || c.defaultTime;
      updated[c.key] = plannedDateTime(publishParts(current).dateValue, time);
    });
    setCombinationTimes(prev => ({ ...prev, ...updated }));
  };

  // Batch Tool 3: Split between Noon and Evening (e.g. Episode 1 at 12:00, Episode 2 at 18:30)
  const handleApplyDayNightSplit = () => {
    const updated: Record<string, string> = {};
    selectedAccounts.forEach(acc => {
      selectedDramas.forEach((drama, idx) => {
        const key = `${acc.id}_${drama.id}`;
        if (idx === 0) {
          updated[key] = plannedDateTime(publishParts(combinationTimes[key] || plannedDateTime(localDateValue(), '12:30')).dateValue, '12:30');
        } else if (idx === 1) {
          updated[key] = plannedDateTime(publishParts(combinationTimes[key] || plannedDateTime(localDateValue(), '18:30')).dateValue, '18:30');
        } else if (idx === 2) {
          updated[key] = plannedDateTime(publishParts(combinationTimes[key] || plannedDateTime(localDateValue(), '20:00')).dateValue, '20:00');
        } else {
          updated[key] = plannedDateTime(publishParts(combinationTimes[key] || plannedDateTime(localDateValue(), '21:30')).dateValue, '21:30');
        }
      });
    });
    setCombinationTimes(prev => ({ ...prev, ...updated }));
  };

  // Handle Quick Add Drama Submit
  const handleCreateNewDrama = (e: React.FormEvent) => {
    e.preventDefault();
    if (!newDramaName.trim()) return;

    const trimmedName = newDramaName.trim();
    const effectiveTheater = lockedTheaterName || '青柠剧场';

    const newDrama: DramaItem = {
      id: `drama-quick-${Date.now()}`,
      name: trimmedName,
      category: newDramaCategory,
      totalEpisodes: newDramaEpisodes || 80,
      theaterName: effectiveTheater,
      theaterId: effectiveTheater === '青柠剧场' ? 'th-qn' : 'th-01',
      productionCount: 0,
      lastScheduledAt: '',
      colorPlaceholder: {
        bg: 'linear-gradient(135deg, #1E293B 0%, #0F172A 100%)',
        text: '#DDFD00',
        tag: newDramaCategory,
      },
    };

    // Add to local drama list
    setDramaList(prev => [newDrama, ...prev]);

    // Automatically select the new drama!
    setSelectedDramaIds(prev => [...prev, newDrama.id]);

    // Toast notification
    setAddDramaToast(`已新建剧集《${trimmedName}》并自动加入当前已选`);
    setTimeout(() => setAddDramaToast(null), 3000);

    // Reset & close quick add dialog
    setNewDramaName('');
    setIsAddDramaOpen(false);
  };

  // Save Schedule Handler
  const handleSaveAll = () => {
    if (combinations.length === 0) return;

    const newTasks: Omit<ScheduleTask, 'id'>[] = combinations.map(c => {
      const publishTime = combinationTimes[c.key] || c.defaultTime;
      return {
        accountId: c.account.id,
        accountName: c.account.name,
        dramaId: c.drama.id,
        dramaName: c.drama.name,
        coverUrl: c.drama.coverUrl,
        colorPlaceholder: c.drama.colorPlaceholder,
        publishTime: publishLabel(publishTime),
        plannedPublishAt: publishTime,
        theaterName: c.account.theaterName || lockedTheaterName || '青柠剧场',
        status: '待制作',
      };
    });

    onSaveSchedule(newTasks);
    onClose();
  };

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-end bg-black/40 backdrop-blur-xs transition-opacity duration-200">
      <div 
        id="schedule-side-panel"
        className="w-full max-w-2xl h-full bg-[#F8FAFC] shadow-2xl flex flex-col justify-between overflow-hidden border-l border-black/[0.08] animate-in slide-in-from-right duration-200"
      >
        {/* Top Header */}
        <div className="px-6 py-4 bg-white border-b border-black/[0.06] flex items-center justify-between shrink-0">
          <div>
            <div className="flex items-center gap-2">
              <h3 className="font-extrabold text-base text-[#1A1D2E] tracking-tight">
                安排今日制作与发布
              </h3>
              {lockedTheaterName ? (
                <span className="inline-flex items-center gap-1 text-[11px] px-2.5 py-0.5 rounded-full bg-[#1A1D2E] text-[#DDFD00] font-bold">
                  <Building2 className="w-3 h-3" />
                  已锁定剧场：{lockedTheaterName}
                </span>
              ) : (
                <span className="text-[11px] px-2 py-0.5 rounded-full bg-slate-100 text-slate-500 font-medium">
                  待选定剧场
                </span>
              )}
            </div>
            <p className="text-xs text-[#64748B] mt-0.5">
              账号 → 剧场联动 → 剧集多选 → 生成独立「账号 × 剧集」排期任务
            </p>
          </div>

          <button
            onClick={onClose}
            className="p-2 rounded-xl text-slate-400 hover:text-slate-700 hover:bg-slate-100 transition-colors cursor-pointer"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Scrollable Form Body */}
        <div className="p-6 overflow-y-auto flex-1 space-y-6">
          {/* =========================================================================
              STEP 1: 选择运营账号 (支持多选 + 剧场锁定联动)
              ========================================================================= */}
          <div className="bg-white rounded-2xl p-4 border border-black/[0.06] shadow-2xs space-y-3">
            <div className="flex items-center justify-between">
              <label className="text-xs font-extrabold text-[#1A1D2E] flex items-center gap-1.5">
                <div className="w-5 h-5 rounded-lg bg-[#1A1D2E] text-[#DDFD00] flex items-center justify-center text-[10px] font-bold">
                  1
                </div>
                <span>选择运营账号（单次仅限同一剧场账号）</span>
              </label>

              <div className="flex items-center gap-2 text-xs">
                <button
                  type="button"
                  onClick={handleSelectAllInTheater}
                  className="text-slate-600 hover:text-[#1A1D2E] font-bold text-[11px] hover:underline cursor-pointer"
                >
                  全选本剧场账号
                </button>
                {selectedAccountIds.length > 0 && (
                  <>
                    <span className="text-slate-300">·</span>
                    <button
                      type="button"
                      onClick={() => setSelectedAccountIds([])}
                      className="text-rose-600 hover:text-rose-700 font-bold text-[11px] hover:underline cursor-pointer"
                    >
                      清空已选
                    </button>
                  </>
                )}
                <span className="text-[11px] font-bold px-2 py-0.5 rounded-md bg-slate-100 text-[#1A1D2E]">
                  已选 {selectedAccountIds.length} 个账号
                </span>
              </div>
            </div>

            {/* Accounts Grid */}
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
              {accounts.map(acc => {
                const isSelected = selectedAccountIds.includes(acc.id);
                const accTheater = acc.theaterName || '青柠剧场';
                const isTheaterMismatch = lockedTheaterName !== null && accTheater !== lockedTheaterName;

                return (
                  <button
                    key={acc.id}
                    type="button"
                    disabled={isTheaterMismatch}
                    onClick={() => handleToggleAccount(acc)}
                    className={`p-3 rounded-xl border text-left flex items-center justify-between transition-all relative cursor-pointer ${
                      isSelected
                        ? 'bg-[#1A1D2E] text-white border-[#1A1D2E] shadow-xs'
                        : isTheaterMismatch
                        ? 'bg-slate-50/70 text-slate-300 border-slate-100 cursor-not-allowed opacity-50'
                        : 'bg-[#F8FAFC] text-[#334155] border-black/[0.06] hover:bg-white hover:border-black/[0.12]'
                    }`}
                  >
                    <div className="min-w-0 pr-2">
                      <div className="flex items-center gap-1.5">
                        <span className="font-bold text-xs truncate">
                          {acc.name}
                        </span>
                        <span className={`text-[10px] px-1.5 py-0.2 rounded font-medium ${
                          isSelected 
                            ? 'bg-white/20 text-[#DDFD00]' 
                            : isTheaterMismatch
                            ? 'bg-slate-200/50 text-slate-400'
                            : 'bg-slate-200/80 text-slate-700'
                        }`}>
                          {accTheater}
                        </span>
                      </div>
                      
                      <div className={`text-[10px] mt-1 flex items-center gap-2 ${
                        isSelected ? 'text-slate-300' : isTheaterMismatch ? 'text-slate-300' : 'text-slate-500'
                      }`}>
                        <span>{acc.yesterdayRevenueState === 'success'
                          ? `昨日 ¥${acc.yesterdayRevenue.toFixed(2)}`
                          : acc.yesterdayRevenueState === 'no_data' ? '昨日无结算数据'
                            : acc.yesterdayRevenueState === 'failed' ? '昨日采集失败'
                              : '昨日未采集'}</span>
                        <span>·</span>
                        <span>{acc.manualStatus}</span>
                      </div>

                      {isTheaterMismatch && (
                        <div className="text-[9px] text-slate-400 mt-0.5 truncate">
                          跨剧场不可混选 (属 {accTheater})
                        </div>
                      )}
                    </div>

                    <div className={`w-5 h-5 rounded-lg flex items-center justify-center shrink-0 transition-all ${
                      isSelected 
                        ? 'bg-[#DDFD00] text-[#1A1D2E]' 
                        : isTheaterMismatch
                        ? 'border border-slate-200 bg-slate-100'
                        : 'border border-slate-300 bg-white'
                    }`}>
                      {isSelected && <Check className="w-3.5 h-3.5 stroke-[3]" />}
                    </div>
                  </button>
                );
              })}
            </div>
          </div>

          {/* =========================================================================
              STEP 2: 选择剧集 (剧场联动 + 频次排序 + 包含匹配搜索 + 勾选持久化 + 新增剧集)
              ========================================================================= */}
          <div className="bg-white rounded-2xl p-4 border border-black/[0.06] shadow-2xs space-y-3">
            <div className="flex items-center justify-between flex-wrap gap-2">
              <label className="text-xs font-extrabold text-[#1A1D2E] flex items-center gap-1.5">
                <div className="w-5 h-5 rounded-lg bg-[#1A1D2E] text-[#DDFD00] flex items-center justify-center text-[10px] font-bold">
                  2
                </div>
                <span>选择剧集（按活跃度排序 · 支持多选）</span>
              </label>

              <div className="flex items-center gap-2">
                <button
                  type="button"
                  onClick={() => setIsAddDramaOpen(true)}
                  className="flex items-center gap-1 px-2.5 py-1 rounded-lg bg-[#1A1D2E] text-[#DDFD00] text-xs font-bold hover:bg-black transition-all cursor-pointer shadow-2xs"
                >
                  <Plus className="w-3.5 h-3.5 stroke-[2.5]" />
                  <span>新增剧集</span>
                </button>

                <span className="text-[11px] font-bold px-2 py-0.5 rounded-md bg-slate-100 text-[#1A1D2E]">
                  已选 {selectedDramaIds.length} 部剧
                </span>
              </div>
            </div>

            {/* Persistent Selected Dramas Chips Summary */}
            {selectedDramas.length > 0 && (
              <div className="p-2.5 rounded-xl bg-slate-50 border border-slate-200/80 space-y-1.5">
                <div className="flex items-center justify-between text-[11px]">
                  <span className="font-bold text-[#1A1D2E] flex items-center gap-1">
                    <CheckCircle2 className="w-3.5 h-3.5 text-emerald-600" />
                    当前已勾选剧目（搜索不影响已选项）：
                  </span>
                  <button
                    type="button"
                    onClick={() => setSelectedDramaIds([])}
                    className="text-slate-400 hover:text-rose-600 text-[10px] font-bold cursor-pointer"
                  >
                    清空已选剧
                  </button>
                </div>

                <div className="flex flex-wrap gap-1.5">
                  {selectedDramas.map(d => (
                    <span
                      key={d.id}
                      className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-lg bg-white border border-black/[0.08] text-xs font-bold text-[#1A1D2E] shadow-2xs"
                    >
                      <span className="truncate max-w-[160px]">《{d.name}》</span>
                      <button
                        type="button"
                        onClick={() => handleToggleDrama(d.id)}
                        className="hover:text-rose-600 text-slate-400 cursor-pointer"
                      >
                        <X className="w-3 h-3" />
                      </button>
                    </span>
                  ))}
                </div>
              </div>
            )}

            {/* Search Input Box */}
            <div className="relative">
              <Search className="w-4 h-4 text-slate-400 absolute left-3 top-1/2 -translate-y-1/2" />
              <input
                type="text"
                value={dramaSearchTerm}
                onChange={(e) => setDramaSearchTerm(e.target.value)}
                placeholder="搜索剧名关键词（如：八零 / 首富 / 战神 / 逆袭）..."
                className="w-full pl-9 pr-8 py-2 bg-[#F8FAFC] border border-black/[0.06] rounded-xl text-xs text-[#1A1D2E] placeholder:text-slate-400 focus:outline-none focus:border-[#1A1D2E] focus:bg-white transition-all"
              />
              {dramaSearchTerm && (
                <button
                  type="button"
                  onClick={() => setDramaSearchTerm('')}
                  className="absolute right-2.5 top-1/2 -translate-y-1/2 text-slate-400 hover:text-slate-600 p-0.5 cursor-pointer"
                >
                  <X className="w-3.5 h-3.5" />
                </button>
              )}
            </div>

            {/* Dramas Candidate List */}
            <div className="grid grid-cols-1 md:grid-cols-2 gap-2 max-h-[500px] overflow-y-auto pr-1">
              {displayedDramas.length > 0 ? (
                displayedDramas.map(drama => {
                  const isSelected = selectedDramaIds.includes(drama.id);
                  return (
                    <button
                      key={drama.id}
                      type="button"
                      onClick={() => handleToggleDrama(drama.id)}
                      className={`min-h-[86px] w-full p-2.5 rounded-xl border text-left flex items-center gap-3 transition-all cursor-pointer ${
                        isSelected
                          ? 'bg-[#1A1D2E]/[0.03] border-[#1A1D2E] shadow-2xs'
                          : 'bg-[#F8FAFC] border-black/[0.05] hover:bg-white hover:border-black/[0.1]'
                      }`}
                    >
                      <DramaCover
                        name={drama.name}
                        coverUrl={drama.coverUrl}
                        colorPlaceholder={drama.colorPlaceholder}
                        size="sm"
                      />

                      <div className="flex-1 min-w-0">
                        <div className="flex items-start gap-1.5">
                          <span className="line-clamp-2 font-extrabold text-xs leading-5 text-[#1A1D2E]">
                            《{drama.name}》
                          </span>
                        </div>

                        <div className="text-[10px] text-[#64748B] flex flex-wrap items-center gap-x-2 gap-y-0.5 mt-1">
                          <span className="text-slate-500 font-mono">
                            生产 {drama.productionCount || 0} 次
                          </span>
                          <span>·</span>
                          <span>{scheduleDateLabel(drama.lastScheduledAt)}</span>
                        </div>
                      </div>

                      <div className={`w-5 h-5 rounded-lg flex items-center justify-center shrink-0 transition-all ${
                        isSelected 
                          ? 'bg-[#1A1D2E] text-[#DDFD00]' 
                          : 'border border-slate-300 bg-white'
                      }`}>
                        {isSelected && <Check className="w-3.5 h-3.5 stroke-[3]" />}
                      </div>
                    </button>
                  );
                })
              ) : (
                <div className="py-8 text-center text-xs text-slate-400 bg-slate-50 rounded-xl border border-dashed border-slate-200">
                  <p>未找到符合搜索条件的「{lockedTheaterName || '当前剧场'}」剧目</p>
                  <button
                    type="button"
                    onClick={() => setIsAddDramaOpen(true)}
                    className="mt-2 text-xs font-bold text-[#1A1D2E] underline cursor-pointer"
                  >
                    + 直接录入并新建《{dramaSearchTerm}》
                  </button>
                </div>
              )}
            </div>
          </div>

          {/* =========================================================================
              STEP 3: 账号 × 剧集 组合与独立发布时间设置 (核心重构)
              ========================================================================= */}
          <div className="bg-white rounded-2xl p-4 border border-black/[0.06] shadow-2xs space-y-3">
            <div className="flex items-center justify-between flex-wrap gap-2">
              <label className="text-xs font-extrabold text-[#1A1D2E] flex items-center gap-1.5">
                <div className="w-5 h-5 rounded-lg bg-[#1A1D2E] text-[#DDFD00] flex items-center justify-center text-[10px] font-bold">
                  3
                </div>
                <span>制作任务清单 & 独立发布时间设定</span>
              </label>

              <span className="text-[11px] font-extrabold px-2.5 py-0.5 rounded-full bg-[#1A1D2E] text-[#DDFD00]">
                {selectedAccountIds.length} 账号 × {selectedDramaIds.length} 剧集 = 共 {combinations.length} 个独立任务
              </span>
            </div>

            {/* Batch Helper Toolbar */}
            {combinations.length > 1 && (
              <div className="p-3 rounded-xl bg-slate-50 border border-slate-200/80 space-y-2">
                <div className="flex items-center justify-between text-[11px] text-[#64748B]">
                  <span className="font-bold text-[#1A1D2E] flex items-center gap-1">
                    <SlidersHorizontal className="w-3 h-3 text-slate-700" />
                    高效率批量排期工具（随后可单独微调每条任务时间）：
                  </span>
                </div>

                <div className="flex flex-wrap gap-1.5 text-xs">
                  <button
                    type="button"
                    onClick={() => handleApplyStaggeredSchedule(18, 0, 30)}
                    className="px-2.5 py-1 rounded-lg bg-white border border-black/[0.08] hover:bg-slate-100 font-bold text-[#1A1D2E] transition-all cursor-pointer shadow-2xs"
                  >
                    ⚡ 晚间黄金档错峰 (+30分间隔)
                  </button>

                  <button
                    type="button"
                    onClick={() => handleApplyStaggeredSchedule(12, 0, 45)}
                    className="px-2.5 py-1 rounded-lg bg-white border border-black/[0.08] hover:bg-slate-100 font-bold text-[#1A1D2E] transition-all cursor-pointer shadow-2xs"
                  >
                    🌤️ 中午档起步错峰 (+45分间隔)
                  </button>

                  <button
                    type="button"
                    onClick={handleApplyDayNightSplit}
                    className="px-2.5 py-1 rounded-lg bg-white border border-black/[0.08] hover:bg-slate-100 font-bold text-[#1A1D2E] transition-all cursor-pointer shadow-2xs"
                  >
                    🌗 早晚双档分流
                  </button>

                  <button
                    type="button"
                    onClick={() => handleApplyUniformTime(publishTimePresets[0] || '18:30')}
                    className="px-2.5 py-1 rounded-lg bg-white border border-black/[0.08] hover:bg-slate-100 font-bold text-slate-700 transition-all cursor-pointer shadow-2xs"
                  >
                    统一使用首个预设
                  </button>
                </div>
              </div>
            )}

            {/* Combinations List */}
            {combinations.length > 0 ? (
              <div className="space-y-2 max-h-72 overflow-y-auto pr-1">
                {combinations.map((combo, index) => {
                  const currentPublishTime = combinationTimes[combo.key] || combo.defaultTime;
                  
                  return (
                    <div
                      key={combo.key}
                      className="p-3 rounded-xl bg-[#F8FAFC] border border-black/[0.06] hover:border-black/[0.12] transition-all flex flex-col sm:flex-row sm:items-center justify-between gap-3 shadow-2xs"
                    >
                      {/* Left: Task Identity (Account x Drama) */}
                      <div className="flex items-center gap-3 min-w-0">
                        <span className="w-5 h-5 rounded-full bg-slate-200 text-slate-700 text-[10px] font-bold flex items-center justify-center shrink-0">
                          {index + 1}
                        </span>

                        <DramaCover
                          name={combo.drama.name}
                          coverUrl={combo.drama.coverUrl}
                          colorPlaceholder={combo.drama.colorPlaceholder}
                          size="sm"
                        />

                        <div className="min-w-0">
                          <div className="flex items-center gap-1.5 flex-wrap">
                            <span className="font-extrabold text-xs text-[#1A1D2E] truncate">
                              《{combo.drama.name}》
                            </span>
                            <span className="text-slate-300">×</span>
                            <span className="text-xs font-bold text-slate-700 truncate">
                              {combo.account.name}
                            </span>
                          </div>

                          <div className="text-[10px] text-slate-400 mt-0.5 flex items-center gap-2">
                            <span>所属剧场: {combo.account.theaterName || lockedTheaterName}</span>
                            <span>·</span>
                            <span>生产 {combo.drama.productionCount || 0} 次</span>
                          </div>
                        </div>
                      </div>

                      {/* Right: Individual publish date and time */}
                      <div className="flex flex-col items-end gap-1.5 shrink-0 self-end sm:self-center">
                        <div className="flex items-center gap-1.5 bg-white px-2.5 py-1.5 rounded-xl border border-black/[0.08] shadow-2xs">
                          <Clock className="w-3.5 h-3.5 text-slate-500" />
                          <span className="text-[11px] text-slate-500 font-medium">发布时间:</span>
                          <input
                            aria-label="发布日期"
                            type="date"
                            min={localDateValue()}
                            value={publishParts(currentPublishTime).dateValue}
                            onChange={(e) => handleSetTimeForCombination(combo.key, plannedDateTime(e.target.value, publishParts(currentPublishTime).timeValue))}
                            className="w-[112px] text-xs font-bold text-[#1A1D2E] focus:outline-none bg-transparent"
                          />
                          <input
                            aria-label="发布时间"
                            type="time"
                            value={publishParts(currentPublishTime).timeValue}
                            onChange={(e) => handleSetTimeForCombination(combo.key, plannedDateTime(publishParts(currentPublishTime).dateValue, e.target.value))}
                            className="w-[68px] text-xs font-bold text-[#1A1D2E] focus:outline-none bg-transparent"
                          />
                        </div>

                        <div className="flex items-center gap-1 flex-wrap justify-end">
                          {publishTimePresets.map(t => (
                            <button
                              key={t}
                              type="button"
                              onClick={() => handleSetTimeForCombination(combo.key, plannedDateTime(publishParts(currentPublishTime).dateValue, t))}
                              className={`px-1.5 py-1 rounded text-[10px] font-bold border transition-all cursor-pointer ${
                                publishParts(currentPublishTime).timeValue === t
                                  ? 'bg-[#1A1D2E] text-[#DDFD00] border-[#1A1D2E]'
                                  : 'bg-white text-slate-600 border-black/[0.06] hover:bg-slate-100'
                              }`}
                            >
                              {t}
                            </button>
                          ))}
                        </div>
                      </div>
                    </div>
                  );
                })}
              </div>
            ) : (
              <div className="py-6 text-center text-xs text-slate-400 bg-slate-50 rounded-xl border border-dashed border-slate-200">
                请先选择至少 1 个运营账号与 1 部短剧目以生成制作任务
              </div>
            )}

            {/* Backend Scheduling Priority Tip */}
            <div className="flex items-start gap-1.5 p-2.5 rounded-xl bg-slate-50 border border-slate-200/60 text-[11px] text-[#64748B]">
              <Info className="w-3.5 h-3.5 text-slate-500 shrink-0 mt-0.5" />
              <span>
                <strong>生产调度说明：</strong>计划发布时间更早的制作任务将在剪映渲染与导出队列中获得更高调度优先级。
              </span>
            </div>
          </div>
        </div>

        {/* Modal Footer Actions */}
        <div className="px-6 py-4 bg-white border-t border-black/[0.06] flex items-center justify-between shrink-0">
          <div className="text-xs text-[#64748B]">
            {combinations.length > 0 ? (
              <span>
                即将创建 <strong className="text-[#1A1D2E] font-extrabold">{combinations.length} 个独立制作任务</strong>
              </span>
            ) : (
              <span>请完成账号与剧集选择</span>
            )}
          </div>

          <div className="flex items-center gap-2.5">
            <button
              type="button"
              onClick={onClose}
              className="px-4 py-2 rounded-xl text-xs font-semibold text-[#64748B] hover:bg-slate-100 transition-colors cursor-pointer"
            >
              取消
            </button>
            <button
              id="btn-confirm-save-schedule"
              type="button"
              onClick={handleSaveAll}
              disabled={combinations.length === 0}
              className="flex items-center gap-1.5 px-5 py-2.5 rounded-xl bg-[#1A1D2E] hover:bg-black text-[#DDFD00] text-xs font-extrabold transition-all shadow-md active:scale-95 disabled:opacity-40 disabled:cursor-not-allowed cursor-pointer"
            >
              <span>保存并加入今日安排 ({combinations.length})</span>
              <ChevronRight className="w-4 h-4 stroke-[2.5]" />
            </button>
          </div>
        </div>
      </div>

      {/* =========================================================================
          INLINE DIALOG: + 新增剧集 (直接在当前流程内弹窗录入，无需页面跳转)
          ========================================================================= */}
      {false && isAddDramaOpen && (
        <div 
          className="fixed inset-0 z-60 flex items-center justify-center p-4 bg-black/50 backdrop-blur-xs animate-in fade-in duration-150"
          onClick={() => setIsAddDramaOpen(false)}
        >
          <div 
            className="bg-white rounded-3xl p-6 w-full max-w-md shadow-2xl border border-black/[0.08] space-y-4"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-center justify-between pb-3 border-b border-slate-100">
              <div className="flex items-center gap-2">
                <div className="w-7 h-7 rounded-xl bg-[#1A1D2E] text-[#DDFD00] flex items-center justify-center font-bold text-xs">
                  <Film className="w-4 h-4" />
                </div>
                <h4 className="font-extrabold text-sm text-[#1A1D2E]">快速录入新剧集</h4>
              </div>
              <button
                type="button"
                onClick={() => setIsAddDramaOpen(false)}
                className="p-1 rounded-lg text-slate-400 hover:text-slate-700 cursor-pointer"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            <form onSubmit={handleCreateNewDrama} className="space-y-3.5 text-xs">
              <div>
                <label className="block font-bold text-slate-700 mb-1">
                  剧集名称 <span className="text-rose-500">*</span>
                </label>
                <input
                  type="text"
                  required
                  value={newDramaName}
                  onChange={(e) => setNewDramaName(e.target.value)}
                  placeholder="例如：重返八零：我成了首富"
                  className="w-full px-3 py-2 rounded-xl border border-slate-200 bg-slate-50 focus:bg-white focus:outline-none focus:border-[#1A1D2E] font-bold text-[#1A1D2E]"
                />
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block font-bold text-slate-700 mb-1">
                    所属剧场
                  </label>
                  <input
                    type="text"
                    disabled
                    value={lockedTheaterName || '青柠剧场'}
                    className="w-full px-3 py-2 rounded-xl border border-slate-200 bg-slate-100 text-slate-500 font-bold cursor-not-allowed"
                  />
                </div>

                <div>
                  <label className="block font-bold text-slate-700 mb-1">
                    题材分类
                  </label>
                  <select
                    value={newDramaCategory}
                    onChange={(e) => setNewDramaCategory(e.target.value)}
                    className="w-full px-3 py-2 rounded-xl border border-slate-200 bg-slate-50 focus:bg-white focus:outline-none focus:border-[#1A1D2E] font-bold text-[#1A1D2E]"
                  >
                    <option value="都市逆袭">都市逆袭</option>
                    <option value="家庭伦理">家庭伦理</option>
                    <option value="年代致富">年代致富</option>
                    <option value="豪门打脸">豪门打脸</option>
                    <option value="战神爽剧">战神爽剧</option>
                    <option value="银发爆款">银发爆款</option>
                  </select>
                </div>
              </div>

              <div>
                <label className="block font-bold text-slate-700 mb-1">
                  总集数
                </label>
                <input
                  type="number"
                  min={1}
                  max={200}
                  value={newDramaEpisodes}
                  onChange={(e) => setNewDramaEpisodes(Number(e.target.value))}
                  className="w-full px-3 py-2 rounded-xl border border-slate-200 bg-slate-50 focus:bg-white focus:outline-none focus:border-[#1A1D2E] font-bold text-[#1A1D2E]"
                />
              </div>

              <div className="pt-3 border-t border-slate-100 flex items-center justify-end gap-2">
                <button
                  type="button"
                  onClick={() => setIsAddDramaOpen(false)}
                  className="px-3.5 py-1.5 rounded-xl text-xs font-semibold text-slate-500 hover:bg-slate-100 cursor-pointer"
                >
                  取消
                </button>
                <button
                  type="submit"
                  disabled={!newDramaName.trim()}
                  className="px-4 py-2 rounded-xl bg-[#1A1D2E] hover:bg-black text-[#DDFD00] text-xs font-bold transition-all shadow-xs cursor-pointer disabled:opacity-40"
                >
                  创建并直接勾选
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      <DramaRenameModal
        isOpen={isAddDramaOpen}
        onClose={() => setIsAddDramaOpen(false)}
        drama={null}
        theaters={theaters}
        lockedTheaterName={lockedTheaterName || undefined}
        onSave={(data) => {
          onCreateDrama(data).then((created) => {
            setDramaList((items) => [created, ...items]);
            setSelectedDramaIds((ids) => [...ids, created.id]);
            setIsAddDramaOpen(false);
            setAddDramaToast(`已新建剧集《${created.name}》并自动加入当前已选`);
            setTimeout(() => setAddDramaToast(null), 3000);
          }).catch((error: unknown) => setAddDramaToast(error instanceof Error ? error.message : '剧集创建失败。'));
        }}
      />

      {/* Floating Toast Notification inside Modal */}
      {addDramaToast && (
        <div className="fixed bottom-6 left-6 z-60 flex items-center gap-2 px-4 py-2.5 rounded-2xl bg-[#1A1D2E] text-white text-xs font-bold shadow-2xl border border-white/10 animate-in fade-in slide-in-from-bottom-2 duration-150">
          <div className="w-4 h-4 rounded-full bg-[#DDFD00] text-[#1A1D2E] flex items-center justify-center font-bold">
            <Check className="w-3 h-3 stroke-[3]" />
          </div>
          <span>{addDramaToast}</span>
        </div>
      )}
    </div>
  );
};
