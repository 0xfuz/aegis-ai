"""
FastAPI dependency-injection wiring for auth/RBAC. Every protected router in
every module imports `get_current_principal` and, where an action is
sensitive, `require_permission(...)` — this is the single choke point for
"is this request allowed to do this."
"""
from dataclasses import dataclass
from uuid import UUID

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.security import InvalidTokenError, TokenType, decode_token

_bearer_scheme = HTTPBearer(auto_error=True)


@dataclass(frozen=True)
class Principal:
    """The authenticated caller, as derived from a validated access token.
    Deliberately NOT a full User ORM object — routers that need more than
    identity/role/permissions should fetch the User explicitly via
    UserService, keeping this dependency fast and DB-free."""

    user_id: UUID
    org_id: UUID
    role: str
    permissions: frozenset[str]
    password_rotation_required: bool

    def has_permission(self, code: str) -> bool:
        return code in self.permissions


def get_current_principal(
    credentials: HTTPAuthorizationCredentials = Depends(_bearer_scheme),
) -> Principal:
    try:
        payload = decode_token(credentials.credentials, expected_type=TokenType.ACCESS)
    except InvalidTokenError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Your session has expired. Please sign in again.",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc

    if payload.org_id is None or payload.role is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Malformed access token.")

    return Principal(
        user_id=UUID(payload.user_id),
        org_id=UUID(payload.org_id),
        role=payload.role,
        permissions=frozenset(payload.permissions),
        password_rotation_required=payload.password_rotation_required,
    )


def require_password_rotation_complete(principal: Principal = Depends(get_current_principal)) -> Principal:
    if principal.password_rotation_required:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Password rotation is required before privileged access.")
    return principal


def require_permission(permission_code: str):
    """Usage: `Depends(require_permission("investigation:approve_remediation"))`"""

    def _check(principal: Principal = Depends(require_password_rotation_complete)) -> Principal:
        if not principal.has_permission(permission_code):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"This action requires the '{permission_code}' permission.",
            )
        return principal

    return _check


def require_any_role(*role_names: str):
    """Coarser guard for pages that gate on role rather than a specific
    permission (e.g. the User Management page is admin-only)."""

    def _check(principal: Principal = Depends(require_password_rotation_complete)) -> Principal:
        if principal.role not in role_names:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Your role does not have access to this resource.",
            )
        return principal

    return _check
