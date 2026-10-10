import { ArrowLeftRight, Flag, GitCompareArrows, Save } from 'lucide-react';
import { useEffect, useMemo, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { DemoBadge, KindBadge, StatusBadge } from '../components/badges';
import { FindingBody, FindingHeader } from '../components/FindingView';
import { Card, EmptyState, ErrorState, JsonView, Loading, PageHeader } from '../components/ui';
import { useAnalyzeRun, useCompare, useProjects, useRuns } from '../hooks/queries';
import { cn } from '../lib/cn';
import { formatDuration, formatRelative, humanize, shortId } from '../lib/format';
import type { CompareEntry, CompareResult, Run, RunMeta } from '../types/api';

function runLabel(r: Run): string {
  return `${r.name} · ${r.version ? `v${r.version} · ` : ''}${r.status} · ${formatRelative(r.started_at)} · ${shortId(r.run_id)}`;
}

function RunHeader({ label, run }: { label: string; run: RunMeta }) {
  return (
    <div className="card-strong p-3">
      <p className="label">{label}</p>
      <Link to={`/runs/${run.run_id}`} className="block truncate font-semibold hover:underline">{run.name}</Link>
      <div className="mt-1.5 flex flex-wrap items-center gap-2 text-xs text-muted">
        <StatusBadge status={run.status} />
        {run.is_demo && <DemoBadge />}
        <span>v{run.version ?? '—'}</span>
        <span>{run.event_count} events</span>
        <span>{formatDuration(run.duration_ms)}</span>
      </div>
    </div>
  );
}

function stepCell(ref: CompareEntry['baseline']) {
  if (!ref) return <span className="text-xs italic text-muted">not recorded</span>;
  return (
    <span className="flex items-center gap-2">
      <StatusBadge status={ref.status} />
      <span className="font-mono text-xs text-muted">#{ref.sequence} · {formatDuration(ref.duration_ms)}</span>
    </span>
  );
}

function EvidencePanel({ entry }: { entry: CompareEntry | null }) {
  if (!entry) return <p className="text-sm text-muted">Select a step to see the recorded values side by side.</p>;
  return (
    <div className="space-y-3">
      <div className="flex items-center gap-2">
        <KindBadge kind={entry.kind} />
        <span className="font-semibold">{entry.name}</span>
        <span className="mono-id">{entry.step_key}</span>
        {entry.reordered && <span className="chip border-warning text-warning">reordered</span>}
      </div>
      {entry.description && <p className="text-sm">{entry.description}</p>}
      {entry.differences.map((d) => (
        <div key={d.field} className="rounded-md border border-line p-2.5">
          <p className="label">{d.field}{d.schema_changed ? ' · schema changed' : ''}</p>
          {d.changes ? (
            <ul className="space-y-1 text-xs">
              {d.changes.map((c, i) => (
                <li key={i} className="font-mono">
                  <span className="font-semibold">{c.path}</span> <span className="text-muted">{humanize(c.kind)}</span>
                  {c.kind === 'type_changed' && <span> {c.baseline_type} → {c.comparison_type}</span>}
                  {c.kind === 'value_changed' && <span> {JSON.stringify(c.baseline)} → {JSON.stringify(c.comparison)}</span>}
                  {c.kind === 'length_changed' && <span> {String(c.baseline)} → {String(c.comparison)}</span>}
                </li>
              ))}
            </ul>
          ) : (
            <p className="font-mono text-xs">{JSON.stringify(d.baseline)} → {JSON.stringify(d.comparison)}</p>
          )}
        </div>
      ))}
      {entry.timing && (
        <p className={cn('text-xs', entry.timing.notable ? 'text-warning' : 'text-muted')}>
          Duration {formatDuration(entry.timing.baseline_ms)} → {formatDuration(entry.timing.comparison_ms)}
          {entry.timing.ratio ? ` (×${entry.timing.ratio})` : ''}{entry.timing.notable ? ' · notable' : ''} — timing alone is not counted as divergence.
        </p>
      )}
      <div className="grid gap-3 md:grid-cols-2">
        {(['baseline', 'comparison'] as const).map((side) => {
          const ref = entry[side];
          return (
            <div key={side} className="min-w-0">
              <p className="label">{side}</p>
              {ref ? (
                <div className="space-y-1.5">
                  {ref.error && <p className="font-mono text-xs text-danger">{ref.error.type}: {ref.error.message}</p>}
                  <p className="text-[11px] text-muted">input</p>
                  <JsonView value={ref.input_summary} />
                  <p className="text-[11px] text-muted">output</p>
                  <JsonView value={ref.output_summary} />
                </div>
              ) : (
                <p className="text-sm italic text-muted">Step not recorded in this run.</p>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}

function Results({ result }: { result: CompareResult }) {
  const analyze = useAnalyzeRun();
  const div = result.earliest_divergence;
  const [selected, setSelected] = useState<number | null>(div ? div.position : null);
  useEffect(() => setSelected(div ? div.position : null), [div]);
  const entry = selected !== null ? result.entries[selected] ?? null : null;
  const s = result.summary;
  const looksLikeFix = (result.baseline.status === 'failed' || result.baseline.status === 'timed_out') && result.comparison.status === 'success';

  return (
    <div className="space-y-6">
      <div className="grid gap-3 md:grid-cols-2">
        <RunHeader label="Baseline" run={result.baseline} />
        <RunHeader label="Comparison" run={result.comparison} />
      </div>
      {result.warnings.map((w) => (
        <p key={w} className="rounded-md border-[1.5px] border-warning bg-[var(--warning-soft)] px-3 py-2 text-sm">{w}</p>
      ))}

      <div className="flex flex-wrap gap-2 text-xs">
        {(['unchanged', 'changed', 'added', 'missing'] as const).map((k) => (
          <span key={k} className="chip border-line"><KindBadge kind={k} /> {String(s[k] ?? 0)}</span>
        ))}
        <span className="chip border-line text-muted">status changed: {String(s.status_changed ?? 0)}</span>
        <span className="chip border-line text-muted">output changed: {String(s.output_changed ?? 0)}</span>
        <span className="chip border-line text-muted">notable timing: {String(s.notable_timing ?? 0)}</span>
      </div>

      {div ? (
        <div className="card-strong flex flex-col gap-2 border-strong bg-accent p-4 text-accent-fg sm:flex-row sm:items-center" data-testid="earliest-divergence">
          <Flag size={22} className="shrink-0" />
          <div className="flex-1">
            <p className="font-display text-lg font-bold uppercase">Earliest observable divergence · step {div.position + 1}</p>
            <p className="text-sm">{div.description}</p>
          </div>
          <button type="button" className="btn-secondary" onClick={() => setSelected(div.position)}>Show evidence</button>
        </div>
      ) : (
        <EmptyState title="No divergence" description="All recorded steps match in status, output, error and metadata (timing differences are listed separately)." />
      )}

      {looksLikeFix && (
        <p className="rounded-md border-[1.5px] border-success bg-[var(--success-soft)] px-3 py-2 text-sm">
          The comparison run succeeded where the baseline failed. To confirm a fix, open the failed run’s{' '}
          <Link className="font-semibold underline" to={`/findings?run_id=${result.baseline.run_id}`}>findings</Link> and verify them against this run.
        </p>
      )}

      <div className="grid gap-6 lg:grid-cols-5">
        <Card title="Step by step" className="lg:col-span-3" bodyClassName="p-0">
          <div className="overflow-x-auto">
            <table className="table-compact">
              <thead><tr><th>#</th><th>Step</th><th>Baseline</th><th>Comparison</th><th>Change</th></tr></thead>
              <tbody>
                {result.entries.map((e) => (
                  <tr
                    key={e.step_key + e.position}
                    onClick={() => setSelected(e.position)}
                    aria-selected={selected === e.position}
                    className={cn('cursor-pointer', selected === e.position && 'bg-[var(--accent-soft)]', div?.position === e.position && 'border-l-4 border-l-[var(--accent)]')}
                  >
                    <td className="font-mono text-xs">{e.position + 1}</td>
                    <td className="font-semibold">{e.name}</td>
                    <td>{stepCell(e.baseline)}</td>
                    <td>{stepCell(e.comparison)}</td>
                    <td>
                      <KindBadge kind={e.kind} />
                      {e.differences.length > 0 && <span className="ml-1 text-xs text-muted">{e.differences.map((d) => d.field).join(', ')}</span>}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="px-4 py-2 text-[11px] text-muted">Alignment: {result.alignment_strategy}. Steps are paired by name and occurrence, never by sequence number alone.</p>
        </Card>
        <Card title="Evidence" className="lg:col-span-2"><EvidencePanel entry={entry} /></Card>
      </div>

      {result.run_differences.length > 0 && (
        <Card title="Run-level differences">
          <ul className="space-y-1 font-mono text-xs">
            {result.run_differences.map((d) =>
              d.changes ? (
                d.changes.map((c) => <li key={d.field + c.path}>{d.field} {c.path}: {JSON.stringify(c.baseline)} → {JSON.stringify(c.comparison)}</li>)
              ) : (
                <li key={d.field}>{d.field}: {JSON.stringify(d.baseline)} → {JSON.stringify(d.comparison)}</li>
              ),
            )}
          </ul>
        </Card>
      )}

      {result.diagnosis && (
        <Card
          title="Diagnostic hypotheses"
          actions={
            <button
              type="button"
              className="btn-primary py-1.5"
              disabled={analyze.isPending || result.comparison.status === 'running'}
              onClick={() => analyze.mutate({ runId: result.comparison.run_id, baselineRunId: result.baseline.run_id })}
            >
              <Save size={14} /> {analyze.isPending ? 'Saving…' : 'Save findings'}
            </button>
          }
        >
          <p className="mb-3 text-xs text-muted">{result.diagnosis.note}</p>
          {analyze.isError && <ErrorState error={analyze.error} compact />}
          {analyze.data && (
            <p className="mb-3 rounded-md border-[1.5px] border-success bg-[var(--success-soft)] px-3 py-2 text-sm">
              Saved {analyze.data.findings.length} findings.{' '}
              <Link className="font-semibold underline" to={`/findings?run_id=${result.comparison.run_id}`}>Open findings to verify a fix</Link>
            </p>
          )}
          {result.diagnosis.findings.length === 0 ? (
            <p className="text-sm text-muted">No known failure pattern matched the recorded data.</p>
          ) : (
            <div className="space-y-3">
              {result.diagnosis.findings.map((f) => (
                <details key={f.category + (f.step_key ?? '')} className="rounded-md border-[1.5px] border-line p-3 open:border-strong" open={f.severity === 'high'}>
                  <summary className="cursor-pointer list-none">
                    <p className="font-semibold">{f.title}</p>
                    <div className="mt-1.5"><FindingHeader finding={f} /></div>
                  </summary>
                  <div className="mt-3"><FindingBody finding={f} /></div>
                </details>
              ))}
            </div>
          )}
        </Card>
      )}
    </div>
  );
}

export function ComparePage() {
  const [params, setParams] = useSearchParams();
  const projectId = params.get('project_id') ?? '';
  const [baseline, setBaseline] = useState(params.get('baseline') ?? '');
  const [comparison, setComparison] = useState(params.get('comparison') ?? '');
  const projects = useProjects({ page_size: 100 });
  const runs = useRuns({ project_id: projectId || undefined, page_size: 100 });
  const compare = useCompare();
  const items = useMemo(() => runs.data?.items ?? [], [runs.data]);

  const urlBaseline = params.get('baseline');
  const urlComparison = params.get('comparison');
  const { mutate } = compare;
  useEffect(() => {
    if (urlBaseline && urlComparison && urlBaseline !== urlComparison) mutate({ baseline: urlBaseline, comparison: urlComparison });
  }, [urlBaseline, urlComparison, mutate]);

  const commit = (b: string, c: string) => {
    const next = new URLSearchParams(params);
    if (b) next.set('baseline', b); else next.delete('baseline');
    if (c) next.set('comparison', c); else next.delete('comparison');
    setParams(next);
  };

  const suggestBaseline = () => {
    const target = items.find((r) => r.run_id === comparison);
    const candidate = items.find((r) => r.status === 'success' && r.run_id !== comparison && (!target || (r.name === target.name && r.started_at < target.started_at)));
    if (candidate) setBaseline(candidate.run_id);
  };

  return (
    <div className="space-y-6">
      <PageHeader title="Compare Runs" subtitle="Align a known-good baseline with a failing (or fixed) run to find the earliest recorded difference." />
      <Card>
        <form
          className="grid items-end gap-3 lg:grid-cols-[1fr_1fr_auto_1fr_auto]"
          onSubmit={(e) => {
            e.preventDefault();
            if (!baseline || !comparison || baseline === comparison) return;
            // Changing the URL triggers the comparison (see effect above); re-submitting the same pair re-runs it.
            if (baseline === urlBaseline && comparison === urlComparison) compare.mutate({ baseline, comparison });
            else commit(baseline, comparison);
          }}
        >
          <div>
            <label className="label" htmlFor="cmp-project">Project</label>
            <select id="cmp-project" className="input" value={projectId} onChange={(e) => {
              const next = new URLSearchParams(params);
              if (e.target.value) next.set('project_id', e.target.value); else next.delete('project_id');
              setParams(next);
            }}>
              <option value="">All projects</option>
              {projects.data?.items.map((p) => <option key={p.project_id} value={p.project_id}>{p.name}</option>)}
            </select>
          </div>
          <div>
            <label className="label" htmlFor="cmp-baseline">Baseline (known good)</label>
            <select id="cmp-baseline" className="input" value={baseline} onChange={(e) => setBaseline(e.target.value)}>
              <option value="">Select baseline run…</option>
              {items.map((r) => <option key={r.run_id} value={r.run_id}>{runLabel(r)}</option>)}
            </select>
          </div>
          <button type="button" className="btn-ghost h-[38px]" aria-label="Swap runs" onClick={() => { setBaseline(comparison); setComparison(baseline); }}>
            <ArrowLeftRight size={16} />
          </button>
          <div>
            <label className="label" htmlFor="cmp-comparison">Comparison</label>
            <select id="cmp-comparison" className="input" value={comparison} onChange={(e) => setComparison(e.target.value)}>
              <option value="">Select comparison run…</option>
              {items.map((r) => <option key={r.run_id} value={r.run_id}>{runLabel(r)}</option>)}
            </select>
          </div>
          <button type="submit" className="btn-primary h-[38px]" disabled={!baseline || !comparison || baseline === comparison || compare.isPending}>
            <GitCompareArrows size={16} /> {compare.isPending ? 'Comparing…' : 'Compare'}
          </button>
        </form>
        <div className="mt-3 flex flex-wrap items-center gap-3 text-xs text-muted">
          {comparison && !baseline && (
            <button type="button" className="underline" onClick={suggestBaseline}>Use the latest earlier successful run as baseline</button>
          )}
          {baseline && baseline === comparison && <span className="text-danger">Choose two different runs.</span>}
          {runs.isError && <ErrorState error={runs.error} compact />}
        </div>
      </Card>

      {compare.isPending && <Loading label="Comparing runs…" rows={4} />}
      {compare.isError && <ErrorState error={compare.error} onRetry={() => compare.mutate({ baseline, comparison })} />}
      {compare.data && !compare.isPending && <Results result={compare.data} />}
      {!compare.data && !compare.isPending && !compare.isError && (
        <EmptyState
          icon={<GitCompareArrows size={22} />}
          title="Pick two runs"
          description="Choose a successful baseline and the run you want to investigate. RunTrace reports added, missing and changed steps, and the earliest point where behaviour diverged."
        />
      )}
    </div>
  );
}
