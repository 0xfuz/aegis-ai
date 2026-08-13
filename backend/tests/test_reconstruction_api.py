from datetime import datetime, timezone
from uuid import uuid4
from fastapi.testclient import TestClient
import pytest
from app.core.security import create_access_token
from app.main import app
from app.modules.evidence.infrastructure.models import EvidenceItem
from app.modules.identity.infrastructure.models import Organization, Role, User
from app.modules.investigations.infrastructure.models import Investigation, InvestigationStatus, Severity
from app.shared.database import SessionLocal

@pytest.fixture()
def db():
 s=SessionLocal()
 try: yield s
 finally:s.rollback();s.close()
def scope(db):
 k=uuid4().hex;org=Organization(name=k,slug=f"api-read-{k}");role=Role(name=f"api-read-role-{k}");db.add_all((org,role));db.flush();user=User(org_id=org.id,role_id=role.id,email=f"{k}@test",hashed_password="x",full_name="test");inv=Investigation(org_id=org.id,title="read",source="test",severity=Severity.LOW,status=InvestigationStatus.NEW);db.add_all((user,inv));db.flush();db.add(EvidenceItem(org_id=org.id,investigation_id=inv.id,original_filename="safe",storage_key=k,sha256="a"*64,byte_size=0,detected_mime="text/plain",extension=".log",acquisition_source="test",imported_at=datetime(2026,1,1,tzinfo=timezone.utc),parsing_status="complete"));db.commit();return org,user,inv
def auth(user,org,perms=("investigation:read",)):return {"Authorization":f"Bearer {create_access_token(user.id,org.id,'analyst',perms)}"}
def url(inv):return f"/api/v1/investigations/{inv.id}/intelligence/reconstruction"
def test_reconstruction_api_scoped_safe_and_read_only(db):
 org,user,inv=scope(db);other,other_user,other_inv=scope(db);client=TestClient(app)
 response=client.get(url(inv),headers=auth(user,org));assert response.status_code==200
 body=response.json();assert {"policy_id","investigation","versions","context","activity","gaps","sections","pagination","warnings"}<=set(body)
 assert "content" not in str(body) and "input_snapshot" not in str(body)
 assert client.get(url(other_inv),headers=auth(user,org)).status_code==404
 assert client.get(url(inv),headers=auth(user,org,())).status_code==403
 user.is_active=False;db.commit();assert client.get(url(inv),headers=auth(user,org)).status_code==404
def test_reconstruction_api_has_only_get_route_and_framework_uuid_validation(db):
 org,user,inv=scope(db);client=TestClient(app);paths=[route for route in app.routes if route.path.endswith("/intelligence/reconstruction")]
 assert len(paths)==1 and paths[0].methods=={"GET"}
 assert client.get("/api/v1/investigations/not-a-uuid/intelligence/reconstruction",headers=auth(user,org)).status_code==422
 assert client.get(url(inv)+"?org_id=bad",headers=auth(user,org)).status_code in {200,422}
