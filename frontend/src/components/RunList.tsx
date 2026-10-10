import { ChevronRight } from 'lucide-react';
import { Link } from 'react-router-dom';
import { formatDuration, formatRelative } from '../lib/format';
import type { Run } from '../types/api';
import { DemoBadge, StatusBadge } from './badges';

/** Run cards with the reference's route marker (accent square → dashed line → black square). */
export function RunList({ runs, showProject = true }: { runs: Run[]; showProject?: boolean }) {
  return (
    <ul className="space-y-2.5">
      {runs.map((run) => (
        <li key={run.run_id}>
          <Link
            to={`/runs/${run.run_id}`}
            className="flex items-center gap-3 rounded-md border-[1.5px] border-strong bg-card px-3 py-2.5 transition-colors hover:bg-soft"
          >
            <span aria-hidden="true" className="flex h-11 flex-col items-center justify-between py-0.5">
              <span className={run.status === 'failed' || run.status === 'timed_out' ? 'h-2.5 w-2.5 bg-danger' : 'h-2.5 w-2.5 bg-accent'} />
              <span className="w-px flex-1 border-l-[1.5px] border-dashed border-strong" />
              <span className="h-2.5 w-2.5 bg-fg" />
            </span>
            <span className="min-w-0 flex-1">
              <span className="flex items-center gap-2">
                <span className="truncate font-semibold">{run.name}</span>
                {run.is_demo && <DemoBadge />}
              </span>
              <span className="block truncate text-xs text-muted">
                {showProject && run.project_name ? `${run.project_name} · ` : ''}
                {run.version ? `v${run.version} · ` : ''}
                {run.event_count} events · {formatRelative(run.started_at)}
              </span>
            </span>
            <span className="flex flex-col items-end gap-1">
              <StatusBadge status={run.status} />
              <span className="font-mono text-xs text-muted">{formatDuration(run.duration_ms)}</span>
            </span>
            <ChevronRight size={18} className="text-muted" />
          </Link>
        </li>
      ))}
    </ul>
  );
}
