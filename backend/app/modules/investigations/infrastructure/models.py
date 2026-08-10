"""
ORM models for the `investigations` module — the core case object every
other module (attack_graph, reporting, analytics) hangs off of.

v1 (MVP) scope: all data here is either user-entered or seeded mock data
standing in for a real correlation/AI pipeline. The `root_cause`,
`mitre_techniques`, `confidence`, `false_positive_probability`, and
`recommended actions` fields are exactly what a real `ai_reasoning` module
would populate later — the shape is deliberately final even though the
values are mocked, so wiring in a real AI pipeline in v2 is a
service-layer swap, not a schema change.
"""
import enum
import uuid

from sqlalchemy import (
    Boolean,
    ForeignKey,
    Integer,
    String,
    Text,
    DateTime,
    Enum as SAEnum,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.shared.base import Base, OrgScopedMixin, TimestampMixin, UUIDPrimaryKeyMixin


class Severity(str, enum.Enum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"


class InvestigationStatus(str, enum.Enum):
    NEW = "new"
    TRIAGING = "triaging"
    INVESTIGATING = "investigating"
    CONTAINED = "contained"
    RESOLVED = "resolved"


class EvidenceType(str, enum.Enum):
    IP = "ip"
    HASH = "hash"
    DOMAIN = "domain"
    URL = "url"
    ASSET = "asset"


class EvidenceCategory(str, enum.Enum):
    """The Evidence Explorer's categories — real forensic telemetry, as
    distinct from the simple IOC chips (EvidenceType above), which stay
    as the quick-glance indicator list. Stored as plain text (not a DB
    enum) since this list is far more likely to grow as real EDR/log
    sources are wired in than the core investigation severity/status
    enums are — a DB enum migration for every new category would be
    the wrong trade-off here."""

    PROCESS = "process"
    FILE = "file"
    REGISTRY = "registry"
    DNS = "dns"
    FIREWALL = "firewall"
    AUTHENTICATION = "authentication"
    NETWORK_CONNECTION = "network_connection"
    POWERSHELL = "powershell"
    COMMAND_HISTORY = "command_history"
    BROWSER_HISTORY = "browser_history"


class ActionStatus(str, enum.Enum):
    PENDING = "pending"
    APPROVED = "approved"
    DISMISSED = "dismissed"


class IOCVerdict(str, enum.Enum):
    """A real analyst/system classification — independent of `confidence`
    (a 0-100 malicious-ness score). Two IOCs can both sit at confidence 60
    with different verdicts: one because an analyst reviewed it and called
    it suspicious, the other because nobody has looked at it yet and it's
    honestly unknown. Stored as plain String (not a DB enum), same
    rationale as Asset.criticality/health: a low-cardinality, frequently
    analyst-updated classification, not a structural/foundational type —
    a DB enum migration for every new value would be the wrong trade-off."""

    MALICIOUS = "malicious"
    SUSPICIOUS = "suspicious"
    UNKNOWN = "unknown"
    BENIGN = "benign"


class Investigation(Base, UUIDPrimaryKeyMixin, TimestampMixin, OrgScopedMixin):
    __tablename__ = "investigations"

    title: Mapped[str] = mapped_column(String(255), nullable=False)
    source: Mapped[str] = mapped_column(String(100), nullable=False, default="Mock Data")
    severity: Mapped[Severity] = mapped_column(
        SAEnum(Severity, name="severity", values_callable=lambda enum_cls: [e.value for e in enum_cls]),
        nullable=False,
    )
    status: Mapped[InvestigationStatus] = mapped_column(
        SAEnum(
            InvestigationStatus,
            name="investigation_status",
            values_callable=lambda enum_cls: [e.value for e in enum_cls],
        ),
        nullable=False,
        default=InvestigationStatus.NEW,
    )
    assignee_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )

    # --- AI reasoning fields (mocked in v1, real in a later ai_reasoning module) ---
    confidence: Mapped[int] = mapped_column(Integer, nullable=False, default=0)  # 0-100
    root_cause: Mapped[str] = mapped_column(Text, nullable=False, default="")
    mitre_techniques: Mapped[list[str]] = mapped_column(ARRAY(String(20)), nullable=False, default=list)
    blast_radius_summary: Mapped[str] = mapped_column(Text, nullable=False, default="")
    false_positive_probability: Mapped[int] = mapped_column(Integer, nullable=False, default=0)  # 0-100

    # Structured reasoning detail — schemaless JSONB (same rationale as
    # EvidenceRecord.details): an attack chain's stage count and an
    # alternative hypothesis's shape don't need a rigid schema, and this
    # is exactly the data a real multi-agent LangGraph pipeline (see the
    # architecture doc) would populate per-agent rather than in one call.
    # attack_chain: [{"phase": "Initial Access", "description": "..."}]
    # alternative_hypotheses: [{"hypothesis": "...", "likelihood": 15}]
    # reasoning_chain: ["Observed X because Y", "This rules out Z because...", ...]
    attack_chain: Mapped[list[dict]] = mapped_column(JSONB, nullable=False, default=list)
    alternative_hypotheses: Mapped[list[dict]] = mapped_column(JSONB, nullable=False, default=list)
    reasoning_chain: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)

    timeline_events: Mapped[list["TimelineEvent"]] = relationship(
        back_populates="investigation", cascade="all, delete-orphan", order_by="TimelineEvent.occurred_at"
    )
    evidence: Mapped[list["Evidence"]] = relationship(
        back_populates="investigation", cascade="all, delete-orphan"
    )
    evidence_records: Mapped[list["EvidenceRecord"]] = relationship(
        back_populates="investigation", cascade="all, delete-orphan", order_by="EvidenceRecord.occurred_at"
    )
    notes: Mapped[list["Note"]] = relationship(
        back_populates="investigation", cascade="all, delete-orphan", order_by="Note.created_at"
    )
    recommended_actions: Mapped[list["RecommendedAction"]] = relationship(
        back_populates="investigation", cascade="all, delete-orphan"
    )


