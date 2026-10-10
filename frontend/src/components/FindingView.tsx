import { Bot, CheckCircle2, CircleSlash, FlaskConical, Lightbulb, ListChecks, Microscope, Sparkles } from 'lucide-react';
import { useState, type ReactNode } from 'react';
import { Link } from 'react-router-dom';
import { useAIChat, useAIStatus, useRuns, useVerifyFinding } from '../hooks/queries';
import { formatRelative, humanize, shortId } from '../lib/format';
import type { Finding, FindingDraft } from '../types/api';
import { ConfidenceBadge, SeverityBadge, VerificationBadge } from './badges';
import { CodeBlock, ErrorState, JsonView } from './ui';

function Section({ icon, title, children, tone }: { icon: ReactNode; title: string; children: ReactNode; tone?: string }) {
  return (
    <div>
      <p className={`label flex items-center gap-1.5 ${tone ?? ''}`}>
        {icon} {title}
      </p>
      {children}
    </div>
  );
}

export function FindingHeader({ finding }: { finding: FindingDraft | Finding }) {
  return (
    <div className="flex flex-wrap items-center gap-2">
      <SeverityBadge severity={finding.severity} />
      <ConfidenceBadge confidence={finding.confidence} />
      <span className="chip border-line text-muted">{humanize(finding.category)}</span>
      {'verification_status' in finding && <VerificationBadge status={finding.verification_status} />}
    </div>
  );
}

export function FindingBody({ finding }: { finding: FindingDraft | Finding }) {
  return (
    <div className="space-y-4">
      <Section icon={<Microscope size={14} />} title="Observation (recorded)">
        <p className="text-sm">{finding.observation}</p>
      </Section>
      <Section icon={<ListChecks size={14} />} title={`Evidence (${finding.evidence.length})`}>
        <ul className="space-y-2">
          {finding.evidence.map((item, i) => (
            <li key={i} className="rounded-md border border-line p-2.5">
              <p className="text-sm font-medium">{item.description}</p>
              <p className="mono-id mb-1.5">
                {item.run_id && (
                  <Link className="underline decoration-dotted hover:text-fg" to={`/runs/${item.run_id}`}>
                    {shortId(item.run_id)}
                  </Link>
                )}
                {item.sequence !== undefined && item.sequence !== null && ` · step #${item.sequence}`}
                {item.event_id && ` · ${shortId(item.event_id)}`}
                {item.field && ` · ${item.field}`}
              </p>
              {item.value !== undefined && item.value !== null && <JsonView value={item.value} />}
            </li>
          ))}
        </ul>
      </Section>
      <Section icon={<Lightbulb size={14} />} title="Hypothesis — not a proven cause" tone="text-warning">
        <p className="rounded-md border-l-4 border-accent bg-[var(--accent-soft)] p-2.5 text-sm">{finding.hypothesis}</p>
      </Section>
      <Section icon={<FlaskConical size={14} />} title="Suggested investigation">
        <ol className="list-decimal space-y-1 pl-5 text-sm">
          {finding.suggested_actions.map((a) => (
            <li key={a}>{a}</li>
          ))}
        </ol>
      </Section>
      {finding.regression_test && (
        <Section icon={<CheckCircle2 size={14} />} title="Suggested regression test">
          <CodeBlock code={finding.regression_test} label="pytest" />
        </Section>
      )}
    </div>
  );
}

