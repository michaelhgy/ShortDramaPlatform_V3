import { changeAffects, eventDetail, type V2DataChangeDetail } from './dataChangeEvents';

export type V2DataArea = 'analytics' | 'assets' | 'production' | 'task_center';
export type V2RefreshRequest = {
  reason: 'change' | 'reconcile' | 'resume';
  detail?: V2DataChangeDetail;
};

type Subscriber = {
  area: V2DataArea;
  refresh: (request: V2RefreshRequest) => Promise<void> | void;
  running: boolean;
  queued?: V2RefreshRequest;
};

const subscribers = new Set<Subscriber>();
let lifecycleStarted = false;
let reconcileTimer: number | null = null;

function run(subscriber: Subscriber, request: V2RefreshRequest): void {
  if (subscriber.running) {
    // A request that arrives while an older one is still loading is retained.
    // The page gets one more current refresh afterwards instead of competing
    // requests whose response order is unknowable.
    subscriber.queued = request;
    return;
  }
  subscriber.running = true;
  Promise.resolve(subscriber.refresh(request)).catch(() => {
    // Each page preserves its last valid data and decides how to show errors.
  }).finally(() => {
    subscriber.running = false;
    const queued = subscriber.queued;
    subscriber.queued = undefined;
    if (queued) run(subscriber, queued);
  });
}

function broadcast(request: V2RefreshRequest): void {
  subscribers.forEach((subscriber) => run(subscriber, request));
}

function onDataChanged(event: Event): void {
  const detail = eventDetail(event);
  subscribers.forEach((subscriber) => {
    if (changeAffects(detail, subscriber.area)) run(subscriber, { reason: 'change', detail });
  });
}

/**
 * One lifecycle for page refresh fallback checks. Normal work is event-driven;
 * this 60-second check only repairs a missed notification or local-service
 * restart. Hidden windows do not issue ordinary requests.
 */
export function startV2DataRefreshCoordinator(): () => void {
  if (lifecycleStarted) return () => undefined;
  lifecycleStarted = true;
  window.addEventListener('v2-data-changed', onDataChanged);
  const onVisibilityChange = () => {
    if (!document.hidden) broadcast({ reason: 'resume' });
  };
  document.addEventListener('visibilitychange', onVisibilityChange);
  reconcileTimer = window.setInterval(() => {
    if (!document.hidden) broadcast({ reason: 'reconcile' });
  }, 60_000);
  return () => {
    lifecycleStarted = false;
    window.removeEventListener('v2-data-changed', onDataChanged);
    document.removeEventListener('visibilitychange', onVisibilityChange);
    if (reconcileTimer) window.clearInterval(reconcileTimer);
    reconcileTimer = null;
  };
}

/** Register a mounted page with the shared refresh lifecycle. */
export function subscribeV2DataRefresh(
  area: V2DataArea,
  refresh: (request: V2RefreshRequest) => Promise<void> | void,
): () => void {
  const subscriber: Subscriber = { area, refresh, running: false };
  subscribers.add(subscriber);
  return () => subscribers.delete(subscriber);
}
