"""Bounded, read-only Entity and Indicator occurrence projections."""
from uuid import UUID

from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from app.modules.evidence.infrastructure.models import Entity, EntityObservation, Indicator, IndicatorOccurrence, RawRecord
from app.modules.investigations.domain.service import InvestigationService
from app.shared.exceptions import NotFoundError


class OccurrenceProjectionService:
    def __init__(self, db: Session):
        self.db = db

    def entities(self, org_id: UUID, investigation_id: UUID, limit: int, offset: int) -> dict:
        InvestigationService(self.db).get_investigation(org_id, investigation_id)
        available = func.sum(case((RawRecord.content.is_not(None), 1), else_=0)).label("available")
        base = select(Entity.id).where(Entity.org_id == org_id, Entity.investigation_id == investigation_id)
        total = self.db.scalar(select(func.count()).select_from(base.subquery())) or 0
        rows = self.db.execute(
            select(Entity, func.count(EntityObservation.id), func.min(EntityObservation.observed_at), func.max(EntityObservation.observed_at), func.coalesce(available, 0))
            .outerjoin(EntityObservation, EntityObservation.entity_id == Entity.id)
            .outerjoin(RawRecord, RawRecord.id == EntityObservation.raw_record_id)
            .where(Entity.org_id == org_id, Entity.investigation_id == investigation_id)
            .group_by(Entity.id)
            .order_by(Entity.type.asc(), Entity.canonical_value.asc(), Entity.id.asc()).limit(limit).offset(offset)
        ).all()
        return self._page([{"id": entity.id, "type": entity.type, "display_value": entity.display_name,
                            "observation_count": count, "first_observed_at": first, "last_observed_at": last,
                            "provenance_available_count": int(available_count)}
                           for entity, count, first, last, available_count in rows], limit, offset, total)

    def entity_observations(self, org_id: UUID, investigation_id: UUID, entity_id: UUID, limit: int, offset: int) -> dict:
        entity = self.db.scalar(select(Entity.id).where(Entity.id == entity_id, Entity.org_id == org_id, Entity.investigation_id == investigation_id))
        if entity is None:
            raise NotFoundError("Entity not found.")
        where = (EntityObservation.org_id == org_id, EntityObservation.investigation_id == investigation_id, EntityObservation.entity_id == entity_id)
        total = self.db.scalar(select(func.count()).select_from(EntityObservation).where(*where)) or 0
        rows = self.db.execute(select(EntityObservation, RawRecord).join(RawRecord, RawRecord.id == EntityObservation.raw_record_id).where(*where).order_by(EntityObservation.observed_at.asc().nulls_last(), EntityObservation.id.asc()).limit(limit).offset(offset)).all()
        return self._page([self._observation(row, raw) for row, raw in rows], limit, offset, total)

    def indicators(self, org_id: UUID, investigation_id: UUID, limit: int, offset: int) -> dict:
        InvestigationService(self.db).get_investigation(org_id, investigation_id)
        where = (IndicatorOccurrence.org_id == org_id, IndicatorOccurrence.investigation_id == investigation_id)
        total = self.db.scalar(select(func.count()).select_from(IndicatorOccurrence).where(*where)) or 0
        rows = self.db.execute(select(IndicatorOccurrence, Indicator, RawRecord).join(Indicator, Indicator.id == IndicatorOccurrence.indicator_id).join(RawRecord, RawRecord.id == IndicatorOccurrence.raw_record_id).where(*where).order_by(IndicatorOccurrence.observed_at.asc().nulls_last(), IndicatorOccurrence.id.asc()).limit(limit).offset(offset)).all()
        return self._page([{"id": occurrence.id, "indicator_id": indicator.id, "type": indicator.type,
                            "canonical_value": indicator.display_value or indicator.normalized_value,
                            "observed_at": occurrence.observed_at, "extractor_name": occurrence.extractor_name,
                            "extractor_version": occurrence.extractor_version, "evidence_id": occurrence.evidence_id,
                            "raw_record_id": occurrence.raw_record_id, "event_id": occurrence.event_id,
                            "provenance_status": self._status(raw)} for occurrence, indicator, raw in rows], limit, offset, total)

    @classmethod
    def _observation(cls, observation: EntityObservation, raw: RawRecord) -> dict:
        return {"id": observation.id, "observed_at": observation.observed_at, "extractor_name": observation.extractor_name,
                "extractor_version": observation.extractor_version, "evidence_id": observation.evidence_id,
                "raw_record_id": observation.raw_record_id, "event_id": observation.event_id,
                "provenance_status": cls._status(raw)}

    @staticmethod
    def _status(raw: RawRecord) -> str:
        if raw.content is None:
            return "RAW_CONTENT_UNAVAILABLE"
        if raw.content_locator is None:
            return "RAW_LOCATOR_UNAVAILABLE"
        return "AVAILABLE"

    @staticmethod
    def _page(items: list[dict], limit: int, offset: int, total: int) -> dict:
        return {"items": items, "limit": limit, "offset": offset, "returned_count": len(items), "total": total}
