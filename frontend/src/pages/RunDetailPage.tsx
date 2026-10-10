import { GitCompareArrows, ScanSearch } from 'lucide-react';
import { Link, useParams } from 'react-router-dom';
import { DemoBadge, StatusBadge } from '../components/badges';
import { EventTimeline } from '../components/EventTimeline';
import { AIPanel, FindingBody, FindingHeader } from '../components/FindingView';
import { Card, CopyButton, EmptyState, ErrorState, JsonView, KeyValue, Loading, PageHeader } from '../components/ui';
import { useAnalyzeRun, useRun, useRunEvents, useRunFindings } from '../hooks/queries';
import { formatDateTime, formatDuration } from '../lib/format';

export function RunDetailPage() {
  const { runId = '' } = useParams();
  const run = useRun(runId);
  const events = useRunEvents(runId);
  const findings = useRunFindings(runId);
  const analyze = useAnalyzeRun();

  if (run.isLoading) return <Loading />;
  if (run.isError) return <ErrorState error={run.error} onRetry={() => run.refetch()} />;
  if (!run.data) return null;
  const r = run.data;

  return (
    <div className="space-y-6">
      <PageHeader
        title={r.name}
        subtitle={
          <span className="flex flex-wrap items-center gap-2">
            <StatusBadge status={r.status} />
            {r.is_demo && <DemoBadge />}
            <span className="chip border-line text-muted">source: {r.source}</span>
            <span className="font-mono text-xs">{r.run_id}</span>
            <CopyButton text={r.run_id} label="Copy ID" />
          </span>
        }
        actions={
          <>
            <Link to={`/compare?comparison=${r.run_id}&project_id=${r.project_id}`} className="btn-ghost">
              <GitCompareArrows size={16} /> Compare
            </Link>
            <button
              type="button"
              className="btn-primary"
              disabled={analyze.isPending || r.status === 'running'}
              onClick={() => analyze.mutate({ runId: r.run_id })}
              title={r.status === 'running' ? 'Wait for the run to finish' : 'Run deterministic diagnosis'}
            >
              <ScanSearch size={16} /> {analyze.isPending ? 'Analyzing…' : 'Analyze'}
            </button>
          </>
        }
      />

      <Card>
        <dl className="grid grid-cols-2 gap-4 md:grid-cols-4">
          <KeyValue label="Project">
            <Link className="underline decoration-dotted" to={`/projects/${r.project_id}`}>{r.project_name ?? r.project_id}</Link>
          </KeyValue>
          <KeyValue label="Version">{r.version ?? '—'}</KeyValue>
          <KeyValue label="Environment">{r.environment ?? '—'}</KeyValue>
          <KeyValue label="Duration">{r.status === 'running' ? 'In progress' : formatDuration(r.duration_ms)}</KeyValue>
          <KeyValue label="Started">{formatDateTime(r.started_at)}</KeyValue>
          <KeyValue label="Finished">{r.finished_at ? formatDateTime(r.finished_at) : 'Not finished'}</KeyValue>
          <KeyValue label="Events">{r.event_count} ({r.failed_event_count} failed)</KeyValue>
          <KeyValue label="First failed step">{String(r.summary?.first_failed_step ?? '—')}</KeyValue>
        </dl>
        {r.error_summary && (
          <div className="mt-4 rounded-md border-[1.5px] border-danger bg-[var(--danger-soft)] p-3">
            <p className="label text-danger">Error summary</p>
            <p className="font-mono text-sm">{r.error_summary}</p>
          </div>
        )}
        {Object.keys(r.metadata ?? {}).length > 0 && (
          <details className="mt-4">
            <summary className="label cursor-pointer">Run metadata</summary>
            <JsonView value={r.metadata} />
          </details>
        )}
      </Card>

      <div className="grid gap-6 xl:grid-cols-5">
        <Card title="Event timeline" className="xl:col-span-3">
          {events.isLoading && <Loading />}
          {events.isError && <ErrorState error={events.error} onRetry={() => events.refetch()} />}
          {events.data && events.data.items.length === 0 && <EmptyState title="No events" description="This run has no recorded steps." />}
          {events.data && events.data.items.length > 0 && <EventTimeline events={events.data.items} />}
        </Card>

        <Card title="Findings" className="xl:col-span-2">
          {analyze.isError && <ErrorState error={analyze.error} compact />}
          {analyze.data && (
            <p className="mb-3 text-xs text-muted">
              Baseline: {analyze.data.baseline_run_id ? (
                <Link className="underline" to={`/runs/${analyze.data.baseline_run_id}`}>{analyze.data.baseline_run_id.slice(0, 12)}</Link>
              ) : 'none found'} ({analyze.data.baseline_selection.replace(/_/g, ' ')})
            </p>
          )}
          {findings.isLoading && <Loading />}
          {findings.isError && <ErrorState error={findings.error} onRetry={() => findings.refetch()} />}
          {findings.data && findings.data.length === 0 && (
            <EmptyState title="Not analyzed yet" description="Click Analyze to classify recorded errors and compare with the latest successful run of this workflow." />
          )}
          <div className="space-y-3">
            {findings.data?.map((f) => (
              <details key={f.finding_id} className="rounded-md border-[1.5px] border-line p-3 open:border-strong">
                <summary className="cursor-pointer list-none">
                  <p className="font-semibold">{f.title}</p>
                  <div className="mt-1.5"><FindingHeader finding={f} /></div>
                </summary>
                <div className="mt-3 space-y-3">
                  <FindingBody finding={f} />
                  <Link className="btn-ghost" to={`/findings?selected=${f.finding_id}`}>Open & verify</Link>
                </div>
              </details>
            ))}
          </div>
          <div className="mt-4"><AIPanel runId={r.run_id} /></div>
        </Card>
      </div>
    </div>
  );
}
