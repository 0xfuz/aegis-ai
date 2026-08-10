import { describe, expect, it } from "vitest";
import { aggregateRelationships, shouldShowEdgeLabel } from "@/components/attack-graph/attack-graph-view";
import { connectedComponents, layoutGraph, layoutSpacing } from "@/components/attack-graph/layout";
import type { AttackGraphEdge, AttackGraphNode } from "@/components/attack-graph/types";

const nodes: AttackGraphNode[] = [
  { id: "incident", type: "incident", label: "Incident", tier: "confirmed", timestamp: null, data: {} },
  { id: "event", type: "event", label: "Event", tier: "confirmed", timestamp: null, data: {} },
  { id: "ioc", type: "ioc", label: "IOC", tier: "probable", timestamp: null, data: {} },
];
const edges: AttackGraphEdge[] = [
  { id: "one", source: "incident", target: "event", relationship: "leads_to", tier: "confirmed", rationale: "first" },
  { id: "two", source: "incident", target: "event", relationship: "leads_to", tier: "confirmed", rationale: "second" },
  { id: "three", source: "event", target: "ioc", relationship: "supports", tier: "probable", rationale: "third" },
];

describe("attack graph layout", () => {
  it("is deterministic and assigns unique non-overlapping coordinates", () => {
    const first = layoutGraph(nodes, edges, "TB");
    const second = layoutGraph([...nodes].reverse(), [...edges].reverse(), "TB");
    expect(first.map(({ id, x, y }) => ({ id, x, y })).sort((a, b) => a.id.localeCompare(b.id))).toEqual(second.map(({ id, x, y }) => ({ id, x, y })).sort((a, b) => a.id.localeCompare(b.id)));
    expect(new Set(first.map((node) => `${node.x}:${node.y}`)).size).toBe(first.length);
  });

  it("places downstream nodes lower in top-to-bottom and rightward in left-to-right", () => {
    const topBottom = Object.fromEntries(layoutGraph(nodes, edges, "TB").map((node) => [node.id, node]));
    const leftRight = Object.fromEntries(layoutGraph(nodes, edges, "LR").map((node) => [node.id, node]));
    expect(topBottom.event!.y).toBeGreaterThan(topBottom.incident!.y);
    expect(leftRight.event!.x).toBeGreaterThan(leftRight.incident!.x);
  });

  it("aggregates repeated relationships while retaining every underlying record", () => {
    const aggregated = aggregateRelationships(edges);
    expect(aggregated).toHaveLength(2);
    expect(aggregated.find((edge) => edge.relationship === "leads_to")?.records.map((edge) => edge.id)).toEqual(["one", "two"]);
  });

  it("keeps disconnected components separate and places isolated facts in a deterministic region", () => {
    const withIsolated = [...nodes, { id: "isolated-a", type: "evidence" as const, label: "a", tier: "confirmed" as const, timestamp: null, data: {} }, { id: "isolated-b", type: "evidence" as const, label: "b", tier: "confirmed" as const, timestamp: null, data: {} }];
    expect(connectedComponents(withIsolated, edges).map((component) => component.length)).toEqual([3, 1, 1]);
    const positioned = layoutGraph(withIsolated, edges, "LR");
    const isolated = positioned.filter((node) => node.region === "unconnected");
    expect(isolated.map((node) => node.id)).toEqual(["isolated-a", "isolated-b"]);
    expect(isolated[0]!.y).toBeGreaterThan(positioned.find((node) => node.id === "event")!.y);
  });

  it("uses independently tuned TB and LR spacing", () => {
    expect(layoutSpacing("TB").nodesep).toBeLessThan(layoutSpacing("LR").nodesep);
    expect(layoutSpacing("TB").ranksep).toBeLessThan(layoutSpacing("LR").ranksep);
  });

  it("suppresses secondary edge labels at overview zoom but keeps active labels readable", () => {
    expect(shouldShowEdgeLabel(0.5, false, 0)).toBe(false);
    expect(shouldShowEdgeLabel(0.5, true, 1)).toBe(true);
    expect(shouldShowEdgeLabel(1, false, 0)).toBe(true);
    expect(shouldShowEdgeLabel(1, false, 1)).toBe(false);
  });
});
