# Attack Graph UX

The Attack Graph remains a read-only projection of canonical investigation facts. It does not create, alter, or hide canonical relationships; filters and focus only control the client-side presentation.

The default is now **Left to Right**. Manual readability evaluation found it keeps the usual directed investigation chain compact in the wide workspace while leaving enough separation for relationship routing. **Hierarchical** and **Top to Bottom** remain available for vertical review. Changing a filter, focus state, or layout mode recomputes the layout and fits the canvas.

Nodes use the existing dark semantic palette: incident red, events/evidence cyan, accounts and assets neutral-cyan, IP/domain orange, and MITRE purple. Selecting a node highlights its direct neighbours and relationships while dimming unrelated context. Selecting an edge highlights its two endpoints.

Repeated identical relationships between the same endpoints are rendered as one edge with a count, for example `related to × 7`. The edge inspector retains every underlying presentation record and rationale. The node inspector exposes its canonical value when supplied by the projection, timestamps, relationships, data/provenance fields, and actions for timeline, evidence, focus, and neighbourhood expansion.

For large graphs (150+ nodes), the UI shows a status warning and keeps all nodes available. Use existing type/confidence/MITRE/relationship filters and focus controls to work with a smaller subgraph; no data is silently discarded.

Disconnected components are laid out independently. Facts with no visible relationship are placed in a clearly marked **Unconnected facts** region rather than appearing as an invented continuation of the attack path. This is presentation only: no relationship is created or inferred.

At overview zoom, secondary edge labels are suppressed; selecting the relationship restores its label. The inspector-aware fit and selected-node focus shift the graph left when the right inspector is open, so the selected fact is not hidden behind it.

Controls and inspector actions are native focusable buttons/links with accessible labels and visible focus rings.
