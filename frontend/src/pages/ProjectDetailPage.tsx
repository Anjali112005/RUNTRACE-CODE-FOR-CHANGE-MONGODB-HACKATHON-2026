import { BarChart3, KeyRound, Pencil, RotateCw, Tag } from 'lucide-react';
import { useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { DemoBadge, StatusBadge } from '../components/badges';
import { KeyReveal } from '../components/KeyReveal';
import { RunList } from '../components/RunList';
import { Card, EmptyState, ErrorState, KeyValue, Loading, PageHeader } from '../components/ui';
import { useCreateVersion, useProject, useRevokeKey, useRotateKey, useRuns, useUpdateProject } from '../hooks/queries';
import { formatDateTime, formatRelative } from '../lib/format';
import type { KeyIssued, Project } from '../types/api';

function EditProject({ project, onDone }: { project: Project; onDone: () => void }) {
  const update = useUpdateProject(project.project_id);
  const [name, setName] = useState(project.name);
  const [description, setDescription] = useState(project.description);
  return (
    <form
      className="space-y-3"
      onSubmit={(e) => {
        e.preventDefault();
        if (!name.trim()) return;
        update.mutate({ name: name.trim(), description }, { onSuccess: onDone });
      }}
    >
      <div>
        <label className="label" htmlFor="edit-name">Name</label>
        <input id="edit-name" className="input" value={name} maxLength={120} onChange={(e) => setName(e.target.value)} />
      </div>
      <div>
        <label className="label" htmlFor="edit-desc">Description</label>
        <textarea id="edit-desc" className="input" value={description} maxLength={2000} onChange={(e) => setDescription(e.target.value)} />
      </div>
      {update.isError && <ErrorState error={update.error} compact />}
      <div className="flex gap-2">
        <button type="submit" className="btn-primary" disabled={update.isPending || !name.trim()}>Save</button>
        <button type="button" className="btn-ghost" onClick={onDone}>Cancel</button>
      </div>
    </form>
  );
}

export function ProjectDetailPage() {
  const { projectId = '' } = useParams();
  const detail = useProject(projectId);
  const runs = useRuns({ project_id: projectId, page_size: 8 });
  const rotate = useRotateKey(projectId);
  const revoke = useRevokeKey(projectId);
  const addVersion = useCreateVersion(projectId);
  const [issued, setIssued] = useState<KeyIssued | null>(null);
  const [editing, setEditing] = useState(false);
  const [version, setVersion] = useState('');

  if (detail.isLoading) return <Loading />;
  if (detail.isError) return <ErrorState error={detail.error} onRetry={() => detail.refetch()} />;
  if (!detail.data) return null;
  const { project, keys, versions } = detail.data;

  return (
    <div className="space-y-6">
      <PageHeader
        title={project.name}
        subtitle={project.description || 'No description'}
        actions={
          <>
            {project.is_demo && <DemoBadge />}
            <Link to={`/metrics?project_id=${project.project_id}`} className="btn-ghost"><BarChart3 size={16} /> Metrics</Link>
            <button type="button" className="btn-ghost" onClick={() => setEditing((e) => !e)}><Pencil size={16} /> Edit</button>
          </>
        }
      />

      {editing && <Card title="Edit project"><EditProject project={project} onDone={() => setEditing(false)} /></Card>}
      {issued && <KeyReveal issued={issued} onDismiss={() => setIssued(null)} />}

      <Card>
        <dl className="grid grid-cols-2 gap-4 md:grid-cols-4">
          <KeyValue label="Project ID"><span className="font-mono text-xs">{project.project_id}</span></KeyValue>
          <KeyValue label="Created">{formatDateTime(project.created_at)}</KeyValue>
          <KeyValue label="Environment">{String(project.settings?.environment ?? '—')}</KeyValue>
          <KeyValue label="Runs">{project.stats?.total_runs ?? 0} ({project.stats?.failed_runs ?? 0} failed)</KeyValue>
        </dl>
      </Card>

      <div className="grid gap-6 lg:grid-cols-2">
        <Card
          title={<span className="flex items-center gap-2"><KeyRound size={18} /> API keys</span>}
          actions={
            <button
              type="button"
              className="btn-primary py-1.5"
              disabled={rotate.isPending}
              onClick={() => {
                if (window.confirm('Issue a new key and revoke all existing active keys? Apps using the old key will stop sending data.')) {
                  rotate.mutate(true, { onSuccess: setIssued });
                }
              }}
            >
              <RotateCw size={14} /> Rotate
            </button>
          }
        >
          {rotate.isError && <ErrorState error={rotate.error} compact />}
          {revoke.isError && <ErrorState error={revoke.error} compact />}
          <p className="mb-3 text-xs text-muted">Only key prefixes are shown. Full keys are displayed once, when issued.</p>
          <div className="overflow-x-auto">
            <table className="table-compact">
              <thead>
                <tr><th>Prefix</th><th>Created</th><th>Last used</th><th>Status</th><th /></tr>
              </thead>
              <tbody>
                {keys.map((k) => (
                  <tr key={k.key_id}>
                    <td className="font-mono text-xs">{k.prefix}…</td>
                    <td>{formatRelative(k.created_at)}</td>
                    <td>{formatRelative(k.last_used_at)}</td>
                    <td><StatusBadge status={k.active ? 'success' : 'failed'} /></td>
                    <td className="text-right">
                      {k.active && (
                        <button
                          type="button"
                          className="btn-danger px-2 py-1 text-xs"
                          disabled={revoke.isPending}
                          onClick={() => window.confirm(`Revoke key ${k.prefix}…? This cannot be undone.`) && revoke.mutate(k.key_id)}
                        >
                          Revoke
                        </button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>

        <Card title={<span className="flex items-center gap-2"><Tag size={18} /> Versions</span>}>
          <form
            className="mb-3 flex gap-2"
            onSubmit={(e) => {
              e.preventDefault();
              if (version.trim()) addVersion.mutate(version.trim(), { onSuccess: () => setVersion('') });
            }}
          >
            <input aria-label="New version" className="input" placeholder="e.g. 1.3.0" value={version} onChange={(e) => setVersion(e.target.value)} />
            <button type="submit" className="btn-secondary" disabled={!version.trim() || addVersion.isPending}>Add</button>
          </form>
          {addVersion.isError && <ErrorState error={addVersion.error} compact />}
          {versions.length === 0 ? (
            <p className="text-sm text-muted">No versions yet. Runs started with a version (SDK: RUNTRACE_VERSION) register it automatically.</p>
          ) : (
            <table className="table-compact">
              <thead><tr><th>Version</th><th>Runs</th><th>Registered</th></tr></thead>
              <tbody>
                {versions.map((v) => (
                  <tr key={v.version_id}>
                    <td className="font-mono">
                      <Link className="underline decoration-dotted" to={`/runs?project_id=${project.project_id}&version=${encodeURIComponent(v.version)}`}>{v.version}</Link>
                    </td>
                    <td>{v.run_count ?? 0}</td>
                    <td>{formatRelative(v.created_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </Card>
      </div>

      <Card title="Recent runs" actions={<Link to={`/runs?project_id=${project.project_id}`} className="text-sm font-semibold text-[var(--warning)] hover:underline">View all</Link>}>
        {runs.isError && <ErrorState error={runs.error} onRetry={() => runs.refetch()} />}
        {runs.isLoading && <Loading />}
        {runs.data && runs.data.items.length === 0 && (
          <EmptyState title="No runs yet" description={<>Set <code>RUNTRACE_API_KEY</code> and run your instrumented app. See <Link className="underline" to="/integration">SDK &amp; Integration</Link>.</>} />
        )}
        {runs.data && runs.data.items.length > 0 && <RunList runs={runs.data.items} showProject={false} />}
      </Card>
    </div>
  );
}
