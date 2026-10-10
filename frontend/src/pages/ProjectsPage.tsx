import { zodResolver } from '@hookform/resolvers/zod';
import { FolderPlus, Search } from 'lucide-react';
import { useState } from 'react';
import { useForm } from 'react-hook-form';
import { Link, useSearchParams } from 'react-router-dom';
import { z } from 'zod';
import { DemoBadge } from '../components/badges';
import { KeyReveal } from '../components/KeyReveal';
import { Card, EmptyState, ErrorState, Loading, PageHeader, Pagination } from '../components/ui';
import { useCreateProject, useProjects } from '../hooks/queries';
import { formatRelative } from '../lib/format';
import type { ProjectCreated } from '../types/api';

export const projectSchema = z.object({
  name: z.string().trim().min(1, 'Name is required').max(120, 'At most 120 characters'),
  description: z.string().max(2000, 'At most 2000 characters'),
  environment: z.string().trim().max(64, 'At most 64 characters'),
});
type ProjectForm = z.infer<typeof projectSchema>;

function CreateProjectForm({ onCreated, onCancel }: { onCreated: (c: ProjectCreated) => void; onCancel: () => void }) {
  const create = useCreateProject();
  const { register, handleSubmit, formState } = useForm<ProjectForm>({
    resolver: zodResolver(projectSchema),
    defaultValues: { name: '', description: '', environment: '' },
  });
  const submit = handleSubmit((values) => {
    create.mutate(
      { name: values.name, description: values.description, settings: values.environment ? { environment: values.environment } : {} },
      { onSuccess: onCreated },
    );
  });
  return (
    <Card title="New project">
      <form onSubmit={submit} className="grid gap-4 md:grid-cols-2" noValidate>
        <div>
          <label className="label" htmlFor="project-name">Name</label>
          <input id="project-name" className="input" placeholder="Customer Support Assistant" {...register('name')} />
          {formState.errors.name && <p className="mt-1 text-xs text-danger">{formState.errors.name.message}</p>}
        </div>
        <div>
          <label className="label" htmlFor="project-env">Environment (optional)</label>
          <input id="project-env" className="input" placeholder="dev" {...register('environment')} />
        </div>
        <div className="md:col-span-2">
          <label className="label" htmlFor="project-desc">Description</label>
          <textarea id="project-desc" className="input min-h-[72px]" {...register('description')} />
          {formState.errors.description && <p className="mt-1 text-xs text-danger">{formState.errors.description.message}</p>}
        </div>
        {create.isError && <div className="md:col-span-2"><ErrorState error={create.error} compact /></div>}
        <div className="flex gap-2 md:col-span-2">
          <button type="submit" className="btn-primary" disabled={create.isPending}>
            {create.isPending ? 'Creating…' : 'Create project'}
          </button>
          <button type="button" className="btn-ghost" onClick={onCancel}>Cancel</button>
        </div>
      </form>
    </Card>
  );
}

export function ProjectsPage() {
  const [params, setParams] = useSearchParams();
  const [q, setQ] = useState(params.get('q') ?? '');
  const [page, setPage] = useState(1);
  const [created, setCreated] = useState<ProjectCreated | null>(null);
  const showForm = params.get('new') === '1';
  const projects = useProjects({ q: params.get('q') ?? undefined, page, page_size: 24 });

  const setShowForm = (open: boolean) => {
    const next = new URLSearchParams(params);
    if (open) next.set('new', '1');
    else next.delete('new');
    setParams(next, { replace: true });
  };

  return (
    <div className="space-y-6">
      <PageHeader
        title="Projects"
        subtitle="Each project has its own API keys, version history and runs."
        actions={
          !showForm && (
            <button type="button" className="btn-primary" onClick={() => setShowForm(true)}>
              <FolderPlus size={16} /> New project
            </button>
          )
        }
      />

      {created && (
        <div className="space-y-2">
          <p className="text-sm">
            Project <Link className="font-semibold underline" to={`/projects/${created.project.project_id}`}>{created.project.name}</Link> created.
          </p>
          <KeyReveal issued={created.key} onDismiss={() => setCreated(null)} />
        </div>
      )}
      {showForm && (
        <CreateProjectForm
          onCancel={() => setShowForm(false)}
          onCreated={(c) => {
            setCreated(c);
            setShowForm(false);
          }}
        />
      )}

      <form
        role="search"
        className="flex gap-2"
        onSubmit={(e) => {
          e.preventDefault();
          const next = new URLSearchParams(params);
          if (q.trim()) next.set('q', q.trim());
          else next.delete('q');
          setPage(1);
          setParams(next);
        }}
      >
        <div className="relative flex-1">
          <Search size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-muted" />
          <input aria-label="Search projects" className="input pl-9" placeholder="Search by name, description or ID" value={q} onChange={(e) => setQ(e.target.value)} />
        </div>
        <button type="submit" className="btn-secondary">Search</button>
      </form>

      {projects.isLoading && <Loading />}
      {projects.isError && <ErrorState error={projects.error} onRetry={() => projects.refetch()} />}
      {projects.data && projects.data.items.length === 0 && (
        <EmptyState
          title={params.get('q') ? 'No matching projects' : 'No projects yet'}
          description={params.get('q') ? 'Try a different search.' : 'Create your first project to receive an API key.'}
          action={!showForm ? <button type="button" className="btn-primary" onClick={() => setShowForm(true)}>Create project</button> : undefined}
        />
      )}
      {projects.data && projects.data.items.length > 0 && (
        <>
          <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
            {projects.data.items.map((p) => (
              <Link key={p.project_id} to={`/projects/${p.project_id}`} className="card-strong flex flex-col gap-3 p-4 transition-colors hover:bg-soft">
                <div className="flex items-start justify-between gap-2">
                  <h2 className="truncate text-2xl">{p.name}</h2>
                  {p.is_demo && <DemoBadge />}
                </div>
                <p className="line-clamp-2 min-h-[2.5rem] text-sm text-muted">{p.description || 'No description'}</p>
                <div className="grid grid-cols-3 divide-x divide-line rounded-md border border-line text-center">
                  <div className="py-2"><p className="metric text-2xl">{p.stats?.total_runs ?? 0}</p><p className="text-[11px] text-muted">Runs</p></div>
                  <div className="py-2"><p className="metric text-2xl text-success">{p.stats?.success_runs ?? 0}</p><p className="text-[11px] text-muted">Success</p></div>
                  <div className="py-2"><p className="metric text-2xl text-danger">{p.stats?.failed_runs ?? 0}</p><p className="text-[11px] text-muted">Failed</p></div>
                </div>
                <p className="mono-id">{p.project_id} · last run {formatRelative(p.stats?.last_run_at)}</p>
              </Link>
            ))}
          </div>
          <Pagination meta={projects.data.meta} onPage={setPage} />
        </>
      )}
    </div>
  );
}
