import React, { useState } from 'react';
import { VideoTrafficTags } from './VideoTrafficTags';
import { ACCOUNT_DAILY_COLUMNS, accountDailyCell, accountDailyExport } from '../../services/accountDailyExport';
import { 
  RevenueRecord, 
  AccountDailyTrafficDetail, 
  VideoTrafficItem 
} from '../../types/shortDramaOps';
import { 
  Download, 
  Table, 
  DollarSign, 
  Activity, 
  Film, 
  Search, 
  ArrowUpDown, 
  CheckCircle2, 
  Sparkles,
  ChevronLeft,
  ChevronRight
} from 'lucide-react';

interface DataPivotViewProps {
  revenueList: RevenueRecord[];
  trafficList: AccountDailyTrafficDetail[];
  videoList: VideoTrafficItem[];
  showToast?: (msg: string) => void;
}

export const DataPivotView: React.FC<DataPivotViewProps> = ({
  revenueList,
  trafficList,
  videoList,
  showToast = (_msg: string) => {}
}) => {
  const [activeSubTab, setActiveSubTab] = useState<'video' | 'traffic' | 'revenue'>('video');
  const [searchQuery, setSearchQuery] = useState('');
  const [currentPage, setCurrentPage] = useState(1);
  const pageSize = 20;

  // 导出 CSV 功能
  const handleExportCSV = () => {
    let headers: string[] = [];
    let rows: string[][] = [];
    let filename = '';

    if (activeSubTab === 'revenue') {
      filename = `短剧矩阵_收益明细_${new Date().toISOString().slice(0, 10)}.csv`;
      headers = ['记录ID', '账号名称', '所属剧场', '日期', '收益金额(元)'];
      rows = revenueList.map(r => [r.id, r.accountName, r.theater, r.date, r.amount.toString()]);
    } else if (activeSubTab === 'traffic') {
      filename = `短剧矩阵_账号日流量_${new Date().toISOString().slice(0, 10)}.csv`;
      ({headers,rows} = accountDailyExport(trafficList));
    } else {
      filename = `短剧矩阵_视频切片流量_${new Date().toISOString().slice(0, 10)}.csv`;
      headers = ['视频ID', '账号名称', '所属剧场', '文件名(剧名-n)', '发布时间', '播放量', '完播率(%)', '爱心', '评论', '转发', '点赞', '是否被优化'];
      rows = videoList.map(v => [
        v.id,
        v.accountName,
        v.theater,
        v.fileName,
        v.publishTime,
        v.views.toString(),
        v.completionRate.toString(),
        v.hearts.toString(),
        v.comments.toString(),
        v.shares.toString(),
        v.thumbsUp.toString(),
        v.hasOptimization ? '是' : '否'
      ]);
    }

    const csvContent = '\uFEFF' + [headers.join(','), ...rows.map(r => r.map(c => `"${c.replace(/"/g, '""')}"`).join(','))].join('\n');
    const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.setAttribute('href', url);
    link.setAttribute('download', filename);
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    URL.revokeObjectURL(url);
    showToast(`✅ 成功导出 ${rows.length} 条数据至 ${filename}`);
  };

  // 重置分页
  React.useEffect(() => {
    setCurrentPage(1);
  }, [activeSubTab, searchQuery]);

  return (
    <div className="bg-white rounded-2xl border border-slate-200/80 shadow-sm overflow-hidden space-y-0">
      {/* 顶部控制栏 */}
      <div className="p-5 border-b border-slate-100 flex flex-col md:flex-row md:items-center justify-between gap-4 bg-slate-50/60">
        <div className="flex flex-wrap items-center gap-2">
          <button
            onClick={() => setActiveSubTab('video')}
            className={`px-4 py-2 rounded-xl text-xs font-bold transition-all flex items-center gap-2 cursor-pointer ${
              activeSubTab === 'video'
                ? 'bg-indigo-600 text-white shadow-sm'
                : 'bg-white text-slate-600 border border-slate-200 hover:bg-slate-50'
            }`}
          >
            <Film className="w-3.5 h-3.5" />
            <span>账号的视频流量情况 ({videoList.length})</span>
          </button>

          <button
            onClick={() => setActiveSubTab('traffic')}
            className={`px-4 py-2 rounded-xl text-xs font-bold transition-all flex items-center gap-2 cursor-pointer ${
              activeSubTab === 'traffic'
                ? 'bg-indigo-600 text-white shadow-sm'
                : 'bg-white text-slate-600 border border-slate-200 hover:bg-slate-50'
            }`}
          >
            <Activity className="w-3.5 h-3.5" />
            <span>账号日流量情况 ({trafficList.length})</span>
          </button>

          <button
            onClick={() => setActiveSubTab('revenue')}
            className={`px-4 py-2 rounded-xl text-xs font-bold transition-all flex items-center gap-2 cursor-pointer ${
              activeSubTab === 'revenue'
                ? 'bg-indigo-600 text-white shadow-sm'
                : 'bg-white text-slate-600 border border-slate-200 hover:bg-slate-50'
            }`}
          >
            <DollarSign className="w-3.5 h-3.5" />
            <span>账号收益明细 ({revenueList.length})</span>
          </button>
        </div>

        <div className="flex items-center gap-3">
          <div className="relative">
            <Search className="w-4 h-4 text-slate-400 absolute left-3 top-1/2 -translate-y-1/2" />
            <input
              type="text"
              placeholder="搜账号 / 剧名-n / 剧场..."
              value={searchQuery}
              onChange={e => setSearchQuery(e.target.value)}
              className="pl-9 pr-4 py-1.5 bg-white border border-slate-200 rounded-xl text-xs text-slate-800 focus:outline-none focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-500 w-56"
            />
          </div>

          <button
            onClick={handleExportCSV}
            className="px-3.5 py-1.5 bg-slate-900 hover:bg-slate-800 text-white rounded-xl text-xs font-semibold shadow-sm transition-all flex items-center gap-1.5 cursor-pointer"
          >
            <Download className="w-3.5 h-3.5" />
            <span>导出 CSV</span>
          </button>
        </div>
      </div>

      {/* 表格内容区 */}
      <div className="overflow-x-auto">
        {/* 1. 视频流量透视表 */}
        {activeSubTab === 'video' && (
          <table className="w-full text-left border-collapse text-xs">
            <thead>
              <tr className="bg-slate-50/80 text-slate-500 font-semibold border-b border-slate-100">
                <th className="py-3 px-4">文件名 (规范: 剧名-n)</th>
                <th className="py-3 px-4">所属账号</th>
                <th className="py-3 px-4">绑定剧场</th>
                <th className="py-3 px-4">精确发布时间</th>
                <th className="py-3 px-4 text-right">播放量</th>
                <th className="py-3 px-4 text-right">完播率</th>
                <th className="py-3 px-4 text-right">爱心</th>
                <th className="py-3 px-4 text-right">评论</th>
                <th className="py-3 px-4 text-right">转发</th>
                <th className="py-3 px-4 text-right">点赞</th>
                <th className="py-3 px-4 text-center">视频标签</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100 text-slate-700">
              {videoList
                .filter(v => {
                  if (!searchQuery.trim()) return true;
                  const q = searchQuery.toLowerCase();
                  return (
                    v.fileName.toLowerCase().includes(q) ||
                    v.accountName.toLowerCase().includes(q) ||
                    v.theater.toLowerCase().includes(q)
                  );
                })
                .slice((currentPage - 1) * pageSize, currentPage * pageSize)
                .map(v => (
                  <tr key={v.id} className="hover:bg-slate-50/60 transition-colors">
                    <td className="py-3 px-4 font-mono font-bold text-slate-900">
                      {v.fileName}
                    </td>
                    <td className="py-3 px-4 font-medium">{v.accountName}</td>
                    <td className="py-3 px-4 text-slate-500">{v.theater}</td>
                    <td className="py-3 px-4 font-mono text-slate-500">{v.publishTime}</td>
                    <td className="py-3 px-4 text-right font-bold text-slate-900">
                      {v.views.toLocaleString()}
                    </td>
                    <td className="py-3 px-4 text-right font-bold text-emerald-600">
                      {v.completionRate}%
                    </td>
                    <td className="py-3 px-4 text-right">{v.hearts.toLocaleString()}</td>
                    <td className="py-3 px-4 text-right">{v.comments.toLocaleString()}</td>
                    <td className="py-3 px-4 text-right">{v.shares.toLocaleString()}</td>
                    <td className="py-3 px-4 text-right">{v.thumbsUp.toLocaleString()}</td>
                    <td className="py-3 px-4 text-center">
                      <VideoTrafficTags video={v} />
                    </td>
                  </tr>
                ))}
            </tbody>
          </table>
        )}

        {/* 2. 账号日流量透视表 */}
        {activeSubTab === 'traffic' && (
          <table className="w-full text-left border-collapse text-xs">
            <thead>
              <tr className="bg-slate-50/80 text-slate-500 font-semibold border-b border-slate-100">
                {ACCOUNT_DAILY_COLUMNS.map(column => <th key={column.key}
                  className={`py-3 px-4 whitespace-nowrap ${column.numeric ? 'text-right' : ''}`}>{column.title}</th>)}
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100 text-slate-700">
              {trafficList
                .filter(t => {
                  if (!searchQuery.trim()) return true;
                  const q = searchQuery.toLowerCase();
                  return t.accountName.toLowerCase().includes(q) || t.theater.toLowerCase().includes(q);
                })
                .slice((currentPage - 1) * pageSize, currentPage * pageSize)
                .map(t => (
                  <tr key={t.id} className="hover:bg-slate-50/60 transition-colors">
                    {ACCOUNT_DAILY_COLUMNS.map(column => <td key={column.key}
                      className={`py-3 px-4 whitespace-nowrap ${column.numeric ? 'text-right tabular-nums' : ''} ${column.key === 'views' || column.key === 'accountName' ? 'font-bold text-slate-900' : column.key === 'follows' ? 'font-bold text-indigo-600' : ''}`}>
                      {accountDailyCell(t[column.key],column.signed)}
                    </td>)}
                  </tr>
                ))}
            </tbody>
          </table>
        )}

        {/* 3. 收益明细透视表 */}
        {activeSubTab === 'revenue' && (
          <table className="w-full text-left border-collapse text-xs">
            <thead>
              <tr className="bg-slate-50/80 text-slate-500 font-semibold border-b border-slate-100">
                <th className="py-3 px-4">账号</th>
                <th className="py-3 px-4">绑定剧场</th>
                <th className="py-3 px-4">日期</th>
                <th className="py-3 px-4 text-right">当日收益金额</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100 text-slate-700">
              {revenueList
                .filter(r => {
                  if (!searchQuery.trim()) return true;
                  const q = searchQuery.toLowerCase();
                  return r.accountName.toLowerCase().includes(q) || r.theater.toLowerCase().includes(q);
                })
                .slice((currentPage - 1) * pageSize, currentPage * pageSize)
                .map(r => (
                  <tr key={r.id} className="hover:bg-slate-50/60 transition-colors">
                    <td className="py-3 px-4 font-bold text-slate-900">{r.accountName}</td>
                    <td className="py-3 px-4 text-slate-500">{r.theater}</td>
                    <td className="py-3 px-4 font-mono text-slate-500">{r.date}</td>
                    <td className="py-3 px-4 text-right font-bold text-emerald-600">
                      ¥{r.amount.toLocaleString()}
                    </td>
                  </tr>
                ))}
            </tbody>
          </table>
        )}
      </div>

      {/* 底部翻页控制器 */}
      <div className="p-4 border-t border-slate-100 flex items-center justify-between bg-slate-50/40 text-xs text-slate-500">
        <span>
          当前展示第 <strong>{(currentPage - 1) * pageSize + 1}</strong> 至{' '}
          <strong>
            {Math.min(
              currentPage * pageSize,
              activeSubTab === 'video'
                ? videoList.length
                : activeSubTab === 'traffic'
                  ? trafficList.length
                  : revenueList.length
            )}
          </strong>{' '}
          条，共{' '}
          {activeSubTab === 'video'
            ? videoList.length
            : activeSubTab === 'traffic'
              ? trafficList.length
              : revenueList.length}{' '}
          条记录
        </span>

        <div className="flex items-center gap-2">
          <button
            onClick={() => setCurrentPage(p => Math.max(1, p - 1))}
            disabled={currentPage === 1}
            className="p-1.5 rounded-lg border border-slate-200 bg-white text-slate-600 hover:bg-slate-50 disabled:opacity-40 disabled:cursor-not-allowed cursor-pointer"
          >
            <ChevronLeft className="w-4 h-4" />
          </button>
          <span className="font-mono font-medium">第 {currentPage} 页</span>
          <button
            onClick={() => setCurrentPage(p => p + 1)}
            disabled={
              currentPage * pageSize >=
              (activeSubTab === 'video'
                ? videoList.length
                : activeSubTab === 'traffic'
                  ? trafficList.length
                  : revenueList.length)
            }
            className="p-1.5 rounded-lg border border-slate-200 bg-white text-slate-600 hover:bg-slate-50 disabled:opacity-40 disabled:cursor-not-allowed cursor-pointer"
          >
            <ChevronRight className="w-4 h-4" />
          </button>
        </div>
      </div>
    </div>
  );
};
