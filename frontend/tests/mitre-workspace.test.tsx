import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { MitreWorkspace } from "@/components/investigations/mitre-workspace";

const state = vi.hoisted(() => ({ api: vi.fn(), replace: vi.fn(), search: "", permissions: ["investigation:read", "investigation:write"] as string[], active: true }));
vi.mock("next/navigation", () => ({ usePathname: () => "/investigations/case-1/mitre", useRouter: () => ({ replace: state.replace }), useSearchParams: () => new URLSearchParams(state.search) }));
vi.mock("next/link", () => ({ default: ({ href, children }: { href: string; children: ReactNode }) => <a href={href}>{children}</a> }));
vi.mock("@/lib/api-client", () => ({ apiFetch: state.api, ApiError: class ApiError extends Error { constructor(message: string, public status: number) { super(message); } } }));
vi.mock("@/lib/auth-context", () => ({ useAuth: () => ({ user: state.active ? { is_active: true } : { is_active: false }, hasPermission: (permission: string) => state.permissions.includes(permission) }) }));

const mapping = (id: string, status: "PROPOSED" | "CONFIRMED" | "REJECTED" = "PROPOSED", technique = "T1059") => ({ id, technique_id: technique, technique_name: "<img src=x onerror=alert(1)>", tactic: "execution", status, confidence: 72, review_rationale: null, created_at: "2026-01-01T00:00:00Z", reviewed_at: null, provenance: { available: true, omitted: 0 }, fact_links: [{ fact_id: "event-1", fact_type: "EVENT", role: "CONTEXT" }] });
const page = (items = [mapping("m-1")], offset = 0, total = items.length, limit = 25) => ({ items, offset, total, limit, returned_count: items.length });

beforeEach(() => { state.api.mockReset(); state.replace.mockReset(); state.search = ""; state.permissions = ["investigation:read", "investigation:write"]; state.active = true; });
afterEach(cleanup);

