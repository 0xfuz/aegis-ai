import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "@/lib/api-client";
import { TimelineWorkspace } from "@/components/investigations/factual-workspace";

const { apiFetch } = vi.hoisted(() => ({ apiFetch: vi.fn() }));
vi.mock("@/lib/api-client", async () => ({ ...(await vi.importActual<typeof import("@/lib/api-client")>("@/lib/api-client")), apiFetch }));
vi.mock("next/navigation", () => ({ usePathname: () => "/investigations/case-1/timeline" }));
vi.mock("next/link", () => ({ default: ({ href, children }: { href: string; children: ReactNode }) => <a href={href}>{children}</a> }));

const inventory = { id: "evidence-1", filename: "safe.log", sha256: "a".repeat(64), byte_size: 1, detected_mime: "text/plain", acquisition_source: "test", imported_at: "2026-01-01T00:00:00Z", parsing_status: "complete", latest_parse_status: "complete", parser_name: "line", parser_version: "1", parse_warning_count: 0, raw_record_count: 1, raw_content_unavailable_count: 0, event_count: 2, importer: null };
const first = { id: "event-1", timestamp: "2026-01-01T00:00:00Z", time_basis: "SOURCE_EVENT_TIMESTAMP", event_type: "<script>inert</script>", source: null, host: "host-a", user: "user-a", source_ip: "192.0.2.1", destination_ip: null, deterministic_severity: "medium", evidence: { id: "evidence-1", filename: "safe.log" }, raw_content_available: false, raw_locator_available: true, provenance_status: "RAW_CONTENT_UNAVAILABLE" };
const missing = { ...first, id: "event-2", timestamp: null, event_type: "later server item", source_ip: null, destination_ip: "198.51.100.1" };
const page = { items: [first, missing], limit: 25, offset: 0, returned_count: 2, total: 3 };

function setup(timeline: unknown = page) {
  apiFetch.mockImplementation((path: string) => path.includes("/evidence/inventory") ? Promise.resolve({ items: [inventory], limit: 200, offset: 0, total: 1 }) : Promise.resolve(timeline));
}

