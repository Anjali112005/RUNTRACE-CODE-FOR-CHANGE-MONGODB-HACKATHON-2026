import { Activity, CheckCircle2, SearchCheck, Timer } from 'lucide-react';
import { useSearchParams } from 'react-router-dom';
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import { ActivityChart } from '../components/ActivityChart';
import { Card, EmptyState, ErrorState, Loading, PageHeader, StatStrip } from '../components/ui';
import { useMetrics, useProjects } from '../hooks/queries';
import { formatDuration, formatPercent } from '../lib/format';

const DAY_OPTIONS = [7, 30, 90, 365];

export function MetricsPage() {
  const [params, setParams] = useSearchParams();
  const projectId = params.get('project_id') ?? undefined;
  const days = Number(params.get('days') ?? '30') || 30;
  const includeDemo = params.get('include_demo') !== 'false';
  const metrics = useMetrics({ project_id: projectId, days, include_demo: includeDemo });
  const projects = useProjects({ page_size: 100 });
  const m = metrics.data;

  const set = (key: string, value: string | null) => {
    const next = new URLSearchParams(params);
    if (value) next.set(key, value);
    else next.delete(key);
    setParams(next);
  };

  return (
    <div className="space-y-6">
      <PageHeader title="Metrics" subtitle="Computed from every matching run in the selected window — never from a paginated subset." />
      <Card>
        <div className="flex flex-wrap items-center gap-3">
          <select aria-label="Project" className="input w-auto" value={projectId ?? ''} onChange={(e) => set('project_id', e.target.value || null)}>
            <option value="">All projects</option>
            {projects.data?.items.map((p) => <option key={p.project_id} value={p.project_id}>{p.name}</option>)}
          </select>
          <div className="flex overflow-hidden rounded-md border-[1.5px] border-strong" role="group" aria-label="Time window">
            {DAY_OPTIONS.map((d) => (
              <button key={d} type="button" onClick={() => set('days', String(d))} aria-pressed={d === days}
                className={d === days ? 'bg-accent px-3 py-1.5 text-sm font-semibold text-accent-fg' : 'bg-card px-3 py-1.5 text-sm hover:bg-soft'}>
                {d === 365 ? '1y' : `${d}d`}
              </button>
            ))}
          </div>
          <label className="flex items-center gap-2 text-sm">
            <input type="checkbox" checked={includeDemo} onChange={(e) => set('include_demo', e.target.checked ? null : 'false')} /> Include demo data
          </label>
        </div>
      </Card>

      {metrics.isLoading && <Loading rows={4} />}
      {metrics.isError && <ErrorState error={metrics.error} onRetry={() => metrics.refetch()} />}
      {m && (
        <>
          <StatStrip
            items={[
              { icon: <Activity size={22} />, value: m.totals.runs, label: `Runs (${m.scope.days}d)` },
              { icon: <CheckCircle2 size={22} />, value: formatPercent(m.success_rate), label: `Success rate (${m.totals.finished} finished)` },
              { icon: <Timer size={22} />, value: formatDuration(m.average_duration_ms), label: `Avg. duration (n=${m.duration_sample_size})` },
              { icon: <SearchCheck size={22} />, value: `${m.findings.verified}/${m.findings.total}`, label: 'Findings verified' },
            ]}
          />
          {m.totals.runs === 0 ? (
            <EmptyState title="No runs in this window" description="Widen the time window or record runs with the SDK." />
          ) : (
            <div className="grid gap-6 lg:grid-cols-2">
              <Card title="Run activity"><ActivityChart data={m.activity} /></Card>
              <Card title="Failures by version">
                <div style={{ height: 240 }} role="img" aria-label="Successful and failed runs per version">
                  <ResponsiveContainer width="100%" height="100%">
                    <BarChart data={m.by_version} margin={{ top: 8, right: 8, left: -20, bottom: 0 }}>
                      <CartesianGrid stroke="var(--border)" vertical={false} />
                      <XAxis dataKey="version" tick={{ fontSize: 11, fill: 'var(--muted)' }} />
                      <YAxis allowDecimals={false} tick={{ fontSize: 11, fill: 'var(--muted)' }} axisLine={false} tickLine={false} />
                      <Tooltip contentStyle={{ background: 'var(--card)', border: '1.5px solid var(--border-strong)', fontSize: 12 }} />
                      <Bar dataKey="success" name="Success" stackId="v" fill="var(--accent)" stroke="var(--border-strong)" />
                      <Bar dataKey="failed" name="Failed" stackId="v" fill="var(--danger)" stroke="var(--border-strong)" />
                    </BarChart>
                  </ResponsiveContainer>
                </div>
                <p className="mt-2 text-xs text-muted">A version with more failures is correlated with them; it is not proof the version caused them.</p>
              </Card>
            </div>
          )}
          <Card title="Status breakdown">
            <table className="table-compact">
              <thead><tr><th>Status</th><th>Runs</th></tr></thead>
              <tbody>
                <tr><td>Success</td><td>{m.totals.success}</td></tr>
                <tr><td>Failed</td><td>{m.totals.failed}</td></tr>
                <tr><td>Timed out (no finish received)</td><td>{m.totals.timed_out}</td></tr>
                <tr><td>Running</td><td>{m.totals.running}</td></tr>
                <tr><td>All time (scope)</td><td>{m.totals.all_time_runs}</td></tr>
              </tbody>
            </table>
            <ul className="mt-3 list-disc space-y-1 pl-5 text-xs text-muted">
              {m.notes.map((n) => <li key={n}>{n}</li>)}
            </ul>
          </Card>
        </>
      )}
    </div>
  );
}
