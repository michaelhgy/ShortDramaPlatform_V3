/**
 * 统一数据层（刷新机制大修 · 第 1 步的 1a）
 *
 * ## 为什么要有这个文件
 *
 * 现在的毛病是：**5 个页面各有一套缓存 + 8 套计时器**，互相不知道对方
 * （详见 `docs/软件结构全景.md` §2）。所以"同一份数据被重复拿""改完别的页面不知道"。
 *
 * 这个模块把「谁在什么时候拉什么数据」收拢到**一个地方**，只做四件事：
 *
 * 1. **一份缓存**：每个"数据区域"只存一份，所有页面共用
 * 2. **一个定时器**：有人看的时候每 3 秒拉一次；**没人看就停**
 * 3. **失败不清空**：拉失败时保留上一次的好数据，只记下错误原因
 * 4. **改完立刻刷**：写操作完成后喊一声 `refreshArea()`
 *
 * 它是**纯 TypeScript，不依赖 React**，所以可以直接跑测试。
 * （页面怎么用它，见第 1b 步。）
 *
 * ## 约定
 *
 * - **一个区域只有一个 fetcher**：后注册的会覆盖前一个（第 1 步只有生产中心一个使用者）
 * - **同一个区域同时只允许一个请求在飞**：重复调用复用同一个 Promise（去重）
 * - **`updatedAt` 只在成功时更新**：所以它表示"数据真正的时间"，不是"最后一次尝试的时间"
 *   （这正是现在"更新于 HH:mm:ss"骗人的原因 —— 见结构全景 §4 问题 5）
 */

/** 数据区域。第 1 步只接 `production`；其余在第 2~4 步逐个接。 */
export type DataArea = 'production' | 'taskCenter' | 'catalog' | 'revenue';

/** 用户明确"几秒内变就行"，所以统一 3 秒（见 `docs/数据与功能全景.md` §4）。 */
export const REFRESH_INTERVAL_MS = 3000;

/** 一个区域当前的样子。页面拿到的就是这个。 */
export type AreaSnapshot<T> = {
  /** 最后一次**成功**拿到的数据。从没成功过就是 null。失败时**保留旧值，不清空**。 */
  data: T | null;
  /** 最后一次**成功**的时间戳。失败不会改它 —— 所以它能如实回答"数据是什么时候的"。 */
  updatedAt: number | null;
  /** 最后一次失败的原因。成功后清空。 */
  error: string | null;
  /** 是否正在请求 */
  loading: boolean;
};

type Entry = {
  snapshot: AreaSnapshot<unknown>;
  fetcher: (() => Promise<unknown>) | null;
  listeners: Set<() => void>;
  inFlight: Promise<void> | null;
};

const entries = new Map<DataArea, Entry>();
let timer: ReturnType<typeof setInterval> | null = null;
let intervalMs = REFRESH_INTERVAL_MS;
let clock: () => number = () => Date.now();

function emptySnapshot(): AreaSnapshot<unknown> {
  return { data: null, updatedAt: null, error: null, loading: false };
}

function entryOf(area: DataArea): Entry {
  let entry = entries.get(area);
  if (!entry) {
    entry = { snapshot: emptySnapshot(), fetcher: null, listeners: new Set(), inFlight: null };
    entries.set(area, entry);
  }
  return entry;
}

function describeError(error: unknown): string {
  if (error instanceof Error && error.message) return error.message;
  if (typeof error === 'string' && error) return error;
  return '读取失败';
}

function notify(entry: Entry): void {
  for (const listener of [...entry.listeners]) listener();
}

/**
 * 拉一次。失败**不清空**旧数据，只写 `error`。
 * 同一区域同时只飞一个请求，重复调用直接复用。
 */
function loadArea(area: DataArea): Promise<void> {
  const entry = entryOf(area);
  const fetcher = entry.fetcher;
  if (!fetcher) return Promise.resolve();
  if (entry.inFlight) return entry.inFlight;

  entry.snapshot = { ...entry.snapshot, loading: true };
  notify(entry);

  const run = (async () => {
    try {
      const data = await fetcher();
      entry.snapshot = { data, updatedAt: clock(), error: null, loading: false };
    } catch (error) {
      // 关键：data / updatedAt 原样保留 —— 界面不会变空，也不会假装刚刚更新过
      entry.snapshot = { ...entry.snapshot, loading: false, error: describeError(error) };
    }
  })();

  entry.inFlight = run;
  return run.finally(() => {
    entry.inFlight = null;
    notify(entry);
  });
}

function ensureTimer(): void {
  if (timer !== null) return;
  timer = setInterval(() => {
    for (const [area, entry] of entries) {
      if (entry.listeners.size > 0) void loadArea(area);
    }
  }, intervalMs);
}

function stopTimerIfIdle(): void {
  if (timer === null) return;
  for (const entry of entries.values()) {
    if (entry.listeners.size > 0) return;
  }
  clearInterval(timer);
  timer = null;
}

/** 读当前快照，**不触发请求**。 */
export function readArea<T>(area: DataArea): AreaSnapshot<T> {
  return entryOf(area).snapshot as AreaSnapshot<T>;
}

/**
 * 订阅一个区域。返回取消订阅的函数。
 *
 * - 订阅时若还没有任何数据，会**立刻拉一次**（页面不用自己管首次加载）
 * - 只要还有订阅者，定时器就会每 3 秒刷一次这个区域
 * - 最后一个订阅者退订后，该区域停止自动刷新（**没人看就不浪费**）
 */
export function subscribeArea<T>(
  area: DataArea,
  fetcher: () => Promise<T>,
  listener: (snapshot: AreaSnapshot<T>) => void,
): () => void {
  const entry = entryOf(area);
  entry.fetcher = fetcher as () => Promise<unknown>;

  const wrapped = () => listener(readArea<T>(area));
  entry.listeners.add(wrapped);
  ensureTimer();

  if (entry.snapshot.data === null && !entry.inFlight) void loadArea(area);
  else wrapped();

  return () => {
    entry.listeners.delete(wrapped);
    stopTimerIfIdle();
  };
}

/**
 * 立刻刷新一个区域。**写操作成功后调用它**，这样用户点完按钮马上能看到结果，
 * 不用等下一个 3 秒周期。
 */
export function refreshArea(area: DataArea): Promise<void> {
  return loadArea(area);
}

/** 当前有几个订阅者（给测试和调试用） */
export function subscriberCount(area: DataArea): number {
  return entryOf(area).listeners.size;
}

/** 定时器是否在跑（给测试和调试用） */
export function isTimerRunning(): boolean {
  return timer !== null;
}

// ------------------------------------------------------------------ 测试辅助

/** 清空全部状态并停表。**只给测试用**，生产代码不要调用。 */
export function resetDataHubForTests(): void {
  if (timer !== null) {
    clearInterval(timer);
    timer = null;
  }
  entries.clear();
  intervalMs = REFRESH_INTERVAL_MS;
  clock = () => Date.now();
}

/** 改自动刷新间隔（**只给测试用**，让测试不用真等 3 秒）。 */
export function setDataHubIntervalForTests(ms: number): void {
  intervalMs = ms;
  if (timer !== null) {
    clearInterval(timer);
    timer = null;
    ensureTimer();
  }
}

/** 换一个假时钟（**只给测试用**），用来验证 `updatedAt` 的语义。 */
export function setDataHubClockForTests(fn: () => number): void {
  clock = fn;
}
