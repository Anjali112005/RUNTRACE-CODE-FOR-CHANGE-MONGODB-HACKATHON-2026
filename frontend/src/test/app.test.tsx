import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';
import { baseHandlers, emptyPage, mockFetch, renderApp, run } from './utils';

describe('navigation', () => {
  it('renders all eight sections and navigates between them', async () => {
    mockFetch(baseHandlers);
    renderApp('/');
    const nav = screen.getByRole('navigation', { name: 'Main' });
    const labels = within(nav).getAllByRole('link').map((a) => a.textContent);
    expect(labels).toEqual(['Overview', 'Projects', 'Runs', 'Compare Runs', 'Findings', 'Metrics', 'SDK & Integration', 'Settings']);
    expect(screen.getByRole('heading', { level: 1, name: 'Overview' })).toBeInTheDocument();

    await userEvent.click(within(nav).getByRole('link', { name: 'Runs' }));
    expect(await screen.findByRole('heading', { level: 1, name: 'Runs' })).toBeInTheDocument();
    expect(within(nav).getByRole('link', { name: 'Runs' })).toHaveAttribute('aria-current', 'page');

    await userEvent.click(within(nav).getByRole('link', { name: 'SDK & Integration' }));
    expect(await screen.findByRole('heading', { level: 1, name: 'SDK & Integration' })).toBeInTheDocument();
  });

  it('shows backend connection status', async () => {
    mockFetch(baseHandlers);
    renderApp('/');
    expect(await screen.findByText('Connected')).toBeInTheDocument();
  });
});

describe('theme', () => {
  it('defaults to light and persists the dark selection', async () => {
    mockFetch(baseHandlers);
    renderApp('/');
    expect(document.documentElement).not.toHaveClass('dark');
    await userEvent.click(screen.getByRole('button', { name: 'Switch to dark theme' }));
    expect(document.documentElement).toHaveClass('dark');
    expect(localStorage.getItem('runtrace-theme')).toBe('dark');
    await userEvent.click(screen.getByRole('button', { name: 'Switch to light theme' }));
    expect(document.documentElement).not.toHaveClass('dark');
  });
});

describe('states', () => {
  it('shows empty states when there is no data', async () => {
    mockFetch(baseHandlers);
    renderApp('/runs');
    expect(await screen.findByText('No runs match')).toBeInTheDocument();
  });

  it('shows a loading state before data arrives', () => {
    mockFetch(baseHandlers);
    renderApp('/runs');
    expect(screen.getAllByRole('status')[0]).toHaveTextContent('Loading');
  });

  it('shows an actionable error (never fake data) when the API is unreachable', async () => {
    const { fetchMock } = mockFetch(baseHandlers);
    fetchMock.mockImplementation(async () => {
      throw new TypeError('Failed to fetch');
    });
    renderApp('/runs');
    expect(await screen.findByRole('alert')).toHaveTextContent('Cannot reach the RunTrace API');
    expect(screen.queryByText('Customer Support Workflow')).not.toBeInTheDocument();
  });

  it('explains database outages', async () => {
    mockFetch({
      ...baseHandlers,
      'GET /api/runs': () => ({ status: 503, body: { error: { code: 'database_unavailable', message: 'MongoDB is not reachable.' } } }),
    });
    renderApp('/runs');
    const alert = await screen.findByRole('alert');
    expect(alert).toHaveTextContent('MongoDB is not reachable.');
    expect(alert).toHaveTextContent('RUNTRACE_MONGODB_URI');
  });
});

describe('runs', () => {
  it('lists runs and shows a run timeline with the recorded error', async () => {
    const r = run();
    mockFetch({
      ...baseHandlers,
      'GET /api/runs': { items: [r], meta: { total: 1, page: 1, page_size: 25, pages: 1 } },
      [`GET /api/runs/${r.run_id}`]: r,
      [`GET /api/runs/${r.run_id}/events`]: {
        run_id: r.run_id,
        total: 2,
        items: [
          { event_id: 'evt_1', run_id: r.run_id, project_id: r.project_id, sequence: 1, event_type: 'llm', name: 'call_llm', status: 'success',
            timestamp: '2026-10-10T10:00:00Z', duration_ms: 900, input_summary: null, output_summary: { text: '```json {}```' }, error: null, metadata: {} },
          { event_id: 'evt_2', run_id: r.run_id, project_id: r.project_id, sequence: 2, event_type: 'parse', name: 'parse_response', status: 'failed',
            timestamp: '2026-10-10T10:00:01Z', duration_ms: 1, input_summary: '```json {}```', output_summary: null,
            error: { type: 'json.decoder.JSONDecodeError', message: 'Expecting value' }, metadata: {} },
        ],
      },
      [`GET /api/runs/${r.run_id}/findings`]: [],
    });
    renderApp('/runs');
    await userEvent.click(await screen.findByRole('link', { name: 'Customer Support Workflow' }));
    expect(await screen.findByText('call_llm')).toBeInTheDocument();
    expect(screen.getAllByText('parse_response').length).toBeGreaterThan(0);
    // The first failed step is expanded automatically and shows its error.
    expect(await screen.findByText(/json.decoder.JSONDecodeError: Expecting value/)).toBeInTheDocument();
    expect(screen.getByText('Not analyzed yet')).toBeInTheDocument();
  });
});

