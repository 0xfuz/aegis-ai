"""Phase 7.7.1 adversarial measurement only; frozen v1 algorithms."""
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from sqlalchemy import select

from app.modules.alert_triage.domain.correlation_service import AlertCorrelationService
from app.modules.alert_triage.domain.deduplication_service import AlertDeduplicationService
from app.modules.alert_triage.domain.service import CanonicalAlertCreate, CanonicalAlertService
from app.modules.alert_triage.domain.triage_service import AlertClusterTriageService
from app.modules.connectors.infrastructure.models import Connector, RawEvent
from app.modules.identity.infrastructure.models import Organization
from app.shared.database import SessionLocal


def _alert(db, org, connector, key, at, obs, rule="rule", severity="HIGH", category="network"):
    raw=RawEvent(connector_id=connector.id,received_at=at,payload={"synthetic":key});db.add(raw);db.commit()
    return CanonicalAlertService(db).create(org.id,connector.id,raw.id,CanonicalAlertCreate(source="adversarial",source_alert_id=key,observed_at=at,title=rule,description="synthetic",severity=severity,category=category,rule_id=rule,observables=obs))[0]


def test_adversarial_v1_measurement_catalog():
    db=SessionLocal(); suffix=uuid4().hex; org=Organization(name=suffix,slug=f"adv-{suffix}");db.add(org);db.flush(); source=Connector(org_id=org.id,name=suffix,type="webhook",secret_hash="x");db.add(source);db.commit(); t=datetime(2026,8,9,12,tzinfo=timezone.utc)
    try:
        # Rotating IP retains hostname/user signals and should group; NAT-only must not.
        rotate=[_alert(db,org,source,"r1",t,{"hostname":"srv","username":"admin","source_ip":"198.51.100.1"},"auth"),_alert(db,org,source,"r2",t+timedelta(seconds=15),{"hostname":"srv","username":"admin","source_ip":"198.51.100.2"},"exec")]
        nat=[_alert(db,org,source,"n1",t,{"source_ip":"198.51.100.9"},"nat-a"),_alert(db,org,source,"n2",t+timedelta(seconds=10),{"source_ip":"198.51.100.9"},"nat-b")]
        parallel=[_alert(db,org,source,"p1",t,{"hostname":"shared"},"attack-a"),_alert(db,org,source,"p2",t+timedelta(seconds=10),{"hostname":"shared"},"attack-b")]
        correlation=AlertCorrelationService(db); clusters={row.id:correlation.process(org.id,row.id) for row in rotate+nat+parallel}
        assert clusters[rotate[0].id].id == clusters[rotate[1].id].id
        assert clusters[nat[0].id].id != clusters[nat[1].id].id
        # Parallel same-host attacks merge: intentionally captured false merge.
        assert clusters[parallel[0].id].id == clusters[parallel[1].id].id
        # Semantic flood is deduplicated and cannot become cluster members.
        duplicate=_alert(db,org,source,"d",t+timedelta(seconds=20),{"hostname":"srv","username":"admin","source_ip":"198.51.100.1"},"auth")
        assert AlertDeduplicationService(db).process(org.id,duplicate.id).is_duplicate
        assert correlation.process(org.id,duplicate.id) is None
        assessment=AlertClusterTriageService(db).assess(org.id,clusters[rotate[0].id].id,t+timedelta(hours=1))
        assert assessment.priority in {"LOW","MEDIUM","HIGH","CRITICAL"}
    finally: db.rollback();db.close()
