"""
The AI reasoning service. This is intentionally a single-pass analysis in
v1 — one prompt, one structured response — rather than the full
multi-agent LangGraph pipeline the architecture doc describes (Triage ->
Context Builder -> Root Cause / MITRE / Blast Radius / False Positive ->
Severity Synthesis -> Remediation Planner -> Report Writer). That pipeline
is the documented target; this is the smallest version that's honestly
useful: it fills in the same fields a real multi-agent pipeline would
(root_cause, mitre_techniques, confidence, blast_radius_summary,
false_positive_probability, attack_chain, alternative_hypotheses,
reasoning_chain, and per-action Decision Center detail) so the UI and API
contract don't change when the real multi-agent version replaces this
function's internals.
"""
import json
from uuid import UUID

from pydantic import BaseModel, Field, ValidationError as PydanticValidationError
from sqlalchemy.orm import Session

from app.modules.ai_reasoning.infrastructure.llm_provider import LLMProvider, get_llm_provider
from app.modules.investigations.infrastructure.models import (
    ActionStatus,
    Investigation,
    RecommendedAction,
)
from app.modules.investigations.infrastructure.repository import InvestigationRepository
from app.shared.exceptions import NotFoundError, ValidationError

_SYSTEM_PROMPT = """You are a senior security architect embedded in a SOC decision-support \
platform. Given a raw security investigation, produce a structured assessment. \
Respond with ONLY a single JSON object — no prose, no markdown fences, no explanation \
before or after it. The JSON object must have exactly these keys:

{
  "root_cause": "2-4 sentences explaining what most likely happened and why, in plain technical language",
  "mitre_techniques": ["T1078", "..."],
  "confidence": 0-100 integer, how confident you are in this root cause assessment,
  "false_positive_probability": 0-100 integer, how likely this is a benign/false alarm,
  "blast_radius_summary": "1-2 sentences on what's actually at risk if this is real",
  "attack_chain": [
    {"phase": "e.g. Initial Access", "description": "1 sentence on what happened at this stage"}
    ... ordered stages actually supported by the evidence, 0-6 entries. Empty list if the
    evidence doesn't support reconstructing a sequence.
  ],
  "alternative_hypotheses": [
    {"hypothesis": "a different plausible explanation for the same evidence", "likelihood": 0-100 integer}
    ... 0-3 entries, each less likely than the main root_cause. Omit entirely if the evidence
    is unambiguous enough that no real alternative exists.
  ],
  "reasoning_chain": [
    "Observed X in the evidence",
    "This is significant because Y",
    "Combined with Z, this indicates ..."
    ... 2-6 short steps showing the actual inference path from evidence to conclusion,
    not a restatement of root_cause
  ],
  "recommended_actions": [
    {
      "title": "short imperative action, e.g. 'Isolate endpoint'",
      "description": "1 sentence on what it does and why",
      "confidence": 0-100 integer, how confident you are this specific action is correct and useful,
      "business_impact": "low" | "medium" | "high", the disruption THIS ACTION causes if taken,
      "side_effects": "1 sentence on what a human will actually notice happen (e.g. a user session drops)",
      "rollback": "1 sentence on how to undo this action if it turns out to be wrong",
      "estimated_time_to_contain": "a short duration estimate, e.g. '5 minutes' or '1-2 hours'",
      "approval_tier": "SOC Tier 1" | "SOC Tier 2" | "CISO", who should be the one to approve this
        given its business_impact and how irreversible it is
    }
    ... 0-3 actions, fewer if the evidence doesn't support more
  ]
}

Ground every field in the specific evidence given — do not invent indicators, asset names, \
or techniques that weren't mentioned. If evidence is too thin to name a MITRE technique with \
any confidence, return an empty list for mitre_techniques rather than guessing. Never suggest \
an action with business_impact "high" and approval_tier "SOC Tier 1" — higher-impact actions \
need higher approval tiers."""


class _RecommendedActionOut(BaseModel):
    title: str
    description: str = ""
    confidence: int = Field(default=50, ge=0, le=100)
    business_impact: str = "low"
    side_effects: str = ""
    rollback: str = ""
    estimated_time_to_contain: str = ""
    approval_tier: str = "SOC Tier 1"


class _AttackChainStep(BaseModel):
    phase: str
    description: str = ""


class _AlternativeHypothesis(BaseModel):
    hypothesis: str
    likelihood: int = Field(ge=0, le=100)