class Finding(Base, UUIDPrimaryKeyMixin, TimestampMixin, OrgScopedMixin):
    """An analyst-owned conclusion. Source inference remains immutable."""
    __tablename__ = "findings"
    __table_args__ = (UniqueConstraint("source_intelligence_item_id", name="uq_findings_source_item"),)
    investigation_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("investigations.id", ondelete="RESTRICT"), nullable=False, index=True)
    source_intelligence_item_id: Mapped[uuid.UUID | None] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("intelligence_items.id", ondelete="RESTRICT"), nullable=True)
    source_analysis_id: Mapped[uuid.UUID | None] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("intelligence_analyses.id", ondelete="RESTRICT"), nullable=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    severity: Mapped[str] = mapped_column(String(20), nullable=False, default="medium")
    confidence: Mapped[int | None] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="OPEN")
    analyst_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)


class FindingFactLink(Base, UUIDPrimaryKeyMixin, OrgScopedMixin):
    __tablename__ = "finding_fact_links"
    finding_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("findings.id", ondelete="RESTRICT"), nullable=False, index=True)
    fact_type: Mapped[str] = mapped_column(String(64), nullable=False)
    fact_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    role: Mapped[str] = mapped_column(String(20), nullable=False, default="SUPPORTS")


class MitreMapping(Base, UUIDPrimaryKeyMixin, TimestampMixin, OrgScopedMixin):
    __tablename__ = "mitre_mappings"
    investigation_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("investigations.id", ondelete="RESTRICT"), nullable=False, index=True)
    source_intelligence_item_id: Mapped[uuid.UUID | None] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("intelligence_items.id", ondelete="RESTRICT"), nullable=True)
    finding_id: Mapped[uuid.UUID | None] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("findings.id", ondelete="RESTRICT"), nullable=True)
    technique_id: Mapped[str] = mapped_column(String(32), nullable=False)
    technique_name: Mapped[str | None] = mapped_column(String(255))
    tactic: Mapped[str | None] = mapped_column(String(100))
    confidence: Mapped[int | None] = mapped_column(Integer)
    ai_rationale: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="PROPOSED")
    reviewed_by_id: Mapped[uuid.UUID | None] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"))
    reviewed_at: Mapped["DateTime | None"] = mapped_column(DateTime(timezone=True))
    review_rationale: Mapped[str | None] = mapped_column(Text)


