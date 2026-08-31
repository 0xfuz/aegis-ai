import { apiFetch } from "@/lib/api-client";
import { isInvestigationRouteId } from "@/lib/reconstruction-client";

export type IntelligenceRunStatus = "QUEUED" | "RUNNING" | "COMPLETED" | "FAILED" | "CANCELLED";

export type IntelligenceRun = {
  id: string;
  investigation_id: string;
  status: IntelligenceRunStatus;
  request_key: string;
  input_hash: string;
  predecessor_analysis_id: string | null;
  context_version: string | null;
  builder_version: string | null;
  prompt_template_version: string;
  output_schema_version: string;
  generated_at: string | null;
  created_at: string;
  updated_at: string;
  error_summary: string | null;
};

type IntelligenceRunList = { items: IntelligenceRun[]; limit: number; offset: number };
export type IntelligenceRunRequestOptions = Pick<RequestInit, "signal">;
export type IntelligenceAnalysisRequestOptions = Pick<RequestInit, "signal">;

function route(investigationId: string) {
  if (!isInvestigationRouteId(investigationId)) throw new TypeError("A non-empty Investigation ID is required.");
  return `/api/v1/investigations/${encodeURIComponent(investigationId)}/intelligence/runs`;
}

export function queueIntelligenceRun(investigationId: string, requestKey: string): Promise<IntelligenceRun> {
  return apiFetch<IntelligenceRun>(route(investigationId), { method: "POST", body: JSON.stringify({ request_key: requestKey }) });
}

export function fetchIntelligenceRun(investigationId: string, runId: string, options: IntelligenceRunRequestOptions = {}): Promise<IntelligenceRun> {
  if (!runId) return Promise.reject(new TypeError("An Intelligence Run ID is required."));
  return apiFetch<IntelligenceRun>(`${route(investigationId)}/${encodeURIComponent(runId)}`, options);
}

export function listIntelligenceRuns(investigationId: string, options: IntelligenceRunRequestOptions = {}): Promise<IntelligenceRunList> {
  return apiFetch<IntelligenceRunList>(`${route(investigationId)}?limit=20&offset=0`, options);
}

export function fetchIntelligenceAnalysis<T>(investigationId: string, runId?: string | null, options: IntelligenceAnalysisRequestOptions = {}): Promise<T> {
  const selected = runId ? `?run_id=${encodeURIComponent(runId)}` : "";
  return apiFetch<T>(`/api/v1/investigations/${encodeURIComponent(investigationId)}/intelligence${selected}`, options);
}

export function isActiveIntelligenceRun(run: IntelligenceRun | null): boolean {
  return run?.status === "QUEUED" || run?.status === "RUNNING";
}

export function createIntelligenceRunRequestKey(): string {
  const suffix = typeof crypto !== "undefined" && typeof crypto.randomUUID === "function"
    ? crypto.randomUUID().replaceAll("-", "")
    : `${Date.now().toString(36)}${Math.random().toString(36).slice(2, 12)}`;
  return `ui:${suffix}`;
}
