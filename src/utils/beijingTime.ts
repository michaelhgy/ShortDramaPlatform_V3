export const BEIJING_TIME_ZONE = 'Asia/Shanghai';

function parts(now: Date) {
  const values = new Intl.DateTimeFormat('en-CA', {
    timeZone: BEIJING_TIME_ZONE,
    year: 'numeric', month: '2-digit', day: '2-digit',
    hour: '2-digit', minute: '2-digit', second: '2-digit', hourCycle: 'h23',
  }).formatToParts(now).reduce<Record<string, string>>((result, part) => {
    if (part.type !== 'literal') result[part.type] = part.value;
    return result;
  }, {});
  return values;
}

export function beijingDateString(now = new Date()): string {
  const value = parts(now);
  return `${value.year}-${value.month}-${value.day}`;
}

export function beijingTimeString(now = new Date()): string {
  const value = parts(now);
  return `${value.hour}:${value.minute}:${value.second}`;
}

export function beijingDateTimeString(now = new Date()): string {
  return `${beijingDateString(now)} ${beijingTimeString(now).slice(0, 5)}`;
}

export function shiftBeijingDateTime(value: string, minutes: number): string {
  const match = /^(\d{4})-(\d{2})-(\d{2})[ T](\d{2}):(\d{2})/.exec(value);
  if (!match) return '';
  const [, year, month, day, hour, minute] = match;
  const shifted = new Date(Date.UTC(Number(year), Number(month) - 1, Number(day), Number(hour), Number(minute) + minutes));
  const pad = (number: number) => String(number).padStart(2, '0');
  return `${shifted.getUTCFullYear()}-${pad(shifted.getUTCMonth() + 1)}-${pad(shifted.getUTCDate())} ${pad(shifted.getUTCHours())}:${pad(shifted.getUTCMinutes())}`;
}
