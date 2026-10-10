import { cn } from '../lib/cn';

/** Two offset squares (black + yellow): the RunTrace mark, echoing the "baseline vs comparison" idea. */
export function LogoMark({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 32 32" aria-hidden="true" className={cn('h-7 w-7 shrink-0', className)}>
      <rect x="3" y="3" width="15" height="15" fill="var(--fg)" />
      <rect x="14" y="14" width="15" height="15" fill="var(--accent)" />
    </svg>
  );
}

export function Logo({ compact = false }: { compact?: boolean }) {
  return (
    <span className="flex items-center gap-2.5">
      <LogoMark />
      {!compact && (
        <span className="font-display text-2xl font-extrabold uppercase leading-none tracking-wide">
          Run<span className="text-fg">Trace</span>
        </span>
      )}
    </span>
  );
}

/** Small decorative squares used beside page titles, as in the visual reference. */
export function CornerMark() {
  return (
    <span aria-hidden="true" className="relative inline-block h-8 w-8 shrink-0">
      <span className="absolute left-0 top-0 h-4 w-4 bg-fg" />
      <span className="absolute bottom-0 right-0 h-4 w-4 bg-accent" />
    </span>
  );
}
