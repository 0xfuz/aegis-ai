import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import AlertTriagePage from "@/app/(dashboard)/alert-triage/page";
import { ApiError } from "@/lib/api-client";

const state = vi.hoisted(() => ({ apiFetch: vi.fn(), push: vi.fn(), write: true }));
vi.mock("next/navigation", () => ({ useRouter: () => ({ push: state.push }) }));
vi.mock("next/link", () => ({ default: ({ href, children }: { href: string; children: ReactNode }) => <a href={href}>{children}</a> }));
vi.mock("@/lib/api-client", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api-client")>("@/lib/api-client");
  return { ...actual, apiFetch: state.apiFetch };
});
vi.mock("@/lib/auth-context", () => ({ useAuth: () => ({ hasPermission: (permission: string) => state.write && permission === "investigation:write" }) }));

const cluster = {
  id: "cluster<safe>", correlation_version: "correlation-v2", status: "OPEN", member_count: 1,
  triage: { priority: "HIGH", score: 80, version: "triage-v1" }, promotion: null,
  promotion_eligible: true, promotion_reason: "ELIGIBLE",
};

describe("Alert triage surface", () => {
  beforeEach(() => { state.apiFetch.mockReset(); state.push.mockReset(); state.write = true; });
  afterEach(cleanup);

  it("renders the server ordered list, safe detail and accessible confirmation", async () => {
    state.apiFetch.mockResolvedValueOnce([{ ...cluster, members: [{ id: "m1", score: 1, reason_codes: ["INITIAL_CLUSTER"], added_at: "now", detection_label: "Wazuh rule 100500", source: "wazuh", category: "auth", severity: "HIGH", observed_at: "2026-01-01T00:00:00Z", hostname: "host-a", occurrence_count: 1 }] }]).mockResolvedValueOnce({ ...cluster, members: [{ id: "m1", score: 1, reason_codes: ["INITIAL_CLUSTER"], added_at: "now", detection_label: "Wazuh rule 100500", source: "wazuh", category: "auth", severity: "HIGH", observed_at: "2026-01-01T00:00:00Z", hostname: "host-a", occurrence_count: 1 }, { id: "m2", score: 1, reason_codes: [], added_at: "now", detection_label: "Wazuh rule 502", source: "wazuh", category: "auth", severity: "LOW", observed_at: "2026-01-01T00:00:01Z", occurrence_count: 1 }] });
    render(<AlertTriagePage />);
    expect(await screen.findByText("Cluster cluster<safe>")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Promote to Investigation" })).toBeVisible();
    fireEvent.click(screen.getByRole("button", { name: "View details" }));
    expect(await screen.findByText("Cluster detail")).toBeInTheDocument();
    expect(screen.getAllByText("Wazuh rule 100500").length).toBeGreaterThan(0);
    expect(screen.getByText("Wazuh rule 502")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Promote to Investigation" }));
    expect(screen.getByRole("button", { name: "Confirm promotion" })).toBeVisible();
    fireEvent.click(screen.getByRole("button", { name: "Cancel" }));
    expect(screen.getByRole("button", { name: "Promote to Investigation" })).toBeVisible();
  });

  it("hides write controls for read-only users and links an existing investigation", async () => {
    state.write = false;
    state.apiFetch.mockResolvedValue([{ ...cluster, promotion: { status: "COMPLETED", investigation_id: "case-7" }, promotion_eligible: false }]);
    render(<AlertTriagePage />);
    expect(await screen.findByRole("link", { name: "Open Investigation" })).toHaveAttribute("href", "/investigations/case-7");
    expect(screen.queryByRole("button", { name: /Promote/ })).toBeNull();
  });

  it("handles empty, retryable failure and prevents duplicate confirmation submission", async () => {
    state.apiFetch.mockRejectedValueOnce(new ApiError("network", 500)).mockResolvedValueOnce([cluster]).mockResolvedValueOnce({ investigation_id: "case-9" });
    render(<AlertTriagePage />);
    expect(await screen.findByRole("alert")).toHaveTextContent("network");
    fireEvent.click(screen.getByRole("button", { name: "Retry" }));
    expect(await screen.findByRole("button", { name: "Promote to Investigation" })).toBeVisible();
    fireEvent.click(screen.getByRole("button", { name: "Promote to Investigation" }));
    fireEvent.click(screen.getByRole("button", { name: "Confirm promotion" }));
    await waitFor(() => expect(state.push).toHaveBeenCalledWith("/investigations/case-9"));
    expect(state.apiFetch.mock.calls.filter((call) => String(call[0]).endsWith("/promote"))).toHaveLength(1);
  });
});
