"""Read-only bounded canonical Timeline projection.

Ordering is source Event.timestamp normalized to UTC, ascending, with Event.id
as the stable tie-breaker. Missing source timestamps are explicitly
unavailable and sort last. Range filters are UTC ``[from, to)`` and never use
the server wall clock as an implicit bound.
"""
from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.modules.evidence.infrastructure.models import Event, EvidenceItem, RawRecord
from app.modules.investigations.domain.service import InvestigationService
from app.shared.exceptions import NotFoundError, ValidationError

_MAX_RANGE = timedelta(days=90)


class TimelineProjectionService:
    def __init__(self, db: Session):
        self.db = db

    def list(self, org_id: UUID, investigation_id: UUID, *, limit: int, offset: int,
             from_at: datetime | None, to_at: datetime | None, evidence_id: UUID | None) -> dict:
        InvestigationService(self.db).get_investigation(org_id, investigation_id)
        from_at, to_at = self._range(from_at, to_at)
        if evidence_id is not None:
            found = self.db.scalar(select(EvidenceItem.id).where(
                EvidenceItem.id == evidence_id, EvidenceItem.org_id == org_id,
                EvidenceItem.investigation_id == investigation_id,
            ))
            if found is None:
                raise NotFoundError("Evidence not found.")

        where = [Event.org_id == org_id, Event.investigation_id == investigation_id]
        if evidence_id is not None:
            where.append(Event.evidence_id == evidence_id)
        if from_at is not None:
            where.extend((Event.timestamp >= from_at, Event.timestamp < to_at))

        total = self.db.scalar(select(func.count()).select_from(Event).where(*where)) or 0
        rows = self.db.execute(
            select(Event, EvidenceItem, RawRecord)
            .join(EvidenceItem, EvidenceItem.id == Event.evidence_id)
            .join(RawRecord, RawRecord.id == Event.raw_record_id)
            .where(*where)
            .order_by(Event.timestamp.asc().nulls_last(), Event.id.asc())
            .limit(limit).offset(offset)
        ).all()
        return {"items": [self._item(event, evidence, raw) for event, evidence, raw in rows],
                "limit": limit, "offset": offset, "returned_count": len(rows), "total": total}

    @staticmethod
    def _range(from_at: datetime | None, to_at: datetime | None) -> tuple[datetime | None, datetime | None]:
        if (from_at is None) != (to_at is None):
            raise ValidationError("Both timeline range boundaries are required.")
        if from_at is None:
            return None, None
        if from_at.tzinfo is None or from_at.utcoffset() is None or to_at.tzinfo is None or to_at.utcoffset() is None:
            raise ValidationError("Timeline range timestamps must include a timezone.")
        start, end = from_at.astimezone(timezone.utc), to_at.astimezone(timezone.utc)
        if start >= end:
            raise ValidationError("Timeline range start must precede its end.")
        if end - start > _MAX_RANGE:
            raise ValidationError("Timeline range must not exceed 90 days.")
        return start, end

    @staticmethod
    def _item(event: Event, evidence: EvidenceItem, raw: RawRecord) -> dict:
        if evidence.parsing_status == "failed":
            provenance = "PARSER_FAILED"
        elif raw.content is None and raw.content_locator is None:
            provenance = "RAW_UNAVAILABLE"
        elif raw.content is None:
            provenance = "RAW_CONTENT_UNAVAILABLE"
        elif raw.content_locator is None:
            provenance = "RAW_LOCATOR_UNAVAILABLE"
        else:
            provenance = "AVAILABLE"
        return {
            "id": event.id, "timestamp": event.timestamp.astimezone(timezone.utc) if event.timestamp else None,
            "time_basis": "SOURCE_EVENT_TIMESTAMP" if event.timestamp else "UNAVAILABLE",
            "event_type": event.event_type, "source": event.source, "host": event.host, "user": event.user,
            "source_ip": event.source_ip, "destination_ip": event.destination_ip,
            "deterministic_severity": event.deterministic_severity,
            "evidence": {"id": evidence.id, "filename": evidence.original_filename[:1024]},
            "raw_content_available": raw.content is not None,
            "raw_locator_available": raw.content_locator is not None,
            "provenance_status": provenance,
        }
