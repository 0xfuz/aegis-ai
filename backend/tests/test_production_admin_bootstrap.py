"""PostgreSQL coverage for the internal production-admin bootstrap boundary."""
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.core.security import decode_token, verify_password
from app.modules.evidence.infrastructure.models import AuditEvent
from app.modules.identity.api import router as identity_router
from app.modules.identity.cli import bootstrap_admin
from app.modules.identity.domain.bootstrap import ProductionAdminBootstrapService
from app.modules.identity.domain.service import AuthService, UserService
from app.modules.identity.infrastructure.models import Organization, User
from app.shared.database import SessionLocal
from app.shared.exceptions import AuthenticationError, ConflictError, ValidationError

_PASSWORD = "R1-Valid-Credential-42"
_ROTATED = "R1-Rotated-Credential-73"
_SETTINGS = SimpleNamespace(ENVIRONMENT="production", SEED_DEMO_DATA=False)


@pytest.fixture()
def db():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.rollback()
        session.close()


def _bootstrap(db, slug=None, email=None):
    suffix = uuid4().hex
    slug = slug or f"r1-{suffix}"
    email = email or f"admin-{suffix}@release.example.com"
    return ProductionAdminBootstrapService(db, environment="production", demo_seed_enabled=False).bootstrap(
        organization_name="Release Tenant", organization_slug=slug, email=email, full_name="Release Administrator", password=_PASSWORD,
    )


def _contains(value, needle):
    return needle in str(value)


def test_bootstrap_creates_one_scoped_admin_and_safe_audit_only(db, caplog):
    user_id = _bootstrap(db)
    user = db.get(User, user_id)
    audit = db.scalar(select(AuditEvent).where(AuditEvent.target_id == user_id))
    assert user is not None and user.role.name == "admin" and user.must_rotate_password and verify_password(_PASSWORD, user.hashed_password)
    assert audit.action == "PRODUCTION_ADMIN_BOOTSTRAPPED" and audit.metadata_ == {"password_rotation_required": True}
    assert not _contains((user.hashed_password, audit.metadata_, caplog.text), _PASSWORD)


def test_bootstrap_rejects_default_or_invalid_credentials_without_rows(db):
    service = ProductionAdminBootstrapService(db, environment="production", demo_seed_enabled=False)
    organizations = db.scalar(select(func.count()).select_from(Organization))
    users = db.scalar(select(func.count()).select_from(User))
    with pytest.raises(ValidationError):
        service.bootstrap(organization_name="x", organization_slug="x", email="admin@aegis.demo", full_name="x", password=_PASSWORD)
    with pytest.raises(ValidationError):
        service.bootstrap(organization_name="x", organization_slug="x", email="admin@release.example.com", full_name="x", password="password")
    assert db.scalar(select(func.count()).select_from(Organization)) == organizations
    assert db.scalar(select(func.count()).select_from(User)) == users


def test_bootstrap_repeated_or_concurrent_requests_do_not_duplicate_scope(db):
    slug, email = f"repeat-{uuid4().hex}", f"repeat-{uuid4().hex}@release.example.com"
    _bootstrap(db, slug, email)
    with pytest.raises(ConflictError):
        _bootstrap(db, slug, email)
    assert db.scalar(select(func.count()).select_from(Organization).where(Organization.slug == slug)) == 1
    assert db.scalar(select(func.count()).select_from(User).where(User.email == email)) == 1


def test_concurrent_bootstrap_has_one_winner_and_no_duplicate_organization(db):
    slug, email = f"concurrent-{uuid4().hex}", f"admin-{uuid4().hex}@concurrent.example.com"
    barrier = Barrier(2)

    def invoke():
        session = SessionLocal()
        try:
            barrier.wait(timeout=5)
            return ProductionAdminBootstrapService(session, environment="production", demo_seed_enabled=False).bootstrap(
                organization_name="Concurrent Tenant", organization_slug=slug, email=email, full_name="Administrator", password=_PASSWORD,
            )
        except ConflictError:
            return None
        finally:
            session.close()

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _index: invoke(), range(2)))
    assert sum(result is not None for result in results) == 1
    assert db.scalar(select(func.count()).select_from(Organization).where(Organization.slug == slug)) == 1
    assert db.scalar(select(func.count()).select_from(User).where(User.email == email)) == 1


