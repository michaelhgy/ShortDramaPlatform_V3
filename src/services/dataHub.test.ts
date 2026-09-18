/**
 * 统一数据层的报警器（刷新大修 · 第 1 步的 1a）
 *
 * 跑法：`npm test`（或 `node --test src/services/dataHub.test.ts`）
 *
 * 这些测试要钉住的是**行为契约**，不是实现细节：
 *   - 有人看才刷、没人看就停
 *   - 失败**绝不清空**旧数据，也**绝不假装刚更新过**
 *   - 同一区域同时只飞一个请求
 */

import assert from 'node:assert/strict';
import { afterEach, beforeEach, test } from 'node:test';

import {
  isTimerRunning,
  readArea,
  refreshArea,
  resetDataHubForTests,
  setDataHubAreaIntervalForTests,
  setDataHubClockForTests,
  setDataHubTickForTests,
  subscribeArea,
  subscriberCount,
} from './dataHub.ts';

const sleep = (ms: number) => new Promise<void>((resolve) => setTimeout(resolve, ms));

/** 等到条件成立；超时就报错，避免测试挂死 */
async function waitFor(check: () => boolean, timeoutMs = 3000): Promise<void> {
  const started = Date.now();
  while (!check()) {
    if (Date.now() - started > timeoutMs) throw new Error('等待超时');
    await sleep(5);
  }
}

beforeEach(() => resetDataHubForTests());
afterEach(() => resetDataHubForTests());

// ------------------------------------------------------------- 基本：首次加载

test('订阅时若还没有数据，立刻拉一次', async () => {
  let calls = 0;
  const stop = subscribeArea('production', async () => {
    calls += 1;
    return { n: calls };
  }, () => {});

  await waitFor(() => readArea<{ n: number }>('production').data !== null);
  assert.equal(readArea<{ n: number }>('production').data?.n, 1);
  stop();
});

test('数据回来后通知订阅者', async () => {
  let notified = 0;
  const stop = subscribeArea('production', async () => 'v1', () => {
    notified += 1;
  });

  await waitFor(() => notified >= 1);
  assert.equal(readArea<string>('production').data, 'v1');
  stop();
});

test('有数据之后再次订阅：直接给缓存，不重复请求', async () => {
  let calls = 0;
  const fetcher = async () => {
    calls += 1;
    return calls;
  };

  const stopA = subscribeArea('production', fetcher, () => {});
  await waitFor(() => readArea<number>('production').data !== null);
  const afterFirst = calls;

  let seen: number | null = null;
  const stopB = subscribeArea('production', fetcher, (s) => {
    seen = s.data as number | null;
  });

  assert.equal(calls, afterFirst, '第二次订阅不该再发请求');
  assert.equal(seen, afterFirst, '第二次订阅应立刻拿到已有缓存');
  stopA();
  stopB();
});

// --------------------------------------------------------- 有人看才刷、没人停

test('有订阅者时按间隔自动刷新', async () => {
  setDataHubTickForTests(20);
  setDataHubAreaIntervalForTests('production', 20);
  let calls = 0;
  const stop = subscribeArea('production', async () => {
    calls += 1;
    return calls;
  }, () => {});

  await waitFor(() => calls >= 3);
  stop();
});

test('最后一个订阅者退订后：定时器停掉、不再发请求', async () => {
  setDataHubTickForTests(20);
  setDataHubAreaIntervalForTests('production', 20);
  let calls = 0;
  const stop = subscribeArea('production', async () => {
    calls += 1;
    return calls;
  }, () => {});

  await waitFor(() => calls >= 2);
  assert.equal(subscriberCount('production'), 1);
  assert.equal(isTimerRunning(), true);

  stop();
  assert.equal(subscriberCount('production'), 0);
  assert.equal(isTimerRunning(), false, '没人看时定时器必须停');

  const frozen = calls;
  await sleep(90);
  assert.equal(calls, frozen, '退订之后不该再发任何请求');
});

test('多个订阅者共享同一份请求', async () => {
  setDataHubTickForTests(20);
  setDataHubAreaIntervalForTests('production', 20);
  let calls = 0;
  const fetcher = async () => {
    calls += 1;
    return calls;
  };

  const stopA = subscribeArea('production', fetcher, () => {});
  const stopB = subscribeArea('production', fetcher, () => {});

  await waitFor(() => readArea<number>('production').data !== null);
  assert.equal(calls, 1, '两个订阅者应共用同一个请求');
  assert.equal(subscriberCount('production'), 2);
  stopA();
  stopB();
});

// ------------------------------------------------------- 失败：保留旧数据