export function VerifyPanel({ finding }: { finding: Finding }) {
  const candidates = useRuns({ project_id: finding.project_id, page_size: 50 });
  const verify = useVerifyFinding();
  const [runId, setRunId] = useState('');
  const options = (candidates.data?.items ?? []).filter((r) => r.run_id !== finding.run_id && r.status !== 'running');
  const verification = verify.data?.verification ?? finding.verification;

  return (
    <div className="space-y-3 rounded-md border-[1.5px] border-strong p-3">
      <p className="section-title flex items-center gap-2">
        <CheckCircle2 size={18} /> Verify the fix
      </p>
      <p className="text-xs text-muted">
        Pick a run recorded after your change. RunTrace checks observable behaviour (run status, the affected step, failed
        steps). A pass shows the symptom is gone; it does not prove the hypothesis was the root cause.
      </p>
      {candidates.isError && <ErrorState error={candidates.error} compact />}
      <form
        className="flex flex-col gap-2 sm:flex-row"
        onSubmit={(e) => {
          e.preventDefault();
          if (runId) verify.mutate({ findingId: finding.finding_id, runId });
        }}
      >
        <select aria-label="Corrected run" className="input" value={runId} onChange={(e) => setRunId(e.target.value)}>
          <option value="">Select corrected run…</option>
          {options.map((r) => (
            <option key={r.run_id} value={r.run_id}>
              {r.name} · {r.version ? `v${r.version} · ` : ''}
              {r.status} · {formatRelative(r.started_at)}
            </option>
          ))}
        </select>
        <button type="submit" className="btn-primary" disabled={!runId || verify.isPending}>
          {verify.isPending ? 'Checking…' : 'Verify'}
        </button>
      </form>
      {verify.isError && <ErrorState error={verify.error} compact />}
      {verification && (
        <div className="space-y-2">
          <div className="flex items-center gap-2 text-sm">
            Result: <VerificationBadge status={verification.result} /> against{' '}
            <Link to={`/runs/${verification.run_id}`} className="mono-id underline">
              {shortId(verification.run_id)}
            </Link>
          </div>
          <ul className="space-y-1 text-sm">
            {verification.checks.map((c) => (
              <li key={c.check} className="flex items-center gap-2">
                {c.passed ? <CheckCircle2 size={15} className="text-success" /> : <CircleSlash size={15} className="text-danger" />}
                <span>{c.description}</span>
                <span className="mono-id">observed: {JSON.stringify(c.observed)}</span>
              </li>
            ))}
          </ul>
          <p className="text-xs text-muted">{verification.note}</p>
        </div>
      )}
    </div>
  );
}

export function AIPanel({ runId, findingId }: { runId?: string; findingId?: string }) {
  const status = useAIStatus();
  const chat = useAIChat();
  const [question, setQuestion] = useState('What is the most likely explanation, and what should I check first?');
  if (status.isLoading) return null;
  if (!status.data?.enabled) {
    return (
      <p className="flex items-center gap-2 rounded-md border border-dashed border-line p-2.5 text-xs text-muted">
        <Bot size={14} /> AI assistance is off. {status.data?.reason ?? ''} All deterministic analysis works without it.
      </p>
    );
  }
  return (
    <div className="space-y-2 rounded-md border-[1.5px] border-dashed border-strong p-3">
      <p className="section-title flex items-center gap-2">
        <Sparkles size={16} /> Ask AI <span className="chip border-line text-muted">{status.data.model}</span>
      </p>
      <form
        className="flex flex-col gap-2"
        onSubmit={(e) => {
          e.preventDefault();
          chat.mutate({ question, run_id: runId, finding_id: findingId });
        }}
      >
        <textarea aria-label="Question for AI" className="input min-h-[64px]" value={question} onChange={(e) => setQuestion(e.target.value)} />
        <button type="submit" className="btn-secondary self-start" disabled={!question.trim() || chat.isPending}>
          {chat.isPending ? 'Asking…' : 'Ask'}
        </button>
      </form>
      {chat.isError && <ErrorState error={chat.error} compact />}
      {chat.data && (
        <div className="rounded-md bg-soft p-3">
          <p className="chip mb-2 border-info text-info">AI-generated · not stored</p>
          <p className="whitespace-pre-wrap text-sm">{chat.data.answer}</p>
          <p className="mt-2 text-xs text-muted">{chat.data.disclaimer}</p>
        </div>
      )}
    </div>
  );
}
