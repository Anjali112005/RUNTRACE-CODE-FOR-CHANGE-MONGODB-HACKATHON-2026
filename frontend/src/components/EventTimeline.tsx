import { ChevronDown, ChevronRight } from 'lucide-react';
import { useState } from 'react';
import { cn } from '../lib/cn';
import { formatDuration } from '../lib/format';
import type { RunEvent } from '../types/api';
import { StatusBadge } from './badges';
import { JsonView } from './ui';

function EventRow({ event, defaultOpen }: { event: RunEvent; defaultOpen: boolean }) {
  const [open, setOpen] = useState(defaultOpen);
  const failed = event.status === 'failed';
  return (
    <li className="relative pl-8">
      <span aria-hidden="true" className={cn('absolute left-[7px] top-3 h-3 w-3 border-[1.5px] border-strong', failed ? 'bg-danger' : 'bg-accent')} />
      <div className={cn('rounded-md border-[1.5px] bg-card', failed ? 'border-danger' : 'border-line')}>
        <button
          type="button"
          onClick={() => setOpen((o) => !o)}
          aria-expanded={open}
          className="flex w-full items-center gap-3 px-3 py-2 text-left hover:bg-soft"
        >
          {open ? <ChevronDown size={16} /> : <ChevronRight size={16} />}
          <span className="font-mono text-xs text-muted">#{event.sequence}</span>
          <span className="flex-1 truncate font-semibold">{event.name}</span>
          <span className="hidden font-mono text-xs text-muted sm:inline">{event.event_type}</span>
          <span className="w-16 text-right font-mono text-xs text-muted">{formatDuration(event.duration_ms)}</span>
          <StatusBadge status={event.status} />
        </button>
        {open && (
          <div className="grid gap-3 border-t border-line p-3 md:grid-cols-2">
            {event.error && (
              <div className="md:col-span-2">
                <p className="label text-danger">Error</p>
                <p className="mb-1 font-mono text-sm text-danger">
                  {event.error.type}: {event.error.message}
                </p>
                {event.error.traceback && <JsonView value={event.error.traceback} />}
              </div>
            )}
            <div>
              <p className="label">Input</p>
              <JsonView value={event.input_summary} />
            </div>
            <div>
              <p className="label">Output</p>
              <JsonView value={event.output_summary} />
            </div>
            {Object.keys(event.metadata ?? {}).length > 0 && (
              <div className="md:col-span-2">
                <p className="label">Metadata</p>
                <JsonView value={event.metadata} />
              </div>
            )}
            <p className="mono-id md:col-span-2">
              {event.event_id} · {event.timestamp}
            </p>
          </div>
        )}
      </div>
    </li>
  );
}

export function EventTimeline({ events }: { events: RunEvent[] }) {
  const firstFailure = events.find((e) => e.status === 'failed')?.event_id;
  return (
    <ol className="relative space-y-2 before:absolute before:bottom-3 before:left-[12px] before:top-3 before:border-l-[1.5px] before:border-dashed before:border-strong">
      {events.map((event) => (
        <EventRow key={event.event_id} event={event} defaultOpen={event.event_id === firstFailure} />
      ))}
    </ol>
  );
}
