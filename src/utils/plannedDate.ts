/** Calendar planning only. Actual publishing and cleanup keep full timestamps. */
export function plannedDate(value?: string): string {
  if (!value || !/^\d{4}-\d{2}-\d{2}(?:$|T|\s)/.test(value)) return '';
  const day = value.slice(0, 10), parsed = new Date(`${day}T00:00:00Z`);
  return Number.isFinite(parsed.getTime()) && parsed.toISOString().slice(0, 10) === day ? day : '';
}
export function planningToday(now = new Date()): string {
  return new Intl.DateTimeFormat('en-CA', { timeZone: 'Asia/Shanghai', year: 'numeric', month: '2-digit', day: '2-digit' }).format(now);
}
export function planningDayOffset(days = 0, now = new Date()): string {
  const day = new Date(`${planningToday(now)}T00:00:00Z`);
  day.setUTCDate(day.getUTCDate() + days);
  return day.toISOString().slice(0, 10);
}
export function formatPlannedDate(value?: string): string {
  const day=plannedDate(value);
  return day ? `${Number(day.slice(5,7))}月${Number(day.slice(8,10))}日` : '未设置计划发布日期';
}
export function plannedSortTimestamp(value?: string): number {
  const day = plannedDate(value);
  return day ? Date.parse(`${day}T00:00:00+08:00`) : Number.MAX_SAFE_INTEGER;
}
export function isPlanOverdue(value?: string, now = new Date()): boolean {
  const day = plannedDate(value);
  return Boolean(day && day < planningToday(now));
}
