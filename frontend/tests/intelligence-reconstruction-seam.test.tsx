import { render, screen } from "@testing-library/react";
import type { ReactNode } from "react";
import { describe, expect, it, vi } from "vitest";
import IntelligencePage from "@/app/(dashboard)/investigations/[id]/intelligence/page";
import type { InvestigationReconstruction } from "@/lib/reconstruction-client";

const apiFetch = vi.hoisted(() => vi.fn());
const reconstruction = vi.hoisted(() => vi.fn());

vi.mock("next/navigation", () => ({ useParams: () => ({ id: "case-42" }), usePathname: () => "/investigations/case-42/intelligence" }));
vi.mock("next/link", () => ({ default: ({ href, children }: { href: string; children: ReactNode }) => <a href={href}>{children}</a> }));
vi.mock("@/lib/api-client", () => ({ apiFetch, ApiError: class ApiError extends Error {}, downloadFile: vi.fn() }));
vi.mock("@/lib/reconstruction-client", () => ({ isInvestigationRouteId: (value: unknown) => typeof value === "string" && value.length > 0, fetchInvestigationReconstruction: reconstruction }));

const response = { policy_id: "reconstruction-read-v1", investigation: { id: "case-42", title: "Case", status: "new" }, versions: { context: "context", activity: "activity", gaps: "gaps" }, context: { warnings: [], omissions: [], section_counts: {} }, activity: { policy_id: "activity", anchor: null, activities: [], omitted: 0, warnings: [] }, gaps: { policy_id: "gaps", gaps: [], omitted: 0 }, promotion: { state: "UNAVAILABLE", warning: "PROMOTION_LINK_MISSING", promotion: null, correlation: null, triage: null }, sections: { evidence: [], raw_records: [], events: [], entity_observations: [], indicator_occurrences: [], relationships: [], citations: [], findings: [], mitre: [] }, pagination: { section_omissions: {}, total_omitted: 0 }, warnings: [] } as InvestigationReconstruction;

describe("Intelligence reconstruction fetch seam", () => {
  it("acknowledges the certified reconstruction without replacing the legacy notebook", async () => {
    reconstruction.mockResolvedValue(response);
    apiFetch.mockResolvedValue({ status: "COMPLETED", generated_at: null, items: [] });
    render(<IntelligencePage />);
    expect(await screen.findByRole("heading", { name: "Certified reconstruction overview" })).toBeInTheDocument();
    expect(reconstruction).toHaveBeenCalledWith("case-42", expect.objectContaining({ signal: expect.any(AbortSignal) }));
    expect(screen.getByRole("button", { name: "Run analysis" })).toBeInTheDocument();
  });
});
