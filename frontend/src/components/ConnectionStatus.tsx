import { useHealth } from '../hooks/queries';
import { cn } from '../lib/cn';

export function ConnectionStatus() {
  const health = useHealth();
  let tone = 'bg-muted';
  let label = 'Checking API…';
  let detail = '';
  if (health.isError) {
    tone = 'bg-danger';
    label = 'API offline';
    detail = health.error instanceof Error ? health.error.message : '';
  } else if (health.data) {
    if (health.data.database.connected) {
      tone = 'bg-success';
      label = 'Connected';
      detail = `MongoDB "${health.data.database.name}" · ${health.data.database.latency_ms ?? '?'} ms`;
    } else {
      tone = 'bg-warning';
      label = 'Database unavailable';
      detail = health.data.database.error ?? '';
    }
  }
  return (
    <span
      title={detail}
      data-testid="connection-status"
      className="inline-flex items-center gap-2 rounded-md border-[1.5px] border-line bg-card px-2.5 py-1 text-xs font-semibold"
    >
      <span className={cn('h-2 w-2 rounded-full', tone)} aria-hidden="true" />
      {label}
    </span>
  );
}