class _ReasoningOut(BaseModel):
    """Validates the LLM's JSON response before anything touches the DB —
    a malformed or hallucinated-shape response fails loudly here rather
    than corrupting an investigation with partial data."""

    root_cause: str
    mitre_techniques: list[str] = Field(default_factory=list)
    confidence: int = Field(ge=0, le=100)
    false_positive_probability: int = Field(ge=0, le=100)
    blast_radius_summary: str = ""
    attack_chain: list[_AttackChainStep] = Field(default_factory=list)
    alternative_hypotheses: list[_AlternativeHypothesis] = Field(default_factory=list)
    reasoning_chain: list[str] = Field(default_factory=list)
    recommended_actions: list[_RecommendedActionOut] = Field(default_factory=list)


def _build_user_prompt(investigation: Investigation) -> str:
    evidence_lines = "\n".join(f"- {e.type.value}: {e.value}" for e in investigation.evidence) or "None recorded."
    timeline_lines = (
        "\n".join(
            f"- {e.occurred_at.isoformat()}: {e.description}"
            for e in sorted(investigation.timeline_events, key=lambda e: e.occurred_at)
        )
        or "None recorded."
    )
    return f"""Title: {investigation.title}
Source: {investigation.source}
Severity (as reported by source): {investigation.severity.value}
Description / raw notes: {investigation.root_cause or "None provided."}

Evidence:
{evidence_lines}

Timeline:
{timeline_lines}"""


class ReasoningService:
    def __init__(self, db: Session, llm: LLMProvider | None = None):
        self.db = db
        self.repo = InvestigationRepository(db)
        self.llm = llm or get_llm_provider()

    async def analyze(self, org_id: UUID, investigation_id: UUID) -> Investigation:
        investigation = self.repo.get_by_id(org_id, investigation_id)
        if investigation is None:
            raise NotFoundError("Investigation not found.")

        raw_response = await self.llm.complete_json(_SYSTEM_PROMPT, _build_user_prompt(investigation))
        result = self._parse_response(raw_response)

        investigation.root_cause = result.root_cause
        investigation.mitre_techniques = result.mitre_techniques
        investigation.confidence = result.confidence
        investigation.false_positive_probability = result.false_positive_probability
        investigation.blast_radius_summary = result.blast_radius_summary
        investigation.attack_chain = [step.model_dump() for step in result.attack_chain]
        investigation.alternative_hypotheses = [h.model_dump() for h in result.alternative_hypotheses]
        investigation.reasoning_chain = result.reasoning_chain

        # Replace any prior recommendations. Known limitation: this drops
        # the approve/dismiss history of previous actions if an
        # investigation is re-analyzed — acceptable for v1 since
        # re-analysis isn't part of the primary flow (the UI only offers
        # "Analyze" on investigations that haven't been analyzed yet).
        # A v2 version of this would archive rather than delete.
        for action in list(investigation.recommended_actions):
            self.db.delete(action)
        for action_out in result.recommended_actions:
            self.db.add(
                RecommendedAction(
                    investigation_id=investigation.id,
                    title=action_out.title,
                    description=action_out.description,
                    status=ActionStatus.PENDING,
                    confidence=action_out.confidence,
                    business_impact=action_out.business_impact,
                    side_effects=action_out.side_effects,
                    rollback=action_out.rollback,
                    estimated_time_to_contain=action_out.estimated_time_to_contain,
                    approval_tier=action_out.approval_tier,
                )
            )

        self.db.flush()
        return self.repo.get_by_id(org_id, investigation_id)

    @staticmethod
    def _parse_response(raw_text: str) -> _ReasoningOut:
        cleaned = raw_text.strip()
        # Defensive: strip markdown fences if the model adds them despite
        # instructions not to — cheap insurance, not a hard dependency.
        if cleaned.startswith("```"):
            cleaned = cleaned.strip("`")
            if cleaned.startswith("json"):
                cleaned = cleaned[4:]
            cleaned = cleaned.strip()

        try:
            parsed = json.loads(cleaned)
        except json.JSONDecodeError as exc:
            raise ValidationError("The AI's response wasn't valid JSON — try again.") from exc

        try:
            return _ReasoningOut.model_validate(parsed)
        except PydanticValidationError as exc:
            raise ValidationError(f"The AI's response didn't match the expected shape: {exc}") from exc
