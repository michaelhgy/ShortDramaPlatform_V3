import { accountImportStatus, type AccountImportRun } from '../api/accountImport';
import { publishV2DataChange } from './dataChangeEvents';
import { refreshArea } from './dataHub';

interface Watch {
  run: AccountImportRun;
  listeners: Set<(run: AccountImportRun) => void>;
  notified: Set<string>;
  failures: number;
}
const watches = new Map<string, Watch>();
const active = (run: AccountImportRun) => ['queued', 'running'].includes(run.status);

function update(watch: Watch, run: AccountImportRun) {
  watch.run = run;
  let changed = false;
  for (const result of run.results) {
    if (result.status !== 'updated' || !result.account_id || watch.notified.has(result.account_id)) continue;
    watch.notified.add(result.account_id);
    changed = true;
    publishV2DataChange({ changeType: 'account_changed', accountId: result.account_id, origin: 'client' });
  }
  if (changed) void refreshArea('catalog');
  watch.listeners.forEach(listener => listener(run));
}

async function poll(watch: Watch) {
  try {
    const result = await accountImportStatus(watch.run.id);
    watch.failures = 0;
    update(watch, result);
  } catch (error) {
    watch.failures += 1;
    if (watch.failures >= 3) {
      update(watch, { ...watch.run, status: 'error', message: '读取头像同步进度失败，后台任务可能仍在继续；重新获取可核对头像' });
    }
  }
  if (active(watch.run)) window.setTimeout(() => void poll(watch), 700);
}

/** One observer per task. Closing the dialog only removes its listener. */
export function observeAvatarSync(initial: AccountImportRun, listener?: (run: AccountImportRun) => void): () => void {
  let watch = watches.get(initial.id);
  if (!watch) {
    watch = { run: initial, listeners: new Set(), notified: new Set(), failures: 0 };
    watches.set(initial.id, watch);
    update(watch, initial);
    if (active(initial)) window.setTimeout(() => void poll(watch!), 700);
    for (const [id, item] of watches) {
      if (watches.size <= 20) break;
      if (!active(item.run) && !item.listeners.size) watches.delete(id);
    }
  }
  if (listener) { watch.listeners.add(listener); listener(watch.run); }
  return () => { if (listener) watch!.listeners.delete(listener); };
}
