"""Bounded FACT-only Investigation graph projection.

The graph is a read model over persisted canonical records.  It never writes,
infers, or expands relationships; layout is deliberately left to the browser.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.modules.evidence.infrastructure.models import Entity, EntityRelationship, EvidenceItem, Indicator, IndicatorOccurrence
from app.modules.investigations.domain.service import InvestigationService
from app.shared.exceptions import NotFoundError, ValidationError

GRAPH_POLICY_ID = "canonical-graph-v1"


@dataclass(frozen=True)
class GraphPolicy:
    max_nodes: int = 200
    max_edges: int = 100
    max_support_references_per_edge: int = 20
    max_text: int = 255


@dataclass(frozen=True)
class GraphFilters:
    entity_type: str | None = None
    relationship_type: str | None = None
    evidence_id: UUID | None = None


def _safe_text(value: str | None, maximum: int) -> str:
    """Bound persisted labels without interpreting markup or metadata."""
    text = "" if value is None else "".join(char for char in str(value) if char >= " ")
    return text[:maximum]


class CanonicalGraphProjectionService:
    def __init__(self, db: Session, policy: GraphPolicy = GraphPolicy()):
        self.db = db
        self.policy = policy

    def project(self, org_id: UUID, investigation_id: UUID, filters: GraphFilters) -> dict:
        InvestigationService(self.db).get_investigation(org_id, investigation_id)
        self._validate_filters(org_id, investigation_id, filters)
        entity_type = filters.entity_type.lower() if filters.entity_type else None

        entity_stmt = select(Entity).options(selectinload(Entity.observations)).where(
            Entity.org_id == org_id, Entity.investigation_id == investigation_id
        )
        if entity_type:
            entity_stmt = entity_stmt.where(Entity.type == entity_type)
        entity_count = self.db.scalar(select(func.count()).select_from(entity_stmt.subquery())) or 0
        entities = list(self.db.scalars(entity_stmt.order_by(Entity.type, Entity.canonical_value, Entity.id).limit(self.policy.max_nodes)))

        remaining_nodes = max(0, self.policy.max_nodes - len(entities))
        occurrence_exists = select(IndicatorOccurrence.id).where(
            IndicatorOccurrence.org_id == org_id,
            IndicatorOccurrence.investigation_id == investigation_id,
            IndicatorOccurrence.indicator_id == Indicator.id,
        ).exists()
        indicator_stmt = select(Indicator).where(Indicator.org_id == org_id, occurrence_exists)
        indicator_count = self.db.scalar(select(func.count()).select_from(indicator_stmt.subquery())) or 0
        indicators = list(self.db.scalars(indicator_stmt.order_by(Indicator.type, Indicator.normalized_value, Indicator.id).limit(remaining_nodes)))
        entity_ids = {entity.id for entity in entities}

        relationships: list[EntityRelationship] = []
        if entity_ids:
            relationship_stmt = select(EntityRelationship).where(
                EntityRelationship.org_id == org_id,
                EntityRelationship.investigation_id == investigation_id,
                EntityRelationship.source_entity_id.in_(entity_ids),
                EntityRelationship.target_entity_id.in_(entity_ids),
            )
            if filters.relationship_type:
                relationship_stmt = relationship_stmt.where(EntityRelationship.relationship_type == filters.relationship_type)
            if filters.evidence_id:
                relationship_stmt = relationship_stmt.where(EntityRelationship.evidence_id == filters.evidence_id)
            group_count = self.db.scalar(select(func.count()).select_from(
                relationship_stmt.with_only_columns(
                    EntityRelationship.source_entity_id,
                    EntityRelationship.target_entity_id,
                    EntityRelationship.relationship_type,
                ).distinct().subquery()
            )) or 0
            relationships = list(self.db.scalars(relationship_stmt.order_by(
                EntityRelationship.source_entity_id,
                EntityRelationship.target_entity_id,
                EntityRelationship.relationship_type,
                EntityRelationship.observed_at.nulls_last(),
                EntityRelationship.id,
            ).limit(self.policy.max_edges * self.policy.max_support_references_per_edge)))

        return build_canonical_graph(
            investigation_id, entities, indicators, relationships,
            policy=self.policy,
            omitted_nodes=max(0, entity_count + indicator_count - len(entities) - len(indicators)),
            expected_edge_count=group_count if entity_ids else 0,
        )

    def _validate_filters(self, org_id: UUID, investigation_id: UUID, filters: GraphFilters) -> None:
        if filters.evidence_id and not self.db.scalar(select(EvidenceItem.id).where(
            EvidenceItem.id == filters.evidence_id,
            EvidenceItem.org_id == org_id,
            EvidenceItem.investigation_id == investigation_id,
        )):
            raise NotFoundError("Graph not found.")
        entity_type = filters.entity_type.lower() if filters.entity_type else None
        if entity_type and not self.db.scalar(select(Entity.id).where(
            Entity.org_id == org_id, Entity.investigation_id == investigation_id, Entity.type == entity_type,
        ).limit(1)):
            raise ValidationError("Unsupported graph filter.")
        if filters.relationship_type and not self.db.scalar(select(EntityRelationship.id).where(
            EntityRelationship.org_id == org_id,
            EntityRelationship.investigation_id == investigation_id,
            EntityRelationship.relationship_type == filters.relationship_type,
        ).limit(1)):
            raise ValidationError("Unsupported graph filter.")


def build_canonical_graph(
    investigation_id: UUID,
    entities: list,
    indicators: list,
    relationships: list,
    *,
    policy: GraphPolicy = GraphPolicy(),
    omitted_nodes: int = 0,
    expected_edge_count: int | None = None,
) -> dict:
    """Pure bounded aggregation helper used by the database service and tests."""
    entities = sorted(entities, key=lambda entity: (str(entity.type), str(entity.canonical_value), str(entity.id)))[:policy.max_nodes]
    indicators = sorted(indicators, key=lambda indicator: (str(indicator.type), str(indicator.normalized_value), str(indicator.id)))[:max(0, policy.max_nodes - len(entities))]
    entity_ids = {entity.id for entity in entities}
    nodes = [
        {
            "id": f"entity:{entity.id}", "type": _safe_text(entity.type.upper(), 50),
            "label": _safe_text(entity.display_name, policy.max_text),
            "canonical_value": _safe_text(entity.canonical_value, policy.max_text),
            "observation_count": len(getattr(entity, "observations", ())),
            "first_seen_at": entity.first_seen_at, "last_seen_at": entity.last_seen_at,
            "status": "FACT",
        }
        for entity in entities
    ]
    nodes.extend(
        {
            "id": f"indicator:{indicator.id}", "type": "INDICATOR",
            "label": _safe_text(indicator.display_value or indicator.normalized_value, policy.max_text),
            "canonical_value": _safe_text(indicator.normalized_value, policy.max_text),
            "observation_count": int(getattr(indicator, "occurrence_count", 0)),
            "first_seen_at": indicator.first_seen_at, "last_seen_at": indicator.last_seen_at,
            "status": "FACT",
        }
        for indicator in indicators
    )
    nodes.sort(key=lambda node: (node["type"], node["canonical_value"] or "", node["id"]))

    grouped: dict[tuple, list] = defaultdict(list)
    for relationship in relationships:
        if relationship.source_entity_id in entity_ids and relationship.target_entity_id in entity_ids:
            grouped[(relationship.source_entity_id, relationship.target_entity_id, relationship.relationship_type)].append(relationship)
    all_groups = sorted(grouped.items(), key=lambda item: (str(item[0][0]), str(item[0][1]), item[0][2]))
    edges = []
    for (source_id, target_id, relationship_type), rows in all_groups[:policy.max_edges]:
        rows.sort(key=lambda row: (row.observed_at is None, row.observed_at, str(row.id)))
        observed = [row.observed_at for row in rows if row.observed_at is not None]
        support_rows = rows[:policy.max_support_references_per_edge]
        provenance = [
            {
                "relationship_id": str(row.id),
                "evidence_id": str(row.evidence_id) if row.evidence_id else None,
                "event_id": str(row.event_id) if row.event_id else None,
                "source_observation_id": str(row.source_observation_id) if row.source_observation_id else None,
                "target_observation_id": str(row.target_observation_id) if row.target_observation_id else None,
                "derivation_name": _safe_text(getattr(row, "derivation_name", "unknown"), 100),
                "derivation_version": _safe_text(getattr(row, "derivation_version", "unknown"), 100),
                "observed_at": row.observed_at,
                "support_status": "AVAILABLE" if (row.evidence_id or row.event_id or row.source_observation_id or row.target_observation_id) else "UNAVAILABLE",
            }
            for row in support_rows
        ]
        edges.append({
            "id": f"relationship:{source_id}:{target_id}:{relationship_type}",
            "source": f"entity:{source_id}", "target": f"entity:{target_id}",
            "relationship_type": _safe_text(relationship_type, 100),
            "observed_at": min(observed) if observed else None,
            "first_seen_at": min(observed) if observed else None,
            "last_seen_at": max(observed) if observed else None,
            "occurrence_count": len(rows), "support_omitted": max(0, len(rows) - len(support_rows)),
            "status": "FACT", "provenance": provenance,
        })
    return {
        "investigation_id": str(investigation_id), "policy_id": GRAPH_POLICY_ID,
        "nodes": nodes, "edges": edges,
        "omissions": {"nodes": omitted_nodes, "edges": max(0, (expected_edge_count if expected_edge_count is not None else len(all_groups)) - len(edges)), "reason": "POLICY_LIMIT" if omitted_nodes or (expected_edge_count if expected_edge_count is not None else len(all_groups)) > len(edges) else None},
    }
