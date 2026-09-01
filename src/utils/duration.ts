/** Format an elapsed duration for the task-centre UI. */
export function formatElapsedSeconds(seconds: number | null | undefined, fallback = '尚未开始'): string {
  if (seconds === null || seconds === undefined || !Number.isFinite(seconds) || seconds < 0) return fallback;
  const total = Math.max(0, Math.floor(seconds));
  if (total < 60) return `${total}秒`;
  const minutes = Math.floor(total / 60);
  const remainingSeconds = total % 60;
  if (minutes < 60) return `${minutes}分${String(remainingSeconds).padStart(2, '0')}秒`;
  const hours = Math.floor(minutes / 60);
  const remainingMinutes = minutes % 60;
  return `${hours}小时${remainingMinutes}分${String(remainingSeconds).padStart(2, '0')}秒`;
}

export function taskElapsedLabel(seconds: number | null | undefined, legacy?: string): string {
  if (seconds !== null && seconds !== undefined && Number.isFinite(seconds) && seconds > 0) return formatElapsedSeconds(seconds);
  return legacy && !/^[-—]$/.test(legacy.trim()) ? legacy : formatElapsedSeconds(seconds);
}
