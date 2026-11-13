import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { AlertTriangle, ArrowDown, ArrowUp, ArrowUpDown, Check, ChevronDown, RefreshCw, Search, ShieldCheck } from 'lucide-react';
import { loadAccountDataOverview, refreshAccountData, type AccountDataOverview, type AccountDataSnapshot } from '../../api/accountData';

type MetricKey = 'fansTotal' | 'view' | 'fansAdd' | 'fansNet' | 'fansReduce' | 'like' | 'favorite' | 'comment' | 'forward';
type AccountRow = { account: AccountDataOverview['accounts'][number]; snapshot?: AccountDataSnapshot; daily: Record<string, unknown> | null; status: 'record' | 'missing' | 'unknown' | 'failed' | 'unavailable' };

const METRICS: Array<{ key: MetricKey; label: string }> = [
  { key: 'fansTotal', label: '粉丝总量' },
  { key: 'view', label: '播放量' },
  { key: 'fansAdd', label: '新增粉丝' },
  { key: 'fansNet', label: '净增粉丝' },
  { key: 'fansReduce', label: '掉粉' },
  { key: 'like', label: '点赞' },
  { key: 'favorite', label: '收藏' },
  { key: 'comment', label: '评论' },
  { key: 'forward', label: '转发' },
];
const dateOffset = (days: number) => { const value = new Date(); value.setHours(12, 0, 0, 0); value.setDate(value.getDate() + days); return `${value.getFullYear()}-${String(value.getMonth() + 1).padStart(2, '0')}-${String(value.getDate()).padStart(2, '0')}`; };

const METRIC_ALIASES: Record<MetricKey, string[]> = {
  fansTotal: ['fansTotal', 'fans', '粉丝总量'],
  view: ['view', 'views', 'playCount', '播放量'],
  fansAdd: ['fansAdd', 'fans_add', '新增粉丝'],
  fansNet: ['fansNet', 'fans_net', '净增粉丝'],
  fansReduce: ['fansReduce', 'fans_reduce', '掉粉'],
  like: ['like', 'likes', '点赞'],
  favorite: ['favorite', 'favorites', '收藏'],
  comment: ['comment', 'comments', '评论'],
  forward: ['forward', 'forwards', 'share', '转发'],
};

