# Attack Graph Layout Strategy

The frontend uses **Dagre**, which is already a project dependency and provides deterministic layered layout for directed graphs. It is preferable to a force layout here because the same canonical graph must produce a stable, reviewable investigation view.

Known node dimensions are 220 × 72 px. Dagre receives those dimensions rather than zero-size points, with 40 px graph margins. Spacing is intentionally direction-specific: TB uses `nodesep: 34` and `ranksep: 82` to prevent excessive horizontal spread; LR uses `nodesep: 52` and `ranksep: 116` to give directed connections room to route. Nodes and edges are sorted by stable ID before layout, making the output stable even if an API response arrives in a different order.

`hierarchical` and `top-bottom` use Dagre `TB`; their source handle is bottom and target handle is top. `left-right` uses `LR`, with right source and left target handles. Edges use React Flow `smoothstep` routing, keeping directed connections orthogonal where practical. Labels use a small dark semi-opaque background and are non-interactive so they do not intercept graph navigation.

Before Dagre runs, the frontend splits the visible graph into real undirected connected components. Components are packed vertically; true isolates go in a compact, deterministic grid below them, exposed as the **Unconnected facts** region. No relationship is fabricated to influence layout.

The graph runs layout only for memoized visible nodes/edges or an explicit arrange request. Filtering and client-side focus change the visible set, then `fitView` runs after the new layout. Fit padding expands while an inspector is open, and selected-node focus applies a right-inspector offset. Relationship aggregation happens after filtering and before layout; provenance remains attached to all records in the edge inspector. At low zoom labels are limited to an active edge; at readable zoom, one label per convergent corridor is retained.
