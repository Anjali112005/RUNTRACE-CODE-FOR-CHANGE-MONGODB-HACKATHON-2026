import { Database, KeyRound, Moon, Server, ShieldCheck, Sun } from 'lucide-react';
import { useEffect, useState, useSyncExternalStore } from 'react';
import { Link } from 'react-router-dom';
import { getAdminToken, setAdminToken, subscribeAdminToken } from '../api/client';
import { StatusBadge } from '../components/badges';
import { Card, ErrorState, KeyValue, Loading, PageHeader } from '../components/ui';
import { useTheme } from '../contexts/ThemeContext';
import { useHealth } from '../hooks/queries';
import { API_BASE_URL } from '../lib/config';
import { cn } from '../lib/cn';
import { useQueryClient } from '@tanstack/react-query';

function AdminTokenForm() {
  const token = useSyncExternalStore(subscribeAdminToken, getAdminToken);
  const [value, setValue] = useState('');
  const qc = useQueryClient();
  useEffect(() => setValue(''), [token]);
  return (
    <form
      className="space-y-2"
      onSubmit={(e) => {
        e.preventDefault();
        setAdminToken(value);
        qc.invalidateQueries();
      }}
    >
      <label className="label" htmlFor="admin-token">Admin token</label>
      <div className="flex gap-2">
        <input id="admin-token" type="password" autoComplete="off" className="input" placeholder={token ? 'Token set for this tab' : 'Paste RUNTRACE_ADMIN_TOKEN'} value={value} onChange={(e) => setValue(e.target.value)} />
        <button type="submit" className="btn-secondary" disabled={!value.trim()}>Use</button>
        {token && (
          <button type="button" className="btn-ghost" onClick={() => { setAdminToken(null); qc.invalidateQueries(); }}>Clear</button>
        )}
      </div>
      <p className="text-xs text-muted">Kept in memory only — never written to localStorage or cookies — so you will need to re-enter it after a reload.</p>
    </form>
  );
}

export function SettingsPage() {
  const { theme, setTheme } = useTheme();
  const health = useHealth();
  const h = health.data;

  return (
    <div className="space-y-6">
      <PageHeader title="Settings" subtitle="Theme, API connection and how RunTrace handles your data." />
      <div className="grid gap-6 lg:grid-cols-2">
        <Card title="Theme">
          <div className="flex gap-3" role="radiogroup" aria-label="Theme">
            {(['light', 'dark'] as const).map((t) => (
              <button
                key={t}
                type="button"
                role="radio"
                aria-checked={theme === t}
                onClick={() => setTheme(t)}
                className={cn('flex flex-1 items-center justify-center gap-2 rounded-md border-[1.5px] px-4 py-3 font-semibold capitalize',
                  theme === t ? 'border-strong bg-accent text-accent-fg' : 'border-line bg-card hover:border-strong')}
              >
                {t === 'light' ? <Sun size={16} /> : <Moon size={16} />} {t}
              </button>
            ))}
          </div>
          <p className="mt-2 text-xs text-muted">Your choice is saved in this browser (a display preference only).</p>
        </Card>

        <Card title={<span className="flex items-center gap-2"><Server size={18} /> API connection</span>}>
          <dl className="grid grid-cols-2 gap-3">
            <KeyValue label="Base URL"><span className="font-mono text-xs">{API_BASE_URL}</span></KeyValue>
            <KeyValue label="Status">{h ? <StatusBadge status={h.status === 'ok' ? 'success' : 'failed'} /> : '—'}</KeyValue>
            <KeyValue label="API version">{h?.version ?? '—'}</KeyValue>
            <KeyValue label="Auth mode">{h ? (h.auth_mode === 'open' ? 'Open (local)' : 'Admin token required') : '—'}</KeyValue>
            <KeyValue label="AI assistance">{h ? (h.ai.enabled ? `On (${h.ai.model})` : 'Off') : '—'}</KeyValue>
            <KeyValue label="Max request">{h ? `${Math.round(h.limits.max_request_bytes / 1024)} KB` : '—'}</KeyValue>
          </dl>
          {health.isLoading && <Loading rows={1} />}
          {health.isError && <div className="mt-3"><ErrorState error={health.error} onRetry={() => health.refetch()} /></div>}
          <p className="mt-3 text-xs text-muted">Change the URL with <code>VITE_API_BASE_URL</code> in <code>frontend/.env</code> and restart Vite.</p>
        </Card>

        <Card title={<span className="flex items-center gap-2"><Database size={18} /> Database</span>}>
          {h ? (
            <dl className="grid grid-cols-2 gap-3">
              <KeyValue label="Connected">{h.database.connected ? 'Yes' : 'No'}</KeyValue>
              <KeyValue label="Database">{h.database.name}</KeyValue>
              <KeyValue label="Latency">{h.database.latency_ms !== null ? `${h.database.latency_ms} ms` : '—'}</KeyValue>
              <KeyValue label="Indexes">{h.database.indexes_ready ? 'Ready' : 'Pending'}</KeyValue>
            </dl>
          ) : (
            <p className="text-sm text-muted">Unavailable while the API is unreachable.</p>
          )}
          {h?.database.error && <p className="mt-3 rounded-md border border-danger p-2 font-mono text-xs text-danger">{h.database.error}</p>}
        </Card>

        <Card title={<span className="flex items-center gap-2"><KeyRound size={18} /> Access & keys</span>}>
          {h?.auth_mode === 'admin_token' ? (
            <AdminTokenForm />
          ) : (
            <p className="text-sm">The server runs in <strong>open mode</strong> (no <code>RUNTRACE_ADMIN_TOKEN</code>). Keep it bound to 127.0.0.1.</p>
          )}
          <p className="mt-3 text-sm">Project API keys are managed per project: rotate or revoke them on each <Link className="underline" to="/projects">project page</Link>.</p>
        </Card>
      </div>

      <Card title={<span className="flex items-center gap-2"><ShieldCheck size={18} /> Data handling</span>}>
        <ul className="grid list-disc gap-x-8 gap-y-1.5 pl-5 text-sm md:grid-cols-2">
          <li>API keys are generated with a cryptographic RNG; only SHA-256 hashes are stored.</li>
          <li>Secrets in event payloads (passwords, tokens, API keys, credentials in URLs) are redacted by the SDK and again by the server.</li>
          <li>Long values are truncated and request bodies are size-limited.</li>
          <li>Raw events are never modified by analysis or AI; findings are stored separately.</li>
          <li>Observations come from recorded data; hypotheses are labelled and never presented as proven causes.</li>
          <li>Gemini (optional) is called from the server only; its key never reaches the browser, and its answers are not stored.</li>
          <li>Demo records are flagged and can be excluded from lists and metrics.</li>
          <li>This dashboard keeps no credentials in browser storage.</li>
        </ul>
      </Card>
    </div>
  );
}
