import React, { useEffect, useMemo, useRef, useState } from 'react';
import { eventDetail } from '../../services/dataChangeEvents';
import {
  Activity, AlertTriangle, ArrowDownRight, ArrowRight, ArrowUpRight, BarChart3,
  CalendarDays, CheckCircle2, ChevronRight, CircleDollarSign, Database, Eye,
  FileWarning, Film, Layers3, RefreshCw, ShieldAlert, Sparkles, Users, WalletCards,
} from 'lucide-react';
import { loadAnalyticsDataBase, type AnalyticsAccountDaily, type AnalyticsDataBase, type AnalyticsPostDaily, type AnalyticsVideoPost } from '../../api/analyticsDataBase';

type ViewMode = 'overview' | 'accounts' | 'posts' | 'revenue';
type RangeMode = '1' | '7' | '30';

type AccountRow = {
  id: string;
  uid: string;
  name: string;
  group: string;
  fans: number;
  views: number;
  fansAdd: number;
  fansNet: number;
  likes: number;
  favorites: number;
  comments: number;
  forwards: number;
  topPost?: PostRow;
  abnormal: boolean;
};

type PostRow = AnalyticsVideoPost & {
  periodViews: number;
  periodLikes: number;
  periodFansAdd: number;
  periodDays: number;
};

