# Frontend Dependency Inventory

## Shared application dependencies

| Component | Current role | State/hooks/API dependencies | Classification |
|---|---|---|---|
| `app/layout.tsx` | Fonts, globals, AuthProvider | AuthProvider | KEEP |
| `app/(dashboard)/layout.tsx` | Client-side route protection and shell | `useAuth`, router, Sidebar, Topbar | KEEP |
| `lib/auth-context.tsx` | Token/user state and login/logout | localStorage; `/auth/login`, `/auth/me`, `/auth/logout`; API client refresh | KEEP; security hardening deferred |
| `lib/api-client.ts` | Bearer fetch, refresh/retry, download | `/auth/refresh`, localStorage | KEEP |
| `components/layout/sidebar.tsx` | Primary navigation, open-case count | pathname, `useAuth`, `/investigations/dashboard-summary` | REFACTOR for approved unified navigation |
| `components/layout/topbar.tsx` | Search/bell/profile controls | `useAuth`, local UI state | KEEP; no backend search dependency currently |
| UI primitives | Card/Button/Input/badges/copy/confidence | utility classes; CopyButton local state | KEEP |

## Page inventory

| Page | Endpoints used | Shared components / hooks / state | Graph/timeline dependency | Classification |
|---|---|---|---|---|
| `/` | none; redirect | Next redirect | none | KEEP |
| `/login` | via AuthProvider: login | Button, Input, `useState`, `useAuth` | none | KEEP |
| `/dashboard` | dashboard summary; investigation list limit 5 | Cards, badges, confidence ring; `useEffect/useState` | queue uses Investigation summaries | REFACTOR; metrics include legacy AI FP field |
| `/investigations` | investigation list | Card/badges/ring; `useEffect/useState` | summary only | REFACTOR; becomes Cases list/operations view |
| `/investigations/[id]` | detail; status; action approve/dismiss; note; analyze; report download | EvidenceExplorer, IOC overlay, AI panel, Card/Button/badge; params/router; callbacks/effects/state | renders inline legacy evidence record timeline and links graph | REFACTOR — highest frontend coupling |
| `/investigations/[id]/attack-graph` | attack graph | AttackGraphView; params/router; effect/state | consumes graph DTO | REFACTOR; reuse renderer with factual/inference layers |
| `/attack-graph` | none | router/button | navigation-only | REPLACE as case-context graph entry or keep redirect |
| `/threat-intel` | IOC list/watchlist; IOC overlay lookup/watch | Input/Button/Card/VerdictBadge; effects/state | indicator relations only | REFACTOR; retains org intel but link occurrence evidence |
| `/assets` | assets list/detail | Card/badge; search params, effects/state | asset detail links related cases | KEEP / REFACTOR |
| `/settings` | connectors list/create/delete | Card/Button/Input/CopyButton; callbacks/effects/state | none | KEEP |
| `/user-management` | users list/create | Card/Button/Input; callbacks/effects/state | none | KEEP |
| `/analytics` | none | ComingSoon | none | DEFER |
| `/detections` | none | ComingSoon | none | DEFER |
| `/reports` | none | static construction UI | none | REPLACE with workspace report history/list |

## Investigation and graph component inventory

| Component | Dependencies and state | Classification |
|---|---|---|
| `EvidenceExplorer` | Receives `EvidenceRecord[]`; local category/search/filter state via `useMemo/useState` | REPLACE data input with Events + Evidence/RawRecord source links; retain filter UX where useful |
| `IOCDetailOverlay` | IOC lookup and watch mutation; local loading/error/detail state | REFACTOR for occurrence provenance and verdict/audit controls |
| `AIReasoningPanel` | Pure display of confidence, root cause, chain, hypotheses/actions | REPLACE props with immutable Analysis/Proposal/Review state; preserve visual components |
| `AttackGraphView` | React Flow, Dagre, filter state, selected node, primary path derivation | KEEP / REFACTOR only input semantics/styles |
| `GraphNode`, filters, layout, node details, types/visuals | React Flow node customisation, graph filtering, layout and styling | KEEP; add fact/inference status/provenance fields without duplicating renderer |

## Frontend migration constraints

- Current page state is component-local; there is no query cache/store to
  migrate. Do not introduce one merely for consistency.
- The central workspace expects one large `InvestigationDetail` response. Build
  a compatibility projection before splitting it into case subpages.
- Preserve direct deep links to `/investigations/[id]` during transition.
- The graph page should be migrated only after the backend serves evidence-derived
  relationships; React Flow/Dagre need not be replaced.
- Add the approved Operations/Investigation/Aegis Intelligence/Workspace
  navigation only after canonical endpoints have stable read models.
