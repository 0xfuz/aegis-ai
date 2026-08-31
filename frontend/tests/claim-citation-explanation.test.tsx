import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { CitationList, ClaimExplanationPanel, PromotionExplanationPanel, type IntelligenceAnalysisRead } from "@/components/investigations/claim-citation-explanation";
import type { InvestigationReconstruction } from "@/lib/reconstruction-client";

const data: InvestigationReconstruction = {
  policy_id: "reconstruction-read-v1", investigation: { id: "case-1", title: "Safe", status: "NEW" }, versions: { context: "context", activity: "activity", gaps: "gaps" }, context: { warnings: [], omissions: [], section_counts: {} }, activity: { policy_id: "activity", anchor: null, activities: [], omitted: 0, warnings: [] }, gaps: { policy_id: "gaps", gaps: [], omitted: 0 },
  promotion: { state: "AVAILABLE", warning: null, promotion: { id: "promotion-1", status: "COMPLETED", cluster_id: "cluster-1", promoted_at: "2026-01-01T00:00:00Z" }, correlation: { version: "correlation-v2", membership_count: 2, memberships: [{ id: "member-1", score: 88, reasons: { observable: "198.51.100.4" }, added_at: "2026-01-01T00:00:00Z" }], memberships_omitted: 1 }, triage: { id: "triage-1", status: "AVAILABLE", priority: "HIGH", score: 74, version: "triage-v1" } },
  sections: { evidence: [], raw_records: [], events: [], entity_observations: [], indicator_occurrences: [], relationships: [], citations: [
    { id: "citation-1", alias: "EV1", type: "EVENT", context_version: "context", builder_version: "builder", policy_version: "policy", locator: { line: 1 }, producer: "normalizer", producer_version: "1", claim_links: [{ claim_id: "claim-1", role: "SUPPORTS" }, { claim_id: "claim-2", role: "CONTRADICTS" }], claim_links_omitted: 1 },
    { id: "citation-2", alias: "E1", type: "FINDING", context_version: "context", builder_version: "builder", policy_version: "policy", locator: {}, producer: null, producer_version: null, claim_links: [{ claim_id: "claim-1", role: "CONTEXT" }], claim_links_omitted: 0 },
    { id: "citation-3", alias: "RR1", type: "RAW_RECORD", context_version: "context", builder_version: "builder", policy_version: "policy", locator: {}, producer: null, producer_version: null, claim_links: [], claim_links_omitted: 0 },
  ], findings: [], mitre: [] }, pagination: { section_omissions: {}, total_omitted: 0 }, warnings: [],
};

const analysis: IntelligenceAnalysisRead = { status: "COMPLETED", generated_at: null, items: [
  { id: "claim-1", kind: "FACT", claim_type: "FACT", origin: "DETERMINISTIC_ENGINE", statement: "Deterministic fact", confidence: 100, review_status: "CONFIRMED", fact_links: [] },
  { id: "claim-2", kind: "OBSERVATION", claim_type: "OBSERVATION", origin: "AI", statement: "<img src=x onerror=alert(1)>", confidence: 61, review_status: "PENDING", fact_links: [] },
  { id: "claim-3", kind: "INFERENCE", claim_type: "INFERENCE", origin: "AI", statement: "Inference", confidence: null, review_status: "REJECTED", fact_links: [] },
  { id: "claim-4", kind: "HYPOTHESIS", claim_type: "HYPOTHESIS", origin: "ANALYST", statement: "Hypothesis", confidence: null, review_status: "UNRESOLVED", fact_links: [] },
  { id: "claim-5", kind: "RECOMMENDATION", claim_type: "RECOMMENDATION", origin: "AI", statement: "Advice", confidence: null, review_status: "SUPERSEDED", fact_links: [] },
] };

afterEach(() => cleanup());

