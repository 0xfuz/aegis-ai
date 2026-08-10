"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import ReactFlow, { Background, MiniMap, ReactFlowProvider, useReactFlow, useStore, type Edge, type EdgeMouseHandler, type Node, type NodeMouseHandler, type ReactFlowState } from "reactflow";
import "reactflow/dist/style.css";
import { GraphNode } from "./graph-node";
import { NodeDetailPanel } from "./node-detail-panel";
import { FilterPanel, defaultFilters, type GraphFilters } from "./filters";
import { derivePrimaryPath, layoutDirection, layoutGraph } from "./layout";
import { NODE_COLORS, TIER_BORDER_STYLE } from "./node-visuals";
import type { AttackGraphData, AttackGraphEdge, GraphLayoutMode } from "./types";

const nodeTypes = { graphNode: GraphNode };
const LARGE_GRAPH_THRESHOLD = 150;
const INSPECTOR_WIDTH = 336;

type AggregatedEdge = AttackGraphEdge & { records: AttackGraphEdge[] };

export function aggregateRelationships(edges: AttackGraphEdge[]): AggregatedEdge[] {
  const groups = new Map<string, AttackGraphEdge[]>();
  for (const edge of edges) {
    const key = `${edge.source}\u0000${edge.target}\u0000${edge.relationship}\u0000${edge.tier}`;
    groups.set(key, [...(groups.get(key) ?? []), edge]);
  }
  return [...groups.values()].flatMap((records) => {
    const first = records[0];
    return first ? [{ ...first, id: records.map((edge) => edge.id).sort().join("+"), records }] : [];
  });
}

export function shouldShowEdgeLabel(zoom: number, active: boolean, corridorIndex: number): boolean {
  // At overview zoom only the selected/hovered relationship is named. At
  // readable zoom, retain one label per corridor to avoid a label stack.
  return active || (zoom >= 0.86 && corridorIndex === 0);
}

function ControlButton({ onClick, title, children, disabled = false }: { onClick: () => void; title: string; children: React.ReactNode; disabled?: boolean }) {
  return <button type="button" onClick={onClick} title={title} aria-label={title} disabled={disabled} className="rounded border border-hairline bg-surface px-2.5 py-1.5 text-xs text-text-muted hover:border-signal hover:text-signal focus:outline-none focus:ring-2 focus:ring-signal disabled:opacity-40">{children}</button>;
}

