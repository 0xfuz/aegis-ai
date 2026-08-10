# Aegis AI — UI/UX Specification & Design System
Version 0.1 · Companion to AEGIS_AI_ARCHITECTURE.md

---

## Part 1 — Design System

### 1.1 Design thesis

Every competitor (Defender, Falcon, Wiz, Sentinel) uses the same visual grammar: a navy/black shell, a single blue or green accent, card grids with drop shadows, and severity badges that all look borrowed from Bootstrap. Aegis AI's point of difference is that **the AI's confidence and reasoning are first-class visual citizens**, not a chatbot bolted onto a SIEM. The signature element carried through every screen is the **Confidence Ring** — a small circular arc (not a bar, not a percentage-in-a-badge) that appears next to every AI-generated verdict: a severity call, a root-cause claim, a remediation suggestion. It always answers "how sure is the AI, and why" in one glance, and clicking it always opens the reasoning trail behind that specific number. This is the one recurring motif — everything else stays quiet and disciplined around it.

### 1.2 Color palette

Named tokens, 6 hex values, dark-native (this is a SOC analyst's primary workspace, used for long shifts — dark is the default and only mode for v1):

| Token | Hex | Role |
|---|---|---|
| `--bg-void` | `#0A0D12` | App background — near-black with a cold blue undertone, not pure black |
| `--bg-surface` | `#12161D` | Panel/card background |
| `--bg-surface-raised` | `#1A2029` | Modals, popovers, hover states |
| `--border-hairline` | `#252C38` | 1px dividers, card borders |
| `--text-primary` | `#E8ECF2` | Primary text |
| `--text-muted` | `#8A93A3` | Secondary/caption text |
| `--accent-signal` | `#4DD8E8` | Primary interactive accent — a cold cyan ("telemetry cyan"), used for links, active nav, primary buttons, the Confidence Ring's "high confidence" arc. Deliberately not blue (too Microsoft) or green (too CrowdStrike/Falcon) |
| `--accent-cognition` | `#9B8CFF` | Reserved exclusively for AI-generated content — the violet border/glow on any card the AI wrote, so analysts always know "this text was reasoned, not logged" |

Severity is a **separate, strictly semantic** ramp — never reused for anything else in the UI, so severity always means severity:

| Severity | Hex | 
|---|---|
| Critical | `#E5484D` |
| High | `#F2994A` |
| Medium | `#F2C94C` |
| Low | `#4DD8E8` (reuses accent-signal — "low severity" and "informational" share visual weight intentionally) |
| Informational / resolved | `#6B7280` |

### 1.3 Typography

- **Display / headings**: Space Grotesk (geometric, slightly technical without being a coding font — used for page titles, severity numbers, the confidence percentage itself)
- **Body / UI**: Inter (neutral, dense-table-friendly, excellent at small sizes for a data-heavy product)
- **Data / mono**: IBM Plex Mono — for anything an analyst would copy-paste: hashes, IPs, file paths, JSON, timestamps, IoCs. This is not decorative; it signals "this value is literal and copyable" versus prose

Type scale: 32/24/18/15/13/11px. Body default 14px (13px in "compact" density — see 1.6). Line height 1.5 for prose, 1.3 for tabular data.

### 1.4 Layout grid

- Sidebar: 240px expanded / 64px collapsed (icon-only), fixed left
- Top bar: 56px, fixed, holds global command palette trigger (⌘K), org switcher, notifications, user menu
- Content: 24px page padding, 12-column responsive grid, 24px gutters
- Right contextual panel (used in Investigation Workspace and Attack Graph): 360px, slides in, never modal — it's a peer panel, not an overlay, so the analyst never loses their place

### 1.5 Signature interaction: Command Palette (⌘K)

Every action in the product is reachable without a mouse: jump to any investigation by ID, run a saved query, pivot to an asset, escalate a case, generate a report. This isn't a nice-to-have — SOC analysts triage under time pressure and power-user keyboard flows are a real differentiator against Sentinel/QRadar's mouse-heavy consoles.

### 1.6 Density modes

`Comfortable` (default, 14px body, 48px row height) and `Compact` (13px body, 32px row height, for analysts running triage on high-volume queues). A single toggle in the top bar switches app-wide — not per-page.

### 1.7 Core components (system-wide)

| Component | Notes |
|---|---|
| Confidence Ring | 32px circular arc, fill = severity-adjacent hue at low opacity, arc = `--accent-cognition`, center shows % ; click opens the AI reasoning trail (agent-by-agent breakdown from Part 2 of the architecture doc) |
| Severity Badge | Pill, left-aligned dot + label, sentence case ("Critical", not "CRITICAL") — no exclamation marks, no icons inside the pill itself |
| Evidence Chip | Small mono-font chip for IoCs/hashes/IPs, click-to-copy, hover reveals "add to investigation" |
| Case Status Track | Horizontal stepper: New → Triaging → Investigating → Contained → Resolved — always visible at the top of an Investigation, never buried in a dropdown |
| Empty state | Icon (outline style, muted), one-line headline naming the space, one-line body, single primary action — never "Nothing here yet" alone |
| Toast | Bottom-right, 4s auto-dismiss, past-tense confirmation ("Report generated", not "Report is being generated successfully!") |

---

## Part 2 — Navigation & Sidebar

### Top-level navigation (sidebar, icon + label)

1. **Dashboard** (home)
2. **Investigations** (badge = open case count)
3. **Attack Graph**
4. **Assets** (asset inventory)
5. **Threat Intelligence**
6. **Detections** (MITRE mapping + rule suggestions)
7. **Reports**
8. **Analytics**
— divider —
9. **Settings**
10. **User Management** (admin-role only — hidden entirely for non-admins, not just disabled)

Sidebar footer: org switcher (for MSSP multi-tenant users), collapse toggle, current user avatar + role badge.

**Global elements present on every page:**
- Top bar: ⌘K command palette trigger, live "new critical investigations" counter (pulses once, no infinite animation — respects `prefers-reduced-motion`), notification bell, user menu
- Breadcrumb under the top bar on any page nested more than one level deep (e.g. Investigations → INV-4821 → Evidence)

---

## Part 3 — Page Specifications

Each page below follows: Layout · Components · Empty state · Loading state · Error state · Mobile · User flow.

### 3.1 Dashboard

**Layout**: 3-zone vertical stack. (1) Top row: 4 metric cards (Open investigations, Critical this week, Mean time to triage, AI-resolved-as-false-positive rate). (2) Middle: 60/40 split — left is a live investigation queue table, right is a Risk Heatmap (assets × severity). (3) Bottom: recent Attack Graph anomalies as small preview cards.

**Components**: Metric card, investigation queue table (sortable by severity/confidence/time), heatmap grid, anomaly preview card, "Ask Aegis" inline query bar at the top of the queue (natural-language filter: "show me identity-related criticals from the last 24h").

**Empty state** (new tenant, no data yet): headline "No investigations yet", body "Connect a data source to start correlating signals.", primary action "Connect a data source" → deep-links to Settings → Connectors.

**Loading state**: metric cards show skeleton pulses (single subtle opacity fade, not shimmer-gradient — keeps it calm on a screen analysts stare at all day); queue table shows 6 skeleton rows.

**Error state**: if the correlation service is down, the queue table area shows an inline banner ("Investigation feed is delayed — showing cached data from [time]") rather than a full-page error, since partial data is still actionable for a SOC.

**Mobile**: metric cards stack 2×2 then 1-column below 480px; heatmap collapses to a ranked list ("Top 5 at-risk assets"); queue table becomes a card list (one investigation per card, severity + title + confidence ring only, tap to open).

**User flow**: analyst opens app → scans metric cards → sorts queue by severity → clicks a critical investigation → lands in Investigation Workspace.

### 3.2 Investigation Workspace

**Layout**: This is the flagship screen. Header holds the Case Status Track + severity/confidence + assignee. Below: 3-column — left is a vertical timeline (evidence chronologically), center is the active view (tabs: Overview / Timeline / Evidence / Notes / Related), right is the persistent 360px AI panel (Root cause, MITRE mapping, blast radius summary, recommended actions — each with its own Confidence Ring).

**Components**: Case Status Track, tabbed content area, Evidence Chip list, IoC table, note composer (with @mention for analyst handoff), "Recommended actions" card list where each action has an "Approve & execute" / "Dismiss" pair (never a bare "execute" — approval is always explicit per the architecture doc's human-in-the-loop rule).

**Empty state**: N/A (workspace only exists once an investigation exists) — but the "Related investigations" tab, when nothing correlates, shows "No related cases found" with a muted icon, no CTA needed.

**Loading state**: AI panel shows a distinct "Aegis is reasoning…" state per section (not a generic spinner) — Root Cause section shows "Analyzing root cause…", MITRE section shows "Mapping techniques…" — so the analyst knows which specific agent is still running rather than one opaque loader.

**Error state**: if an individual agent fails (e.g. blast-radius agent times out), only that card shows "Couldn't compute blast radius — retry", the rest of the panel still renders. One failed agent never blanks the whole workspace.

**Mobile**: right AI panel becomes a bottom sheet (swipe up), timeline and tabs stack full-width; note composer sticks to the bottom like a chat input.

**User flow**: analyst lands from Dashboard → reads AI Root Cause + confidence → expands MITRE mapping → reviews blast radius in mini attack-graph preview → approves a recommended containment action → status track advances to "Contained" → adds a closing note → marks Resolved.

### 3.3 Attack Graph

**Layout**: Full-canvas React Flow graph, minimal chrome. Floating top-left control cluster (zoom, layout mode: force/hierarchical/timeline). Floating top-right filter chips (asset type, identity, cloud, time window). Right panel (same 360px pattern) shows node detail when a node is selected — never a modal, so the graph stays visible for context.

**Components**: Graph canvas, node types color-coded by category (not severity — user/device/identity/cloud-resource each get a distinct neutral hue, severity is shown as a ring around the node instead so category and risk are never conflated), edge types (privilege escalation = dashed red, lateral movement = solid amber, normal auth = thin gray), path-highlight-on-hover (hovering any node dims unrelated paths).

**Empty state**: "No graph data for this time window" with a "Widen time range" quick action.

**Loading state**: graph area shows a centered "Building attack graph…" with a subtle skeleton of node-shaped placeholders — not a full-screen spinner, since the chrome (filters, controls) should stay usable while data streams in incrementally.

**Error state**: if graph computation fails for a subset of assets, those nodes render in gray with a small warning glyph and a tooltip ("relationship data unavailable") rather than disappearing — missing data is itself informative to a security engineer.

**Mobile**: graph exploration is genuinely hard on small screens — mobile shows a simplified "Blast radius list" view instead of the canvas (ranked list of affected assets with hop-distance), with a note "Full graph available on desktop."

**User flow**: analyst arrives from an Investigation's "view full graph" link with the relevant node pre-selected and pre-centered → explores adjacent nodes → selects a suspicious lateral-movement edge → right panel shows the edge's supporting evidence → pivots back to the source investigation.

### 3.4 Reports

**Layout**: Two-pane. Left: report list (past generated reports, filterable by type: Executive/Technical/Incident). Right: report builder — template picker, scope selector (single investigation, date range, or asset group), format toggle (PDF/Markdown/JSON), live preview pane.

**Components**: Template card picker (Executive Summary, Technical Deep-Dive, Compliance Snapshot), scope selector, live preview (renders the actual report styling, not a placeholder), "Generate" primary action, version history per report.

**Empty state**: "No reports generated yet" → "Generate your first report" primary action, pre-selecting the Executive Summary template as the friendliest starting point.

**Loading state**: preview pane shows a page-shaped skeleton while the Report Writer agent composes; a determinate progress label ("Drafting executive summary…", "Formatting technical appendix…") since report generation can take 10-30s and an indeterminate spinner would feel broken.

**Error state**: "Couldn't generate report — the investigation may still be missing required fields (e.g. no assigned severity)" with a direct link back to the incomplete investigation, rather than a generic failure message.

**Mobile**: builder becomes a single-column wizard (pick template → pick scope → pick format → generate); reports are best reviewed on desktop, so mobile's primary action is "generate and email me the PDF" rather than an inline preview.

**User flow**: CISO or analyst picks a template → selects scope → previews → generates → downloads or shares a link → report appears in the left-pane history with a version number.

### 3.5 Threat Intelligence

**Layout**: Search-first. Prominent IoC search bar at top (hash/IP/domain/URL). Below: two tabs — "Feed activity" (a scrolling list of new TI matches against your environment) and "Watchlist" (IoCs the org is explicitly tracking). Selecting a search result opens a detail panel: reputation score, first/last seen, related investigations, source feeds.

**Components**: IoC search bar (accepts paste of raw hash/IP, auto-detects type), reputation gauge (reuses the Confidence Ring visual language but relabeled "Reputation" so it's clear this is external-feed data, not an AI verdict — an important distinction: Confidence Rings for AI reasoning are violet-bordered, Reputation gauges are neutral-bordered, so analysts never confuse "the AI is 80% sure" with "80% of feeds flag this as malicious"), feed source list, "Add to watchlist" action.

**Empty state**: search with no results — "No intelligence found for this indicator" with "Add to watchlist anyway" so analysts can pre-stage tracking on something newly suspicious.

**Loading state**: search results show a skeleton reputation gauge + skeleton text lines while feeds are queried in parallel; feeds that respond render immediately rather than waiting for the slowest one.

**Error state**: if a specific TI feed is unreachable, its section shows "Feed unavailable" inline rather than blocking the whole lookup — other feeds' results still display.

**Mobile**: search bar sticks to top; results are single-column cards; watchlist becomes a simple list with swipe-to-remove.

**User flow**: analyst pastes a suspicious hash from an investigation's evidence tab → sees reputation + related investigations across the org → adds to watchlist → gets notified next time it appears.

### 3.6 Settings

**Layout**: Left sub-nav (Connectors, Organization, API keys, Notifications, Billing) + right content pane, standard settings pattern — this page intentionally looks the most "conventional enterprise SaaS" of the whole product, since settings is not where analysts want novelty.

**Components**: Connector cards (Sentinel, Splunk, Elastic, CrowdStrike, etc. — each shows connection status, last sync time, "Configure"/"Reconnect"), org profile form, API key table with scoped permissions and one-time-reveal on creation, notification preference toggles (per severity level, per channel: email/Slack/in-app).

**Empty state**: Connectors page with zero connectors — "Connect your first data source" with a grid of available connector logos to pick from.

**Loading state**: connector cards show a "Checking connection…" pill while a health-check runs; standard form skeletons elsewhere.

**Error state**: a broken connector shows a red "Connection failed" pill with the specific reason ("Token expired — reconnect required") rather than a generic error, since this is the single most common support request in this category of product.

**Mobile**: sub-nav collapses into a top dropdown selector; forms stack full-width; API key creation flow is discouraged on mobile (show a "Create API keys from desktop" note) since the one-time-reveal pattern is risky on small screens.

**User flow**: admin adds a connector → authenticates via OAuth or API token → sees "Connected" status → sets sync frequency → returns to Dashboard to watch data flow in.

### 3.7 User Management

**Layout**: Table-first — user list (name, email, role, last active, status) with a right-side "Invite user" panel (slide-in, not a separate page). Role definitions are visible via a small "What can each role do?" expandable reference table above the user list, since RBAC clarity is a common enterprise pain point.

**Components**: User table (sortable, filterable by role/status), invite panel (email + role picker), role badge, "Deactivate" / "Reactivate" row actions (deactivate, never hard-delete, preserves audit trail), bulk-select for role changes across multiple users.

**Empty state**: N/A — the inviting admin's own account always populates this list; if no other users exist yet, an inline banner above the table reads "You're the only member — invite your team to start assigning investigations."

**Loading state**: standard table skeleton, 5 rows.

**Error state**: invite failure ("This email is already part of another organization") shown inline in the invite panel next to the email field, not as a toast, since the fix is right there.

**Mobile**: table becomes a card list (name + role + status), invite panel becomes a full-screen sheet.

**User flow**: admin opens User Management → clicks Invite → enters email + selects role (e.g. Incident Responder) → invite sent → new row appears with status "Invited" → updates to "Active" once accepted.

---

## Part 4 — Cross-cutting states summary

| State type | System-wide rule |
|---|---|
| Loading | Never a generic spinner where the system knows what it's doing — name the specific operation. Skeleton over spinner wherever layout is already known. |
| Empty | Always: icon + one-line headline naming the space + one-line body + one primary action. Never just "No data." |
| Error | Always: what happened, in plain terms, then what to do next. Partial failures degrade gracefully — one broken widget/agent never takes down the page around it. |
| Mobile | SOC analysts triage on mobile but investigate on desktop. Mobile optimizes for "glance and approve/dismiss," not full investigative depth — the Attack Graph and API key creation are the two explicit desktop-only depths. |

---

## Next step

This spec plus the architecture document define everything needed to start Phase 1 implementation. Two high-fidelity wireframes follow (Dashboard and Investigation Workspace) to make the visual language concrete — the remaining pages follow the same tokens and component patterns described above.
