function parseLocalDate(value: string): Date | null {
  const match = value.match(/^(\d{4})-(\d{2})-(\d{2})(?:T|\s)?(\d{2}:\d{2})?/);
  if (!match) return null;
  const [, year, month, day, time = '00:00'] = match;
  const parsed = new Date(`${year}-${month}-${day}T${time}`);
  return Number.isNaN(parsed.getTime()) ? null : parsed;
}

export function formatRelativeDateTime(value?: string): string {
  if (!value) return '';
  if (/^\d{1,2}:\d{2}(:\d{2})?$/.test(value)) return value;
  const parsed = parseLocalDate(value);
  if (!parsed) return value.replace('T', ' ').replace(/\.\d+$/, '').replace(/^\d{4}-/, '');
  const today = new Date();
  const startToday = new Date(today.getFullYear(), today.getMonth(), today.getDate());
  const startDate = new Date(parsed.getFullYear(), parsed.getMonth(), parsed.getDate());
  const dayOffset = Math.round((startDate.getTime() - startToday.getTime()) / 86400000);
  const labels: Record<number, string> = { [-2]: '前天', [-1]: '昨天', 0: '今天', 1: '明天', 2: '后天' };
  const dateLabel = labels[dayOffset] || `${parsed.getMonth() + 1}月${parsed.getDate()}日`;
  return `${dateLabel} ${String(parsed.getHours()).padStart(2, '0')}:${String(parsed.getMinutes()).padStart(2, '0')}`;
}

export function formatDisplayDateTime(value?: string): string {
  if (!value) return '';
  const normalized = value.replace('T', ' ').replace(/\.\d+$/, '');
  return normalized;
}