const number = (value: number) => Math.round(value).toLocaleString('zh-CN');
const money = (value: number) => `¥${value.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
const compact = (value: number) => value >= 1_000_000 ? `${(value / 1_000_000).toFixed(2)}M` : value >= 10_000 ? `${(value / 10_000).toFixed(1)}万` : number(value);
const percent = (value: number | null) => value === null || !Number.isFinite(value) ? '—' : `${value >= 0 ? '+' : ''}${value.toFixed(1)}%`;
const amount = (value: string | null) => Number.isFinite(Number(value)) ? Number(value) : 0;

function daysBetween(start: string, end: string): string[] {
  const result: string[] = [];
  const cursor = new Date(`${start}T12:00:00`);
  const last = new Date(`${end}T12:00:00`);
  while (cursor <= last) {
    result.push(cursor.toISOString().slice(0, 10));
    cursor.setDate(cursor.getDate() + 1);
  }
  return result;
}

function shiftDate(value: string, days: number): string {
  const date = new Date(`${value}T12:00:00`);
  date.setDate(date.getDate() + days);
  return date.toISOString().slice(0, 10);
}

function metricSum(rows: AnalyticsAccountDaily[], key: keyof AnalyticsAccountDaily): number {
  return rows.reduce((sum, row) => sum + Number(row[key] || 0), 0);
}

function postDailyMap(rows: AnalyticsPostDaily[]): Map<string, AnalyticsPostDaily[]> {
  const map = new Map<string, AnalyticsPostDaily[]>();
  rows.forEach((row) => map.set(row.post_id, [...(map.get(row.post_id) || []), row]));
  return map;
}

export const AnalyticsDashboard: React.FC<{ onScheduleToday?: (dramaId?: string, accountId?: string) => void; showToast: (message: string) => void }> = ({ showToast }) => {
  const [data, setData] = useState<AnalyticsDataBase | null>(null);
  const [mode, setMode] = useState<ViewMode>('overview');
  const [range, setRange] = useState<RangeMode>('7');
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState('');
  const [selectedAccountId, setSelectedAccountId] = useState<string | null>(null);
  const [selectedPostId, setSelectedPostId] = useState<string | null>(null);

  const requestId = useRef(0);
  const load = async () => {
    const request = ++requestId.current;
    try {
      setRefreshing(true);
      const next = await loadAnalyticsDataBase({ sourceKind: 'simulation_ui' });
      if (request !== requestId.current) return;
      setData(next);
      setError('');
    } catch (cause) {
      if (request !== requestId.current) return;
      setError(cause instanceof Error ? cause.message : '分析数据读取失败');
    } finally {
      if (request === requestId.current) {
        setLoading(false);
        setRefreshing(false);
      }
    }
  };

  useEffect(() => {
    void load();
    const changed = (event: Event) => {
      if (eventDetail(event).changeType === 'account_changed') void load();
    };
    window.addEventListener('v2-data-changed', changed);
    return () => { ++requestId.current; window.removeEventListener('v2-data-changed', changed); };
  }, []);

  const latestDate = useMemo(() => {
    const dates = data?.video_account_daily.map((row) => row.stat_date) || [];
    return dates.sort().at(-1) || '2026-10-29';
  }, [data]);
  const startDate = range === '1' ? latestDate : shiftDate(latestDate, range === '30' ? -29 : -6);
  const dates = useMemo(() => daysBetween(startDate, latestDate), [startDate, latestDate]);
  const dailyRows = useMemo(() => (data?.video_account_daily || []).filter((row) => row.stat_date >= startDate && row.stat_date <= latestDate), [data, startDate, latestDate]);
  const postDailyRows = useMemo(() => (data?.video_post_daily || []).filter((row) => row.stat_date >= startDate && row.stat_date <= latestDate), [data, startDate, latestDate]);
  const postDailyById = useMemo(() => postDailyMap(postDailyRows), [postDailyRows]);
  const diagnostics = data?.video_account_diagnostics || [];

  const posts = useMemo<PostRow[]>(() => (data?.video_posts || []).map((post) => {
    const rows = postDailyById.get(post.post_id) || [];
    return {
      ...post,
      periodViews: rows.length ? metricSum(rows, 'view') : post.view,
      periodLikes: metricSum(rows, 'like_count'),
      periodFansAdd: metricSum(rows, 'fans_add'),
      periodDays: rows.length,
    };
  }).sort((left, right) => right.periodViews - left.periodViews), [data, postDailyById]);

  const accounts = useMemo<AccountRow[]>(() => {
    const byAccount = new Map<string, AnalyticsAccountDaily[]>();
    dailyRows.forEach((row) => byAccount.set(row.account_id, [...(byAccount.get(row.account_id) || []), row]));
    return (data?.video_accounts || []).map((account) => {
      const rows = byAccount.get(account.account_id) || [];
      const latest = rows.find((row) => row.stat_date === latestDate) || rows.at(-1);
      const topPost = posts.find((post) => post.account_id === account.account_id);
      const diagnostic = diagnostics.find((item) => item.account_id === account.account_id);
      return {
        id: account.account_id,
        uid: account.uid,
        name: account.account_name,
        group: account.group_name,
        fans: Number(latest?.fans_total ?? account.fans_total),
        views: metricSum(rows, 'view'),
        fansAdd: metricSum(rows, 'fans_add'),
        fansNet: metricSum(rows, 'fans_net'),
        likes: metricSum(rows, 'like_count'),
        favorites: metricSum(rows, 'favorite_count'),
        comments: metricSum(rows, 'comment_count'),
        forwards: metricSum(rows, 'forward_count'),
        topPost,
        abnormal: Boolean(diagnostic?.abnormal),
      };
    }).sort((left, right) => right.views - left.views);
  }, [data, dailyRows, diagnostics, latestDate, posts]);

  const topPerAccount = useMemo(() => accounts.map((account) => account.topPost).filter((post): post is PostRow => Boolean(post)), [accounts]);
  const top10 = posts.slice(0, 10);
  const latestDaily = dailyRows.filter((row) => row.stat_date === latestDate);
  const previousDaily = dailyRows.filter((row) => row.stat_date === shiftDate(latestDate, -1));
  const yesterdayViews = metricSum(latestDaily, 'view');
  const previousViews = metricSum(previousDaily, 'view');
  const yesterdayFans = metricSum(latestDaily, 'fans_add');
  const interaction = metricSum(latestDaily, 'like_count') + metricSum(latestDaily, 'favorite_count') + metricSum(latestDaily, 'comment_count') + metricSum(latestDaily, 'forward_count');
  const viewChange = previousViews ? (yesterdayViews - previousViews) / previousViews * 100 : null;
  const includedRevenue = (data?.revenue_account_periods || []).filter((row) => row.include_in_analysis === 1 && row.period_start <= latestDate && row.period_end >= startDate);
  const currentMonthRevenue = (data?.revenue_account_periods || []).filter((row) => row.include_in_analysis === 1 && row.period_start.startsWith(latestDate.slice(0, 7))).reduce((sum, row) => sum + amount(row.amount), 0);
  const dailyRevenue = dates.map((date) => ({ date, value: includedRevenue.filter((row) => row.period_type === 'day' && row.period_start === date).reduce((sum, row) => sum + amount(row.amount), 0) }));
  const revenueSources = data?.revenue_source_inventory || [];
  const excludedSettled = (data?.revenue_account_periods || []).filter((row) => row.settlement_state === 'settled' && row.include_in_analysis === 0).length;
  const abnormalCount = diagnostics.filter((row) => Boolean(row.abnormal)).length;
  const punishmentCount = data?.video_post_punishments.length || 0;
  const attentionCount = abnormalCount + punishmentCount;
  const selectedAccount = accounts.find((account) => account.id === selectedAccountId);
  const selectedPost = posts.find((post) => post.post_id === selectedPostId);

  if (loading) return <div className="flex min-h-[680px] items-center justify-center rounded-[28px] bg-white/60"><div className="flex items-center gap-3 text-sm text-slate-500"><RefreshCw className="h-4 w-4 animate-spin" />正在加载运营数据中心…</div></div>;
  if (!data) return <div className="rounded-[28px] border border-rose-200 bg-rose-50 p-8 text-rose-800"><div className="flex items-center gap-2 font-semibold"><AlertTriangle className="h-5 w-5" />数据中心暂时无法读取</div><p className="mt-2 text-sm">{error || '本地数据服务没有返回分析底座。'}</p><button type="button" onClick={() => void load()} className="mt-5 rounded-xl bg-slate-900 px-4 py-2 text-sm font-semibold text-white">重新读取</button></div>;

  return <section className="space-y-5 pb-12 text-slate-900">
    <header className="relative overflow-hidden rounded-[30px] border border-white/80 bg-gradient-to-br from-[#fbf8ff] via-white to-[#eef8ff] px-6 py-6 shadow-[0_20px_60px_rgba(79,70,229,0.08)] sm:px-8 sm:py-7">
      <div className="pointer-events-none absolute -right-16 -top-28 h-80 w-80 rounded-full bg-fuchsia-200/35 blur-3xl" />
      <div className="pointer-events-none absolute -bottom-32 left-1/3 h-64 w-64 rounded-full bg-cyan-200/35 blur-3xl" />
      <div className="relative flex flex-wrap items-end justify-between gap-6">
        <div><div className="mb-2 flex items-center gap-2 text-[11px] font-bold tracking-[0.18em] text-violet-600"><Sparkles className="h-4 w-4" />短剧推广运营驾驶舱</div><h1 className="text-3xl font-black tracking-tight text-[#24134f] sm:text-4xl">昨日运营表现</h1><p className="mt-2 max-w-xl text-sm text-slate-500">从账号流量、作品表现到未结算收益，快速看清今天最需要关注的变化。</p></div>
        <div className="flex flex-wrap items-center gap-2"><SourceBadge /><div className="rounded-xl border border-slate-200 bg-white/75 px-3 py-2 text-xs text-slate-600 shadow-sm"><span className="text-slate-400">数据截至</span><strong className="ml-2 text-slate-900">{latestDate}</strong></div><button type="button" onClick={() => { void load(); showToast('已重新读取本地演示数据'); }} disabled={refreshing} className="inline-flex items-center gap-2 rounded-xl bg-[#7c3aed] px-3.5 py-2 text-xs font-bold text-white shadow-sm hover:bg-[#6d28d9] disabled:opacity-60"><RefreshCw className={`h-3.5 w-3.5 ${refreshing ? 'animate-spin' : ''}`} />读取已保存数据</button></div>
      </div>
      <div className="relative mt-6 flex flex-wrap items-center justify-between gap-3 border-t border-violet-100 pt-4"><nav className="flex flex-wrap gap-1 rounded-xl border border-violet-100 bg-white/70 p-1" aria-label="数据中心视图">{([['overview', '驾驶舱'], ['accounts', '账号分析'], ['posts', '作品分析'], ['revenue', '收益分析']] as const).map(([key, label]) => <button key={key} type="button" onClick={() => setMode(key)} className={`rounded-lg px-4 py-2 text-xs font-semibold transition ${mode === key ? 'bg-[#24134f] text-white shadow-sm' : 'text-slate-500 hover:bg-violet-50 hover:text-violet-700'}`}>{label}</button>)}</nav><div className="flex items-center gap-1 rounded-xl border border-violet-100 bg-white/70 p-1">{([['1', '昨日'], ['7', '近7日'], ['30', '近30日']] as const).map(([key, label]) => <button key={key} type="button" onClick={() => setRange(key)} className={`rounded-lg px-3 py-2 text-xs font-semibold ${range === key ? 'bg-fuchsia-200 text-[#24134f]' : 'text-slate-500 hover:bg-violet-50'}`}>{label}</button>)}</div></div>
    </header>

    {error && <div className="flex items-start gap-2 rounded-2xl border border-amber-200 bg-amber-50 px-4 py-3 text-xs text-amber-800"><AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />{error}。当前展示的数据可能不完整。</div>}
    {mode === 'overview' && <OverviewView accounts={accounts} topPerAccount={topPerAccount} top10={top10} latestDate={latestDate} dates={dates} dailyRows={dailyRows} dailyRevenue={dailyRevenue} includedPeriods={includedRevenue} yesterdayViews={yesterdayViews} previousViews={previousViews} yesterdayFans={yesterdayFans} interaction={interaction} viewChange={viewChange} currentMonthRevenue={currentMonthRevenue} activeRevenue={includedRevenue.length} attentionCount={attentionCount} abnormalCount={abnormalCount} punishmentCount={punishmentCount} excludedSettled={excludedSettled} onModeChange={setMode} onAccount={setSelectedAccountId} onPost={setSelectedPostId} />}
    {mode === 'accounts' && <AccountsView accounts={accounts} dates={dates} dailyRows={dailyRows} selected={selectedAccount} onSelect={setSelectedAccountId} />}
    {mode === 'posts' && <PostsView topPerAccount={topPerAccount} top10={top10} selected={selectedPost} onSelect={setSelectedPostId} />}
    {mode === 'revenue' && <RevenueView periods={includedRevenue} details={data.revenue_details} sources={revenueSources} dailyRevenue={dailyRevenue} currentMonthRevenue={currentMonthRevenue} excludedSettled={excludedSettled} />}
  </section>;
};

function OverviewView(props: {
  accounts: AccountRow[]; topPerAccount: PostRow[]; top10: PostRow[]; latestDate: string; dates: string[]; dailyRows: AnalyticsAccountDaily[]; dailyRevenue: Array<{ date: string; value: number }>;
  yesterdayViews: number; previousViews: number; yesterdayFans: number; interaction: number; viewChange: number | null; currentMonthRevenue: number; activeRevenue: number; attentionCount: number; abnormalCount: number; punishmentCount: number; excludedSettled: number; includedPeriods: AnalyticsDataBase['revenue_account_periods'];
  onModeChange: (mode: ViewMode) => void; onAccount: (id: string) => void; onPost: (id: string) => void;
}) {
  const { accounts, topPerAccount, top10, latestDate, dates, dailyRows, dailyRevenue, includedPeriods, yesterdayViews, previousViews, yesterdayFans, interaction, viewChange, currentMonthRevenue, activeRevenue, attentionCount, abnormalCount, punishmentCount, excludedSettled, onModeChange, onAccount, onPost } = props;
  const trend = dates.map((date) => ({ date, value: metricSum(dailyRows.filter((row) => row.stat_date === date), 'view') }));
  const topAccounts = accounts.slice(0, 6);
  return <>
    <div className="grid grid-cols-2 gap-3 lg:grid-cols-3 xl:grid-cols-6"><Kpi icon={<Eye />} label="昨日总播放" value={compact(yesterdayViews)} detail={`${accounts.filter((row) => row.views > 0).length} 个账号有记录`} tone="cyan" /><Kpi icon={viewChange !== null && viewChange >= 0 ? <ArrowUpRight /> : <ArrowDownRight />} label="昨日环比" value={percent(viewChange)} detail={`昨日 ${compact(previousViews)} 次`} tone={viewChange !== null && viewChange >= 0 ? 'green' : 'rose'} /><Kpi icon={<Users />} label="昨日新增粉丝" value={number(yesterdayFans)} detail="账号日数据合计" tone="violet" /><Kpi icon={<Activity />} label="互动总量" value={compact(interaction)} detail="赞 · 藏 · 评 · 转" tone="amber" /><Kpi icon={<CircleDollarSign />} label="当前可计收益" value={money(currentMonthRevenue)} detail={`${activeRevenue} 条有效周期`} tone="emerald" /><Kpi icon={<ShieldAlert />} label="待关注" value={number(attentionCount)} detail={`${abnormalCount} 个账号 · ${punishmentCount} 条处罚`} tone={attentionCount ? 'rose' : 'green'} /></div>
    <div className="grid gap-5 xl:grid-cols-[1.45fr_0.85fr]"><Panel title="账号流量趋势" description={`${dates[0]} 至 ${latestDate} · 账号播放与收益保持独立口径`} icon={<Activity className="h-4 w-4 text-cyan-600" />} action={<button type="button" onClick={() => onModeChange('accounts')} className="inline-flex items-center gap-1 text-[11px] font-semibold text-slate-400 hover:text-slate-900">查看账号 <ChevronRight className="h-3.5 w-3.5" /></button>}><TrafficChart points={trend} /></Panel><Panel title="收益来源" description="仅展示纳入分析的当前周期数据" icon={<CircleDollarSign className="h-4 w-4 text-emerald-600" />} action={<button type="button" onClick={() => onModeChange('revenue')} className="inline-flex items-center gap-1 text-[11px] font-semibold text-slate-400 hover:text-slate-900">查看收益 <ChevronRight className="h-3.5 w-3.5" /></button>}><RevenueSourceBars periods={includedPeriods} total={currentMonthRevenue} /><div className="mt-4 grid grid-cols-2 gap-2"><SmallStat label="当前可计周期" value={number(activeRevenue)} /><SmallStat label="已结算排除" value={number(excludedSettled)} accent="amber" /></div></Panel></div>
    <div className="grid gap-5 xl:grid-cols-[1.12fr_0.88fr]"><Panel title="账号贡献排行" description="按所选范围的账号播放总量排序" icon={<BarChart3 className="h-4 w-4 text-violet-600" />} action={<button type="button" onClick={() => onModeChange('accounts')} className="text-[11px] font-semibold text-violet-600 hover:text-violet-800">查看账号分析</button>}><div className="space-y-3">{topAccounts.map((account, index) => <RankBar key={account.id} index={index} label={account.name} meta={`${account.group} · ${number(account.fans)} 粉丝`} value={account.views} max={topAccounts[0]?.views || 1} color={index === 0 ? 'bg-violet-500' : 'bg-cyan-400'} onClick={() => onAccount(account.id)} />)}</div></Panel><Panel title="账号流量结构" description="播放集中在哪些账号，一眼看清" icon={<Layers3 className="h-4 w-4 text-fuchsia-600" />}><AccountDistribution accounts={accounts.slice(0, 6)} total={accounts.reduce((sum, account) => sum + account.views, 0)} onAccount={onAccount} /></Panel></div>
    <div className="grid gap-5 xl:grid-cols-2"><PostPanel title="每个账号的最高播放作品" description="每个账号只保留一条最高作品，方便发现账号当前最强内容。" posts={topPerAccount} perAccount onSelect={onPost} /><PostPanel title="全账号播放 Top 10" description="所有账号作品合并排名，播放指标按当前时间范围汇总。" posts={top10} ranked onSelect={onPost} /></div>
    <AttentionPanel abnormalCount={abnormalCount} punishmentCount={punishmentCount} excludedSettled={excludedSettled} onModeChange={onModeChange} />
  </>;
}

function AccountsView({ accounts, dates, dailyRows, selected, onSelect }: { accounts: AccountRow[]; dates: string[]; dailyRows: AnalyticsAccountDaily[]; selected: AccountRow | undefined; onSelect: (id: string | null) => void }) {
  const selectedDaily = selected ? dailyRows.filter((row) => row.account_id === selected.id) : [];
  return <div className="space-y-5"><PageTitle eyebrow="运营数据 / 账号" title="账号表现" description="按账号查看流量、涨粉、互动和最高作品。" icon={<Users className="h-5 w-5" />} /><div className="grid gap-5 xl:grid-cols-[1.45fr_0.85fr]"><Panel title="账号流量分布" description={`${dates[0]} 至 ${dates.at(-1)} · 点击账号查看详情`} icon={<BarChart3 className="h-4 w-4 text-cyan-600" />}><div className="space-y-3">{accounts.map((account, index) => <RankBar key={account.id} index={index} label={account.name} meta={`${account.group} · ${account.abnormal ? '需复核' : '状态正常'}`} value={account.views} max={accounts[0]?.views || 1} color={account.abnormal ? 'bg-rose-400' : index < 3 ? 'bg-cyan-500' : 'bg-slate-300'} onClick={() => onSelect(account.id)} />)}</div></Panel><Panel title="指标说明" description="流量不是单一播放量" icon={<Layers3 className="h-4 w-4 text-violet-600" />}><div className="space-y-3 text-xs leading-5 text-slate-600"><MetricExplain label="播放" text="账号在统计日的播放量，按有记录的账号汇总。" /><MetricExplain label="粉丝" text="粉丝总量是存量；新增、净增、掉粉是变化量。" /><MetricExplain label="互动" text="点赞、收藏、评论、转发分别保留，不合并成播放。" /><MetricExplain label="来源" text="本页使用小V猫视频号快照，页面读取不会触发平台刷新。" /></div></Panel></div><Panel title="账号明细" description="点击行查看近期开发表现" icon={<Users className="h-4 w-4 text-slate-600" />}><div className="overflow-x-auto"><table className="min-w-[900px] w-full text-left text-xs"><thead className="border-b border-slate-100 text-slate-400"><tr>{['账号', '范围播放', '粉丝总量', '新增粉丝', '净增粉', '互动', '最高作品', '状态'].map((label) => <th key={label} className="px-3 py-3 font-medium">{label}</th>)}</tr></thead><tbody className="divide-y divide-slate-100">{accounts.map((account) => <tr key={account.id} onClick={() => onSelect(account.id)} className={`cursor-pointer transition hover:bg-cyan-50/50 ${selected?.id === account.id ? 'bg-cyan-50/70' : ''}`}><td className="px-3 py-3"><div className="font-bold text-slate-800">{account.name}</div><div className="mt-0.5 font-mono text-[10px] text-slate-400">{account.uid}</div></td><td className="px-3 py-3 font-bold tabular-nums">{number(account.views)}</td><td className="px-3 py-3 tabular-nums">{number(account.fans)}</td><td className="px-3 py-3 text-emerald-600 tabular-nums">+{number(account.fansAdd)}</td><td className={`px-3 py-3 tabular-nums ${account.fansNet < 0 ? 'text-rose-600' : 'text-slate-700'}`}>{account.fansNet >= 0 ? '+' : ''}{number(account.fansNet)}</td><td className="px-3 py-3 tabular-nums">{number(account.likes + account.favorites + account.comments + account.forwards)}</td><td className="max-w-[220px] truncate px-3 py-3 text-slate-600">{account.topPost?.title || '—'}</td><td className="px-3 py-3"><StatusChip label={account.abnormal ? '需复核' : '正常'} tone={account.abnormal ? 'rose' : 'green'} /></td></tr>)}</tbody></table></div></Panel>{selected && <AccountDetail account={selected} daily={selectedDaily} onClose={() => onSelect(null)} />}</div>;
}

function PostsView({ topPerAccount, top10, selected, onSelect }: { topPerAccount: PostRow[]; top10: PostRow[]; selected: PostRow | undefined; onSelect: (id: string | null) => void }) {
  return <div className="space-y-5"><PageTitle eyebrow="运营数据 / 作品" title="作品表现" description="按作品查看播放、互动和内容排名。" icon={<Film className="h-5 w-5" />} /><div className="grid gap-5 xl:grid-cols-2"><PostPanel title="每个账号最高作品" description="一个账号一条，适合判断账号当前最强内容。" posts={topPerAccount} perAccount onSelect={onSelect} /><PostPanel title="全账号播放 Top 10" description="全量合并排名，适合寻找可复制的爆点。" posts={top10} ranked onSelect={onSelect} /></div>{selected && <PostDetail post={selected} onClose={() => onSelect(null)} />}</div>;
}

function RevenueView({ periods, details, sources, dailyRevenue, currentMonthRevenue, excludedSettled }: { periods: AnalyticsDataBase['revenue_account_periods']; details: AnalyticsDataBase['revenue_details']; sources: AnalyticsDataBase['revenue_source_inventory']; dailyRevenue: Array<{ date: string; value: number }>; currentMonthRevenue: number; excludedSettled: number }) {
  const qingning = periods.filter((row) => row.period_type === 'day');
  const touch = periods.filter((row) => row.period_type === 'month_cumulative');
  const avg = qingning.length ? qingning.reduce((sum, row) => sum + amount(row.amount), 0) / qingning.length : 0;
  return <div className="space-y-5"><PageTitle eyebrow="运营数据 / 收益" title="收益表现" description="收益按剧场来源和返回粒度展示，暂不把不同口径强行合并成一条趋势。" icon={<CircleDollarSign className="h-5 w-5" />} /><div className="grid grid-cols-2 gap-3 lg:grid-cols-4"><Kpi icon={<CircleDollarSign />} label="当前可计收益" value={money(currentMonthRevenue)} detail="按来源合计" tone="emerald" /><Kpi icon={<Activity />} label="日收益平均" value={money(avg)} detail="青柠日明细" tone="cyan" /><Kpi icon={<Database />} label="已登记来源" value={number(sources.length)} detail="当前演示来源" tone="violet" /><Kpi icon={<ShieldAlert />} label="已结算排除" value={number(excludedSettled)} detail="不进入当前分析" tone="amber" /></div><div className="grid gap-5 xl:grid-cols-[1.2fr_0.8fr]"><Panel title="日收益趋势" description="只有按日返回的数据进入这张趋势图。月累计数据单独呈现。" icon={<Activity className="h-4 w-4 text-emerald-600" />}><RevenueTrend points={dailyRevenue} /></Panel><Panel title="剧场来源" description="来源、查询粒度和明细能力保持可见。" icon={<Layers3 className="h-4 w-4 text-violet-600" />}><div className="space-y-3">{sources.map((source) => { const total = source.adapter_key.includes('qingning') ? qingning.reduce((sum, row) => sum + amount(row.amount), 0) : touch.filter((row) => row.include_in_analysis === 1).reduce((sum, row) => sum + amount(row.amount), 0); return <div key={source.id} className="rounded-2xl border border-slate-100 p-3"><div className="flex items-center justify-between gap-3"><div><div className="text-sm font-bold text-slate-800">{source.adapter_key.includes('qingning') ? '青柠剧场' : '触摸剧场'}</div><div className="mt-1 text-[11px] text-slate-400">{source.query_mode} · {source.date_precision} · {source.supports_detail ? '支持明细' : '仅金额'}</div></div><strong className="text-sm tabular-nums text-slate-900">{money(total)}</strong></div><div className="mt-2"><StatusChip label="演示来源" tone="violet" /></div></div>; })}</div></Panel></div><Panel title="收益明细" description="当前演示数据中的有效周期，已结算月份不纳入。" icon={<WalletCards className="h-4 w-4 text-amber-600" />}><div className="overflow-x-auto"><table className="min-w-[820px] w-full text-left text-xs"><thead className="border-b border-slate-100 text-slate-400"><tr>{['周期', '口径', '来源', '金额', '结算状态', '数据状态'].map((label) => <th key={label} className="px-3 py-3 font-medium">{label}</th>)}</tr></thead><tbody className="divide-y divide-slate-100">{periods.slice().sort((a, b) => b.period_start.localeCompare(a.period_start)).slice(0, 24).map((row) => <tr key={row.id}><td className="px-3 py-3 font-medium text-slate-700">{row.period_label}</td><td className="px-3 py-3 text-slate-500">{row.period_type === 'day' ? '按日' : '月累计'}</td><td className="px-3 py-3 text-slate-500">{row.period_type === 'day' ? '青柠剧场' : '触摸剧场'}</td><td className="px-3 py-3 font-semibold tabular-nums">{money(amount(row.amount))}</td><td className="px-3 py-3"><StatusChip label={row.settlement_state === 'settled' ? '已结算 · 排除' : '未结算 · 纳入'} tone={row.settlement_state === 'settled' ? 'amber' : 'green'} /></td><td className="px-3 py-3 text-slate-400">{row.freshness_state}</td></tr>)}</tbody></table></div>{details.length > 0 && <div className="mt-4 text-[11px] text-slate-400">青柠收益明细 {number(details.length)} 条，可继续下钻到账号、日期、视频和剧名。</div>}</Panel></div>;
}

function PageTitle({ eyebrow, title, description, icon }: { eyebrow: string; title: string; description: string; icon: React.ReactNode }) { return <div className="flex flex-wrap items-end justify-between gap-4"><div><div className="flex items-center gap-2 text-xs font-semibold text-cyan-700"><span className="flex h-7 w-7 items-center justify-center rounded-lg bg-cyan-50">{icon}</span>{eyebrow}</div><h2 className="mt-3 text-2xl font-black tracking-tight text-slate-900">{title}</h2><p className="mt-1 text-sm text-slate-500">{description}</p></div></div>; }

function Panel({ title, description, icon, action, children }: { title: string; description: string; icon: React.ReactNode; action?: React.ReactNode; children: React.ReactNode }) { return <section className="rounded-[24px] border border-slate-200/80 bg-white p-5 shadow-[0_10px_35px_rgba(15,23,42,0.045)] sm:p-6"><div className="mb-5 flex items-start justify-between gap-3"><div className="flex min-w-0 items-start gap-2.5"><span className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-xl bg-slate-50 text-slate-600">{icon}</span><div><h3 className="text-sm font-bold text-slate-900">{title}</h3><p className="mt-1 text-[11px] leading-4 text-slate-500">{description}</p></div></div>{action}</div>{children}</section>; }

function Kpi({ icon, label, value, detail, tone }: { icon: React.ReactNode; label: string; value: string; detail: string; tone: 'cyan' | 'green' | 'violet' | 'amber' | 'emerald' | 'rose' }) { const colors = { cyan: 'bg-cyan-50 text-cyan-700', green: 'bg-emerald-50 text-emerald-700', violet: 'bg-violet-50 text-violet-700', amber: 'bg-amber-50 text-amber-700', emerald: 'bg-emerald-50 text-emerald-700', rose: 'bg-rose-50 text-rose-700' }; return <article className="rounded-[20px] border border-slate-200/80 bg-white p-4 shadow-[0_8px_26px_rgba(15,23,42,0.035)]"><span className={`flex h-8 w-8 items-center justify-center rounded-xl ${colors[tone]}`}>{React.cloneElement(icon as React.ReactElement<{ className?: string }>, { className: 'h-4 w-4' })}</span><div className="mt-4 text-[11px] text-slate-500">{label}</div><div className="mt-1 truncate text-xl font-black tracking-tight text-slate-900">{value}</div><div className="mt-1 truncate text-[11px] text-slate-400">{detail}</div></article>; }

function TrafficChart({ points }: { points: Array<{ date: string; value: number }> }) { const max = Math.max(...points.map((point) => point.value), 1); return <div><div className="flex h-56 items-end gap-1.5 border-b border-slate-100 px-1 pt-5 sm:gap-3">{points.map((point) => <div key={point.date} className="group flex h-full min-w-0 flex-1 flex-col items-center justify-end gap-2" title={`${point.date} · ${number(point.value)} 播放`}><span className="opacity-0 text-[10px] tabular-nums text-slate-500 transition group-hover:opacity-100">{compact(point.value)}</span><div className="w-full max-w-12 rounded-t-lg bg-gradient-to-t from-cyan-500 to-cyan-300 transition-all group-hover:from-violet-500 group-hover:to-fuchsia-300" style={{ height: `${Math.max(7, point.value / max * 78)}%` }} /><span className="text-[10px] text-slate-400">{point.date.slice(5)}</span></div>)}</div><div className="mt-3 flex items-center justify-between text-[11px] text-slate-400"><span>播放量 · 账号日数据合计</span><span>{points.length} 个数据日</span></div></div>; }

function RevenueTrend({ points }: { points: Array<{ date: string; value: number }> }) { const max = Math.max(...points.map((point) => point.value), 1); return <div><div className="flex h-56 items-end gap-1.5 border-b border-slate-100 px-1 pt-5 sm:gap-3">{points.map((point) => <div key={point.date} className="group flex h-full min-w-0 flex-1 flex-col items-center justify-end gap-2" title={`${point.date} · ${money(point.value)}`}><span className="opacity-0 text-[10px] tabular-nums text-slate-500 transition group-hover:opacity-100">{point.value ? money(point.value) : '—'}</span><div className="w-full max-w-12 rounded-t-lg bg-gradient-to-t from-emerald-500 to-teal-300" style={{ height: `${Math.max(point.value ? 7 : 2, point.value / max * 78)}%` }} /><span className="text-[10px] text-slate-400">{point.date.slice(5)}</span></div>)}</div><div className="mt-3 text-[11px] text-slate-400">仅绘制按日返回的收益；月累计来源保留在右侧来源卡中。</div></div>; }

function RevenueSourceBars({ periods, total }: { periods: AnalyticsDataBase['revenue_account_periods']; total: number }) { const grouped = periods.reduce<Record<string, number>>((out, row) => { const key = row.theater_id || 'unknown'; out[key] = (out[key] || 0) + (Number(row.amount) || 0); return out; }, {}); const items = Object.entries(grouped).sort((a, b) => b[1] - a[1]); const max = Math.max(...items.map(([, value]) => value), 1); const labels: Record<string, string> = { simulation_qingning: '青柠剧场', simulation_touch: '触摸剧场' }; return <div className="rounded-2xl bg-slate-50/80 p-4"><div className="flex items-end justify-between"><div><div className="text-[11px] font-semibold text-slate-500">当前可计收益</div><div className="mt-1 text-2xl font-black text-slate-900">{money(total)}</div></div><span className="text-[10px] text-slate-400">按来源合计</span></div><div className="mt-6 space-y-3">{items.length ? items.map(([key, value], index) => <div key={key} className="flex items-center gap-3 text-xs"><span className={`h-2.5 w-2.5 rounded-full ${index === 0 ? 'bg-emerald-500' : 'bg-violet-500'}`} /><span className="w-20 truncate text-slate-600">{labels[key] || key}</span><div className="h-2 flex-1 overflow-hidden rounded-full bg-slate-200"><div className={`h-full rounded-full ${index === 0 ? 'bg-emerald-500' : 'bg-violet-500'}`} style={{ width: `${Math.max(4, value / max * 100)}%` }} /></div><span className="tabular-nums text-slate-700">{money(value)}</span></div>) : <div className="text-xs text-slate-400">当前范围没有可计收益</div>}</div></div>; }

function AccountDistribution({ accounts, total, onAccount }: { accounts: AccountRow[]; total: number; onAccount: (id: string) => void }) { const colors = ['#8b5cf6', '#ec4899', '#06b6d4', '#f59e0b', '#10b981', '#94a3b8']; let cursor = 0; const stops = accounts.map((account, index) => { const start = cursor; cursor += total ? account.views / total * 360 : 0; return `${colors[index % colors.length]} ${start}deg ${cursor}deg`; }).join(', '); const gradient = `conic-gradient(${stops || '#e2e8f0 0deg 360deg'})`; return <div className="flex items-center gap-5"><div className="relative h-32 w-32 shrink-0 rounded-full" style={{ background: gradient }}><div className="absolute inset-5 flex flex-col items-center justify-center rounded-full bg-white text-center shadow-inner"><strong className="text-xl font-black text-slate-900">{number(total)}</strong><span className="text-[10px] text-slate-400">范围播放</span></div></div><div className="min-w-0 flex-1 space-y-2">{accounts.slice(0, 5).map((account, index) => <button key={account.id} type="button" onClick={() => onAccount(account.id)} className="flex w-full items-center gap-2 text-left text-[11px] hover:text-violet-700"><span className="h-2.5 w-2.5 shrink-0 rounded-full" style={{ background: colors[index % colors.length] }} /><span className="min-w-0 flex-1 truncate text-slate-600">{account.name}</span><strong className="tabular-nums text-slate-800">{total ? (account.views / total * 100).toFixed(1) : '0.0'}%</strong></button>)}<div className="pt-1 text-[10px] text-slate-400">点击账号查看详细趋势</div></div></div>; }

function RankBar({ index, label, meta, value, max, color, onClick }: { key?: React.Key; index: number; label: string; meta: string; value: number; max: number; color: string; onClick?: () => void }) { return <button type="button" onClick={onClick} className="group block w-full text-left"><div className="flex items-center gap-3"><span className={`flex h-6 w-6 shrink-0 items-center justify-center rounded-full text-[11px] font-bold ${index === 0 ? 'bg-[#11172A] text-cyan-300' : 'bg-slate-100 text-slate-500'}`}>{index + 1}</span><div className="min-w-0 flex-1"><div className="flex items-center justify-between gap-3"><span className="truncate text-xs font-bold text-slate-800 group-hover:text-cyan-700">{label}</span><strong className="text-xs tabular-nums text-slate-900">{compact(value)}</strong></div><div className="mt-1 h-2 overflow-hidden rounded-full bg-slate-100"><div className={`h-full rounded-full ${color}`} style={{ width: `${Math.max(3, value / max * 100)}%` }} /></div><div className="mt-1 text-[10px] text-slate-400">{meta}</div></div></div></button>; }

function PostPanel({ title, description, posts, ranked = false, perAccount = false, onSelect }: { title: string; description: string; posts: PostRow[]; ranked?: boolean; perAccount?: boolean; onSelect: (id: string) => void }) { return <Panel title={title} description={description} icon={<Film className="h-4 w-4 text-amber-600" />} action={<span className="text-[11px] font-semibold text-slate-400">{number(posts.length)} {perAccount ? '个账号' : '条'}</span>}><div className="space-y-1.5">{posts.slice(0, ranked ? 10 : 12).map((post, index) => <button key={post.post_id} type="button" onClick={() => onSelect(post.post_id)} className="flex w-full items-center gap-3 rounded-xl border border-slate-100 px-3 py-2.5 text-left transition hover:border-cyan-200 hover:bg-cyan-50/40"><span className={`flex h-6 w-6 shrink-0 items-center justify-center rounded-full text-[11px] font-bold ${index === 0 ? 'bg-amber-100 text-amber-700' : 'bg-slate-100 text-slate-500'}`}>{ranked ? index + 1 : '•'}</span><div className="min-w-0 flex-1"><div className="truncate text-xs font-bold text-slate-800">{post.post_id}</div><div className="mt-0.5 truncate text-[10px] text-slate-400">投放账号：{post.account_name} · {post.periodDays} 个数据日 · 完播 {Math.round(post.full_view * 100)}%</div></div><div className="text-right"><strong className="block text-sm tabular-nums text-slate-900">{compact(post.periodViews)}</strong><span className="text-[10px] text-slate-400">播放</span></div></button>)}</div></Panel>; }

function AttentionPanel({ abnormalCount, punishmentCount, excludedSettled, onModeChange }: { abnormalCount: number; punishmentCount: number; excludedSettled: number; onModeChange: (mode: ViewMode) => void }) { return <Panel title="待关注事项" description="把需要人工判断的数据状态单独放出来。" icon={<ShieldAlert className="h-4 w-4 text-rose-600" />}><div className="grid gap-2 md:grid-cols-3"><Attention icon={<ShieldAlert />} title="账号诊断" value={abnormalCount} detail="小V猫返回异常或需复核" action={() => onModeChange('accounts')} /><Attention icon={<FileWarning />} title="作品处罚" value={punishmentCount} detail="存在推荐曝光或内容状态异常" action={() => onModeChange('posts')} /><Attention icon={<WalletCards />} title="结算排除" value={excludedSettled} detail="已结算月份不进入当前收益" action={() => onModeChange('revenue')} /></div></Panel>; }
function Attention({ icon, title, value, detail, action }: { icon: React.ReactNode; title: string; value: number; detail: string; action: () => void }) { return <button type="button" onClick={action} className="flex items-center gap-3 rounded-2xl border border-slate-100 px-3 py-3 text-left transition hover:border-cyan-200 hover:bg-cyan-50/30"><span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-rose-50 text-rose-600">{React.cloneElement(icon as React.ReactElement<{ className?: string }>, { className: 'h-4 w-4' })}</span><span className="min-w-0 flex-1"><span className="flex items-center gap-2 text-xs font-bold text-slate-800">{title}<strong className="text-rose-600">{value}</strong></span><span className="mt-1 block truncate text-[10px] text-slate-400">{detail}</span></span><ArrowRight className="h-4 w-4 text-slate-300" /></button>; }

function AccountDetail({ account, daily, onClose }: { account: AccountRow; daily: AnalyticsAccountDaily[]; onClose: () => void }) { const max = Math.max(...daily.map((row) => row.view), 1); return <Panel title={`${account.name} · 账号详情`} description="当前范围的每日快照和关键指标。" icon={<Users className="h-4 w-4 text-cyan-600" />} action={<button type="button" onClick={onClose} className="text-[11px] font-semibold text-slate-400 hover:text-slate-900">收起详情</button>}><div className="grid grid-cols-2 gap-3 sm:grid-cols-5"><SmallStat label="粉丝总量" value={number(account.fans)} /><SmallStat label="范围播放" value={compact(account.views)} accent="cyan" /><SmallStat label="新增粉丝" value={number(account.fansAdd)} accent="green" /><SmallStat label="净增粉" value={number(account.fansNet)} accent={account.fansNet < 0 ? 'rose' : 'violet'} /><SmallStat label="互动" value={compact(account.likes + account.favorites + account.comments + account.forwards)} /></div><div className="mt-5 flex h-36 items-end gap-2 border-b border-slate-100">{daily.map((row) => <div key={row.stat_date} className="group flex h-full flex-1 flex-col items-center justify-end gap-1" title={`${row.stat_date} · ${number(row.view)}`}><div className="w-full max-w-10 rounded-t-md bg-cyan-400 transition group-hover:bg-violet-500" style={{ height: `${Math.max(5, row.view / max * 75)}%` }} /><span className="text-[9px] text-slate-400">{row.stat_date.slice(5)}</span></div>)}</div></Panel>; }
function PostDetail({ post, onClose }: { post: PostRow; onClose: () => void }) { return <Panel title={`${post.account_name} · 作品详情`} description="作品指标来自小V猫作品快照；收益关联需要独立剧场明细确认。" icon={<Film className="h-4 w-4 text-amber-600" />} action={<button type="button" onClick={onClose} className="text-[11px] font-semibold text-slate-400 hover:text-slate-900">收起详情</button>}><div className="flex flex-wrap items-start justify-between gap-4"><div><div className="text-lg font-black text-slate-900">{post.title || '作品标题未返回'}</div><div className="mt-1 text-xs text-slate-400">{post.post_id} · 发布于 {post.post_time.slice(0, 10)} · {post.periodDays} 个数据日</div></div><StatusChip label="小V猫作品数据" tone="violet" /></div><div className="mt-5 grid grid-cols-2 gap-3 sm:grid-cols-5"><SmallStat label="范围播放" value={compact(post.periodViews)} accent="cyan" /><SmallStat label="点赞" value={number(post.periodLikes)} /><SmallStat label="新增粉丝" value={number(post.periodFansAdd)} accent="green" /><SmallStat label="完播率" value={`${Math.round(post.full_view * 100)}%`} accent="violet" /><SmallStat label="观看时长" value={`${post.view_time.toFixed(1)} 秒`} /></div></Panel>; }

function MetricExplain({ label, text }: { label: string; text: string }) { return <div><div className="font-semibold text-slate-800">{label}</div><div className="mt-0.5 text-slate-500">{text}</div></div>; }
function SmallStat({ label, value, accent = 'slate' }: { label: string; value: string; accent?: 'slate' | 'cyan' | 'green' | 'violet' | 'amber' | 'rose' }) { const colors = { slate: 'text-slate-900', cyan: 'text-cyan-700', green: 'text-emerald-700', violet: 'text-violet-700', amber: 'text-amber-700', rose: 'text-rose-700' }; return <div className="rounded-2xl bg-slate-50 px-3 py-3"><div className="text-[10px] text-slate-500">{label}</div><div className={`mt-1 text-lg font-black tabular-nums ${colors[accent]}`}>{value}</div></div>; }
function StatusChip({ label, tone }: { label: string; tone: 'green' | 'rose' | 'amber' | 'violet' }) { const style = tone === 'green' ? 'bg-emerald-50 text-emerald-700' : tone === 'rose' ? 'bg-rose-50 text-rose-700' : tone === 'amber' ? 'bg-amber-50 text-amber-700' : 'bg-violet-50 text-violet-700'; return <span className={`inline-flex rounded-full px-2 py-1 text-[10px] font-semibold ${style}`}>{label}</span>; }
function SourceBadge() { return <span className="inline-flex items-center gap-1.5 rounded-xl border border-violet-200 bg-violet-50 px-3 py-2 text-[11px] font-semibold text-violet-700"><Sparkles className="h-3.5 w-3.5" />演示数据 · simulation_ui</span>; }
