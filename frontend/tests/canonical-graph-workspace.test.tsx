import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { CanonicalGraphWorkspace } from "@/components/investigations/canonical-graph-workspace";

const state = vi.hoisted(() => ({ replace: vi.fn(), search: "" }));
vi.mock("next/navigation", () => ({ usePathname: () => "/investigations/case-1/relationships", useRouter: () => ({ replace: state.replace }), useSearchParams: () => new URLSearchParams(state.search) }));
vi.mock("next/link", () => ({ default: ({ href, children }: { href: string; children: ReactNode }) => <a href={href}>{children}</a> }));
vi.mock("reactflow", () => ({
  default: ({ nodes, edges, onNodeClick, onEdgeClick, children }: { nodes: { id: string }[]; edges: { id: string }[]; children: ReactNode; onNodeClick: (event: { target: null }, node: { id: string }) => void; onEdgeClick: (event: { target: null }, edge: { id: string }) => void }) => <div>{nodes.map((node) => <button key={node.id} onClick={() => onNodeClick({ target: null }, node)}>node:{node.id}</button>)}{edges.map((edge) => <button key={edge.id} onClick={() => onEdgeClick({ target: null }, edge)}>edge:{edge.id}</button>)}{children}</div>,
  Background: () => null, MarkerType: { ArrowClosed: "arrowclosed" }, MiniMap: () => null, ReactFlowProvider: ({ children }: { children: ReactNode }) => <>{children}</>, useReactFlow: () => ({ zoomIn: vi.fn(), zoomOut: vi.fn(), fitView: vi.fn() }),
}));

const graph = { investigation_id: "case-1", policy_id: "canonical-graph-v1", omissions: { nodes: 0, edges: 0, reason: null }, nodes: [{ id: "entity:a", type: "HOST", label: "host-a", canonical_value: "host-a", observation_count: 2, first_seen_at: null, last_seen_at: null, status: "FACT" }, { id: "entity:b", type: "IP", label: "10.0.0.1", canonical_value: "10.0.0.1", observation_count: 1, first_seen_at: null, last_seen_at: null, status: "FACT" }], edges: [{ id: "relationship:a:b:CONNECTS_TO", source: "entity:a", target: "entity:b", relationship_type: "CONNECTS_TO", observed_at: null, first_seen_at: null, last_seen_at: null, occurrence_count: 1, support_omitted: 0, status: "FACT", provenance: [{ relationship_id: "relationship-1", evidence_id: "evidence-1", event_id: "event-1", source_observation_id: null, target_observation_id: null, derivation_name: "safe", derivation_version: "v1", observed_at: null, support_status: "AVAILABLE" }] }] };

