# Architecture

## Components and data flow

```
┌─────────────────────┐   HTTPS/HTTP + Bearer rt_live_…   ┌──────────────────────────────┐    PyMongo    ┌──────────┐
│ Your Python app     │ ───────────────────────────────▶ │ FastAPI backend               │ ────────────▶ │ MongoDB  │
│  runtrace_sdk       │  POST /api/runs/start             │  routes → services →          │               │ (local / │
│  client.run(...)    │  POST /api/runs/{id}/events       │  repositories                 │               │  Atlas)  │
│   run.step(...)     │  POST /api/runs/{id}/finish       │  comparison/  diagnosis/      │               └──────────┘
└─────────────────────┘                                    │  (pure, deterministic)        │
                                                           │  services/ai.py (optional) ──┼──▶ Gemini API
┌─────────────────────┐   REST (CORS-restricted)           │                               │    (server-side key)
│ React dashboard     │ ◀────────────────────────────────▶ │                               │
└─────────────────────┘   optional X-RunTrace-Admin-Token  └──────────────────────────────┘
```

1. `client.run(name)` → `POST /api/runs/start` with a random `client_run_key`. The server creates the run
   (`status: running`, server-generated `run_id`, UTC `started_at`) or returns the existing run for the same key.
2. Each `run.step(name)` gets the next sequence number on entry and is recorded on exit with status, duration,
   input/output summaries, metadata and (if it raised) the error. Events are buffered and sent in batches to
   `POST /api/runs/{run_id}/events`, each with a client-generated `event_id`.
3. Leaving the `with client.run(...)` block flushes and calls `POST /api/runs/{run_id}/finish` with `success`
   or `failed`, the duration and an error summary.
4. The backend validates (Pydantic), authenticates the key (SHA-256 lookup), checks project ownership,
   redacts and truncates payloads, computes a content hash per event, and stores documents in MongoDB.
5. The dashboard reads runs/events/findings/metrics, triggers comparisons, analysis and verification.

## Run lifecycle

| Status | Meaning |
|---|---|
| `running` | started, not finished (`finished_at`/`duration_ms` are `null`) |
| `success` / `failed` | finished by the client (`finish` is idempotent for the same status; a different status → 409) |
| `timed_out` | no `finish` within `RUNTRACE_STALE_RUN_MINUTES`; set by a throttled server sweep, `duration_ms` stays `null`. A late `finish` still records the real outcome. |

Events for a finished run are rejected (409) unless they are identical retries of already-stored events.

## Data model (MongoDB)

| Collection | Key fields |
|---|---|
| `projects` | `project_id`, `name`, `description`, `settings`, `is_demo`, `demo_key?`, `created_at`, `updated_at` |
| `project_keys` | `key_id`, `project_id`, `key_hash` (SHA-256), `prefix` (display only), `created_at`, `revoked_at`, `last_used_at` |
| `project_versions` | `version_id`, `project_id`, `version`, `metadata`, `created_at` |
| `runs` | `run_id`, `project_id`, `client_run_key`, `version_id`, `version`, `name`, `status`, `environment`, `started_at`, `finished_at`, `duration_ms`, `error_summary`, `summary`, `metadata`, `event_count`, `failed_event_count`, `is_demo`, `source` (`sdk`/`demo_seed`) |
| `events` | `event_id`, `run_id`, `project_id`, `sequence`, `event_type`, `name`, `status`, `timestamp`, `duration_ms`, `input_summary`, `output_summary`, `error`, `metadata`, `content_hash`, `received_at` |
| `findings` | `finding_id`, `fingerprint`, `project_id`, `run_id`, `baseline_run_id`, `category`, `severity`, `confidence`, `title`, `summary`, `observation`, `evidence[]`, `hypothesis`, `suggested_actions[]`, `regression_test`, `step`, `step_key`, `verification_status`, `verification`, `source`, `is_demo`, `created_at`, `updated_at` |

All IDs are server-generated `prefix_<uuid4 hex>` (`prj_`, `run_`, `evt_`, `fnd_`, `key_`, `ver_`), except that the
SDK may supply its own `evt_<32 hex>` event IDs for idempotent retries. Uniqueness is enforced by indexes.

### Indexes (created idempotently at startup / first successful connection)

| Collection | Index | Purpose |
|---|---|---|
| projects | `project_id` unique; `created_at` desc | lookup; listing |
| project_keys | `key_id` unique; `key_hash` unique; `(project_id, created_at)` | auth lookup by hash |
| project_versions | `version_id` unique; `(project_id, version)` unique | one label per project |
| runs | `run_id` unique; `(project_id, client_run_key)` unique; `(project_id, started_at)`; `(project_id, status, started_at)`; `(status, started_at)`; `started_at` | lookups, idempotent start, filtered listing, stale sweep |
| events | `(run_id, event_id)` unique; `(run_id, sequence)` unique; `(project_id, timestamp)` | idempotency, ordering |
| findings | `finding_id` unique; `fingerprint` unique; `(run_id, created_at)`; `(project_id, severity, created_at)`; `(project_id, verification_status)`; `created_at` | idempotent analysis, filters |

