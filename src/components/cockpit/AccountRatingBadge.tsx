import { useState } from 'react';
import { Activity, Ban, Flame, HelpCircle, Hourglass, Rocket, ShieldCheck, TrendingDown, TrendingUp } from 'lucide-react';
import type { AccountInfo, AccountRevenueRating, RevenueAccountTier } from '../../types/shortDramaOps';
import { formatRevenueQueryTime, REVENUE_TIER_LIMITS } from '../../services/accountRevenueRating';
import { STATUS_BADGE_FRAME, StatusBadgePopover, StatusBadgeRulesDialog } from './StatusBadgePopover';

// Visuals extracted from Gemini's AccountStatusBadge; all facts still come from V3's rating.
const bTierMinimum = REVENUE_TIER_LIMITS.B;
const grades: Record<RevenueAccountTier, { badge: string; pill: string; rule: string }> = {
  SS: { badge: 'bg-gradient-to-r from-purple-600 to-indigo-600 text-white font-black shadow-xs', pill: 'bg-purple-50/80 border-purple-200/90 hover:border-purple-300 text-purple-950', rule: '累计收益 > ¥5,000' },
  S: { badge: 'bg-gradient-to-r from-amber-500 to-yellow-600 text-white font-black shadow-xs', pill: 'bg-amber-50/80 border-amber-200/90 hover:border-amber-300 text-amber-950', rule: '¥2,000 ≤ 累计收益 ≤ ¥5,000' },
  A: { badge: 'bg-emerald-600 text-white font-bold shadow-xs', pill: 'bg-emerald-50/80 border-emerald-200/90 hover:border-emerald-300 text-emerald-950', rule: '¥500 ≤ 累计收益 < ¥2,000' },
  B: { badge: 'bg-sky-600 text-white font-bold shadow-xs', pill: 'bg-sky-50/80 border-sky-200/90 hover:border-sky-300 text-sky-950', rule: `¥${bTierMinimum} ≤ 累计收益 < ¥500` },
  C: { badge: 'bg-slate-600 text-white font-bold shadow-xs', pill: 'bg-slate-100 border-slate-200 hover:border-slate-300 text-slate-800', rule: `累计收益 < ¥${bTierMinimum}，且完成试投观察` },
  待评: { badge: 'bg-stone-400 text-white font-semibold', pill: 'bg-stone-50 border-stone-200/90 hover:border-stone-300 text-stone-700', rule: '收益或试投记录尚不足以评定' },
};
const phases = {
  爆发: { icon: Flame, color: 'text-amber-700', iconColor: 'text-amber-500 fill-amber-500', summary: '最近确认单日收益达到 ¥500' },
  起量: { icon: TrendingUp, color: 'text-emerald-700', iconColor: 'text-emerald-500', summary: '收益正在起量' },
  平稳: { icon: Activity, color: 'text-blue-700', iconColor: 'text-blue-500', summary: '近期收益表现平稳' },
  回落: { icon: TrendingDown, color: 'text-orange-700', iconColor: 'text-orange-500', summary: '近期收益回落，累计等级保留' },
  尾量: { icon: Hourglass, color: 'text-amber-800', iconColor: 'text-amber-600', summary: '连续两个已确认完整收益日低于 ¥10' },
  试投: { icon: Rocket, color: 'text-indigo-700', iconColor: 'text-indigo-500', summary: '试投观察中，等待更多收益记录' },
  停用: { icon: Ban, color: 'text-slate-500', iconColor: 'text-slate-400', summary: '账号已停用，保留累计成绩' },
  待判: { icon: HelpCircle, color: 'text-slate-500', iconColor: 'text-slate-400', summary: '日收益记录不足，阶段待判断' },
} satisfies Record<AccountRevenueRating['phase'], unknown>;
const money = (value: number) => `¥${value.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
const dotColors = { 已更新: 'bg-emerald-500 ring-emerald-500/20 shadow-[0_0_6px_rgba(16,185,129,0.9)]', 待更新: 'bg-amber-500 ring-amber-500/20 shadow-[0_0_6px_rgba(245,158,11,0.9)]', 查询失败: 'bg-rose-500 ring-rose-500/20 shadow-[0_0_6px_rgba(244,63,94,0.9)]' };
type BadgeSize = 'sm' | 'md' | 'lg';
// Keep the archive's size tiers, including its natural-height grade chip.
const sizes = {
  sm: { wrapper: 'h-6 px-1.5 gap-1.5 rounded-md text-[11px] leading-[1.333333]', dot: 'h-1.5 w-1.5', grade: 'px-1 py-[0.8px] text-[10px] rounded', stage: 'text-[10px]', icon: 'h-3 w-3', divider: 'h-2.5' },
  md: { wrapper: 'h-6.5 px-2 gap-1.5 rounded-md text-[11.5px] font-medium leading-[1.5]', dot: 'h-1.5 w-1.5', grade: 'px-[4.8px] py-[0.8px] text-[10.5px] rounded', stage: 'text-[11px] font-semibold', icon: 'h-[12.8px] w-[12.8px]', divider: 'h-3' },
  lg: { wrapper: 'h-8 px-2.5 gap-2 rounded-lg text-xs font-medium leading-[1.333333]', dot: 'h-2 w-2', grade: 'px-1.5 py-0.5 text-xs rounded-md', stage: 'text-xs font-semibold', icon: 'h-3.5 w-3.5', divider: 'h-3.5' },
};
const conditions: Record<RevenueAccountTier, string> = { SS: '＞5000元', S: '≥2000元，且≤5000元', A: '≥500元，且＜2000元', B: `≥${bTierMinimum}元，且＜500元`, C: `＜${bTierMinimum}元，已完成试投`, 待评: '初始数据不足，暂时无法定级' };
const gradeDescriptions: Record<RevenueAccountTier, string> = { SS: '本轮累计已确认收益大于5000元，矩阵核心创收主力', S: '本轮累计已确认收益2000—5000元，稳健高产号', A: '本轮累计已确认收益500—不足2000元，腰部成长号', B: `本轮累计已确认收益${bTierMinimum}—不足500元，起步测试号`, C: `试投观察充分但累计收益不足${bTierMinimum}元`, 待评: '新号开跑或样本不足，暂时无法有效评级' };
const syncDescriptions = { 已更新: '已取得该收益日的有效数据', 待更新: '目标收益日尚未发布或无法确认', 查询失败: '本次查询失败，保留原有结果' };
const phasePills = { 爆发: 'bg-amber-500/10 text-amber-800 border-amber-200/80', 起量: 'bg-emerald-500/10 text-emerald-800 border-emerald-200/80', 平稳: 'bg-blue-500/10 text-blue-800 border-blue-200/80', 回落: 'bg-orange-500/10 text-orange-800 border-orange-200/80', 尾量: 'bg-amber-600/10 text-amber-900 border-amber-300/80', 试投: 'bg-indigo-500/10 text-indigo-800 border-indigo-200/80', 停用: 'bg-slate-200/70 text-slate-500 border-slate-300', 待判: 'bg-slate-100 text-slate-500 border-slate-200' };
function UpdateMark({ status, size = 'h-1.5 w-1.5' }: { status: AccountRevenueRating['updateStatus']; size?: string }) {
  return <span aria-hidden="true" className={`inline-block flex-none rounded-full ring-2 ${size} ${dotColors[status]}`} />;
}
function BadgeFace({ tier, phase, update, size }: { tier: RevenueAccountTier; phase: AccountRevenueRating['phase']; update: AccountRevenueRating['updateStatus']; size: BadgeSize }) {
  const sz = sizes[size], stage = phases[phase], Icon = stage.icon;
  return <>
    <span className="flex flex-none items-center justify-center"><UpdateMark status={update} size={sz.dot} /></span>
    <span className={`inline-flex flex-none items-center justify-center font-mono ${grades[tier].badge} ${sz.grade}`}>{tier}</span>
    <span aria-hidden="true" className={`w-px flex-none bg-slate-300/70 ${sz.divider}`} />
    <span className={`inline-flex flex-none items-center gap-1 font-sans ${stage.color} ${sz.stage}`}><Icon aria-hidden="true" className={`flex-none ${sz.icon} ${stage.iconColor}`} /><span className="leading-none">{phase}</span></span>
  </>;
}

export function AccountRatingBadge({ account, compact = false, size, displayOnly = false }: { account: AccountInfo; compact?: boolean; size?: BadgeSize; displayOnly?: boolean }) {
  const [rulesOpen, setRulesOpen] = useState(false);
  const rating = account.rating;
  const tier = rating?.tier ?? '待评', phase = rating?.phase ?? '待判', update = rating?.updateStatus ?? '待更新';
  const grade = grades[tier], stage = phases[phase], Icon = stage.icon;
  const resolvedSize = size ?? (compact ? 'sm' : 'md');
  if (displayOnly) return <span data-account-tag="true" aria-label={`${tier}，${phase}，收益${update}`}
    className={`${STATUS_BADGE_FRAME} ${grade.pill} ${sizes[resolvedSize].wrapper}`}>
    <BadgeFace tier={tier} phase={phase} update={update} size={resolvedSize} />
  </span>;
  return <>
    <StatusBadgePopover kind="account" status={update} label={`${tier}，${phase}，收益${update}`}
      className={`${grade.pill} ${sizes[resolvedSize].wrapper}`} onRules={() => setRulesOpen(true)}
      badge={<BadgeFace tier={tier} phase={phase} update={update} size={resolvedSize} />}
      heading={<div className="flex min-w-0 flex-wrap items-center gap-1.5"><span className="font-bold text-slate-900">账号复合状态解读</span><div className="inline-flex flex-none items-center gap-1 rounded-md border border-slate-200 bg-slate-50 px-1.5 py-0.5 text-[10.5px]"><UpdateMark status={update} size="h-2 w-2" /><span className={`rounded px-1 py-[0.8px] font-mono text-[10px] font-bold ${grade.badge}`}>{tier}</span><span className="text-slate-300">|</span><Icon className={`h-3 w-3 flex-none ${stage.iconColor}`} /><span className={`font-semibold ${stage.color}`}>{phase}</span></div></div>}>
      <div className="mb-2.5 rounded-lg border border-slate-200/70 bg-slate-50 p-2">
        <div className="mb-1 flex items-center justify-between gap-2 text-[11px]"><span className="flex items-center gap-1.5 font-medium text-slate-500"><UpdateMark status={update} size="h-2 w-2" />数据更新状态</span><strong className={update === '已更新' ? 'text-emerald-700' : update === '待更新' ? 'text-amber-700' : 'text-rose-700'}>{update}</strong></div>
        <p className="break-words text-[11px] leading-relaxed text-slate-600">{rating?.updateReason || syncDescriptions[update]}</p>
      </div>
      <div className="mb-2.5 rounded-lg border border-slate-200/70 bg-slate-50 p-2">
        <div className="mb-1 flex items-center justify-between gap-2 text-[11px]"><span className="font-medium text-slate-500">本轮累计已确认收益</span><span className="font-mono font-extrabold text-emerald-700">{rating?.recordedTotal == null ? '—' : money(rating.recordedTotal)}</span></div>
        <div className="flex flex-wrap items-center justify-between gap-x-2 gap-y-1 text-[11px] text-slate-600"><span className="flex items-center gap-1"><span>评定等级：</span><strong className={`rounded px-1 font-mono ${grade.badge}`}>{tier}</strong><span className="font-medium text-slate-800">{tier === '待评' ? tier : `${tier}级`}</span></span><span className="font-mono text-[10.5px] text-slate-400">({conditions[tier]})</span></div>
      </div>
      <div className="mb-2.5 rounded-lg border border-slate-200/70 bg-slate-50 p-2">
        <div className="mb-1 flex items-center justify-between text-[11px]"><span className="font-medium text-slate-500">当前生命周期阶段</span><strong className={`flex items-center gap-1 ${stage.color}`}><Icon className={`h-3.5 w-3.5 flex-none ${stage.iconColor}`} />{phase}阶段</strong></div>
        <p className="text-[11px] leading-relaxed text-slate-600">{rating?.phaseReason || stage.summary}</p>
      </div>
    </StatusBadgePopover>
    {rulesOpen && <StatusBadgeRulesDialog kind="account" title="账号标签规则" onClose={() => setRulesOpen(false)}>
      <section><h4 className="mb-2 flex items-center gap-1.5 font-bold text-slate-900"><span className="h-2 w-2 rounded-full bg-indigo-600" />实心状态指示符规范</h4><div className="grid gap-2 sm:grid-cols-3">{(['已更新', '待更新', '查询失败'] as const).map(status => <div key={status} className={`rounded-xl border p-2.5 ${status === '已更新' ? 'border-emerald-200/80 bg-emerald-50/70 text-emerald-900' : status === '待更新' ? 'border-amber-200/80 bg-amber-50/70 text-amber-900' : 'border-rose-200/80 bg-rose-50/70 text-rose-900'}`}><div className="mb-1 flex items-center gap-1.5 font-bold"><UpdateMark status={status} size="h-2 w-2" />{status}</div><p className="text-[11px] leading-relaxed">{syncDescriptions[status]}</p></div>)}</div></section>
      <section><h4 className="mb-2 flex items-center gap-1.5 font-bold text-slate-900"><span className="h-2 w-2 rounded-full bg-purple-600" />等级规则（本轮累计已确认收益）</h4><div className="overflow-x-auto rounded-xl border border-slate-200"><table className="w-full min-w-[480px] text-left text-xs"><thead className="border-b border-slate-200 bg-slate-50 font-semibold text-slate-500"><tr><th className="w-24 p-2.5">等级徽章</th><th className="w-36 p-2.5">本轮累计已确认收益</th><th className="p-2.5">定位与说明</th></tr></thead><tbody className="divide-y divide-slate-100">{Object.entries(grades).map(([name, config]) => <tr key={name} className="hover:bg-slate-50/50"><td className="p-2.5"><span className={`inline-flex rounded px-1.5 py-0.5 font-mono text-[11px] ${config.badge}`}>{name}</span><span className="ml-1.5 font-bold text-slate-900">{name === '待评' ? name : `${name}级`}</span></td><td className="p-2.5 font-mono font-semibold text-emerald-700">{config.rule}</td><td className="p-2.5 text-slate-600">{gradeDescriptions[name as RevenueAccountTier]}</td></tr>)}</tbody></table></div></section>
      <section><h4 className="mb-2 flex items-center gap-1.5 font-bold text-slate-900"><span className="h-2 w-2 rounded-full bg-amber-600" />阶段规则（生命周期主要情况与专属图标）</h4><div className="overflow-hidden rounded-xl border border-slate-200"><table className="w-full text-left text-xs"><thead className="border-b border-slate-200 bg-slate-50 font-semibold text-slate-500"><tr><th className="w-28 p-2.5">阶段与图标</th><th className="p-2.5">判定情况与规则</th></tr></thead><tbody className="divide-y divide-slate-100">{Object.entries(phases).map(([name, config]) => <tr key={name} className="hover:bg-slate-50/50"><td className="p-2.5"><span className={`inline-flex items-center gap-1 whitespace-nowrap rounded border px-2 py-0.5 ${phasePills[name as AccountRevenueRating['phase']]}`}><config.icon className={`h-3.5 w-3.5 flex-none ${config.iconColor}`} />{name}</span></td><td className="p-2.5 leading-relaxed text-slate-600">{config.summary}</td></tr>)}</tbody></table></div></section>
      <section className="rounded-xl border border-slate-200 bg-slate-50 p-3"><strong className="mb-2 block text-slate-800">样式融合呈现示例</strong><div className="flex flex-wrap items-center gap-2">{(['SS', 'S', 'A', 'B', 'C', '待评'] as const).map((example, i) => <span key={example} className={`inline-flex w-max flex-none items-center whitespace-nowrap border leading-[1.5] shadow-2xs ${grades[example].pill} ${sizes.md.wrapper}`}><BadgeFace tier={example} phase={(['爆发', '平稳', '起量', '回落', '尾量', '待判'] as const)[i]} update={(['已更新', '待更新', '查询失败'] as const)[i % 3]} size="md" /></span>)}</div></section>
      {rating && <section className="rounded-xl border border-indigo-100 bg-indigo-50/40 p-3"><strong className="text-slate-800">{account.name} · 当前判定依据</strong><p className="mt-2">{rating.reason}</p><p className="mt-1">{rating.phaseReason}</p><p className="mt-2 text-[11px] text-slate-400">收益截至 {rating.confirmedThrough || '暂无记录'} · 最近查询 {formatRevenueQueryTime(rating.lastQueryAt)}</p><p className="mt-1 text-[11px] text-slate-400">{rating.updateStatus} · {rating.updateReason}</p></section>}
    </StatusBadgeRulesDialog>}
  </>;
}

export function AccountRatingDetails({account}:{account:AccountInfo}) {
  const rating=account.rating;if(!rating)return null;
  const grade=grades[rating.tier],stage=phases[rating.phase],StageIcon=stage.icon;
  const syncTitle=rating.updateStatus==='已更新'?'已更新（有效数据已确认）'
    :rating.updateStatus==='待更新'?'待更新（目标日收益待确认）'
    :rating.recordedTotal===null?'查询失败（等待重试）':'查询失败（已保留原有结果）';
  return <section aria-label="账号复合运营状态评估" className="rounded-xl border border-slate-200/90 bg-white p-3 text-xs shadow-2xs">
    <h4 className="flex items-center gap-1.5 font-bold text-slate-900"><ShieldCheck className="h-4 w-4 flex-none text-indigo-600" />账号复合运营状态评估</h4>
    <div className="mt-3 grid grid-cols-1 gap-2 text-[11px] sm:grid-cols-3">
      <div className="min-w-0 rounded-lg border border-slate-200 bg-slate-50 p-2.5">
        <div className="mb-1 flex items-center gap-1.5 text-[10px] font-medium text-slate-500"><UpdateMark status={rating.updateStatus} size="h-2 w-2" />数据更新状态</div>
        <div className="font-bold text-slate-800">{syncTitle}</div>
        <p className="mt-0.5 line-clamp-1 text-[10px] text-slate-500">{rating.updateReason||syncDescriptions[rating.updateStatus]}</p>
      </div>
      <div className="min-w-0 rounded-lg border border-slate-200 bg-slate-50 p-2.5">
        <div className="mb-1 text-[10px] font-medium text-slate-500">本轮累计已确认收益</div>
        <div className="flex flex-wrap items-center gap-1.5 font-mono font-extrabold text-emerald-700"><span>{rating.recordedTotal===null?'—':money(rating.recordedTotal)}</span><span className={`rounded px-1.5 py-[0.8px] text-[10.5px] ${grade.badge}`}>{rating.tier}</span></div>
        <div className="mt-0.5 text-[10px] text-slate-500">{conditions[rating.tier]}</div>
      </div>
      <div className="min-w-0 rounded-lg border border-slate-200 bg-slate-50 p-2.5">
        <div className="mb-1 text-[10px] font-medium text-slate-500">生命周期阶段与单日表现</div>
        <div className={`flex flex-wrap items-center gap-1.5 font-bold ${stage.color}`}><StageIcon className={`h-3.5 w-3.5 flex-none ${stage.iconColor}`} /><span>{rating.phase==='待判'?'阶段待判断':`${rating.phase}阶段`}</span><span className="font-mono text-[10.5px] font-normal text-slate-500">{rating.lastValid?`（最新单日 ${money(rating.lastValid.amount)}）`:'（暂无确认单日收益）'}</span></div>
        <p className="mt-0.5 line-clamp-1 text-[10px] text-slate-500">{rating.phaseReason||stage.summary}</p>
      </div>
    </div>
    {rating.reviewReason&&<p className="mt-2 rounded-lg bg-orange-50 px-3 py-2 text-[11px] text-orange-800">{rating.reviewReason}</p>}
    <details className="mt-3 text-[11px] text-slate-500">
      <summary className="w-fit cursor-pointer text-indigo-600">查看标签规则与近期记录</summary>
      <div className="mt-2 flex flex-wrap gap-x-5 gap-y-1 text-[10px] text-slate-400"><span>收益截至 {rating.confirmedThrough||'—'}</span><span>最近确认日 {rating.lastValid?.date||'暂无日记录'}</span><span>历史单日峰值 {rating.peak?`${money(rating.peak.amount)} · ${rating.peak.date}`:'—'}</span><span>截至确认日近3日收益 {rating.recentComplete?money(rating.recentTotal):'数据不完整'}</span></div>
      <p className="mt-2 leading-relaxed">{rating.reason} {rating.phaseReason}</p>
      <p className={`mt-1 leading-relaxed ${rating.updateStatus==='查询失败'?'text-rose-600':''}`}>
        {rating.updateStatus} · 最近查询 {formatRevenueQueryTime(rating.lastQueryAt)} · {rating.updateReason}
      </p>
      <p className="mt-2 leading-relaxed">按累计收益：SS大于¥5000；S为¥2000—¥5000；A为¥500—不足¥2000；B为¥{bTierMinimum}—不足¥500；C不足¥{bTierMinimum}且已完成试投。达到金额即升级，正常回落不降级，跨月不清零。累计含已结算且去除重复金额，不等于页面所选区间的未结算收益。</p>
      <p className="mt-1 leading-relaxed">阶段按最后可确认收益日推进：试投、起量、爆发、平稳、回落、尾量、停用；日数据不足时待判。更新状态仅为待更新、已更新、查询失败。采集成功或跨过零点不单独证明收益已发布，等待和失败不计作零收益，不自动停用账号。</p>
      <div className="mt-2 flex flex-wrap gap-3">{rating.recentDays.map(day=><span key={day.date}>{day.date}：{day.amount!==null?money(day.amount):day.state==='failed'?'查询失败':day.state==='partial'?'待确认更新':'未取得记录'}</span>)}</div>
    </details>
  </section>;
}
