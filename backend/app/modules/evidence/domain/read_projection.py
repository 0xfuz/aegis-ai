"""Bounded, read-only evidence inventory projections.

This module has no ingestion or parsing authority.  It projects persisted
metadata only and deliberately never selects ``RawRecord.content``.
"""
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.modules.evidence.infrastructure.models import EvidenceItem, EvidenceParseRun, Event, RawRecord
from app.modules.identity.infrastructure.models import User
from app.modules.investigations.domain.service import InvestigationService


class EvidenceInventoryService:
    def __init__(self, db: Session):
        self.db = db

    def list(self, org_id: UUID, investigation_id: UUID, limit: int, offset: int) -> dict:
        InvestigationService(self.db).get_investigation(org_id, investigation_id)
        where = (EvidenceItem.org_id == org_id, EvidenceItem.investigation_id == investigation_id)
        total = self.db.scalar(select(func.count()).select_from(EvidenceItem).where(*where)) or 0

        latest_run_id = (
            select(EvidenceParseRun.id)
            .where(EvidenceParseRun.evidence_id == EvidenceItem.id, EvidenceParseRun.org_id == org_id)
            .order_by(EvidenceParseRun.run_sequence.desc(), EvidenceParseRun.started_at.desc(), EvidenceParseRun.id.desc())
            .limit(1)
            .correlate(EvidenceItem)
            .scalar_subquery()
        )
        raw_count = select(func.count()).select_from(RawRecord).where(
            RawRecord.org_id == org_id, RawRecord.evidence_id == EvidenceItem.id
        ).correlate(EvidenceItem).scalar_subquery()
        unavailable_raw_count = select(func.count()).select_from(RawRecord).where(
            RawRecord.org_id == org_id, RawRecord.evidence_id == EvidenceItem.id, RawRecord.content.is_(None)
        ).correlate(EvidenceItem).scalar_subquery()
        event_count = select(func.count()).select_from(Event).where(
            Event.org_id == org_id, Event.evidence_id == EvidenceItem.id
        ).correlate(EvidenceItem).scalar_subquery()

        rows = self.db.execute(
            select(EvidenceItem, User, EvidenceParseRun, raw_count.label("raw_count"), unavailable_raw_count.label("unavailable_raw_count"), event_count.label("event_count"))
            .outerjoin(User, User.id == EvidenceItem.imported_by_id)
            .outerjoin(EvidenceParseRun, EvidenceParseRun.id == latest_run_id)
            .where(*where)
            .order_by(EvidenceItem.imported_at.desc(), EvidenceItem.id.desc())
            .limit(limit).offset(offset)
        ).all()
        return {
            "items": [self._item(evidence, user, run, raw_records, unavailable_raw_records, events) for evidence, user, run, raw_records, unavailable_raw_records, events in rows],
            "limit": limit, "offset": offset, "total": total,
        }

    @staticmethod
    def _item(evidence: EvidenceItem, user: User | None, run: EvidenceParseRun | None, raw_records: int, unavailable_raw_records: int, events: int) -> dict:
        warnings = run.warnings if run and isinstance(run.warnings, list) else []
        return {
            "id": evidence.id,
            "filename": evidence.original_filename[:1024],
            "detected_mime": evidence.detected_mime[:255],
            "byte_size": evidence.byte_size,
            "sha256": evidence.sha256,
            "acquisition_source": evidence.acquisition_source[:100],
            "imported_at": evidence.imported_at,
            "parsing_status": evidence.parsing_status[:20],
            "latest_parse_status": run.status[:20] if run else None,
            "parser_name": run.parser_name[:100] if run else None,
            "parser_version": run.parser_version[:100] if run else None,
            "parse_warning_count": len(warnings),
            "raw_record_count": raw_records,
            "raw_content_unavailable_count": unavailable_raw_records,
            "event_count": events,
            "importer": ({"id": user.id, "display_name": (user.full_name or user.email)[:255]} if user else None),
        }
