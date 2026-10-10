// Types mirroring the RunTrace REST API (see docs/API.md).

export type RunStatus = 'running' | 'success' | 'failed' | 'timed_out';
export type Severity = 'high' | 'medium' | 'low';
export type VerificationStatus = 'unverified' | 'verified' | 'not_improved' | 'inconclusive';

export interface PageMeta {
  total: number;
  page: number;
  page_size: number;
  pages: number;
}

export interface Page<T> {
  items: T[];
  meta: PageMeta;
}

export interface ProjectStats {
  total_runs: number;
  success_runs: number;
  failed_runs: number;
  last_run_at: string | null;
}

export interface Project {
  project_id: string;
  name: string;
  description: string;
  settings: Record<string, unknown>;
  is_demo: boolean;
  created_at: string;
  updated_at: string;
  stats?: ProjectStats | null;
}

export interface KeyInfo {
  key_id: string;
  project_id: string;
  prefix: string;
  created_at: string;
  revoked_at: string | null;
  last_used_at: string | null;
  active: boolean;
}

export interface KeyIssued {
  key_id: string;
  project_id: string;
  api_key: string;
  prefix: string;
  created_at: string;
}

export interface Version {
  version_id: string;
  project_id: string;
  version: string;
  metadata: Record<string, unknown>;
  created_at: string;
  run_count: number | null;
}

export interface ProjectDetail {
  project: Project;
  keys: KeyInfo[];
  versions: Version[];
}

export interface ProjectCreated {
  project: Project;
  key: KeyIssued;
}

export interface Run {
  run_id: string;
  project_id: string;
  project_name: string | null;
  version_id: string | null;
  version: string | null;
  name: string;
  status: RunStatus;
  environment: string | null;
  started_at: string;
  finished_at: string | null;
  duration_ms: number | null;
  error_summary: string | null;
  summary: Record<string, unknown>;
  metadata: Record<string, unknown>;
  event_count: number;
  failed_event_count: number;
  is_demo: boolean;
  source: string;
}

export interface EventError {
  type?: string;
  message?: string;
  traceback?: string | null;
}

export interface RunEvent {
  event_id: string;
  run_id: string;
  project_id: string;
  sequence: number;
  event_type: string;
  name: string;
  status: string;
  timestamp: string;
  duration_ms: number | null;
  input_summary: unknown;
  output_summary: unknown;
  error: EventError | null;
  metadata: Record<string, unknown>;
}

export interface EventList {
  run_id: string;
  items: RunEvent[];
  total: number;
}

export interface EvidenceItem {
  kind: string;
  description: string;
  run_id?: string | null;
  event_id?: string | null;
  sequence?: number | null;
  step?: string | null;
  field?: string;
  value?: unknown;
}

export interface VerificationCheck {
  check: string;
  description: string;
  passed: boolean;
  observed: unknown;
  expected: unknown;
}

export interface Verification {
  run_id: string;
  checked_at: string;
  result: VerificationStatus;
  checks: VerificationCheck[];
  note: string;
}

export interface FindingDraft {
  category: string;
  severity: Severity;
  confidence: Severity;
  title: string;
  summary: string;
  observation: string;
  hypothesis: string;
  suggested_actions: string[];
  evidence: EvidenceItem[];
  regression_test: string | null;
  step: string | null;
  step_key?: string | null;
}

export interface Finding extends FindingDraft {
  finding_id: string;
  project_id: string;
  run_id: string;
  baseline_run_id: string | null;
  verification_status: VerificationStatus;
  verification: Verification | null;
  source: string;
  is_demo: boolean;
  created_at: string;
  updated_at: string;
}

export interface EventRef {
  event_id: string;
  run_id: string;
  sequence: number;
  name: string;
  event_type: string;
  status: string;
  duration_ms: number | null;
  timestamp: string | null;
  input_summary: unknown;
  output_summary: unknown;
  error: EventError | null;
  metadata: Record<string, unknown>;
}

export interface ChangeItem {
  path: string;
  kind: string;
  baseline?: unknown;
  comparison?: unknown;
  baseline_type?: string;
  comparison_type?: string;
}

export interface Difference {
  field: string;
  baseline?: unknown;
  comparison?: unknown;
  changes?: ChangeItem[];
  schema_changed?: boolean;
}

export interface Timing {
  baseline_ms: number;
  comparison_ms: number;
  delta_ms: number;
  ratio: number | null;
  notable: boolean;
}

export type EntryKind = 'unchanged' | 'changed' | 'added' | 'missing';

export interface CompareEntry {
  position: number;
  step_key: string;
  name: string;
  kind: EntryKind;
  baseline: EventRef | null;
  comparison: EventRef | null;
  reordered: boolean;
  differences: Difference[];
  timing: Timing | null;
  description: string | null;
}

export interface RunMeta {
  run_id: string;
  project_id: string;
  name: string;
  status: RunStatus;
  version: string | null;
  environment: string | null;
  started_at: string | null;
  finished_at: string | null;
  duration_ms: number | null;
  error_summary: string | null;
  event_count: number;
  is_demo: boolean;
  metadata: Record<string, unknown>;
}

export interface Divergence {
  position: number;
  step_key: string;
  name: string;
  kind: EntryKind;
  description: string;
  baseline_event_id: string | null;
  comparison_event_id: string | null;
  baseline_sequence: number | null;
  comparison_sequence: number | null;
  fields: string[];
}

export interface CompareResult {
  baseline: RunMeta;
  comparison: RunMeta;
  alignment_strategy: string;
  entries: CompareEntry[];
  summary: Record<string, number | boolean>;
  earliest_divergence: Divergence | null;
  first_failure: EventRef | null;
  run_differences: Difference[];
  warnings: string[];
  diagnosis?: { persisted: boolean; note: string; findings: FindingDraft[] };
}

export interface AnalyzeResponse {
  run_id: string;
  baseline_run_id: string | null;
  baseline_selection: string;
  findings: Finding[];
  comparison_summary: Record<string, unknown> | null;
}

export interface ActivityDay {
  date: string;
  total: number;
  success: number;
  failed: number;
  running: number;
}

export interface VersionMetric {
  version: string;
  total: number;
  success: number;
  failed: number;
  failure_rate: number | null;
}

export interface Metrics {
  scope: { project_id: string | null; days: number; since: string; include_demo: boolean };
  totals: {
    projects: number;
    runs: number;
    success: number;
    failed: number;
    timed_out: number;
    running: number;
    finished: number;
    all_time_runs: number;
  };
  success_rate: number | null;
  average_duration_ms: number | null;
  duration_sample_size: number;
  by_version: VersionMetric[];
  activity: ActivityDay[];
  findings: { total: number; high: number; verified: number; unverified: number };
  notes: string[];
  generated_at: string;
}

export interface Health {
  status: 'ok' | 'degraded';
  service: string;
  version: string;
  time: string;
  database: { connected: boolean; name: string; latency_ms: number | null; error: string | null; indexes_ready: boolean };
  auth_mode: 'open' | 'admin_token';
  ai: { enabled: boolean; model: string | null };
  limits: { max_request_bytes: number; max_events_per_batch: number };
}

export interface AIStatus {
  enabled: boolean;
  model: string | null;
  reason: string | null;
}

export interface AIChatResponse {
  source: 'ai_generated';
  model: string;
  answer: string;
  context: Record<string, unknown>;
  disclaimer: string;
}
