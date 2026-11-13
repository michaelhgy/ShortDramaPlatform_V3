import { VIDEO_TRAFFIC_RULES, type VideoTrafficStatus } from '../../services/videoTrafficRating';
import { VideoTrafficStatusMark } from './VideoTrafficTags';

export function VideoTrafficFilter({ value, onChange, counts, total }: {
  value: VideoTrafficStatus | 'ALL';
  onChange: (value: VideoTrafficStatus | 'ALL') => void;
  counts: Record<VideoTrafficStatus, number>;
  total: number;
}) {
  return <div role="group" aria-label="视频标签筛选"
    className="inline-flex w-max max-w-full flex-none flex-wrap items-center gap-1.5">
    {([...VIDEO_TRAFFIC_RULES.map(item => item.status), 'ALL'] as const).map(status => {
      const label = status === 'ALL' ? '全部' : status;
      const count = status === 'ALL' ? total : counts[status];
      const selected = value === status;
      return <button key={status} type="button" aria-label={`${label} ${count}`} aria-pressed={selected}
        onClick={() => onChange(status)}
        className={`inline-flex flex-none items-center gap-1.5 whitespace-nowrap rounded-md px-1.5 py-1 text-[10px] leading-[1.5] outline-none transition-colors focus-visible:ring-2 focus-visible:ring-indigo-300 ${selected ? 'bg-indigo-50/70 ring-1 ring-indigo-400' : 'hover:bg-slate-50'}`}>
        {status === 'ALL' ? <span className={`rounded px-1.5 py-[0.8px] font-semibold ${selected ? 'bg-indigo-100 text-indigo-700' : 'bg-slate-100 text-slate-600'}`}>全部</span> : <VideoTrafficStatusMark status={status} />}
        <span className="font-mono text-[10px] font-medium tabular-nums text-slate-400">{count}</span>
      </button>;
    })}
  </div>;
}
