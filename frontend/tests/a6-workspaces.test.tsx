import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import FindingsPage from "@/app/(dashboard)/investigations/[id]/findings/page";
import MitrePage from "@/app/(dashboard)/investigations/[id]/mitre/page";
import IntelligencePage from "@/app/(dashboard)/investigations/[id]/intelligence/page";
import { OverviewWorkspace } from "@/components/investigations/factual-workspace";
import { ApiError } from "@/lib/api-client";

const state = vi.hoisted(() => ({ apiFetch: vi.fn() }));
const reconstruction = vi.hoisted(() => ({ fetch: vi.fn() }));
const reconstructionResponse = {
  policy_id: "reconstruction-read-v1",
  investigation: { id: "case-1", title: "Case", status: "OPEN" },
  versions: { context: "phase8-context-v1", activity: "activity-window-v1", gaps: "reconstruction-gaps-v1" },
  context: { warnings: [], omissions: [], section_counts: {} },
  activity: { policy_id: "activity-window-v1", anchor: null, activities: [], omitted: 0, warnings: [] },
  gaps: { policy_id: "reconstruction-gaps-v1", gaps: [], omitted: 0 },
  promotion: { state: "UNAVAILABLE", warning: "PROMOTION_LINK_MISSING", promotion: null, correlation: null, triage: null },
  sections: { evidence: [], raw_records: [], events: [], entity_observations: [], indicator_occurrences: [], relationships: [], citations: [], findings: [], mitre: [] },
  pagination: { section_omissions: {}, total_omitted: 0 },
  warnings: [],
};
vi.mock("next/navigation", () => ({ useParams: () => ({ id: "case-1" }), usePathname: () => "/investigations/case-1/findings" }));
vi.mock("next/link", () => ({ default: ({ href, children }: { href: string; children: ReactNode }) => <a href={href}>{children}</a> }));
vi.mock("@/lib/api-client", async () => ({ ...(await vi.importActual<typeof import("@/lib/api-client")>("@/lib/api-client")), apiFetch: state.apiFetch }));
vi.mock("@/lib/reconstruction-client", () => ({ isInvestigationRouteId: (value: unknown) => typeof value === "string" && value.length > 0, fetchInvestigationReconstruction: reconstruction.fetch }));
vi.mock("@/lib/auth-context", () => ({ useAuth: () => ({ user: { is_active: true }, hasPermission: () => true }) }));

const findings = ["OPEN", "CONFIRMED", "DISMISSED", "RESOLVED"].map((status, index) => ({ id: String(index), title: status, description: "finding detail", severity: "high", confidence: 80, status, source_intelligence_item_id: index ? null : "ai-1", fact_links: [{ fact_id: "fact-1", fact_type: "EVENT", role: "SUPPORTS" }] }));
const mappings = ["PROPOSED", "CONFIRMED", "REJECTED"].map((status, index) => ({ id: String(index), technique_id: `T10${index}`, technique_name: "Technique", tactic: "execution", confidence: 70, ai_rationale: "mapping rationale", status, source_intelligence_item_id: index === 0 ? "ai-1" : null, finding_id: index === 1 ? "finding-1" : null, fact_links: [{ fact_id: "event-1", role: "SUPPORTS" }] }));

