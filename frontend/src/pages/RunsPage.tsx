import { Search } from 'lucide-react';
import { useState } from 'react';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import { DemoBadge, StatusBadge } from '../components/badges';
import { Card, EmptyState, ErrorState, Loading, PageHeader, Pagination } from '../components/ui';
import { useProjects, useRuns } from '../hooks/queries';
import { formatDuration, formatRelative, shortId } from '../lib/format';

const STATUSES = ['', 'running', 'success', 'failed', 'timed_out'];

export function RunsPage() {
  const [params, setParams] = useSearchParams();
  const navigate = useNavigate();
  const [q, setQ] = useState(params.get('q') ?? '');
  const filters = {
    project_id: params.get('project_id') ?? undefined,
    status: params.get('status') ?? undefined,
    q: params.get('q') ?? undefined,
    version: params.get('version') ?? undefined,
    include_demo: params.get('include_demo') !== 'false',
    page: Number(params.get('page') ?? '1') || 1,
    page_size: 25,
  };
  const runs = useRuns(filters);
  const projects = useProjects({ page_size: 100 });

  const update = (key: string, value: string | null) => {
    const next = new URLSearchParams(params);
    if (value) next.set(key, value);
    else next.delete(key);
    if (key !== 'page') next.delete('page');
    setParams(next);
  };

  return (
    <div className="space-y-6">
      <PageHeader title="Runs" subtitle="Every recorded execution. Filter by project, status or version; open a run to inspect its timeline." />
      <Card>
        <div className="grid gap-3 md:grid-cols-5">
          <form
            role="search"
            className="relative md:col-span-2"
            onSubmit={(e) => {
              e.preventDefault();
              update('q', q.trim() || null);
            }}
          >
            <Search size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-muted" />
            <input aria-label="Search runs" className="input pl-9" placeholder="Name, run ID or error text — press Enter" value={q} onChange={(e) => setQ(e.target.value)} />
          </form>
          <select aria-label="Filter by project" className="input" value={filters.project_id ?? ''} onChange={(e) => update('project_id', e.target.value || null)}>
            <option value="">All projects</option>
            {projects.data?.items.map((p) => (
              <option key={p.project_id} value={p.project_id}>{p.name}</option>
            ))}
          </select>
          <select aria-label="Filter by status" className="input" value={filters.status ?? ''} onChange={(e) => update('status', e.target.value || null)}>
            {STATUSES.map((s) => (
              <option key={s} value={s}>{s ? s.replace('_', ' ') : 'Any status'}</option>
            ))}
          </select>
          <label className="flex items-center gap-2 text-sm">
            <input type="checkbox" checked={filters.include_demo} onChange={(e) => update('include_demo', e.target.checked ? null : 'false')} />
            Include demo data
          </label>
        </div>
        {filters.version && (
          <p className="mt-3 text-sm">
            Version <code className="font-semibold">{filters.version}</code>{' '}
            <button type="button" className="text-xs underline" onClick={() => update('version', null)}>clear</button>
          </p>
        )}
      </Card>

      {runs.isLoading && <Loading rows={6} />}
      {runs.isError && <ErrorState error={runs.error} onRetry={() => runs.refetch()} />}
      {runs.data && runs.data.items.length === 0 && (
        <EmptyState title="No runs match" description="Adjust the filters, or record a run with the SDK." action={<Link className="btn-primary" to="/integration">Set up the SDK</Link>} />
      )}
      {runs.data && runs.data.items.length > 0 && (
        <Card bodyClassName="p-0">
          <div className="overflow-x-auto">
            <table className="table-compact">
              <thead>
                <tr><th>Run</th><th>Project</th><th>Version</th><th>Status</th><th>Started</th><th>Duration</th><th>Events</th></tr>
              </thead>
              <tbody>
                {runs.data.items.map((r) => (
                  <tr key={r.run_id} className="cursor-pointer" onClick={() => navigate(`/runs/${r.run_id}`)}>
                    <td>
                      <Link to={`/runs/${r.run_id}`} className="font-semibold hover:underline" onClick={(e) => e.stopPropagation()}>{r.name}</Link>
                      <div className="mono-id flex items-center gap-1.5">{shortId(r.run_id)} {r.is_demo && <DemoBadge />}</div>
                    </td>
                    <td className="max-w-[180px] truncate">{r.project_name ?? shortId(r.project_id)}</td>
                    <td className="font-mono text-xs">{r.version ?? '—'}</td>
                    <td><StatusBadge status={r.status} /></td>
                    <td className="whitespace-nowrap">{formatRelative(r.started_at)}</td>
                    <td className="font-mono text-xs">{formatDuration(r.duration_ms)}</td>
                    <td>{r.event_count}{r.failed_event_count > 0 && <span className="text-danger"> ({r.failed_event_count} failed)</span>}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="px-4 pb-3">
            <Pagination meta={runs.data.meta} onPage={(p) => update('page', String(p))} />
          </div>
        </Card>
      )}
    </div>
  );
}
