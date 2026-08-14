from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.modules.identity.api.dependencies import Principal, require_password_rotation_complete
from app.modules.investigations.domain.service import InvestigationService
from app.modules.reporting.domain.service import ReportService
from app.shared.database import get_db

router = APIRouter(prefix="/investigations", tags=["Reporting"])

# type -> required permission. Technical reports are available to a wider
# set of roles (incident_responder, security_architect) than executive
# reports (ciso-and-up) — see the role/permission map in seed_data.py.
_REQUIRED_PERMISSION = {
    "executive": "reports:generate_executive",
    "technical": "reports:generate_technical",
}


@router.get("/{investigation_id}/report")
def generate_report(
    investigation_id: UUID,
    type: str = Query(default="technical", description="'executive' or 'technical'"),
    format: str = Query(default="markdown", description="'markdown' or 'pdf'"),
    principal: Principal = Depends(require_password_rotation_complete),
    db: Session = Depends(get_db),
) -> Response:
    required_permission = _REQUIRED_PERMISSION.get(type, "reports:generate_technical")
    if not principal.has_permission(required_permission):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"This action requires the '{required_permission}' permission.",
        )

    investigation = InvestigationService(db).get_investigation(principal.org_id, investigation_id)
    content, media_type, filename = ReportService().generate(investigation, type, format)

    return Response(
        content=content,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