describe("canonical graph workspace", () => {
  beforeEach(() => { vi.unstubAllGlobals(); state.replace.mockReset(); state.search = ""; });
  afterEach(() => cleanup());
  it("distinguishes an empty factual graph", async () => {
    vi.stubGlobal("fetch", vi.fn((url: string) => Promise.resolve(new Response(JSON.stringify(url.includes("/graph") ? { investigation_id: "case-1", policy_id: "canonical-graph-v1", omissions: { nodes: 0, edges: 0, reason: null }, nodes: [], edges: [] } : []), { status: 200, headers: { "Content-Type": "application/json" } }))));
    render(<CanonicalGraphWorkspace id="case-1" />);
    expect(await screen.findByText("No factual relationships")).toBeInTheDocument();
  });
  it("renders returned factual identities, dark controls, and bounded inspector navigation", async () => {
    vi.stubGlobal("fetch", vi.fn((url: string) => Promise.resolve(new Response(JSON.stringify(url.includes("/graph") ? graph : [{ id: "evidence-1", original_filename: "auth.log" }]), { status: 200, headers: { "Content-Type": "application/json" } }))));
    render(<CanonicalGraphWorkspace id="case-1" />);
    fireEvent.click(await screen.findByText("node:entity:a"));
    expect(await screen.findByText("Node inspector")).toBeInTheDocument();
    expect(screen.getAllByText(/HOST · FACT/).length).toBeGreaterThan(0);
    fireEvent.click(screen.getByText("edge:relationship:a:b:CONNECTS_TO"));
    expect(await screen.findByText("Relationship inspector")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "View supporting Evidence" })).toHaveAttribute("href", "/investigations/case-1/evidence");
    expect(screen.getByText(/Legend:/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Fit graph" })).toBeVisible();
    expect(screen.queryByText(/Raw record/i)).not.toBeInTheDocument();
  });
  it("uses one canonical server graph request per filter and URL-backs it", async () => {
    const fetchMock = vi.fn((url: string) => Promise.resolve(
      new Response(JSON.stringify(url.includes("/graph") ? graph : [{ id: "evidence-1", original_filename: "auth.log" }]), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    ));
    vi.stubGlobal("fetch", fetchMock);
    render(<CanonicalGraphWorkspace id="case-1" />);
    await screen.findByText("node:entity:a");
    fireEvent.change(screen.getByLabelText("Entity type"), { target: { value: "HOST" } });
    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith(expect.stringContaining("entity_type=HOST"), expect.objectContaining({ signal: expect.any(AbortSignal) })));
    expect(state.replace).toHaveBeenCalledWith("/investigations/case-1/relationships?entity_type=HOST");
    expect(fetchMock.mock.calls.filter(([url]) => String(url).includes("/evidence")).length).toBe(1);
  });
  it("restores URL-backed filters and handles bounded authorization and retry states", async () => {
    state.search = "entity_type=HOST&relationship_type=CONNECTS_TO&evidence_id=evidence-1";
    const fetchMock = vi.fn(() => Promise.resolve(new Response(JSON.stringify({ detail: "not exposed" }), { status: 403, headers: { "Content-Type": "application/json" } })));
    vi.stubGlobal("fetch", fetchMock);
    render(<CanonicalGraphWorkspace id="case-1" />);
    expect(await screen.findByText("Permission denied")).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledWith(expect.stringContaining("entity_type=HOST&relationship_type=CONNECTS_TO&evidence_id=evidence-1"), expect.any(Object));
  });
  it("shows a bounded retry instead of a fallback graph", async () => {
    vi.stubGlobal("fetch", vi.fn(() => Promise.resolve(new Response(JSON.stringify({ detail: "internal detail" }), { status: 500, headers: { "Content-Type": "application/json" } }))));
    render(<CanonicalGraphWorkspace id="case-1" />);
    expect(await screen.findByText("Graph unavailable")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Retry" })).toBeVisible();
    expect(screen.queryByText("internal detail")).toBeNull();
  });
  it("aborts stale graph work on unmount", async () => {
    let resolveFirst: (value: Response) => void = () => undefined;
    const first = new Promise<Response>((resolve) => { resolveFirst = resolve; });
    const fetchMock = vi.fn((url: string) => url.includes("/graph") ? first : Promise.resolve(new Response(JSON.stringify([]), { status: 200, headers: { "Content-Type": "application/json" } })));
    vi.stubGlobal("fetch", fetchMock);
    const view = render(<CanonicalGraphWorkspace id="case-1" />);
    expect(await screen.findByText("Loading canonical graph")).toBeInTheDocument();
    view.unmount();
    resolveFirst(new Response(JSON.stringify(graph), { status: 200, headers: { "Content-Type": "application/json" } }));
    await Promise.resolve();
    expect(screen.queryByText("Canonical Attack Graph")).toBeNull();
  });
  it("shows bounded omission and unavailable support without choosing a factual replacement", async () => {
    const originalEdge = graph.edges[0]!;
    const bounded = { ...graph, omissions: { nodes: 1, edges: 2, reason: "POLICY_LIMIT" }, edges: [{ ...originalEdge, support_omitted: 1, provenance: [{ ...originalEdge.provenance[0]!, support_status: "UNAVAILABLE" as const }] }] };
    vi.stubGlobal("fetch", vi.fn((url: string) => Promise.resolve(new Response(JSON.stringify(url.includes("/graph") ? bounded : []), { status: 200, headers: { "Content-Type": "application/json" } }))));
    render(<CanonicalGraphWorkspace id="case-1" />);
    await screen.findByText("edge:relationship:a:b:CONNECTS_TO");
    fireEvent.click(screen.getByText("edge:relationship:a:b:CONNECTS_TO"));
    expect(await screen.findByText("Relationship inspector")).toBeInTheDocument();
    expect(await screen.findByText(/^Support:/)).toHaveTextContent("Supporting provenance unavailable");
    expect(screen.getByText(/supporting reference was omitted/)).toBeInTheDocument();
    expect(screen.getByText(/Bounded graph notice: 1 node and 2 edges omitted/)).toBeInTheDocument();
  });
  it("renders hostile labels as inert text", async () => {
    const hostileGraph = { ...graph, nodes: [{ ...graph.nodes[0], label: "<img src=x onerror=alert(1)>" }, graph.nodes[1]] };
    vi.stubGlobal("fetch", vi.fn((url: string) => Promise.resolve(new Response(JSON.stringify(url.includes("/graph") ? hostileGraph : []), { status: 200, headers: { "Content-Type": "application/json" } }))));
    render(<CanonicalGraphWorkspace id="case-1" />);
    fireEvent.click(await screen.findByText("node:entity:a"));
    expect((await screen.findAllByText("<img src=x onerror=alert(1)>")).length).toBeGreaterThan(0);
    expect(document.querySelector("img")).toBeNull();
  });
});
