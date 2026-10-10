import {
  Activity,
  BarChart3,
  ChevronRight,
  FolderKanban,
  GitCompareArrows,
  LayoutDashboard,
  Menu,
  Moon,
  Plug,
  SearchCheck,
  Settings,
  Sun,
  X,
} from 'lucide-react';
import { useEffect, useState, type ReactNode } from 'react';
import { Link, NavLink, Outlet, useLocation } from 'react-router-dom';
import { ConnectionStatus } from '../components/ConnectionStatus';
import { Logo } from '../components/Logo';
import { useTheme } from '../contexts/ThemeContext';
import { cn } from '../lib/cn';
import { shortId } from '../lib/format';

export const NAV_ITEMS: { to: string; label: string; icon: ReactNode }[] = [
  { to: '/', label: 'Overview', icon: <LayoutDashboard size={18} /> },
  { to: '/projects', label: 'Projects', icon: <FolderKanban size={18} /> },
  { to: '/runs', label: 'Runs', icon: <Activity size={18} /> },
  { to: '/compare', label: 'Compare Runs', icon: <GitCompareArrows size={18} /> },
  { to: '/findings', label: 'Findings', icon: <SearchCheck size={18} /> },
  { to: '/metrics', label: 'Metrics', icon: <BarChart3 size={18} /> },
  { to: '/integration', label: 'SDK & Integration', icon: <Plug size={18} /> },
  { to: '/settings', label: 'Settings', icon: <Settings size={18} /> },
];

const SEGMENT_LABELS: Record<string, string> = {
  projects: 'Projects', runs: 'Runs', compare: 'Compare Runs', findings: 'Findings', metrics: 'Metrics',
  integration: 'SDK & Integration', settings: 'Settings',
};

function Breadcrumbs() {
  const { pathname } = useLocation();
  const segments = pathname.split('/').filter(Boolean);
  const crumbs = [{ to: '/', label: 'Overview' }];
  segments.forEach((seg, i) => {
    crumbs.push({ to: '/' + segments.slice(0, i + 1).join('/'), label: SEGMENT_LABELS[seg] ?? shortId(seg) });
  });
  return (
    <nav aria-label="Breadcrumb" className="min-w-0">
      <ol className="flex items-center gap-1 overflow-hidden text-xs text-muted">
        {crumbs.map((c, i) => (
          <li key={c.to} className="flex min-w-0 items-center gap-1">
            {i > 0 && <ChevronRight size={12} className="shrink-0" />}
            {i === crumbs.length - 1 ? (
              <span aria-current="page" className="truncate font-semibold text-fg">{c.label}</span>
            ) : (
              <Link to={c.to} className="truncate hover:text-fg">{c.label}</Link>
            )}
          </li>
        ))}
      </ol>
    </nav>
  );
}

function NavLinks({ onNavigate }: { onNavigate?: () => void }) {
  return (
    <ul className="space-y-1">
      {NAV_ITEMS.map((item) => (
        <li key={item.to}>
          <NavLink
            to={item.to}
            end={item.to === '/'}
            onClick={onNavigate}
            className={({ isActive }) =>
              cn(
                'flex items-center gap-3 rounded-md border-[1.5px] px-3 py-2 text-sm font-semibold transition-colors',
                isActive ? 'border-strong bg-accent text-accent-fg' : 'border-transparent text-fg hover:border-line hover:bg-soft',
              )
            }
          >
            {item.icon}
            {item.label}
          </NavLink>
        </li>
      ))}
    </ul>
  );
}

function ThemeToggle() {
  const { theme, toggleTheme } = useTheme();
  return (
    <button
      type="button"
      onClick={toggleTheme}
      className="btn-ghost px-2.5 py-1.5"
      aria-label={theme === 'dark' ? 'Switch to light theme' : 'Switch to dark theme'}
      title="Toggle theme"
    >
      {theme === 'dark' ? <Sun size={16} /> : <Moon size={16} />}
    </button>
  );
}

export function AppLayout() {
  const [drawerOpen, setDrawerOpen] = useState(false);
  const location = useLocation();
  useEffect(() => setDrawerOpen(false), [location.pathname]);

  return (
    <div className="flex min-h-screen bg-soft">
      <aside className="sticky top-0 hidden h-screen w-64 shrink-0 flex-col border-r-[1.5px] border-strong bg-card lg:flex">
        <div className="border-b border-line px-5 py-5">
          <Link to="/" aria-label="RunTrace home"><Logo /></Link>
          <p className="mt-2 text-[11px] font-semibold uppercase tracking-wider text-muted">Find · Trace · Verify</p>
        </div>
        <nav aria-label="Main" className="flex-1 overflow-y-auto p-3">
          <NavLinks />
        </nav>
        <p className="border-t border-line px-5 py-3 text-[11px] text-muted">RunTrace v0.1 · local</p>
      </aside>

      {drawerOpen && (
        <div className="fixed inset-0 z-40 lg:hidden" role="dialog" aria-modal="true" aria-label="Navigation">
          <button type="button" aria-label="Close navigation" className="absolute inset-0 bg-black/40" onClick={() => setDrawerOpen(false)} />
          <div className="absolute left-0 top-0 flex h-full w-72 flex-col border-r-[1.5px] border-strong bg-card">
            <div className="flex items-center justify-between border-b border-line px-4 py-4">
              <Logo />
              <button type="button" className="btn-ghost px-2 py-1" aria-label="Close navigation" onClick={() => setDrawerOpen(false)}>
                <X size={18} />
              </button>
            </div>
            <nav aria-label="Mobile" className="flex-1 overflow-y-auto p-3">
              <NavLinks onNavigate={() => setDrawerOpen(false)} />
            </nav>
          </div>
        </div>
      )}

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="sticky top-0 z-30 flex items-center gap-3 border-b-[1.5px] border-strong bg-card px-4 py-2.5 sm:px-6">
          <button type="button" className="btn-ghost px-2 py-1.5 lg:hidden" aria-label="Open navigation" onClick={() => setDrawerOpen(true)}>
            <Menu size={18} />
          </button>
          <span className="lg:hidden"><Logo compact /></span>
          <div className="min-w-0 flex-1"><Breadcrumbs /></div>
          <span className="hidden whitespace-nowrap font-display text-sm font-bold uppercase tracking-wider md:inline">
            Built for <span className="bg-accent px-1.5 py-0.5 text-accent-fg">Code for Change</span>
            <span className="mx-2 text-muted">|</span>MongoDB<span className="mx-2 text-muted">|</span>2026
          </span>
          <div className="hidden flex-1 md:block" />
          <ConnectionStatus />
          <ThemeToggle />
        </header>
        <main className="mx-auto w-full max-w-7xl flex-1 px-4 py-6 sm:px-6 lg:py-8">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
