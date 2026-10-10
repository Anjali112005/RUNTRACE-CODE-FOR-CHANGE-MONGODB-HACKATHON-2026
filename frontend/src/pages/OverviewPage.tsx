import { Activity, CheckCircle2, FolderKanban, Timer } from 'lucide-react';
import { Link } from 'react-router-dom';
import { ActivityChart } from '../components/ActivityChart';
import { DemoBadge, SeverityBadge, VerificationBadge } from '../components/badges';
import { RunList } from '../components/RunList';
import { ArrowCta, Card, EmptyState, ErrorState, Loading, PageHeader, StatStrip } from '../components/ui';
import { useFindings, useMetrics, useRuns } from '../hooks/queries';
import { formatDuration, formatPercent, formatRelative } from '../lib/format';

export function OverviewPage() {
  const metrics = useMetrics({ days: 14 });
  const runs = useRuns({ page_size: 5 });
  const findings = useFindings({ page_size: 5 });
  const m = metrics.data;
  const noData = m && m.totals.projects === 0;

  return (
    <div className="space-y-6">
      <PageHeader title="Overview" subtitle="A summary of recent runs, failures and findings across your projects (last 14 days)." />

      {metrics.isLoading && <Loading rows={1} />}
      {metrics.isError && <ErrorState error={metrics.error} onRetry={() => metrics.refetch()} />}
      {m && (
        <StatStrip
          items={[
            { icon: <FolderKanban size={22} />, value: m.totals.projects, label: 'Projects' },
            { icon: <Activity size={22} />, value: m.totals.runs, label: 'Runs (14 days)' },
            { icon: <CheckCircle2 size={22} />, value: formatPercent(m.success_rate), label: 'Success rate' },
            { icon: <Timer size={22} />, value: formatDuration(m.average_duration_ms), label: 'Avg. duration' },
          ]}
        />
      )}

      {noData && (
        <EmptyState
          title="No projects yet"
          description={
            <>
              Create a project to get an API key and start recording runs with the SDK — or load the demo with{' '}
              <code className="rounded bg-soft px-1">python -m app.seed_demo</code> in the backend folder.
            </>
          }
          action={<Link to="/projects?new=1" className="btn-primary">Create project</Link>}
        />
      )}

      <div className="grid gap-6 lg:grid-cols-5">
        <Card title="Run activity" className="lg:col-span-3">
          {m ? <ActivityChart data={m.activity} /> : metrics.isLoading ? <Loading rows={4} /> : null}
          {m && (
            <p className="mt-2 text-xs text-muted">
              {m.totals.success} successful · {m.totals.failed + m.totals.timed_out} failed or timed out · {m.totals.running} running
            </p>
          )}
        </Card>
        <div className="space-y-3 lg:col-span-2">
          <h2 className="section-title">Quick actions</h2>
          <ArrowCta to="/projects?new=1">New project</ArrowCta>
          <ArrowCta to="/compare">Compare runs</ArrowCta>
          <ArrowCta to="/integration">Instrument your app</ArrowCta>
        </div>
      </div>

      <div className="grid gap-6 lg:grid-cols-2">
        <Card title="Recent runs" actions={<Link to="/runs" className="text-sm font-semibold text-[var(--warning)] hover:underline">View all</Link>}>
          {runs.isLoading && <Loading />}
          {runs.isError && <ErrorState error={runs.error} onRetry={() => runs.refetch()} />}
          {runs.data && runs.data.items.length === 0 && (
            <EmptyState title="No runs recorded" description="Runs appear here once an instrumented app sends them." />
          )}
          {runs.data && runs.data.items.length > 0 && <RunList runs={runs.data.items} />}
        </Card>
        <Card title="Recent findings" actions={<Link to="/findings" className="text-sm font-semibold text-[var(--warning)] hover:underline">View all</Link>}>
          {findings.isLoading && <Loading />}
          {findings.isError && <ErrorState error={findings.error} onRetry={() => findings.refetch()} />}
          {findings.data && findings.data.items.length === 0 && (
            <EmptyState title="No findings yet" description="Analyze a failed run or compare two runs to generate evidence-backed findings." />
          )}
          <ul className="divide-y divide-line">
            {findings.data?.items.map((f) => (
              <li key={f.finding_id}>
                <Link to={`/findings?selected=${f.finding_id}`} className="flex items-center gap-3 py-2.5 hover:bg-soft">
                  <SeverityBadge severity={f.severity} />
                  <span className="min-w-0 flex-1">
                    <span className="block truncate font-medium">{f.title}</span>
                    <span className="text-xs text-muted">{formatRelative(f.created_at)}</span>
                  </span>
                  {f.is_demo && <DemoBadge />}
                  <VerificationBadge status={f.verification_status} />
                </Link>
              </li>
            ))}
          </ul>
        </Card>
      </div>
    </div>
  );
}
