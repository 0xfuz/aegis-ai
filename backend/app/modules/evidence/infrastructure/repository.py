from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.evidence.infrastructure.models import (
    Entity,
    EntityRelationship,
    Event,
    EvidenceItem,
    Indicator,
    RawRecord,
    IndicatorOccurrence,
    EntityObservation,
)


class EvidenceRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_evidence(self, org_id: UUID, investigation_id: UUID, evidence_id: UUID) -> EvidenceItem | None:
        return self.db.execute(select(EvidenceItem).where(EvidenceItem.id == evidence_id, EvidenceItem.org_id == org_id, EvidenceItem.investigation_id == investigation_id)).scalar_one_or_none()

    def duplicate(self, org_id: UUID, investigation_id: UUID, sha256: str) -> EvidenceItem | None:
        return self.db.execute(select(EvidenceItem).where(EvidenceItem.org_id == org_id, EvidenceItem.investigation_id == investigation_id, EvidenceItem.sha256 == sha256)).scalar_one_or_none()

    def raw_records(self, org_id: UUID, investigation_id: UUID, evidence_id: UUID) -> list[RawRecord]:
        stmt = select(RawRecord).join(EvidenceItem).where(EvidenceItem.org_id == org_id, EvidenceItem.investigation_id == investigation_id, EvidenceItem.id == evidence_id).order_by(RawRecord.ordinal)
        return list(self.db.execute(stmt).scalars())

    def events(self, org_id: UUID, investigation_id: UUID) -> list[Event]:
        return list(self.db.execute(select(Event).where(Event.org_id == org_id, Event.investigation_id == investigation_id).order_by(Event.timestamp, Event.created_at)).scalars())

    def indicators(self, org_id: UUID, investigation_id: UUID) -> list[Indicator]:
        stmt = select(Indicator).join(Indicator.occurrences).where(Indicator.org_id == org_id, Indicator.occurrences.any(investigation_id=investigation_id)).distinct().order_by(Indicator.normalized_value)
        return list(self.db.execute(stmt).scalars())

    def entities(self, org_id: UUID, investigation_id: UUID) -> list[Entity]:
        return list(self.db.execute(select(Entity).where(Entity.org_id == org_id, Entity.investigation_id == investigation_id).order_by(Entity.type, Entity.canonical_value)).scalars())

    def relationships(self, org_id: UUID, investigation_id: UUID) -> list[EntityRelationship]:
        return list(self.db.execute(select(EntityRelationship).where(EntityRelationship.org_id == org_id, EntityRelationship.investigation_id == investigation_id).order_by(EntityRelationship.observed_at, EntityRelationship.created_at)).scalars())

    def indicator_occurrences(self, org_id: UUID, investigation_id: UUID, indicator_id: UUID) -> list[IndicatorOccurrence]:
        stmt = select(IndicatorOccurrence).where(IndicatorOccurrence.org_id == org_id, IndicatorOccurrence.investigation_id == investigation_id, IndicatorOccurrence.indicator_id == indicator_id).order_by(IndicatorOccurrence.observed_at)
        return list(self.db.execute(stmt).scalars())

    def entity_observations(self, org_id: UUID, investigation_id: UUID, entity_id: UUID) -> list[EntityObservation]:
        stmt = select(EntityObservation).where(EntityObservation.org_id == org_id, EntityObservation.investigation_id == investigation_id, EntityObservation.entity_id == entity_id).order_by(EntityObservation.observed_at)
        return list(self.db.execute(stmt).scalars())
