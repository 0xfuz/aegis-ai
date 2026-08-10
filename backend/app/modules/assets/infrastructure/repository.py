from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.modules.assets.infrastructure.models import Asset
from app.modules.investigations.infrastructure.models import Evidence, Investigation, TimelineEvent


class AssetRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_by_id(self, org_id: UUID, asset_id: UUID) -> Asset | None:
        stmt = select(Asset).where(Asset.id == asset_id, Asset.org_id == org_id)
        return self.db.execute(stmt).scalar_one_or_none()

    def get_by_name(self, org_id: UUID, name: str) -> Asset | None:
        stmt = select(Asset).where(Asset.org_id == org_id, Asset.name == name)
        return self.db.execute(stmt).scalar_one_or_none()

    def list_by_org(self, org_id: UUID) -> list[Asset]:
        stmt = select(Asset).where(Asset.org_id == org_id).order_by(Asset.risk_score.desc())
        return list(self.db.execute(stmt).scalars().all())

    def create(self, asset: Asset) -> Asset:
        self.db.add(asset)
        self.db.flush()
        return asset

    def save(self, asset: Asset) -> Asset:
        self.db.flush()
        return asset

    def record_mention(self, org_id: UUID, name: str, seen_at: datetime | None = None) -> Asset:
        """Same upsert pattern as IOCRepository.record_sighting: the
        first time an investigation mentions this asset name, a bare
        registry entry is created (unknown health, medium criticality —
        honest defaults, not invented risk data); every mention after
        that just bumps last_seen. Manual/seed enrichment (criticality,
        vulnerabilities, etc.) is layered on top via save(), same as
        IOC.set_enrichment."""
        seen_at = seen_at or datetime.now(timezone.utc)
        asset = self.get_by_name(org_id, name)
        if asset is None:
            asset = Asset(org_id=org_id, name=name, last_seen=seen_at)
            self.db.add(asset)
        elif seen_at > asset.last_seen:
            asset.last_seen = seen_at
        self.db.flush()
        return asset

    def find_related_investigations(self, org_id: UUID, asset_name: str) -> list[Investigation]:
        """Every investigation that ever referenced this asset, either as
        a timeline event's affected_asset or as a simple 'asset' evidence
        chip — genuinely computed, not mocked, same as IOC's related
        investigations."""
        via_events = (
            select(Investigation.id)
            .join(TimelineEvent, TimelineEvent.investigation_id == Investigation.id)
            .where(Investigation.org_id == org_id, TimelineEvent.affected_asset == asset_name)
        )
        via_evidence = (
            select(Investigation.id)
            .join(Evidence, Evidence.investigation_id == Investigation.id)
            .where(Investigation.org_id == org_id, Evidence.type == "asset", Evidence.value == asset_name)
        )
        stmt = (
            select(Investigation)
            .where(or_(Investigation.id.in_(via_events), Investigation.id.in_(via_evidence)))
            .order_by(Investigation.created_at.desc())
        )
        return list(self.db.execute(stmt).scalars().all())
