import { API_BASE_URL } from '../lib/config';

/** Error thrown for every failed API call. status 0 means the API could not be reached. */
export class ApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly details?: unknown;

  constructor(status: number, code: string, message: string, details?: unknown) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.code = code;
    this.details = details;
  }
}

// The optional admin token lives in memory only (never in localStorage/sessionStorage),
// so it disappears on reload and cannot be read from browser storage.
let adminToken: string | null = null;
const listeners = new Set<() => void>();

export function setAdminToken(token: string | null): void {
  adminToken = token && token.trim() ? token.trim() : null;
  listeners.forEach((fn) => fn());
}

export function getAdminToken(): string | null {
  return adminToken;
}

export function subscribeAdminToken(fn: () => void): () => void {
  listeners.add(fn);
  return () => listeners.delete(fn);
}

export type QueryValue = string | number | boolean | null | undefined;

export interface RequestOptions {
  method?: 'GET' | 'POST' | 'PATCH';
  body?: unknown;
  query?: Record<string, QueryValue>;
  signal?: AbortSignal;
}

export function buildUrl(path: string, query?: Record<string, QueryValue>): string {
  const url = new URL(API_BASE_URL + path);
  if (query) {
    for (const [key, value] of Object.entries(query)) {
      if (value === undefined || value === null || value === '') continue;
      url.searchParams.set(key, String(value));
    }
  }
  return url.toString();
}

export async function apiRequest<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const headers: Record<string, string> = { Accept: 'application/json' };
  if (options.body !== undefined) headers['Content-Type'] = 'application/json';
  if (adminToken) headers['X-RunTrace-Admin-Token'] = adminToken;

  let response: Response;
  try {
    response = await fetch(buildUrl(path, options.query), {
      method: options.method ?? 'GET',
      headers,
      body: options.body !== undefined ? JSON.stringify(options.body) : undefined,
      signal: options.signal,
    });
  } catch (err) {
    if (err instanceof DOMException && err.name === 'AbortError') throw err;
    throw new ApiError(
      0,
      'network_error',
      `Cannot reach the RunTrace API at ${API_BASE_URL}. Is the backend running and is this origin allowed by CORS?`,
    );
  }

  const text = await response.text();
  let data: unknown = null;
  if (text) {
    try {
      data = JSON.parse(text);
    } catch {
      data = null;
    }
  }
  if (!response.ok) {
    const err = (data as { error?: { code?: string; message?: string; details?: unknown } } | null)?.error;
    throw new ApiError(
      response.status,
      err?.code ?? `http_${response.status}`,
      err?.message ?? `Request failed with HTTP ${response.status}.`,
      err?.details,
    );
  }
  return data as T;
}
