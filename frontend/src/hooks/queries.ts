import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { api, type FindingListParams, type ProjectInput, type ProjectListParams, type RunListParams } from '../api/endpoints';

export const keys = {
  health: ['health'] as const,
  projects: (p: ProjectListParams) => ['projects', p] as const,
  project: (id: string) => ['project', id] as const,
  runs: (p: RunListParams) => ['runs', p] as const,
  run: (id: string) => ['run', id] as const,
  events: (id: string) => ['run', id, 'events'] as const,
  runFindings: (id: string) => ['run', id, 'findings'] as const,
  findings: (p: FindingListParams) => ['findings', p] as const,
  metrics: (p: object) => ['metrics', p] as const,
  aiStatus: ['ai-status'] as const,
};

export function useHealth() {
  return useQuery({ queryKey: keys.health, queryFn: api.health, refetchInterval: 15_000, retry: false });
}

export function useProjects(params: ProjectListParams = {}) {
  return useQuery({ queryKey: keys.projects(params), queryFn: () => api.listProjects(params), placeholderData: keepPreviousData });
}

export function useProject(id: string | undefined) {
  return useQuery({ queryKey: keys.project(id ?? ''), queryFn: () => api.getProject(id!), enabled: Boolean(id) });
}

export function useRuns(params: RunListParams = {}, enabled = true) {
  return useQuery({ queryKey: keys.runs(params), queryFn: () => api.listRuns(params), placeholderData: keepPreviousData, enabled });
}

export function useRun(id: string | undefined) {
  return useQuery({ queryKey: keys.run(id ?? ''), queryFn: () => api.getRun(id!), enabled: Boolean(id) });
}

export function useRunEvents(id: string | undefined) {
  return useQuery({ queryKey: keys.events(id ?? ''), queryFn: () => api.getRunEvents(id!), enabled: Boolean(id) });
}

export function useRunFindings(id: string | undefined) {
  return useQuery({ queryKey: keys.runFindings(id ?? ''), queryFn: () => api.getRunFindings(id!), enabled: Boolean(id) });
}

export function useFindings(params: FindingListParams = {}) {
  return useQuery({ queryKey: keys.findings(params), queryFn: () => api.listFindings(params), placeholderData: keepPreviousData });
}

export function useFinding(id: string | null | undefined) {
  return useQuery({ queryKey: ['finding', id ?? ''], queryFn: () => api.getFinding(id!), enabled: Boolean(id) });
}

export function useMetrics(params: { project_id?: string; days?: number; include_demo?: boolean } = {}) {
  return useQuery({ queryKey: keys.metrics(params), queryFn: () => api.metrics(params), placeholderData: keepPreviousData });
}

export function useAIStatus() {
  return useQuery({ queryKey: keys.aiStatus, queryFn: api.aiStatus, staleTime: 60_000 });
}

// --- mutations -------------------------------------------------------------------

export function useCreateProject() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (input: ProjectInput) => api.createProject(input),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['projects'] });
      qc.invalidateQueries({ queryKey: ['metrics'] });
    },
  });
}

export function useUpdateProject(id: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (input: Partial<ProjectInput>) => api.updateProject(id, input),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: keys.project(id) });
      qc.invalidateQueries({ queryKey: ['projects'] });
    },
  });
}

export function useRotateKey(id: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (revokeExisting: boolean) => api.rotateKey(id, revokeExisting),
    onSuccess: () => qc.invalidateQueries({ queryKey: keys.project(id) }),
  });
}

export function useRevokeKey(id: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (keyId?: string) => api.revokeKey(id, keyId),
    onSuccess: () => qc.invalidateQueries({ queryKey: keys.project(id) }),
  });
}

export function useCreateVersion(id: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (version: string) => api.createVersion(id, version),
    onSuccess: () => qc.invalidateQueries({ queryKey: keys.project(id) }),
  });
}

export function useAnalyzeRun() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ runId, baselineRunId }: { runId: string; baselineRunId?: string }) => api.analyzeRun(runId, baselineRunId),
    onSuccess: (_data, vars) => {
      qc.invalidateQueries({ queryKey: keys.runFindings(vars.runId) });
      qc.invalidateQueries({ queryKey: ['findings'] });
      qc.invalidateQueries({ queryKey: ['metrics'] });
    },
  });
}

export function useCompare() {
  return useMutation({
    mutationFn: ({ baseline, comparison }: { baseline: string; comparison: string }) => api.compare(baseline, comparison),
  });
}

export function useVerifyFinding() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ findingId, runId }: { findingId: string; runId: string }) => api.verifyFinding(findingId, runId),
    onSuccess: (finding) => {
      qc.invalidateQueries({ queryKey: ['findings'] });
      qc.invalidateQueries({ queryKey: ['finding', finding.finding_id] });
      qc.invalidateQueries({ queryKey: keys.runFindings(finding.run_id) });
      qc.invalidateQueries({ queryKey: ['metrics'] });
    },
  });
}

export function useAIChat() {
  return useMutation({
    mutationFn: ({ question, run_id, finding_id }: { question: string; run_id?: string; finding_id?: string }) =>
      api.aiChat(question, { run_id, finding_id }),
  });
}
