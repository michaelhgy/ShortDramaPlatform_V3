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
      return payload as T;
    } catch (error) {
      if (error instanceof ApiError) throw error;
      if (error instanceof DOMException && error.name === 'AbortError') {
        throw new ApiError(`请求 V2 本地服务超时（${this.timeoutMs}ms）。`);
      }
      throw new ApiError(error instanceof Error ? error.message : '无法连接 V2 本地服务。');
    } finally {
      window.clearTimeout(timer);
    }
  }
}

export const v2Client = new ApiClient();
