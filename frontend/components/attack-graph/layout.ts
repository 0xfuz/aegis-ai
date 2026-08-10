import dagre from "dagre";
import type { AttackGraphData, AttackGraphEdge, AttackGraphNode, GraphLayoutMode } from "./types";

export interface PositionedNode extends AttackGraphNode {
  x: number;
  y: number;
  width: number;
  height: number;
  region?: "connected" | "unconnected";
}

export function layoutSpacing(direction: "TB" | "LR") {
  // TB needs a smaller same-rank gap to stay within a practical viewport;
  // LR benefits from a longer rank gap so directed edges remain legible.
  return direction === "TB"
    ? { nodesep: 34, ranksep: 82, componentGap: 120 }
    : { nodesep: 52, ranksep: 116, componentGap: 132 };
}

export function connectedComponents(nodes: AttackGraphNode[], edges: AttackGraphEdge[]): AttackGraphNode[][] {
  const byId = new Map(nodes.map((node) => [node.id, node]));
  const adjacent = new Map(nodes.map((node) => [node.id, new Set<string>()]));
  for (const edge of edges) {
    if (!byId.has(edge.source) || !byId.has(edge.target)) continue;
    adjacent.get(edge.source)?.add(edge.target);
    adjacent.get(edge.target)?.add(edge.source);
  }
  const visited = new Set<string>();
  const components: AttackGraphNode[][] = [];
  for (const start of [...nodes].sort((a, b) => a.id.localeCompare(b.id))) {
    if (visited.has(start.id)) continue;
    const component: AttackGraphNode[] = [];
    const queue = [start.id];
    visited.add(start.id);
    while (queue.length) {
      const id = queue.shift();
      const node = id ? byId.get(id) : undefined;
      if (node) component.push(node);
      for (const next of adjacent.get(id ?? "") ?? []) if (!visited.has(next)) { visited.add(next); queue.push(next); }
    }
    components.push(component.sort((a, b) => a.id.localeCompare(b.id)));
  }
  return components.sort((a, b) => {
    const aRoot = a.some((node) => node.type === "incident") ? 1 : 0;
    const bRoot = b.some((node) => node.type === "incident") ? 1 : 0;
    return bRoot - aRoot || b.length - a.length || a[0]!.id.localeCompare(b[0]!.id);
  });
}

export const NODE_WIDTH = 220;
export const NODE_HEIGHT = 72;

export function layoutDirection(mode: GraphLayoutMode): "TB" | "LR" {
  return mode === "left-right" ? "LR" : "TB";
}

/**
 * Real automatic layout via Dagre — a directed-graph layered layout
 * algorithm, not a hand-rolled column grid. Feeding it the actual edges
 * means node rank (depth) follows the real relationship structure: an
 * event genuinely downstream of the incident via several hops ends up
 * visually downstream, rather than everything of the same TYPE being
 * forced into one column regardless of how connected it actually is.
 *
 * direction: "TB" (top-to-bottom) matches the attack-progression
 * diagram in the spec; "LR" is offered for wide/shallow graphs.
 */
