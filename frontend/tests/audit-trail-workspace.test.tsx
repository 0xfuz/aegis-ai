import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { AuditTrailWorkspace } from "@/components/investigations/audit-trail-workspace";

const state = vi.hoisted(() => ({ apiFetch: vi.fn() }));
vi.mock("next/link", () => ({ default: ({ href, children }: { href: string; children: ReactNode }) => <a href={href}>{children}</a> }));
vi.mock("@/lib/api-client", () => ({ apiFetch: state.apiFetch, ApiError: class ApiError extends Error { constructor(message: string, public status: number) { super(message); } } }));

const item = (id: string, type = "INTELLIGENCE_ITEM_REVIEWED") => ({ id, event_type: type, occurred_at: "2026-01-01T10:00:00Z", actor: { type: "user", id: "actor-1" }, target: { type: "IntelligenceItem", id: `target-${id}` }, transition: { from: "PENDING", to: "UNRESOLVED" } });
const page = (items = [item("event-1")], offset = 0, total = items.length) => ({ items, offset, total, limit: 25 });

afterEach(cleanup);
beforeEach(() => state.apiFetch.mockReset());

describe("AuditTrailWorkspace", () => {
  it("renders bounded server-order audit events with timezone and claim-review transition", async () => {
    state.apiFetch.mockResolvedValue(page());
    render(<AuditTrailWorkspace id="case 1" />);
    expect(await screen.findByRole("heading", { name: "Chronological audit events" })).toBeVisible();
    expect(state.apiFetch).toHaveBeenCalledWith("/api/v1/investigations/case%201/audit?limit=25&offset=0", expect.any(Object));
    expect(screen.getByText("PENDING → UNRESOLVED")).toBeVisible();
    expect(screen.getByText("Time (local timezone)")).toBeVisible();
    expect(screen.getByText(/Server order: newest first/)).toBeVisible();
  });

  it("renders loading, empty, permission, not-found, degraded and retry states", async () => {
    let resolve!: (value: ReturnType<typeof page>) => void;
    state.apiFetch.mockImplementationOnce(() => new Promise(r => { resolve = r; }));
    const view = render(<AuditTrailWorkspace id="case-1" />);
    expect(screen.getByRole("heading", { name: "Loading audit trail" })).toBeVisible();
    resolve(page([]));
    expect(await screen.findByRole("heading", { name: "No audit events" })).toBeVisible();
    view.unmount();
    state.apiFetch.mockRejectedValueOnce(new (await import("@/lib/api-client")).ApiError("no", 403));
    render(<AuditTrailWorkspace id="case-2" />); expect(await screen.findByRole("heading", { name: "Permission denied" })).toBeVisible(); cleanup();
    state.apiFetch.mockRejectedValueOnce(new (await import("@/lib/api-client")).ApiError("no", 404));
    render(<AuditTrailWorkspace id="case-3" />); expect(await screen.findByRole("heading", { name: "Not found" })).toBeVisible(); cleanup();
    state.apiFetch.mockRejectedValueOnce(new (await import("@/lib/api-client")).ApiError("no", 503));
    render(<AuditTrailWorkspace id="case-4" />); expect(await screen.findByRole("heading", { name: "Limited availability" })).toBeVisible(); cleanup();
    state.apiFetch.mockRejectedValueOnce(new Error("network")).mockResolvedValueOnce(page());
    render(<AuditTrailWorkspace id="case-5" />); fireEvent.click(await screen.findByRole("button", { name: "Retry" }));
    expect(await screen.findByRole("heading", { name: "Chronological audit events" })).toBeVisible();
  });

  it("paginates without sorting or interpreting hostile persisted display text", async () => {
    state.apiFetch.mockResolvedValueOnce(page([item("event-2", "<img src=x onerror=alert(1)>")], 0, 26)).mockResolvedValueOnce(page([item("event-1")], 25, 26));
    render(<AuditTrailWorkspace id="case-1" />);
    expect(await screen.findByText("<img src=x onerror=alert(1)>")).toBeVisible();
    expect(document.querySelector("img")).toBeNull();
    expect(screen.getByText("Showing 1–1 of 26 audit events")).toBeVisible();
    fireEvent.click(screen.getByRole("button", { name: "Next" }));
    await waitFor(() => expect(state.apiFetch).toHaveBeenLastCalledWith("/api/v1/investigations/case-1/audit?limit=25&offset=25", expect.any(Object)));
    expect(await screen.findByText("target-event-1")).toBeVisible();
  });
});
