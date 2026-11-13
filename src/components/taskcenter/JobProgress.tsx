import React from 'react';
import { jobPercent } from './ffmpegTaskModel';

export function JobProgress({ value, label }: { value: number; label: string }) {
  const percent = jobPercent(value);
  return <div role="progressbar" aria-label={label} aria-valuemin={0} aria-valuemax={100} aria-valuenow={percent}
    className="h-1.5 w-full overflow-hidden rounded-full bg-slate-200">
    <div className="h-full rounded-full bg-indigo-500 transition-[width] duration-300" style={{ width: `${percent}%` }} />
  </div>;
}
