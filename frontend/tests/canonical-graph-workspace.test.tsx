import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { CanonicalGraphWorkspace } from "@/components/investigations/canonical-graph-workspace";

vi.mock("next/navigation", () => ({ usePathname: () => "/investigations/case-1/relationships" }));
vi.mock("next/link", () => ({ default: ({ href, children }: { href: string; children: ReactNode }) => <a href={href}>{children}</a> }));
vi.mock("reactflow", () => ({
  default: ({ nodes, edges, onNodeClick, onEdgeClick }: { nodes: { id: string }[]; edges: { id: string }[]; onNodeClick: (event: unknown, node: { id: string }) => void; onEdgeClick: (event: unknown, edge: { id: string }) => void }) => <div>{nodes.map((node) => <button key={node.id} onClick={() => onNodeClick({}, node)}>node:{node.id}</button>)}{edges.map((edge) => <button key={edge.id} onClick={() => onEdgeClick({}, edge)}>edge:{edge.id}</button>)}</div>,
  Background: () => null, Controls: () => null, MiniMap: () => null, ReactFlowProvider: ({ children }: { children: ReactNode }) => <>{children}</>,
}));

const graph = { investigation_id: "case-1", policy_id: "canonical-graph-v1", omissions: { nodes: 0, edges: 0, reason: null }, nodes: [{ id: "entity:a", type: "HOST", label: "host-a", canonical_value: "host-a", observation_count: 2, first_seen_at: null, last_seen_at: null, status: "FACT" }, { id: "entity:b", type: "IP", label: "10.0.0.1", canonical_value: "10.0.0.1", observation_count: 1, first_seen_at: null, last_seen_at: null, status: "FACT" }], edges: [{ id: "relationship:a:b:CONNECTS_TO", source: "entity:a", target: "entity:b", relationship_type: "CONNECTS_TO", observed_at: null, first_seen_at: null, last_seen_at: null, occurrence_count: 1, support_omitted: 0, status: "FACT", provenance: [{ relationship_id: "relationship-1", evidence_id: "evidence-1", event_id: "event-1", source_observation_id: null, target_observation_id: null, derivation_name: "safe", derivation_version: "v1", observed_at: null, support_status: "AVAILABLE" }] }] };

describe("canonical graph workspace", () => {
  beforeEach(() => { vi.unstubAllGlobals(); });
  afterEach(() => cleanup());
  it("shows the empty factual graph state", async () => {
    vi.stubGlobal("fetch", vi.fn((url: string) => Promise.resolve(new Response(JSON.stringify(url.endsWith("/graph") ? { investigation_id: "case-1", policy_id: "canonical-graph-v1", omissions: { nodes: 0, edges: 0, reason: null }, nodes: [], edges: [] } : []), { status: 200, headers: { "Content-Type": "application/json" } }))));
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
    expect(screen.queryByText(/Raw record/i)).not.toBeInTheDocument();
  });
  it("asks the canonical server projection to apply filters", async () => {
    const fetchMock = vi.fn((url: string) => Promise.resolve(
      new Response(JSON.stringify(url.includes("/graph") ? graph : [{ id: "evidence-1", original_filename: "auth.log" }]), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    ));
    vi.stubGlobal("fetch", fetchMock);
    render(<CanonicalGraphWorkspace id="case-1" />);
    await screen.findByText("node:entity:a");
    fireEvent.change(screen.getAllByLabelText("Entity type").at(-1)!, { target: { value: "HOST" } });
    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith(expect.stringContaining("entity_type=HOST"), expect.objectContaining({ signal: expect.any(AbortSignal) })));
  });
  it("shows API errors instead of a fallback graph", async () => {
    vi.stubGlobal("fetch", vi.fn(() => Promise.resolve(new Response(JSON.stringify({ detail: "denied" }), { status: 500, headers: { "Content-Type": "application/json" } }))));
    render(<CanonicalGraphWorkspace id="case-1" />);
    expect(await screen.findByText("denied")).toBeInTheDocument();
  });
  it("renders bounded persisted labels as inert text", async () => {
    const hostileGraph = { ...graph, nodes: [{ ...graph.nodes[0], label: "<img src=x onerror=alert(1)>" }, graph.nodes[1]] };
    vi.stubGlobal("fetch", vi.fn((url: string) => Promise.resolve(new Response(JSON.stringify(url.endsWith("/graph") ? hostileGraph : []), { status: 200, headers: { "Content-Type": "application/json" } }))));
    render(<CanonicalGraphWorkspace id="case-1" />);
    fireEvent.click(await screen.findByText("node:entity:a"));
    expect(await screen.findByText("<img src=x onerror=alert(1)>")).toBeInTheDocument();
    expect(document.querySelector("img")).toBeNull();
  });
});
