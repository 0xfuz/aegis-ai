# Phase 3 Provenance UX

Phase 3 makes the canonical factual chain inspectable without creating a second client-side data store.

## Factual navigation

```text
Indicator -> IndicatorOccurrence -> Event / RawRecord -> EvidenceItem
Entity    -> EntityObservation  -> Event / RawRecord -> EvidenceItem
Event     -> RawRecord          -> EvidenceItem
```

Evidence is selected in a split-view inspector. The inspector displays immutable SHA-256, detected type, parser identity, parsing status, safe controlled download, and the evidence's raw records. It never displays a storage key or server path.

Timeline detail displays the normalized event payload, the linked evidence, and raw-record ID. Indicator and entity inspectors display their scoped occurrences/observations, including evidence, event, raw-record, and observation-time references. Each evidence reference links back to the case evidence view.

## Trust boundary

All Phase 3 pages labelled “canonical” render FACT records only. They do not render AI conclusions as facts, do not perform enrichment or reputation lookup, and do not assign malicious verdicts. Legacy AI and manually authored content remain isolated behind the retained legacy view until a later trust-model phase.

## Error and empty behavior

- Authentication and authorization errors are shown as API errors; no client fallback exposes data.
- Duplicate upload feedback is returned by the existing `409` evidence API contract.
- Failed parsing is visibly marked while preserving the original evidence.
- Empty canonical collections say so plainly rather than substituting analytics or generated summaries.
