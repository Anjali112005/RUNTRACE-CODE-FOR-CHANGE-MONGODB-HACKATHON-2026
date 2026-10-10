import { Link } from 'react-router-dom';
import { Card, CodeBlock, PageHeader } from '../components/ui';
import { API_BASE_URL } from '../lib/config';

const INSTALL = `# From the RunTraceNew folder (the SDK is local; it is not published to PyPI)
python -m pip install -e ./sdk`;

const ENV_PS = `$env:RUNTRACE_API_URL = "${API_BASE_URL}"
$env:RUNTRACE_API_KEY = "rt_live_..."      # shown once when you create or rotate a key
$env:RUNTRACE_VERSION = "1.0.0"            # optional: groups runs by version
$env:RUNTRACE_ENVIRONMENT = "dev"          # optional`;

const ENV_SH = `export RUNTRACE_API_URL="${API_BASE_URL}"
export RUNTRACE_API_KEY="rt_live_..."
export RUNTRACE_VERSION="1.0.0"
export RUNTRACE_ENVIRONMENT="dev"`;

const USAGE = `from runtrace_sdk import RunTraceClient

client = RunTraceClient.from_env()

with client.run("Customer Support Workflow") as run:
    with run.step("retrieve_context", event_type="retrieval", input={"question": question}) as step:
        context = retrieve_context(question)
        step.set_output([doc.id for doc in context])     # optional: recorded (redacted, truncated)

    with run.step("generate_answer", event_type="llm", metadata={"model": MODEL}) as step:
        answer = generate_answer(context)
        step.set_output({"text": answer})`;

const OPTIONS = `RUNTRACE_STRICT=true        # raise TelemetryError if RunTrace is unreachable (default: best effort)
RUNTRACE_ENABLED=false      # turn telemetry off entirely (no key needed)
RUNTRACE_TIMEOUT=5          # seconds per HTTP request
RUNTRACE_MAX_RETRIES=2      # retries are duplicate-safe (client event IDs)
RUNTRACE_BATCH_SIZE=20      # events per request`;

export function IntegrationPage() {
  return (
    <div className="space-y-6">
      <PageHeader title="SDK & Integration" subtitle="Instrument any Python workflow without rewriting its logic: wrap the run and its important steps." />
      <div className="grid gap-6 lg:grid-cols-2">
        <Card title="1 · Install">
          <CodeBlock label="shell" code={INSTALL} />
          <p className="mt-2 text-xs text-muted">Requires Python 3.10+. The only dependency is httpx.</p>
        </Card>
        <Card title="2 · Configure">
          <p className="mb-2 text-sm">
            Create a project on the <Link to="/projects?new=1" className="font-semibold underline">Projects</Link> page to get a key. Keys are shown once and stored only as hashes.
          </p>
          <div className="space-y-3">
            <CodeBlock label="Windows PowerShell" code={ENV_PS} />
            <CodeBlock label="macOS / Linux" code={ENV_SH} />
          </div>
        </Card>
      </div>
      <Card title="3 · Instrument">
        <CodeBlock label="python" code={USAGE} />
        <ul className="mt-3 list-disc space-y-1 pl-5 text-sm text-muted">
          <li>Exceptions inside a step are recorded (type, message, traceback) and then re-raised unchanged.</li>
          <li>Values are converted to JSON, truncated, and scanned for secrets (keys, tokens, passwords) before sending.</li>
          <li>If RunTrace is down, your app keeps running; the SDK logs one warning (unless strict mode is on).</li>
        </ul>
      </Card>
      <div className="grid gap-6 lg:grid-cols-2">
        <Card title="4 · Check the connection">
          <CodeBlock label="shell" code={`runtrace ping            # API health + key validity\nruntrace send-test-run   # records a tiny two-step run`} />
        </Card>
        <Card title="Options">
          <CodeBlock label="environment" code={OPTIONS} />
        </Card>
      </div>
      <Card title="First-run tutorial">
        <ol className="list-decimal space-y-2 pl-5 text-sm">
          <li>Start the backend and this dashboard (see the project README).</li>
          <li>Create a project and copy its API key into <code>RUNTRACE_API_KEY</code>.</li>
          <li>Record a baseline: <code>python examples/sample_ai_workflow.py --variant good</code></li>
          <li>Record the regression: <code>python examples/sample_ai_workflow.py --variant regressed</code> (it fails on purpose).</li>
          <li>Open <Link className="underline" to="/compare">Compare Runs</Link>, pick the good run as baseline and the failed run as comparison.</li>
          <li>Review the earliest divergence and the hypotheses, then click <strong>Save findings</strong>.</li>
          <li>Record the fix: <code>python examples/sample_ai_workflow.py --variant fixed</code></li>
          <li>On <Link className="underline" to="/findings">Findings</Link>, verify the invalid-JSON finding against the fixed run.</li>
        </ol>
        <p className="mt-3 text-xs text-muted">Or run the whole loop in one go: <code>python examples/regression_demo.py</code></p>
      </Card>
    </div>
  );
}
