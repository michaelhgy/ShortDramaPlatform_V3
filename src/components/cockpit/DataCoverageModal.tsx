import { CockpitModal } from './CockpitModal';
import React from 'react';
import { COCKPIT_DATA, THEATER_NAME_MAP } from '../../data/cockpitData';
import { X, Database, ShieldCheck, CheckCircle2, AlertTriangle, Layers, Info, RefreshCw } from 'lucide-react';

interface DataCoverageModalProps {
  isOpen: boolean;
  onClose: () => void;
  onReloadData?: () => void;
}

export const DataCoverageModal: React.FC<DataCoverageModalProps> = ({
  isOpen,
  onClose,
  onReloadData,
}) => {
  if (!isOpen) return null;

  return (
    <CockpitModal label="数据覆盖详情" onClose={onClose} width="max-w-4xl">
        {/* Header */}
        <div className="px-6 py-5 border-b border-slate-100 flex items-center justify-between bg-slate-50/80">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-[#1E1644] text-[#DDFD00] flex items-center justify-center shadow-sm">
              <Database className="w-5 h-5" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h3 className="text-base font-extrabold text-[#1E1644]">数据采集与覆盖状态全景</h3>
                <span className="text-[11px] font-bold px-2 py-0.5 rounded bg-amber-50 text-amber-800 border border-amber-200">
                  演示数据包 v{COCKPIT_DATA.package.version}
                </span>
              </div>
              <p className="text-xs text-slate-400 mt-0.5">
                快照截至: {COCKPIT_DATA.package.latest_date} · 覆盖范围: {COCKPIT_DATA.package.range.start} ~ {COCKPIT_DATA.package.range.end}
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

        {/* Content Body */}
        <div className="p-6 space-y-6 max-h-[75vh] overflow-y-auto text-xs">
          {/* Status Discipline Banner */}
          <div className="p-4 rounded-xl bg-indigo-50/70 border border-indigo-200/80 text-indigo-950">
            <div className="flex items-center gap-2 font-bold mb-1 text-indigo-900">
              <Info className="w-4 h-4 text-indigo-600" />
              <span>数据状态严谨性声明 (Data State Discipline)</span>
            </div>
            <p className="text-indigo-800 leading-relaxed text-[11px]">
              系统严格执行规范：<strong>缺失 (missing)、查询失败 (failed)、明确为0 (zero)、正常记录 (record)</strong> 必须四态独立区分，严禁把无返回记录的缺失账号直接判定显示为 0。
            </p>
          </div>

          {/* 4 State Badges Cards */}
          <div className="grid grid-cols-4 gap-3 text-center">
            <div className="p-3.5 rounded-xl bg-emerald-50/60 border border-emerald-200">
              <span className="text-[11px] text-emerald-800 font-bold block">正常有记录 (record)</span>
              <p className="text-2xl font-extrabold text-emerald-700 font-mono mt-1">8</p>
              <span className="text-[10px] text-emerald-600">8 个账号全部正常返回</span>
            </div>

            <div className="p-3.5 rounded-xl bg-slate-50 border border-slate-200">
              <span className="text-[11px] text-slate-600 font-bold block">明确为0 (zero)</span>
              <p className="text-2xl font-extrabold text-slate-500 font-mono mt-1">0</p>
              <span className="text-[10px] text-slate-400">有返回且明确无播放</span>
            </div>

            <div className="p-3.5 rounded-xl bg-amber-50/60 border border-amber-200">
              <span className="text-[11px] text-amber-800 font-bold block">缺失无记录 (missing)</span>
              <p className="text-2xl font-extrabold text-amber-600 font-mono mt-1">0</p>
              <span className="text-[10px] text-amber-600">无静默丢失</span>
            </div>

            <div className="p-3.5 rounded-xl bg-rose-50/60 border border-rose-200">
              <span className="text-[11px] text-rose-800 font-bold block">查询失败 (failed)</span>
              <p className="text-2xl font-extrabold text-rose-600 font-mono mt-1">0</p>
              <span className="text-[10px] text-rose-600">采集失败率为 0%</span>
            </div>
          </div>

          {/* Account Diagnostics Matrix */}
          <div>
            <h4 className="font-bold text-slate-800 mb-2">账号快照与健康状态矩阵</h4>
            <div className="border border-slate-200 rounded-xl overflow-hidden">
              <table className="w-full text-left">
                <thead className="bg-slate-50 text-slate-500 font-semibold border-b border-slate-200">
                  <tr>
                    <th className="py-2 px-3">账号名称</th>
                    <th className="py-2 px-3">分组</th>
                    <th className="py-2 px-3">数据状态</th>
                    <th className="py-2 px-3">视频状态</th>
                    <th className="py-2 px-3">热度状态</th>
                    <th className="py-2 px-3">异常作品数</th>
                    <th className="py-2 px-3">记录天数</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100 font-mono">
                  {COCKPIT_DATA.account_cards.map(acc => {
                    const diag = COCKPIT_DATA.diagnostics.find(d => d.account_id === acc.account_id);
                    return (
                      <tr key={acc.account_id} className="hover:bg-slate-50">
                        <td className="py-2 px-3 font-semibold text-slate-800">{acc.account_name}</td>
                        <td className="py-2 px-3 text-slate-500">{acc.group_name}</td>
                        <td className="py-2 px-3">
                          <span className="px-1.5 py-0.5 rounded bg-emerald-100 text-emerald-800 text-[10px] font-bold">
                            {acc.latest.data_state}
                          </span>
                        </td>
                        <td className="py-2 px-3">
                          <span className={diag?.video_status === '需复核' ? 'text-amber-600 font-bold' : 'text-slate-600'}>
                            {diag?.video_status || '正常'}
                          </span>
                        </td>
                        <td className="py-2 px-3">
                          <span className={diag?.heat_status === '偏低' ? 'text-rose-600 font-bold' : 'text-slate-600'}>
                            {diag?.heat_status || '正常'}
                          </span>
                        </td>
                        <td className="py-2 px-3 text-slate-600 tabular-nums">
                          {diag?.abnormal_post_count || 0}
                        </td>
                        <td className="py-2 px-3 text-indigo-600 font-semibold tabular-nums">
                          {acc.record_days}/{acc.expected_days} 天
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </div>

          {/* Revenue Source Adapter Specs */}
          <div>
            <h4 className="font-bold text-slate-800 mb-2">剧场接口适配矩阵 (各剧场独立查询)</h4>
            <div className="grid grid-cols-2 gap-3">
              {COCKPIT_DATA.revenue_sources.map(src => {
                const meta = THEATER_NAME_MAP[src.theater_id];
                return (
                  <div key={src.theater_id} className="p-3.5 rounded-xl border border-slate-200 bg-slate-50/50">
                    <div className="flex items-center justify-between">
                      <span className="font-bold text-slate-800">{meta?.name}</span>
                      <span className="text-[10px] px-1.5 py-0.5 rounded bg-slate-200 font-mono text-slate-600">
                        {src.adapter_key}
                      </span>
                    </div>
                    <div className="mt-2 space-y-1 text-[11px] text-slate-500">
                      <div>返回精度: <span className="font-semibold text-slate-700">{src.date_precision} ({src.date_precision === 'day' ? '按日' : '按月'})</span></div>
                      <div>单片明细: <span className="font-semibold text-slate-700">{src.supports_detail ? '支持作品/剧名' : '仅月总额'}</span></div>
                      <div>适配状态: <span className="font-semibold text-emerald-600">{src.adapter_status}</span></div>
                    </div>
                    <div className="mt-2 pt-2 border-t border-slate-200/60 text-[10px] text-slate-400">
                      {src.notes}
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        </div>

        {/* Footer */}
        <div className="px-6 py-4 border-t border-slate-100 bg-slate-50 flex items-center justify-between">
          <span className="text-xs text-slate-400">
            视频号流量快照来自小V猫官方后台 · 收益来自剧场独立对账
          </span>
          <div className="flex items-center gap-3">
            {onReloadData && (
              <button
                onClick={onReloadData}
                className="flex items-center gap-1.5 px-3 py-1.5 rounded-xl bg-white border border-slate-200 text-slate-700 hover:bg-slate-100 font-medium text-xs transition-colors cursor-pointer"
              >
                <RefreshCw className="w-3.5 h-3.5" />
                <span>重新读取已保存数据</span>
              </button>
            )}
            <button
              onClick={onClose}
              className="px-4 py-1.5 rounded-xl bg-[#1E1644] text-white hover:bg-black font-semibold text-xs transition-colors cursor-pointer"
            >
              关闭
            </button>
          </div>
        </div>
    </CockpitModal>
  );
};
