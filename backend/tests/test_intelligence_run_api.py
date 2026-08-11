from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.core.security import create_access_token
from app.main import app
from app.modules.ai_reasoning.domain.run_orchestration_service import IntelligenceRunOrchestrationService
from app.modules.ai_reasoning.infrastructure.intelligence_models import IntelligenceAnalysis, IntelligenceItem
from app.modules.evidence.infrastructure.models import AuditEvent, Entity
from app.modules.identity.infrastructure.models import Organization, Role, User
from app.modules.investigations.infrastructure.models import Investigation, InvestigationStatus, Severity
from app.shared.database import SessionLocal


@pytest.fixture()
def db():
    session=SessionLocal()
    try: yield session
    finally: session.rollback();session.close()


def scope(db):
    suffix=uuid4().hex; org=Organization(name=suffix,slug=f"api-{suffix}"); role=Role(name=f"api-role-{suffix}")
    db.add_all([org,role]);db.flush(); user=User(org_id=org.id,role_id=role.id,email=f"{suffix}@test",hashed_password="x",full_name="API analyst")
    inv=Investigation(org_id=org.id,title="API",source="test",severity=Severity.MEDIUM,status=InvestigationStatus.NEW)
    db.add_all([user,inv]);db.commit();return org,user,inv


def headers(user,org,permissions):
    return {"Authorization":f"Bearer {create_access_token(user.id,org.id,'analyst',permissions)}"}


def base(inv): return f"/api/v1/investigations/{inv.id}/intelligence/runs"


def test_queue_get_list_are_idempotent_safe_and_strict(db):
    org,user,inv=scope(db);client=TestClient(app); auth=headers(user,org,["investigation:read","investigation:write"])
    first=client.post(base(inv),json={"request_key":"api-one"},headers=auth); assert first.status_code==202
    replay=client.post(base(inv),json={"request_key":"api-one"},headers=auth); assert replay.status_code==202 and replay.json()["id"]==first.json()["id"]
    run_id=first.json()["id"]; body=client.get(f"{base(inv)}/{run_id}",headers=auth).json()
    assert body["status"]=="QUEUED" and "input_snapshot" not in body and "provider" not in body
    listed=client.get(base(inv),headers=auth);assert listed.status_code==200 and [row["id"] for row in listed.json()["items"]]==[run_id]
    assert client.post(base(inv),json={"request_key":"bad","org_id":str(org.id)},headers=auth).status_code==422
    assert client.post(base(inv),json={"request_key":"x"*129},headers=auth).status_code==422
    assert client.get(base(inv)+"?limit=-1",headers=auth).status_code==422
    assert db.scalar(select(func.count()).select_from(IntelligenceItem).where(IntelligenceItem.investigation_id==inv.id))==0


def test_cancel_retry_and_conflict_preserve_authority_boundaries(db):
    org,user,inv=scope(db);client=TestClient(app);auth=headers(user,org,["investigation:read","investigation:write"])
    queued=client.post(base(inv),json={"request_key":"cancel"},headers=auth).json();run_id=queued["id"]
    assert client.post(f"{base(inv)}/{run_id}/cancel",json={"reason":"analyst stop"},headers=auth).json()["status"]=="CANCELLED"
    assert client.post(f"{base(inv)}/{run_id}/cancel",json={},headers=auth).status_code==200
    retry=client.post(f"{base(inv)}/{run_id}/retry",json={"request_key":"retry"},headers=auth);assert retry.status_code==202 and retry.json()["predecessor_analysis_id"]==run_id
    terminal=client.post(base(inv),json={"request_key":"terminal"},headers=auth).json()["id"]
    service=IntelligenceRunOrchestrationService(db);service.acquire(org.id,terminal);service.complete(org.id,terminal)
    assert client.post(f"{base(inv)}/{terminal}/retry",json={"request_key":"nope"},headers=auth).status_code==422
    conflict=client.post(base(inv),json={"request_key":"conflict"},headers=auth);assert conflict.status_code==202
    db.add(Entity(org_id=org.id,investigation_id=inv.id,type="host",canonical_value="changed",display_name="changed"));db.commit()
    assert client.post(base(inv),json={"request_key":"conflict"},headers=auth).status_code==409
    assert db.scalar(select(AuditEvent).where(AuditEvent.action=="INTELLIGENCE_RUN_CANCELLED")) is not None


def test_route_authentication_permission_activity_and_foreign_scope(db):
    org,user,inv=scope(db);other,other_user,other_inv=scope(db);client=TestClient(app);write=headers(user,org,["investigation:write"]);read=headers(user,org,["investigation:read"])
    assert client.post(base(inv),json={"request_key":"auth"}).status_code==403
    assert client.post(base(inv),json={"request_key":"read-only"},headers=read).status_code==403
    run=client.post(base(inv),json={"request_key":"own"},headers=write).json()["id"]
    assert client.get(f"{base(inv)}/{run}",headers=read).status_code==200
    assert client.get(f"{base(other_inv)}/{run}",headers=headers(other_user,other,["investigation:read"])).status_code==404
    user.is_active=False;db.commit()
    assert client.post(base(inv),json={"request_key":"inactive"},headers=write).status_code==404
    paths={route.path for route in app.routes}
    assert not any(any(token in path for token in ("/acquire","/complete","/fail","/transition","/snapshot")) and "/intelligence/runs" in path for path in paths)
