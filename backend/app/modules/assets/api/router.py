from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.modules.identity.api.dependencies import Principal, require_permission
from app.modules.assets.api.schemas import AssetDetail, AssetRead, AssetUpdate
from app.modules.assets.domain.service import AssetService
from app.shared.database import get_db

router = APIRouter(prefix="/assets", tags=["Assets"])


@router.get("", response_model=list[AssetRead])
def list_assets(
    principal: Principal = Depends(require_permission("investigation:read")),
    db: Session = Depends(get_db),
) -> list[AssetRead]:
    assets = AssetService(db).list_assets(principal.org_id)
    return [AssetRead.model_validate(a) for a in assets]


@router.get("/{asset_id}", response_model=AssetDetail)
def get_asset(
    asset_id: UUID,
    principal: Principal = Depends(require_permission("investigation:read")),
    db: Session = Depends(get_db),
) -> AssetDetail:
    return AssetService(db).get_asset_detail(principal.org_id, asset_id)


@router.patch("/{asset_id}", response_model=AssetRead)
def update_asset(
    asset_id: UUID,
    payload: AssetUpdate,
    principal: Principal = Depends(require_permission("investigation:write")),
    db: Session = Depends(get_db),
) -> AssetRead:
    asset = AssetService(db).update_asset(principal.org_id, asset_id, payload)
    db.commit()
    return AssetRead.model_validate(asset)
