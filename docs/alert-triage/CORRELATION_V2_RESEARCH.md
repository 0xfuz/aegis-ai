# Correlation-v2 Research

## Confirmed v1 false merge

`correlation-v1` starts at 20, adds 40 for a shared `hostname`, 5 for matching category, and 20 for the inclusive 180-second observed-time window. Its strong path merges when a non-IP strong signal exists and score is at least 50. Thus two independent same-host alerts score at least 80/85 and merge. Cluster selection then assigns the alert to the matching root; bridge logic can merge multiple roots. No rule-family, user, process, destination, attack-stage, or all-member compatibility check vetoes that result.

## Proposed v2 decision strategy

Use an explainable pairwise ledger followed by conservative cluster admission:

1. Reject different organizations unconditionally.
2. Apply hard incompatibility discriminators before positive scoring.
3. Require at least two independent positive signal families, one of which is identity/behavior rather than time or host alone.
4. Require a thresholded net score and no unresolved hard conflict.
5. Admit into a cluster only when compatible with its deterministic representative and a quorum of current members; otherwise create/retain a separate cluster.

V2 should prefer unmerged/uncertain incidents over unjustified fusion. This deliberately trades some recall for materially higher precision.

## Discriminators

Hard veto candidates: same host but explicitly different users plus incompatible process/destination; mutually exclusive attack stages within a short sequence; independently named rule families with no shared identity/behavior signal; conflicting connector/source identity where source semantics are known. Soft penalties: different rule family, process family, user, destination, or large behavioral divergence. A discriminator must be evidence-backed, not inferred from alert prose.

## Rotating IP continuity

Changing IP is neither identity nor a veto. Preserve correlation where same target host and account are corroborated by process/destination/domain or an ordered behavior transition inside the time window. Shared-IP-only traffic remains insufficient, preserving NAT separation.

## Triage note

The inability of externally severe alerts to reach HIGH/CRITICAL without trusted asset/IOC/sequence context is intentional conservative behavior and a data-enrichment limitation. It is a future triage-v2 research candidate, not a correlation-v2 change.

## Recommendation

Proceed to a separately approved correlation-v2 implementation only after the rule matrix and adversarial test plan below are accepted. Do not proceed directly to external Wazuh integration on v1.