export const AccountDataModule: React.FC<{ showToast: (message: string) => void }> = ({ showToast }) => {
  const [data, setData] = useState<AccountDataOverview | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState('');
  const [startDate, setStartDate] = useState(() => dateOffset(-7));
  const [endDate, setEndDate] = useState(() => dateOffset(-1));
  const [search, setSearch] = useState('');
  const [sortKey, setSortKey] = useState<MetricKey>('view');
  const [sortDirection, setSortDirection] = useState<'asc' | 'desc'>('desc');
  const [showUnavailable, setShowUnavailable] = useState(false);
  const [trendMetric, setTrendMetric] = useState<MetricKey>('view');

  const reload = useCallback(async (collectionDay?: string) => {
    try {
      const next = await loadAccountDataOverview(collectionDay || startDate || undefined, collectionDay ? undefined : endDate || undefined);
      setData(next);
      setError('');
      if (!startDate && !endDate) { setStartDate(next.collection_day); setEndDate(next.collection_day); }
      return next;
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : '账号数据读取失败');
      return null;
    } finally { setLoading(false); }
  }, [startDate, endDate]);

  useEffect(() => { void reload(); }, [reload]);
  useEffect(() => {
    if (!data?.active_run) return undefined;
    const timer = window.setInterval(() => { void reload(); }, 1500);
    return () => window.clearInterval(timer);
  }, [data?.active_run, reload]);

  const rows = useMemo<AccountRow[]>(() => (data?.accounts || []).map((account) => {
    const snapshot = data?.snapshots.find((item) => (item.account_id === account.id || item.uid === account.uid) && item.collection_day === data.collection_day);
    const status: AccountRow['status'] = snapshot?.status === 'unavailable' ? 'unavailable'
      : snapshot?.status === 'failed' ? 'failed'
        : snapshot?.data_state === 'record' ? 'record'
          : snapshot?.data_state === 'no_daily_record' ? 'missing' : 'unknown';
    return { account, snapshot, status, daily: status === 'record' && snapshot ? getDailyRecord(snapshot, data?.collection_day || '') : null };
  }), [data]);

  const eligibleRows = useMemo(() => rows.filter((row) => row.status === 'record' && matches(row, search)), [rows, search]);
  const sortedRows = useMemo(() => [...eligibleRows].sort((a, b) => {
    const left = metricNumber(a.daily, sortKey);
    const right = metricNumber(b.daily, sortKey);
    return (sortDirection === 'desc' ? right - left : left - right) || a.account.nickname.localeCompare(b.account.nickname, 'zh-CN');
  }), [eligibleRows, sortDirection, sortKey]);
  const totals = useMemo(() => METRICS.reduce((result, metric) => {
    result[metric.key] = rows.reduce((sum, row) => row.status === 'record' ? sum + metricNumber(row.daily, metric.key) : sum, 0);
    return result;
  }, {} as Record<MetricKey, number>), [rows]);
  const issues = rows.filter((row) => row.status !== 'record');
  const unavailableCount = issues.filter((row) => row.status === 'unavailable').length;
  const missingCount = issues.filter((row) => row.status === 'missing').length;
  const trend = useMemo(() => {
    const points = new Map<string, { total: number; accounts: number }>();
    for (const snapshot of data?.snapshots || []) {
      if (snapshot.data_state !== 'record' || snapshot.status !== 'success') continue;
      const daily = getDailyRecord(snapshot, snapshot.collection_day);
      if (!daily) continue;
      const point = points.get(snapshot.collection_day) || { total: 0, accounts: 0 };
      point.total += metricNumber(daily, trendMetric);
      point.accounts += 1;
      points.set(snapshot.collection_day, point);
    }
    return [...points.entries()].sort(([left], [right]) => left.localeCompare(right)).map(([date, point]) => ({ date, ...point }));
  }, [data, trendMetric]);

  const handleRefresh = async () => {
    try {
      if (!startDate || !endDate) throw new Error('请选择开始日期和结束日期');
      if (startDate > endDate) throw new Error('结束日期不能早于开始日期');
      setRefreshing(true); setError('');
      const result = await refreshAccountData(undefined, false, startDate, endDate);
      if (result.status === 'skipped') showToast(result.message || '所选日期已获取，未重复访问平台。');
      else showToast(`已开始获取 ${result.account_count} 个账号的 ${startDate} 至 ${endDate} 数据。`);
      await reload();
    } catch (cause) { setError(cause instanceof Error ? cause.message : '账号数据获取启动失败'); }
    finally { setRefreshing(false); }
  };

  const toggleSort = (key: MetricKey) => {
    if (sortKey === key) setSortDirection((direction) => direction === 'desc' ? 'asc' : 'desc');
    else { setSortKey(key); setSortDirection('desc'); }
  };

  return <section className="space-y-5 text-slate-900">
    <header className="flex flex-wrap items-end justify-between gap-4">
      <div><div className="text-xs font-medium text-teal-700">运营数据 / 视频号</div><h2 className="mt-1 text-xl font-semibold">账号表现</h2><p className="mt-1 text-sm text-slate-500">{data?.collection_day || '读取中'} · 统计仅使用 V3 已保存快照</p></div>
      <button type="button" onClick={() => void handleRefresh()} disabled={loading || refreshing || Boolean(data?.active_run)} className="inline-flex h-9 items-center gap-2 rounded-md bg-slate-900 px-3 text-sm font-medium text-white hover:bg-slate-700 disabled:opacity-50" title="先刷新小V猫平台数据，再保存到 V3"><RefreshCw className={`h-4 w-4 ${refreshing || data?.active_run ? 'animate-spin' : ''}`} />{data?.active_run ? '正在获取' : '获取所选日期'}</button>
    </header>

    <div className="flex flex-wrap items-end gap-3 border-y border-slate-200 py-3">
      <label className="text-xs text-slate-500">开始日期<input aria-label="开始日期" type="date" value={startDate} onChange={(event) => setStartDate(event.target.value)} className="mt-1 block h-9 rounded-md border border-slate-300 bg-white px-2 text-sm text-slate-800" /></label>
      <label className="text-xs text-slate-500">结束日期<input aria-label="结束日期" type="date" value={endDate} onChange={(event) => setEndDate(event.target.value)} className="mt-1 block h-9 rounded-md border border-slate-300 bg-white px-2 text-sm text-slate-800" /></label>
      <button type="button" onClick={() => void reload()} disabled={loading || !startDate || !endDate} className="h-9 rounded-md border border-slate-300 px-3 text-sm font-medium text-slate-700 hover:bg-slate-50 disabled:opacity-50">应用范围</button>
      <span className="pb-2 text-xs text-slate-400">分析范围最多 90 天；读取本地快照不会访问小V猫</span>
    </div>

    {error && <div role="alert" className="border-l-4 border-red-500 bg-red-50 px-3 py-2 text-sm text-red-700">{error}</div>}
    {data?.latest_run?.status === 'failed' && data.latest_run.error_message && <div role="alert" className="border-l-4 border-red-500 bg-red-50 px-3 py-2 text-sm text-red-700">最近一次获取未完成：{data.latest_run.error_message}</div>}
    {loading && <div role="status" className="py-16 text-center text-sm text-slate-500">正在读取本地账号快照…</div>}

    {!loading && data && <>
      <section aria-label="所选日期汇总" className="grid grid-cols-2 gap-x-5 gap-y-3 border-b border-slate-200 pb-4 sm:grid-cols-4 xl:grid-cols-7">
        <Summary label="已登记账号" value={rows.length} />
        <Summary label="有数据账号" value={rows.filter((row) => row.status === 'record').length} />
        <Summary label="总播放" value={totals.view} accent />
        <Summary label="粉丝总量" value={totals.fansTotal} />
        <Summary label="新增粉丝" value={totals.fansAdd} />
        <Summary label="点赞互动" value={totals.like} />
        <Summary label="待处理账号" value={issues.length} warning={issues.length > 0} />
      </section>

      <section className="border-b border-slate-200 pb-4" aria-label="账号流量趋势">
        <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
          <div><h3 className="text-sm font-semibold">每日趋势</h3><p className="mt-0.5 text-xs text-slate-500">只汇总该日存在每日记录的账号；柱下数字为纳入账号数。</p></div>
          <label className="text-xs text-slate-500">指标<select aria-label="趋势指标" value={trendMetric} onChange={(event) => setTrendMetric(event.target.value as MetricKey)} className="ml-2 h-8 rounded-md border border-slate-300 bg-white px-2 text-sm text-slate-800">{METRICS.map((metric) => <option key={metric.key} value={metric.key}>{metric.label}</option>)}</select></label>
        </div>
        {trend.length ? <div className="grid min-h-44 grid-flow-col auto-cols-fr items-end gap-2 border-b border-slate-200 px-1 pt-3">
          {trend.map((point) => { const max = Math.max(...trend.map((item) => item.total), 1); const height = Math.max(4, Math.round(point.total / max * 100)); return <div key={point.date} className="flex h-40 min-w-0 flex-col items-center justify-end gap-1" title={`${point.date}: ${formatNumber(point.total)}，${point.accounts} 个账号有记录`}><span className="text-[10px] tabular-nums text-slate-500">{formatNumber(point.total)}</span><div className="w-full max-w-12 rounded-t-sm bg-teal-600" style={{ height: `${height}%` }} /><span className="mb-1 text-[10px] text-slate-500">{point.date.slice(5)}</span><span className="text-[9px] text-slate-400">{point.accounts} 账</span></div>; })}
        </div> : <div className="py-10 text-center text-sm text-slate-400">所选范围还没有可绘制的账号每日记录</div>}
      </section>

      <div className="flex flex-wrap items-center justify-between gap-3">
        <div><h3 className="text-sm font-semibold">账号排行</h3><p className="mt-0.5 text-xs text-slate-500">只比较所选日期有每日记录的账号；合计不包含无记录、失效或失败账号。</p></div>
        <label className="relative block"><Search className="pointer-events-none absolute left-2.5 top-2.5 h-4 w-4 text-slate-400" /><input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="搜索账号" aria-label="搜索账号" className="h-9 w-52 rounded-md border border-slate-300 bg-white pl-8 pr-3 text-sm outline-none focus:border-teal-600" /></label>
      </div>

      <div className="overflow-x-auto border-y border-slate-200">
        <table className="w-full min-w-[900px] border-collapse text-left text-sm">
          <thead className="bg-slate-50 text-xs text-slate-500"><tr>
            <th className="w-12 px-3 py-2.5 font-medium">#</th><th className="min-w-52 px-3 py-2.5 font-medium">账号</th>
            {METRICS.map((metric) => <th key={metric.key} className="px-3 py-2.5 text-right font-medium"><button type="button" onClick={() => toggleSort(metric.key)} className="inline-flex items-center gap-1 hover:text-slate-900">{metric.label}{sortKey === metric.key ? (sortDirection === 'desc' ? <ArrowDown className="h-3.5 w-3.5" /> : <ArrowUp className="h-3.5 w-3.5" />) : <ArrowUpDown className="h-3.5 w-3.5 opacity-40" />}</button></th>)}
          </tr></thead>
          <tbody className="divide-y divide-slate-100">
            {sortedRows.map((row, index) => <tr key={row.account.id} className="hover:bg-slate-50/70">
              <td className="px-3 py-3 text-xs tabular-nums text-slate-400">{index + 1}</td>
              <td className="px-3 py-3"><div className="font-medium text-slate-800">{row.account.nickname}</div><div className="mt-0.5 font-mono text-[11px] text-slate-400">{row.account.uid}</div></td>
              {METRICS.map((metric) => <td key={metric.key} className={`px-3 py-3 text-right tabular-nums ${metric.key === sortKey ? 'font-semibold text-slate-900' : 'text-slate-700'}`}>{formatValue(readMetric(row.daily, metric.key))}</td>)}
            </tr>)}
            {!sortedRows.length && <tr><td colSpan={2 + METRICS.length} className="px-3 py-12 text-center text-sm text-slate-500">{search ? '没有匹配的有效账号' : '所选日期暂无已确认的每日记录'}</td></tr>}
          </tbody>
          {sortedRows.length > 0 && <tfoot className="border-t border-slate-200 bg-slate-50 font-semibold"><tr><td className="px-3 py-3" colSpan={2}>有记录账号合计</td>{METRICS.map((metric) => <td key={metric.key} className="px-3 py-3 text-right tabular-nums">{formatNumber(sortedRows.reduce((sum, row) => sum + metricNumber(row.daily, metric.key), 0))}</td>)}</tr></tfoot>}
        </table>
      </div>

      {issues.length > 0 && <section className="border-b border-slate-200 pb-2">
        <button type="button" onClick={() => setShowUnavailable((value) => !value)} aria-expanded={showUnavailable} className="flex w-full items-center justify-between py-2 text-left">
          <span className="flex items-center gap-2 text-sm font-semibold">数据状态 <span className="text-xs font-normal text-slate-500">{unavailableCount} 个失效 · {missingCount} 个无每日记录 · {issues.length - unavailableCount - missingCount} 个其他</span></span>
          <ChevronDown className={`h-4 w-4 text-slate-500 transition-transform ${showUnavailable ? 'rotate-180' : ''}`} />
        </button>
        {showUnavailable && <div className="divide-y divide-slate-100">
          {issues.map((row) => <div key={row.account.id} className="flex flex-wrap items-center justify-between gap-2 py-2.5 text-sm">
            <div><span className="font-medium">{row.account.nickname}</span><span className="ml-2 font-mono text-xs text-slate-400">{row.account.uid}</span></div>
            <div className={`flex items-center gap-1.5 text-xs ${row.status === 'failed' ? 'text-red-700' : 'text-amber-700'}`} title={row.snapshot?.error_message || undefined}><AlertTriangle className="h-3.5 w-3.5" />{statusLabel(row.status)}</div>
          </div>)}
        </div>}
      </section>}

      <div className="flex items-start gap-2 text-xs leading-5 text-slate-500"><ShieldCheck className="mt-0.5 h-4 w-4 shrink-0 text-teal-700" /><span>无每日记录不等于数据为 0。仅将平台返回了该日期记录的账号纳入排行及合计；有记录且指标为 0 才按 0 统计。收益单独按剧场口径获取，不混入此处。</span></div>
      {data.snapshots.some((item) => item.status === 'success') && <details className="border-t border-slate-200 pt-3"><summary className="cursor-pointer text-xs font-medium text-slate-500 hover:text-slate-800">查看原始 MCP 返回</summary><pre className="mt-3 max-h-96 overflow-auto rounded-md bg-slate-950 p-4 text-xs text-slate-200">{JSON.stringify(data.snapshots.filter((item) => item.status === 'success'), null, 2)}</pre></details>}
    </>}
  </section>;
};

