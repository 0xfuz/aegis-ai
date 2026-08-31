import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { FindingsWorkspace } from "@/components/investigations/findings-workspace";

const state = vi.hoisted(() => ({ api: vi.fn(), replace: vi.fn(), search: "", permissions: ["investigation:read", "investigation:write"] as string[], active: true }));
vi.mock("next/navigation", () => ({ usePathname: () => "/investigations/case-1/findings", useRouter: () => ({ replace: state.replace }), useSearchParams: () => new URLSearchParams(state.search) }));
vi.mock("next/link", () => ({ default: ({ href, children }: { href: string; children: ReactNode }) => <a href={href}>{children}</a> }));
vi.mock("@/lib/api-client", () => ({ apiFetch: state.api, ApiError: class ApiError extends Error { constructor(message: string, public status: number) { super(message); } } }));
vi.mock("@/lib/auth-context", () => ({ useAuth: () => ({ user: state.active ? { is_active: true } : { is_active: false }, hasPermission: (permission: string) => state.permissions.includes(permission) }) }));

const finding = (id: string, status: "OPEN" | "CONFIRMED" | "DISMISSED" | "RESOLVED" = "OPEN", title = "Credential access finding") => ({ id, title, description: "<img src=x onerror=alert(1)>", severity: "high", confidence: 86, status, created_at: "2026-01-01T00:00:00Z", updated_at: "2026-01-02T00:00:00Z", provenance: { available: true, omitted: 0 }, fact_links: [{ fact_id: "event-1", fact_type: "EVENT", role: "SUPPORTS" } ] });
const page = (items = [finding("f-1")], offset = 0, total = items.length, limit = 25) => ({ items, offset, total, limit, returned_count: items.length });

beforeEach(() => { state.api.mockReset(); state.replace.mockReset(); state.search = ""; state.permissions = ["investigation:read", "investigation:write"]; state.active = true; });
afterEach(cleanup);

