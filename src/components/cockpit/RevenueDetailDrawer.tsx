import { CockpitModal } from './CockpitModal';
import React, { useState } from 'react';
import { COCKPIT_DATA, THEATER_NAME_MAP } from '../../data/cockpitData';
import { X, DollarSign, Calendar, Layers, CheckCircle2, AlertCircle, FileText, Filter } from 'lucide-react';

interface RevenueDetailDrawerProps {
  initialTheaterId?: string;
  onClose: () => void;
}

export const RevenueDetailDrawer: React.FC<RevenueDetailDrawerProps> = ({
  initialTheaterId = '3a319630f5cb4dfb8b30e1670bca3172',
  onClose,
}) => {
  const [selectedTheaterId, setSelectedTheaterId] = useState<string>(initialTheaterId);
  const [searchQuery, setSearchQuery] = useState('');
  const [selectedDramaFilter, setSelectedDramaFilter] = useState<string>('all');

  const theaterSource = COCKPIT_DATA.revenue_sources.find(s => s.theater_id === selectedTheaterId);
  const theaterMeta = THEATER_NAME_MAP[selectedTheaterId] || {
    name: '第三方合作剧场',
    tag: '标准接口',
    description: '独立剧场结算系统',
  };

  // 当前剧场的所有 periods
  const theaterPeriods = COCKPIT_DATA.revenue_periods.filter(p => p.theater_id === selectedTheaterId);

  // 未结算可计入分析的 (include_in_analysis === 1)
  const activePeriods = theaterPeriods.filter(p => p.include_in_analysis === 1);
  const currentTotalAmount = activePeriods.reduce((sum, p) => sum + parseFloat(p.amount || '0'), 0);

  // 已结算归档的 (include_in_analysis === 0)
  const settledPeriods = theaterPeriods.filter(p => p.include_in_analysis === 0);
  const settledTotalAmount = settledPeriods.reduce((sum, p) => sum + parseFloat(p.amount || '0'), 0);

  // 如果是青柠剧场，有单片明细 (revenue_details)
  const details = COCKPIT_DATA.revenue_details.filter(d => d.theater_id === selectedTheaterId);

  // 所有独特的剧名列表（从 revenue_details 提取真实 source_drama_name）
  const uniqueDramas = Array.from(new Set(details.map(d => d.source_drama_name))).filter(Boolean);

  // 过滤后的明细
  const filteredDetails = details.filter(d => {
    if (selectedDramaFilter !== 'all' && d.source_drama_name !== selectedDramaFilter) {
      return false;
    }
    if (searchQuery.trim()) {
      const q = searchQuery.toLowerCase();
      const matchDrama = d.source_drama_name.toLowerCase().includes(q);
      const matchAccount = d.account_id.toLowerCase().includes(q);
      const matchVideo = d.source_video_id.toLowerCase().includes(q);
      return matchDrama || matchAccount || matchVideo;
    }
    return true;
  });

  return (
    <CockpitModal label="收益详情" onClose={onClose} width="max-w-5xl">
        {/* Header */}
        <div className="px-6 py-5 border-b border-slate-100 flex items-center justify-between bg-slate-50/70">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-emerald-500 to-teal-600 text-white font-extrabold flex items-center justify-center text-sm shadow-sm">
              <DollarSign className="w-5 h-5 stroke-[2.4]" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h3 className="text-base font-extrabold text-[#1E1644]">剧场收益与对账明细</h3>
                <span className="text-[11px] font-semibold px-2 py-0.5 rounded bg-emerald-50 text-emerald-700 border border-emerald-200">
                  来源：剧场独立查询
                </span>
              </div>
              <p className="text-xs text-slate-400 mt-0.5">
                支持按剧场独立接口精度查验未结算流水与作品分账明细
              </p>
            </div>
          </div>

          <button
            onClick={onClose}
            className="p-2 rounded-xl text-slate-400 hover:text-slate-700 hover:bg-slate-100 transition-colors"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Theater Switcher Segmented Bar */}
        <div className="px-6 py-3 border-b border-slate-100 bg-white flex items-center justify-between gap-4">
          <div className="flex items-center gap-2 p-1 bg-slate-100 rounded-xl">
            {COCKPIT_DATA.revenue_sources.map(src => {
              const meta = THEATER_NAME_MAP[src.theater_id];
              const isSelected = selectedTheaterId === src.theater_id;
              return (
                <button
                  key={src.theater_id}
                  onClick={() => {
                    setSelectedTheaterId(src.theater_id);
                    setSelectedDramaFilter('all');
                    setSearchQuery('');
                  }}
                  className={`flex items-center gap-2 px-3.5 py-1.5 rounded-lg text-xs font-bold transition-all ${
                    isSelected
                      ? 'bg-white text-indigo-900 shadow-xs border border-black/[0.04]'
                      : 'text-slate-500 hover:text-slate-900'
                  }`}
                >
                  <span>{meta?.name || src.theater_id.slice(0, 8)}</span>
                  <span
                    className={`text-[10px] px-1.5 py-0.2 rounded font-mono ${
                      src.supports_detail ? 'bg-emerald-100 text-emerald-800' : 'bg-slate-200 text-slate-700'
                    }`}
                  >
                    {src.date_precision === 'day' ? '按日明细' : '月累计'}
                  </span>
                </button>
              );
            })}
          </div>

          <div className="text-right">
            <span className="text-xs text-slate-400">当前剧场未结算</span>
            <p className="text-base font-extrabold text-emerald-600 font-mono tabular-nums leading-none mt-0.5">
              ¥{currentTotalAmount.toLocaleString('zh-CN', { minimumFractionDigits: 2 })}
            </p>
          </div>
        </div>

        {/* Body Content */}
        <div className="min-h-0 flex-1 overflow-y-auto p-6 space-y-6">
          {/* Theater Protocol Specs Banner */}
          <div className="p-4 rounded-xl bg-slate-50 border border-slate-200/80">
            <div className="flex items-start justify-between">
              <div>
                <div className="flex items-center gap-2">
                  <h4 className="text-xs font-bold text-slate-800">{theaterMeta.name} · 接口返回规范说明</h4>
                  <span className="text-[10px] px-2 py-0.5 rounded bg-slate-200/70 text-slate-600 font-mono">
                    adapter: {theaterSource?.adapter_key}
                  </span>
                </div>
                <p className="text-xs text-slate-500 mt-1">{theaterMeta.description}</p>
              </div>
              <div className="text-right text-[11px] text-slate-400">
                最后拉取: {theaterSource?.last_checked_at.slice(0, 16).replace('T', ' ')}
              </div>
            </div>

            <div className="grid grid-cols-4 gap-3 mt-3 pt-3 border-t border-slate-200/60 text-xs">
              <div>
                <span className="text-slate-400 text-[11px]">查询模式:</span>
                <p className="font-mono font-semibold text-slate-700">{theaterSource?.query_mode}</p>
              </div>
              <div>
                <span className="text-slate-400 text-[11px]">日期精度:</span>
                <p className="font-mono font-semibold text-slate-700">
                  {theaterSource?.date_precision === 'day' ? '单日精度 (day)' : '按月汇总 (month)'}
                </p>
              </div>
              <div>
                <span className="text-slate-400 text-[11px]">作品级明细:</span>
                <p className="font-semibold text-slate-700 flex items-center gap-1">
                  {theaterSource?.supports_detail ? (
                    <span className="text-emerald-600 flex items-center gap-0.5">
                      <CheckCircle2 className="w-3.5 h-3.5" /> 支持
                    </span>
                  ) : (
                    <span className="text-slate-400">不支持单片拆解</span>
                  )}
                </p>
              </div>
              <div>
                <span className="text-slate-400 text-[11px]">入账规则:</span>
                <p className="text-[11px] text-slate-600">
                  已结算月份 (include=0) 排除
                </p>
              </div>
            </div>
          </div>

          {/* If Touch Theater (Month Cumulative without details) */}
          {!theaterSource?.supports_detail ? (
            <div className="space-y-4">
              <div className="p-4 rounded-xl bg-amber-50/70 border border-amber-200 text-xs text-amber-900 flex items-start gap-2.5">
                <AlertCircle className="w-4 h-4 text-amber-600 shrink-0 mt-0.5" />
                <div>
                  <p className="font-bold">数据约束提示：该剧场仅返回月度累计流水，未提供每日明细接口</p>
                  <p className="text-amber-700 mt-0.5 leading-relaxed">
                    系统严格遵守“不将月累计收益画成每日假收益曲线”规范。下方列表为该剧场当前未结算账期（2026-10）与已归档结算历史（2026-09）的各账号实际返回总额。
                  </p>
                </div>
              </div>

              {/* Month Unsettled Table */}
              <div>
                <div className="flex items-center justify-between mb-2">
                  <h4 className="text-xs font-bold text-slate-800">
                    2026-10 未结算周期账号金额清单 (计入当前总收益)
                  </h4>
                  <span className="text-xs font-bold text-emerald-600 font-mono">
                    小计: ¥{currentTotalAmount.toFixed(2)}
                  </span>
                </div>
                <div className="border border-slate-200 rounded-xl overflow-hidden">
                  <table className="w-full text-left text-xs">
                    <thead className="bg-slate-50 text-slate-500 font-semibold border-b border-slate-200">
                      <tr>
                        <th className="py-2.5 px-3">账号标识</th>
                        <th className="py-2.5 px-3">账期标签</th>
                        <th className="py-2.5 px-3">结算状态</th>
                        <th className="py-2.5 px-3">分析纳入</th>
                        <th className="py-2.5 px-3 text-right">金额 (CNY)</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-100 font-mono">
                      {activePeriods.map(p => (
                        <tr key={p.account_id} className="hover:bg-slate-50/70">
                          <td className="py-2 px-3 font-semibold text-slate-700">{p.account_id}</td>
                          <td className="py-2 px-3 text-slate-500">{p.period_label}</td>
                          <td className="py-2 px-3 text-amber-600 font-medium">未结算 (unsettled)</td>
                          <td className="py-2 px-3 text-emerald-600 font-medium">计入分析 (include=1)</td>
                          <td className="py-2 px-3 text-right font-extrabold text-[#1E1644] tabular-nums">
                            ¥{parseFloat(p.amount).toFixed(2)}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>

              {/* Past Settled History (Exempted) */}
              <div>
                <div className="flex items-center justify-between mb-2">
                  <h4 className="text-xs font-bold text-slate-500">
                    2026-09 已结算历史归档 (include_in_analysis=0，不计入当前收益)
                  </h4>
                  <span className="text-xs text-slate-400 font-mono">
                    归档金额: ¥{settledTotalAmount.toFixed(2)}
                  </span>
                </div>
                <div className="border border-slate-200/60 rounded-xl overflow-hidden opacity-75">
                  <table className="w-full text-left text-xs">
                    <thead className="bg-slate-100/60 text-slate-400 font-semibold border-b border-slate-200/60">
                      <tr>
                        <th className="py-2 px-3">账号标识</th>
                        <th className="py-2 px-3">账期标签</th>
                        <th className="py-2 px-3">结算状态</th>
                        <th className="py-2 px-3 text-right">归档金额 (CNY)</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-100 font-mono">
                      {settledPeriods.slice(0, 5).map(p => (
                        <tr key={p.account_id} className="text-slate-500">
                          <td className="py-1.5 px-3">{p.account_id}</td>
                          <td className="py-1.5 px-3">{p.period_label}</td>
                          <td className="py-1.5 px-3 text-slate-400">已结算 (settled)</td>
                          <td className="py-1.5 px-3 text-right tabular-nums">¥{parseFloat(p.amount).toFixed(2)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                  <div className="p-2 text-center bg-slate-50 text-[11px] text-slate-400">
                    其余 {settledPeriods.length - 5} 个账号已结算记录已静默收录
                  </div>
                </div>
              </div>
            </div>
          ) : (
            /* If Qingning Theater (Supports Details) */
            <div className="space-y-4">
              {/* Filter controls */}
              <div className="flex flex-col sm:flex-row items-center justify-between gap-3 p-3 bg-slate-50 rounded-xl border border-slate-200/70">
                <div className="flex items-center gap-2 w-full sm:w-auto">
                  <Filter className="w-3.5 h-3.5 text-slate-400" />
                  <span className="text-xs text-slate-500 shrink-0">筛选剧名:</span>
                  <select
                    value={selectedDramaFilter}
                    onChange={e => setSelectedDramaFilter(e.target.value)}
                    className="text-xs font-semibold text-slate-800 bg-white border border-slate-200 rounded-lg px-2.5 py-1 focus:outline-none focus:ring-1 focus:ring-indigo-500"
                  >
                    <option value="all">全部剧目 ({uniqueDramas.length})</option>
                    {uniqueDramas.map(name => (
                      <option key={name} value={name}>
                        《{name}》
                      </option>
                    ))}
                  </select>
                </div>

                <div className="w-full sm:w-64">
                  <input
                    type="text"
                    placeholder="按作品ID / 账号搜索..."
                    value={searchQuery}
                    onChange={e => setSearchQuery(e.target.value)}
                    className="w-full text-xs bg-white border border-slate-200 rounded-lg px-3 py-1.5 focus:outline-none focus:ring-1 focus:ring-indigo-500 text-slate-800 placeholder-slate-400"
                  />
                </div>
              </div>

              {/* Detail Table */}
              <div>
                <div className="flex items-center justify-between mb-2">
                  <div className="flex items-center gap-2">
                    <FileText className="w-4 h-4 text-emerald-600" />
                    <h4 className="text-xs font-bold text-slate-800">
                      2026-10-29 作品级流水收益明细 ({filteredDetails.length} 条)
                    </h4>
                  </div>
                  <span className="text-xs font-mono text-slate-400">
                    明细流水合计: ¥
                    {filteredDetails
                      .reduce((sum, d) => sum + parseFloat(d.gross_revenue || '0'), 0)
                      .toFixed(2)}
                  </span>
                </div>

                <div className="border border-slate-200 rounded-xl overflow-hidden max-h-[460px] overflow-y-auto">
                  <table className="w-full text-left text-xs">
                    <thead className="bg-slate-50 text-slate-500 font-semibold border-b border-slate-200 sticky top-0 z-10">
                      <tr>
                        <th className="py-2.5 px-3">所属剧目</th>
                        <th className="py-2.5 px-3">作品编号</th>
                        <th className="py-2.5 px-3">投放账号</th>
                        <th className="py-2.5 px-3 text-right">单片播放</th>
                        <th className="py-2.5 px-3 text-right">全剧播放</th>
                        <th className="py-2.5 px-3 text-right">分账流水 (CNY)</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-100 font-mono">
                      {filteredDetails.map(d => (
                        <tr key={`${d.account_id}-${d.source_video_id}`} className="hover:bg-indigo-50/40">
                          <td className="py-2 px-3 font-bold text-slate-800">《{d.source_drama_name}》</td>
                          <td className="py-2 px-3 text-indigo-600">{d.source_video_id}</td>
                          <td className="py-2 px-3 text-slate-600">{d.account_id}</td>
                          <td className="py-2 px-3 text-right text-slate-700 tabular-nums">
                            {d.video_views.toLocaleString()}
                          </td>
                          <td className="py-2 px-3 text-right text-slate-400 tabular-nums">
                            {d.drama_views.toLocaleString()}
                          </td>
                          <td className="py-2 px-3 text-right font-bold text-emerald-600 tabular-nums">
                            ¥{parseFloat(d.gross_revenue).toFixed(2)}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            </div>
          )}
        </div>
    </CockpitModal>
  );
};
