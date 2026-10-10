import type { ReactNode } from 'react';
import { cn } from '../lib/cn';
import { humanize } from '../lib/format';

const tones = {
  success: 'border-success text-success bg-[var(--success-soft)]',
  danger: 'border-danger text-danger bg-[var(--danger-soft)]',
  warning: 'border-warning text-warning bg-[var(--warning-soft)]',
  accent: 'border-strong text-accent-fg bg-accent',
  neutral: 'border-line text-muted bg-card',
  info: 'border-info text-info bg-card',
} as const;

type Tone = keyof typeof tones;

export function Badge({ tone = 'neutral', children, className, title }: { tone?: Tone; children: ReactNode; className?: string; title?: string }) {
  return (
    <span title={title} className={cn('chip', tones[tone], className)}>
      {children}
    </span>
  );
}

const statusTone: Record<string, Tone> = {
  success: 'success', failed: 'danger', timed_out: 'warning', running: 'info', info: 'neutral', skipped: 'neutral',
};

export function StatusBadge({ status }: { status: string }) {
  return <Badge tone={statusTone[status] ?? 'neutral'}>{humanize(status)}</Badge>;
}

const severityTone: Record<string, Tone> = { high: 'danger', medium: 'warning', low: 'neutral' };

export function SeverityBadge({ severity }: { severity: string }) {
  return <Badge tone={severityTone[severity] ?? 'neutral'}>{severity}</Badge>;
}

export function ConfidenceBadge({ confidence }: { confidence: string }) {
  return <Badge tone="neutral" title="How strongly the recorded evidence supports this pattern">{confidence} confidence</Badge>;
}

const verificationTone: Record<string, Tone> = { verified: 'success', not_improved: 'danger', inconclusive: 'warning', unverified: 'neutral' };

export function VerificationBadge({ status }: { status: string }) {
  return <Badge tone={verificationTone[status] ?? 'neutral'}>{humanize(status)}</Badge>;
}

export function DemoBadge() {
  return <Badge tone="accent" title="Seeded demonstration data, not SDK-ingested">Demo</Badge>;
}

const kindTone: Record<string, Tone> = { unchanged: 'neutral', changed: 'warning', added: 'info', missing: 'danger' };

export function KindBadge({ kind }: { kind: string }) {
  return <Badge tone={kindTone[kind] ?? 'neutral'}>{kind}</Badge>;
}
