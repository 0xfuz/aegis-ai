"""
Application services for the investigations module. Routers call these —
never the repository or DB session directly.
"""
from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.modules.investigations.infrastructure.models import (
    ActionStatus,
    Investigation,
    InvestigationStatus,
    Note,
    Severity,
)
from app.modules.investigations.infrastructure.repository import InvestigationRepository, IOCRepository
from app.modules.investigations.api.schemas import (
    DashboardSummary,
    DashboardWindowRead,
    EvidenceRecordRead,
    IOCDetail,
    RelatedInvestigation,
)
from app.shared.exceptions import NotFoundError, ValidationError

_VALID_IOC_TYPES = {"ip", "hash", "domain", "url", "asset"}
_VALID_IOC_VERDICTS = {"malicious", "suspicious", "unknown", "benign"}
_DASHBOARD_PRESETS = {"24h": timedelta(hours=24), "7d": timedelta(days=7), "30d": timedelta(days=30)}
_MAX_DASHBOARD_RANGE = timedelta(days=90)

# Valid forward/backward moves on the Case Status Track. Kept explicit
# rather than allowing any-to-any status changes, since the UX spec's
# Case Status Track is meant to represent a real workflow, not a free-form
# label.
_VALID_TRANSITIONS: dict[InvestigationStatus, set[InvestigationStatus]] = {
    InvestigationStatus.NEW: {InvestigationStatus.TRIAGING},
    InvestigationStatus.TRIAGING: {InvestigationStatus.INVESTIGATING, InvestigationStatus.NEW},
    InvestigationStatus.INVESTIGATING: {InvestigationStatus.CONTAINED, InvestigationStatus.TRIAGING},
    InvestigationStatus.CONTAINED: {InvestigationStatus.RESOLVED, InvestigationStatus.INVESTIGATING},
    InvestigationStatus.RESOLVED: set(),
}


