/**
 * 让「内容没变的元素沿用旧引用」，从而让 React 跳过不必要的重画。
 *
 * ## 为什么需要它（用户 2026-09-18 的历史经验）
 *
 * 用户原话："**以前最开始就是全量刷新，会很卡，页面经常闪**。"
 *
 * 问题不在于「从后端拿多少数据」（106 个任务，实测几十毫秒，很便宜），
 * 而在于「**界面重画了多少**」——生产中心那 106 张任务卡是内联画的，
 * 没有 `React.memo` 隔离。所以只要列表数组换了引用，**所有卡片都会重画一遍**。
 *
 * 如果每 3 秒无条件重画 106 张卡片，就会重现用户说的"卡"和"闪"。
 *
 * ## 它怎么解决
 *
 * 后端照旧**整体拉一遍**（便宜、不会漏、不需要"谁变了"的通知），
 * 但拿到之后先跟旧数据逐条对比：
 *
 * - **内容没变的** → 沿用**旧对象引用**
 * - **真的变了的** → 用新对象
 * - **连内容带顺序都没变** → **整个数组也沿用旧的**
 *
 * React 对 `setState` 有一个优化：**传入的值和当前值全等时直接跳过重渲染**。
 * 所以最后那种情况（刷新时什么都没变 —— 大多数时候都是这样）**一次重画都不会发生**。
 *
 * ## 比较方式
 *
 * 只做**浅比较**（逐字段 `!==`）。这是**故意的保守选择**：
 * 如果某个字段是每次都新建的数组/对象，浅比较会判成"变了"，
 * 最坏结果只是**多画一张卡片** —— 不会漏更新。**宁可多画，不可漏画。**
 */

function shallowEqual(a: object, b: object): boolean {
  if (a === b) return true;
  const keysA = Object.keys(a);
  const keysB = Object.keys(b);
  if (keysA.length !== keysB.length) return false;
  const left = a as Record<string, unknown>;
  const right = b as Record<string, unknown>;
  for (const key of keysA) {
    if (left[key] !== right[key]) return false;
  }
  return true;
}

/**
 * 把 `next` 里"和 `previous` 中同 id 条目内容相同"的元素换成旧引用。
 *
 * 若整个列表（内容 + 顺序 + 长度）都没变，**返回 `previous` 本身**，
 * 这样调用方 `setState` 时会被 React 判定为"没变化"，跳过重画。
 */
export function reuseUnchanged<T extends { id: string }>(previous: T[], next: T[]): T[] {
  if (previous === next) return previous;
  if (previous.length === 0) return next.length === 0 ? previous : next;
  if (next.length === 0) return next;

  const byId = new Map<string, T>();
  for (const item of previous) byId.set(item.id, item);

  let changed = 0;
  const merged = next.map((item) => {
    const old = byId.get(item.id);
    if (old && shallowEqual(old, item)) return old;
    changed += 1;
    return item;
  });

  if (changed === 0 && merged.length === previous.length) {
    let identical = true;
    for (let i = 0; i < merged.length; i += 1) {
      if (merged[i] !== previous[i]) {
        identical = false;
        break;
      }
    }
    if (identical) return previous;
  }

  return merged;
}

/** 给"按 id 存的对象字典"用：内容没变的条目沿用旧引用。 */
export function reuseUnchangedRecord<T extends { id: string }>(
  previous: Record<string, T>,
  next: Record<string, T>,
): Record<string, T> {
  let changed = false;
  const merged: Record<string, T> = {};
  for (const [id, item] of Object.entries(next)) {
    const old = previous[id];
    if (old && shallowEqual(old, item)) {
      merged[id] = old;
    } else {
      merged[id] = item;
      changed = true;
    }
  }
  if (!changed && Object.keys(merged).length === Object.keys(previous).length) return previous;
  return merged;
}
