"""Canonical FACT-only investigation graph projection.

This module is a read model: it never writes a graph or infers a relationship.
Every returned edge is an aggregation of one or more EntityRelationship rows.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.evidence.infrastructure.models import Entity, EntityRelationship, Indicator
from app.modules.investigations.domain.service import InvestigationService


@dataclass(frozen=True)
class GraphFilters:
    entity_type: str | None = None
    relationship_type: str | None = None
    evidence_id: UUID | None = None
    start_at: datetime | None = None
    end_at: datetime | None = None


class CanonicalGraphProjectionService:
    def __init__(self, db: Session):
        self.db = db

    def project(self, org_id: UUID, investigation_id: UUID, filters: GraphFilters) -> dict:
        # Validates org/investigation scope even when the factual graph is empty.
        InvestigationService(self.db).get_investigation(org_id, investigation_id)
        entity_stmt = select(Entity).where(Entity.org_id == org_id, Entity.investigation_id == investigation_id)
        if filters.entity_type:
            entity_stmt = entity_stmt.where(Entity.type == filters.entity_type)
        entities = list(self.db.execute(entity_stmt).scalars())
        entity_ids = {entity.id for entity in entities}

        relationship_stmt = select(EntityRelationship).where(
            EntityRelationship.org_id == org_id,
            EntityRelationship.investigation_id == investigation_id,
        )
        if filters.relationship_type:
            relationship_stmt = relationship_stmt.where(EntityRelationship.relationship_type == filters.relationship_type)
        if filters.evidence_id:
            relationship_stmt = relationship_stmt.where(EntityRelationship.evidence_id == filters.evidence_id)
        if filters.start_at:
            relationship_stmt = relationship_stmt.where(EntityRelationship.observed_at >= filters.start_at)
        if filters.end_at:
            relationship_stmt = relationship_stmt.where(EntityRelationship.observed_at <= filters.end_at)
        relationships = [row for row in self.db.execute(relationship_stmt).scalars() if row.source_entity_id in entity_ids and row.target_entity_id in entity_ids]

        # Indicators are factual graph nodes only. No synthetic indicator edges are
        # created because EntityRelationship is the sole canonical edge source.
        indicators = list(self.db.execute(
            select(Indicator).where(
                Indicator.org_id == org_id,
                Indicator.occurrences.any(investigation_id=investigation_id),
            )
        ).scalars())
        return build_canonical_graph(investigation_id, entities, indicators, relationships)


def build_canonical_graph(investigation_id: UUID, entities: list, indicators: list, relationships: list) -> dict:
    """Pure aggregation helper used by the database service and tests."""
    nodes = [
        {
            "id": f"entity:{entity.id}", "type": entity.type.upper(), "label": entity.display_name,
            "canonical_value": entity.canonical_value, "observation_count": len(getattr(entity, "observations", [])),
            "first_seen_at": entity.first_seen_at, "last_seen_at": entity.last_seen_at,
            "status": "FACT", "metadata": entity.attributes or {},
        }
        for entity in entities
    ]
    nodes.extend(
        {
            "id": f"indicator:{indicator.id}", "type": "INDICATOR", "label": indicator.display_value or indicator.normalized_value,
            "canonical_value": indicator.normalized_value, "observation_count": indicator.occurrence_count,
            "first_seen_at": indicator.first_seen_at, "last_seen_at": indicator.last_seen_at,
            "status": "FACT", "metadata": {"indicator_type": indicator.type},
        }
        for indicator in indicators
    )

    grouped: dict[tuple, list] = defaultdict(list)
    for relationship in relationships:
        grouped[(relationship.source_entity_id, relationship.target_entity_id, relationship.relationship_type)].append(relationship)
    edges = []
    for (source_id, target_id, relationship_type), rows in sorted(grouped.items(), key=lambda item: tuple(str(part) for part in item[0])):
        observed = [row.observed_at for row in rows if row.observed_at is not None]
        provenance = [
            {
                "relationship_id": str(row.id), "evidence_id": str(row.evidence_id) if row.evidence_id else None,
                "raw_record_id": str(row.raw_record_id) if row.raw_record_id else None,
                "event_id": str(row.event_id) if row.event_id else None,
                "source_observation_id": str(row.source_observation_id) if row.source_observation_id else None,
                "target_observation_id": str(row.target_observation_id) if row.target_observation_id else None,
            }
            for row in rows
        ]
        edges.append({
            "id": f"relationship:{source_id}:{target_id}:{relationship_type}",
            "source": f"entity:{source_id}", "target": f"entity:{target_id}",
            "relationship_type": relationship_type, "observed_at": min(observed) if observed else None,
            "first_seen_at": min(observed) if observed else None, "last_seen_at": max(observed) if observed else None,
            "occurrence_count": len(rows), "confidence": None, "status": "FACT", "provenance": provenance,
        })
    return {"investigation_id": str(investigation_id), "nodes": nodes, "edges": edges}
