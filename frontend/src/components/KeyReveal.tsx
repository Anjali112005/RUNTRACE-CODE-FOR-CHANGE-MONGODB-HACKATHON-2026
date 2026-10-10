import { KeyRound, ShieldAlert } from 'lucide-react';
import { API_BASE_URL } from '../lib/config';
import type { KeyIssued } from '../types/api';
import { CodeBlock, CopyButton } from './ui';

/**
 * Shows a freshly issued API key exactly once. The key lives only in React state of the
 * parent; it is never written to browser storage and disappears when dismissed.
 */
export function KeyReveal({ issued, onDismiss }: { issued: KeyIssued; onDismiss: () => void }) {
  const powershell = `$env:RUNTRACE_API_URL = "${API_BASE_URL}"\n$env:RUNTRACE_API_KEY = "${issued.api_key}"`;
  const bash = `export RUNTRACE_API_URL="${API_BASE_URL}"\nexport RUNTRACE_API_KEY="${issued.api_key}"`;
  return (
    <div className="card-strong space-y-4 border-accent p-4" role="region" aria-label="New API key">
      <div className="flex items-start gap-3">
        <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-accent text-accent-fg">
          <KeyRound size={20} />
        </span>
        <div>
          <h3 className="text-xl">Your project API key</h3>
          <p className="flex items-center gap-1.5 text-sm text-muted">
            <ShieldAlert size={14} className="text-warning" />
            Copy it now. RunTrace stores only a hash and cannot show this key again.
          </p>
        </div>
      </div>
      <div className="flex items-center gap-2 rounded-md border-[1.5px] border-strong bg-soft p-2">
        <code data-testid="api-key" className="flex-1 break-all text-sm">{issued.api_key}</code>
        <CopyButton text={issued.api_key} />
      </div>
      <div className="grid gap-3 lg:grid-cols-2">
        <CodeBlock label="Windows PowerShell" code={powershell} />
        <CodeBlock label="macOS / Linux" code={bash} />
      </div>
      <CodeBlock
        label="python"
        code={`from runtrace_sdk import RunTraceClient\n\nclient = RunTraceClient.from_env()\n\nwith client.run("My Workflow") as run:\n    with run.step("first_step") as step:\n        step.set_output({"ok": True})`}
      />
      <button type="button" className="btn-secondary" onClick={onDismiss}>
        I have saved the key
      </button>
    </div>
  );
}
