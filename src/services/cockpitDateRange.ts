export type CockpitDateRange = 'yesterday' | '7days' | '14days' | '30days' | 'month' | 'all'
  | { kind: 'day'; date: string }
  | { kind: 'range'; start: string; end: string };

export function shiftDate(value: string, days: number): string {
  const date = new Date(value + 'T00:00:00Z');
  date.setUTCDate(date.getUTCDate() + days);
  return date.toISOString().slice(0, 10);
}

function validDate(value: string): boolean {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(value)) return false;
  const date = new Date(value + 'T00:00:00Z');
  return Number.isFinite(date.getTime()) && date.toISOString().slice(0, 10) === value;
}

export function dateRangeError(start: string, end: string, today: string): string {
  if (!validDate(start) || !validDate(end)) return '请选择完整的有效日期';
  if (start > end) return '开始日期不能晚于结束日期';
  if (end > today) return '不能选择未来日期';
  return '';
}

/** Date-only arithmetic uses the server's Beijing date, never the computer's timezone. */
export function resolveCockpitDateRange(range: CockpitDateRange, today: string, earliestDate = today) {
  const yesterday = shiftDate(today, -1);
  let start: string, end: string, label: string;
  if (typeof range === 'object') {
    start = range.kind === 'day' ? range.date : range.start;
    end = range.kind === 'day' ? range.date : range.end;
    const error = dateRangeError(start, end, today);
    if (error) throw new RangeError(error);
    label = start === end ? start : `${start} 至 ${end}`;
  } else {
    end = yesterday;
    switch (range) {
      case 'yesterday': start = yesterday; label = '昨天'; break;
      case '7days': start = shiftDate(yesterday, -6); label = '近7天'; break;
      case '14days': start = shiftDate(yesterday, -13); label = '近14天'; break;
      case '30days': start = shiftDate(yesterday, -29); label = '近30天'; break;
      case 'month': start = today.slice(0, 7) + '-01'; end = today; label = '本月'; break;
      case 'all': start = earliestDate <= yesterday ? earliestDate : yesterday; label = '全部历史'; break;
    }
  }
  const days = Math.round((Date.parse(end + 'T00:00:00Z') - Date.parse(start + 'T00:00:00Z')) / 86400000) + 1;
  return { start, end, days, label };
}

export function dateInRange(date: string, bounds: { start: string; end: string }): boolean {
  return date >= bounds.start && date <= bounds.end;
}
