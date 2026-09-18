/**
 * 文件名自然序比较：把数字段按数值比，其余按文字比。
 *
 * 用于参数中心显示"引流视频（中插 / 尾插）"素材清单时的排序。
 * 必须与后端选素材的排序（`server/v2_file_service.py` 的 `natural_key`）语义一致，
 * 否则界面上显示的"当前会用到哪一条"会和真正生成时选的那条不一致。
 *
 * 例：中插2 < 中插10（不是字符串序的"中插10" < "中插2"）。
 */
function segments(name: string): Array<string | number> {
  const parts: Array<string | number> = [];
  const pattern = /(\d+)/g;
  let cursor = 0;
  let match: RegExpExecArray | null;
  while ((match = pattern.exec(name)) !== null) {
    if (match.index > cursor) parts.push(name.slice(cursor, match.index));
    parts.push(Number(match[1]));
    cursor = match.index + match[1].length;
  }
  if (cursor < name.length) parts.push(name.slice(cursor));
  return parts;
}

export function naturalCompare(left: string, right: string): number {
  const a = segments(left);
  const b = segments(right);
  const length = Math.max(a.length, b.length);
  for (let index = 0; index < length; index += 1) {
    const first = a[index];
    const second = b[index];
    if (first === undefined) return -1;
    if (second === undefined) return 1;
    if (typeof first === 'number' && typeof second === 'number') {
      if (first !== second) return first - second;
      continue;
    }
    const firstText = String(first).toLowerCase();
    const secondText = String(second).toLowerCase();
    if (firstText !== secondText) return firstText < secondText ? -1 : 1;
  }
  return 0;
}
