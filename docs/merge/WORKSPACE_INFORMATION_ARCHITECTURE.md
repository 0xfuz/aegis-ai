# Phase 3 Workspace Information Architecture

The Aegis-AI authenticated shell remains the single product workspace. CIOS is not presented as a product or brand.

## Global navigation

- Operations: Dashboard, Alerts, Cases.
- Investigation: the selected case exposes Overview, Evidence, Timeline, Indicators, Entities, Attack Graph, Findings, and MITRE ATT&CK.
- Aegis Intelligence: existing analysis, hypotheses, reasoning, and recommendations remain in the retained legacy case view until their trust-model migration.
- Workspace: Notes, Reports, and Audit Trail remain available through the retained legacy case view or current Reports surface until dedicated cutover phases.

`/investigations` remains the compatible case-list/alert entry point. The existing `/investigations/{id}` route is retained unchanged and is explicitly linked as **Legacy view** from every new factual workspace route.

## Case-scoped routes

| Route | Phase 3 responsibility | Data boundary |
| --- | --- | --- |
| `/investigations/{id}/overview` | canonical factual counts | canonical FACT APIs only |
| `/evidence` | upload, safe download, inspector, raw browsing | EvidenceItem / RawRecord |
| `/timeline` | normalized factual event timeline | Event only |
| `/indicators` | deterministic occurrences and provenance | Indicator / IndicatorOccurrence |
| `/entities` | observations and relationship counts | Entity / EntityObservation |
| `/relationships` | explicit graph cutover placeholder | no graph unification |
| `/findings`, `/mitre`, `/notes`, `/reports`, `/audit` | compatibility placeholders | existing legacy surfaces retained |

The timeline deliberately excludes manually-created legacy timeline entries. They continue to be visible only in the legacy investigation route, preventing facts and legacy/AI context from being silently blended.