class InvestigationService:
    def __init__(self, db: Session):
        self.db = db
        self.repo = InvestigationRepository(db)

    def list_investigations(self, org_id: UUID, status: str | None, limit: int, offset: int) -> dict:
        status_enum = self._parse_status(status) if status is not None else None
        items = self.repo.list_by_org(org_id, status=status_enum, limit=limit, offset=offset)
        return {"items": items, "limit": limit, "offset": offset, "returned_count": len(items),
                "total": self.repo.count_by_org(org_id, status=status_enum)}

    def get_investigation(self, org_id: UUID, investigation_id: UUID) -> Investigation:
        investigation = self.repo.get_by_id(org_id, investigation_id)
        if investigation is None:
            raise NotFoundError("Investigation not found.")
        return investigation

    def create_alert_promotion_investigation(self, org_id: UUID, title: str, severity: Severity) -> Investigation:
        """Create a normal investigation for an explicitly approved alert promotion."""
        investigation = Investigation(
            org_id=org_id, title=title, source="Alert Cluster Promotion", severity=severity,
            status=InvestigationStatus.NEW, confidence=0, false_positive_probability=0,
        )
        self.repo.create(investigation)
        self.db.flush()
        return investigation

    def update_status(self, org_id: UUID, investigation_id: UUID, new_status: str) -> Investigation:
        investigation = self.get_investigation(org_id, investigation_id)
        new_status_enum = self._parse_status(new_status)

        allowed = _VALID_TRANSITIONS.get(investigation.status, set())
        if new_status_enum not in allowed:
            raise ValidationError(
                f"Can't move an investigation from '{investigation.status.value}' to "
                f"'{new_status_enum.value}'. Valid next steps: "
                f"{', '.join(s.value for s in allowed) or 'none — this case is closed'}."
            )

        investigation.status = new_status_enum
        return self.repo.save(investigation)

    def add_note(self, org_id: UUID, investigation_id: UUID, author_id: UUID, body: str) -> Note:
        investigation = self.get_investigation(org_id, investigation_id)
        note = Note(investigation_id=investigation.id, author_id=author_id, body=body)
        self.repo.add_note(note)
        self.db.flush()
        return note

    def list_notes(self, org_id: UUID, investigation_id: UUID, limit: int, offset: int) -> dict:
        self.get_investigation(org_id, investigation_id)
        where = (Note.investigation_id == investigation_id,)
        total = self.db.scalar(select(func.count()).select_from(Note).where(*where)) or 0
        rows = self.db.scalars(
            select(Note).where(*where).order_by(Note.created_at.desc(), Note.id.desc()).limit(limit).offset(offset)
        )
        return {
            "items": [{"id": str(note.id), "author_id": str(note.author_id), "body": note.body[:4000],
                       "created_at": note.created_at, "updated_at": note.updated_at} for note in rows],
            "limit": limit, "offset": offset, "total": total,
        }

    def decide_action(self, org_id: UUID, action_id: UUID, approve: bool) -> Investigation:
        action = self.repo.get_action(org_id, action_id)
        if action is None:
            raise NotFoundError("Recommended action not found.")

        # Human-in-the-loop by design (see architecture doc §4): this endpoint
        # only ever flips a status flag. No connector call, no external
        # system state change happens here or anywhere else in v1 — there
        # are no connectors yet. Wiring an actual containment action to this
        # decision is explicitly a v2 concern once real connectors exist.
        action.status = ActionStatus.APPROVED if approve else ActionStatus.DISMISSED
        self.db.flush()
        return self.get_investigation(org_id, action.investigation_id)

    @staticmethod
    def resolve_dashboard_window(
        preset: str | None, from_at: datetime | None, to_at: datetime | None, now: datetime | None = None
    ) -> DashboardWindowRead | None:
        if preset and (from_at is not None or to_at is not None):
            raise ValidationError("A preset cannot be combined with a custom range.")
        if preset:
            duration = _DASHBOARD_PRESETS.get(preset)
            if duration is None:
                raise ValidationError("Unsupported dashboard window preset.")
            end = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
            return DashboardWindowRead(preset=preset, from_at=end - duration, to_at=end)
        if (from_at is None) != (to_at is None):
            raise ValidationError("Both custom range boundaries are required.")
        if from_at is None:
            return None
        if from_at.tzinfo is None or from_at.utcoffset() is None or to_at.tzinfo is None or to_at.utcoffset() is None:
            raise ValidationError("Dashboard range timestamps must include a timezone.")
        start, end = from_at.astimezone(timezone.utc), to_at.astimezone(timezone.utc)
        if start > end:
            raise ValidationError("Dashboard range start must not be later than its end.")
        if end - start > _MAX_DASHBOARD_RANGE:
            raise ValidationError("Dashboard range must not exceed 90 days.")
        return DashboardWindowRead(from_at=start, to_at=end)

    def dashboard_summary(self, org_id: UUID, window: DashboardWindowRead | None = None) -> DashboardSummary:
        from_at = window.from_at if window else None
        to_at = window.to_at if window else None
        return DashboardSummary(
            open_investigations=self.repo.count_open(org_id, from_at, to_at),
            critical_open=self.repo.count_critical_open(org_id, from_at, to_at),
            avg_false_positive_probability=round(self.repo.avg_false_positive_probability(org_id, from_at, to_at), 1),
            total_investigations=self.repo.count_by_org(org_id, from_at=from_at, to_at=to_at),
            window=window,
        )

    @staticmethod
    def _parse_status(status: str) -> InvestigationStatus:
        try:
            return InvestigationStatus(status)
        except ValueError as exc:
            valid = ", ".join(s.value for s in InvestigationStatus)
            raise ValidationError(f"Invalid status '{status}'. Valid values: {valid}.") from exc