describe("MitreWorkspace", () => {
  it("uses only the bounded MITRE route, preserves server order, and renders hostile text inertly", async () => {
    state.api.mockResolvedValue(page([mapping("m-2", "CONFIRMED", "T1003"), mapping("m-1", "PROPOSED", "T1059")]));
    render(<MitreWorkspace id="case 1" />);
    await screen.findAllByText("T1003");
    expect(screen.getAllByRole("button", { name: /T1003|T1059/ }).map(node => node.textContent)).toEqual(["T1003", "T1059", "T1003 · <img src=x onerror=alert(1)>", "T1059 · <img src=x onerror=alert(1)>"]);
    expect(state.api).toHaveBeenCalledWith("/api/v1/investigations/case%201/mitre?limit=25&offset=0", expect.objectContaining({ signal: expect.any(AbortSignal) }));
    expect(state.api.mock.calls.every(call => !String(call[0]).includes("/mitre-mappings"))).toBe(true);
    expect(screen.getAllByText(/<img src=x/)).toHaveLength(4);
    expect(document.querySelector("img")).toBeNull();
    expect(screen.getByText("Analyst-controlled mapping authority")).toBeVisible();
    expect(screen.getAllByText(/Proposed — not confirmed/).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/Proposal confidence \(non-authoritative\)/).length).toBeGreaterThan(0);
    expect(screen.queryByText(/AI inference|Convert to MITRE|Run analysis/i)).toBeNull();
  });

  it("restores URL state and resets offset for canonical filters and page bounds", async () => {
    state.search = "status=CONFIRMED&limit=50&offset=100"; state.api.mockResolvedValue(page([], 100, 0, 50));
    render(<MitreWorkspace id="case-1" />);
    await screen.findByRole("heading", { name: "No mappings match this status" });
    expect(state.api).toHaveBeenCalledWith(expect.stringContaining("status=CONFIRMED"), expect.anything());
    fireEvent.change(screen.getByLabelText("MITRE mapping status"), { target: { value: "PROPOSED" } });
    expect(state.replace).toHaveBeenCalledWith("/investigations/case-1/mitre?status=PROPOSED&limit=50&offset=0");
    fireEvent.change(screen.getByLabelText("MITRE mapping page size"), { target: { value: "100" } });
    expect(state.replace).toHaveBeenLastCalledWith("/investigations/case-1/mitre?status=CONFIRMED&limit=100&offset=0");
  });

  it("handles pagination, empty, bounded errors, retry, and aborted stale requests", async () => {
    state.api.mockResolvedValueOnce(page([mapping("m-1")], 0, 26)).mockResolvedValueOnce(page([mapping("m-2")], 25, 26));
    render(<MitreWorkspace id="case-1" />); await screen.findAllByText("T1059");
    expect(screen.getByRole("button", { name: "Previous" })).toBeDisabled(); fireEvent.click(screen.getByRole("button", { name: "Next" }));
    expect(state.replace).toHaveBeenCalledWith("/investigations/case-1/mitre?limit=25&offset=25");
    cleanup(); state.api.mockReset(); state.api.mockRejectedValueOnce(new Error("network")).mockResolvedValueOnce(page([])); render(<MitreWorkspace id="case-1" />);
    expect(await screen.findByRole("heading", { name: "Unable to load MITRE mappings" })).toBeVisible(); fireEvent.click(screen.getByRole("button", { name: "Retry" }));
    expect(await screen.findByRole("heading", { name: "No MITRE mappings" })).toBeVisible(); cleanup();
    let signal: AbortSignal | undefined; state.api.mockImplementation((_path: string, options?: { signal?: AbortSignal }) => { signal = options?.signal; return new Promise(() => {}); });
    const view = render(<MitreWorkspace id="case-1" />); await waitFor(() => expect(signal).toBeDefined()); view.unmount(); expect(signal?.aborted).toBe(true);
  });

  it("renders permission states and a same-page bounded provenance inspector", async () => {
    const { ApiError } = await import("@/lib/api-client"); state.api.mockRejectedValueOnce(new ApiError("no", 403)); render(<MitreWorkspace id="case-1" />);
    expect(await screen.findByRole("heading", { name: "Permission denied" })).toBeVisible(); cleanup();
    state.api.mockRejectedValueOnce(new ApiError("no", 404)); render(<MitreWorkspace id="case-1" />); expect(await screen.findByRole("heading", { name: "Not found" })).toBeVisible(); cleanup();
    state.search = "mapping=m-1"; state.api.mockResolvedValue(page([mapping("m-1")])); render(<MitreWorkspace id="case-1" />);
    expect(await screen.findByRole("heading", { name: "MITRE mapping detail" })).toBeVisible(); expect(screen.getByText("Available structured references")).toBeVisible();
    expect(screen.getByText(/Raw telemetry and arbitrary metadata/)).toBeVisible(); fireEvent.keyDown(window, { key: "Escape" });
    await waitFor(() => expect(state.replace).toHaveBeenLastCalledWith("/investigations/case-1/mitre?limit=25&offset=0"));
  });

  it("uses only actual proposed review actions with confirmation, rationale, and authoritative refresh", async () => {
    state.api.mockResolvedValueOnce(page([mapping("m-open")])).mockResolvedValueOnce({ status: "CONFIRMED" }).mockResolvedValueOnce(page([mapping("m-open", "CONFIRMED")]));
    render(<MitreWorkspace id="case-1" />); fireEvent.click((await screen.findAllByRole("button", { name: "Confirm" }))[0]!);
    expect(screen.getByRole("dialog", { name: "Confirm MITRE mapping" })).toBeVisible(); expect(state.api).toHaveBeenCalledTimes(1); fireEvent.click(screen.getByRole("button", { name: "Confirm mapping" }));
    await waitFor(() => expect(state.api).toHaveBeenCalledWith("/api/v1/investigations/mitre-mappings/m-open/review", expect.objectContaining({ method: "POST", body: JSON.stringify({ status: "CONFIRMED", rationale: "" }) })));
    cleanup(); state.api.mockResolvedValue(page([mapping("m-reject")])); render(<MitreWorkspace id="case-1" />); fireEvent.click((await screen.findAllByRole("button", { name: "Reject" }))[0]!);
    expect(screen.getByRole("button", { name: "Reject mapping" })).toBeDisabled(); fireEvent.change(screen.getByLabelText("Rejection rationale"), { target: { value: "bounded reason" } }); expect(screen.getByRole("button", { name: "Reject mapping" })).toBeEnabled();
  });

  it("hides review controls for read-only users and reports stale review errors without optimistic authority", async () => {
    state.permissions = ["investigation:read"]; state.api.mockResolvedValue(page()); render(<MitreWorkspace id="case-1" />); await screen.findAllByText("T1059"); expect(screen.queryByRole("button", { name: "Confirm" })).toBeNull(); cleanup();
    state.permissions = ["investigation:write"]; const { ApiError } = await import("@/lib/api-client"); state.api.mockResolvedValueOnce(page()).mockRejectedValueOnce(new ApiError("stale", 422)); render(<MitreWorkspace id="case-1" />); fireEvent.click((await screen.findAllByRole("button", { name: "Confirm" }))[0]!); fireEvent.click(screen.getByRole("button", { name: "Confirm mapping" })); expect(await screen.findByRole("alert")).toHaveTextContent("no longer valid");
  });
});
