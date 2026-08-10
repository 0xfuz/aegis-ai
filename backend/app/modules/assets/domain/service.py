from uuid import UUID

from sqlalchemy.orm import Session

from app.modules.assets.api.schemas import AssetDetail, AssetUpdate, RelatedInvestigationSummary
from app.modules.assets.infrastructure.repository import AssetRepository
from app.shared.exceptions import NotFoundError


class AssetService:
    def __init__(self, db: Session):
        self.db = db
        self.repo = AssetRepository(db)

    def list_assets(self, org_id: UUID):
        return self.repo.list_by_org(org_id)

    def get_asset_detail(self, org_id: UUID, asset_id: UUID) -> AssetDetail:
        asset = self.repo.get_by_id(org_id, asset_id)
        if asset is None:
            raise NotFoundError("Asset not found.")
        related = self.repo.find_related_investigations(org_id, asset.name)
        return AssetDetail(
            id=asset.id,
            name=asset.name,
            asset_type=asset.asset_type,
            os=asset.os,
            owner=asset.owner,
            department=asset.department,
            criticality=asset.criticality,
            health=asset.health,
            risk_score=asset.risk_score,
            last_seen=asset.last_seen,
            open_vulnerabilities=asset.open_vulnerabilities,
            installed_software=asset.installed_software,
            running_services=asset.running_services,
            security_controls=asset.security_controls,
            cloud_tags=asset.cloud_tags,
            ai_risk_summary=asset.ai_risk_summary,
            related_investigations=[RelatedInvestigationSummary.model_validate(inv) for inv in related],
        )

    def update_asset(self, org_id: UUID, asset_id: UUID, payload: AssetUpdate):
        asset = self.repo.get_by_id(org_id, asset_id)
        if asset is None:
            raise NotFoundError("Asset not found.")
        updates = payload.model_dump(exclude_unset=True)
        for field, value in updates.items():
            setattr(asset, field, value)
        return self.repo.save(asset)
