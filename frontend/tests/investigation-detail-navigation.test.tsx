import { fireEvent, render, screen } from "@testing-library/react";
import type { ReactNode } from "react";
import { describe, expect, it, vi } from "vitest";
import InvestigationDetailPage from "@/app/(dashboard)/investigations/[id]/page";

const state = vi.hoisted(() => ({ apiFetch: vi.fn() }));

vi.mock("next/navigation", () => ({
  useParams: () => ({ id: "case-42" }),
  usePathname: () => "/investigations/case-42",
  useRouter: () => ({ push: vi.fn() }),
}));
vi.mock("next/link", () => ({ default: ({ href, children }: { href: string; children: ReactNode }) => <a href={href}>{children}</a> }));
vi.mock("@/lib/api-client", () => ({ apiFetch: state.apiFetch, ApiError: class ApiError extends Error {}, downloadFile: vi.fn() }));
vi.mock("@/components/investigations/evidence-explorer", () => ({ EvidenceExplorer: () => null }));
vi.mock("@/components/investigations/ioc-detail", () => ({ IOCDetailOverlay: () => null }));
vi.mock("@/components/investigations/ai-reasoning-panel", () => ({ AIReasoningPanel: ({ onAnalyze }: { onAnalyze: () => void }) => <button onClick={onAnalyze}>Queue intelligence</button> }));

describe("legacy investigation detail navigation", () => {
  it("exposes the shared workspace routes for the current investigation", async () => {
    state.apiFetch.mockResolvedValue({
      id: "case-42", title: "Insider Threat", source: "test", severity: "medium", status: "new", confidence: 0.5,
      root_cause: "", mitre_techniques: [], blast_radius_summary: "", false_positive_probability: 0,
      attack_chain: [], alternative_hypotheses: [], reasoning_chain: [], created_at: "2026-01-01T00:00:00Z",
      timeline_events: [], evidence: [], evidence_records: [], notes: [], recommended_actions: [],
    });

    render(<InvestigationDetailPage />);

    expect(await screen.findByRole("navigation", { name: "Investigation workspace" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Overview" })).toHaveAttribute("href", "/investigations/case-42/overview");
    expect(screen.getByRole("link", { name: "Audit Trail" })).toHaveAttribute("href", "/investigations/case-42/audit");
    expect(screen.getByRole("link", { name: "Attack Graph" })).toHaveAttribute("href", "/investigations/case-42/relationships");
    expect(screen.getByRole("link", { name: "View attack graph" })).toHaveAttribute("href", "/investigations/case-42/relationships");
    expect(screen.getByRole("link", { name: "Reports" })).toHaveAttribute("href", "/investigations/case-42/reports");
  });

  it("queues through the canonical run endpoint and never calls the retired synchronous route", async () => {
    state.apiFetch.mockResolvedValue({
      id: "case-42", title: "Insider Threat", source: "test", severity: "medium", status: "new", confidence: 0.5,
      root_cause: "", mitre_techniques: [], blast_radius_summary: "", false_positive_probability: 0,
      attack_chain: [], alternative_hypotheses: [], reasoning_chain: [], created_at: "2026-01-01T00:00:00Z",
      timeline_events: [], evidence: [], evidence_records: [], notes: [], recommended_actions: [],
    });
    render(<InvestigationDetailPage />);
    await screen.findByText("Insider Threat");
    fireEvent.click(screen.getAllByRole("button", { name: "Queue intelligence" }).at(-1)!);
    await vi.waitFor(() => expect(state.apiFetch).toHaveBeenCalledWith(
      "/api/v1/investigations/case-42/intelligence/runs",
      expect.objectContaining({ method: "POST", body: expect.stringMatching(/legacy-ui:/) }),
    ));
    expect(state.apiFetch.mock.calls.some(([url]) => String(url).endsWith("/analyze"))).toBe(false);
  });
});