class IOCService:
    def __init__(self, db: Session):
        self.db = db
        self.repo = IOCRepository(db)

    def list_iocs(self, org_id: UUID, verdict: str | None = None, watched_only: bool = False) -> list:
        if verdict is not None:
            self._validate_verdict(verdict)
        return self.repo.list_by_org(org_id, verdict=verdict, watched_only=watched_only)

    def list_watchlist(self, org_id: UUID) -> list:
        return self.repo.list_watched(org_id)

    def get_ioc_detail(
        self, org_id: UUID, ioc_type: str, value: str, exclude_investigation_id: UUID | None = None
    ) -> IOCDetail:
        self._validate_type(ioc_type)
        ioc = self.repo.get_by_value(org_id, ioc_type, value)
        related = self.repo.find_investigations_with_value(org_id, ioc_type, value, exclude_investigation_id)
        related_assets = self.repo.find_related_asset_names(org_id, ioc_type, value, exclude_investigation_id)
        related_evidence = self.repo.find_related_evidence_records(
            org_id, ioc_type, value, exclude_investigation_id
        )

        # An indicator can appear as Evidence without ever having been
        # explicitly recorded through record_sighting() (e.g. evidence
        # seeded before this feature existed) — rather than 404 in that
        # case, return honest defaults: unenriched, unclassified, seen now.
        if ioc is None:
            now = datetime.now(timezone.utc)
            return IOCDetail(
                type=ioc_type,
                value=value,
                tags=[],
                confidence=50,
                verdict="unknown",
                provenance="internal",
                is_watched=False,
                watched_at=None,
                enrichment={},
                first_seen=now,
                last_seen=now,
                sightings_count=max(len(related), 1),
                related_investigations=[RelatedInvestigation.model_validate(inv) for inv in related],
                related_assets=related_assets,
                related_evidence=[EvidenceRecordRead.model_validate(r) for r in related_evidence],
            )

        return IOCDetail(
            type=ioc.type.value,
            value=ioc.value,
            tags=ioc.tags,
            confidence=ioc.confidence,
            verdict=ioc.verdict,
            provenance=ioc.provenance,
            is_watched=ioc.is_watched,
            watched_at=ioc.watched_at,
            enrichment=ioc.enrichment,
            first_seen=ioc.first_seen,
            last_seen=ioc.last_seen,
            sightings_count=ioc.sightings_count,
            related_investigations=[RelatedInvestigation.model_validate(inv) for inv in related],
            related_assets=related_assets,
            related_evidence=[EvidenceRecordRead.model_validate(r) for r in related_evidence],
        )

    def set_watched(self, org_id: UUID, ioc_type: str, value: str, watched: bool) -> IOCDetail:
        self._validate_type(ioc_type)
        if not value or not value.strip():
            raise ValidationError("An indicator value is required.")
        ioc = self.repo.get_or_create(org_id, ioc_type, value)
        self.repo.set_watched(ioc, watched)
        return self.get_ioc_detail(org_id, ioc_type, value)

    def set_verdict(self, org_id: UUID, ioc_type: str, value: str, verdict: str) -> IOCDetail:
        self._validate_type(ioc_type)
        self._validate_verdict(verdict)
        if not value or not value.strip():
            raise ValidationError("An indicator value is required.")
        ioc = self.repo.get_or_create(org_id, ioc_type, value)
        self.repo.set_verdict(ioc, verdict)
        return self.get_ioc_detail(org_id, ioc_type, value)

    @staticmethod
    def _validate_type(ioc_type: str) -> None:
        if ioc_type not in _VALID_IOC_TYPES:
            raise ValidationError(
                f"Invalid indicator type '{ioc_type}'. Valid values: {', '.join(sorted(_VALID_IOC_TYPES))}."
            )

    @staticmethod
    def _validate_verdict(verdict: str) -> None:
        if verdict not in _VALID_IOC_VERDICTS:
            raise ValidationError(
                f"Invalid verdict '{verdict}'. Valid values: {', '.join(sorted(_VALID_IOC_VERDICTS))}."
            )
