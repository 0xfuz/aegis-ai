"""Bounded read-only AI-origin MITRE suggestion projection."""
from uuid import uuid4

import pytest

from app.modules.investigations.domain.service import InvestigationService
from app.modules.investigations.infrastructure.models import Investigation, InvestigationStatus, Severity
from app.modules.identity.infrastructure.models import Organization
from app.shared.database import SessionLocal
from app.shared.exceptions import NotFoundError


@pytest.fixture()
def db():
    session = SessionLocal()
    try: yield session
    finally: session.rollback(); session.close()


def test_suggestions_are_bounded_deduplicated_catalogued_and_scoped(db):
    org = Organization(name=f"Suggestion {uuid4().hex}", slug=f"suggestion-{uuid4().hex}"); db.add(org); db.flush()
    investigation = Investigation(org_id=org.id, title="Test", source="test", severity=Severity.LOW, status=InvestigationStatus.NEW, confidence=0, root_cause="", mitre_techniques=["T1078", "T1110", "T1110", "T9999"], blast_radius_summary="", false_positive_probability=0, attack_chain=[], alternative_hypotheses=[], reasoning_chain=[]); db.add(investigation); db.commit()
    result = InvestigationService(db).mitre_suggestions(org.id, investigation.id)
    assert [item["technique_id"] for item in result["items"]] == ["T1078", "T1110", "T9999"]
    assert result["items"][0]["technique_name"] == "Valid Accounts" and result["items"][1]["technique_name"] == "Brute Force"
    assert all(item["origin"] == "AI_SUGGESTION" and item["review_state"] == "SUGGESTED" for item in result["items"])
    with pytest.raises(NotFoundError): InvestigationService(db).mitre_suggestions(uuid4(), investigation.id)
