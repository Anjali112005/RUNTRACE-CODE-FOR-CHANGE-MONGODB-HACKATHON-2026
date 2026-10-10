import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { vi } from 'vitest';
import { AppRoutes } from '../App';
import { ThemeProvider } from '../contexts/ThemeContext';

export type Handler = (url: URL, init: RequestInit | undefined) => { status?: number; body: unknown } | undefined;

/** Stub global fetch. Handlers are matched in order; unmatched requests get a 404 error body. */
export function mockFetch(handlers: Record<string, Handler | unknown>) {
  const calls: { url: URL; init?: RequestInit }[] = [];
  const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = new URL(String(input));
    calls.push({ url, init });
    const key = `${init?.method ?? 'GET'} ${url.pathname}`;
    const entry = handlers[key];
    let result: { status?: number; body: unknown } | undefined;
    if (typeof entry === 'function') result = (entry as Handler)(url, init);
    else if (entry !== undefined) result = { body: entry };
    if (!result) result = { status: 404, body: { error: { code: 'not_found', message: `No mock for ${key}` } } };
    return new Response(JSON.stringify(result.body), {
      status: result.status ?? 200,
      headers: { 'Content-Type': 'application/json' },
    });
  });
  vi.stubGlobal('fetch', fetchMock);
  return { fetchMock, calls };
}

export function renderApp(path = '/') {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <ThemeProvider>
        <MemoryRouter initialEntries={[path]}>
          <AppRoutes />
        </MemoryRouter>
      </ThemeProvider>
    </QueryClientProvider>,
  );
}

export const health = {
  status: 'ok', service: 'runtrace-api', version: '0.1.0', time: '2026-10-10T00:00:00Z',
  database: { connected: true, name: 'runtrace', latency_ms: 1.2, error: null, indexes_ready: true },
  auth_mode: 'open', ai: { enabled: false, model: null }, limits: { max_request_bytes: 1048576, max_events_per_batch: 500 },
};

export const emptyPage = { items: [], meta: { total: 0, page: 1, page_size: 25, pages: 1 } };

export const emptyMetrics = {
  scope: { project_id: null, days: 14, since: '2026-09-27T00:00:00Z', include_demo: true },
  totals: { projects: 0, runs: 0, success: 0, failed: 0, timed_out: 0, running: 0, finished: 0, all_time_runs: 0 },
  success_rate: null, average_duration_ms: null, duration_sample_size: 0, by_version: [], activity: [],
  findings: { total: 0, high: 0, verified: 0, unverified: 0 }, notes: [], generated_at: '2026-10-10T00:00:00Z',
};

export function run(overrides: Record<string, unknown> = {}) {
  return {
    run_id: 'run_' + 'a'.repeat(32), project_id: 'prj_' + 'b'.repeat(32), project_name: 'Support Bot', version_id: null,
    version: '1.1', name: 'Customer Support Workflow', status: 'failed', environment: 'dev',
    started_at: '2026-10-10T10:00:00Z', finished_at: '2026-10-10T10:00:01Z', duration_ms: 1000,
    error_summary: 'parse_response: JSONDecodeError: Expecting value', summary: { first_failed_step: 'parse_response' },
    metadata: {}, event_count: 2, failed_event_count: 1, is_demo: false, source: 'sdk', ...overrides,
  };
}

export const baseHandlers = {
  'GET /health': health,
  'GET /api/metrics': emptyMetrics,
  'GET /api/runs': emptyPage,
  'GET /api/findings': emptyPage,
  'GET /api/projects': emptyPage,
  'GET /api/ai/status': { enabled: false, model: null, reason: 'GEMINI_API_KEY is not configured on the server.' },
};
