# Security

## Threat model (what RunTrace is designed for)

RunTrace is a developer tool intended to run on a developer machine or a private network. It stores execution
data that may contain sensitive content, accepts writes from instrumented apps, and exposes a dashboard. It has
**no user accounts**. Protect the dashboard with `RUNTRACE_ADMIN_TOKEN` (and TLS/reverse-proxy access control)
before exposing it beyond `127.0.0.1`.

## Project API keys

* Format `rt_live_` + `secrets.token_urlsafe(32)` (256 bits of CSPRNG randomness). The prefix is a convention to
  recognise and redact keys; it is not a security property.
* Only `sha256(key)` is stored (`project_keys.key_hash`, unique index). For high-entropy random tokens a fast hash is
  appropriate; a password KDF adds nothing. Validation is a hash lookup plus a constant-time comparison.
* The plaintext key is returned exactly once (project creation / rotation) and never logged, stored, or re-shown.
  The dashboard keeps it only in component state for the reveal panel.
* Rotation issues a new key and (by default) revokes the previous active keys; revocation is immediate.
  `last_used_at` is updated at most once a minute.
* Keys are scoped to one project: a key cannot read or write another project's data (403).

## Dashboard access

* Open mode (no `RUNTRACE_ADMIN_TOKEN`) is for localhost only; `/health` reports `auth_mode`.
* With a token set, every management endpoint requires `X-RunTrace-Admin-Token` (constant-time compare). The
  dashboard holds the token in memory only (not localStorage/sessionStorage/cookies).

## Data protection

* **Redaction** (SDK *and* server): string values under sensitive keys (`password`, `secret`, `token`,
  `api_key`, `authorization`, `cookie`, `credentials`, `private_key`, `session_id`, …) become `[REDACTED]`;
  numeric values such as `max_tokens` are kept. Known secret formats are redacted anywhere: RunTrace keys,
  `sk-…`, Google `AIza…`, GitHub tokens, AWS access key IDs, bearer tokens, and credentials embedded in
  `mongodb://` / `http(s)://` URLs. Add keys with `RUNTRACE_REDACT_KEYS`.
* **Bounded payloads**: request bodies ≤ `RUNTRACE_MAX_REQUEST_BYTES` (checked via Content-Length and while
  streaming), ≤ `RUNTRACE_MAX_EVENTS_PER_BATCH` events per request, strings truncated to
  `RUNTRACE_MAX_FIELD_CHARS`, collections to 200 items, nesting depth limited.
* **Validation**: strict Pydantic schemas (`extra="forbid"`), ID patterns, enum statuses, length limits.
* **Safe errors**: uniform JSON errors; validation errors never echo submitted values; unexpected errors return
  a generic 500 (details only in server logs); database errors are reported without connection-string credentials.
* **Logs**: the access log records method, path, status and latency only — no headers, query strings or bodies.
* **Rate limiting**: sliding-window limits per API key (ingestion/reader) and per client IP (admin). In-process only;
  use a reverse proxy for multi-instance deployments.
* **CORS**: only `RUNTRACE_CORS_ORIGINS`; credentials are not allowed; explicit method/header allow-lists.

## Secrets management

* MongoDB URI and `GEMINI_API_KEY` live only in `backend/.env` (server). Nothing secret is placed in `VITE_*`
  variables, which are compiled into the browser bundle.
* `.gitignore` excludes `.env`, virtual environments, build outputs and caches; only `.env.example` files with
  placeholders are committed.
* Gemini is called from the server with the key in a header; AI responses are labelled, not persisted, and never
  overwrite stored evidence.

## Known limitations

* No multi-user authorization model; the admin token is a single shared secret.
* In-memory rate limiting resets on restart and is per process.
* Redaction is pattern-based and cannot recognise every possible secret; avoid recording secrets in step
  inputs/outputs at the source and use `RUNTRACE_REDACT_KEYS` for domain-specific fields.
* Use TLS (e.g. a reverse proxy) for any non-local deployment; the SDK warns when an API key would be sent over
  plain HTTP to a non-local host.
