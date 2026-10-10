# API reference

Base URL: `http://127.0.0.1:8000` (configurable). Interactive OpenAPI docs: `/docs`; schema: `/openapi.json`.
All timestamps are ISO-8601 UTC with a trailing `Z`.

## Authentication

| Caller | Header | Can access |
|---|---|---|
| Project (SDK) | `Authorization: Bearer rt_live_…` or `X-RunTrace-Key: rt_live_…` | ingestion; read/compare/analyze/verify/metrics **for its own project only** |
| Dashboard / admin | `X-RunTrace-Admin-Token: …` when `RUNTRACE_ADMIN_TOKEN` is set; nothing in *open mode* | everything |

"Reader" endpoints below accept either; with a project key, access to another project's data returns **403**.
Admin-only endpoints never accept a project key.

## Errors

```json
{ "error": { "code": "conflict", "message": "Conflicting duplicate event: …", "details": { } } }
```

| HTTP | code | When |
|---|---|---|
| 400 | `bad_request` | semantic problems (same run twice, empty update, …) |
| 401 | `unauthorized` | missing/invalid/revoked key or admin token |
| 403 | `forbidden` | project key used for another project |
| 404 | `not_found` | unknown project/run/finding |
| 409 | `conflict` | conflicting duplicate event, finished run, revoked key, status change on finish |
| 413 | `payload_too_large` / `batch_too_large` | body > `RUNTRACE_MAX_REQUEST_BYTES` / too many events |
| 422 | `validation_error` | schema violations (`details` lists `loc`, `msg`, `type`; submitted values are never echoed) |
| 429 | `rate_limited` | per key / per IP limit; `Retry-After` header |
| 503 | `database_unavailable` | MongoDB unreachable (`details.reason` has a credential-free reason) |
| 503 | `ai_disabled` | AI requested without `GEMINI_API_KEY`; 502/504 for provider errors/timeouts |

## Health

`GET /health` (public) → `{status: "ok"|"degraded", version, time, database: {connected, name, latency_ms, error, indexes_ready}, auth_mode, ai: {enabled, model}, limits}`

## Projects (admin unless noted)

| Method & path | Body | Response |
|---|---|---|
| `GET /api/projects?q&include_demo=true&page=1&page_size=25` | — | `{items: Project[], meta}` (each with `stats`) |
| `POST /api/projects` | `{name (1–120), description? (≤2000), settings?: {environment?, …}}` | **201** `{project, key: {key_id, api_key, prefix, created_at}}` — `api_key` shown once |
| `GET /api/projects/{project_id}` *(reader)* | — | `{project, keys: KeyInfo[], versions: Version[]}` |
| `PATCH /api/projects/{project_id}` | `{name?, description?, settings?}` | `Project` |
| `GET /api/projects/{project_id}/keys` | — | `KeyInfo[]` (`prefix`, `active`, timestamps — never the key) |
| `POST /api/projects/{project_id}/keys/rotate` | `{revoke_existing?: true}` | **201** `KeyIssued` |
| `POST /api/projects/{project_id}/keys/revoke` | `{key_id?}` (omit = all active) | `{revoked: [key_id]}`; 409 if already revoked |
| `POST /api/projects/{project_id}/versions` *(reader)* | `{version: "[A-Za-z0-9._-+]{1,64}", metadata?}` | **201** created / **200** existing `Version` |
| `GET /api/projects/{project_id}/versions` *(reader)* | — | `Version[]` with `run_count` |
| `GET /api/projects/{project_id}/runs?status&q&version&page&page_size` *(reader)* | — | `{items: Run[], meta}` |
| `GET /api/projects/{project_id}/metrics?days=30` *(reader)* | — | `Metrics` |
| `GET /api/keys/verify` *(project key)* | — | `{project_id, project_name, key_id}` |

## Ingestion (project key)

`POST /api/runs/start`
```json
{ "name": "Customer Support Workflow", "version": "1.1", "environment": "dev",
  "metadata": {"model": "x"}, "client_run_key": "4c1f…(8–100 chars [A-Za-z0-9_-])" }
```
→ **201** `Run` (new) or **200** `Run` (same `client_run_key` retried).

