import type { AccountDailySummary } from '../../services/accountDailySummary';

function count(value: number | null): string {
  if (value === null) return '—';
  return Math.abs(value) >= 10_000
    ? new Intl.NumberFormat('zh-CN', { notation: 'compact', maximumFractionDigits: 2 }).format(value)
    : value.toLocaleString('zh-CN');
}

export function AccountYesterdayMetrics({ data }: { data: AccountDailySummary }) {
  const previous = data.status === 'previous';
  const stale = data.status !== 'yesterday';
  const metrics = [['净增关注', data.follows], ['新增播放', data.views], ['新增爱心', data.hearts], ['新增评论', data.comments]] as const;
  return <section data-account-daily-status={data.status} aria-label={previous ? `最近数据 ${data.date}，昨日数据待更新` : '昨日数据'}>
    <div className="mb-1.5 flex items-center justify-between gap-2 text-[10px] leading-4 text-slate-400">
      <span>{previous ? `最近数据 · ${data.date}` : '昨日数据'}</span>
      {stale ? <span className="rounded bg-slate-50 px-1.5 text-slate-400">{previous ? '待昨日更新' : '待获取'}</span> : <span>{data.date?.slice(5)}</span>}
    </div>
    <div className="grid grid-cols-4 gap-1.5 text-center">
      {metrics.map(([label, value]) => <div key={label} className={`min-w-0 rounded-lg px-1 py-2 ${stale ? 'bg-slate-50/50' : 'bg-slate-50'}`}
        aria-label={`${label} ${value === null ? '暂无数据' : value.toLocaleString('zh-CN')}`}>
        <span className="block whitespace-nowrap text-[10px] leading-4 text-slate-400">{label}</span>
        <span className={`mt-0.5 block font-mono text-[11px] font-semibold leading-4 tabular-nums ${stale ? 'text-slate-500' : 'text-slate-800'}`}>{count(value)}</span>
      </div>)}
    </div>
  </section>;
}
