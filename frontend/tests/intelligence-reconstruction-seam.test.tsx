import { render, screen } from "@testing-library/react";
import type { ReactNode } from "react";
import { describe, expect, it, vi } from "vitest";
import IntelligencePage from "@/app/(dashboard)/investigations/[id]/intelligence/page";
import type { InvestigationReconstruction } from "@/lib/reconstruction-client";

const apiFetch = vi.hoisted(() => vi.fn());
const reconstruction = vi.hoisted(() => vi.fn());
const auth = vi.hoisted(() => ({ canWrite: true, active: true }));

vi.mock("next/navigation", () => ({ useParams: () => ({ id: "case-42" }), usePathname: () => "/investigations/case-42/intelligence", useRouter: () => ({ replace: vi.fn() }), useSearchParams: () => new URLSearchParams() }));
vi.mock("next/link", () => ({ default: ({ href, children }: { href: string; children: ReactNode }) => <a href={href}>{children}</a> }));
vi.mock("@/lib/api-client", () => ({ apiFetch, ApiError: class ApiError extends Error {}, downloadFile: vi.fn() }));
vi.mock("@/lib/reconstruction-client", () => ({ isInvestigationRouteId: (value: unknown) => typeof value === "string" && value.length > 0, fetchInvestigationReconstruction: reconstruction }));
vi.mock("@/lib/auth-context", () => ({ useAuth: () => ({ user: { is_active: auth.active }, hasPermission: () => auth.canWrite }) }));

const response = { policy_id: "reconstruction-read-v1", investigation: { id: "case-42", title: "Case", status: "new" }, versions: { context: "context", activity: "activity", gaps: "gaps" }, context: { warnings: [], omissions: [], section_counts: {} }, activity: { policy_id: "activity", anchor: null, activities: [], omitted: 0, warnings: [] }, gaps: { policy_id: "gaps", gaps: [], omitted: 0 }, promotion: { state: "UNAVAILABLE", warning: "PROMOTION_LINK_MISSING", promotion: null, correlation: null, triage: null }, sections: { evidence: [], raw_records: [], events: [], entity_observations: [], indicator_occurrences: [], relationships: [], citations: [], findings: [], mitre: [] }, pagination: { section_omissions: {}, total_omitted: 0 }, warnings: [] } as InvestigationReconstruction;

describe("Intelligence reconstruction fetch seam", () => {
  it("acknowledges the certified reconstruction without replacing the legacy notebook", async () => {
    reconstruction.mockResolvedValue(response);
    apiFetch.mockResolvedValue({ items: [], limit: 20, offset: 0 });
    render(<IntelligencePage />);
    expect(await screen.findByRole("heading", { name: "Certified reconstruction overview" })).toBeInTheDocument();
    expect(reconstruction).toHaveBeenCalledWith("case-42", expect.objectContaining({ signal: expect.any(AbortSignal) }));
    expect(screen.getByRole("button", { name: "Run analysis" })).toBeInTheDocument();
  });

  it("only exposes review controls to an active principal with investigation write permission", async () => {
    reconstruction.mockResolvedValue(response);
    const completed = { id: "run-1", investigation_id: "case-42", status: "COMPLETED", request_key: "ui:test", input_hash: "hash", predecessor_analysis_id: null, context_version: null, builder_version: null, prompt_template_version: "prompt", output_schema_version: "schema", generated_at: null, created_at: "2026-01-01T00:00:00Z", updated_at: "2026-01-01T00:00:00Z", error_summary: null };
    apiFetch.mockResolvedValueOnce({ items: [completed], limit: 20, offset: 0 }).mockResolvedValueOnce({ status: "COMPLETED", generated_at: null, items: [{ id: "claim-1", kind: "OBSERVATION", claim_type: "OBSERVATION", origin: "AI", statement: "reviewable", confidence: 50, review_status: "PENDING", fact_links: [] }] });
    auth.canWrite = false;
    const view = render(<IntelligencePage />);
    await screen.findByText("reviewable");
    expect(screen.queryByRole("button", { name: /Review OBSERVATION/ })).toBeNull();
    auth.canWrite = true;
    auth.active = false;
    view.rerender(<IntelligencePage />);
    expect(screen.queryByRole("button", { name: /Review OBSERVATION/ })).toBeNull();
    auth.active = true;
    view.rerender(<IntelligencePage />);
    expect(screen.getByRole("button", { name: "Review OBSERVATION claim as CONFIRMED" })).toBeInTheDocument();
  });
});