`POST /api/runs/{run_id}/events`
```json
{ "events": [ {
    "event_id": "evt_<32 hex> (optional, enables idempotent retries)",
    "sequence": 1, "event_type": "llm", "name": "call_llm", "status": "success|failed|info|skipped",
    "timestamp": "2026-10-10T10:00:00Z", "duration_ms": 812.5,
    "input_summary": {}, "output_summary": {}, "metadata": {},
    "error": {"type": "json.decoder.JSONDecodeError", "message": "…", "traceback": "…"}
} ] }
```
1–`RUNTRACE_MAX_EVENTS_PER_BATCH` events. → `{run_id, accepted, duplicates, results: [{event_id, sequence, result: "created"|"duplicate"}]}`.
409 on conflicting duplicates or new events for a finished run (`details.accepted_before_conflict` lists what was stored).

`POST /api/runs/{run_id}/finish`
```json
{ "status": "success|failed", "error_summary": "optional", "summary": {}, "duration_ms": 1234 }
```
→ `Run`. Idempotent for the same status; 409 for a different one. If `error_summary` is omitted for a failed run,
it is derived from the first failed event.

## Runs

| Method & path | Auth | Response |
|---|---|---|
| `GET /api/runs?project_id&status&q&version&include_demo&page&page_size` | admin | `{items: Run[], meta}` (`q` matches name, error text or exact run ID) |
| `GET /api/runs/{run_id}` | reader | `Run` (with `project_name`) |
| `GET /api/runs/{run_id}/events` | reader | `{run_id, items: Event[], total}` in sequence order |
| `GET /api/runs/{run_id}/findings` | reader | `Finding[]` |
| `POST /api/runs/{run_id}/analyze` | reader | body `{baseline_run_id?}` → `{run_id, baseline_run_id, baseline_selection, findings, comparison_summary}` |

## Comparison

`POST /api/compare` *(reader)* — `{baseline_run_id, comparison_run_id, include_diagnosis: true}` →

```text
{ baseline: RunMeta, comparison: RunMeta, alignment_strategy,
  entries: [{position, step_key, name, kind: unchanged|changed|added|missing, reordered,
             baseline: EventRef|null, comparison: EventRef|null,
             differences: [{field: status|output|input|error|metadata|event_type, baseline?, comparison?, changes?, schema_changed?}],
             timing: {baseline_ms, comparison_ms, delta_ms, ratio, notable}|null, description}],
  summary: {unchanged, changed, added, missing, reordered, status_changed, output_changed, schema_changed,
            error_changed, metadata_changed, input_changed, notable_timing, total_entries, baseline_events,
            comparison_events, identical},
  earliest_divergence: {position, step_key, name, kind, description, baseline_event_id, comparison_event_id,
                        baseline_sequence, comparison_sequence, fields} | null,
  first_failure: EventRef|null, run_differences: [...], warnings: [...],
  diagnosis: {persisted: false, note, findings: FindingDraft[]} }
```

## Findings

| Method & path | Auth | Notes |
|---|---|---|
| `GET /api/findings?project_id&run_id&severity&category&verification_status&q&include_demo&page&page_size` | reader | project keys are scoped to their project automatically |
| `GET /api/findings/{finding_id}` | reader | `Finding` |
| `POST /api/findings/{finding_id}/verify` | reader | `{run_id: corrected run}` → `Finding` with `verification_status` (`verified`/`not_improved`/`inconclusive`) and `verification: {run_id, checked_at, result, checks[], note}` |

`Finding` fields: `finding_id, project_id, run_id, baseline_run_id, category, severity (high|medium|low),
confidence (high|medium|low), title, summary, observation, evidence[{kind, description, run_id, event_id, sequence,
step, field?, value}], hypothesis, suggested_actions[], regression_test, step, verification_status, verification,
source ("deterministic"), is_demo, created_at, updated_at`.

## Metrics

`GET /api/metrics?project_id&days=30&include_demo=true` *(reader)* →
`{scope, totals: {projects, runs, success, failed, timed_out, running, finished, all_time_runs}, success_rate,
average_duration_ms, duration_sample_size, by_version: [{version, total, success, failed, failure_rate}],
activity: [{date, total, success, failed, running}], findings: {total, high, verified, unverified}, notes, generated_at}`

## AI (optional)

* `GET /api/ai/status` → `{enabled, model, reason}`
* `POST /api/ai/chat` *(reader)* `{question, run_id?, finding_id?}` (one of the IDs required) →
  `{source: "ai_generated", model, answer, context, disclaimer}`
