import { CockpitModal } from './CockpitModal';
import React from 'react';
import { PostItem, COCKPIT_DATA } from '../../data/cockpitData';
import { X, Play, Heart, MessageCircle, Share2, Bookmark, Clock, Eye, AlertTriangle, ShieldCheck } from 'lucide-react';
import { AreaTrendChart } from './InteractiveCharts';

interface PostDetailDrawerProps {
  post: PostItem | null;
  onClose: () => void;
  onBackToAccount?: (accountId: string) => void;
}

export const PostDetailDrawer: React.FC<PostDetailDrawerProps> = ({
  post,
  onClose,
  onBackToAccount,
}) => {
  if (!post) return null;

  // 获取该作品的每日数据 (post_daily)
  const dailyRecords = COCKPIT_DATA.post_daily.filter(d => d.post_id === post.post_id);
  dailyRecords.sort((a, b) => a.stat_date.localeCompare(b.stat_date));

  // 获取是否有处罚记录
  const punishment = COCKPIT_DATA.punishments.find(p => p.post_id_or_export_id === post.post_id);

  // 趋势点
  const trendData = dailyRecords.map(d => ({
    date: d.stat_date,
    label: d.stat_date.slice(5),
    value: d.view,
    subLabel: '点赞',
    subValue: d.like_count,
  }));

  const totalInteraction = (post.like_count || 0) + (post.comment_count || 0) + (post.forward_count || 0) + (post.love_count || 0);

  return (
    <CockpitModal label="作品数据详情" onClose={onClose} width="max-w-4xl">
        {/* Header */}
        <div className="px-6 py-5 border-b border-slate-100 flex items-center justify-between bg-slate-50/70">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-violet-500 to-indigo-600 text-white font-extrabold flex items-center justify-center text-sm shadow-sm">
              <Play className="w-5 h-5 fill-current" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                {/* 需求约束：只显示 title，不要从标题猜剧名 */}
                <h3 className="text-base font-extrabold text-[#1E1644] max-w-[340px] truncate">
                  {post.title}
                </h3>
                {punishment ? (
                  <span className="text-[11px] font-semibold px-2 py-0.5 rounded bg-rose-50 text-rose-700 border border-rose-200 flex items-center gap-1">
                    <AlertTriangle className="w-3 h-3 text-rose-600" />
                    {punishment.punish_state}
                  </span>
                ) : (
                  <span className="text-[11px] font-semibold px-2 py-0.5 rounded bg-emerald-50 text-emerald-700 border border-emerald-200 flex items-center gap-1">
                    <ShieldCheck className="w-3 h-3 text-emerald-600" />
                    健康正常
                  </span>
                )}
              </div>
              <div className="text-xs text-slate-400 mt-0.5 flex items-center gap-2">
                <button
                  onClick={() => onBackToAccount && onBackToAccount(post.account_id)}
                  className="text-indigo-600 font-semibold hover:underline"
                >
                  {post.account_name}
                </button>
                <span>·</span>
                <span>发布: {post.post_time}</span>
                <span>·</span>
                <span>快照: {post.snapshot_date}</span>
              </div>
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
        <div className="min-h-0 flex-1 overflow-y-auto p-6 space-y-6">
          {/* Key Metrics Grid */}
          <div className="grid grid-cols-4 gap-3">
            <div className="p-3.5 rounded-xl bg-[#F8F9FD] border border-slate-100">
              <span className="text-[11px] text-slate-400 font-medium flex items-center gap-1">
                <Eye className="w-3 h-3 text-indigo-500" /> 累计总播放
              </span>
              <p className="text-lg font-extrabold text-[#1E1644] font-mono tabular-nums mt-1">
                {post.view.toLocaleString()}
              </p>
              <span className="text-[10px] text-slate-400">视频号快照</span>
            </div>

            <div className="p-3.5 rounded-xl bg-[#F8F9FD] border border-slate-100">
              <span className="text-[11px] text-slate-400 font-medium flex items-center gap-1">
                <Clock className="w-3 h-3 text-cyan-500" /> 完播率
              </span>
              <p className={`text-lg font-extrabold font-mono tabular-nums mt-1 ${post.full_view <= 0.25 ? 'text-amber-600' : 'text-emerald-600'}`}>
                {(post.full_view * 100).toFixed(1)}%
              </p>
              <span className="text-[10px] text-slate-400">时长: {post.view_time}秒</span>
            </div>

            <div className="p-3.5 rounded-xl bg-[#F8F9FD] border border-slate-100">
              <span className="text-[11px] text-slate-400 font-medium flex items-center gap-1">
                <Heart className="w-3 h-3 text-rose-500" /> 互动总量
              </span>
              <p className="text-lg font-extrabold text-[#1E1644] font-mono tabular-nums mt-1">
                {totalInteraction.toLocaleString()}
              </p>
              <span className="text-[10px] text-slate-400">互动率: {((totalInteraction / post.view) * 100).toFixed(2)}%</span>
            </div>

            <div className="p-3.5 rounded-xl bg-[#F8F9FD] border border-slate-100">
              <span className="text-[11px] text-slate-400 font-medium flex items-center gap-1">
                <Play className="w-3 h-3 text-violet-500" /> 带来涨粉
              </span>
              <p className="text-lg font-extrabold text-[#1E1644] font-mono tabular-nums mt-1">
                +{post.fans_add || 0}
              </p>
              <span className="text-[10px] text-slate-400">单片转化</span>
            </div>
          </div>

          {/* Interaction Breakdown 4-card strip */}
          <div className="p-4 rounded-xl bg-slate-50 border border-slate-200/70">
            <h4 className="text-xs font-bold text-slate-700 mb-2">互动指标四维拆解</h4>
            <div className="grid grid-cols-4 gap-2 text-center">
              <div className="p-2 bg-white rounded-lg border border-slate-200/50">
                <span className="text-[10px] text-slate-400 flex items-center justify-center gap-1">
                  <Heart className="w-3 h-3 text-rose-500" /> 点赞
                </span>
                <span className="text-sm font-bold text-slate-800 font-mono tabular-nums mt-0.5 block">
                  {post.like_count.toLocaleString()}
                </span>
              </div>
              <div className="p-2 bg-white rounded-lg border border-slate-200/50">
                <span className="text-[10px] text-slate-400 flex items-center justify-center gap-1">
                  <Bookmark className="w-3 h-3 text-amber-500" /> 收藏
                </span>
                <span className="text-sm font-bold text-slate-800 font-mono tabular-nums mt-0.5 block">
                  {(post.love_count || 0).toLocaleString()}
                </span>
              </div>
              <div className="p-2 bg-white rounded-lg border border-slate-200/50">
                <span className="text-[10px] text-slate-400 flex items-center justify-center gap-1">
                  <MessageCircle className="w-3 h-3 text-blue-500" /> 评论
                </span>
                <span className="text-sm font-bold text-slate-800 font-mono tabular-nums mt-0.5 block">
                  {post.comment_count.toLocaleString()}
                </span>
              </div>
              <div className="p-2 bg-white rounded-lg border border-slate-200/50">
                <span className="text-[10px] text-slate-400 flex items-center justify-center gap-1">
                  <Share2 className="w-3 h-3 text-emerald-500" /> 转发
                </span>
                <span className="text-sm font-bold text-slate-800 font-mono tabular-nums mt-0.5 block">
                  {post.forward_count.toLocaleString()}
                </span>
              </div>
            </div>
          </div>

          {/* Daily Trend Chart (from post_daily) */}
          <div className="p-4 rounded-2xl bg-white border border-slate-200">
            <div className="flex items-center justify-between mb-3">
              <h4 className="text-xs font-bold text-slate-800">近 7 日每日播放趋势 (post_daily)</h4>
              <span className="text-[10px] text-slate-400 font-mono">数据粒度: 按日 (daily)</span>
            </div>
            <AreaTrendChart
              data={trendData}
              metricName="当日播放"
              color="#8B5CF6"
              height={180}
            />
          </div>

          {/* Daily Detail Table */}
          <div>
            <h4 className="text-xs font-bold text-slate-800 mb-2">每日明细数据表</h4>
            <div className="border border-slate-200 rounded-xl overflow-hidden">
              <table className="w-full text-left text-xs">
                <thead className="bg-slate-50 text-slate-500 font-semibold border-b border-slate-200">
                  <tr>
                    <th className="py-2.5 px-3">日期</th>
                    <th className="py-2.5 px-3 text-right">单日播放</th>
                    <th className="py-2.5 px-3 text-right">点赞</th>
                    <th className="py-2.5 px-3 text-right">收藏</th>
                    <th className="py-2.5 px-3 text-right">评论</th>
                    <th className="py-2.5 px-3 text-right">转发</th>
                    <th className="py-2.5 px-3 text-right">涨粉</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {dailyRecords.map(record => (
                    <tr key={record.stat_date} className="hover:bg-slate-50/70 font-mono">
                      <td className="py-2 px-3 text-slate-700 font-medium">{record.stat_date}</td>
                      <td className="py-2 px-3 text-right font-bold text-[#1E1644] tabular-nums">
                        {record.view.toLocaleString()}
                      </td>
                      <td className="py-2 px-3 text-right text-slate-600 tabular-nums">{record.like_count}</td>
                      <td className="py-2 px-3 text-right text-slate-600 tabular-nums">{record.favorite_count}</td>
                      <td className="py-2 px-3 text-right text-slate-600 tabular-nums">{record.comment_count}</td>
                      <td className="py-2 px-3 text-right text-slate-600 tabular-nums">{record.forward_count}</td>
                      <td className="py-2 px-3 text-right text-emerald-600 font-semibold tabular-nums">+{record.fans_add}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </div>
    </CockpitModal>
  );
};
