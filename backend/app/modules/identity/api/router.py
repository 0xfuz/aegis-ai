from uuid import UUID

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.modules.identity.api.dependencies import Principal, get_current_principal, require_any_role
from app.modules.identity.api.schemas import (
    LoginRequest,
    PasswordRotationRequest,
    RefreshRequest,
    TokenResponse,
    UserInvite,
    UserRead,
    UserUpdateRole,
)
from app.modules.identity.domain.service import AuthService, UserService
from app.shared.database import get_db

settings = get_settings()

auth_router = APIRouter(prefix="/auth", tags=["Authentication"])
users_router = APIRouter(prefix="/users", tags=["User Management"])


@auth_router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest, db: Session = Depends(get_db)) -> TokenResponse:
    """Authenticate with email + password and receive an access/refresh
    token pair. The access token is a short-lived JWT carrying the caller's
    role and flattened permission list, so downstream services never need
    a DB round trip to authorize a request."""
    access, refresh, rotation_required = AuthService(db).authenticate(payload.email, payload.password)
    db.commit()
    return TokenResponse(
        access_token=access,
        refresh_token=refresh,
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        password_rotation_required=rotation_required,
    )


@auth_router.post("/refresh", response_model=TokenResponse)
def refresh_token(payload: RefreshRequest, db: Session = Depends(get_db)) -> TokenResponse:
    """Exchange a valid refresh token for a new access/refresh pair. The
    presented refresh token is revoked as part of this call (rotation)."""
    access, refresh, rotation_required = AuthService(db).refresh(payload.refresh_token)
    db.commit()
    return TokenResponse(
        access_token=access,
        refresh_token=refresh,
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        password_rotation_required=rotation_required,
    )


@auth_router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(payload: RefreshRequest, db: Session = Depends(get_db)) -> None:
    """Revoke a refresh token so it can no longer be used to mint new
    access tokens. Idempotent — logging out twice is not an error."""
    AuthService(db).logout(payload.refresh_token)
    db.commit()


@auth_router.get("/me", response_model=UserRead)
def get_me(
    principal: Principal = Depends(get_current_principal),
    db: Session = Depends(get_db),
) -> UserRead:
    user = UserService(db).get_current_user(principal.user_id)
    return UserRead.model_validate(user)


@auth_router.post("/password/rotate", status_code=status.HTTP_204_NO_CONTENT)
def rotate_password(payload: PasswordRotationRequest, principal: Principal = Depends(get_current_principal), db: Session = Depends(get_db)) -> None:
    UserService(db).rotate_own_password(principal.user_id, payload.current_password, payload.new_password)
    db.commit()


@users_router.get("", response_model=list[UserRead])
def list_users(
    principal: Principal = Depends(require_any_role("admin", "ciso")),
    db: Session = Depends(get_db),
) -> list[UserRead]:
    users = UserService(db).list_org_users(principal.org_id)
    return [UserRead.model_validate(u) for u in users]


@users_router.post("", response_model=UserRead, status_code=status.HTTP_201_CREATED)
def invite_user(
    payload: UserInvite,
    principal: Principal = Depends(require_any_role("admin")),
    db: Session = Depends(get_db),
) -> UserRead:
    # MVP: a temporary password is generated and would be emailed via the
    # (not-yet-built) notification service; for local dev it's returned in
    # a plaintext dev-only field so the flow is testable end-to-end.
    import secrets

    temp_password = secrets.token_urlsafe(12)
    user = UserService(db).invite_user(
        principal.org_id, payload.email, payload.full_name, payload.role_name, temp_password
    )
    db.commit()
    return UserRead.model_validate(user)


@users_router.patch("/{user_id}/role", response_model=UserRead)
def update_user_role(
    user_id: UUID,
    payload: UserUpdateRole,
    principal: Principal = Depends(require_any_role("admin")),
    db: Session = Depends(get_db),
) -> UserRead:
    user = UserService(db).update_role(principal.org_id, user_id, payload.role_name)
    db.commit()
    return UserRead.model_validate(user)


@users_router.post("/{user_id}/deactivate", response_model=UserRead)
def deactivate_user(
    user_id: UUID,
    principal: Principal = Depends(require_any_role("admin")),
    db: Session = Depends(get_db),
) -> UserRead:
    user = UserService(db).deactivate(principal.org_id, user_id)
    db.commit()
    return UserRead.model_validate(user)


@users_router.post("/{user_id}/reactivate", response_model=UserRead)
def reactivate_user(
    user_id: UUID,
    principal: Principal = Depends(require_any_role("admin")),
    db: Session = Depends(get_db),
) -> UserRead:
    user = UserService(db).reactivate(principal.org_id, user_id)
    db.commit()
    return UserRead.model_validate(user)
