import React from 'react';
import type { DramaDownloadReadTaskState } from '../../../api/v2Catalog';
import {
  CheckCircle2,
  ChevronDown,
  ClipboardList,
  Download,
  FolderOpen,
  Link2,
  Loader2,
  Play,
  RefreshCw,
  Square,
  X,
} from 'lucide-react';

interface DramaDownloadModalProps {
  isOpen: boolean;
  downloadRoot: string;
  readTaskState: DramaDownloadReadTaskState;
  onClose: () => void;
  onOpenFolder: (path: string) => void;
  onStartPipeline: () => void;
  onStopPipeline: () => void;
}

const stages = [
  { phase: 'read-task', label: '读取置顶任务', description: '识别主微信第一条置顶聊天中的任务', icon: ClipboardList },
  { phase: 'collect-links', label: '采集分享链接', description: '按剧集逐集采集分享短链', icon: Link2 },
  { phase: 'parse-download', label: '后台解析下载', description: '解析短链并保存视频文件', icon: RefreshCw },
  { phase: 'verify-download', label: '校验下载视频', description: '逐集对账，检查视频轨道和时长', icon: Download },
] as const;

const phaseOrder = new Map<string, number>(stages.map((stage, index) => [stage.phase, index]));

function stageState(state: DramaDownloadReadTaskState, index: number): 'pending' | 'running' | 'done' | 'failed' {
  if ((state.cleanup_pending && state.complete) || state.phase === 'cleanup-task') return 'done';
  const saved = state.stage_states?.[stages[index].phase];
  if (saved === 'running') {
    const active = state.status === 'queued' || state.status === 'running';
    if (active && state.phase === stages[index].phase) return 'running';
    if (index < (phaseOrder.get(state.phase) ?? -1)) return 'done';
    return state.status === 'failed' && state.phase === stages[index].phase ? 'failed' : 'pending';
  }
  if (saved) return saved;
  if (state.status === 'failed' && index === (phaseOrder.get(state.phase) ?? 0)) return 'failed';
  if (state.phase === 'completed' || index < (phaseOrder.get(state.phase) ?? -1)) return 'done';
  if (state.status === 'succeeded' && index === (phaseOrder.get(state.phase) ?? -1)) return 'done';
  if ((state.status === 'queued' || state.status === 'running') && index === (phaseOrder.get(state.phase) ?? 0)) return 'running';
  return 'pending';
}

