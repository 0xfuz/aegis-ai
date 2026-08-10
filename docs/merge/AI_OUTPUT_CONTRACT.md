# AI Output Contract

## Boundary

The Aegis analysis engine receives a bounded factual snapshot and emits
structured **INFERENCES** only. It has no repository/API authority to modify:

- original evidence bytes or EvidenceItem metadata/hashes;
- EvidenceParseRuns or RawRecords;
- normalized Events;
- Indicator, Entity, or EntityRelationship factual identity/provenance;
- analyst Findings, ATT&CK confirmations, ReportSnapshots, or AuditEvents.

## AIAnalysis envelope

Every completed run must persist an immutable `AIAnalysis` envelope:

```json
{
  "id": "uuid",
  "org_id": "uuid",
  "investigation_id": "uuid",
  "status": "COMPLETED",
  "provider": "gemini|anthropic|ollama|other",
  "model": "provider model identifier",
  "model_version": "optional deployment/version identifier",
  "generated_at": "UTC timestamp",
  "input_snapshot_id": "uuid or immutable snapshot hash",
  "prompt_template_version": "versioned identifier",
  "confidence": 0,
  "supporting_facts": [
    {"target_type":"Event","target_id":"uuid","role":"supports","rationale":"optional short locator"}
  ]
}
```

`status` is operational (`QUEUED`, `RUNNING`, `COMPLETED`, `FAILED`), not an
analyst truth claim. Review status for the analysis/proposals is separately
`UNREVIEWED`, `CONFIRMED`, or `REJECTED`.

## Structured output requirements

| Output | Required generated content | Required factual links |
|---|---|---|
| Root-cause assessment | Statement, confidence, uncertainty/limitations | At least one factual support; otherwise explicit “insufficient evidence” |
| Hypothesis | Statement, ordinal, confidence/likelihood | Supports and contradictions where available |
| MITRE proposal | AttackTechnique external/catalog ID, confidence, rationale | Event/relationship/observation support; no indicator-only assertion without evidence context |
| Attack-stage proposal | Stage/order/description, confidence | Supporting Event or factual relationship IDs |
| Recommendation | Title/description, confidence, risk/impact, rollback/approval metadata | Evidence/Event/Entity/relationship support; state assumptions |
| ReasoningStep | Ordinal, statement, step type | Supports/contradicts links sufficient to reproduce the explanation |

## Safety and review rules

1. JSON/Pydantic validation is necessary but not sufficient: validated output is
   still an inference, never evidence.
2. Re-analysis creates a new AIAnalysis. It does not overwrite previous output
   or delete prior Recommendation records/decisions.
3. Low-confidence or unsupported claims must be represented as uncertainty, not
   silently omitted or rendered as facts.
4. The API/UI must visually distinguish factual graph nodes/edges from AI
   overlay nodes/edges and expose factual support links for every inference.
5. Analyst confirmation must create a Finding, mapping, or decision with its
   own rationale and AuditEvent; it must not change generated text in place.
6. An AI recommendation approval is a human decision, not automatic external
   action authorization. Execution integrations remain out of scope.

## Current-to-canonical transition

Current Aegis `POST /investigations/{id}/analyze` writes root cause, MITRE
strings, confidence, blast radius, attack chain, hypotheses, reasoning chain,
and replaces RecommendedAction rows. That behavior remains unchanged until the
approved implementation phase. Its eventual replacement creates an AIAnalysis
and returns a compatibility projection while existing consumers remain active.
