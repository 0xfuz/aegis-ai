import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ReportsWorkspace } from "@/components/investigations/reports-workspace";

const state = vi.hoisted(() => ({ download: vi.fn(), permissions: ["reports:generate_technical", "reports:generate_executive"] as string[] }));
vi.mock("next/link", () => ({ default: ({ href, children }: { href: string; children: ReactNode }) => <a href={href}>{children}</a> }));
vi.mock("@/lib/auth-context", () => ({ useAuth: () => ({ isLoading: false, hasPermission: (permission: string) => state.permissions.includes(permission) }) }));
vi.mock("@/lib/api-client", () => ({ downloadInvestigationReport: state.download, ApiError: class ApiError extends Error { constructor(message: string, public status: number) { super(message); } } }));

afterEach(cleanup);
beforeEach(() => { state.download.mockReset(); state.permissions = ["reports:generate_technical", "reports:generate_executive"]; });

describe("ReportsWorkspace", () => {
  it("renders only authoritative report formats and initiates a safe markdown download", async () => {
    state.download.mockResolvedValue(undefined);
    render(<ReportsWorkspace id="case 1" />);
    expect(screen.getByRole("heading", { name: "Technical report" })).toBeVisible();
    expect(screen.getByRole("heading", { name: "Executive report" })).toBeVisible();
    expect(screen.queryByRole("link", { name: /Global Reports/i })).toBeNull();
    fireEvent.click(screen.getAllByRole("button", { name: "Download Markdown" })[0]!);
    await waitFor(() => expect(state.download).toHaveBeenCalledWith("/api/v1/investigations/case%201/report?type=technical&format=markdown", expect.objectContaining({ signal: expect.any(AbortSignal) })));
    expect(await screen.findByText("Report download started.")).toBeVisible();
  });

  it("prevents duplicate submission and exposes loading/downloading status", async () => {
    let resolve!: () => void;
    state.download.mockImplementationOnce((_path: string, options: { onDownloading: () => void }) => new Promise<void>(done => { options.onDownloading(); resolve = done; }));
    render(<ReportsWorkspace id="case-1" />);
    const markdown = screen.getAllByRole("button", { name: "Download Markdown" })[0]!;
    fireEvent.click(markdown);
    expect(await screen.findByText("Downloading report…")).toBeVisible();
    expect(screen.getAllByRole("button", { name: /Download/ })[1]).toBeDisabled();
    resolve();
    expect(await screen.findByText("Report download started.")).toBeVisible();
  });

  it("shows permission, not-found, unavailable, generic retry, and aborts on unmount", async () => {
    state.permissions = [];
    const view = render(<ReportsWorkspace id="case-1" />);
    expect(screen.getByRole("heading", { name: "Permission denied" })).toBeVisible();
    view.unmount();
    state.permissions = ["reports:generate_technical", "reports:generate_executive"];
    const { ApiError } = await import("@/lib/api-client");
    state.download.mockRejectedValueOnce(new ApiError("no", 404)); render(<ReportsWorkspace id="case-2" />); fireEvent.click(screen.getAllByRole("button", { name: "Download Markdown" })[0]!); expect(await screen.findByRole("heading", { name: "Not found" })).toBeVisible(); cleanup();
    state.download.mockRejectedValueOnce(new ApiError("no", 503)); render(<ReportsWorkspace id="case-3" />); fireEvent.click(screen.getAllByRole("button", { name: "Download Markdown" })[0]!); expect(await screen.findByRole("heading", { name: "Limited availability" })).toBeVisible(); cleanup();
    state.download.mockRejectedValueOnce(new Error("no")); render(<ReportsWorkspace id="case-4" />); fireEvent.click(screen.getAllByRole("button", { name: "Download Markdown" })[0]!); fireEvent.click(await screen.findByRole("button", { name: "Retry" })); expect(await screen.findByText("Choose an authorized report format.")).toBeVisible();
    cleanup();
    let signal: AbortSignal | undefined;
    state.download.mockImplementationOnce((_path: string, options: { signal: AbortSignal }) => { signal = options.signal; return new Promise<void>(() => {}); });
    const mounted = render(<ReportsWorkspace id="case-5" />); fireEvent.click(screen.getAllByRole("button", { name: "Download Markdown" })[0]!); await waitFor(() => expect(signal).toBeDefined()); mounted.unmount(); expect(signal?.aborted).toBe(true);
  });

  it("keeps persisted report descriptions inert and controls keyboard-operable", () => {
    render(<ReportsWorkspace id="case-1" />);
    expect(screen.getAllByRole("button", { name: "Download PDF" })[0]!).toHaveClass("focus-visible:outline");
    expect(document.querySelector("script")).toBeNull();
  });
});
