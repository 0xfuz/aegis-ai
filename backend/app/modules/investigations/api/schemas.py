from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

# Kept as plain sets here rather than importing the ORM's IOCVerdict/
# EvidenceType enums, so the API schema layer doesn't reach into
# infrastructure models (see shared/base.py's module-boundary note) just
# to validate a request body's string fields.
_VALID_IOC_TYPES = {"ip", "hash", "domain", "url", "asset"}
_VALID_IOC_VERDICTS = {"malicious", "suspicious", "unknown", "benign"}


class TimelineEventRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    occurred_at: datetime
    description: str
    severity: str | None
    mitre_technique: str | None
    source: str | None
    affected_asset: str | None
    actor: str | None


class EvidenceRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    type: str
    value: str


class EvidenceRecordRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    category: str
    occurred_at: datetime
    summary: str
    details: dict


class NoteRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    author_id: UUID
    body: str = Field(max_length=4000)
    created_at: datetime
    updated_at: datetime


class NoteCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    body: str = Field(min_length=1, max_length=4000)

    @field_validator("body")
    @classmethod
    def non_blank_body(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Note body must not be blank.")
        return value


class NotePage(BaseModel):
    items: list[NoteRead]
    limit: int
    offset: int
    total: int


class RecommendedActionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    title: str
    description: str
    status: str
    confidence: int | None
    business_impact: str | None
    side_effects: str | None
    rollback: str | None
    estimated_time_to_contain: str | None
    approval_tier: str | None


class InvestigationSummary(BaseModel):
    """Lightweight shape for list views (dashboard queue, investigations table)."""

    model_config = ConfigDict(from_attributes=True)
    id: UUID
    title: str
    source: str
    severity: str
    status: str
    confidence: int
    created_at: datetime


class InvestigationDetail(BaseModel):
    """Full shape for the Investigation Workspace."""

    model_config = ConfigDict(from_attributes=True)
    id: UUID
    org_id: UUID
    title: str
    source: str
    severity: str
    status: str
    assignee_id: UUID | None
    confidence: int
    root_cause: str
    mitre_techniques: list[str]
    blast_radius_summary: str
    false_positive_probability: int
    attack_chain: list[dict]
    alternative_hypotheses: list[dict]
    reasoning_chain: list[str]
    created_at: datetime
    updated_at: datetime
    timeline_events: list[TimelineEventRead]
    evidence: list[EvidenceRead]
    evidence_records: list[EvidenceRecordRead]
    notes: list[NoteRead]
    recommended_actions: list[RecommendedActionRead]


class InvestigationStatusUpdate(BaseModel):
    status: str


class RelatedInvestigation(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    title: str
    severity: str
    status: str


class IOCSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    type: str
    value: str
    tags: list[str]
    confidence: int
    verdict: str
    provenance: str
    is_watched: bool
    sightings_count: int
    last_seen: datetime

    @field_validator("type", mode="before")
    @classmethod
    def flatten_type(cls, v):
        return v.value if hasattr(v, "value") else v


class IOCDetail(BaseModel):
    type: str
    value: str
    tags: list[str]
    confidence: int
    verdict: str
    provenance: str
    is_watched: bool
    watched_at: datetime | None
    enrichment: dict
    first_seen: datetime
    last_seen: datetime
    sightings_count: int
    related_investigations: list[RelatedInvestigation]
    related_assets: list[str]
    related_evidence: list[EvidenceRecordRead]


class IOCWatchRequest(BaseModel):
    """Body for POST /iocs/watch — toggles watchlist membership for one
    indicator. `type`/`value` identify the indicator the same way the
    existing lookup endpoint does; watchlisting an indicator that hasn't
    been sighted yet is allowed on purpose (an analyst watching a hash
    from a threat report before it ever shows up in an investigation)."""

    type: str
    value: str = Field(min_length=1, max_length=255)
    watched: bool

    @field_validator("type")
    @classmethod
    def validate_type(cls, v: str) -> str:
        if v not in _VALID_IOC_TYPES:
            raise ValueError(f"Invalid indicator type '{v}'. Valid values: {', '.join(sorted(_VALID_IOC_TYPES))}.")
        return v


class IOCVerdictRequest(BaseModel):
    """Body for POST /iocs/verdict — a real analyst classification
    action, independent of `confidence`."""

    type: str
    value: str = Field(min_length=1, max_length=255)
    verdict: str

    @field_validator("type")
    @classmethod
    def validate_type(cls, v: str) -> str:
        if v not in _VALID_IOC_TYPES:
            raise ValueError(f"Invalid indicator type '{v}'. Valid values: {', '.join(sorted(_VALID_IOC_TYPES))}.")
        return v

    @field_validator("verdict")
    @classmethod
    def validate_verdict(cls, v: str) -> str:
        if v not in _VALID_IOC_VERDICTS:
            raise ValueError(f"Invalid verdict '{v}'. Valid values: {', '.join(sorted(_VALID_IOC_VERDICTS))}.")
        return v


class DashboardSummary(BaseModel):
    open_investigations: int
    critical_open: int
    avg_false_positive_probability: float
    total_investigations: int


class AuditActorRead(BaseModel):
    type: str
    id: UUID | None


class AuditTargetRead(BaseModel):
    type: str
    id: UUID


class AuditTransitionRead(BaseModel):
    from_: str | None = Field(alias="from")
    to: str | None


class AuditEventRead(BaseModel):
    id: UUID
    event_type: str
    occurred_at: datetime
    actor: AuditActorRead
    target: AuditTargetRead
    transition: AuditTransitionRead | None


class AuditEventPage(BaseModel):
    items: list[AuditEventRead]
    limit: int
    offset: int
    total: int
