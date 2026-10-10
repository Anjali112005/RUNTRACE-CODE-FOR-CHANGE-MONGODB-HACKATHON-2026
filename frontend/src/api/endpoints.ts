import { apiRequest } from './client';
import type {
  AIChatResponse,
  AIStatus,
  AnalyzeResponse,
  CompareResult,
  EventList,
  Finding,
  Health,
  KeyIssued,
  Metrics,
  Page,
  Project,
  ProjectCreated,
  ProjectDetail,
  Run,
  Version,
} from '../types/api';

export interface ProjectListParams {
  q?: string;
  include_demo?: boolean;
  page?: number;
  page_size?: number;
}

export interface RunListParams {
  project_id?: string;
  status?: string;
  q?: string;
  version?: string;
  include_demo?: boolean;
  page?: number;
  page_size?: number;
}

export interface FindingListParams {
  project_id?: string;
  run_id?: string;
  severity?: string;
  category?: string;
  verification_status?: string;
  q?: string;
  include_demo?: boolean;
  page?: number;
  page_size?: number;
}

export interface ProjectInput {
  name: string;
  description?: string;
  settings?: { environment?: string };
}

export const api = {
  health: () => apiRequest<Health>('/health'),

  listProjects: (params: ProjectListParams = {}) => apiRequest<Page<Project>>('/api/projects', { query: { ...params } }),
  getProject: (id: string) => apiRequest<ProjectDetail>(`/api/projects/${encodeURIComponent(id)}`),
  createProject: (input: ProjectInput) => apiRequest<ProjectCreated>('/api/projects', { method: 'POST', body: input }),
  updateProject: (id: string, input: Partial<ProjectInput>) =>
    apiRequest<Project>(`/api/projects/${encodeURIComponent(id)}`, { method: 'PATCH', body: input }),
  rotateKey: (id: string, revokeExisting = true) =>
    apiRequest<KeyIssued>(`/api/projects/${encodeURIComponent(id)}/keys/rotate`, {
      method: 'POST',
      body: { revoke_existing: revokeExisting },
    }),
  revokeKey: (id: string, keyId?: string) =>
    apiRequest<{ revoked: string[] }>(`/api/projects/${encodeURIComponent(id)}/keys/revoke`, {
      method: 'POST',
      body: keyId ? { key_id: keyId } : {},
    }),
  createVersion: (id: string, version: string, metadata: Record<string, unknown> = {}) =>
    apiRequest<Version>(`/api/projects/${encodeURIComponent(id)}/versions`, { method: 'POST', body: { version, metadata } }),

  listRuns: (params: RunListParams = {}) => apiRequest<Page<Run>>('/api/runs', { query: { ...params } }),
  getRun: (id: string) => apiRequest<Run>(`/api/runs/${encodeURIComponent(id)}`),
  getRunEvents: (id: string) => apiRequest<EventList>(`/api/runs/${encodeURIComponent(id)}/events`),
  getRunFindings: (id: string) => apiRequest<Finding[]>(`/api/runs/${encodeURIComponent(id)}/findings`),
  analyzeRun: (id: string, baselineRunId?: string) =>
    apiRequest<AnalyzeResponse>(`/api/runs/${encodeURIComponent(id)}/analyze`, {
      method: 'POST',
      body: baselineRunId ? { baseline_run_id: baselineRunId } : {},
    }),

  compare: (baselineRunId: string, comparisonRunId: string) =>
    apiRequest<CompareResult>('/api/compare', {
      method: 'POST',
      body: { baseline_run_id: baselineRunId, comparison_run_id: comparisonRunId, include_diagnosis: true },
    }),

  listFindings: (params: FindingListParams = {}) => apiRequest<Page<Finding>>('/api/findings', { query: { ...params } }),
  getFinding: (id: string) => apiRequest<Finding>(`/api/findings/${encodeURIComponent(id)}`),
  verifyFinding: (id: string, runId: string) =>
    apiRequest<Finding>(`/api/findings/${encodeURIComponent(id)}/verify`, { method: 'POST', body: { run_id: runId } }),

  metrics: (params: { project_id?: string; days?: number; include_demo?: boolean } = {}) =>
    apiRequest<Metrics>('/api/metrics', { query: { ...params } }),

  aiStatus: () => apiRequest<AIStatus>('/api/ai/status'),
  aiChat: (question: string, refs: { run_id?: string; finding_id?: string }) =>
    apiRequest<AIChatResponse>('/api/ai/chat', { method: 'POST', body: { question, ...refs } }),
};
