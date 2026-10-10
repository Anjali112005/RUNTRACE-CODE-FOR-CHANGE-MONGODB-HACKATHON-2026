import { Search, X } from 'lucide-react';
import { useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { DemoBadge, SeverityBadge, VerificationBadge } from '../components/badges';
import { AIPanel, FindingBody, FindingHeader, VerifyPanel } from '../components/FindingView';
import { Card, EmptyState, ErrorState, Loading, PageHeader, Pagination } from '../components/ui';
import { useFinding, useFindings, useProjects } from '../hooks/queries';
import { cn } from '../lib/cn';
import { formatRelative, humanize, shortId } from '../lib/format';

const CATEGORIES = ['', 'divergence', 'invalid_json', 'schema_change', 'missing_field', 'missing_module', 'missing_env_var',
  'config_mismatch', 'external_timeout', 'http_failure', 'tool_failure', 'null_output', 'step_failure', 'timing_change'];

export function FindingsPage() {
  const [params, setParams] = useSearchParams();
  const [q, setQ] = useState(params.get('q') ?? '');
  const filters = {
    project_id: params.get('project_id') ?? undefined,
    run_id: params.get('run_id') ?? undefined,
    severity: params.get('severity') ?? undefined,
    category: params.get('category') ?? undefined,
    verification_status: params.get('verification_status') ?? undefined,
    q: params.get('q') ?? undefined,
    page: Number(params.get('page') ?? '1') || 1,
    page_size: 20,
  };
  const findings = useFindings(filters);
  const projects = useProjects({ page_size: 100 });
  const selectedId = params.get('selected');
  const inList = findings.data?.items.find((f) => f.finding_id === selectedId);
  const single = useFinding(inList ? null : selectedId); // selected item may be outside the current page/filters
  const selected = inList ?? single.data ?? null;

  const update = (key: string, value: string | null) => {
    const next = new URLSearchParams(params);
    if (value) next.set(key, value);
    else next.delete(key);
    if (key !== 'page' && key !== 'selected') next.delete('page');
    setParams(next);
  };

  return (
    <div className="space-y-6">
      <PageHeader
        title="Findings"
        subtitle="Each finding separates what was recorded (observation, evidence) from what might explain it (hypothesis). Verify fixes against later runs."
      />
      <Card>
        <div className="grid gap-3 md:grid-cols-6">
          <form role="search" className="relative md:col-span-2" onSubmit={(e) => { e.preventDefault(); update('q', q.trim() || null); }}>
            <Search size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-muted" />
            <input aria-label="Search findings" className="input pl-9" placeholder="Title, summary or step — Enter" value={q} onChange={(e) => setQ(e.target.value)} />
          </form>
          <select aria-label="Project" className="input" value={filters.project_id ?? ''} onChange={(e) => update('project_id', e.target.value || null)}>
            <option value="">All projects</option>
            {projects.data?.items.map((p) => <option key={p.project_id} value={p.project_id}>{p.name}</option>)}
          </select>
          <select aria-label="Severity" className="input" value={filters.severity ?? ''} onChange={(e) => update('severity', e.target.value || null)}>
            <option value="">Any severity</option>
            <option value="high">High</option>
            <option value="medium">Medium</option>
            <option value="low">Low</option>
          </select>
          <select aria-label="Category" className="input" value={filters.category ?? ''} onChange={(e) => update('category', e.target.value || null)}>
            {CATEGORIES.map((c) => <option key={c} value={c}>{c ? humanize(c) : 'Any category'}</option>)}
          </select>
          <select aria-label="Verification" className="input" value={filters.verification_status ?? ''} onChange={(e) => update('verification_status', e.target.value || null)}>
            <option value="">Any verification</option>
            <option value="unverified">Unverified</option>
            <option value="verified">Verified</option>
            <option value="not_improved">Not improved</option>
            <option value="inconclusive">Inconclusive</option>
          </select>
        </div>
        {filters.run_id && (
          <p className="mt-3 flex items-center gap-2 text-sm">
            Run <Link className="font-mono underline" to={`/runs/${filters.run_id}`}>{shortId(filters.run_id)}</Link>
            <button type="button" aria-label="Clear run filter" className="btn-ghost px-1.5 py-0.5" onClick={() => update('run_id', null)}><X size={12} /></button>
          </p>
        )}
      </Card>

      {findings.isLoading && <Loading rows={5} />}
      {findings.isError && <ErrorState error={findings.error} onRetry={() => findings.refetch()} />}
      {findings.data && findings.data.items.length === 0 && (
        <EmptyState title="No findings" description="Open a failed run and click Analyze, or save hypotheses from the Compare Runs page." />
      )}
      {findings.data && findings.data.items.length > 0 && (
        <div className="grid gap-6 lg:grid-cols-5">
          <div className="lg:col-span-2">
            <ul className="space-y-2.5">
              {findings.data.items.map((f) => (
                <li key={f.finding_id}>
                  <button
                    type="button"
                    onClick={() => update('selected', f.finding_id)}
                    className={cn('w-full rounded-md border-[1.5px] bg-card p-3 text-left transition-colors hover:bg-soft',
                      f.finding_id === selectedId ? 'border-strong ring-2 ring-[var(--accent)]' : 'border-line')}
                  >
                    <div className="flex items-center gap-2">
                      <SeverityBadge severity={f.severity} />
                      <span className="flex-1 truncate font-semibold">{f.title}</span>
                      {f.is_demo && <DemoBadge />}
                    </div>
                    <div className="mt-1.5 flex items-center gap-2 text-xs text-muted">
                      <span>{humanize(f.category)}</span>·<span>{formatRelative(f.created_at)}</span>
                      <span className="ml-auto"><VerificationBadge status={f.verification_status} /></span>
                    </div>
                  </button>
                </li>
              ))}
            </ul>
            <Pagination meta={findings.data.meta} onPage={(p) => update('page', String(p))} />
          </div>
          <div className="lg:col-span-3">
            {selected ? (
              <Card title={selected.title}>
                <div className="space-y-4">
                  <FindingHeader finding={selected} />
                  <p className="mono-id">
                    run <Link className="underline" to={`/runs/${selected.run_id}`}>{shortId(selected.run_id)}</Link>
                    {selected.baseline_run_id && (
                      <> · baseline <Link className="underline" to={`/runs/${selected.baseline_run_id}`}>{shortId(selected.baseline_run_id)}</Link>
                        {' · '}<Link className="underline" to={`/compare?baseline=${selected.baseline_run_id}&comparison=${selected.run_id}`}>compare</Link></>
                    )}
                  </p>
                  <FindingBody finding={selected} />
                  <VerifyPanel finding={selected} />
                  <AIPanel findingId={selected.finding_id} />
                </div>
              </Card>
            ) : (
              <EmptyState title="Select a finding" description="Choose a finding to see its evidence, hypothesis, regression test and verification." />
            )}
          </div>
        </div>
      )}
    </div>
  );
}
