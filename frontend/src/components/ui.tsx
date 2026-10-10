import { ArrowRight, Check, Copy, Inbox, Loader2, RefreshCw, TriangleAlert } from 'lucide-react';
import { useState, type ReactNode } from 'react';
import { Link } from 'react-router-dom';
import { ApiError } from '../api/client';
import { cn } from '../lib/cn';
import { toJson } from '../lib/format';
import type { PageMeta } from '../types/api';
import { CornerMark } from './Logo';

export function PageHeader({ title, subtitle, actions }: { title: string; subtitle?: ReactNode; actions?: ReactNode }) {
  return (
    <div className="mb-6 flex flex-wrap items-start justify-between gap-4">
      <div className="flex items-start gap-4">
        <div>
          <h1 className="text-4xl leading-none sm:text-5xl">{title}</h1>
          {subtitle && <p className="mt-2 max-w-2xl text-sm text-muted">{subtitle}</p>}
        </div>
      </div>
      <div className="flex items-center gap-3">
        {actions}
        <CornerMark />
      </div>
    </div>
  );
}

export function Card({ title, actions, children, className, bodyClassName }: {
  title?: ReactNode;
  actions?: ReactNode;
  children: ReactNode;
  className?: string;
  bodyClassName?: string;
}) {
  return (
    <section className={cn('card shadow-card', className)}>
      {(title || actions) && (
        <header className="flex items-center justify-between gap-3 border-b border-line px-4 py-3">
          {title && <h2 className="section-title">{title}</h2>}
          {actions}
        </header>
      )}
      <div className={cn('p-4', bodyClassName)}>{children}</div>
    </section>
  );
}

export interface StatItem {
  icon: ReactNode;
  value: ReactNode;
  label: string;
}

/** Bordered stat strip with dividers (the "32 / 18.5 km / 12h 45m" pattern from the reference). */
export function StatStrip({ items }: { items: StatItem[] }) {
  return (
    <div className="card-strong grid grid-cols-2 divide-line sm:grid-cols-4 sm:divide-x">
      {items.map((item, i) => (
        <div key={item.label} className={cn('flex flex-col items-center gap-1.5 px-3 py-4 text-center', i < 2 && 'border-b border-line sm:border-b-0')}>
          <span className="text-fg">{item.icon}</span>
          <span className="metric">{item.value}</span>
          <span className="text-xs text-muted">{item.label}</span>
        </div>
      ))}
    </div>
  );
}

/** Primary call-to-action: yellow block with a black arrow box, as in the reference. */
export function ArrowCta({ to, onClick, children, className }: { to?: string; onClick?: () => void; children: ReactNode; className?: string }) {
  const inner = (
    <>
      <span className="flex-1 px-4 py-3 text-center font-display text-lg font-bold uppercase tracking-wide">{children}</span>
      <span className="flex items-center self-stretch bg-inverse px-4 text-inverse-fg">
        <ArrowRight size={20} />
      </span>
    </>
  );
  const classes = cn('flex w-full items-stretch overflow-hidden rounded-md border-[1.5px] border-strong bg-accent text-accent-fg transition-colors hover:bg-accent-hover', className);
  return to ? (
    <Link to={to} className={classes}>
      {inner}
    </Link>
  ) : (
    <button type="button" onClick={onClick} className={classes}>
      {inner}
    </button>
  );
}

export function EmptyState({ title, description, action, icon }: { title: string; description?: ReactNode; action?: ReactNode; icon?: ReactNode }) {
  return (
    <div className="flex flex-col items-center gap-3 rounded-md border-[1.5px] border-dashed border-line px-6 py-10 text-center">
      <span className="flex h-12 w-12 items-center justify-center rounded-full bg-accent text-accent-fg">{icon ?? <Inbox size={22} />}</span>
      <h3 className="text-xl">{title}</h3>
      {description && <div className="max-w-md text-sm text-muted">{description}</div>}
      {action}
    </div>
  );
}

export function Loading({ label = 'Loading…', rows = 3 }: { label?: string; rows?: number }) {
  return (
    <div role="status" aria-busy="true" className="space-y-2">
      <span className="flex items-center gap-2 text-sm text-muted">
        <Loader2 size={16} className="animate-spin" /> {label}
      </span>
      {Array.from({ length: rows }).map((_, i) => (
        <div key={i} className="h-10 animate-pulse rounded-md bg-soft" />
      ))}
    </div>
  );
}