export const DramaDownloadModal: React.FC<DramaDownloadModalProps> = ({
  isOpen,
  downloadRoot,
  readTaskState,
  onClose,
  onOpenFolder,
  onStartPipeline,
  onStopPipeline,
}) => {
  const [expandedStages, setExpandedStages] = React.useState<Record<string, boolean>>({});
  React.useEffect(() => {
    setExpandedStages({});
  }, [readTaskState.created_at, readTaskState.phase, readTaskState.status]);
  if (!isOpen) return null;
  const busy = readTaskState.status === 'queued' || readTaskState.status === 'running';
  const currentIndex = phaseOrder.get(readTaskState.phase) ?? -1;
  const hasResult = readTaskState.phase === 'completed' && readTaskState.status === 'succeeded' && readTaskState.complete;
  const linkCount = readTaskState.collected_count ?? readTaskState.link_episode_map?.length ?? 0;
  const parsedCount = readTaskState.parsed_episodes?.length ?? 0;
  const cleanupVisible = Boolean((readTaskState.cleanup_state && readTaskState.cleanup_state !== 'pending') || readTaskState.cleanup_pending || readTaskState.phase === 'cleanup-task');
  const cleanupState = readTaskState.cleanup_state ?? (busy ? 'running' : 'failed');
  const cleanupFailed = cleanupVisible && cleanupState === 'failed';
  const chatName = readTaskState.task?.chat_name;
  const chatConfirmed = Boolean(chatName && !/^(昨天|今天|前天|当前聊天|\d{1,2}[:：]\d{2}|(?:星期|周)[一二三四五六日天])$/.test(chatName));

  return (
    <div className="fixed inset-0 z-[70] flex items-center justify-center bg-[#0B1020]/50 p-4 backdrop-blur-[2px]" role="dialog" aria-modal="true" aria-label="短剧原片下载">
      <div className="w-full max-w-4xl max-h-[92vh] overflow-y-auto rounded-3xl bg-[#F8F9FA] shadow-2xl border border-white/30">
        <div className="sticky top-0 z-10 flex items-start justify-between gap-4 border-b border-black/[0.06] bg-white px-6 py-5">
          <div className="flex items-center gap-3">
            <div className="flex h-11 w-11 items-center justify-center rounded-2xl bg-[#1A1D2E] text-[#DDFD00] shadow-xs">
              <Download className="h-5 w-5" />
            </div>
            <div>
              <h2 className="text-lg font-black text-[#1A1D2E]">短剧原片下载</h2>
              <p className="mt-1 text-xs text-[#64748B]">自动处理置顶聊天最后一组任务，完成后继续下一部</p>
            </div>
          </div>
          <button type="button" onClick={onClose} className="rounded-xl p-2 text-slate-400 hover:bg-slate-100 hover:text-slate-700" aria-label="关闭短剧原片下载">
            <X className="h-5 w-5" />
          </button>
        </div>

        <div className="space-y-4 p-6">
          <section className="rounded-2xl border border-black/[0.06] bg-white p-4">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div className="min-w-0">
                <p className="text-xs font-extrabold text-[#1A1D2E]">下载目录</p>
                <p className="mt-1 break-all font-mono text-xs text-[#64748B]">{downloadRoot || '尚未设置'}</p>
                <p className="mt-2 text-[11px] text-slate-400">保存结构为 下载目录 / 剧场 / 剧名 / 分集原片</p>
                {readTaskState.link_manifest_path && (
                  <p className="mt-1 break-all text-[11px] text-slate-400">
                    全部剧目链接清单 <span className="font-mono">{readTaskState.link_manifest_path}</span>
                    {typeof readTaskState.link_record_count === 'number' ? ' · 累计 ' + readTaskState.link_record_count + ' 条' : ''}
                  </p>
                )}
              </div>
              <button type="button" onClick={() => onOpenFolder(downloadRoot)} disabled={!downloadRoot} className="inline-flex items-center gap-1.5 rounded-xl bg-[#1A1D2E] px-3 py-2 text-xs font-bold text-[#DDFD00] hover:bg-black disabled:cursor-not-allowed disabled:opacity-40">
                <FolderOpen className="h-3.5 w-3.5" />
                打开下载目录
              </button>
            </div>
          </section>

          <section className="rounded-2xl border border-black/[0.06] bg-white p-5">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div className="min-w-0">
                <p className="text-xs font-extrabold text-[#1A1D2E]">当前任务</p>
                <p className="mt-1 truncate text-sm font-bold text-[#1A1D2E]">{readTaskState.task?.task_label || '尚未读取微信任务'}</p>
                <p className="mt-1 text-[11px] text-[#64748B]">{readTaskState.task ? '聊天 ' + (chatConfirmed ? chatName : '待重新核对') + (readTaskState.task_count ? ' · 当前可见 ' + readTaskState.task_count + ' 个任务' : '') : '点击开始后读取主微信第一条置顶聊天'}</p>
                {Boolean(readTaskState.task_count) && readTaskState.current_task_index !== undefined && busy && <p className="mt-1 text-[11px] font-semibold text-blue-600">正在处理第 {readTaskState.current_task_index + 1} 个任务</p>}
                {readTaskState.current_step && <p className="mt-2 text-[11px] font-semibold text-slate-500">{readTaskState.current_step}</p>}
                {readTaskState.error && <p className="mt-2 text-[11px] font-bold text-rose-600">{readTaskState.error}</p>}
                {readTaskState.manual_cleanup_required && (
                  <div className="mt-3 rounded-xl border border-amber-200 bg-amber-50 px-3 py-2 text-[11px] leading-5 text-amber-800">
                    <p className="font-extrabold">下载已完成</p>
                    <p>{readTaskState.manual_cleanup_message || '请手动删除微信中的剧名消息和视频卡片。'}</p>
                  </div>
                )}
                {(linkCount > 0 || parsedCount > 0 || readTaskState.expected_count) && (
                  <div className="mt-3 flex flex-wrap gap-2 text-[10px] font-semibold text-slate-500">
                    {linkCount > 0 && <span className="rounded-full bg-slate-100 px-2 py-1">链接对应 {linkCount} 集</span>}
                    <span className="rounded-full bg-slate-100 px-2 py-1">已下载 {readTaskState.downloaded_episodes?.length ?? 0} 集</span>
                    <span className="rounded-full bg-emerald-50 px-2 py-1 text-emerald-700">已校验 {readTaskState.verified_count ?? 0} 集</span>
                    {readTaskState.total_conflict && <span className="rounded-full bg-rose-50 px-2 py-1 text-rose-700">总集数待核对</span>}
                    {readTaskState.missing_video_episodes?.length ? <span className="rounded-full bg-amber-50 px-2 py-1 text-amber-700">待完成 {readTaskState.missing_video_episodes.join('、')}</span> : null}
                    {parsedCount > 0 && <span className="rounded-full bg-blue-50 px-2 py-1 text-blue-700">解析返回 {parsedCount} 集</span>}
                    {readTaskState.expected_count ? <span className="rounded-full bg-emerald-50 px-2 py-1 text-emerald-700">应有 {readTaskState.expected_count} 集</span> : null}
                    {readTaskState.missing_link_episodes?.length ? <span className="rounded-full bg-amber-50 px-2 py-1 text-amber-700">缺链 {readTaskState.missing_link_episodes.join('、')}</span> : null}
                    {readTaskState.parse_failed_episodes?.length ? <span className="rounded-full bg-rose-50 px-2 py-1 text-rose-700">待补采 {readTaskState.parse_failed_episodes.join('、')}</span> : null}
                  </div>
                )}
                {readTaskState.tasks?.length ? (
                  <div className="mt-3 max-h-24 space-y-1 overflow-y-auto rounded-xl bg-slate-50 p-2">
                    {readTaskState.tasks.map((task, index) => (
                      <div key={task.task_label + '-' + index} className={'flex items-center gap-2 rounded-lg px-2 py-1 text-[11px] ' + (index === readTaskState.current_task_index ? 'bg-white font-bold text-[#1A1D2E]' : 'text-slate-500')}>
                        <span className="w-4 text-right text-slate-400">{index + 1}</span>
                        <span className="truncate">{task.task_label}</span>
                        {readTaskState.completed_tasks?.some((done) => done.task_label === task.task_label && done.chat_name === task.chat_name) && <CheckCircle2 aria-label="任务已完成" className="ml-auto h-3.5 w-3.5 shrink-0 text-emerald-500" />}
                      </div>
                    ))}
                  </div>
                ) : null}
              </div>
              <div className="flex items-center gap-2">
                {busy && (
                  <button type="button" onClick={onStopPipeline} disabled={readTaskState.stop_requested} className="inline-flex items-center gap-1.5 rounded-xl border border-rose-200 bg-rose-50 px-3 py-2.5 text-xs font-bold text-rose-700 hover:bg-rose-100 disabled:cursor-not-allowed disabled:opacity-50">
                    <Square className="h-3.5 w-3.5 fill-current" />
                    {readTaskState.stop_requested ? '正在停止' : '停止脚本'}
                  </button>
                )}
                <button type="button" onClick={onStartPipeline} disabled={busy} className="inline-flex items-center gap-1.5 rounded-xl bg-[#1A1D2E] px-4 py-2.5 text-xs font-bold text-[#DDFD00] hover:bg-black disabled:cursor-not-allowed disabled:opacity-40">
                  {busy ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Play className="h-3.5 w-3.5" />}
                  {busy ? '正在处理' : readTaskState.cleanup_pending ? '重试微信清理' : readTaskState.resume_phase === 'parse-download' ? '继续解析下载' : readTaskState.resume_phase === 'verify-download' ? '继续校验视频' : hasResult ? '再次处理置顶任务' : '开始处理置顶任务'}
                </button>
              </div>
            </div>
          </section>

          <section className="rounded-2xl border border-black/[0.06] bg-white p-5">
            <div className="mb-4 flex items-center justify-between">
              <div>
                <p className="text-sm font-black text-[#1A1D2E]">任务进度</p>
                <p className="mt-1 text-[11px] text-slate-400">{hasResult ? '任务已完成，文件已经写入下载目录' : cleanupFailed ? '视频校验已通过，微信任务清理未完成' : readTaskState.phase === 'cleanup-task' && busy ? '视频校验已通过，正在清理微信任务' : busy && currentIndex >= 0 ? '正在执行阶段 ' + (currentIndex + 1) + ' / ' + stages.length : readTaskState.status === 'failed' ? '任务已中断，可展开对应阶段查看记录' : readTaskState.status === 'stopped' ? '任务已停止' : '等待开始'}</p>
                {busy && readTaskState.current_step && <p className="mt-2 rounded-lg bg-blue-50 px-2.5 py-1.5 text-[11px] font-bold text-blue-700">当前动作：{readTaskState.current_step}</p>}
                {readTaskState.status === 'stopped' && <p className="mt-2 rounded-lg bg-amber-50 px-2.5 py-1.5 text-[11px] font-bold text-amber-700">脚本已停止，已保留已经采集和下载的文件</p>}
              </div>
              {hasResult && <CheckCircle2 className="h-6 w-6 text-emerald-500" />}
            </div>
            <div className="space-y-2">
              {stages.map((stage, index) => {
                const state = stageState(readTaskState, index);
                const Icon = stage.icon;
                const expanded = expandedStages[stage.phase] ?? (state === 'running');
                const messages = readTaskState.stage_logs?.[stage.phase] ?? [];
                const showCurrentAction = state === 'running' && readTaskState.phase === stage.phase && Boolean(readTaskState.current_step);
                return (
                  <div key={stage.phase} className={'rounded-2xl border px-4 py-3 ' + (state === 'running' ? 'border-blue-200 bg-blue-50/60' : state === 'failed' ? 'border-rose-200 bg-rose-50/60' : state === 'done' ? 'border-emerald-100 bg-emerald-50/40' : 'border-slate-100 bg-slate-50/50')}>
                    <div
                      className="flex cursor-pointer items-center gap-3"
                      role="button"
                      tabIndex={0}
                      aria-expanded={expanded}
                      aria-label={stage.label + (expanded ? '，收起进展' : '，展开进展')}
                      onClick={() => setExpandedStages((current) => ({ ...current, [stage.phase]: !expanded }))}
                      onKeyDown={(event) => {
                        if (event.key === 'Enter' || event.key === ' ') {
                          event.preventDefault();
                          setExpandedStages((current) => ({ ...current, [stage.phase]: !expanded }));
                        }
                      }}
                    >
                      <div className={'flex h-8 w-8 shrink-0 items-center justify-center rounded-xl ' + (state === 'running' ? 'bg-blue-500 text-white' : state === 'failed' ? 'bg-rose-500 text-white' : state === 'done' ? 'bg-emerald-500 text-white' : 'bg-white text-slate-400')}>
                        {state === 'running' ? <Loader2 className="h-4 w-4 animate-spin" /> : state === 'done' ? <CheckCircle2 className="h-4 w-4" /> : <Icon className="h-4 w-4" />}
                      </div>
                      <div className="min-w-0 flex-1">
                        <div className="flex items-center justify-between gap-3">
                          <p className="text-xs font-extrabold text-[#1A1D2E]">阶段 {index + 1} · {stage.label}</p>
                          <span className={'text-[10px] font-bold ' + (state === 'running' ? 'text-blue-600' : state === 'failed' ? 'text-rose-600' : state === 'done' ? 'text-emerald-600' : 'text-slate-400')}>{state === 'running' ? '进行中' : state === 'failed' ? '失败' : state === 'done' ? '已完成' : '待开始'}</span>
                        </div>
                        <p className="mt-1 text-[11px] text-slate-500">{stage.description}</p>
                      </div>
                      <ChevronDown className={'h-4 w-4 shrink-0 text-slate-400 transition-transform ' + (expanded ? 'rotate-180' : '')} />
                    </div>
                    {expanded ? (
                      <div className="mt-3 ml-11 max-h-64 overflow-y-auto space-y-1.5 border-l border-current/10 pl-3 text-[11px] leading-5 text-slate-600">
                        {showCurrentAction && <p className="font-bold text-blue-700">当前动作：{readTaskState.current_step}</p>}
                        {[...messages].reverse().map((message, logIndex) => <p key={message + '-' + logIndex}>{message}</p>)}
                        {!showCurrentAction && messages.length === 0 && <p className="text-slate-400">该阶段暂无进展记录</p>}
                      </div>
                    ) : null}
                  </div>
                );
              })}
            </div>
          </section>

          {cleanupVisible && (
            <section className={'rounded-2xl border p-4 ' + (cleanupFailed ? 'border-amber-200 bg-amber-50/70' : 'border-slate-200 bg-white')} aria-label="微信任务清理">
              <div className="flex items-center justify-between gap-3">
                <p className="text-xs font-extrabold text-[#1A1D2E]">微信任务清理</p>
                <span className="text-[11px] font-semibold text-amber-700">{cleanupState === 'done' ? '已完成' : cleanupFailed ? '待重试' : readTaskState.status === 'stopped' ? '已停止' : '进行中'}</span>
              </div>
              <p className="mt-2 text-[11px] text-slate-600">{cleanupState === 'done' ? '本次卡片和剧名均已确认清理。' : '视频成果已保留。重试会先核对聊天和本次剧名，再继续清理，不重新采集下载。'}</p>
              {readTaskState.cleanup_error && <p className="mt-2 text-[11px] text-amber-800">{readTaskState.cleanup_error}</p>}
              <details className="mt-2 text-[11px] text-slate-600" open={busy && readTaskState.phase === 'cleanup-task'}>
                <summary className="cursor-pointer font-semibold">查看清理记录</summary>
                <div className="mt-2 max-h-40 space-y-1 overflow-y-auto">{[...(readTaskState.stage_logs?.['cleanup-task'] ?? [])].reverse().map((message,index) => <p key={index}>{message}</p>)}</div>
              </details>
            </section>
          )}

          <div className="flex items-center justify-between border-t border-black/[0.06] pt-4">
            <span className="text-[11px] text-slate-400">本剧全部校验通过后清理对应剧名和卡片；异常时保留任务</span>
            <button type="button" onClick={onClose} className="rounded-xl bg-[#1A1D2E] px-4 py-2 text-xs font-bold text-white hover:bg-black">关闭</button>
          </div>
        </div>
      </div>
    </div>
  );
};
