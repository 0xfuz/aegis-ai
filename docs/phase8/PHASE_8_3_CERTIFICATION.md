# Phase 8.3 Certification

## Scope

Phase 8.3 adds the Investigation Intelligence presentation layer on top of
the certified Phase 8.2 reconstruction read model. It is certified from the
Phase 8.2 tag baseline `daa128bf6bb5daa24b9549e204647a3b2127b20a` on branch
`phase8-alert-intelligence`; the migration graph remains at the single head
`0021`.

The review integration implementation commit is
`db696a5435fdad766221688463c88495ecedfd76`; this certification document is
committed separately so its commit remains the certified tag target.

The Intelligence workspace remains the only Investigation-scoped destination
for this explanation. It reuses factual Evidence, Timeline, Entities,
Indicators, Relationships, Findings, and MITRE routes rather than creating a
second evidence store, timeline, graph, or authority surface.

## UI and trust boundary

- The typed reconstruction client calls only the certified, read-only
  reconstruction GET endpoint. Overview, activity-window, gap, promotion, and
  citation components render server ordering and bounded projections without
  client-side reconstruction, correlation, triage, or confidence calculation.
- Claim and citation explanation preserves the difference between claim type,
  origin, and review status. FACT is deterministic-engine-origin only;
  confirming an AI-origin claim does not turn it into FACT, a Finding, or a
  confirmed MITRE mapping.
- The review integration invokes only the pre-existing authorized mutation
  `POST /api/v1/investigations/intelligence/items/{item_id}/review`. The
  browser supplies only the selected canonical status and bounded rationale;
  item, organization, Investigation, actor, and permission scope remain
  server authoritative.
- UI actions expose exactly PENDING -> CONFIRMED/REJECTED/UNRESOLVED and
  UNRESOLVED -> CONFIRMED/REJECTED. CONFIRMED, REJECTED, and SUPERSEDED are
  terminal in the UI. Supersession and predecessor linkage are intentionally
  absent because the authorized read contract does not expose them.
- An active principal with `investigation:write` may see review controls.
  Read-only or inactive principals see claims and citations without active
  controls. The backend remains the authority for active-user, organization,
  and Investigation checks; 403 and 404 feedback is bounded and does not show
  server details.
- Rejecting is explicitly confirmed with a required, 500-character bounded
  rationale. All review choices use a confirmation surface, are disabled while
  pending, prevent duplicate submissions after acknowledgement, reconcile from
  the authoritative claim read, and preserve reconstruction content on error.

## Safety and accessibility

- Persisted text is React text only: no raw payload, normalized event data,
  full snapshot, prompt, provider output, secret, audit payload, browser
  storage, response logging, or HTML injection is added.
- Claim, citation, activity, and gap output is server-bounded. Hostile
  HTML-like claim text remains inert.
- Review controls have labels containing claim type and intended status,
  keyboard-operable buttons, a semantic confirmation dialog, semantic live
  success/error feedback, and predictable focus return after cancellation or
  successful confirmation. Status remains textually visible and is never
  color-only.
- Review status changes no semantic content and has no automatic Finding,
  MITRE, promotion, RecommendedAction, containment, provider, or rerun effect.
  Findings and MITRE links remain read-only navigation to their existing
  analyst-controlled workspaces.

## Certification evidence

| Area | Evidence | Result |
| --- | --- | --- |
| Reconstruction explanation | Frontend reconstruction, overview/activity/gap, v2 promotion/triage, v1/unknown degradation, omission, deterministic ordering, and factual-link tests. | PASS |
| Citations and claims | Many-to-many SUPPORTS/CONTRADICTS/CONTEXT citation tests; claim type/origin/status semantic and hostile-text tests. | PASS |
| Review controls | Canonical transition matrix, terminal/forbidden absence, permission and inactive-user gating, confirmation, rejection rationale, duplicate prevention, safe 403/404/error/retry, focus, and authoritative refresh tests. | PASS |
| Backend review contract | PostgreSQL review-transition, append-only event/audit, active actor and organization isolation, API canonical CONFIRMED compatibility, explicit Finding handoff, and reconstruction read-only tests. | PASS |
| Static boundary audit | No new provider/action/run-execution control, reconstruction mutation route, legacy provider/action panel, raw/snapshot/prompt/secret rendering, or browser persistence added. | PASS |

Frontend certification completed with `50 passed` tests. Typecheck passed,
lint reported no warnings or errors, and the Next.js production build passed.
Focused PostgreSQL backend regression completed with `85 passed, 60 warnings`
on a fresh disposable database upgraded to `0021 (head)`.

## Deferred scope

Provider/Ollama execution, prompt construction, worker/lease/dispatch,
automatic AI claim generation, supersession linkage UI, live Wazuh end-to-end
validation, cross-case retrieval, automatic containment/remediation, and
SaaS/billing remain deferred. Phase 8 is not complete; this document certifies
only Phase 8.3.
