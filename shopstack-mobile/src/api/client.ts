import { getToken, getApiBaseUrl } from '../storage/token';

const TIMEOUT_MS = 15000;
const API_BASE_DEFAULT = 'http://localhost:7860';

// In-memory cache for token and base URL — avoids async SecureStore read
// on every network request. Refreshed on auth flow transitions.
let _cachedBaseUrl: string | null = null;
let _cachedToken: string | null = null;

export function setCachedBaseUrl(url: string): void {
  _cachedBaseUrl = url;
}

export function setCachedToken(token: string | null): void {
  _cachedToken = token;
}

export function getCachedToken(): string | null {
  return _cachedToken;
}

async function _resolveBaseUrl(): Promise<string> {
  if (_cachedBaseUrl) return _cachedBaseUrl;
  const stored = await getApiBaseUrl();
  _cachedBaseUrl = stored || API_BASE_DEFAULT;
  return _cachedBaseUrl;
}

async function _resolveToken(): Promise<string | null> {
  if (_cachedToken) return _cachedToken;
  const stored = await getToken();
  _cachedToken = stored;
  return _cachedToken;
}

export class ApiErrorResponse extends Error {
  constructor(
    public status: number,
    public code: string,
    message: string,
    public details?: Record<string, unknown>,
  ) {
    super(message);
    this.name = 'ApiErrorResponse';
  }
}

interface RequestOptions {
  method?: string;
  body?: unknown;
  params?: Record<string, string | number | boolean | undefined>;
  skipAuth?: boolean;
  timeout?: number;
}

export async function apiRequest<T>(
  path: string,
  options: RequestOptions = {},
): Promise<T> {
  const baseUrl = await _resolveBaseUrl();
  const { method = 'GET', body, params, skipAuth = false, timeout = TIMEOUT_MS } = options;

  const url = new URL(path, baseUrl.replace(/\/+$/, ''));
  if (params) {
    for (const [key, value] of Object.entries(params)) {
      if (value !== undefined) {
        url.searchParams.set(key, String(value));
      }
    }
  }

  const headers: Record<string, string> = {
    'Accept': 'application/json',
  };

  if (!skipAuth) {
    const token = await _resolveToken();
    if (token) {
      headers['Authorization'] = `Bearer ${token}`;
    }
  }

  if (body !== undefined) {
    headers['Content-Type'] = 'application/json';
  }

  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeout);

  try {
    const response = await fetch(url.toString(), {
      method,
      headers,
      body: body ? JSON.stringify(body) : undefined,
      signal: controller.signal,
    });

    if (!response.ok) {
      let errorData: { code?: string; message?: string; details?: Record<string, unknown> } = {};
      try {
        errorData = await response.json();
      } catch {
        // Non-JSON error response
      }
      // Clear cached token on 401 so the next auth gate check is accurate
      if (response.status === 401) {
        _cachedToken = null;
      }
      throw new ApiErrorResponse(
        response.status,
        errorData.code || `http_${response.status}`,
        errorData.message || `Request failed with status ${response.status}`,
        errorData.details,
      );
    }

    if (response.status === 204) {
      return undefined as T;
    }

    const data = await response.json();
    return data as T;
  } catch (err) {
    if (err instanceof ApiErrorResponse) throw err;
    if ((err as Error).name === 'AbortError') {
      throw new ApiErrorResponse(0, 'timeout', 'Request timed out');
    }
    throw new ApiErrorResponse(0, 'network_error', (err as Error).message || 'Network request failed');
  } finally {
    clearTimeout(timer);
  }
}

export const api = {
  get: <T>(path: string, params?: Record<string, string | number | boolean | undefined>, skipAuth?: boolean) =>
    apiRequest<T>(path, { method: 'GET', params, skipAuth }),

  post: <T>(path: string, body?: unknown, skipAuth?: boolean) =>
    apiRequest<T>(path, { method: 'POST', body, skipAuth }),

  put: <T>(path: string, body?: unknown) =>
    apiRequest<T>(path, { method: 'PUT', body }),

  delete: <T>(path: string) =>
    apiRequest<T>(path, { method: 'DELETE' }),
};
