"""
The only layer in this module that touches the database — everything
about HOW a graph is constructed lives in graph_builder.py (pure,
DB-free, unit-testable). This class's entire job is: fetch the real
investigation data (reusing investigations' own repository, never a
second query path), fetch real IOC enrichment, and hand both to the
builder.
"""
from uuid import UUID

from sqlalchemy.orm import Session

from app.modules.attack_graph.domain.graph_builder import build_attack_graph
from app.modules.attack_graph.domain.graph_model import AttackGraph
from app.modules.assets.infrastructure.repository import AssetRepository
from app.modules.investigations.domain.service import InvestigationService
from app.modules.investigations.infrastructure.repository import IOCRepository


class AttackGraphService:
    def __init__(self, db: Session):
        self.db = db
        self.investigations = InvestigationService(db)
        self.iocs = IOCRepository(db)
        self.assets = AssetRepository(db)

    def build_graph(self, org_id: UUID, investigation_id: UUID) -> AttackGraph:
        investigation = self.investigations.get_investigation(org_id, investigation_id)

        def ioc_lookup(ioc_type: str, value: str) -> dict | None:
            ioc = self.iocs.get_by_value(org_id, ioc_type, value)
            if ioc is None:
                return None
            return {
                "tags": ioc.tags,
                "confidence": ioc.confidence,
                "sightings_count": ioc.sightings_count,
                "enrichment": ioc.enrichment,
                "verdict": ioc.verdict,
                "provenance": ioc.provenance,
                "is_watched": ioc.is_watched,
            }

        def asset_lookup(name: str) -> dict | None:
            asset = self.assets.get_by_name(org_id, name)
            if asset is None:
                return None
            return {
                "asset_id": str(asset.id),
                "criticality": asset.criticality,
                "health": asset.health,
                "risk_score": asset.risk_score,
                "owner": asset.owner,
            }

        return build_attack_graph(investigation, ioc_lookup=ioc_lookup, asset_lookup=asset_lookup)
