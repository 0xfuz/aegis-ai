from datetime import datetime, timezone
from uuid import uuid4
from sqlalchemy import func, select
from app.modules.alert_triage.domain.correlation_service import AlertCorrelationService, CORRELATION_VERSION
from app.modules.alert_triage.domain.correlation_v2_service import AlertCorrelationV2Service, CORRELATION_V2_VERSION
from app.modules.alert_triage.domain.service import CanonicalAlertCreate, CanonicalAlertService
from app.modules.alert_triage.infrastructure.models import AlertClusterMembership
from app.modules.connectors.infrastructure.models import Connector, RawEvent
from app.modules.identity.infrastructure.models import Organization
from app.modules.investigations.infrastructure.models import Investigation  # registers FK target metadata
from app.shared.database import SessionLocal

def test_v1_v2_membership_history_is_isolated_and_idempotent():
 db=SessionLocal();s=uuid4().hex;org=Organization(name=s,slug=f"iso-{s}");db.add(org);db.flush();c=Connector(org_id=org.id,name=s,type="webhook",secret_hash="x");db.add(c);db.commit()
 try:
  raw=RawEvent(connector_id=c.id,received_at=datetime.now(timezone.utc),payload={});db.add(raw);db.commit()
  a=CanonicalAlertService(db).create(org.id,c.id,raw.id,CanonicalAlertCreate(source="test",source_alert_id="a",observed_at=datetime.now(timezone.utc),title="a",severity="HIGH",category="network",rule_id="r",observables={"hostname":"h","username":"u","process":"p"}))[0]
  v1=AlertCorrelationService(db);v2=AlertCorrelationV2Service(db);one=v1.process(org.id,a.id);two=v2.process(org.id,a.id)
  assert one.correlation_version==CORRELATION_VERSION and two.correlation_version==CORRELATION_V2_VERSION
  assert v1.process(org.id,a.id).id==one.id and v2.process(org.id,a.id).id==two.id
  assert db.scalar(select(func.count()).select_from(AlertClusterMembership).where(AlertClusterMembership.alert_id==a.id))==2
 finally: db.rollback();db.close()