function errorHint(error: unknown): string | null {
  if (!(error instanceof ApiError)) return null;
  if (error.status === 0) return 'Start the backend (python -m app) and check VITE_API_BASE_URL and RUNTRACE_CORS_ORIGINS.';
  if (error.code === 'database_unavailable') return 'MongoDB is not reachable. Check RUNTRACE_MONGODB_URI and that MongoDB is running.';
  if (error.status === 401) return 'This server requires an admin token. Enter it on the Settings page.';
  return null;
}

export function ErrorState({ error, onRetry, compact = false }: { error: unknown; onRetry?: () => void; compact?: boolean }) {
  const message = error instanceof Error ? error.message : 'Something went wrong.';
  const hint = errorHint(error);
  return (
    <div role="alert" className={cn('rounded-md border-[1.5px] border-danger bg-[var(--danger-soft)] text-sm', compact ? 'px-3 py-2' : 'p-4')}>
      <div className="flex items-start gap-2">
        <TriangleAlert size={18} className="mt-0.5 shrink-0 text-danger" />
        <div className="flex-1">
          <p className="font-semibold text-fg">{message}</p>
          {hint && <p className="mt-1 text-muted">{hint}</p>}
          {error instanceof ApiError && error.code && <p className="mono-id mt-1">code: {error.code}</p>}
        </div>
        {onRetry && (
          <button type="button" className="btn-ghost px-2 py-1 text-xs" onClick={onRetry}>
            <RefreshCw size={14} /> Retry
          </button>
        )}
      </div>
    </div>
  );
}

export function Pagination({ meta, onPage }: { meta: PageMeta; onPage: (page: number) => void }) {
  if (meta.pages <= 1) return <p className="mt-3 text-xs text-muted">{meta.total} total</p>;
  return (
    <div className="mt-3 flex items-center justify-between text-sm">
      <span className="text-muted">
        Page {meta.page} of {meta.pages} · {meta.total} total
      </span>
      <div className="flex gap-2">
        <button type="button" className="btn-ghost py-1" disabled={meta.page <= 1} onClick={() => onPage(meta.page - 1)}>
          Previous
        </button>
        <button type="button" className="btn-ghost py-1" disabled={meta.page >= meta.pages} onClick={() => onPage(meta.page + 1)}>
          Next
        </button>
      </div>
    </div>
  );
}

export function CopyButton({ text, label = 'Copy', className }: { text: string; label?: string; className?: string }) {
  const [copied, setCopied] = useState(false);
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(text);
    } catch {
      const area = document.createElement('textarea');
      area.value = text;
      document.body.appendChild(area);
      area.select();
      document.execCommand('copy');
      area.remove();
    }
    setCopied(true);
    window.setTimeout(() => setCopied(false), 1500);
  };
  return (
    <button type="button" onClick={copy} className={cn('btn-ghost px-2 py-1 text-xs', className)} aria-label={`${label} to clipboard`}>
      {copied ? <Check size={14} className="text-success" /> : <Copy size={14} />} {copied ? 'Copied' : label}
    </button>
  );
}

export function CodeBlock({ code, label }: { code: string; label?: string }) {
  return (
    <div className="overflow-hidden rounded-md border-[1.5px] border-strong">
      <div className="flex items-center justify-between bg-inverse px-3 py-1.5 text-inverse-fg">
        <span className="font-mono text-xs uppercase tracking-wider">{label ?? 'code'}</span>
        <CopyButton text={code} className="border-transparent bg-transparent text-inverse-fg hover:border-[var(--accent)]" />
      </div>
      <pre className="max-h-96 overflow-auto bg-card p-3 text-xs leading-relaxed">
        <code>{code}</code>
      </pre>
    </div>
  );
}

export function JsonView({ value, empty = 'null', className }: { value: unknown; empty?: string; className?: string }) {
  const text = value === null || value === undefined ? empty : toJson(value);
  return <pre className={cn('max-h-72 overflow-auto whitespace-pre-wrap break-words rounded-md border border-line bg-soft p-2.5 text-xs', className)}>{text}</pre>;
}

export function KeyValue({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="min-w-0">
      <dt className="label">{label}</dt>
      <dd className="truncate text-sm">{children}</dd>
    </div>
  );
}