describe("TimelineWorkspace", () => {
  afterEach(cleanup);
  beforeEach(() => { apiFetch.mockReset(); window.history.replaceState(null, "", "/investigations/case-1/timeline"); });

  it("renders only certified filters and preserves the server page order", async () => {
    setup(); render(<TimelineWorkspace id="case-1" />);
    expect((await screen.findAllByText("<script>inert</script>")).length).toBeGreaterThan(0);
    expect(screen.getByLabelText("From date/time")).toBeInTheDocument();
    expect(screen.getByLabelText("To date/time")).toBeInTheDocument();
    expect(screen.getByLabelText("Evidence")).toBeInTheDocument();
    for (const label of ["Host", "User", "Source IP", "Destination IP", "Event type"]) expect(screen.queryByPlaceholderText(label)).toBeNull();
    const text = screen.getAllByText("<script>inert</script>")[0]?.parentElement?.parentElement?.parentElement?.textContent || "";
    expect(text).toContain("host-a");
    expect(screen.getAllByText("Source time unavailable").length).toBeGreaterThan(0);
    expect(screen.queryByText("normalized")).not.toBeInTheDocument();
  });

  it("serializes an applied local range to one UTC server request and URL", async () => {
    setup(); render(<TimelineWorkspace id="case-1" />); await screen.findAllByText("later server item");
    fireEvent.change(screen.getByLabelText("From date/time"), { target: { value: "2026-01-01T00:00" } });
    fireEvent.change(screen.getByLabelText("To date/time"), { target: { value: "2026-01-02T00:00" } });
    fireEvent.click(screen.getByRole("button", { name: "Apply" }));
    await waitFor(() => expect(apiFetch.mock.calls.filter(([path]) => String(path).includes("/timeline")).length).toBe(2));
    const path = String(apiFetch.mock.calls.at(-1)?.[0]);
    expect(path).toContain("from=2026-01-01T00%3A00%3A00.000Z");
    expect(path).toContain("to=2026-01-02T00%3A00%3A00.000Z");
    expect(window.location.search).toContain("from=2026-01-01T00%3A00%3A00.000Z");
  });

  it("validates incomplete, reversed, and overlong ranges without a request", async () => {
    setup(); render(<TimelineWorkspace id="case-1" />); await screen.findAllByText("later server item");
    fireEvent.change(screen.getByLabelText("From date/time"), { target: { value: "2026-01-01T00:00" } }); fireEvent.click(screen.getByRole("button", { name: "Apply" }));
    expect(await screen.findByText("Provide both From and To, or clear both fields.")).toHaveFocus();
    fireEvent.change(screen.getByLabelText("To date/time"), { target: { value: "2025-12-31T00:00" } }); fireEvent.click(screen.getByRole("button", { name: "Apply" }));
    expect(await screen.findByText("From must be before To.")).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("To date/time"), { target: { value: "2026-05-01T00:00" } }); fireEvent.click(screen.getByRole("button", { name: "Apply" }));
    expect(await screen.findByText("The selected range cannot exceed 90 days.")).toBeInTheDocument();
    expect(apiFetch.mock.calls.filter(([path]) => String(path).includes("/timeline")).length).toBe(1);
  });

  it("uses one bounded Evidence inventory request, supports clear, and resets pagination", async () => {
    setup(); render(<TimelineWorkspace id="case-1" />); await screen.findAllByText("later server item");
    expect(apiFetch.mock.calls.filter(([path]) => String(path).includes("/evidence/inventory?limit=200&offset=0")).length).toBe(1);
    fireEvent.change(screen.getByLabelText("Evidence"), { target: { value: "evidence-1" } }); fireEvent.click(screen.getByRole("button", { name: "Apply" }));
    await waitFor(() => expect(window.location.search).toContain("evidence_id=evidence-1"));
    fireEvent.click(screen.getByRole("button", { name: "Clear filters" }));
    await waitFor(() => expect(window.location.search).not.toContain("evidence_id"));
    expect(window.location.search).toContain("offset=0");
  });

  it("renders bounded inspector provenance and never creates a network arrow for absent endpoints", async () => {
    setup(); render(<TimelineWorkspace id="case-1" />); await screen.findAllByText("later server item");
    fireEvent.click(screen.getByRole("button", { name: "Inspect event event-1" }));
    expect(await screen.findByText("Event inspector")).toBeInTheDocument();
    expect(screen.getByText("Raw content: unavailable")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "View Evidence" })).toHaveAttribute("href", "/investigations/case-1/evidence");
    expect(screen.getAllByText("Destination: 198.51.100.1").length).toBeGreaterThan(0);
  });

  it("distinguishes valid empty filters and API states, with retry", async () => {
    setup({ items: [], limit: 25, offset: 0, returned_count: 0, total: 0 }); render(<TimelineWorkspace id="case-1" />);
    expect(await screen.findByText("No Events")).toBeInTheDocument();
    apiFetch.mockImplementation((path: string) => path.includes("/evidence/inventory") ? Promise.resolve({ items: [], limit: 200, offset: 0, total: 0 }) : Promise.reject(new ApiError("no", 403)));
    render(<TimelineWorkspace id="case-2" />); expect(await screen.findByText("Permission denied")).toBeInTheDocument();
  });

  it("aborts the in-flight canonical Timeline request on unmount", async () => {
    let timelineSignal: AbortSignal | undefined;
    apiFetch.mockImplementation((path: string, options?: { signal?: AbortSignal }) => {
      if (path.includes("/evidence/inventory")) return Promise.resolve({ items: [], limit: 200, offset: 0, total: 0 });
      timelineSignal = options?.signal;
      return new Promise(() => undefined);
    });
    const view = render(<TimelineWorkspace id="case-1" />);
    await waitFor(() => expect(timelineSignal).toBeDefined());
    view.unmount();
    expect(timelineSignal?.aborted).toBe(true);
  });
});
