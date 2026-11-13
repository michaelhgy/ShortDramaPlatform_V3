import React, { useEffect, useMemo, useState } from 'react';
import { RevenueCollectionLog } from '../../analyticsTypes';
import { getV2Accounts, type V2AccountRecord } from '../../api/v2Catalog';
import type { RevenueCollectionProgress } from '../../services/revenueAnalyticsService';
import { X, DownloadCloud, RefreshCw, CheckCircle2, AlertCircle, Clock, Play, History, FileCheck } from 'lucide-react';

interface RevenueCollectionDrawerProps {
  isOpen: boolean;
  onClose: () => void;
  logs: RevenueCollectionLog[];
  onTriggerCollect: (scope: string, mode: 'immediate' | 'backfill', startDate: string, endDate: string, targets?: { theaters?: string[]; accountIds?: string[] }, onProgress?: (progress: RevenueCollectionProgress) => void) => Promise<void>;
}

const localDateOffset = (days: number) => {
  const value = new Date();
  value.setHours(12, 0, 0, 0);
  value.setDate(value.getDate() + days);
  return `${value.getFullYear()}-${String(value.getMonth() + 1).padStart(2, '0')}-${String(value.getDate()).padStart(2, '0')}`;
};
const yesterday = () => localDateOffset(-1);
const recentSevenDaysStart = () => localDateOffset(-7);
const statusText = { success: '成功', no_data: '无数据', failed: '失败', indeterminate: '待确认' } as const;

