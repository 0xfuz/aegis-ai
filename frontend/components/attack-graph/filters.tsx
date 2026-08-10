import { NODE_TYPE_LABELS, TIER_LABELS, type AttackGraphData, type ConfidenceTier, type EdgeType, type NodeType } from "./types";

export interface GraphFilters {
  types: Set<NodeType>;
  tiers: Set<ConfidenceTier>;
  mitreTechnique: string | null;
  relationships: Set<EdgeType>;
}

export function defaultFilters(graph: AttackGraphData): GraphFilters {
  return {
    types: new Set(graph.nodes.map((n) => n.type)),
    tiers: new Set(["confirmed", "probable", "possible", "unknown"]),
    mitreTechnique: null,
    relationships: new Set(graph.edges.map((edge) => edge.relationship)),
  };
}

export function FilterPanel({
  graph,
  filters,
  onChange,
}: {
  graph: AttackGraphData;
  filters: GraphFilters;
  onChange: (filters: GraphFilters) => void;
}) {
  const presentTypes = Array.from(new Set(graph.nodes.map((n) => n.type)));
  const presentTechniques = Array.from(
    new Set(graph.nodes.filter((n) => n.type === "mitre_technique").map((n) => n.label)),
  );
  const presentRelationships = Array.from(new Set(graph.edges.map((edge) => edge.relationship))).sort();

  function toggleType(t: NodeType) {
    const next = new Set(filters.types);
    if (next.has(t)) next.delete(t);
    else next.add(t);
    onChange({ ...filters, types: next });
  }

  function toggleTier(t: ConfidenceTier) {
    const next = new Set(filters.tiers);
    if (next.has(t)) next.delete(t);
    else next.add(t);
    onChange({ ...filters, tiers: next });
  }
  function toggleRelationship(relationship: EdgeType) {
    const next = new Set(filters.relationships);
    if (next.has(relationship)) next.delete(relationship);
    else next.add(relationship);
    onChange({ ...filters, relationships: next });
  }

  return (
    <div className="absolute left-4 top-4 z-10 w-64 rounded-card border border-hairline bg-surface p-3">
      <div className="mb-2 text-xs text-text-muted">Node types</div>
      <div className="mb-3 flex flex-wrap gap-1">
        {presentTypes.map((t) => (
          <button
            key={t}
            onClick={() => toggleType(t)}
            className={`rounded-full px-2 py-0.5 text-[10px] transition-colors ${
              filters.types.has(t) ? "bg-signal/20 text-signal" : "bg-surface-raised text-text-muted"
            }`}
          >
            {NODE_TYPE_LABELS[t]}
          </button>
        ))}
      </div>

      {presentRelationships.length > 0 && <><div className="mb-2 text-xs text-text-muted">Relationships</div><div className="mb-3 flex flex-wrap gap-1">{presentRelationships.map((relationship) => <button key={relationship} type="button" onClick={() => toggleRelationship(relationship)} className={`rounded-full px-2 py-0.5 text-[10px] transition-colors ${filters.relationships.has(relationship) ? "bg-signal/20 text-signal" : "bg-surface-raised text-text-muted"}`}>{relationship.replace(/_/g, " ")}</button>)}</div></>}

      <div className="mb-2 text-xs text-text-muted">Confidence</div>
      <div className="mb-3 flex flex-wrap gap-1">
        {(["confirmed", "probable", "possible", "unknown"] as ConfidenceTier[]).map((tier) => (
          <button
            key={tier}
            onClick={() => toggleTier(tier)}
            className={`rounded-full px-2 py-0.5 text-[10px] transition-colors ${
              filters.tiers.has(tier) ? "bg-signal/20 text-signal" : "bg-surface-raised text-text-muted"
            }`}
            title={TIER_LABELS[tier]}
          >
            {tier}
          </button>
        ))}
      </div>

      {presentTechniques.length > 0 && (
        <>
          <div className="mb-1.5 text-xs text-text-muted">Focus MITRE technique</div>
          <select
            value={filters.mitreTechnique ?? ""}
            onChange={(e) => onChange({ ...filters, mitreTechnique: e.target.value || null })}
            className="w-full rounded border border-hairline bg-surface-raised px-2 py-1 text-xs text-text-primary"
          >
            <option value="">All techniques</option>
            {presentTechniques.map((t) => (
              <option key={t} value={t}>
                {t}
              </option>
            ))}
          </select>
        </>
      )}
    </div>
  );
}