describe("A6 workspaces", () => {
  beforeEach(() => { state.apiFetch.mockReset(); reconstruction.fetch.mockReset(); reconstruction.fetch.mockResolvedValue(reconstructionResponse); });
  afterEach(() => { cleanup(); vi.restoreAllMocks(); });

  it("renders all finding states, AI source, and FACT provenance", async () => {
    state.apiFetch.mockResolvedValue(findings);
    render(<FindingsPage />);
    for (const status of ["OPEN", "CONFIRMED", "DISMISSED", "RESOLVED"]) expect((await screen.findAllByText(status)).length).toBeGreaterThan(0);
    expect(screen.getByText("ai-1")).toBeInTheDocument();
    expect(screen.getAllByText(/FACT provenance/)).toHaveLength(4);
    expect(screen.getAllByText("finding detail")).toHaveLength(4);
  });

  it("handles finding loading, empty, and API-error states", async () => {
    let resolve!: (value: typeof findings) => void;
    state.apiFetch.mockReturnValueOnce(new Promise<typeof findings>(done => { resolve = done; }));
    const { unmount } = render(<FindingsPage />);
    expect(screen.getByText("Loading findings…")).toBeInTheDocument();
    resolve([]);
    expect(await screen.findByText("No analyst findings yet.")).toBeInTheDocument();
    unmount();
    state.apiFetch.mockRejectedValueOnce(new ApiError("findings unavailable", 500));
    render(<FindingsPage />);
    expect(await screen.findByText("findings unavailable")).toBeInTheDocument();
  });

  it("submits a finding status change and reloads findings", async () => {
    state.apiFetch.mockResolvedValueOnce(findings).mockResolvedValueOnce({}).mockResolvedValueOnce(findings);
    render(<FindingsPage />);
    const confirm = (await screen.findAllByRole("button", { name: "CONFIRMED" }))[0];
    expect(confirm).toBeDefined();
    fireEvent.click(confirm!);
    await waitFor(() => expect(state.apiFetch).toHaveBeenCalledWith("/api/v1/investigations/findings/0/status", expect.objectContaining({ method: "POST" })));
  });

  it("only exposes conversion for confirmed eligible intelligence and reloads after conversion", async () => {
    const analysis = { status: "COMPLETED", generated_at: null, items: [{ id: "a", kind: "OBSERVATION", claim_type: "OBSERVATION", origin: "AI", statement: "confirmed", confidence: 80, review_status: "CONFIRMED", fact_links: [{ fact_id: "event-1", role: "SUPPORTS" }] }, { id: "u", kind: "OBSERVATION", claim_type: "OBSERVATION", origin: "AI", statement: "unreviewed", confidence: 80, review_status: "PENDING", fact_links: [] }, { id: "r", kind: "OBSERVATION", claim_type: "OBSERVATION", origin: "AI", statement: "rejected", confidence: 80, review_status: "REJECTED", fact_links: [] }] };
    state.apiFetch.mockImplementation((path: string) => {
      if (path.endsWith("/intelligence/runs?limit=20&offset=0")) return Promise.resolve({ items: [], limit: 20, offset: 0 });
      if (path.endsWith("/intelligence/items/a/finding")) return Promise.resolve({});
      if (path.endsWith("/intelligence")) return Promise.resolve(analysis);
      return Promise.resolve({});
    });
    render(<IntelligencePage />);
    fireEvent.click(await screen.findByText("Observation"));
    expect(screen.getAllByText("Convert to Finding")).toHaveLength(1);
    fireEvent.click(screen.getByText("Convert to Finding"));
    await waitFor(() => expect(state.apiFetch).toHaveBeenCalledWith("/api/v1/investigations/intelligence/items/a/finding", expect.objectContaining({ method: "POST" })));
    expect(screen.getAllByText("unreviewed").length).toBeGreaterThan(0);
    expect(screen.getAllByText("rejected").length).toBeGreaterThan(0);
  });

  it("surfaces an intelligence conversion API failure", async () => {
    const analysis = { status: "COMPLETED", generated_at: null, items: [{ id: "a", kind: "OBSERVATION", claim_type: "OBSERVATION", origin: "AI", statement: "confirmed", confidence: 80, review_status: "CONFIRMED", fact_links: [] }] };
    state.apiFetch.mockImplementation((path: string) => {
      if (path.endsWith("/intelligence/runs?limit=20&offset=0")) return Promise.resolve({ items: [], limit: 20, offset: 0 });
      if (path.endsWith("/intelligence/items/a/finding")) return Promise.reject(new ApiError("conversion failed", 422));
      if (path.endsWith("/intelligence")) return Promise.resolve(analysis);
      return Promise.resolve({});
    });
    render(<IntelligencePage />);
    fireEvent.click(await screen.findByText("Observation"));
    fireEvent.click(screen.getByText("Convert to Finding"));
    expect(await screen.findByText("conversion failed")).toBeInTheDocument();
  });

  it("renders MITRE states with sources and FACT provenance", async () => {
    state.apiFetch.mockResolvedValue(mappings);
    render(<MitrePage />);
    for (const heading of ["Proposed", "Confirmed", "Rejected"]) expect(await screen.findByText(heading)).toBeInTheDocument();
    expect(screen.getByText("Source: AI inference ai-1")).toBeInTheDocument();
    expect(screen.getByText("Source: Finding finding-1")).toBeInTheDocument();
    expect(screen.getAllByText(/Supporting FACTs: event-1/)).toHaveLength(3);
  });

  it("confirms and rejects proposed MITRE mappings with rationale", async () => {
    vi.spyOn(window, "prompt").mockReturnValue("not applicable");
    state.apiFetch.mockResolvedValue(mappings);
    render(<MitrePage />);
    await screen.findByText("Proposed");
    fireEvent.click(screen.getByText("Confirm"));
    await waitFor(() => expect(state.apiFetch).toHaveBeenCalledWith("/api/v1/investigations/mitre-mappings/0/review", expect.objectContaining({ method: "POST", body: JSON.stringify({ status: "CONFIRMED", rationale: "Confirmed by analyst" }) })));
    fireEvent.click(screen.getByText("Reject"));
    await waitFor(() => expect(state.apiFetch).toHaveBeenCalledWith("/api/v1/investigations/mitre-mappings/0/review", expect.objectContaining({ method: "POST", body: JSON.stringify({ status: "REJECTED", rationale: "not applicable" }) })));
  });

  it("handles MITRE loading, empty, and API-error states", async () => {
    let resolve!: (value: typeof mappings) => void;
    state.apiFetch.mockReturnValueOnce(new Promise<typeof mappings>(done => { resolve = done; }));
    const { unmount } = render(<MitrePage />);
    expect(screen.getByText("Loading MITRE review…")).toBeInTheDocument();
    resolve([]);
    expect(await screen.findByText("No proposed mappings.")).toBeInTheDocument();
    unmount();
    state.apiFetch.mockRejectedValueOnce(new ApiError("MITRE unavailable", 500));
    render(<MitrePage />);
    expect(await screen.findByText("MITRE unavailable")).toBeInTheDocument();
  });

  it("renders one bounded authoritative overview projection", async () => {
    state.apiFetch.mockResolvedValue({ investigation: { id: "case-1", title: "Case one", source: "test", severity: "high", status: "investigating", created_at: "2026-01-01T00:00:00Z", updated_at: "2026-01-02T00:00:00Z" }, counts: { evidence_items: 2, raw_records: 3, events: 3, indicator_occurrences: 1, entities: 2, relationships: 1, findings: 1, confirmed_mitre_mappings: 1, intelligence_runs: 1 } });
    render(<OverviewWorkspace id="case-1" />);
    await screen.findByText("Persisted record counts");
    const metrics: Array<[string, string]> = [["Evidence", "2"], ["Raw records", "3"], ["Events / Timeline", "3"], ["Indicators", "1"], ["Entities", "2"], ["Relationships / Attack Graph", "1"], ["Findings", "1"], ["Confirmed MITRE", "1"], ["Intelligence runs", "1"]];
    for (const [label, value] of metrics) {
      const metric = screen.getAllByText(label).find(element => element.tagName === "DIV");
      expect(metric).toBeDefined();
      expect(within(metric!.parentElement!).getByText(value)).toBeInTheDocument();
    }
    expect(state.apiFetch).toHaveBeenCalledTimes(1);
    expect(state.apiFetch).toHaveBeenCalledWith("/api/v1/investigations/case-1/overview", expect.any(Object));
  });
});
