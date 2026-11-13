import React, { useEffect, useState } from 'react';
import type { V2InsertionSlot } from '../../api/v2EngineParameters';

export function insertionTime(seconds = 0): string {
  if (!Number.isFinite(seconds)) return '';
  const total = Math.round(seconds);
  return `${Math.floor(total / 60)}:${String(total % 60).padStart(2, '0')}`;
}

export function parseInsertionTime(value: string): number {
  const text = value.trim();
  if (!/^\d+:[0-5]\d$/.test(text)) return NaN;
  const [minutes, seconds] = text.split(':').map(Number);
  return minutes * 60 + seconds;
}

function TimeField({ label, value, onChange }: { label: string; value: number; onChange: (value: number) => void }) {
  const [text, setText] = useState(() => insertionTime(value));
  useEffect(() => {
    if (Number.isFinite(value) && parseInsertionTime(text) !== value) setText(insertionTime(value));
  }, [value]);
  const invalid = !Number.isFinite(parseInsertionTime(text));
  return <input aria-label={label} type="text" inputMode="numeric" placeholder="分:秒" value={text}
    aria-invalid={invalid} onChange={(event) => { setText(event.target.value); onChange(parseInsertionTime(event.target.value)); }}
    className={`w-20 rounded-lg border bg-white px-2 py-1 font-bold text-[#1A1D2E] ${invalid ? 'border-rose-400' : 'border-black/[0.08]'}`} />;
}

export function insertionTimingError(slot: Partial<V2InsertionSlot>): string {
  const values = [slot.min_source_duration_seconds ?? 120, slot.position_start_seconds ?? 120, slot.position_end_seconds ?? 120];
  if (values.some(value => !Number.isFinite(value) || value < 0 || value > 86400)) return '请输入有效的时间（分:秒），例如 5:00。';
  if (values[1] <= 0 || values[1] > values[2]) return '中插位置必须大于0，且下限不能大于上限。';
  return '';
}

export function InsertionTimingFields({ value, onChange }: { value: Partial<V2InsertionSlot>; onChange: (patch: Partial<V2InsertionSlot>) => void }) {
  return <div className="space-y-2 text-[11px] text-[#64748B]">
    <div className="flex flex-wrap items-center gap-2"><span>视频短于</span>
      <TimeField label="不插中插的视频时长门槛" value={value.min_source_duration_seconds ?? 120} onChange={seconds => onChange({ min_source_duration_seconds: seconds })} />
      <span>不插中插</span></div>
    <div className="flex flex-wrap items-center gap-2"><span>中插位置</span>
      <TimeField label="中插位置下限" value={value.position_start_seconds ?? 120} onChange={seconds => onChange({ position_start_seconds: seconds })} />
      <span>至</span><TimeField label="中插位置上限" value={value.position_end_seconds ?? 120} onChange={seconds => onChange({ position_end_seconds: seconds })} />
      <span>（分:秒；相同为固定位置）</span></div>
    <p className="text-[10px]">区间内每条选一个插入点并保存。位置超出片长时取有效交集；没有可用位置则跳过。</p>
  </div>;
}
