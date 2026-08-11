"""Demo Investigation Pack integration tests (synthetic repository-owned data only)."""
from uuid import uuid4

import pytest
from sqlalchemy import select

from app.modules.ai_reasoning.infrastructure.intelligence_models import IntelligenceAnalysis, IntelligenceItem
from app.modules.evidence.domain.graph_projection import CanonicalGraphProjectionService, GraphFilters
from app.modules.demos.domain.service import DemoInvestigationService, SCENARIOS
from app.modules.evidence.infrastructure.models import Entity, Event, EvidenceItem, Indicator
from app.modules.identity.infrastructure.models import Organization, Role, User
from app.modules.investigations.infrastructure.models import Investigation
from app.modules.reporting.domain.service import ReportService
from app.shared.database import SessionLocal
from app.shared.exceptions import ConflictError, NotFoundError


@pytest.fixture()
def db():
    session = SessionLocal()
    try: yield session
    finally: session.rollback(); session.close()


def user_context(db):
    suffix = uuid4().hex[:10]
    org = Organization(name=f"Demo {suffix}", slug=f"demo-{suffix}")
    role = Role(name=f"demo-{suffix}")
    db.add_all([org, role]); db.flush()
    user = User(org_id=org.id, role_id=role.id, email=f"{suffix}@example.test", hashed_password="x", full_name="Demo loader")
    db.add(user); db.commit()
    return org, user


def test_all_demo_scenarios_import_build_graph_open_notebook_and_report(db):
    org, user = user_context(db); service = DemoInvestigationService(db)
    for scenario_id in SCENARIOS:
        investigation = service.load(org.id, user.id, scenario_id)
        assert db.scalar(select(EvidenceItem).where(EvidenceItem.investigation_id == investigation.id))
        assert db.scalar(select(Event).where(Event.investigation_id == investigation.id))
        assert db.scalar(select(Entity).where(Entity.investigation_id == investigation.id))
        assert db.scalar(select(Indicator).where(Indicator.org_id == org.id))
        graph = CanonicalGraphProjectionService(db).project(org.id, investigation.id, GraphFilters())
        assert graph["nodes"]
        assert db.scalar(select(IntelligenceAnalysis).where(IntelligenceAnalysis.investigation_id == investigation.id))
        assert db.scalar(select(IntelligenceItem).where(IntelligenceItem.investigation_id == investigation.id, IntelligenceItem.review_status == "CONFIRMED"))
        report, _media_type, _filename = ReportService().generate(investigation, "technical", "markdown")
        report_text = report.decode()
        assert investigation.title in report_text and investigation.mitre_techniques[0] in report_text
    with pytest.raises(ConflictError): service.load(org.id, user.id, "brute-force")


def test_loaded_demo_can_be_deleted_without_affecting_other_scenarios(db):
    org, user = user_context(db); service = DemoInvestigationService(db)
    loaded = service.load(org.id, user.id, "brute-force")
    service.load(org.id, user.id, "phishing")
    service.delete(org.id, "brute-force")
    assert db.get(Investigation, loaded.id) is None
    assert [row["id"] for row in service.catalog(org.id) if row["loaded"]] == ["phishing"]
    with pytest.raises(NotFoundError): service.delete(org.id, "brute-force")
