import { cleanup, render, screen, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import InvestigationsPage from "@/app/(dashboard)/investigations/page";
import InvestigationAttackGraphPage from "@/app/(dashboard)/investigations/[id]/attack-graph/page";
import { DegradedState, EmptyState, LoadingState, NotFoundState, PermissionDeniedState, RetryableErrorState } from "@/components/ui/async-state";

const state = vi.hoisted(() => ({ apiFetch: vi.fn(), replace: vi.fn() }));

vi.mock("next/navigation", () => ({
  useParams: () => ({ id: "case-42" }),
  useRouter: () => ({ push: vi.fn(), replace: state.replace }),
  usePathname: () => "/investigations",
  useSearchParams: () => new URLSearchParams(),
}));
vi.mock("next/link", () => ({ default: ({ href, children }: { href: string; children: ReactNode }) => <a href={href}>{children}</a> }));
vi.mock("@/lib/api-client", () => ({ apiFetch: state.apiFetch, ApiError: class ApiError extends Error {} }));

afterEach(() => { cleanup(); vi.unstubAllEnvs(); });
beforeEach(() => { state.apiFetch.mockReset(); state.replace.mockReset(); });

describe("release UI foundation", () => {
  it("provides semantic, keyboard-operable safe states", () => {
    const retry = vi.fn();
    render(<><LoadingState /><EmptyState /><PermissionDeniedState /><NotFoundState /><RetryableErrorState onRetry={retry} /><DegradedState /></>);
    expect(screen.getByRole("heading", { name: "Loading" })).toBeVisible();
    expect(screen.getAllByRole("status")[0]).toHaveAttribute("aria-busy", "true");
    expect(screen.getByRole("heading", { name: "Permission denied" }).parentElement).toHaveTextContent("do not have permission");
    expect(screen.getByRole("heading", { name: "Not found" }).parentElement).toHaveTextContent("unavailable");
    expect(screen.getByRole("button", { name: "Retry" })).toHaveClass("focus-visible:outline");
  });

  it("does not fetch or display demos in production mode", async () => {
    vi.stubEnv("NEXT_PUBLIC_DEMO_MODE", "false");
    state.apiFetch.mockResolvedValue({ items: [], limit: 25, offset: 0, returned_count: 0, total: 0 });
    render(<InvestigationsPage />);
    await screen.findByText("No Cases yet");
    expect(state.apiFetch).toHaveBeenCalledWith("/api/v1/investigations?limit=25&offset=0", expect.anything());
    expect(state.apiFetch.mock.calls.some(([path]) => String(path).includes("/demos"))).toBe(false);
    expect(document.body.textContent).not.toContain("Demo Investigation");
  });

  it("does not expose demo controls through the production Cases UI", async () => {
    vi.stubEnv("NEXT_PUBLIC_DEMO_MODE", "true");
    state.apiFetch.mockResolvedValue({ items: [], limit: 25, offset: 0, returned_count: 0, total: 0 });
    render(<InvestigationsPage />);
    await screen.findByText("No Cases yet");
    expect(state.apiFetch.mock.calls.some(([path]) => String(path).includes("/demos"))).toBe(false);
  });

  it("redirects the compatibility Attack Graph URL to the sole relationships destination", async () => {
    render(<InvestigationAttackGraphPage />);
    await waitFor(() => expect(state.replace).toHaveBeenCalledWith("/investigations/case-42/relationships"));
    expect(screen.getByText(/authoritative Investigation relationships workspace/)).toBeVisible();
  });

  it("renders hostile display text as inert React text", () => {
    render(<EmptyState title="<img src=x onerror=alert(1)>" message="<script>ignored()</script>" />);
    expect(screen.getByText("<img src=x onerror=alert(1)>")).toBeVisible();
    expect(document.querySelector("img")).toBeNull();
    expect(document.querySelector("script")).toBeNull();
  });
});
