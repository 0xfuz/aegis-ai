"""PostgreSQL coverage for the internal operator password recovery boundary."""
from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy import select

from app.core.security import verify_password
from app.modules.evidence.infrastructure.models import AuditEvent
from app.modules.identity.cli import reset_admin_password
from app.modules.identity.domain.bootstrap import ProductionAdminBootstrapService, ProductionAdminPasswordRecoveryService
from app.modules.identity.infrastructure.models import Role, User
from app.shared.database import SessionLocal
from app.shared.exceptions import NotFoundError, ValidationError

OLD = "Old-Operator-Password-42"
NEW = "New-Operator-Password-73"
SETTINGS = SimpleNamespace(ENVIRONMENT="production", DEBUG=False, SEED_DEMO_DATA=False)


@pytest.fixture()
def db():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.rollback(); session.close()


def provision(db, *, slug=None, email=None):
    suffix = uuid4().hex
    slug, email = slug or f"recovery-{suffix}", email or f"admin-{suffix}@recovery.example.com"
    user_id = ProductionAdminBootstrapService(db, environment="production", demo_seed_enabled=False).bootstrap(
        organization_name="Recovery Tenant", organization_slug=slug, email=email, full_name="Recovery Admin", password=OLD,
    )
    db.get(User, user_id).must_rotate_password = False; db.commit()
    return slug, email, user_id


def test_recovery_updates_one_scoped_admin_and_writes_safe_audit(db, caplog):
    slug, email, user_id = provision(db)
    result = ProductionAdminPasswordRecoveryService(db, environment="production", demo_seed_enabled=False).reset(organization_slug=slug, email=email, password=NEW)
    user = db.get(User, result); audit = db.scalar(select(AuditEvent).where(AuditEvent.target_id == user_id, AuditEvent.action == "OPERATOR_ADMIN_PASSWORD_RESET"))
    assert result == user_id and user.must_rotate_password and verify_password(NEW, user.hashed_password) and not verify_password(OLD, user.hashed_password)
    assert audit is not None and audit.actor_type == "operator" and audit.metadata_ == {"password_rotation_required": True}
    assert OLD not in str((audit.metadata_, caplog.text)) and NEW not in str((audit.metadata_, caplog.text))


def test_recovery_fails_closed_for_wrong_org_or_non_admin(db):
    slug, email, _ = provision(db)
    service = ProductionAdminPasswordRecoveryService(db, environment="production", demo_seed_enabled=False)
    with pytest.raises(NotFoundError): service.reset(organization_slug="missing-org", email=email, password=NEW)
    user = db.scalar(select(User).where(User.email == email)); user.role_id = db.scalar(select(Role.id).where(Role.name != "admin")); db.commit()
    with pytest.raises(NotFoundError): service.reset(organization_slug=slug, email=email, password=NEW)


def test_recovery_cli_file_or_confirmed_prompt_and_production_guard(db, monkeypatch, tmp_path):
    slug, email, _ = provision(db); secret = tmp_path / "password"; secret.write_text(NEW + "\n"); secret.chmod(0o600)
    monkeypatch.setattr(reset_admin_password, "get_settings", lambda: SETTINGS); monkeypatch.setattr(reset_admin_password, "SessionLocal", lambda: db)
    assert reset_admin_password.main(["--organization-slug", slug, "--email", email, "--password-file", str(secret)]) == 0
    assert "--password" not in {value for action in reset_admin_password.parser()._actions for value in action.option_strings}
    slug, email, _ = provision(db); answers = iter([NEW, NEW])
    assert reset_admin_password.main(["--organization-slug", slug, "--email", email], prompt=lambda _label: next(answers)) == 0
    secret.chmod(0o644)
    assert reset_admin_password.main(["--organization-slug", slug, "--email", email, "--password-file", str(secret)]) == 2


def test_recovery_rejects_invalid_or_nonproduction_without_mutation(db):
    slug, email, user_id = provision(db); original = db.get(User, user_id).hashed_password
    service = ProductionAdminPasswordRecoveryService(db, environment="development", demo_seed_enabled=False)
    with pytest.raises(ValidationError): service.reset(organization_slug=slug, email=email, password=NEW)
    with pytest.raises(ValidationError): ProductionAdminPasswordRecoveryService(db, environment="production", demo_seed_enabled=False).reset(organization_slug=slug, email=email, password="password")
    assert db.get(User, user_id).hashed_password == original
