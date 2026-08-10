import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "@/lib/api-client";
import { EvidenceWorkspace, TimelineWorkspace } from "@/components/investigations/factual-workspace";

const { apiFetch } = vi.hoisted(() => ({ apiFetch: vi.fn() }));
vi.mock("@/lib/api-client", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api-client")>("@/lib/api-client");
  return { ...actual, apiFetch, downloadFile: vi.fn() };
});
vi.mock("next/navigation", () => ({ usePathname: () => "/investigations/case-1/evidence" }));
vi.mock("next/link", () => ({ default: ({ href, children }: { href: string; children: ReactNode }) => <a href={href}>{children}</a> }));

const evidence = { id: "evidence-1", original_filename: "auth.log", sha256: "a".repeat(64), byte_size: 12, detected_mime: "text/plain", source_description: "sensor export", imported_at: "2026-01-01T00:00:00Z", parsing_status: "complete", parser_name: "line", parser_version: "1" };

describe("factual workspace", () => {
  beforeEach(() => { apiFetch.mockReset(); });

  it("shows evidence and raw-record provenance", async () => {
    apiFetch.mockImplementation((path: string) => path.endsWith("/evidence") ? Promise.resolve([evidence]) : Promise.resolve([{ id: "raw-1", ordinal: 0, content: "log line", content_type: "text/plain", byte_offset: 0, line_start: 1, line_end: 1 }]));
    render(<EvidenceWorkspace id="case-1" />);
    expect(await screen.findByText("auth.log")).toBeInTheDocument();
    fireEvent.click(screen.getByText("auth.log"));
    expect(await screen.findByText("Raw records")).toBeInTheDocument();
    expect(screen.getByText("#0 · text/plain")).toBeInTheDocument();
  });

  it("surfaces duplicate evidence feedback from the API", async () => {
    apiFetch.mockImplementation((path: string, options?: RequestInit) => options?.method === "POST" ? Promise.reject(new ApiError("Duplicate evidence already exists", 409)) : Promise.resolve([evidence]));
    render(<EvidenceWorkspace id="case-1" />);
    await screen.findByText("auth.log");
    const file = new File(["x"], "copy.log", { type: "text/plain" });
    fireEvent.change(document.querySelector('input[type="file"]')!, { target: { files: [file] } });
    expect(await screen.findByText("Duplicate evidence already exists")).toBeInTheDocument();
  });

  it("filters canonical events and exposes event provenance", async () => {
    apiFetch.mockImplementation((path: string) => path.endsWith("/events") ? Promise.resolve([{ id: "event-1", evidence_id: "evidence-1", raw_record_id: "raw-1", timestamp: "2026-01-01T00:00:00Z", host: "host-a", user: "analyst", source_ip: "10.0.0.1", destination_ip: "10.0.0.2", event_type: "login", normalized: { action: "login" } }]) : Promise.resolve([evidence]));
    render(<TimelineWorkspace id="case-1" />);
    expect(await screen.findByText("login")).toBeInTheDocument();
    fireEvent.change(screen.getByPlaceholderText("Host"), { target: { value: "other-host" } });
    await waitFor(() => expect(screen.queryByText("login")).not.toBeInTheDocument());
    fireEvent.change(screen.getByPlaceholderText("Host"), { target: { value: "host-a" } });
    fireEvent.click(await screen.findByText("login"));
    expect(await screen.findByText("Event provenance")).toBeInTheDocument();
    expect(screen.getByText("raw-1")).toBeInTheDocument();
  });
});