def test_bootstrap_rolls_back_organization_when_user_creation_fails(db, monkeypatch):
    service = ProductionAdminBootstrapService(db, environment="production", demo_seed_enabled=False)
    monkeypatch.setattr(service.users, "create", lambda _user: (_ for _ in ()).throw(RuntimeError("forced")))
    with pytest.raises(ValidationError):
        service.bootstrap(organization_name="Broken Tenant", organization_slug="broken-tenant", email="admin@broken.test", full_name="Administrator", password=_PASSWORD)
    assert db.scalar(select(func.count()).select_from(Organization).where(Organization.slug == "broken-tenant")) == 0


def test_production_seed_configuration_is_rejected(db):
    service = ProductionAdminBootstrapService(db, environment="production", demo_seed_enabled=True)
    with pytest.raises(ValidationError):
        service.bootstrap(organization_name="x", organization_slug="seed-rejected", email="admin@release.example.com", full_name="x", password=_PASSWORD)


def test_initial_rotation_restricts_privileged_access_then_replaces_credential(db):
    email = f"rotation-{uuid4().hex}@release.example.com"
    user_id = _bootstrap(db, email=email)
    access, _refresh, required = AuthService(db).authenticate(email, _PASSWORD)
    assert required and decode_token(access, expected_type=__import__("app.core.security", fromlist=["TokenType"]).TokenType.ACCESS).password_rotation_required
    client = TestClient(__import__("app.main", fromlist=["app"]).app)
    assert client.get("/api/v1/users", headers={"Authorization": f"Bearer {access}"}).status_code == 403
    assert client.post("/api/v1/auth/password/rotate", headers={"Authorization": f"Bearer {access}"}, json={"current_password": _PASSWORD, "new_password": _ROTATED}).status_code == 204
    db.expire_all()
    with pytest.raises(AuthenticationError):
        AuthService(db).authenticate(email, _PASSWORD)
    rotated, _refresh, required = AuthService(db).authenticate(email, _ROTATED)
    assert not required and client.get("/api/v1/users", headers={"Authorization": f"Bearer {rotated}"}).status_code == 200
    assert db.scalar(select(AuditEvent).where(AuditEvent.target_id == user_id, AuditEvent.action == "CREDENTIAL_ROTATED")) is not None


def test_rotation_cannot_target_or_modify_a_foreign_organization_user(db):
    first_id = _bootstrap(db, f"r1-first-{uuid4().hex}", f"admin-{uuid4().hex}@first.example.com")
    second_id = _bootstrap(db, f"r1-second-{uuid4().hex}", f"admin-{uuid4().hex}@second.example.com")
    second = db.get(User, second_id)
    prior_hash = second.hashed_password
    UserService(db).rotate_own_password(first_id, _PASSWORD, _ROTATED)
    db.commit()
    db.refresh(second)
    assert second.org_id != db.get(User, first_id).org_id and second.hashed_password == prior_hash and verify_password(_PASSWORD, second.hashed_password)


def test_cli_uses_secret_file_or_hidden_prompt_and_never_accepts_password_argument(db, monkeypatch, tmp_path):
    secret_file = tmp_path / "bootstrap-password"
    secret_file.write_text(_PASSWORD + "\n", encoding="utf-8")
    monkeypatch.setattr(bootstrap_admin, "get_settings", lambda: _SETTINGS)
    monkeypatch.setattr(bootstrap_admin, "SessionLocal", lambda: db)
    suffix = uuid4().hex
    args = ["--organization-name", "CLI Tenant", "--organization-slug", f"cli-{suffix}", "--email", f"admin-{suffix}@cli.example.com", "--full-name", "CLI Admin", "--password-file", str(secret_file)]
    assert bootstrap_admin.main(args) == 0
    assert "--password" not in {option for action in bootstrap_admin.parser()._actions for option in action.option_strings}
    assert bootstrap_admin.main(["--organization-name", "Prompt Tenant", "--organization-slug", f"prompt-{uuid4().hex}", "--email", f"admin-{uuid4().hex}@prompt.example.com", "--full-name", "Prompt Admin"], prompt=lambda _label: _PASSWORD) == 0


def test_no_public_bootstrap_route_exists():
    paths = {route.path for route in __import__("app.main", fromlist=["app"]).app.routes}
    assert not any("bootstrap" in path for path in paths)
