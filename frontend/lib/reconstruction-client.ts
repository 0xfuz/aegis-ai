import { apiFetch } from "@/lib/api-client";

export type ReconstructionJson = string | number | boolean | null | ReconstructionJson[] | { [key: string]: ReconstructionJson };

export type ReconstructionWarning = {
  section: string;
  reason: string;
  omitted: number;
};

export type ReconstructionOmission = {
  section: string;
  reason: string;
  original_count: number;
  returned_count: number;
};

export type ReconstructionActivity = {
  type: string;
  id: string;
  alias?: string | null;
  original_timestamp: string | null;
  effective_timestamp: string | null;
  time_basis: "SOURCE" | "RECEIPT" | "NONE";
  normalization: "UTC" | "UNAVAILABLE";
  uncertainty: string[];
  position: "ANCHOR" | "BEFORE" | "AFTER" | "OUTSIDE" | "UNKNOWN";
};

export type ReconstructionGap = {
  code: string;
  section: string;
  target_type: string | null;
  target_id: string | null;
  severity: "BLOCKING" | "WARNING" | "INFO";
  classification: "ABSENT" | "UNAVAILABLE" | "UNSUPPORTED" | "INCOMPLETE" | "OMITTED" | "INVALID" | "CONTRADICTORY";
  detail: string;
  provenance: string[];
};

export type ReconstructionCitation = {
  id: string;
  alias: string;
  type: string;
  context_version: string;
  builder_version: string;
  policy_version: string;
  locator: ReconstructionJson;
  producer: string | null;
  producer_version: string | null;
  claim_links: { claim_id: string; role: "SUPPORTS" | "CONTRADICTS" | "CONTEXT" }[];
  claim_links_omitted: number;
};

export type ReconstructionPromotion = {
  state: "AVAILABLE" | "UNAVAILABLE" | "DEGRADED" | "UNSUPPORTED";
  warning: string | null;
  promotion: { id: string; status: string; cluster_id: string; promoted_at: string } | null;
  correlation: {
    version: string;
    membership_count: number;
    memberships: { id: string; score: number; reasons: ReconstructionJson; added_at: string }[];
    memberships_omitted: number;
  } | null;
  triage: { id: string; status: "AVAILABLE"; priority: string; score: number; version: string } | null;
};

export type ReconstructionSections = {
  evidence: { id: string; sha256: string; status: string; imported_at: string }[];
  raw_records: { id: string; evidence_id: string; ordinal: number; content_type: string; locator: ReconstructionJson }[];
  events: { id: string; evidence_id: string; raw_record_id: string; timestamp: string | null; normalizer: string | null; version: string | null }[];
  entity_observations: { id: string; entity_id: string; raw_record_id: string; event_id: string | null; extractor: string | null; version: string | null }[];
  indicator_occurrences: { id: string; indicator_id: string; raw_record_id: string; event_id: string | null; extractor: string | null; version: string | null }[];
  relationships: { id: string; source_entity_id: string; target_entity_id: string; raw_record_id: string | null; event_id: string | null; derivation: string | null; version: string | null }[];
  citations: ReconstructionCitation[];
  findings: { id: string; title: string; status: string }[];
  mitre: { id: string; technique_id: string; status: string }[];
};

export type InvestigationReconstruction = {
  policy_id: string;
  investigation: { id: string; title: string; status: string };
  versions: { context: string; activity: string; gaps: string };
  context: { warnings: Array<{ code?: string; path?: string; returned?: number }>; omissions: ReconstructionOmission[]; section_counts: Record<string, number> };
  activity: { policy_id: string; anchor: { start: string; end: string } | null; activities: ReconstructionActivity[]; omitted: number; warnings: string[] };
  gaps: { policy_id: string; gaps: ReconstructionGap[]; omitted: number };
  promotion: ReconstructionPromotion;
  sections: ReconstructionSections;
  pagination: { section_omissions: Record<string, number>; total_omitted: number };
  warnings: ReconstructionWarning[];
};

export type ReconstructionRequestOptions = Pick<RequestInit, "signal">;

export function isInvestigationRouteId(value: unknown): value is string {
  return typeof value === "string" && value.trim().length > 0;
}

export function fetchInvestigationReconstruction(
  investigationId: string,
  options: ReconstructionRequestOptions = {},
): Promise<InvestigationReconstruction> {
  if (!isInvestigationRouteId(investigationId)) {
    return Promise.reject(new TypeError("A non-empty Investigation ID is required."));
  }
  return apiFetch<InvestigationReconstruction>(
    `/api/v1/investigations/${encodeURIComponent(investigationId)}/intelligence/reconstruction`,
    options,
  );
}