function getDailyRecord(snapshot: AccountDataSnapshot, day: string): Record<string, unknown> | null {
  if (!snapshot.payload || typeof snapshot.payload !== 'object') return null;
  const daily = (snapshot.payload as { daily?: unknown }).daily;
  if (!Array.isArray(daily)) return null;
  const record = daily.find((item) => item && typeof item === 'object' && (item as { date?: unknown }).date === day);
  return record && typeof record === 'object' ? record as Record<string, unknown> : null;
}

function readMetric(daily: Record<string, unknown> | null, key: MetricKey): unknown {
  if (!daily) return null;
  const field = METRIC_ALIASES[key].find((candidate) => Object.prototype.hasOwnProperty.call(daily, candidate));
  return field ? daily[field] : null;
}

function metricNumber(daily: Record<string, unknown> | null, key: MetricKey): number {
  const value = readMetric(daily, key);
  return typeof value === 'number' && Number.isFinite(value) ? value : typeof value === 'string' && value.trim() && Number.isFinite(Number(value)) ? Number(value) : 0;
}

function matches(row: AccountRow, query: string): boolean {
  const term = query.trim().toLocaleLowerCase();
  return !term || row.account.nickname.toLocaleLowerCase().includes(term) || row.account.uid.toLocaleLowerCase().includes(term);
}

function formatNumber(value: number): string { return value.toLocaleString('zh-CN'); }
function formatValue(value: unknown): string { return value === null || value === undefined || value === '' ? '—' : typeof value === 'number' ? formatNumber(value) : String(value); }
function statusLabel(status: AccountRow['status']): string {
  if (status === 'unavailable') return '账号已失效';
  if (status === 'missing') return '刷新成功，但无每日记录';
  if (status === 'failed') return '获取失败';
  return status === 'unknown' ? '尚未获取或旧快照待确认' : '有每日记录';
}

function Summary({ label, value, accent = false, warning = false }: { label: string; value: number; accent?: boolean; warning?: boolean }) {
  return <div className="min-w-0"><div className="text-xs text-slate-500">{label}</div><div className={`mt-1 text-xl font-semibold tabular-nums ${warning ? 'text-amber-700' : accent ? 'text-teal-700' : 'text-slate-900'}`}>{formatNumber(value)}</div></div>;
}