describe("FindingsWorkspace", () => {
  it("consumes the bounded page envelope in server order with inert persisted text", async () => {
    state.api.mockResolvedValue(page([finding("f-2", "CONFIRMED", "Second"), finding("f-1", "OPEN", "First")]));
    render(<FindingsWorkspace id="case 1" />);
    expect((await screen.findAllByText("Second")).length).toBeGreaterThan(0);
    expect(screen.getAllByRole("button", { name: /Second|First/ }).map(node => node.textContent)).toEqual(["Second", "First", "Second", "First"]);
    expect(screen.getAllByText(/<img src=x/)).toHaveLength(4);
    expect(document.querySelector("img")).toBeNull();
    expect(state.api).toHaveBeenCalledWith("/api/v1/investigations/case%201/findings?limit=25&offset=0", expect.objectContaining({ signal: expect.any(AbortSignal) }));
    expect(screen.getByText("Analyst-controlled Findings")).toBeVisible();
    expect(screen.queryByText(/AI INFERENCE/i)).toBeNull();
    expect(screen.queryByText(/Convert to Finding/i)).toBeNull();
  });

  it("restores URL state and resets offset when canonical filters change", async () => {
    state.search = "status=CONFIRMED&limit=50&offset=100"; state.api.mockResolvedValue(page([], 100, 0, 50));
    render(<FindingsWorkspace id="case-1" />);
    await screen.findByRole("heading", { name: "No Findings match this status" });
    expect(state.api).toHaveBeenCalledWith(expect.stringContaining("status=CONFIRMED"), expect.anything());
    fireEvent.change(screen.getByLabelText("Finding status"), { target: { value: "OPEN" } });
    expect(state.replace).toHaveBeenCalledWith("/investigations/case-1/findings?status=OPEN&limit=50&offset=0");
    fireEvent.change(screen.getByLabelText("Finding page size"), { target: { value: "100" } });
    expect(state.replace).toHaveBeenLastCalledWith("/investigations/case-1/findings?status=CONFIRMED&limit=100&offset=0");
  });

  it("provides bounded pagination and distinguishes no Findings from unavailable", async () => {
    state.api.mockResolvedValueOnce(page([finding("f-1")], 0, 26)).mockResolvedValueOnce(page([finding("f-2")], 25, 26));
    render(<FindingsWorkspace id="case-1" />);
    await screen.findAllByText("Credential access finding");
    expect(screen.getByRole("button", { name: "Previous" })).toBeDisabled();
    fireEvent.click(screen.getByRole("button", { name: "Next" }));
    expect(state.replace).toHaveBeenCalledWith("/investigations/case-1/findings?limit=25&offset=25");
    cleanup(); state.api.mockReset(); state.api.mockResolvedValue(page([])); render(<FindingsWorkspace id="case-1" />);
    expect(await screen.findByRole("heading", { name: "No Findings" })).toBeVisible();
  });

  it("renders permission and bounded error states and aborts stale reads", async () => {
    const { ApiError } = await import("@/lib/api-client"); state.api.mockRejectedValueOnce(new ApiError("no", 403));
    const denied = render(<FindingsWorkspace id="case-1" />); expect(await screen.findByRole("heading", { name: "Permission denied" })).toBeVisible(); denied.unmount();
    state.api.mockRejectedValueOnce(new ApiError("no", 404)); render(<FindingsWorkspace id="case-1" />); expect(await screen.findByRole("heading", { name: "Not found" })).toBeVisible(); cleanup();
    let signal: AbortSignal | undefined; state.api.mockImplementation((_path: string, options?: { signal?: AbortSignal }) => { signal = options?.signal; return new Promise(() => {}); });
    const view = render(<FindingsWorkspace id="case-1" />); await waitFor(() => expect(signal).toBeDefined()); view.unmount(); expect(signal?.aborted).toBe(true);
  });

  it("offers a bounded retry without retaining prior list state", async () => {
    state.api.mockRejectedValueOnce(new Error("transport failure")).mockResolvedValueOnce(page([]));
    render(<FindingsWorkspace id="case-1" />);
    expect(await screen.findByRole("heading", { name: "Unable to load Findings" })).toBeVisible();
    fireEvent.click(screen.getByRole("button", { name: "Retry" }));
    expect(await screen.findByRole("heading", { name: "No Findings" })).toBeVisible();
    expect(state.api).toHaveBeenCalledTimes(2);
  });

  it("opens a same-page bounded inspector and restores keyboard focus after Escape", async () => {
    state.api.mockResolvedValue(page()); render(<FindingsWorkspace id="case-1" />);
    const trigger = (await screen.findAllByRole("button", { name: "Credential access finding" }))[0]!; fireEvent.click(trigger);
    expect(state.replace).toHaveBeenCalledWith("/investigations/case-1/findings?limit=25&offset=0&finding=f-1");
    cleanup(); state.search = "finding=f-1"; state.api.mockResolvedValue(page()); render(<FindingsWorkspace id="case-1" />);
    expect(await screen.findByRole("heading", { name: "Finding detail" })).toBeVisible();
    expect(screen.getByText("Available structured references")).toBeVisible();
    expect(screen.getByText(/Raw telemetry and arbitrary metadata/)).toBeVisible();
    fireEvent.keyDown(window, { key: "Escape" });
    await waitFor(() => expect(state.replace).toHaveBeenLastCalledWith("/investigations/case-1/findings?limit=25&offset=0"));
  });

  it("shows only canonical review actions, confirms before sending, and refreshes authoritatively", async () => {
    state.api.mockResolvedValueOnce(page([finding("f-open", "OPEN")])).mockResolvedValueOnce({ status: "CONFIRMED" }).mockResolvedValueOnce(page([finding("f-open", "CONFIRMED")]));
    render(<FindingsWorkspace id="case-1" />); const confirm = (await screen.findAllByRole("button", { name: "Confirm" }))[0]!; fireEvent.click(confirm);
    expect(screen.getByRole("dialog", { name: "Confirm Finding" })).toBeVisible(); expect(state.api).toHaveBeenCalledTimes(1);
    fireEvent.click(screen.getByRole("button", { name: "Confirm Finding" }));
    await waitFor(() => expect(state.api).toHaveBeenCalledWith("/api/v1/investigations/findings/f-open/status", expect.objectContaining({ method: "POST", body: JSON.stringify({ status: "CONFIRMED" }) })));
  });

  it("hides review controls for read-only or inactive users and handles stale review errors", async () => {
    state.permissions = ["investigation:read"]; state.api.mockResolvedValue(page()); render(<FindingsWorkspace id="case-1" />); await screen.findAllByText("Credential access finding"); expect(screen.queryByRole("button", { name: "Confirm" })).toBeNull(); cleanup();
    state.permissions = ["investigation:write"]; state.active = true; const { ApiError } = await import("@/lib/api-client"); state.api.mockResolvedValueOnce(page()).mockRejectedValueOnce(new ApiError("stale", 422)); render(<FindingsWorkspace id="case-1" />); fireEvent.click((await screen.findAllByRole("button", { name: "Confirm" }))[0]!); fireEvent.click(screen.getByRole("button", { name: "Confirm Finding" })); expect(await screen.findByRole("alert")).toHaveTextContent("no longer valid");
  });
});
