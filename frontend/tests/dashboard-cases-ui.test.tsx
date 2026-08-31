import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import DashboardPage from "@/app/(dashboard)/dashboard/page";
import CasesPage from "@/app/(dashboard)/investigations/page";

const state = vi.hoisted(() => ({ api: vi.fn(), replace: vi.fn(), search: "" }));
vi.mock("next/link", () => ({ default: ({ href, children, ...props }: { href: string; children: ReactNode }) => <a href={href} {...props}>{children}</a> }));
vi.mock("next/navigation", () => ({ useRouter: () => ({ replace: state.replace }), usePathname: () => "/investigations", useSearchParams: () => new URLSearchParams(state.search) }));
vi.mock("@/lib/api-client", () => ({ apiFetch: state.api, ApiError: class ApiError extends Error { constructor(message: string, public status: number) { super(message); } } }));
const summary = { open_investigations: 2, critical_open: 1, avg_false_positive_probability: 12, total_investigations: 2, window: { preset: "7d", from_at: "2026-01-01T00:00:00Z", to_at: "2026-01-08T00:00:00Z" } };
const item = { id: "case-1", title: "<img src=x onerror=alert(1)>", source: "Wazuh", severity: "high", status: "triaging", confidence: 20, created_at: "2026-01-02T00:00:00Z" };
const page = { items: [item], limit: 25, offset: 0, returned_count: 1, total: 2 };
afterEach(cleanup);
beforeEach(() => { state.api.mockReset(); state.replace.mockReset(); state.search = ""; });

describe("Dashboard and Cases U2-B", () => {
  it("uses approved presets, explicit UTC custom ranges, and bounded validation", async () => {
    state.api.mockResolvedValue({ items: [] }).mockResolvedValueOnce(summary);
    render(<DashboardPage />); await screen.findByText("Open investigations");
    fireEvent.click(screen.getByRole("button", { name: "24 hours" }));
    await waitFor(() => expect(state.api).toHaveBeenCalledWith("/api/v1/investigations/dashboard-summary?window=24h", expect.anything()));
    fireEvent.click(screen.getByRole("button", { name: "Clear" }));
    fireEvent.change(screen.getByLabelText("From (UTC)"), { target: { value: "2026-01-03T00:00" } });
    fireEvent.change(screen.getByLabelText("To (UTC)"), { target: { value: "2026-01-02T00:00" } });
    fireEvent.click(screen.getByRole("button", { name: "Apply" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("From must not be later");
  });

  it("renders server order, URL-backed filters and inert Case text", async () => {
    state.search = "status=triaging&limit=25&offset=0";
    state.api.mockResolvedValue(page);
    render(<CasesPage />);
    expect((await screen.findAllByText(/<img src=x/)).length).toBe(2); expect(document.querySelector("img")).toBeNull();
    expect(state.api).toHaveBeenCalledWith("/api/v1/investigations?limit=25&offset=0&status=triaging", expect.anything());
    fireEvent.change(screen.getByLabelText("Cases per page"), { target: { value: "50" } });
    expect(state.replace).toHaveBeenCalledWith("/investigations?status=triaging&limit=50");
    fireEvent.change(screen.getByLabelText("Status"), { target: { value: "resolved" } });
    expect(state.replace).toHaveBeenLastCalledWith("/investigations?status=resolved&limit=25");
  });

  it("distinguishes empty, permission, not-found and retryable states", async () => {
    const { ApiError } = await import("@/lib/api-client");
    state.api.mockResolvedValue({ ...page, items: [], total: 0, returned_count: 0 }); render(<CasesPage />); expect(await screen.findByRole("heading", { name: "No Cases yet" })).toBeVisible(); cleanup();
    state.api.mockRejectedValueOnce(new ApiError("x", 403)); render(<CasesPage />); expect(await screen.findByRole("heading", { name: "Permission denied" })).toBeVisible(); cleanup();
    state.api.mockRejectedValueOnce(new ApiError("x", 404)); render(<CasesPage />); expect(await screen.findByRole("heading", { name: "Not found" })).toBeVisible(); cleanup();
    state.api.mockRejectedValueOnce(new Error("x")).mockResolvedValue(page); render(<CasesPage />); fireEvent.click(await screen.findByRole("button", { name: "Retry" })); expect(await screen.findByText(/Showing 1/)).toBeVisible();
  });
});