test('拉失败时：保留旧数据、只记错误、updatedAt 不动', async () => {
  setDataHubClockForTests(() => 1000);
  let shouldFail = false;
  let calls = 0;

  const stop = subscribeArea('production', async () => {
    calls += 1;
    if (shouldFail) throw new Error('后端没起来');
    return { n: calls };
  }, () => {});

  await waitFor(() => readArea<{ n: number }>('production').data !== null);
  const before = readArea<{ n: number }>('production');
  assert.equal(before.updatedAt, 1000);
  assert.equal(before.error, null);

  shouldFail = true;
  await refreshArea('production');

  const after = readArea<{ n: number }>('production');
  assert.deepEqual(after.data, before.data, '失败时必须保留旧数据 —— 界面不能变空');
  assert.equal(after.updatedAt, 1000, '失败不该改 updatedAt —— 不能假装刚更新过');
  assert.equal(after.error, '后端没起来', '失败原因要留下来，界面才有提示可显示');
  assert.equal(after.loading, false);
  stop();
});

test('失败后再成功：错误清空、updatedAt 前进', async () => {
  let time = 1000;
  setDataHubClockForTests(() => time);
  let shouldFail = true;

  const stop = subscribeArea('production', async () => {
    if (shouldFail) throw new Error('暂时失败');
    return 'ok';
  }, () => {});

  await waitFor(() => readArea<string>('production').error !== null);
  assert.equal(readArea<string>('production').error, '暂时失败');
  assert.equal(readArea<string>('production').data, null);

  shouldFail = false;
  time = 2000;
  await refreshArea('production');

  const snapshot = readArea<string>('production');
  assert.equal(snapshot.error, null);
  assert.equal(snapshot.data, 'ok');
  assert.equal(snapshot.updatedAt, 2000);
  stop();
});

test('从没成功过时：data 是 null，但 error 有值（界面能显示"读取失败"）', async () => {
  const stop = subscribeArea('production', async () => {
    throw new Error('连不上');
  }, () => {});

  await waitFor(() => readArea<unknown>('production').error !== null);
  const snapshot = readArea<unknown>('production');
  assert.equal(snapshot.data, null);
  assert.equal(snapshot.updatedAt, null);
  assert.equal(snapshot.error, '连不上');
  stop();
});

// --------------------------------------------------------------- 请求去重

test('同一区域并发刷新：只发一个请求', async () => {
  let calls = 0;
  let release: () => void = () => {};

  const stop = subscribeArea('production', async () => {
    calls += 1;
    await new Promise<void>((resolve) => {
      release = resolve;
    });
    return 'done';
  }, () => {});

  await waitFor(() => calls === 1);

  const first = refreshArea('production');
  const second = refreshArea('production');
  assert.equal(calls, 1, '并发刷新不该发第二个请求');

  release();
  await Promise.all([first, second]);
  assert.equal(readArea<string>('production').data, 'done');
  stop();
});

// ------------------------------------------------------- 没有 fetcher 时

test('没注册 fetcher 时：刷新是空操作，不报错', async () => {
  await refreshArea('revenue');
  const snapshot = readArea<unknown>('revenue');
  assert.equal(snapshot.data, null);
  assert.equal(snapshot.error, null);
  assert.equal(isTimerRunning(), false);
});

// ------------------------------------------------------ 区域之间互不干扰

test('不同区域各自独立：一个失败不影响另一个', async () => {
  const stopA = subscribeArea('production', async () => {
    throw new Error('生产数据挂了');
  }, () => {});
  const stopB = subscribeArea('taskCenter', async () => '任务数据正常', () => {});

  await waitFor(() => readArea<unknown>('production').error !== null);
  await waitFor(() => readArea<string>('taskCenter').data !== null);

  assert.equal(readArea<unknown>('production').data, null);
  assert.equal(readArea<unknown>('production').error, '生产数据挂了');
  assert.equal(readArea<string>('taskCenter').data, '任务数据正常');
  assert.equal(readArea<string>('taskCenter').error, null);

  stopA();
  stopB();
});

// --------------------------------------------- 每个区域有自己的刷新节奏（第 3 步）

test('间隔为 0 的区域：不会自动刷新，但可以按需手动刷', async () => {
  setDataHubTickForTests(20);
  let calls = 0;
  const stop = subscribeArea('catalog', async () => {
    calls += 1;
    return calls;
  }, () => {});

  await waitFor(() => calls === 1); // 首次订阅会拉一次
  const frozen = calls;
  await sleep(100);
  assert.equal(calls, frozen, 'catalog 的间隔是 0，心跳不该触发它（手填资料几天才改一次）');

  await refreshArea('catalog'); // "改完资料立刻刷"走这条路
  assert.equal(calls, frozen + 1, '手动刷必须有效');
  stop();
});

test('不同区域各自独立：慢的区域不被快的带跑', async () => {
  setDataHubTickForTests(20);
  setDataHubAreaIntervalForTests('production', 20);
  setDataHubAreaIntervalForTests('resourceIndex', 100_000); // 真实值是 30 秒

  let fast = 0;
  let slow = 0;
  const stopFast = subscribeArea('production', async () => {
    fast += 1;
    return fast;
  }, () => {});
  const stopSlow = subscribeArea('resourceIndex', async () => {
    slow += 1;
    return slow;
  }, () => {});

  await waitFor(() => fast >= 3);
  assert.equal(slow, 1, '慢区域只该在首次订阅时拉一次 —— 素材盘扫描很贵，绝不能跟着 3 秒跑');

  stopFast();
  stopSlow();
});
