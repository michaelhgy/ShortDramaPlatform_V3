import { publishV2DataChange, type V2DataChangeType } from '../services/dataChangeEvents';

export class ApiError extends Error {
  constructor(
    message: string,
    public readonly status?: number,
    public readonly details?: unknown,
  ) {
    super(message);
    this.name = 'ApiError';
  }
}

export interface ApiClientOptions {
  baseUrl?: string;
  timeoutMs?: number;
}

function changeTypeForPath(path: string): V2DataChangeType {
  if (path.includes('/revenue/')) return 'revenue_changed';
  if (path.includes('/release')) return 'release_changed';
  if (path.includes('/production-videos/')) return path.includes('/export') ? 'video_export_changed' : 'video_changed';
  if (path.includes('/production-tasks/')) {
    if (path.includes('/template')) return 'template_changed';
    if (path.includes('/scan')) return 'material_changed';
    return 'production_task_changed';
  }
  if (path.includes('/task-center')) return path.includes('/re-export') ? 'video_export_changed' : 'task_changed';
  if (path.includes('/production-resources')) return 'resource_changed';
  if (path.includes('/sub-theaters')) return 'sub_theater_changed';
  if (path.includes('/theaters')) return 'theater_changed';
  if (path.includes('/drama-profiles') || path.includes('/cover')) return 'profile_changed';
  if (path.includes('/settings')) return 'settings_changed';
  if (path.includes('/accounts')) return 'account_changed';
  if (path.includes('/dramas')) return 'drama_changed';
  return 'unknown';
}

function idFromPath(path: string, segment: string): string | undefined {
  const match = path.match(new RegExp(`/${segment}/([^/?]+)`));
  return match?.[1];
}

const DEFAULT_TIMEOUT_MS = 15_000;

function normalizeBaseUrl(baseUrl: string): string {
  return baseUrl.replace(/\/$/, '');
}

export class ApiClient {
  private readonly baseUrl: string;
  private readonly timeoutMs: number;

  constructor(options: ApiClientOptions = {}) {
    // Empty means same origin, which is the production pywebview deployment.
    this.baseUrl = normalizeBaseUrl(options.baseUrl ?? import.meta.env.VITE_V2_API_BASE_URL ?? '');
    this.timeoutMs = options.timeoutMs ?? DEFAULT_TIMEOUT_MS;
  }

  get<T>(path: string, query?: Record<string, string | number | undefined>): Promise<T> {
    const search = new URLSearchParams();
    Object.entries(query ?? {}).forEach(([key, value]) => {
      if (value !== undefined) search.set(key, String(value));
    });
    const suffix = search.size ? `?${search.toString()}` : '';
    return this.request<T>(`${path}${suffix}`);
  }

  post<T>(path: string, body: unknown = {}): Promise<T> {
    return this.request<T>(path, { method: 'POST', body: JSON.stringify(body) });
  }

  patch<T>(path: string, body: unknown): Promise<T> {
    return this.request<T>(path, { method: 'PATCH', body: JSON.stringify(body) });
  }

  delete<T>(path: string): Promise<T> {
    return this.request<T>(path, { method: 'DELETE' });
  }

  private async request<T>(path: string, init: RequestInit = {}): Promise<T> {
    const controller = new AbortController();
    const timer = window.setTimeout(() => controller.abort(), this.timeoutMs);
    try {
      const response = await fetch(`${this.baseUrl}${path}`, {
        ...init,
        signal: controller.signal,
        headers: { 'Content-Type': 'application/json', ...init.headers },
      });
      const text = await response.text();
      let payload: unknown = {};
      try {
        payload = text ? JSON.parse(text) : {};
      } catch {
        throw new ApiError('V2 本地服务返回了无法识别的结果。', response.status);
      }
      if (!response.ok) {
        const message = typeof payload === 'object' && payload && 'error' in payload
          ? String(payload.error)
          : 'V2 本地服务请求失败。';
        throw new ApiError(message, response.status, payload);
      }
      if (init.method && init.method !== 'GET') {
        const body = payload && typeof payload === 'object' ? payload as Record<string, unknown> : {};
        const changeType = changeTypeForPath(path);
        const returnedId = typeof body.id === 'string' ? body.id : undefined;
        const detail = {
          path, method: init.method, changeType,
          accountId: typeof body.account_id === 'string' ? body.account_id : changeType === 'account_changed' ? (returnedId || idFromPath(path, 'accounts')) : undefined,
          dramaId: typeof body.drama_id === 'string' ? body.drama_id : changeType === 'drama_changed' ? (returnedId || idFromPath(path, 'dramas')) : undefined,
          productionTaskId: typeof body.task_id === 'string' ? body.task_id : idFromPath(path, 'production-tasks'),
          taskId: ['task_changed', 'video_export_changed'].includes(changeType) ? (returnedId || idFromPath(path, 'tasks')) : idFromPath(path, 'tasks'),
          videoId: typeof body.video_id === 'string' ? body.video_id : idFromPath(path, 'production-videos'),
          materialId: typeof body.material_id === 'string' ? body.material_id : undefined,
          entityId: ['theater_changed', 'sub_theater_changed'].includes(changeType)
            ? (returnedId || idFromPath(path, changeType === 'theater_changed' ? 'theaters' : 'sub-theaters'))
            : changeType === 'profile_changed' || changeType === 'settings_changed'
              ? (typeof body.drama_id === 'string' ? body.drama_id : undefined)
              : undefined,
          updatedAt: typeof body.updated_at === 'string' ? body.updated_at : new Date().toISOString(),
        };
        publishV2DataChange({ ...detail, origin: 'client' });
      }
      return payload as T;
    } catch (error) {
      if (error instanceof ApiError) throw error;
      if (error instanceof DOMException && error.name === 'AbortError') {
        throw new ApiError(`请求 V2 本地服务超时（${this.timeoutMs}ms）。`);
      }
      // fetch throws TypeError("Failed to fetch") when the local service is
      // unavailable. Surface an actionable product message instead.
      if (error instanceof TypeError) {
        throw new ApiError('V2 本地服务请求失败，请检查服务是否已启动。');
      }
      throw new ApiError('V2 本地服务请求失败。');
    } finally {
      window.clearTimeout(timer);
    }
  }
}

export const v2Client = new ApiClient();
