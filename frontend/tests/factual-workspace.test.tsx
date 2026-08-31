import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "@/lib/api-client";
import { EvidenceWorkspace, TimelineWorkspace } from "@/components/investigations/factual-workspace";

const { apiFetch } = vi.hoisted(() => ({ apiFetch: vi.fn() }));
vi.mock("@/lib/api-client", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api-client")>("@/lib/api-client");
  return { ...actual, apiFetch, downloadFile: vi.fn() };
});
vi.mock("next/navigation", () => ({ usePathname: () => "/investigations/case-1/evidence" }));
vi.mock("next/link", () => ({ default: ({ href, children }: { href: string; children: ReactNode }) => <a href={href}>{children}</a> }));
vi.mock("@/lib/auth-context", () => ({ useAuth: () => ({ hasPermission: (code: string) => code === "investigation:write" }) }));

const evidence = { id: "evidence-1", original_filename: "auth.log", sha256: "a".repeat(64), byte_size: 12, detected_mime: "text/plain", source_description: "sensor export", imported_at: "2026-01-01T00:00:00Z", parsing_status: "complete", parser_name: "line", parser_version: "1" };
const inventory = { id: "evidence-1", filename: "auth.log", sha256: "a".repeat(64), byte_size: 12, detected_mime: "text/plain", acquisition_source: "test", imported_at: "2026-01-01T00:00:00Z", parsing_status: "complete", latest_parse_status: "complete", parser_name: "line", parser_version: "1", parse_warning_count: 0, raw_record_count: 1, raw_content_unavailable_count: 0, event_count: 1, importer: { id: "user-1", display_name: "Analyst" } };

describe("factual workspace", () => {
  afterEach(cleanup);
  beforeEach(() => { apiFetch.mockReset(); });

  it("shows the bounded evidence inventory without loading raw-record content", async () => {
    apiFetch.mockImplementation((path: string) => path.includes("/evidence/inventory") ? Promise.resolve({ items: [inventory], limit: 25, offset: 0, total: 1 }) : Promise.resolve([]));
    render(<EvidenceWorkspace id="case-1" />);
    expect((await screen.findAllByText("auth.log")).length).toBeGreaterThan(0);
    expect(screen.getAllByText("1 records · 1 events").length).toBeGreaterThan(0);
    expect(apiFetch).toHaveBeenCalledTimes(1);
    expect(apiFetch.mock.calls[0]![0]).toContain("/evidence/inventory?limit=25&offset=0");
  });

  it("surfaces duplicate evidence feedback from the API", async () => {
    apiFetch.mockImplementation((path: string, options?: RequestInit) => options?.method === "POST" ? Promise.reject(new ApiError("Duplicate evidence already exists", 409)) : Promise.resolve({ items: [inventory], limit: 25, offset: 0, total: 1 }));
    render(<EvidenceWorkspace id="case-1" />);
    await screen.findAllByText("auth.log");
    const file = new File(["x"], "copy.log", { type: "text/plain" });
    fireEvent.change(document.querySelector('input[type="file"]')!, { target: { files: [file] } });
    expect(await screen.findByText("Unable to upload evidence. Please try again.")).toBeInTheDocument();
  });

  it("uses the bounded server Timeline projection and exposes safe provenance", async () => {
    apiFetch.mockImplementation((path: string) => path.includes("/evidence/inventory") ? Promise.resolve({ items: [inventory], limit: 200, offset: 0, total: 1 }) : Promise.resolve({ items: [{ id: "event-1", timestamp: "2026-01-01T00:00:00Z", time_basis: "SOURCE_EVENT_TIMESTAMP", event_type: "login", source: "safe", host: "host-a", user: "analyst", source_ip: "192.0.2.1", destination_ip: "198.51.100.1", deterministic_severity: "medium", evidence: { id: "evidence-1", filename: "auth.log" }, raw_content_available: true, raw_locator_available: true, provenance_status: "AVAILABLE" }], limit: 25, offset: 0, returned_count: 1, total: 1 }));
    render(<TimelineWorkspace id="case-1" />);
    expect((await screen.findAllByText("login")).length).toBeGreaterThan(0);
    expect(apiFetch.mock.calls.some(([path]) => String(path).includes("/timeline?limit=25&offset=0"))).toBe(true);
    expect(apiFetch.mock.calls.some(([path]) => String(path).endsWith("/events"))).toBe(false);
    fireEvent.click(screen.getByRole("button", { name: "Inspect event event-1" }));
    expect(await screen.findByText("Event inspector")).toBeInTheDocument();
    expect(screen.queryByText("normalized")).not.toBeInTheDocument();
  });
});