describe("claim and citation explanation", () => {
  it("renders every many-to-many citation role, unlinked state, and same-page keyboard target", () => {
    render(<><CitationList data={data} /><ClaimExplanationPanel analysis={analysis} loadError={null} citations={data.sections.citations} /></>);
    expect(screen.getAllByText(/Evidence consistent with this claim/).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/Evidence in tension with this claim/).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/Relevant context; not proof of the claim/).length).toBeGreaterThan(0);
    expect(screen.getByText("1 claim links omitted by the server bound.")).toBeInTheDocument();
    expect(screen.getByText("Unlinked citation — no scoped intelligence claim link is available.")).toBeInTheDocument();
    expect(screen.getByText("Finding/MITRE citation: CONTEXT-only.")).toBeInTheDocument();
    fireEvent.click(screen.getAllByRole("button", { name: "Claim claim-1" })[0]!);
    expect(document.activeElement).toHaveAttribute("id", "claim-claim-1");
    expect(screen.getByText(/FACT: deterministic origin required/)).toBeInTheDocument();
    expect(screen.getByText(/SUPPORTS: EV1 \(EVENT\)/)).toBeInTheDocument();
    expect(screen.getByText(/CONTEXT: E1 \(FINDING\)/)).toBeInTheDocument();
  });

  it("renders claim semantics and all review states without authority escalation or HTML execution", () => {
    const { container } = render(<ClaimExplanationPanel analysis={analysis} loadError={null} />);
    for (const status of ["PENDING", "CONFIRMED", "REJECTED", "UNRESOLVED", "SUPERSEDED"]) expect(screen.getByText(`Review: ${status}`)).toBeInTheDocument();
    expect(screen.getByText("Reviewable AI output.")).toBeInTheDocument();
    expect(screen.getAllByText("Not established fact.")).toHaveLength(2);
    expect(screen.getByText("Advisory only — no action executed.")).toBeInTheDocument();
    expect(screen.getByText("<img src=x onerror=alert(1)>")).toBeInTheDocument();
    expect(container.querySelector("img")).toBeNull();
  });

  it("keeps no-claim and failed/cancelled run states safe and distinct", () => {
    const view = render(<ClaimExplanationPanel analysis={{ status: "COMPLETED", generated_at: null, items: [] }} loadError={null} />);
    expect(screen.getByText("No intelligence claims generated yet.")).toBeInTheDocument();
    view.rerender(<ClaimExplanationPanel analysis={{ status: "FAILED", generated_at: null, items: [] }} loadError={null} />);
    expect(screen.getByRole("status")).toHaveTextContent("Deterministic reconstruction remains available");
    view.rerender(<ClaimExplanationPanel analysis={null} loadError="No intelligence analysis yet." />);
    expect(screen.getByText("No intelligence analysis yet.")).toBeInTheDocument();
  });

  it("renders persisted v2 promotion and fails closed for unsupported/degraded variants", () => {
    const view = render(<PromotionExplanationPanel data={data} />);
    expect(screen.getByText("Correlation version")).toBeInTheDocument();
    expect(screen.getByText("correlation-v2")).toBeInTheDocument();
    expect(screen.getByText("Triage priority / score")).toBeInTheDocument();
    expect(screen.getByText("HIGH / 74")).toBeInTheDocument();
    expect(screen.getByText("1 membership summaries omitted by the server bound.")).toBeInTheDocument();
    view.rerender(<PromotionExplanationPanel data={{ ...data, promotion: { ...data.promotion, state: "UNSUPPORTED", warning: "CORRELATION_V1_CONTEXT_UNSUPPORTED", correlation: { version: "correlation-v1", membership_count: 0, memberships: [], memberships_omitted: 0 }, triage: null } }} />);
    expect(screen.getByText(/UNSUPPORTED · CORRELATION_V1_CONTEXT_UNSUPPORTED/)).toBeInTheDocument();
    expect(screen.getByText("correlation-v1")).toBeInTheDocument();
  });
});
