"""Phase 8 intelligence-run and claim-state invariants.

The database is the source of truth.  This module deliberately centralises
creation and transition rules so API adapters cannot invent another state
machine or claim vocabulary.
"""
from __future__ import annotations

from app.shared.exceptions import ValidationError

RUN_TRANSITIONS = {
    "QUEUED": {"RUNNING", "CANCELLED"},
    "RUNNING": {"COMPLETED", "FAILED", "CANCELLED"},
    "COMPLETED": set(), "FAILED": set(), "CANCELLED": set(),
}
CLAIM_TYPES = {"FACT", "OBSERVATION", "INFERENCE", "HYPOTHESIS", "RECOMMENDATION"}
CLAIM_ORIGINS = {"SOURCE", "DETERMINISTIC_ENGINE", "AI", "ANALYST"}
REVIEW_STATUSES = {"PENDING", "CONFIRMED", "REJECTED", "UNRESOLVED", "SUPERSEDED"}
REVIEW_TRANSITIONS = {
    "PENDING": {"CONFIRMED", "REJECTED", "UNRESOLVED", "SUPERSEDED"},
    "UNRESOLVED": {"CONFIRMED", "REJECTED", "SUPERSEDED"},
    "CONFIRMED": {"SUPERSEDED"}, "REJECTED": {"SUPERSEDED"}, "SUPERSEDED": set(),
}
# Historical AIIE output categories remain readable.  New writes use only the
# canonical vocabulary; this mapping makes their canonical semantic explicit.
LEGACY_KIND_TO_CLAIM_TYPE = {"SUMMARY": "INFERENCE", "QUESTION": "INFERENCE", "REASONING": "INFERENCE"}
LEGACY_REVIEW_TO_CANONICAL = {"UNREVIEWED": "PENDING", "APPROVED": "CONFIRMED"}


def canonical_claim_type(kind: str) -> str:
    return LEGACY_KIND_TO_CLAIM_TYPE.get(kind, kind)


def validate_run_transition(current: str, target: str) -> None:
    if target not in RUN_TRANSITIONS.get(current, set()):
        raise ValidationError(f"Invalid intelligence run transition from {current} to {target}.")


def validate_claim_creation(kind: str, origin: str, review_status: str) -> None:
    if kind not in CLAIM_TYPES or origin not in CLAIM_ORIGINS or review_status not in REVIEW_STATUSES:
        raise ValidationError("Invalid intelligence claim contract values.")
    allowed = {
        "SOURCE": {"OBSERVATION"},
        "DETERMINISTIC_ENGINE": {"FACT", "OBSERVATION", "INFERENCE"},
        "AI": {"OBSERVATION", "INFERENCE", "HYPOTHESIS", "RECOMMENDATION"},
        "ANALYST": {"OBSERVATION", "INFERENCE", "HYPOTHESIS", "RECOMMENDATION"},
    }
    if kind not in allowed[origin]:
        raise ValidationError(f"{origin} cannot create {kind} claims.")
    if kind == "FACT" and (origin != "DETERMINISTIC_ENGINE" or review_status != "CONFIRMED"):
        raise ValidationError("FACT claims require a deterministic engine and begin confirmed.")
    if kind != "FACT" and review_status != "PENDING":
        raise ValidationError("New non-FACT claims must begin pending.")


def validate_review_transition(current: str, target: str) -> None:
    if target not in REVIEW_TRANSITIONS.get(current, set()):
        raise ValidationError(f"Invalid review transition from {current} to {target}.")


def canonical_review_status(status: str) -> str:
    return LEGACY_REVIEW_TO_CANONICAL.get(status, status)
