"""
Repository pattern for the investigations module — all direct querying
lives here, same convention as identity/infrastructure/repository.py.
"""
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import Text, cast, func, or_, select
from sqlalchemy.orm import Session, joinedload

from app.modules.investigations.infrastructure.models import (
    Evidence,
    EvidenceRecord,
    EvidenceType,
    Investigation,
    InvestigationStatus,
    IOC,
    Note,
    RecommendedAction,
    TimelineEvent,
)


class InvestigationRepository:
    def __init__(self, db: Session):
        self.db = db

    def _base_query(self):
        return select(Investigation).options(
            joinedload(Investigation.timeline_events),
            joinedload(Investigation.evidence),
            joinedload(Investigation.evidence_records),
            joinedload(Investigation.notes),
            joinedload(Investigation.recommended_actions),
        )

    def get_by_id(self, org_id: UUID, investigation_id: UUID) -> Investigation | None:
        stmt = self._base_query().where(
            Investigation.id == investigation_id, Investigation.org_id == org_id
        )
        return self.db.execute(stmt).unique().scalar_one_or_none()

    def list_by_org(
        self,
        org_id: UUID,
        status: InvestigationStatus | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Investigation]:
        stmt = (
            select(Investigation)
            .where(Investigation.org_id == org_id)
            .order_by(Investigation.created_at.desc(), Investigation.id.desc())
            .limit(limit)
            .offset(offset)
        )
        if status is not None:
            stmt = stmt.where(Investigation.status == status)
        return list(self.db.execute(stmt).scalars().all())

    def count_by_org(
        self,
        org_id: UUID,
        status: InvestigationStatus | None = None,
        from_at: datetime | None = None,
        to_at: datetime | None = None,
    ) -> int:
        stmt = select(func.count()).select_from(Investigation).where(Investigation.org_id == org_id)
        if status is not None:
            stmt = stmt.where(Investigation.status == status)
        if from_at is not None:
            stmt = stmt.where(Investigation.created_at >= from_at)
        if to_at is not None:
            stmt = stmt.where(Investigation.created_at < to_at)
        return self.db.execute(stmt).scalar_one()

    def count_open(self, org_id: UUID, from_at: datetime | None = None, to_at: datetime | None = None) -> int:
        stmt = (
            select(func.count())
            .select_from(Investigation)
            .where(
                Investigation.org_id == org_id,
                Investigation.status != InvestigationStatus.RESOLVED,
            )
        )
        if from_at is not None:
            stmt = stmt.where(Investigation.created_at >= from_at)
        if to_at is not None:
            stmt = stmt.where(Investigation.created_at < to_at)
        return self.db.execute(stmt).scalar_one()

    def count_critical_open(self, org_id: UUID, from_at: datetime | None = None, to_at: datetime | None = None) -> int:
        from app.modules.investigations.infrastructure.models import Severity

        stmt = (
            select(func.count())
            .select_from(Investigation)
            .where(
                Investigation.org_id == org_id,
                Investigation.severity == Severity.CRITICAL,
                Investigation.status != InvestigationStatus.RESOLVED,
            )
        )
        if from_at is not None:
            stmt = stmt.where(Investigation.created_at >= from_at)
        if to_at is not None:
            stmt = stmt.where(Investigation.created_at < to_at)
        return self.db.execute(stmt).scalar_one()

    def avg_false_positive_probability(
        self, org_id: UUID, from_at: datetime | None = None, to_at: datetime | None = None
    ) -> float:
        stmt = select(func.avg(Investigation.false_positive_probability)).where(
            Investigation.org_id == org_id
        )
        if from_at is not None:
            stmt = stmt.where(Investigation.created_at >= from_at)
        if to_at is not None:
            stmt = stmt.where(Investigation.created_at < to_at)
        result = self.db.execute(stmt).scalar_one()
        return float(result) if result is not None else 0.0

    def create(self, investigation: Investigation) -> Investigation:
        self.db.add(investigation)
        self.db.flush()
        return investigation

    def save(self, investigation: Investigation) -> Investigation:
        self.db.flush()
        return investigation

    def add_note(self, note: Note) -> Note:
        self.db.add(note)
        self.db.flush()
        return note

    def get_action(self, org_id: UUID, action_id: UUID) -> RecommendedAction | None:
        stmt = (
            select(RecommendedAction)
            .join(Investigation)
            .where(RecommendedAction.id == action_id, Investigation.org_id == org_id)
        )
        return self.db.execute(stmt).scalar_one_or_none()


class IOCRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_by_value(self, org_id: UUID, ioc_type: str, value: str) -> IOC | None:
        stmt = select(IOC).where(IOC.org_id == org_id, IOC.type == ioc_type, IOC.value == value)
        return self.db.execute(stmt).scalar_one_or_none()

    def record_sighting(
        self, org_id: UUID, ioc_type: str, value: str, seen_at: datetime | None = None
    ) -> IOC:
        """Upsert: first time this (org, type, value) is seen, create the
        IOC row; every subsequent sighting just bumps the counter and
        last_seen. This is what every evidence-creation call site (seed
        data, connector ingest, manual entry) should call — never
        `IOC(...)` directly, or sightings_count silently stops meaning
        anything."""
        seen_at = seen_at or datetime.now(timezone.utc)
        ioc = self.get_by_value(org_id, ioc_type, value)
        if ioc is None:
            ioc = IOC(
                org_id=org_id,
                type=ioc_type,
                value=value,
                first_seen=seen_at,
                last_seen=seen_at,
                sightings_count=1,
            )
            self.db.add(ioc)
        else:
            ioc.sightings_count += 1
            if seen_at > ioc.last_seen:
                ioc.last_seen = seen_at
            if seen_at < ioc.first_seen:
                ioc.first_seen = seen_at
        self.db.flush()
        return ioc

    def set_enrichment(
        self,
        ioc: IOC,
        tags: list[str],
        confidence: int,
        enrichment: dict,
        verdict: str | None = None,
        provenance: str = "internal",
    ) -> IOC:
        """Manual/seed-time curation, or a future real external provider
        (see enrichment_provider.py) calling this same method with
        feed-derived values and its own `provenance` key instead of
        "internal". `verdict` is optional here because curating
        tags/confidence/enrichment doesn't always come with a fresh
        classification decision — pass None to leave the existing verdict
        untouched."""
        ioc.tags = tags
        ioc.confidence = confidence
        ioc.enrichment = enrichment
        if verdict is not None:
            ioc.verdict = verdict
        ioc.provenance = provenance
        self.db.flush()
        return ioc

    def set_verdict(self, ioc: IOC, verdict: str) -> IOC:
        """A standalone analyst classification action — doesn't require
        redoing tags/confidence/enrichment, e.g. 'mark this malicious'
        after reviewing related investigations."""
        ioc.verdict = verdict
        self.db.flush()
        return ioc

    def set_watched(self, ioc: IOC, watched: bool) -> IOC:
        ioc.is_watched = watched
        ioc.watched_at = datetime.now(timezone.utc) if watched else None
        self.db.flush()
        return ioc

    def get_or_create(self, org_id: UUID, ioc_type: str, value: str, seen_at: datetime | None = None) -> IOC:
        """Like record_sighting, but for actions (watchlisting) that need
        an IOC row to exist even for an indicator that's never actually
        been sighted yet — an analyst watchlisting a hash from a threat
        report before it ever shows up in an investigation. Honestly
        starts at sightings_count=0 rather than borrowing
        record_sighting's sightings_count=1, since "watched" and "seen"
        are different facts.

        Unlike record_sighting's existing call sites (always passed a
        real EvidenceType member already), this is reachable directly
        from the API with a plain string — coerce it to EvidenceType
        before constructing a new row, or the in-memory object ends up
        with a raw str in `.type` instead of the enum member until the
        session is expired and reloaded from the DB."""
        ioc = self.get_by_value(org_id, ioc_type, value)
        if ioc is None:
            now = seen_at or datetime.now(timezone.utc)
            ioc = IOC(
                org_id=org_id,
                type=EvidenceType(ioc_type),
                value=value,
                first_seen=now,
                last_seen=now,
                sightings_count=0,
            )
            self.db.add(ioc)
            self.db.flush()
        return ioc

    def list_by_org(
        self, org_id: UUID, verdict: str | None = None, watched_only: bool = False
    ) -> list[IOC]:
        """The Threat Intelligence portal's inventory list — every
        indicator this org has ever recorded a sighting of, most-seen
        first, so the indicators actually worth an analyst's attention
        surface at the top. Optional verdict/watched_only filters back
        the frontend's filter chips and Watchlist tab."""
        stmt = select(IOC).where(IOC.org_id == org_id)
        if verdict is not None:
            stmt = stmt.where(IOC.verdict == verdict)
        if watched_only:
            stmt = stmt.where(IOC.is_watched.is_(True))
        stmt = stmt.order_by(IOC.sightings_count.desc(), IOC.last_seen.desc())
        return list(self.db.execute(stmt).scalars().all())

    def list_watched(self, org_id: UUID) -> list[IOC]:
        """The Watchlist tab — most-recently-watched first, so an
        analyst's newest additions surface at the top."""
        stmt = (
            select(IOC)
            .where(IOC.org_id == org_id, IOC.is_watched.is_(True))
            .order_by(IOC.watched_at.desc())
        )
        return list(self.db.execute(stmt).scalars().all())

    def find_investigations_with_value(
        self, org_id: UUID, ioc_type: str, value: str, exclude_investigation_id: UUID | None = None
    ) -> list[Investigation]:
        """The 'related incidents' behind IOC Intelligence — genuinely
        computed from real Evidence rows, not mocked: every investigation
        that ever recorded this exact indicator."""
        stmt = (
            select(Investigation)
            .join(Evidence, Evidence.investigation_id == Investigation.id)
            .where(Investigation.org_id == org_id, Evidence.type == ioc_type, Evidence.value == value)
            .order_by(Investigation.created_at.desc())
        )
        if exclude_investigation_id is not None:
            stmt = stmt.where(Investigation.id != exclude_investigation_id)
        return list(self.db.execute(stmt).scalars().all())

    def _investigation_ids_with_value(
        self, org_id: UUID, ioc_type: str, value: str, exclude_investigation_id: UUID | None
    ):
        """Shared subquery: investigation ids that recorded this exact
        indicator as Evidence. Used by both related-asset and
        related-evidence lookups so they stay scoped to investigations
        that genuinely involved this indicator, not a coincidental
        substring match anywhere in the org."""
        stmt = (
            select(Investigation.id)
            .join(Evidence, Evidence.investigation_id == Investigation.id)
            .where(Investigation.org_id == org_id, Evidence.type == ioc_type, Evidence.value == value)
        )
        if exclude_investigation_id is not None:
            stmt = stmt.where(Investigation.id != exclude_investigation_id)
        return stmt

    def find_related_asset_names(
        self, org_id: UUID, ioc_type: str, value: str, exclude_investigation_id: UUID | None = None
    ) -> list[str]:
        """Asset names 'seen alongside' this indicator — investigations
        that recorded both this IOC and an 'asset' evidence chip.
        Genuinely computed co-occurrence, not a structured link: the
        schema has no foreign key between iocs and assets, so this is
        explicitly "appeared in the same investigation," not "this asset
        was compromised by this indicator." """
        inv_ids = self._investigation_ids_with_value(org_id, ioc_type, value, exclude_investigation_id)
        stmt = (
            select(Evidence.value)
            .where(Evidence.investigation_id.in_(inv_ids), Evidence.type == EvidenceType.ASSET)
            .distinct()
        )
        return list(self.db.execute(stmt).scalars().all())

    def find_related_evidence_records(
        self,
        org_id: UUID,
        ioc_type: str,
        value: str,
        exclude_investigation_id: UUID | None = None,
        limit: int = 25,
    ) -> list[EvidenceRecord]:
        """Evidence Explorer records that literally reference this
        indicator's value — a real text match against real forensic
        telemetry (summary or the schemaless `details` JSONB, cast to
        text), not a foreign-key join: EvidenceRecord.details is
        deliberately schemaless (see its model docstring), so there's no
        structured field to join an IOC's value against. Scoped to
        investigations that also recorded this IOC as Evidence, so a
        coincidental substring match in an unrelated investigation can't
        surface here."""
        inv_ids = self._investigation_ids_with_value(org_id, ioc_type, value, exclude_investigation_id)
        pattern = f"%{value}%"
        stmt = (
            select(EvidenceRecord)
            .where(
                EvidenceRecord.investigation_id.in_(inv_ids),
                or_(
                    EvidenceRecord.summary.ilike(pattern),
                    cast(EvidenceRecord.details, Text).ilike(pattern),
                ),
            )
            .order_by(EvidenceRecord.occurred_at.desc())
            .limit(limit)
        )
        return list(self.db.execute(stmt).scalars().all())
