# AI Finding Workflow

`FACT → AI INFERENCE → ANALYST VERDICT` is a one-way trust boundary. Canonical facts remain evidence-derived. An AIIE observation, hypothesis, or recommendation can become a Finding only after explicit analyst approval and conversion.

Conversion copies the approved item's analysis reference and supporting fact links into durable Finding records. The resulting Finding is analyst-owned and may be edited or moved through `OPEN`, `CONFIRMED`, `DISMISSED`, and `RESOLVED`; it never depends on mutable notebook UI state. Manual and AI-derived creation, edits, and status changes are audited.