export const RevenueCollectionDrawer: React.FC<RevenueCollectionDrawerProps> = ({ isOpen, onClose, logs, onTriggerCollect }) => {
  const [collectMode, setCollectMode] = useState<'immediate' | 'backfill'>('immediate');
  const [startDate, setStartDate] = useState(yesterday);
  const [endDate, setEndDate] = useState(yesterday);
  const [isCollecting, setIsCollecting] = useState(false);
  const [collectionProgress, setCollectionProgress] = useState<RevenueCollectionProgress | null>(null);
  const [error, setError] = useState('');
  const [status, setStatus] = useState<'all' | RevenueCollectionLog['status']>('all');
  const [recordDateRange, setRecordDateRange] = useState<'yesterday' | '7days' | 'custom'>('7days');
  const [recordStartDate, setRecordStartDate] = useState(recentSevenDaysStart);
  const [recordEndDate, setRecordEndDate] = useState(yesterday);
  const [recordTheater, setRecordTheater] = useState('all');
  const [recordAccount, setRecordAccount] = useState('all');
  const [scope, setScope] = useState<'all' | 'theater' | 'account'>('all');
  const [theater, setTheater] = useState('青柠剧场');
  const [accounts, setAccounts] = useState<V2AccountRecord[]>([]);
  const [accountId, setAccountId] = useState('');

  useEffect(() => { if (isOpen) getV2Accounts().then((result) => setAccounts(result.items)).catch(() => setAccounts([])); }, [isOpen]);

  const latestLogs = useMemo(() => {
    const seen = new Set<string>();
    const latest = [...logs].sort((left, right) => right.updatedAt.localeCompare(left.updatedAt) || right.id.localeCompare(left.id)).filter((log) => {
      const key = `${log.theaterName}\u0000${log.accountName}\u0000${log.period}`;
      if (seen.has(key)) return false;
      seen.add(key);
      return true;
    });
    return latest.sort((left, right) => right.period.localeCompare(left.period) || right.updatedAt.localeCompare(left.updatedAt) || right.id.localeCompare(left.id));
  }, [logs]);
  const recordTheaters = useMemo(() => Array.from(new Set([...latestLogs.map((item) => item.theaterName), ...accounts.map((item) => item.theater_name)])).filter(Boolean).sort(), [latestLogs, accounts]);
  const recordAccounts = useMemo(() => {
    const options = new Map<string, { value: string; accountName: string; theaterName: string }>();
    accounts.forEach((item) => options.set(`${item.theater_name}\u0000${item.nickname}`, { value: `${item.theater_name}\u0000${item.nickname}`, accountName: item.nickname, theaterName: item.theater_name }));
    latestLogs.forEach((item) => options.set(`${item.theaterName}\u0000${item.accountName}`, { value: `${item.theaterName}\u0000${item.accountName}`, accountName: item.accountName, theaterName: item.theaterName }));
    return Array.from(options.values()).filter((item) => recordTheater === 'all' || item.theaterName === recordTheater).sort((left, right) => left.accountName.localeCompare(right.accountName, 'zh-CN'));
  }, [accounts, latestLogs, recordTheater]);
  const scopedLogs = useMemo(() => latestLogs.filter((log) => {
    if (recordTheater !== 'all' && log.theaterName !== recordTheater) return false;
    if (recordAccount !== 'all' && `${log.theaterName}\u0000${log.accountName}` !== recordAccount) return false;
    if (recordStartDate && log.period < recordStartDate) return false;
    if (recordEndDate && log.period > recordEndDate) return false;
    return true;
  }), [latestLogs, recordTheater, recordAccount, recordStartDate, recordEndDate]);
  const filteredLogs = useMemo(() => scopedLogs.filter((log) => status === 'all' || log.status === status), [scopedLogs, status]);
  const summary = useMemo(() => ({ success: scopedLogs.filter((item) => item.status === 'success').length, noData: scopedLogs.filter((item) => item.status === 'no_data').length, failed: scopedLogs.filter((item) => item.status === 'failed').length }), [scopedLogs]);
  const recordDateRangeInvalid = Boolean(recordStartDate && recordEndDate && recordEndDate < recordStartDate);

  if (!isOpen) return null;
  const startCollection = async () => {
    if (!startDate || !endDate) { setError('请选择完整的采集日期'); return; }
    if (endDate < startDate) { setError('截止日期不能早于起始日期'); return; }
    const selectedAccount = accounts.find((item) => item.id === accountId);
    if (scope === 'account' && !selectedAccount) { setError('请选择要采集的账号'); return; }
    setIsCollecting(true); setError(''); setCollectionProgress(null);
    try { await onTriggerCollect(scope, collectMode, startDate, endDate, { theaters: scope === 'all' ? undefined : [scope === 'account' ? selectedAccount!.theater_name : theater], accountIds: scope === 'account' ? [accountId] : undefined }, setCollectionProgress); }
    catch (reason) { setError(reason instanceof Error ? reason.message : '收益采集失败'); }
    finally { setIsCollecting(false); }
  };
  const chooseImmediate = () => { const value = yesterday(); setCollectMode('immediate'); setStartDate(value); setEndDate(value); };
  const chooseBackfill = () => { setCollectMode('backfill'); setStartDate(recentSevenDaysStart()); setEndDate(yesterday()); };
  const chooseRecordDateRange = (range: 'yesterday' | '7days' | 'custom') => {
    setRecordDateRange(range);
    if (range === 'yesterday') { const value = yesterday(); setRecordStartDate(value); setRecordEndDate(value); }
    if (range === '7days') { setRecordStartDate(recentSevenDaysStart()); setRecordEndDate(yesterday()); }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4 backdrop-blur-xs animate-in fade-in duration-150">
      <div className="flex h-[min(920px,calc(100vh-32px))] w-full max-w-6xl flex-col overflow-hidden rounded-2xl border border-black/10 bg-white shadow-2xl animate-in zoom-in-95 duration-150">
        <div className="flex shrink-0 items-center justify-between bg-[#1A1D2E] px-5 py-4 text-white"><div className="flex items-center gap-2.5"><div className="flex h-9 w-9 items-center justify-center rounded-xl bg-white/10 text-[#DDFD00]"><DownloadCloud className="h-4 w-4" /></div><div><h3 className="text-sm font-bold">收益与数据采集中心</h3><p className="text-[11px] text-slate-300">已接入剧场 · 手动采集、补采与采集记录</p></div></div><button onClick={onClose} className="rounded-lg p-1.5 text-slate-300 hover:bg-white/10 hover:text-white"><X className="h-4 w-4" /></button></div>
        <div className="flex-1 overflow-y-auto bg-slate-50/70 p-5">
          <section className="rounded-2xl border border-black/[0.06] bg-white p-4 shadow-xs">
            <div className="mb-3 flex items-center justify-between"><div><h4 className="text-sm font-bold text-[#1A1D2E]">发起收益采集</h4><p className="mt-0.5 text-[11px] text-[#64748B]">采集已接入的青柠、顶好、触摸、花生；停用及注销账号自动跳过。</p></div><span className="rounded-lg bg-emerald-50 px-2.5 py-1 text-[11px] font-semibold text-emerald-700">4 个已接入剧场</span></div>
            <div className="mb-3 flex flex-wrap items-center gap-2 rounded-xl border border-black/[0.06] bg-slate-50 p-2"><div className="flex rounded-xl border border-black/[0.06] bg-white p-0.5 text-xs">{([['all', '全部已接入'], ['theater', '按剧场'], ['account', '按账号']] as const).map(([key, label]) => <button key={key} onClick={() => setScope(key)} className={`rounded-lg px-3 py-1.5 font-medium ${scope === key ? 'bg-[#1A1D2E] text-white' : 'text-[#64748B] hover:bg-slate-100'}`}>{label}</button>)}</div>{scope === 'theater' && <select value={theater} onChange={(event) => setTheater(event.target.value)} className="rounded-xl border border-black/[0.06] bg-white px-3 py-1.5 text-xs outline-none"><option>青柠剧场</option><option>顶好剧场</option><option>触摸剧场</option><option>花生剧场</option></select>}{scope === 'account' && <select value={accountId} onChange={(event) => setAccountId(event.target.value)} className="min-w-[180px] rounded-xl border border-black/[0.06] bg-white px-3 py-1.5 text-xs outline-none"><option value="">选择账号</option>{accounts.filter((item) => item.status !== '注销').map((item) => <option key={item.id} value={item.id}>{item.theater_name} · {item.nickname}</option>)}</select>}<span className="text-[11px] text-[#64748B]">{scope === 'all' ? '将按各剧场实际能力采集' : scope === 'theater' ? '只采所选剧场' : '只采所选账号'}</span></div>
            <div className="grid gap-3 lg:grid-cols-[1fr_210px_210px_170px] lg:items-center"><div className="grid grid-cols-2 gap-2"><button onClick={chooseImmediate} className={`rounded-xl border p-2.5 text-left transition-all ${collectMode === 'immediate' ? 'border-[#1A1D2E] bg-[#1A1D2E] text-white' : 'border-black/[0.06] bg-slate-50 text-[#1A1D2E] hover:bg-slate-100'}`}><div className="flex items-center gap-1.5 text-xs font-bold"><RefreshCw className="h-3.5 w-3.5" />同步昨日</div><div className={`mt-0.5 text-[10px] ${collectMode === 'immediate' ? 'text-slate-300' : 'text-[#64748B]'}`}>读取昨日结算数据</div></button><button onClick={chooseBackfill} className={`rounded-xl border p-2.5 text-left transition-all ${collectMode === 'backfill' ? 'border-[#1A1D2E] bg-[#1A1D2E] text-white' : 'border-black/[0.06] bg-slate-50 text-[#1A1D2E] hover:bg-slate-100'}`}><div className="flex items-center gap-1.5 text-xs font-bold"><History className="h-3.5 w-3.5" />历史补采</div><div className={`mt-0.5 text-[10px] ${collectMode === 'backfill' ? 'text-slate-300' : 'text-[#64748B]'}`}>补全指定日期</div></button></div><label className="flex items-center gap-2 whitespace-nowrap text-[11px] font-medium text-[#64748B]">起始日期<input type="date" value={startDate} onChange={(event) => setStartDate(event.target.value)} className="min-w-0 flex-1 rounded-xl border border-black/[0.06] bg-slate-50 px-2.5 py-2 text-xs text-[#1A1D2E] outline-none" /></label><label className="flex items-center gap-2 whitespace-nowrap text-[11px] font-medium text-[#64748B]">截止日期<input type="date" value={endDate} onChange={(event) => setEndDate(event.target.value)} className="min-w-0 flex-1 rounded-xl border border-black/[0.06] bg-slate-50 px-2.5 py-2 text-xs text-[#1A1D2E] outline-none" /></label><button disabled={isCollecting} onClick={startCollection} className="flex h-[38px] items-center justify-center gap-2 rounded-xl bg-[#1A1D2E] px-4 text-xs font-bold text-[#DDFD00] shadow-sm transition-all hover:bg-black/90 disabled:cursor-wait disabled:opacity-70"><Play className={`h-3.5 w-3.5 ${isCollecting ? 'animate-pulse' : 'fill-current'}`} />{isCollecting ? '正在采集…' : '开始采集'}</button></div>
            {isCollecting && <div className="mt-3 rounded-xl border border-black/[0.06] bg-slate-50 p-3"><div className="flex items-center justify-between gap-3 text-xs"><span className="flex min-w-0 items-center gap-1.5 font-bold text-[#1A1D2E]"><RefreshCw className="h-3.5 w-3.5 shrink-0 animate-spin text-emerald-600" />{collectionProgress?.current_account ? `正在读取：${collectionProgress.current_theater} · ${collectionProgress.current_account}` : '正在准备采集任务…'}</span><span className="shrink-0 font-mono font-bold text-emerald-700">{collectionProgress ? `${collectionProgress.completed_units} / ${collectionProgress.total_units}` : '0 / —'}</span></div><div className="mt-2 h-1.5 overflow-hidden rounded-full bg-slate-200"><div style={{ width: `${collectionProgress?.total_units ? Math.min(100, Math.round(collectionProgress.completed_units / collectionProgress.total_units * 100)) : 0}%` }} className="h-full rounded-full bg-emerald-500 transition-all duration-300" /></div>{collectionProgress && <div className="mt-2 flex flex-wrap gap-x-3 gap-y-1 text-[11px]"><span className="text-emerald-700">成功 {collectionProgress.success_units}</span><span className="text-amber-700">无结算数据 {collectionProgress.no_data_units}</span><span className="text-rose-700">失败 {collectionProgress.failed_units}</span></div>}</div>}
            {error && <div className="mt-3 rounded-xl border border-rose-200 bg-rose-50 px-3 py-2 text-xs text-rose-700">{error}</div>}
          </section>
          <section className="mt-4 rounded-2xl border border-black/[0.06] bg-white shadow-xs">
            <div className="border-b border-black/[0.06] p-4">
              <div className="flex flex-wrap items-center justify-between gap-3"><div className="flex flex-wrap items-baseline gap-x-2 gap-y-1"><h4 className="text-sm font-bold text-[#1A1D2E]">采集记录</h4><span className="text-[11px] text-[#64748B]">默认只看每个账号、每个数据日期的最新结果，旧失败不会干扰当前判断。</span></div><span className="text-[11px] text-slate-400">当前显示 {filteredLogs.length} 条</span></div>
              <div className="mt-3"><div className="flex items-center gap-2 text-[11px] font-medium text-[#64748B]"><span className="shrink-0">选择剧场</span><div className="flex min-w-0 flex-1 gap-2 overflow-x-auto pb-1">{['all', ...recordTheaters].map((name) => { const active = recordTheater === name; const label = name === 'all' ? '全部剧场' : name; return <button key={name} onClick={() => { setRecordTheater(name); setRecordAccount('all'); }} className={`shrink-0 rounded-lg px-3 py-1.5 text-xs font-semibold transition-colors ${active ? 'bg-[#1A1D2E] text-[#DDFD00]' : 'bg-slate-50 text-[#42526B] hover:bg-slate-100'}`}>{label}</button>; })}</div></div><div className="mt-2 flex items-center gap-2 text-[11px] font-medium text-[#64748B]"><span className="shrink-0">选择账号</span><div className="flex min-w-0 flex-1 gap-2 overflow-x-auto pb-1"><button onClick={() => setRecordAccount('all')} className={`shrink-0 rounded-lg px-3 py-1.5 text-xs font-semibold transition-colors ${recordAccount === 'all' ? 'bg-[#1A1D2E] text-[#DDFD00]' : 'bg-slate-50 text-[#42526B] hover:bg-slate-100'}`}>全部账号</button>{recordAccounts.map((item) => <button key={item.value} onClick={() => setRecordAccount(item.value)} className={`shrink-0 rounded-lg px-3 py-1.5 text-xs font-semibold transition-colors ${recordAccount === item.value ? 'bg-[#1A1D2E] text-[#DDFD00]' : 'bg-slate-50 text-[#42526B] hover:bg-slate-100'}`}>{item.accountName}</button>)}</div></div></div>
              <div className="mt-2 flex flex-wrap items-center gap-2"><span className="text-[11px] font-medium text-[#64748B]">数据日期</span><div className="flex rounded-xl border border-black/[0.06] bg-slate-50 p-0.5 text-xs">{([['yesterday', '昨日'], ['7days', '最近 7 天'], ['custom', '自定义']] as const).map(([key, label]) => <button key={key} onClick={() => chooseRecordDateRange(key)} className={`rounded-lg px-2.5 py-1.5 font-medium ${recordDateRange === key ? 'bg-white text-[#1A1D2E] shadow-xs' : 'text-[#64748B] hover:bg-white/70'}`}>{label}</button>)}</div>{recordDateRange === 'custom' ? <><label className="ml-1 flex items-center gap-1.5 text-[11px] font-medium text-[#64748B]">起始<input type="date" value={recordStartDate} onChange={(event) => setRecordStartDate(event.target.value)} className="rounded-xl border border-black/[0.06] bg-slate-50 px-2 py-1.5 text-xs outline-none" /></label><label className="flex items-center gap-1.5 text-[11px] font-medium text-[#64748B]">截止<input type="date" value={recordEndDate} onChange={(event) => setRecordEndDate(event.target.value)} className="rounded-xl border border-black/[0.06] bg-slate-50 px-2 py-1.5 text-xs outline-none" /></label>{recordDateRangeInvalid && <span className="text-[11px] font-medium text-rose-600">截止日期不能早于起始日期</span>}</> : <span className="ml-1 text-[11px] font-medium text-[#64748B]">{recordDateRange === 'yesterday' ? recordEndDate : `${recordStartDate} 至 ${recordEndDate}`}</span>}</div>
              <div className="mt-3 flex flex-wrap gap-2 text-[11px]"><button onClick={() => setStatus('all')} className={`rounded-lg px-2.5 py-1 font-medium ${status === 'all' ? 'bg-[#1A1D2E] text-white' : 'bg-slate-50 text-slate-600 hover:bg-slate-100'}`}>全部 {scopedLogs.length}</button><button onClick={() => setStatus('success')} className={`rounded-lg px-2.5 py-1 font-medium ${status === 'success' ? 'bg-emerald-600 text-white' : 'bg-emerald-50 text-emerald-700 hover:bg-emerald-100'}`}>成功 {summary.success}</button><button onClick={() => setStatus('no_data')} className={`rounded-lg px-2.5 py-1 font-medium ${status === 'no_data' ? 'bg-amber-500 text-white' : 'bg-amber-50 text-amber-700 hover:bg-amber-100'}`}>无结算数据 {summary.noData}</button><button onClick={() => setStatus('failed')} className={`rounded-lg px-2.5 py-1 font-medium ${status === 'failed' ? 'bg-rose-600 text-white' : 'bg-rose-50 text-rose-700 hover:bg-rose-100'}`}>失败 {summary.failed}</button></div>
            </div>
            <div className="overflow-x-auto"><table className="w-full min-w-[760px] text-left text-xs"><thead className="bg-slate-50 text-[11px] font-medium text-[#64748B]"><tr><th className="px-4 py-3">采集时间</th><th className="px-4 py-3">数据日期</th><th className="px-4 py-3">剧场 / 账号</th><th className="px-4 py-3">结果</th><th className="px-4 py-3 text-right">读取收益</th><th className="px-4 py-3">说明</th></tr></thead><tbody className="divide-y divide-black/[0.05]">{filteredLogs.map((log) => { const success = log.status === 'success'; const noData = log.status === 'no_data'; return <tr key={log.id} className="hover:bg-slate-50/70"><td className="whitespace-nowrap px-4 py-3 text-[#64748B]">{log.updatedAt}</td><td className="whitespace-nowrap px-4 py-3 font-mono text-[#1A1D2E]">{log.period}</td><td className="px-4 py-3 font-semibold text-[#1A1D2E]"><div>{log.accountName}</div><div className="mt-0.5 text-[10px] font-normal text-slate-400">{log.theaterName}</div></td><td className="px-4 py-3"><span className={`inline-flex items-center gap-1 rounded-lg px-2 py-1 text-[11px] font-semibold ${success ? 'bg-emerald-50 text-emerald-700' : noData ? 'bg-amber-50 text-amber-700' : 'bg-rose-50 text-rose-700'}`}>{success ? <CheckCircle2 className="h-3.5 w-3.5" /> : noData ? <Clock className="h-3.5 w-3.5" /> : <AlertCircle className="h-3.5 w-3.5" />}{success ? statusText.success : noData ? '无结算数据' : statusText[log.status]}</span></td><td className="px-4 py-3 text-right font-mono font-bold text-[#1A1D2E]">{success && log.collectedAmount != null ? `¥${log.collectedAmount.toFixed(2)}` : '—'}</td><td className="max-w-[300px] px-4 py-3 text-[#64748B]">{log.note || '—'}</td></tr>; })}</tbody></table>{filteredLogs.length === 0 && <div className="px-4 py-12 text-center text-sm text-slate-400">没有符合筛选条件的最新采集记录</div>}</div>
          </section>
        </div>
        <div className="flex shrink-0 items-center justify-between border-t border-black/[0.06] bg-slate-50 px-5 py-3 text-[11px] text-[#64748B]"><span className="flex items-center gap-1"><FileCheck className="h-3.5 w-3.5 text-emerald-600" />数据按各剧场真实来源采集，失败和无数据均保留痕迹。</span><button onClick={onClose} className="rounded-lg border border-black/[0.08] bg-white px-3 py-1.5 text-xs font-semibold hover:bg-slate-100">关闭</button></div>
      </div>
    </div>
  );
};