## Event ingestion and idempotency

For each submitted event the server computes `content_hash = sha256(canonical JSON of the client-supplied
fields after redaction/truncation)`. On a unique-index collision (same `event_id`, or same `sequence`):

* same hash → **duplicate** (200, `result: "duplicate"`, nothing stored);
* different hash → **409 conflict** ("event_id was already used with different content" or "sequence N is already used").

## Comparison engine (`app/comparison/engine.py`)

**Alignment strategy — logical step keys.** Each event's key is `<name>#<n>` where `n` is its occurrence index
of that name in the run (`call_llm#1`, `call_llm#2`). Keys present in both runs are paired; the longest
increasing subsequence (in baseline order) of their comparison positions marks pairs that kept their order, others
are flagged `reordered`. Baseline-only keys are **missing**, comparison-only keys are **added**. Entries are
ordered by the comparison run's execution order, with missing steps inserted after their preceding step.
Events are never paired just because they share a sequence number (a step inserted early shifts every later
sequence number; name-based alignment is unaffected).

**Per-pair differences:** status, event type, output (structural diff: `type_changed`, `key_added`,
`key_removed`, `length_changed`, `value_changed`, with `schema_changed` when keys/types change), input, error
(type + message) and metadata (volatile keys such as `request_id`, `trace_id`, timestamps are ignored). Timing
is compared only when both durations exist and is flagged *notable* at ≥ 250 ms and ≥ 2× change.

**Earliest observable divergence** = the first entry (in that order) that is added, missing, or has any
non-timing difference. Timing alone never counts.

**Limitations:** renamed steps show as missing + added; loops with different iteration counts align by
occurrence; unrecorded work is invisible; the earliest *recorded* difference may not be the true origin.

## Diagnosis engine (`app/diagnosis/engine.py`)

Pure functions over stored events and (optionally) a comparison with a baseline. Baseline selection for
`/analyze`: explicit `baseline_run_id`, else the latest successful run of the same name that started earlier, else
the latest earlier successful run in the project.

| Category | Triggered by (recorded evidence) |
|---|---|
| `invalid_json` | `JSONDecodeError` type, or parse-error message patterns |
| `missing_module` | `ModuleNotFoundError`/`ImportError`, "No module named 'x'" (module extracted) |
| `missing_env_var` | `KeyError('UPPER_CASE')`, "environment variable X is not set" |
| `missing_field` | `KeyError('field')`, validation "field required"; or output keys removed vs baseline |
| `external_timeout` | timeout exception types or "timed out" |
| `http_failure` | HTTP error types, "status code 5xx", or `status_code`/`http_status` ≥ 400 in event metadata |
| `tool_failure` | failed event with `event_type == "tool"` |
| `null_output` | `'NoneType' object …` errors; output became `null` vs baseline |
| `schema_change` | output keys added / types changed vs baseline at or before the first failure |
| `config_mismatch` | version/environment/run-metadata changes; config-like event metadata (`model`, `temperature`, `prompt_version`, …) |
| `divergence` | the earliest observable divergence (an observation with an ordering-only hypothesis) |
| `timing_change` | notable duration change (low severity) |
| `step_failure` | failed step with no known pattern (low confidence) |

Severity is `high` for findings on the first failure of a failed run (and the divergence of a failed run),
otherwise `medium`/`low`. Confidence reflects how specific the matched evidence is. Hypotheses are worded as
possibilities ("may", "likely", "consistent with"). For the failing step the engine links the nearest upstream
step whose output changed versus the baseline as supporting evidence.

**Regression tests** are generated from recorded values (e.g. the exact failing input of a parser) with an explicit
`from your_module import … # TODO` placeholder — RunTrace never invents import paths or line numbers.

Findings are upserted by `fingerprint = sha256(run_id | baseline_run_id | category | step_key)`, so re-running
analysis updates the same findings and keeps their verification state.

## Verification (`POST /api/findings/{id}/verify`)

Given a corrected run from the same project (not the failing run, not still running) the server checks:
`run_succeeded`, `step_present` (same step key or name), `step_succeeded`, `no_failed_events`, and flags a
corrected run that started before the failure. Result: `verified` (all pass), `not_improved`, or `inconclusive`
(e.g. the step is absent but the run succeeded). The stored note states that verification shows the symptom is
gone, not that the hypothesis was the root cause.

## Metrics

Counts use `count_documents` over the full filtered window; average duration and failures-by-version use
aggregation pipelines over the same filter; daily activity buckets every run in the window (≤ 365 days). Success
rate = success / finished (running runs excluded). Nothing is derived from paginated lists.

## Optional AI (Gemini)

`POST /api/ai/chat` builds a context from stored run/events/finding, calls the Gemini `generateContent` REST
endpoint from the server with `x-goog-api-key`, a timeout and graceful errors, and returns the answer labelled
`source: "ai_generated"` with a disclaimer. Nothing is persisted and raw events are never modified. With no
`GEMINI_API_KEY`, `/api/ai/status` reports `enabled: false` and chat returns 503 `ai_disabled`.
