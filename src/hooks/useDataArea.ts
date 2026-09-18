/**
 * 把「数据区域」接进 React 组件（刷新大修 · 第 1 步的 1b）
 *
 * 这是 `src/services/dataHub.ts` 的 **React 薄壳**：组件不再自己管缓存和定时器，
 * 只订阅区域、拿快照。数据层的全部行为（3 秒刷新、失败不清空、请求去重）
 * 都在 dataHub 里，这里**不重复实现**。
 *
 * 用法：
 * ```tsx
 * const snapshot = useDataArea('production', loadProductionSummary);
 * // snapshot.data        —— 最后一次成功的数据（从没成功过就是 null）
 * // snapshot.updatedAt   —— 最后一次成功的时间（失败不会动它）
 * // snapshot.error       —— 最后一次失败的原因（成功后清空）
 * // snapshot.loading     —— 是否正在请求
 * ```
 *
 * ⚠️ **不要在组件里再写 setInterval / 自己存缓存** —— 那正是这次大修要拆掉的东西
 * （见 `docs/软件结构全景.md` §2「8 套计时器 / 5 套缓存」）。
 */

import { useCallback, useEffect, useRef, useSyncExternalStore } from 'react';

import { readArea, subscribeArea, type AreaSnapshot, type DataArea } from '../services/dataHub';

export function useDataArea<T>(area: DataArea, fetcher: () => Promise<T>): AreaSnapshot<T> {
  // 用 ref 存 fetcher：调用方不必为了"引用稳定"去包 useCallback，
  // 也不会因为 fetcher 每次渲染都是新函数而反复订阅/退订。
  const fetcherRef = useRef(fetcher);
  useEffect(() => {
    fetcherRef.current = fetcher;
  });

  const subscribe = useCallback(
    (onStoreChange: () => void) =>
      subscribeArea(area, () => fetcherRef.current(), onStoreChange),
    [area],
  );

  // getSnapshot 必须返回**引用稳定**的值，否则 React 会无限重渲染。
  // dataHub 里只在数据真正变化时才替换 snapshot 对象，所以这里是安全的。
  const getSnapshot = useCallback(() => readArea<T>(area), [area]);

  return useSyncExternalStore(subscribe, getSnapshot, getSnapshot);
}
