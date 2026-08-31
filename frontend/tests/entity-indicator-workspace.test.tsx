import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "@/lib/api-client";
import { EntitiesWorkspace, IndicatorsWorkspace } from "@/components/investigations/factual-workspace";

const { apiFetch } = vi.hoisted(() => ({ apiFetch: vi.fn() }));
vi.mock("@/lib/api-client", async () => ({ ...(await vi.importActual<typeof import("@/lib/api-client")>("@/lib/api-client")), apiFetch, downloadFile: vi.fn() }));
vi.mock("next/navigation", () => ({ usePathname: () => "/investigations/case-1/entities" }));
vi.mock("next/link", () => ({ default: ({ href, children }: { href: string; children: ReactNode }) => <a href={href}>{children}</a> }));

const entityPage = { items: [
  { id: "entity-b", type: "HOST", display_value: "<script>host-b</script>", observation_count: 2, first_observed_at: null, last_observed_at: "2026-01-02T00:00:00Z", provenance_available_count: 1 },
  { id: "entity-a", type: "ACCOUNT", display_value: "account-a", observation_count: 1, first_observed_at: "2026-01-01T00:00:00Z", last_observed_at: "2026-01-01T00:00:00Z", provenance_available_count: 1 },
], limit: 25, offset: 0, returned_count: 2, total: 30 };
const observationPage = { items: [{ id: "observation-1", observed_at: null, extractor_name: "safe-extractor", extractor_version: "v1", evidence_id: "evidence-1", raw_record_id: "raw-1", event_id: "event-1", provenance_status: "AVAILABLE" }], limit: 50, offset: 0, returned_count: 1, total: 1 };
const indicatorPage = { items: [
  { id: "occurrence-b", indicator_id: "indicator-b", type: "DOMAIN", canonical_value: "<img src=x>", observed_at: null, extractor_name: "safe-extractor", extractor_version: "v1", evidence_id: "evidence-1", raw_record_id: "raw-1", event_id: "event-1", provenance_status: "AVAILABLE" },
  { id: "occurrence-a", indicator_id: "indicator-a", type: "IP", canonical_value: "192.0.2.44", observed_at: "2026-01-01T00:00:00Z", extractor_name: "safe-extractor", extractor_version: "v1", evidence_id: "evidence-1", raw_record_id: "raw-2", event_id: null, provenance_status: "UNAVAILABLE" },
], limit: 25, offset: 0, returned_count: 2, total: 30 };

describe("scoped Entity and Indicator workspaces", () => {
  afterEach(cleanup);
  beforeEach(() => { apiFetch.mockReset(); window.history.replaceState(null, "", "/investigations/case-1/entities"); });

  it("uses the bounded Entity page and bounded observation inspector in server order", async () => {
    apiFetch.mockImplementation((path: string) => path.includes("/observations?") ? Promise.resolve(observationPage) : Promise.resolve(entityPage));
    render(<EntitiesWorkspace id="case-1" />);
    expect((await screen.findAllByText("<script>host-b</script>")).length).toBeGreaterThan(0);
    const first = screen.getAllByText("<script>host-b</script>")[0]?.closest("tr")?.textContent || "";
    expect(first).toContain("HOST");
    fireEvent.click(screen.getByRole("button", { name: "Inspect entity entity-b" }));
    expect(await screen.findByText("Entity observation inspector")).toHaveFocus();
    expect(apiFetch.mock.calls.some(([path]) => String(path).includes("/entities/entity-b/observations?limit=50&offset=0"))).toBe(true);
    expect(screen.getAllByRole("link", { name: "Evidence" }).at(-1)).toHaveAttribute("href", "/investigations/case-1/evidence");
    expect(screen.getAllByRole("link", { name: "Timeline" }).at(-1)).toHaveAttribute("href", "/investigations/case-1/timeline");
    expect(screen.queryByText(/relationships:/i)).toBeNull();
    expect(screen.queryByText("raw-1")).toBeNull();
  });

  it("uses occurrence ID as the only Indicator selection authority and never queries global Indicator detail", async () => {
    apiFetch.mockResolvedValue(indicatorPage);
    render(<IndicatorsWorkspace id="case-1" />);
    expect((await screen.findAllByText("<img src=x>")).length).toBeGreaterThan(0);
    fireEvent.click(screen.getByRole("button", { name: "Inspect occurrence occurrence-b" }));
    expect(await screen.findByText("Occurrence inspector")).toHaveFocus();
    expect(screen.getByText("occurrence-b")).toBeInTheDocument();
    expect(screen.getAllByText("Observed time unavailable").length).toBeGreaterThan(0);
    expect(apiFetch.mock.calls).toHaveLength(1);
    expect(String(apiFetch.mock.calls[0]?.[0])).toContain("/investigations/case-1/indicators?limit=25&offset=0");
    expect(apiFetch.mock.calls.some(([path]) => String(path).includes("/indicators/indicator-b"))).toBe(false);
    expect(screen.getByRole("link", { name: "View Evidence" })).toHaveAttribute("href", "/investigations/case-1/evidence");
    expect(screen.getByRole("link", { name: "View Timeline" })).toHaveAttribute("href", "/investigations/case-1/timeline");
    expect(screen.queryByText("raw-1")).toBeNull();
  });

  it("keeps pagination URL-backed and resets offset when page size changes", async () => {
    apiFetch.mockResolvedValue(entityPage);
    render(<EntitiesWorkspace id="case-1" />);
    await screen.findAllByText("account-a");
    fireEvent.click(screen.getByRole("button", { name: "Next" }));
    await waitFor(() => expect(window.location.search).toContain("offset=25"));
    fireEvent.change(screen.getByLabelText("Entity page size"), { target: { value: "50" } });
    await waitFor(() => expect(window.location.search).toContain("limit=50"));
    expect(window.location.search).toContain("offset=0");
    expect(apiFetch.mock.calls.some(([path]) => String(path).includes("/entities?limit=50&offset=0"))).toBe(true);
  });

  it("distinguishes bounded state failures and allows a retry", async () => {
    apiFetch.mockRejectedValue(new ApiError("bounded", 403));
    render(<IndicatorsWorkspace id="case-1" />);
    expect(await screen.findByText("Permission denied")).toBeInTheDocument();
    cleanup(); apiFetch.mockReset();
    apiFetch.mockRejectedValueOnce(new ApiError("bounded", 500)).mockResolvedValue({ items: [], limit: 25, offset: 0, returned_count: 0, total: 0 });
    render(<IndicatorsWorkspace id="case-1" />);
    fireEvent.click(await screen.findByRole("button", { name: "Retry" }));
    expect(await screen.findByText("No Indicator occurrences")).toBeInTheDocument();
  });

  it("aborts scoped Entity and Indicator requests on unmount", async () => {
    let entitySignal: AbortSignal | undefined; let indicatorSignal: AbortSignal | undefined;
    apiFetch.mockImplementation((path: string, options?: { signal?: AbortSignal }) => { if (path.includes("/entities?")) entitySignal = options?.signal; if (path.includes("/indicators?")) indicatorSignal = options?.signal; return new Promise(() => undefined); });
    const entities = render(<EntitiesWorkspace id="case-1" />);
    await waitFor(() => expect(entitySignal).toBeDefined()); entities.unmount(); expect(entitySignal?.aborted).toBe(true);
    const indicators = render(<IndicatorsWorkspace id="case-1" />);
    await waitFor(() => expect(indicatorSignal).toBeDefined()); indicators.unmount(); expect(indicatorSignal?.aborted).toBe(true);
  });
});
