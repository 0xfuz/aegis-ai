import { fireEvent, render, screen } from "@testing-library/react";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { CanonicalGraphWorkspace } from "@/components/investigations/canonical-graph-workspace";

vi.mock("next/navigation", () => ({ usePathname: () => "/investigations/case-1/relationships" }));
vi.mock("next/link", () => ({ default: ({ href, children }: { href: string; children: ReactNode }) => <a href={href}>{children}</a> }));
vi.mock("reactflow", () => ({
  default: ({ nodes, edges, onNodeClick, onEdgeClick }: { nodes: { id: string }[]; edges: { id: string }[]; onNodeClick: (event: unknown, node: { id: string }) => void; onEdgeClick: (event: unknown, edge: { id: string }) => void }) => <div>{nodes.map((node) => <button key={node.id} onClick={() => onNodeClick({}, node)}>node:{node.id}</button>)}{edges.map((edge) => <button key={edge.id} onClick={() => onEdgeClick({}, edge)}>edge:{edge.id}</button>)}</div>,
  Background: () => null, Controls: () => null, MiniMap: () => null, ReactFlowProvider: ({ children }: { children: ReactNode }) => <>{children}</>,
}));

const graph = { investigation_id: "case-1", nodes: [{ id: "entity:a", type: "HOST", label: "host-a", canonical_value: "host-a", observation_count: 2, first_seen_at: null, last_seen_at: null, status: "FACT", metadata: {} }, { id: "entity:b", type: "IP", label: "10.0.0.1", canonical_value: "10.0.0.1", observation_count: 1, first_seen_at: null, last_seen_at: null, status: "FACT", metadata: {} }], edges: [{ id: "relationship:a:b:CONNECTS_TO", source: "entity:a", target: "entity:b", relationship_type: "CONNECTS_TO", observed_at: null, first_seen_at: null, last_seen_at: null, occurrence_count: 1, confidence: null, status: "FACT", provenance: [{ relationship_id: "relationship-1", evidence_id: "evidence-1", raw_record_id: "raw-1", event_id: "event-1", source_observation_id: null, target_observation_id: null }] }] };

describe("canonical graph workspace", () => {
  beforeEach(() => { vi.unstubAllGlobals(); });
  it("shows the empty factual graph state", async () => {
    vi.stubGlobal("fetch", vi.fn((url: string) => Promise.resolve(new Response(JSON.stringify(url.endsWith("/graph") ? { investigation_id: "case-1", nodes: [], edges: [] } : []), { status: 200, headers: { "Content-Type": "application/json" } }))));
    render(<CanonicalGraphWorkspace id="case-1" />);
    expect(await screen.findByText(/No canonical factual graph data yet/)).toBeInTheDocument();
  });
  it("renders factual inspectors and preserves provenance navigation", async () => {
    vi.stubGlobal("fetch", vi.fn((url: string) => Promise.resolve(new Response(JSON.stringify(url.endsWith("/graph") ? graph : [{ id: "evidence-1", original_filename: "auth.log" }]), { status: 200, headers: { "Content-Type": "application/json" } }))));
    render(<CanonicalGraphWorkspace id="case-1" />);
    fireEvent.click(await screen.findByText("node:entity:a"));
    expect(await screen.findByText("Node inspector")).toBeInTheDocument();
    fireEvent.click(screen.getByText("edge:relationship:a:b:CONNECTS_TO"));
    expect(await screen.findByText("Edge inspector")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "evidence-1" })).toHaveAttribute("href", "/investigations/case-1/evidence");
  });
  it("shows API errors instead of a fallback graph", async () => {
    vi.stubGlobal("fetch", vi.fn(() => Promise.resolve(new Response(JSON.stringify({ detail: "denied" }), { status: 500, headers: { "Content-Type": "application/json" } }))));
    render(<CanonicalGraphWorkspace id="case-1" />);
    expect(await screen.findByText("denied")).toBeInTheDocument();
  });
});