class MitreMappingFactLink(Base, UUIDPrimaryKeyMixin, OrgScopedMixin):
    __tablename__ = "mitre_mapping_fact_links"
    mapping_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("mitre_mappings.id", ondelete="RESTRICT"), nullable=False, index=True)
    fact_type: Mapped[str] = mapped_column(String(64), nullable=False)
    fact_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    role: Mapped[str] = mapped_column(String(20), nullable=False, default="SUPPORTS")


class TimelineEvent(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "investigation_timeline_events"

    investigation_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("investigations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    occurred_at: Mapped["DateTime"] = mapped_column(DateTime(timezone=True), nullable=False)
    description: Mapped[str] = mapped_column(String(500), nullable=False)

    # Per-event forensic detail — an investigation's overall severity is a
    # judgment call, but each individual event has its own severity, and a
    # single investigation can span multiple MITRE techniques across its
    # timeline (e.g. initial access, then later privilege escalation).
    severity: Mapped[Severity | None] = mapped_column(
        SAEnum(Severity, name="severity", values_callable=lambda enum_cls: [e.value for e in enum_cls]),
        nullable=True,
    )
    mitre_technique: Mapped[str | None] = mapped_column(String(20), nullable=True)
    source: Mapped[str | None] = mapped_column(String(100), nullable=True)
    affected_asset: Mapped[str | None] = mapped_column(String(255), nullable=True)
    actor: Mapped[str | None] = mapped_column(String(255), nullable=True)

    investigation: Mapped["Investigation"] = relationship(back_populates="timeline_events")


class Evidence(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "investigation_evidence"

    investigation_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("investigations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    type: Mapped[EvidenceType] = mapped_column(
        SAEnum(EvidenceType, name="evidence_type", values_callable=lambda enum_cls: [e.value for e in enum_cls]),
        nullable=False,
    )
    value: Mapped[str] = mapped_column(String(255), nullable=False)

    investigation: Mapped["Investigation"] = relationship(back_populates="evidence")


class IOC(Base, UUIDPrimaryKeyMixin, TimestampMixin, OrgScopedMixin):
    """An indicator's identity is the (org, type, value) tuple, not any
    one investigation — the same IP can show up in five different
    investigations, and 'related incidents' / 'historical sightings'
    only mean something if the IOC is tracked once, org-wide, rather
    than duplicated per investigation the way the simple Evidence chips
    are. Every time an indicator is seen (seeding, connector ingest,
    manual entry), record_sighting() upserts this row rather than
    creating a new one — sightings_count and last_seen accumulate across
    every investigation that ever referenced it."""

    __tablename__ = "iocs"
    __table_args__ = (UniqueConstraint("org_id", "type", "value", name="uq_iocs_org_type_value"),)

    type: Mapped[EvidenceType] = mapped_column(
        SAEnum(EvidenceType, name="evidence_type", values_callable=lambda enum_cls: [e.value for e in enum_cls]),
        nullable=False,
    )
    value: Mapped[str] = mapped_column(String(255), nullable=False, index=True)

    # Manually curated in v1 (seed data / analyst input) — a real
    # threat-intel connector (Phase 4) would populate `enrichment` and
    # bump `confidence` automatically instead. Schemaless JSONB for the
    # same reason as EvidenceRecord.details: enrichment shape varies a
    # lot by indicator type (an IP's enrichment looks nothing like a
    # file hash's) and by which TI feed produced it.
    tags: Mapped[list[str]] = mapped_column(ARRAY(String(50)), nullable=False, default=list)
    confidence: Mapped[int] = mapped_column(Integer, nullable=False, default=50)  # 0-100, malicious-ness
    enrichment: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)

    # A real classification, not inferred from confidence or from any UI
    # label — see IOCVerdict. Defaults to "unknown" (honest: nobody has
    # classified it) rather than defaulting to "benign" or deriving a
    # guess from `confidence`.
    verdict: Mapped[str] = mapped_column(String(20), nullable=False, default=IOCVerdict.UNKNOWN.value)

    # Where tags/confidence/enrichment/verdict came from. "internal" means
    # seed-time curation or an analyst action within Aegis — never a real
    # external feed call. A real external provider (Phase 4 extension,
    # see enrichment_provider.py) would stamp its own provenance key here
    # instead, so the UI can always tell honestly which is which and never
    # imply an external lookup happened when it didn't.
    provenance: Mapped[str] = mapped_column(String(20), nullable=False, default="internal")

    is_watched: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    watched_at: Mapped["DateTime | None"] = mapped_column(DateTime(timezone=True), nullable=True)

    first_seen: Mapped["DateTime"] = mapped_column(DateTime(timezone=True), nullable=False)
    last_seen: Mapped["DateTime"] = mapped_column(DateTime(timezone=True), nullable=False)
    sightings_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class EvidenceRecord(Base, UUIDPrimaryKeyMixin):
    """The Evidence Explorer's actual data: a single piece of structured
    forensic telemetry (a process launch, a file write, a DNS query, an
    auth event, ...). `details` holds whatever key/value fields are
    relevant to that category — a process record has pid/command_line/
    parent, a DNS record has query/response/resolver, etc. This is
    deliberately schemaless at the DB level (JSONB) rather than one table
    per category: the categories share far more (investigation_id,
    occurred_at, a one-line summary, search) than they differ, and a
    real EDR feed's fields vary enough vendor-to-vendor that a rigid
    per-category schema would need constant migrations."""

    __tablename__ = "investigation_evidence_records"

    investigation_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("investigations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    category: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    occurred_at: Mapped["DateTime"] = mapped_column(DateTime(timezone=True), nullable=False)
    summary: Mapped[str] = mapped_column(String(500), nullable=False)
    details: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)

    investigation: Mapped["Investigation"] = relationship(back_populates="evidence_records")


class Note(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "investigation_notes"

    investigation_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("investigations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    author_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)

    investigation: Mapped["Investigation"] = relationship(back_populates="notes")


class RecommendedAction(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "investigation_recommended_actions"

    investigation_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("investigations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    status: Mapped[ActionStatus] = mapped_column(
        SAEnum(ActionStatus, name="action_status", values_callable=lambda enum_cls: [e.value for e in enum_cls]),
        nullable=False,
        default=ActionStatus.PENDING,
    )

    # Decision Center fields — turning "here's an action" into "here's a
    # decision, with the information a human needs to actually make it."
    # Every field here answers a specific question an approver would ask
    # before clicking anything: how sure is the AI, what does this cost
    # us if wrong, can we undo it, how fast does it act, and who's
    # actually allowed to say yes.
    confidence: Mapped[int | None] = mapped_column(Integer, nullable=True)  # 0-100
    business_impact: Mapped[str | None] = mapped_column(String(20), nullable=True)  # low | medium | high
    side_effects: Mapped[str | None] = mapped_column(Text, nullable=True)
    rollback: Mapped[str | None] = mapped_column(Text, nullable=True)
    estimated_time_to_contain: Mapped[str | None] = mapped_column(String(100), nullable=True)
    approval_tier: Mapped[str | None] = mapped_column(String(50), nullable=True)  # e.g. "SOC Tier 2", "CISO"

    investigation: Mapped["Investigation"] = relationship(back_populates="recommended_actions")
