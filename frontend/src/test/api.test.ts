import { describe, expect, it, vi } from 'vitest';
import { ApiError, apiRequest, buildUrl, setAdminToken } from '../api/client';
import { formatDuration, shortId } from '../lib/format';

describe('api client', () => {
  it('builds URLs and drops empty query values', () => {
    const url = new URL(buildUrl('/api/runs', { status: 'failed', q: '', project_id: undefined, page: 2, include_demo: false }));
    expect(url.pathname).toBe('/api/runs');
    expect(Object.fromEntries(url.searchParams)).toEqual({ status: 'failed', page: '2', include_demo: 'false' });
  });

  it('turns error bodies into ApiError with code and message', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => new Response(JSON.stringify({ error: { code: 'conflict', message: 'dup', details: { a: 1 } } }), { status: 409 })));
    await expect(apiRequest('/api/x')).rejects.toMatchObject({ status: 409, code: 'conflict', message: 'dup', details: { a: 1 } });
  });

  it('reports network failures as status 0', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => { throw new TypeError('Failed to fetch'); }));
    const err = await apiRequest('/health').catch((e) => e);
    expect(err).toBeInstanceOf(ApiError);
    expect(err.status).toBe(0);
    expect(err.code).toBe('network_error');
  });

  it('sends the admin token only when set, from memory', async () => {
    const fetchMock = vi.fn(async () => new Response('{}', { status: 200 }));
    vi.stubGlobal('fetch', fetchMock);
    await apiRequest('/api/projects');
    expect((fetchMock.mock.calls[0] as unknown[])[1]).toMatchObject({ headers: expect.not.objectContaining({ 'X-RunTrace-Admin-Token': expect.anything() }) });
    setAdminToken('secret-token');
    await apiRequest('/api/projects');
    expect((fetchMock.mock.calls[1] as unknown[])[1]).toMatchObject({ headers: expect.objectContaining({ 'X-RunTrace-Admin-Token': 'secret-token' }) });
    expect(JSON.stringify(localStorage)).not.toContain('secret-token');
    setAdminToken(null);
  });
});

describe('formatting', () => {
  it('formats durations and ids', () => {
    expect(formatDuration(null)).toBe('—');
    expect(formatDuration(820)).toBe('820 ms');
    expect(formatDuration(1500)).toBe('1.50 s');
    expect(formatDuration(125000)).toBe('2m 5s');
    expect(shortId('run_0123456789abcdef')).toBe('run_01234567');
  });
});