function AttackGraphInner({ graph }: { graph: AttackGraphData }) {
  const { fitView, zoomIn, zoomOut, setCenter, getZoom } = useReactFlow();
  const zoom = useStore((state: ReactFlowState) => state.transform[2]);
  const [filters, setFilters] = useState<GraphFilters>(() => defaultFilters(graph));
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null);
  const [selectedEdge, setSelectedEdge] = useState<AggregatedEdge | null>(null);
  // LR keeps directional investigation chains compact on ordinary wide screens.
  const [layoutMode, setLayoutMode] = useState<GraphLayoutMode>("left-right");
  const [focusIds, setFocusIds] = useState<Set<string> | null>(null);
  const [layoutVersion, setLayoutVersion] = useState(0);
  const direction = layoutDirection(layoutMode);
  const primaryPathIds = useMemo(() => derivePrimaryPath(graph), [graph]);

  const filteredIds = useMemo(() => new Set(graph.nodes.filter((node) => filters.types.has(node.type) && filters.tiers.has(node.tier) && (!filters.mitreTechnique || node.type !== "mitre_technique" || node.label === filters.mitreTechnique)).map((node) => node.id)), [graph.nodes, filters]);
  const visibleIds = useMemo(() => focusIds ? new Set([...filteredIds].filter((id) => focusIds.has(id))) : filteredIds, [filteredIds, focusIds]);
  const visibleNodes = useMemo(() => graph.nodes.filter((node) => visibleIds.has(node.id)), [graph.nodes, visibleIds]);
  const visibleEdges = useMemo(() => graph.edges.filter((edge) => filters.relationships.has(edge.relationship) && visibleIds.has(edge.source) && visibleIds.has(edge.target)), [graph.edges, filters.relationships, visibleIds]);
  const aggregateEdges = useMemo(() => aggregateRelationships(visibleEdges), [visibleEdges]);
  const positioned = useMemo(() => {
    // An explicit Auto Arrange requests a fresh deterministic Dagre pass.
    void layoutVersion;
    return layoutGraph(visibleNodes, aggregateEdges, direction);
  }, [visibleNodes, aggregateEdges, direction, layoutVersion]);

  const hasInspector = !!selectedNodeId || !!selectedEdge;
  const fitUsableCanvas = useCallback(() => fitView({ padding: hasInspector ? 0.3 : 0.18, minZoom: 0.35, duration: 250 }), [fitView, hasInspector]);
  useEffect(() => { const id = requestAnimationFrame(fitUsableCanvas); return () => cancelAnimationFrame(id); }, [positioned, fitUsableCanvas]);

  const emphasisIds = useMemo(() => {
    if (selectedEdge) return new Set([selectedEdge.source, selectedEdge.target]);
    if (!selectedNodeId) return null;
    const ids = new Set([selectedNodeId]);
    for (const edge of visibleEdges) if (edge.source === selectedNodeId || edge.target === selectedNodeId) { ids.add(edge.source); ids.add(edge.target); }
    return ids;
  }, [selectedNodeId, selectedEdge, visibleEdges]);

  const flowNodes: Node[] = useMemo(() => positioned.map((node) => ({ id: node.id, type: "graphNode", position: { x: node.x, y: node.y }, selected: node.id === selectedNodeId || (!!selectedEdge && (node.id === selectedEdge.source || node.id === selectedEdge.target)), data: { ...node, direction, dimmed: emphasisIds ? !emphasisIds.has(node.id) : false, highlighted: emphasisIds ? emphasisIds.has(node.id) && node.id !== selectedNodeId : false, onPrimaryPath: primaryPathIds.has(node.id) } })), [positioned, direction, emphasisIds, selectedNodeId, selectedEdge, primaryPathIds]);
  const flowEdges: Edge[] = useMemo(() => aggregateEdges.map((edge, index) => {
    const active = selectedEdge?.id === edge.id || (!!selectedNodeId && (edge.source === selectedNodeId || edge.target === selectedNodeId));
    const dimmed = emphasisIds ? !(emphasisIds.has(edge.source) && emphasisIds.has(edge.target)) : false;
    const tier = TIER_BORDER_STYLE[edge.tier];
    const corridorIndex = aggregateEdges.findIndex((candidate) => candidate.source === edge.source || candidate.target === edge.target);
    const showLabel = shouldShowEdgeLabel(zoom, active, corridorIndex === index ? 0 : 1);
    return { id: edge.id, source: edge.source, target: edge.target, type: "smoothstep", label: showLabel ? `${edge.relationship.replace(/_/g, " ")}${edge.records.length > 1 ? ` × ${edge.records.length}` : ""}` : undefined, labelShowBg: showLabel, labelBgStyle: { fill: "#10151fcc", stroke: "#3a4453", strokeWidth: 1, rx: 4, ry: 4 }, labelBgPadding: [4, 2] as [number, number], labelStyle: { fill: "#aeb8c8", fontSize: 9, pointerEvents: "none" }, style: { stroke: active ? "#4DD8E8" : dimmed ? "#252c38" : "#4DD8E899", strokeWidth: active ? 3 : tier.width, strokeDasharray: tier.dasharray === "0" ? undefined : tier.dasharray, opacity: dimmed ? 0.14 : tier.opacity } };
  }), [aggregateEdges, selectedEdge, selectedNodeId, emphasisIds, zoom]);

  const selectNode = useCallback((id: string | null) => { setSelectedEdge(null); setSelectedNodeId(id); if (id) { const node = positioned.find((item) => item.id === id); if (node) { const nextZoom = Math.max(getZoom(), 0.9); setCenter(node.x + node.width / 2 + INSPECTOR_WIDTH / (2 * nextZoom), node.y + node.height / 2, { zoom: nextZoom, duration: 300 }); } } }, [positioned, setCenter, getZoom]);
  const focusNode = useCallback((id: string, expanded = false) => { const ids = new Set([id]); for (const edge of graph.edges) if (edge.source === id || edge.target === id) { ids.add(edge.source); ids.add(edge.target); if (expanded) for (const next of graph.edges) if (next.source === edge.source || next.target === edge.source || next.source === edge.target || next.target === edge.target) { ids.add(next.source); ids.add(next.target); } } setFocusIds(ids); selectNode(id); }, [graph.edges, selectNode]);
  const selectedNode = graph.nodes.find((node) => node.id === selectedNodeId) ?? null;

  return <div className="relative h-full w-full">
    <ReactFlow nodes={flowNodes} edges={flowEdges} nodeTypes={nodeTypes} onNodeClick={((_event, node) => selectNode(selectedNodeId === node.id ? null : node.id)) as NodeMouseHandler} onEdgeClick={((_event, edge) => { setSelectedNodeId(null); setSelectedEdge(aggregateEdges.find((item) => item.id === edge.id) ?? null); }) as EdgeMouseHandler} onPaneClick={() => { setSelectedNodeId(null); setSelectedEdge(null); }} minZoom={0.1} maxZoom={2} proOptions={{ hideAttribution: true }}>
      <Background color="#252C38" gap={24} /><MiniMap nodeColor={(node) => NODE_COLORS[(node.data as { type: keyof typeof NODE_COLORS }).type]?.border ?? "#8A93A3"} maskColor="rgba(10,13,18,0.7)" className="!border !border-hairline !bg-surface" />
    </ReactFlow>
    <FilterPanel graph={graph} filters={filters} onChange={(next) => { setFilters(next); setFocusIds(null); }} />
    <div className="absolute left-1/2 top-4 z-10 -translate-x-1/2 rounded-full border border-hairline bg-surface px-3 py-1 text-[11px] text-text-muted"><label htmlFor="graph-layout" className="sr-only">Graph layout</label><select id="graph-layout" aria-label="Graph layout" value={layoutMode} onChange={(event) => setLayoutMode(event.target.value as GraphLayoutMode)} className="mr-2 bg-transparent text-text-primary focus:outline-none"><option value="hierarchical">Hierarchical</option><option value="top-bottom">Top to Bottom</option><option value="left-right">Left to Right</option></select>{visibleNodes.length} of {graph.nodes.length} nodes{graph.nodes.length >= LARGE_GRAPH_THRESHOLD ? " · Large graph: use filters or focus" : ""}</div>
    {positioned.some((node) => node.region === "unconnected") && <div className="absolute bottom-16 right-4 z-10 rounded border border-hairline bg-surface px-3 py-1.5 text-[11px] text-text-muted">Unconnected facts are shown in a separate region; no relationship is inferred.</div>}
    <div className="absolute bottom-4 left-4 z-10 flex flex-wrap gap-1.5"><ControlButton onClick={fitUsableCanvas} title="Fit the current investigation in the usable canvas">Fit to Investigation</ControlButton><ControlButton onClick={() => { setFocusIds(new Set(primaryPathIds)); }} title="Focus the primary attack path">Fit to Attack Path</ControlButton><ControlButton onClick={() => setLayoutVersion((value) => value + 1)} title="Recompute deterministic layout">Auto Arrange</ControlButton><ControlButton onClick={() => selectedNodeId && focusNode(selectedNodeId)} title="Focus selected node and direct neighbours" disabled={!selectedNodeId}>Focus Selection</ControlButton><ControlButton onClick={() => setFocusIds(null)} title="Clear focus and show the filtered graph">Clear Focus</ControlButton><ControlButton onClick={() => { setFocusIds(null); setSelectedNodeId(null); setSelectedEdge(null); setLayoutVersion((value) => value + 1); }} title="Reset layout and selection">Reset Layout</ControlButton><ControlButton onClick={() => zoomIn({ duration: 200 })} title="Zoom in">Zoom In</ControlButton><ControlButton onClick={() => zoomOut({ duration: 200 })} title="Zoom out">Zoom Out</ControlButton></div>
    {selectedNode && <NodeDetailPanel node={selectedNode} graph={graph} onClose={() => setSelectedNodeId(null)} onSelectNode={selectNode} onFocus={() => focusNode(selectedNode.id)} onExpand={() => focusNode(selectedNode.id, true)} />}
    {selectedEdge && <div className="absolute right-4 top-4 z-10 w-80 rounded-card border border-hairline bg-surface p-4 shadow-lg"><div className="flex justify-between"><b className="text-sm">Edge inspector</b><button type="button" aria-label="Close edge inspector" onClick={() => setSelectedEdge(null)}>✕</button></div><p className="mt-2 text-xs uppercase text-cognition">{selectedEdge.relationship.replace(/_/g, " ")}</p><p className="mt-2 text-xs text-text-muted">{graph.nodes.find((node) => node.id === selectedEdge.source)?.label} → {graph.nodes.find((node) => node.id === selectedEdge.target)?.label}</p><p className="mt-2 text-xs">{selectedEdge.records.length} relationship record{selectedEdge.records.length === 1 ? "" : "s"}</p><div className="mt-3 max-h-40 space-y-2 overflow-auto text-[11px] text-text-muted">{selectedEdge.records.map((record) => <div key={record.id} className="rounded border border-hairline p-2"><span className="text-text-primary">{record.id}</span><br />{record.rationale || "No additional rationale."}</div>)}</div></div>}
  </div>;
}

export function AttackGraphView({ graph }: { graph: AttackGraphData }) { return <ReactFlowProvider><AttackGraphInner graph={graph} /></ReactFlowProvider>; }
