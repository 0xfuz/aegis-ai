import { cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { ActivityWindowPanel, ReconstructionExplanation, ReconstructionGapPanel } from "@/components/investigations/reconstruction-explanation";
import type { InvestigationReconstruction } from "@/lib/reconstruction-client";

const base: InvestigationReconstruction = {
  policy_id: "reconstruction-read-v1", investigation: { id: "case-1", title: "Safe Investigation", status: "investigating" }, versions: { context: "phase8-context-v1", activity: "activity-window-v1", gaps: "reconstruction-gaps-v1" },
  context: { warnings: [], omissions: [{ section: "events", reason: "LIMIT", original_count: 12, returned_count: 10 }, { section: "raw_records", reason: "TOTAL_SIZE", original_count: 8, returned_count: 4 }], section_counts: { evidence: 2, events: 10, correlation_v2: 2 } },
  activity: { policy_id: "activity-window-v1", anchor: { start: "2026-01-01T00:00:00+00:00", end: "2026-01-01T00:05:00+00:00" }, omitted: 1, warnings: ["BEFORE_ACTIVITY_NOT_OBSERVED", "AFTER_ACTIVITY_NOT_OBSERVED"], activities: [
    { type: "EVENT", id: "first", original_timestamp: "2026-01-01T00:02:00+00:00", effective_timestamp: "2026-01-01T00:02:00+00:00", time_basis: "SOURCE", normalization: "UTC", uncertainty: ["EQUAL_TIMESTAMP_TIE"], position: "ANCHOR" },
    { type: "EVENT", id: "second", original_timestamp: null, effective_timestamp: "2026-01-01T00:03:00+00:00", time_basis: "RECEIPT", normalization: "UTC", uncertainty: ["SOURCE_TIME_MISSING", "RECEIPT_TIME_FALLBACK"], position: "AFTER" },
    { type: "EVIDENCE_ITEM", id: "outside", original_timestamp: "2025-12-31T00:00:00+00:00", effective_timestamp: "2025-12-31T00:00:00+00:00", time_basis: "SOURCE", normalization: "UTC", uncertainty: ["OUTSIDE_WINDOW", "OMITTED_BY_POLICY_LIMIT"], position: "OUTSIDE" },
  ] },
  gaps: { policy_id: "reconstruction-gaps-v1", omitted: 1, gaps: [
    { code: "EVENT_TIME_UNCERTAIN", section: "temporal", severity: "WARNING", classification: "CONTRADICTORY", detail: "Two compatible observations conflict.", target_type: "EVENT", target_id: "event-1", provenance: ["observation-a", "observation-b"] },
    { code: "RAW_CONTENT_UNAVAILABLE", section: "raw_records", severity: "WARNING", classification: "UNAVAILABLE", detail: "Raw content unavailable.", target_type: "RAW_RECORD", target_id: "raw-1", provenance: [] },
    { code: "CONTEXT_OMITTED_BY_TOTAL_SIZE", section: "events", severity: "INFO", classification: "OMITTED", detail: "TOTAL_SIZE:12", target_type: null, target_id: null, provenance: [] },
  ] },
  promotion: { state: "AVAILABLE", warning: null, promotion: { id: "promotion-1", status: "COMPLETED", cluster_id: "cluster-1", promoted_at: "2026-01-01T00:00:00+00:00" }, correlation: { version: "correlation-v2", membership_count: 0, memberships: [], memberships_omitted: 0 }, triage: { id: "triage-1", status: "AVAILABLE", priority: "HIGH", score: 73, version: "triage-v1" } },
  sections: { evidence: [], raw_records: [{ id: "raw-private", evidence_id: "e1", ordinal: 1, content_type: "text/plain", locator: { content: "never render raw content" } }], events: [], entity_observations: [], indicator_occurrences: [], relationships: [], citations: [], findings: [], mitre: [] }, pagination: { section_omissions: {}, total_omitted: 0 }, warnings: [{ section: "activities", reason: "LIMIT", omitted: 1 }],
};

afterEach(() => cleanup());

describe("reconstruction explanation panels", () => {
  it("renders certified overview values and only authoritative workspace links", () => {
    render(<ReconstructionExplanation investigationId="case-1" data={base} />);
    expect(screen.getByText("Safe Investigation")).toBeInTheDocument();
    expect(screen.getByText("Promoted correlation-v2 context")).toBeInTheDocument();
    expect(screen.getByText("LIMIT: events (10/12)")).toBeInTheDocument();
    expect(screen.getByText("TOTAL_SIZE: raw_records (4/8)")).toBeInTheDocument();
    expect(screen.getByText("activities: LIMIT (1)")).toBeInTheDocument();
    const links = screen.getByRole("navigation", { name: "Open factual investigation workspaces" });
    expect(within(links).getByRole("link", { name: "Evidence" })).toHaveAttribute("href", "/investigations/case-1/evidence");
    expect(within(links).getByRole("link", { name: "Attack Graph" })).toHaveAttribute("href", "/investigations/case-1/relationships");
    expect(within(links).queryByRole("link", { name: "Legacy attack graph" })).not.toBeInTheDocument();
    expect(within(links).queryByRole("link", { name: "Attack Graph" })?.getAttribute("href")).not.toContain("/attack-graph");
  });

  it("preserves server activity order, interval semantics, and uncertainty without recomputation", () => {
    render(<ActivityWindowPanel data={base} />);
    expect(screen.getByText("Anchor interval")).toBeInTheDocument();
    const activities = Array.from(screen.getByRole("list", { name: "Server-ordered reconstruction activities" }).children);
    expect(activities.map((item) => item.textContent)).toEqual(expect.arrayContaining([expect.stringContaining("first"), expect.stringContaining("second"), expect.stringContaining("outside")]));
    expect(activities[0]).toHaveTextContent("EVENT");
    expect(activities[1]).toHaveTextContent("RECEIPT");
    expect(activities[2]).toHaveTextContent("Outside the server-defined activity window.");
    expect(screen.getByLabelText("Uncertainty: EQUAL_TIMESTAMP_TIE")).toBeInTheDocument();
    expect(screen.getByText("Before/after expansion bounds are not exposed by the certified response. Relative positions below are server-authored and are not recalculated in the browser.")).toBeInTheDocument();
    expect(screen.getByLabelText("Uncertainty: BEFORE_ACTIVITY_NOT_OBSERVED")).toBeInTheDocument();
  });

  it("keeps no-anchor and evidence-only states unavailable rather than factual", () => {
    const data = { ...base, context: { ...base.context, section_counts: { evidence: 1 }, warnings: [{ code: "PROMOTION_LINK_MISSING" }, { code: "CORRELATION_VERSION_UNSUPPORTED" }] }, activity: { ...base.activity, anchor: null, activities: [] } };
    render(<ReconstructionExplanation investigationId="case-1" data={data} />);
    expect(screen.getByText("Degraded reconstruction")).toBeInTheDocument();
    expect(screen.getByLabelText("Uncertainty: PROMOTION_LINK_MISSING")).toBeInTheDocument();
    expect(screen.getByText("No temporal anchor is available. This is unavailable observation, not evidence that activity did not occur.")).toBeInTheDocument();
    expect(screen.getByText("No bounded activities are available for this reconstruction.")).toBeInTheDocument();
    expect(screen.getByLabelText("Uncertainty: CORRELATION_VERSION_UNSUPPORTED")).toBeInTheDocument();
  });

  it("labels evidence-only and point anchors without deriving chronology", () => {
    const data = {
      ...base,
      context: { ...base.context, section_counts: { evidence: 1 }, warnings: [] },
      activity: { ...base.activity, anchor: { start: "2026-01-01T00:00:00+00:00", end: "2026-01-01T00:00:00+00:00" }, activities: [] },
    };
    render(<ReconstructionExplanation investigationId="case-1" data={data} />);
    expect(screen.getByText("Evidence-only reconstruction")).toBeInTheDocument();
    expect(screen.getByText("Anchor point")).toBeInTheDocument();
  });

  it("renders all gap labels and retains both contradiction references without a winner", () => {
    const data = { ...base, gaps: { ...base.gaps, gaps: [...base.gaps.gaps, ...(["ABSENT", "INVALID", "INCOMPLETE", "UNSUPPORTED"] as const).map((classification) => ({ code: `${classification}_TEST`, section: "evidence", severity: "INFO" as const, classification, detail: `${classification} detail`, target_type: null, target_id: null, provenance: [] }))] } };
    render(<ReconstructionGapPanel data={data} />);
    for (const classification of ["ABSENT", "UNAVAILABLE", "INVALID", "INCOMPLETE", "CONTRADICTORY", "UNSUPPORTED", "OMITTED"]) {
      expect(screen.getByText(classification)).toBeInTheDocument();
    }
    expect(screen.getByText("Provenance references: observation-a, observation-b. Both references are retained; no winner is selected.")).toBeInTheDocument();
    expect(screen.getByText("Gaps describe reconstruction limits. They are not Facts, Findings, claims, or MITRE conclusions.")).toBeInTheDocument();
  });

  it("keeps hostile text inert and excludes raw response fields", () => {
    const hostile = { ...base, investigation: { ...base.investigation, title: "<img src=x onerror=alert(1)>" }, gaps: { ...base.gaps, gaps: [{ ...base.gaps.gaps[0]!, detail: "<script>never execute</script>" }] } };
    const { container } = render(<ReconstructionExplanation investigationId="case-1" data={hostile} />);
    expect(screen.getByText("<img src=x onerror=alert(1)>")).toBeInTheDocument();
    expect(screen.getByText("<script>never execute</script>")).toBeInTheDocument();
    expect(container.querySelector("img, script")).toBeNull();
    expect(screen.queryByText("never render raw content")).not.toBeInTheDocument();
  });
});
