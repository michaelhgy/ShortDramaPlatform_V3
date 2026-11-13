import React, { useState } from 'react';
import { 
  DramaAnalysisItem, 
  TimeSlotPerformance 
} from '../../data/shortDramaMockData';
import { VideoTrafficItem } from '../../types/shortDramaOps';
import { 
  Film, 
  Clock, 
  TrendingDown, 
  AlertTriangle, 
  Sparkles, 
  CheckCircle2, 
  Play, 
  Eye, 
  ChevronRight,
  SlidersHorizontal,
  Flame,
  Layers,
  ArrowRight
} from 'lucide-react';

interface DramaFunnelViewProps {
  dramaAnalysis: DramaAnalysisItem[];
  timeSlotPerformance: TimeSlotPerformance[];
  onSelectVideo: (video: VideoTrafficItem) => void;
  filteredVideos: VideoTrafficItem[];
}

export const DramaFunnelView: React.FC<DramaFunnelViewProps> = ({
  dramaAnalysis,
  timeSlotPerformance,
  onSelectVideo,
  filteredVideos
}) => {
  const [selectedDramaTitle, setSelectedDramaTitle] = useState<string>(
    dramaAnalysis.length > 0 ? dramaAnalysis[0].dramaTitle : ''
  );

  const currentDrama = dramaAnalysis.find(d => d.dramaTitle === selectedDramaTitle) || dramaAnalysis[0];

  // 找到当前选定剧目的视频切片列表
  const dramaVideos = filteredVideos.filter(v => v.dramaTitle === currentDrama?.dramaTitle);

  return (
    <div className="space-y-6">
      {/* 1. 顶部剧目选择器与宏观留存指标 */}
      <div className="bg-white rounded-2xl p-6 border border-slate-200/80 shadow-sm">
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 mb-6 pb-5 border-b border-slate-100">
          <div>
            <div className="flex items-center gap-2">
              <span className="p-2 bg-indigo-50 text-indigo-600 rounded-xl">
                <Film className="w-5 h-5" />
              </span>
              <div>
                <h3 className="text-lg font-bold text-slate-800">短剧剧目切片与集数留存漏斗</h3>
                <p className="text-xs text-slate-500 mt-0.5">
                  严密追踪「剧名-n」切片链路，从第01集冲突引流钩子到第05集卡点付费门槛的受众留存曲线
                </p>
              </div>
            </div>
          </div>

          {/* 剧目选择胶囊组 */}
          <div className="flex flex-wrap items-center gap-2">
            {dramaAnalysis.map(d => {
              const isActive = d.dramaTitle === currentDrama?.dramaTitle;
              return (
                <button
                  key={d.dramaTitle}
                  onClick={() => setSelectedDramaTitle(d.dramaTitle)}
                  className={`px-3.5 py-1.5 rounded-xl text-xs font-semibold transition-all flex items-center gap-2 cursor-pointer ${
                    isActive 
                      ? 'bg-indigo-600 text-white shadow-md shadow-indigo-100 ring-2 ring-indigo-600/20' 
                      : 'bg-slate-100 text-slate-600 hover:bg-slate-200/70'
                  }`}
                >
                  <span>《{d.dramaTitle}》</span>
                  <span className={`text-[10px] px-1.5 py-0.5 rounded-md ${
                    isActive ? 'bg-indigo-500 text-white' : 'bg-slate-200 text-slate-600'
                  }`}>
                    {(d.totalViews / 10000).toFixed(1)}w播
                  </span>
                </button>
              );
            })}
          </div>
        </div>

        {/* 选定剧目核心统计 */}
        {currentDrama && (
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
            <div className="p-4 bg-slate-50/80 rounded-xl border border-slate-100">
              <span className="text-xs text-slate-500 font-medium">切片累计总播放</span>
              <div className="text-2xl font-bold text-slate-900 mt-1">
                {(currentDrama.totalViews / 10000).toFixed(1)}
                <span className="text-xs font-normal text-slate-500 ml-1">万次</span>
              </div>
              <span className="text-[11px] text-slate-400 mt-0.5 block">
                归属剧场：{currentDrama.theater}
              </span>
            </div>

            <div className="p-4 bg-slate-50/80 rounded-xl border border-slate-100">
              <span className="text-xs text-slate-500 font-medium">全剧平均完播率</span>
              <div className="text-2xl font-bold text-emerald-600 mt-1">
                {currentDrama.avgCompletionRate}%
              </div>
              <span className="text-[11px] text-emerald-600 mt-0.5 block">
                高于大盘中位数 +3.8%
              </span>
            </div>

            <div className="p-4 bg-slate-50/80 rounded-xl border border-slate-100">
              <span className="text-xs text-slate-500 font-medium">在播切片视频数</span>
              <div className="text-2xl font-bold text-indigo-600 mt-1">
                {currentDrama.totalVideos}
                <span className="text-xs font-normal text-slate-500 ml-1">条</span>
              </div>
              <span className="text-[11px] text-slate-400 mt-0.5 block">
                覆盖01至08集切片
              </span>
            </div>

            <div className="p-4 bg-slate-50/80 rounded-xl border border-slate-100">
              <span className="text-xs text-slate-500 font-medium">算法优化预警数</span>
              <div className="text-2xl font-bold text-amber-600 mt-1">
                {currentDrama.optimizedCount}
                <span className="text-xs font-normal text-slate-500 ml-1">条</span>
              </div>
              <span className="text-[11px] text-amber-600 mt-0.5 block">
                优化率 {((currentDrama.optimizedCount / (currentDrama.totalVideos || 1)) * 100).toFixed(1)}%
              </span>
            </div>
          </div>
        )}

        {/* 2. 集数留存漏斗可视化阶梯 */}
        {currentDrama && (
          <div className="mt-4">
            <div className="flex items-center justify-between mb-3">
              <div className="flex items-center gap-2">
                <span className="text-xs font-bold text-slate-700 uppercase tracking-wider">
                  集数留存阶梯图 (01集 钩子 → 05集 充值点 → 08集 终章)
                </span>
                <span className="text-[11px] bg-slate-100 text-slate-500 px-2 py-0.5 rounded-full">
                  基准：以第01集播放量为100%参照
                </span>
              </div>
              <span className="text-xs text-slate-400">
                提示：短剧通常在第05集触发付费卡点，留存通常有自然收窄
              </span>
            </div>

            <div className="grid grid-cols-2 sm:grid-cols-4 md:grid-cols-8 gap-3">
              {currentDrama.episodes.map((ep) => {
                const isEp1 = ep.episodeNumber === 1;
                const isPaywall = ep.episodeNumber === 5;
                const viewsInW = (ep.views / 10000).toFixed(1);

                return (
                  <div 
                    key={ep.fileName}
                    className={`rounded-xl p-3 border transition-all ${
                      isEp1 
                        ? 'bg-gradient-to-b from-indigo-50/80 to-white border-indigo-200 ring-2 ring-indigo-500/20' 
                        : isPaywall 
                          ? 'bg-gradient-to-b from-amber-50/80 to-white border-amber-200' 
                          : 'bg-slate-50/60 border-slate-200/80 hover:bg-slate-100/60'
                    }`}
                  >
                    <div className="flex items-center justify-between mb-1.5">
                      <span className={`text-xs font-bold px-1.5 py-0.5 rounded ${
                        isEp1 
                          ? 'bg-indigo-600 text-white' 
                          : isPaywall 
                            ? 'bg-amber-600 text-white' 
                            : 'bg-slate-200 text-slate-700'
                      }`}>
                        第{ep.episodeNumber}集
                      </span>
                      {ep.optimizationCount > 0 && (
                        <span className="flex items-center gap-0.5 text-[10px] text-rose-600 bg-rose-50 px-1 py-0.5 rounded" title="存在算法优化">
                          <AlertTriangle className="w-3 h-3" />
                          {ep.optimizationCount}
                        </span>
                      )}
                    </div>

                    <div className="text-[11px] font-semibold text-slate-800 truncate mb-1">
                      {ep.fileName}
                    </div>

                    <div className="text-sm font-extrabold text-slate-900">
                      {viewsInW}
                      <span className="text-[10px] font-normal text-slate-500 ml-0.5">万播</span>
                    </div>

                    <div className="mt-2 pt-2 border-t border-slate-100 flex items-center justify-between text-[11px]">
                      <span className="text-slate-400">完播率</span>
                      <span className={`font-semibold ${
                        ep.completionRate >= 24 ? 'text-emerald-600' : ep.completionRate >= 18 ? 'text-indigo-600' : 'text-slate-600'
                      }`}>
                        {ep.completionRate}%
                      </span>
                    </div>

                    {!isEp1 && (
                      <div className="mt-1 flex items-center justify-between text-[10px]">
                        <span className="text-slate-400">较首集</span>
                        <span className="text-rose-500 font-medium">
                          -{ep.dropOffRate}%
                        </span>
                      </div>
                    )}

                    {isPaywall && (
                      <div className="mt-1 text-center bg-amber-100/80 text-amber-800 text-[9px] font-bold py-0.5 rounded">
                        💰 付费卡点
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          </div>
        )}
      </div>

      {/* 3. 下半部分：发布时段效能分析 + 该剧目热门切片列表 */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* 左侧 1/3：黄金发布时段效能分析 */}
        <div className="bg-white rounded-2xl p-6 border border-slate-200/80 shadow-sm flex flex-col justify-between">
          <div>
            <div className="flex items-center justify-between mb-4 pb-3 border-b border-slate-100">
              <div className="flex items-center gap-2">
                <span className="p-2 bg-amber-50 text-amber-600 rounded-xl">
                  <Clock className="w-5 h-5" />
                </span>
                <div>
                  <h4 className="text-sm font-bold text-slate-800">黄金发布时段效能</h4>
                  <p className="text-[11px] text-slate-500">时段流量集中度与完播产出</p>
                </div>
              </div>
            </div>

            <div className="space-y-3.5">
              {timeSlotPerformance.map(slot => {
                const isPeak = slot.slot === '18:30' || slot.slot === '21:15';
                return (
                  <div 
                    key={slot.slot}
                    className={`p-3.5 rounded-xl border transition-all ${
                      isPeak 
                        ? 'bg-amber-50/40 border-amber-200/80' 
                        : 'bg-slate-50/70 border-slate-200/70'
                    }`}
                  >
                    <div className="flex items-center justify-between mb-1.5">
                      <div className="flex items-center gap-2">
                        <span className="font-mono text-xs font-bold text-slate-800 bg-white px-2 py-0.5 rounded border border-slate-200">
                          {slot.slot}
                        </span>
                        <span className="text-xs font-semibold text-slate-700">
                          {slot.name}
                        </span>
                        {isPeak && (
                          <span className="text-[10px] bg-amber-500 text-white font-bold px-1.5 py-0.2 rounded-full">
                            高峰档
                          </span>
                        )}
                      </div>
                      <span className="text-xs font-bold text-slate-800">
                        {(slot.avgViews / 10000).toFixed(1)}w 均播
                      </span>
                    </div>

                    <div className="flex items-center justify-between text-[11px] text-slate-500 mt-2">
                      <span>已发视频: <strong className="text-slate-700">{slot.videoCount}条</strong></span>
                      <span>均完播率: <strong className="text-emerald-600">{slot.avgCompletionRate}%</strong></span>
                      <span>高爆款: <strong className="text-indigo-600">{slot.viralCount}条</strong></span>
                    </div>

                    {/* 完播进度条 */}
                    <div className="w-full bg-slate-200/80 h-1.5 rounded-full mt-2 overflow-hidden">
                      <div 
                        className={`h-full rounded-full ${
                          slot.avgCompletionRate >= 22 ? 'bg-emerald-500' : 'bg-indigo-500'
                        }`}
                        style={{ width: `${Math.min(100, (slot.avgCompletionRate / 35) * 100)}%` }}
                      />
                    </div>
                  </div>
                );
              })}
            </div>
          </div>

          <div className="mt-4 p-3 bg-blue-50/70 rounded-xl border border-blue-100 text-[11px] text-blue-700 leading-relaxed">
            💡 <strong>运营建议</strong>：晚间 <strong>18:30</strong> 与 <strong>21:15</strong> 档期完播率与转化率最高，建议将各剧目的重点第01集钩子切片与第05集卡点切片优先排在上述两个高峰档。
          </div>
        </div>

        {/* 右侧 2/3：当前剧目切片视频全量列表 */}
        <div className="lg:col-span-2 bg-white rounded-2xl p-6 border border-slate-200/80 shadow-sm flex flex-col justify-between">
          <div>
            <div className="flex items-center justify-between mb-4 pb-3 border-b border-slate-100">
              <div className="flex items-center gap-2">
                <span className="p-2 bg-emerald-50 text-emerald-600 rounded-xl">
                  <Play className="w-5 h-5" />
                </span>
                <div>
                  <h4 className="text-sm font-bold text-slate-800">
                    《{currentDrama?.dramaTitle}》切片矩阵视频明细 ({dramaVideos.length}条)
                  </h4>
                  <p className="text-[11px] text-slate-500">点击任意视频行可展开深入诊断抽屉</p>
                </div>
              </div>
              <span className="text-xs text-slate-400">
                按发布时间顺序排列
              </span>
            </div>

            <div className="space-y-2.5 max-h-[460px] overflow-y-auto pr-1">
              {dramaVideos.slice(0, 15).map(vid => {
                const isViral = vid.completionRate >= 25.0;
                return (
                  <div
                    key={vid.id}
                    onClick={() => onSelectVideo(vid)}
                    className="p-3 rounded-xl border border-slate-200/70 hover:border-indigo-400 hover:shadow-sm bg-slate-50/40 hover:bg-white transition-all cursor-pointer flex flex-col sm:flex-row sm:items-center justify-between gap-3"
                  >
                    <div className="flex items-center gap-3">
                      <div className="w-10 h-10 rounded-lg bg-indigo-50 border border-indigo-100 flex flex-col items-center justify-center flex-shrink-0">
                        <span className="text-[10px] text-indigo-500 font-bold">EP</span>
                        <span className="text-xs font-black text-indigo-700 leading-none">
                          {vid.episodeNumber.toString().padStart(2, '0')}
                        </span>
                      </div>

                      <div>
                        <div className="flex items-center gap-2">
                          <span className="font-bold text-sm text-slate-900">
                            {vid.fileName}
                          </span>
                          {isViral && (
                            <span className="flex items-center gap-0.5 text-[10px] font-bold px-1.5 py-0.2 rounded-full bg-gradient-to-r from-amber-500 to-orange-500 text-white">
                              <Flame className="w-2.5 h-2.5" /> 爆款
                            </span>
                          )}
                          {vid.hasOptimization && (
                            <span className="text-[10px] font-semibold px-1.5 py-0.2 rounded-full bg-rose-100 text-rose-700 border border-rose-200">
                              优化预警
                            </span>
                          )}
                        </div>
                        <div className="flex items-center gap-2 text-xs text-slate-500 mt-1">
                          <span>{vid.accountName}</span>
                          <span>•</span>
                          <span className="font-mono">{vid.publishTime}</span>
                        </div>
                      </div>
                    </div>

                    <div className="flex items-center gap-5 sm:justify-end">
                      <div className="text-right">
                        <div className="text-xs font-bold text-slate-800">
                          {(vid.views / 10000).toFixed(1)}万
                        </div>
                        <div className="text-[10px] text-slate-400">播放量</div>
                      </div>

                      <div className="text-right">
                        <div className={`text-xs font-bold ${
                          vid.completionRate >= 22 ? 'text-emerald-600' : 'text-slate-700'
                        }`}>
                          {vid.completionRate}%
                        </div>
                        <div className="text-[10px] text-slate-400">完播率</div>
                      </div>

                      <div className="text-right">
                        <div className="text-xs font-semibold text-slate-700">
                          {vid.hearts.toLocaleString()}
                        </div>
                        <div className="text-[10px] text-slate-400">爱心</div>
                      </div>

                      <ChevronRight className="w-4 h-4 text-slate-400" />
                    </div>
                  </div>
                );
              })}

              {dramaVideos.length === 0 && (
                <div className="py-12 text-center text-slate-400 text-sm">
                  当前筛选条件下暂无该剧目的视频记录
                </div>
              )}
            </div>
          </div>
          
          <div className="mt-3 text-right">
            <span className="text-xs text-slate-400">
              共加载 {dramaVideos.length} 条剧目切片记录，已严格遵守「一个发布时间一个账号只有一条视频」
            </span>
          </div>
        </div>
      </div>
    </div>
  );
};
