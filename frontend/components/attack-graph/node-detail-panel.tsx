import Link from "next/link";
import { ExternalLink } from "lucide-react";
import { NODE_TYPE_LABELS, TIER_LABELS, type AttackGraphData, type AttackGraphNode } from "./types";

function mitreUrl(techniqueId: string): string {
  // T1078 -> .../techniques/T1078/ ; T1078.001 (sub-technique) -> .../techniques/T1078/001/
  const [base, sub] = techniqueId.split(".");
  return sub ? `https://attack.mitre.org/techniques/${base}/${sub}/` : `https://attack.mitre.org/techniques/${base}/`;
}

/** Where "open this node elsewhere in the product" goes, per node type —
 * only for types that actually have a real destination page. Types with
 * no dedicated page (event, evidence, hypothesis, finding, account,
 * uncertainty) simply don't get an action, rather than linking somewhere
 * fake. */
function NavigationAction({ node, investigationId }: { node: AttackGraphNode; investigationId: string }) {
  switch (node.type) {
    case "incident":
      return (
        <Link
          href={`/investigations/${investigationId}`}
          className="mt-3 flex items-center justify-center gap-1.5 rounded border border-hairline py-1.5 text-xs text-signal hover:border-signal"
        >
          Open investigation
        </Link>
      );
    case "asset": {
      const assetId = node.data.asset_id as string | undefined;
      if (!assetId) return null; // not yet in the asset registry — nothing real to link to
      return (
        <Link
          href={`/assets?assetId=${assetId}`}
          className="mt-3 flex items-center justify-center gap-1.5 rounded border border-hairline py-1.5 text-xs text-signal hover:border-signal"
        >
          Open asset
        </Link>
      );
    }
    case "ioc":
    case "ip_domain":
      return (
        <Link
          href="/threat-intel"
          className="mt-3 flex items-center justify-center gap-1.5 rounded border border-hairline py-1.5 text-xs text-signal hover:border-signal"
        >
          Open threat intelligence
        </Link>
      );
    case "mitre_technique":
      return (
        <a
          href={mitreUrl(node.label)}
          target="_blank"
          rel="noopener noreferrer"
          className="mt-3 flex items-center justify-center gap-1.5 rounded border border-hairline py-1.5 text-xs text-signal hover:border-signal"
        >
          Open MITRE ATT&amp;CK reference <ExternalLink size={12} />
        </a>
      );
    default:
      return null;
  }
}

export function NodeDetailPanel({
  node,
  graph,
  onClose,
  onSelectNode,
  onFocus,
  onExpand,
}: {
  node: AttackGraphNode;
  graph: AttackGraphData;
  onClose: () => void;
  onSelectNode: (nodeId: string) => void;
  onFocus: () => void;
  onExpand: () => void;
}) {
  const connected = graph.edges
    .filter((e) => e.source === node.id || e.target === node.id)
    .map((e) => {
      const otherId = e.source === node.id ? e.target : e.source;
      const other = graph.nodes.find((n) => n.id === otherId);
      const direction = e.source === node.id ? "→" : "←";
      return { edge: e, other, direction };
    })
    .filter((c) => c.other);

  return (
    <div className="absolute right-4 top-4 z-10 w-80 max-h-[calc(100%-2rem)] overflow-y-auto rounded-card border border-hairline bg-surface p-4 shadow-lg">
      <div className="flex items-start justify-between">
        <span className="text-[10px] uppercase tracking-wide text-text-muted">{NODE_TYPE_LABELS[node.type]}</span>
        <button onClick={onClose} className="text-text-muted hover:text-text-primary">
          ✕
        </button>
      </div>
      <div className="mt-1 text-sm text-text-primary">{node.label}</div>
      <div className="mt-1 text-[11px] text-text-muted">{TIER_LABELS[node.tier]}</div>
      {node.timestamp && (
        <div className="mt-1 text-[11px] text-text-muted">{new Date(node.timestamp).toLocaleString()}</div>
      )}

      <NavigationAction node={node} investigationId={graph.investigation_id} />

      <div className="mt-3 grid grid-cols-2 gap-1.5">
        <button type="button" onClick={onFocus} className="rounded border border-hairline px-2 py-1.5 text-xs text-signal hover:border-signal">Focus node</button>
        <button type="button" onClick={onExpand} className="rounded border border-hairline px-2 py-1.5 text-xs text-signal hover:border-signal">Expand neighbours</button>
        <Link href={`/investigations/${graph.investigation_id}`} className="rounded border border-hairline px-2 py-1.5 text-center text-xs text-text-muted hover:border-signal">View timeline</Link>
        <Link href={`/investigations/${graph.investigation_id}/evidence`} className="rounded border border-hairline px-2 py-1.5 text-center text-xs text-text-muted hover:border-signal">View evidence</Link>
      </div>
      <div className="mt-3 grid grid-cols-2 gap-2 text-xs">
        <div><span className="text-text-muted">Relationships</span><br />{connected.length}</div>
        <div><span className="text-text-muted">Canonical value</span><br />{String(node.data.canonical_value ?? node.data.value ?? node.label)}</div>
      </div>

      {Object.keys(node.data).length > 0 && (
        <dl className="mt-3 space-y-1.5 text-xs">
          {Object.entries(node.data)
            .filter(([, v]) => v !== null && v !== undefined && v !== "")
            .map(([key, value]) => (
              <div key={key} className="flex justify-between gap-3 border-b border-hairline pb-1.5 last:border-0">
                <dt className="shrink-0 capitalize text-text-muted">{key.replace(/_/g, " ")}</dt>
                <dd className="break-all text-right text-text-primary">
                  {typeof value === "object" ? JSON.stringify(value) : String(value)}
                </dd>
              </div>
            ))}
        </dl>
      )}

      {connected.length > 0 && (
        <div className="mt-4">
          <div className="mb-1.5 text-xs text-text-muted">Connected ({connected.length})</div>
          <div className="space-y-1">
            {connected.map(({ edge, other, direction }) => (
              <button
                key={edge.id}
                onClick={() => other && onSelectNode(other.id)}
                className="block w-full rounded border border-hairline px-2 py-1.5 text-left text-[11px] hover:bg-surface-raised"
                title={edge.rationale}
              >
                <span className="text-text-muted">
                  {direction} {edge.relationship.replace(/_/g, " ")} {direction}
                </span>{" "}
                <span className="text-text-primary">{other?.label}</span>
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