export function layoutGraph(
  nodes: AttackGraphNode[],
  edges: AttackGraphEdge[],
  direction: "TB" | "LR" = "TB",
): PositionedNode[] {
  const spacing = layoutSpacing(direction);
  const layoutComponent = (component: AttackGraphNode[]): PositionedNode[] => {
  const g = new dagre.graphlib.Graph({ multigraph: true });
  g.setGraph({
    rankdir: direction,
    nodesep: spacing.nodesep,
    ranksep: spacing.ranksep,
    marginx: 40,
    marginy: 40,
  });
  g.setDefaultEdgeLabel(() => ({}));

  for (const node of component) {
    g.setNode(node.id, { width: NODE_WIDTH, height: NODE_HEIGHT });
  }
  for (const edge of [...edges].sort((a, b) => a.id.localeCompare(b.id))) {
    // Only add the edge to the layout graph if both ends are actually
    // present (a filtered view may have removed one side) — dagre
    // throws on dangling references otherwise.
    if (g.hasNode(edge.source) && g.hasNode(edge.target)) {
      g.setEdge(edge.source, edge.target, {}, edge.id);
    }
  }

  dagre.layout(g);

  return component.map((node) => {
    const pos = g.node(node.id);
    return {
      ...node,
      x: pos ? pos.x - NODE_WIDTH / 2 : 0,
      y: pos ? pos.y - NODE_HEIGHT / 2 : 0,
      width: NODE_WIDTH,
      height: NODE_HEIGHT,
    };
  }); };

  const components = connectedComponents(nodes, edges);
  const connected = components.filter((component) => component.length > 1);
  const isolated = components.filter((component) => component.length === 1).flat();
  const positioned: PositionedNode[] = [];
  let nextY = 40;
  for (const component of connected) {
    const laidOut = layoutComponent(component);
    const minX = Math.min(...laidOut.map((node) => node.x));
    const minY = Math.min(...laidOut.map((node) => node.y));
    const maxY = Math.max(...laidOut.map((node) => node.y + node.height));
    positioned.push(...laidOut.map((node) => ({ ...node, x: node.x - minX + 40, y: node.y - minY + nextY, region: "connected" as const })));
    nextY += maxY - minY + spacing.componentGap;
  }
  // Isolated facts must remain visible, but do not imply a fabricated path.
  // A fixed grid gives them an explicit, compact "Unconnected facts" region.
  const columns = direction === "LR" ? 3 : 4;
  for (const [index, node] of isolated.entries()) {
    positioned.push({ ...node, x: 40 + (index % columns) * (NODE_WIDTH + spacing.nodesep), y: nextY + Math.floor(index / columns) * (NODE_HEIGHT + spacing.nodesep), width: NODE_WIDTH, height: NODE_HEIGHT, region: "unconnected" });
  }
  return positioned;
}

/**
 * The primary attack path — derived purely from real LEADS_TO edges
 * (the only relationship type that represents progression/sequence),
 * plus, for each event actually on that chain, whatever it's directly
 * confirmed to have originated from, targeted, or been mapped to
 * (ORIGINATED_FROM / TARGETED / SUPPORTS). This is a graph traversal
 * over data that already exists — there is no hardcoded phase list
 * anywhere in this function.
 */
export function derivePrimaryPath(graph: AttackGraphData): Set<string> {
  const path = new Set<string>();
  const incident = graph.nodes.find((n) => n.type === "incident");
  if (!incident) return path;
  path.add(incident.id);

  // Walk every LEADS_TO edge reachable from the incident — covers both
  // the event chronology chain and the attack-phase chain, however deep.
  const leadsTo = graph.edges.filter((e) => e.relationship === "leads_to");
  const queue = [incident.id];
  while (queue.length > 0) {
    const current = queue.shift();
    if (!current) continue;
    for (const edge of leadsTo) {
      if (edge.source === current && !path.has(edge.target)) {
        path.add(edge.target);
        queue.push(edge.target);
      }
    }
  }

  // The one explicit exception: if there's no real chain, the
  // "insufficient evidence" placeholder IS the honest attack path for
  // this investigation — surfacing it in the path view (rather than
  // hiding it) is the correct behavior, not a fabrication.
  for (const edge of graph.edges) {
    if (edge.source === incident.id && edge.relationship === "related_to") {
      const target = graph.nodes.find((n) => n.id === edge.target);
      if (target?.type === "uncertainty") path.add(target.id);
    }
  }

  // For every event on the backbone, pull in whatever it's directly and
  // confirmedly connected to — this is what makes the path view show
  // "svc-payments-01" or "185.220.101.4" alongside the event that
  // actually referenced them, instead of just a chain of event bubbles.
  const contextEdgeTypes = new Set(["originated_from", "targeted", "supports"]);
  const onPathEvents = graph.nodes.filter((n) => path.has(n.id) && n.type === "event");
  for (const event of onPathEvents) {
    for (const edge of graph.edges) {
      if (edge.source === event.id && contextEdgeTypes.has(edge.relationship)) {
        path.add(edge.target);
      }
    }
  }

  return path;
}