describe('projects', () => {
  it('validates and creates a project, showing the key exactly once', async () => {
    const key = 'rt_live_' + 'k'.repeat(43);
    const created = {
      project: { project_id: 'prj_' + 'c'.repeat(32), name: 'Support Bot', description: '', settings: {}, is_demo: false,
        created_at: '2026-10-10T10:00:00Z', updated_at: '2026-10-10T10:00:00Z', stats: null },
      key: { key_id: 'key_1', project_id: 'prj_' + 'c'.repeat(32), api_key: key, prefix: 'rt_live_kkkk', created_at: '2026-10-10T10:00:00Z' },
    };
    let body: unknown = null;
    mockFetch({
      ...baseHandlers,
      'GET /api/projects': emptyPage,
      'POST /api/projects': (_url: URL, init: RequestInit | undefined) => {
        body = JSON.parse(String(init?.body));
        return { status: 201, body: created };
      },
    });
    renderApp('/projects?new=1');
    await userEvent.click(await screen.findByRole('button', { name: 'Create project' }));
    expect(await screen.findByText('Name is required')).toBeInTheDocument();

    await userEvent.type(screen.getByLabelText('Name'), 'Support Bot');
    await userEvent.type(screen.getByLabelText('Environment (optional)'), 'dev');
    await userEvent.click(screen.getByRole('button', { name: 'Create project' }));
    expect(await screen.findByTestId('api-key')).toHaveTextContent(key);
    expect(body).toEqual({ name: 'Support Bot', description: '', settings: { environment: 'dev' } });
    expect(JSON.stringify(localStorage)).not.toContain(key);

    await userEvent.click(screen.getByRole('button', { name: 'I have saved the key' }));
    await waitFor(() => expect(screen.queryByTestId('api-key')).not.toBeInTheDocument());
  });
});

describe('compare', () => {
  it('shows the earliest divergence and hypotheses', async () => {
    const base = run({ run_id: 'run_' + '1'.repeat(32), status: 'success', version: '1.0' });
    const cmp = run({ run_id: 'run_' + '2'.repeat(32) });
    const ref = (r: typeof base, seq: number, name: string, status: string, output: unknown) => ({
      event_id: `evt_${r.run_id}_${seq}`, run_id: r.run_id, sequence: seq, name, event_type: 'step', status,
      duration_ms: 1, timestamp: null, input_summary: null, output_summary: output, error: null, metadata: {},
    });
    const result = {
      baseline: { ...base, metadata: {} }, comparison: { ...cmp, metadata: {} },
      alignment_strategy: 'logical-step-key', warnings: [], run_differences: [],
      summary: { unchanged: 0, changed: 1, added: 0, missing: 0, status_changed: 0, output_changed: 1, notable_timing: 0 },
      entries: [{
        position: 0, step_key: 'call_llm#1', name: 'call_llm', kind: 'changed', reordered: false, timing: null,
        baseline: ref(base, 1, 'call_llm', 'success', { text: '{}' }), comparison: ref(cmp, 1, 'call_llm', 'success', { text: '```' }),
        differences: [{ field: 'output', schema_changed: false, changes: [{ path: '$.text', kind: 'value_changed', baseline: '{}', comparison: '```' }] }],
        description: "Step 'call_llm': output value changed (text).",
      }],
      earliest_divergence: { position: 0, step_key: 'call_llm#1', name: 'call_llm', kind: 'changed',
        description: "Step 'call_llm': output value changed (text).", baseline_event_id: null, comparison_event_id: null,
        baseline_sequence: 1, comparison_sequence: 1, fields: ['output'] },
      first_failure: null,
      diagnosis: { persisted: false, note: 'Hypotheses are not proven causes.', findings: [{
        category: 'invalid_json', severity: 'high', confidence: 'high', title: "Invalid JSON while running 'parse_response'",
        summary: 'x', observation: 'Step raised JSONDecodeError.', hypothesis: 'The step likely received fenced JSON.',
        suggested_actions: ['Inspect the input.'], evidence: [], regression_test: 'def test_x():\n    assert True\n', step: 'parse_response' }] },
    };
    const { calls } = mockFetch({
      ...baseHandlers,
      'GET /api/runs': { items: [base, cmp], meta: { total: 2, page: 1, page_size: 100, pages: 1 } },
      'POST /api/compare': result,
    });
    renderApp(`/compare?baseline=${base.run_id}&comparison=${cmp.run_id}`);
    const callout = await screen.findByTestId('earliest-divergence');
    expect(callout).toHaveTextContent("Step 'call_llm': output value changed (text).");
    expect(screen.getByText("Invalid JSON while running 'parse_response'")).toBeInTheDocument();
    expect(screen.getByText('Hypothesis — not a proven cause', { exact: false })).toBeInTheDocument();
    const post = calls.find((c) => c.init?.method === 'POST');
    expect(JSON.parse(String(post?.init?.body))).toMatchObject({ baseline_run_id: base.run_id, comparison_run_id: cmp.run_id });
  });
});
