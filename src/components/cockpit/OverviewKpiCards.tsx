import { formatOptimizationRate } from '../../services/optimizationHealth';
import { AlertTriangle, Award, DollarSign, Film, Play, ShieldAlert } from 'lucide-react';
import type { createCockpitModel } from '../../services/cockpitModel';

type Summary = ReturnType<ReturnType<typeof createCockpitModel>['getKPISummary']>;

export function OverviewKpiCards({ summary, days }: { summary: Summary; days: number }) {
  const cards = [
    { id: 'revenue', title: '矩阵区间创收', value: !summary.hasRevenue ? '—' : `¥${summary.totalRevenue.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`, unit: '',
      detail: !summary.hasRevenue ? '—' : `日均 ¥${Math.round(summary.totalRevenue / Math.max(days, 1)).toLocaleString('zh-CN')}`, icon: DollarSign,
      iconColor: 'bg-emerald-50 text-emerald-600', valueColor: 'text-emerald-700', detailColor: 'text-emerald-600' },
    { id: 'views', title: '区间播放', value: summary.hasTraffic ? (summary.totalViews / 10000).toFixed(1) : '—', unit: summary.hasTraffic ? '万次' : '',
      detail: '所选区间新增播放', icon: Play,
      iconColor: 'bg-indigo-50 text-indigo-600', valueColor: 'text-indigo-600', detailColor: 'text-slate-400' },
    { id: 'rpm', title: '万播收益（RPM）', value: summary.hasRevenue && summary.hasTraffic && summary.totalViews > 0 ? `¥${summary.rpm}` : '—', unit: '',
      detail: '每万次播放变现额', icon: Award,
      iconColor: 'bg-purple-50 text-purple-600', valueColor: 'text-purple-700', detailColor: 'text-slate-400' },
    { id: 'published', title: '发布作品', value: summary.totalVideos.toLocaleString('zh-CN'), unit: '条',
      detail: `发布账号 ${summary.publishedAccountCount} 个`, icon: Film,
      iconColor: 'bg-blue-50 text-blue-600', valueColor: 'text-blue-600', detailColor: 'text-slate-400' },
    { id: 'originality', title: '原创优化率', value: summary.originalOptRate === null ? '—' : summary.originalOptimizedVideos.toLocaleString('zh-CN'), unit: summary.originalOptRate === null ? '' : '条',
      detail: `优化率 ${formatOptimizationRate(summary.originalOptRate)}`, icon: ShieldAlert,
      iconColor: 'bg-indigo-50 text-indigo-600', valueColor: 'text-indigo-600', detailColor: 'text-indigo-600' },
    { id: 'warnings', title: '平台优化预警', value: summary.overallOptRate === null ? '—' : summary.optimizedVideos.toLocaleString('zh-CN'), unit: summary.overallOptRate === null ? '' : '条',
      detail: `受限率 ${formatOptimizationRate(summary.overallOptRate)}`, icon: AlertTriangle,
      iconColor: 'bg-rose-100 text-rose-600', valueColor: 'text-rose-600', detailColor: 'text-rose-600' },
  ];
  return <section aria-label="核心经营指标" className="grid grid-cols-2 gap-3.5 md:grid-cols-3 xl:grid-cols-6">
    {cards.map(card => <article key={card.id} data-overview-kpi={card.id} aria-label={card.title}
      className={`flex min-w-0 flex-col justify-between rounded-2xl border p-4 shadow-xs ${card.id === 'warnings' ? 'border-rose-200/80 bg-white bg-rose-50/10' : 'border-slate-200/80 bg-white'}`}>
      <div className={`flex items-center justify-between gap-1 ${card.id === 'warnings' ? 'text-rose-600' : 'text-slate-500'}`}>
        <span className="text-xs font-medium">{card.title}</span>
        <span className={`shrink-0 rounded-lg p-1.5 ${card.iconColor}`}><card.icon className="h-3.5 w-3.5" /></span>
      </div>
      <div className="mt-2">
        <div className={`font-mono text-xl font-black tracking-tight ${card.valueColor}`}>{card.value}
          {card.unit && <span className={`ml-1 text-xs font-normal ${card.id === 'views' || card.id === 'published' ? 'text-inherit' : 'text-slate-500'}`}>{card.unit}</span>}
        </div>
        <div className={`mt-0.5 text-[11px] ${card.id === 'warnings' || card.id === 'revenue' ? 'font-medium' : ''} ${card.detailColor}`}>{card.detail}</div>
      </div>
    </article>)}
  </section>;
}
