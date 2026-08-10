"""Synthetic, idempotent demo investigations built through canonical ingestion."""
from __future__ import annotations

import hashlib
import io
import json
from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.modules.ai_reasoning.infrastructure.intelligence_models import IntelligenceAnalysis, IntelligenceFactLink, IntelligenceItem, IntelligenceReviewEvent
from app.modules.evidence.domain.service import EvidenceIngestionService
from app.modules.evidence.infrastructure.models import AuditEvent, Entity, EntityRelationship, EntityObservation, Event, EvidenceItem, EvidenceParseRun, IndicatorOccurrence, RawRecord
from app.modules.evidence.infrastructure.storage import EvidenceStorage
from app.modules.investigations.infrastructure.models import ActionStatus, EvidenceRecord, Investigation, InvestigationStatus, RecommendedAction, Severity, TimelineEvent
from app.shared.exceptions import ConflictError, NotFoundError

DEMO_SOURCE_PREFIX = "Demo Investigation Pack"

SCENARIOS = {
    "brute-force": {"title": "Brute Force Attack", "file": "auth.log.json", "severity": Severity.HIGH, "mitre": ["T1110", "T1078"], "root": "Repeated SSH password failures from 198.51.100.44 were followed by a successful login to the backup account.", "rows": [{"timestamp":"2025-01-12T08:00:00Z","host":"ssh-gateway-01","user":"backup","source_ip":"198.51.100.44","event_type":"authentication","action":"failed SSH password"},{"timestamp":"2025-01-12T08:01:00Z","host":"ssh-gateway-01","user":"backup","source_ip":"198.51.100.44","event_type":"authentication","action":"failed SSH password"},{"timestamp":"2025-01-12T08:03:00Z","host":"ssh-gateway-01","user":"backup","source_ip":"198.51.100.44","event_type":"authentication","action":"successful SSH login"}]},
    "phishing": {"title": "Phishing Campaign", "file": "email-headers.json", "severity": Severity.HIGH, "mitre": ["T1566.001", "T1204.002"], "root": "A synthetic invoice lure delivered a credential-harvesting URL and attachment to finance recipients.", "rows": [{"timestamp":"2025-02-03T09:00:00Z","host":"mail-gateway-01","user":"finance@aegis.demo","source_ip":"203.0.113.25","destination_ip":"198.51.100.88","event_type":"email","action":"sender billing@invoice-alert.test attachment invoice.html query login-secure.test"},{"timestamp":"2025-02-03T09:04:00Z","host":"finance-ws-02","user":"finance@aegis.demo","source_ip":"10.10.2.18","event_type":"browser","action":"opened https://login-secure.test/invoice"}]},
    "ransomware": {"title": "Ransomware Incident", "file": "windows-events.json", "severity": Severity.CRITICAL, "mitre": ["T1059.001", "T1547.001", "T1486"], "root": "PowerShell execution established registry persistence, contacted 203.0.113.77, and encrypted shared documents.", "rows": [{"timestamp":"2025-03-10T11:00:00Z","host":"win-finance-07","user":"maria","source_ip":"10.10.3.7","destination_ip":"203.0.113.77","process":"powershell.exe","event_type":"process","action":"powershell download payload"},{"timestamp":"2025-03-10T11:02:00Z","host":"win-finance-07","user":"maria","process":"reg.exe","event_type":"registry","action":"Run key persistence"},{"timestamp":"2025-03-10T11:07:00Z","host":"win-finance-07","user":"maria","event_type":"file","action":"encrypted finance-share files"}]},
    "insider-threat": {"title": "Insider Threat", "file": "activity.json", "severity": Severity.HIGH, "mitre": ["T1078", "T1098", "T1021.002"], "root": "An employee account used removable media after privilege escalation and copied restricted files outside normal hours.", "rows": [{"timestamp":"2025-04-18T22:10:00Z","host":"eng-ws-14","user":"devon","source_ip":"10.10.4.14","event_type":"authentication","action":"unusual late login"},{"timestamp":"2025-04-18T22:18:00Z","host":"eng-ws-14","user":"devon","event_type":"usb","action":"USB mass storage attached"},{"timestamp":"2025-04-18T22:23:00Z","host":"eng-ws-14","user":"devon","process":"cmd.exe","event_type":"file","action":"copied product-roadmap files"}]},
    "web-breach": {"title": "Web Application Breach", "file": "access.log.json", "severity": Severity.CRITICAL, "mitre": ["T1190", "T1505.003"], "root": "SQL injection probes from 198.51.100.66 targeted /search before a synthetic webshell upload was observed.", "rows": [{"timestamp":"2025-05-22T14:00:00Z","host":"web-prod-01","source_ip":"198.51.100.66","event_type":"http","action":"GET /search?q=union select password from users"},{"timestamp":"2025-05-22T14:02:00Z","host":"web-prod-01","source_ip":"198.51.100.66","event_type":"http","action":"POST /upload webshell.php"},{"timestamp":"2025-05-22T14:04:00Z","host":"web-prod-01","source_ip":"198.51.100.66","destination_ip":"203.0.113.66","process":"nginx","event_type":"process","action":"webshell command execution"}]},
}


class DemoInvestigationService:
    def __init__(self, db: Session): self.db = db

    def catalog(self, org_id: UUID):
        existing = {row.source.removeprefix(f"{DEMO_SOURCE_PREFIX}:") for row in self.db.scalars(select(Investigation).where(Investigation.org_id == org_id, Investigation.source.like(f"{DEMO_SOURCE_PREFIX}:%"))).all()}
        return [{"id": key, "title": value["title"], "loaded": key in existing} for key, value in SCENARIOS.items()]

    def load(self, org_id: UUID, user_id: UUID, scenario_id: str) -> Investigation:
        scenario = SCENARIOS.get(scenario_id)
        if scenario is None: raise NotFoundError("Demo scenario not found.")
        source = f"{DEMO_SOURCE_PREFIX}:{scenario_id}"
        if self.db.scalar(select(Investigation).where(Investigation.org_id == org_id, Investigation.source == source)): raise ConflictError("This demo investigation is already loaded.")
        investigation = Investigation(org_id=org_id, title=scenario["title"], source=source, severity=scenario["severity"], status=InvestigationStatus.INVESTIGATING, confidence=92, root_cause=scenario["root"], mitre_techniques=scenario["mitre"], blast_radius_summary="Synthetic training investigation; no production systems are affected.", false_positive_probability=5, attack_chain=[{"phase":"Detection","description":scenario["root"]}], alternative_hypotheses=[{"hypothesis":"Benign administrative activity","likelihood":5}], reasoning_chain=["Synthetic evidence was parsed into canonical FACT records."])
        self.db.add(investigation); self.db.commit()
        payload = json.dumps(scenario["rows"], separators=(",", ":")).encode()
        upload = SimpleNamespace(filename=scenario["file"], content_type="application/json", file=io.BytesIO(payload))
        EvidenceIngestionService(self.db, get_settings()).ingest(org_id, investigation.id, user_id, upload)
        now = datetime.now(timezone.utc)
        for row in scenario["rows"]:
            occurred = datetime.fromisoformat(row["timestamp"].replace("Z", "+00:00"))
            self.db.add(TimelineEvent(investigation_id=investigation.id, occurred_at=occurred, description=row["action"], severity=scenario["severity"], mitre_technique=scenario["mitre"][0], source="Synthetic demo evidence", affected_asset=row.get("host"), actor=row.get("user") or row.get("source_ip")))
            self.db.add(EvidenceRecord(investigation_id=investigation.id, category=row["event_type"], occurred_at=occurred, summary=row["action"], details=row))
        self.db.add(RecommendedAction(investigation_id=investigation.id, title="Contain simulated activity", description="Training-only recommendation generated from synthetic evidence.", status=ActionStatus.APPROVED, confidence=92, business_impact="low", estimated_time_to_contain="Under 5 minutes", approval_tier="SOC Tier 1"))
        self._approved_notebook(org_id, user_id, investigation)
        self.db.commit(); return investigation

    def _approved_notebook(self, org_id: UUID, user_id: UUID, investigation: Investigation):
        event = self.db.scalars(select(Event).where(Event.org_id == org_id, Event.investigation_id == investigation.id).order_by(Event.timestamp)).first()
        if event is None: return
        snapshot = {"demo": True, "investigation_id": str(investigation.id)}
        analysis = IntelligenceAnalysis(org_id=org_id, investigation_id=investigation.id, provider="demo", model="repository-owned-synthetic", prompt_template_version="demo-v1", input_snapshot=snapshot, input_hash=hashlib.sha256(json.dumps(snapshot, sort_keys=True).encode()).hexdigest(), status="COMPLETED", generated_at=datetime.now(timezone.utc))
        self.db.add(analysis); self.db.flush()
        summary = IntelligenceItem(org_id=org_id, analysis_id=analysis.id, investigation_id=investigation.id, kind="SUMMARY", ordinal=0, statement=investigation.root_cause, confidence=92, payload={}, review_status="APPROVED", reviewed_by_id=user_id, reviewed_at=datetime.now(timezone.utc), review_rationale="Repository-owned demo approved for training.")
        finding = IntelligenceItem(org_id=org_id, analysis_id=analysis.id, investigation_id=investigation.id, kind="OBSERVATION", ordinal=0, statement="Synthetic canonical event supports the training finding.", confidence=92, payload={}, review_status="APPROVED", reviewed_by_id=user_id, reviewed_at=datetime.now(timezone.utc), review_rationale="Repository-owned demo approved for training.")
        self.db.add_all([summary, finding]); self.db.flush()
        self.db.add(IntelligenceFactLink(org_id=org_id, item_id=finding.id, fact_type="FACT", fact_id=event.id, role="SUPPORTS"))
        self.db.add(IntelligenceReviewEvent(org_id=org_id, item_id=finding.id, from_status="UNREVIEWED", to_status="APPROVED", reviewer_id=user_id, rationale="Repository-owned demo approved for training."))
        self.db.add(AuditEvent(org_id=org_id, investigation_id=investigation.id, actor_id=user_id, actor_type="user", action="DEMO_INTELLIGENCE_APPROVED", target_type="IntelligenceItem", target_id=finding.id, occurred_at=datetime.now(timezone.utc)))

    def delete(self, org_id: UUID, scenario_id: str):
        investigation = self.db.scalar(select(Investigation).where(Investigation.org_id == org_id, Investigation.source == f"{DEMO_SOURCE_PREFIX}:{scenario_id}"))
        if investigation is None: raise NotFoundError("Loaded demo investigation not found.")
        item_ids = list(self.db.scalars(select(IntelligenceItem.id).where(IntelligenceItem.investigation_id == investigation.id)))
        analysis_ids = list(self.db.scalars(select(IntelligenceAnalysis.id).where(IntelligenceAnalysis.investigation_id == investigation.id)))
        evidence_ids = list(self.db.scalars(select(EvidenceItem.id).where(EvidenceItem.investigation_id == investigation.id)))
        storage_keys = list(self.db.scalars(select(EvidenceItem.storage_key).where(EvidenceItem.investigation_id == investigation.id)))
        run_ids = list(self.db.scalars(select(EvidenceParseRun.id).where(EvidenceParseRun.evidence_id.in_(evidence_ids)))) if evidence_ids else []
        raw_ids = list(self.db.scalars(select(RawRecord.id).where(RawRecord.evidence_id.in_(evidence_ids)))) if evidence_ids else []
        self.db.execute(delete(IntelligenceReviewEvent).where(IntelligenceReviewEvent.item_id.in_(item_ids))) if item_ids else None
        self.db.execute(delete(IntelligenceFactLink).where(IntelligenceFactLink.item_id.in_(item_ids))) if item_ids else None
        self.db.execute(delete(IntelligenceItem).where(IntelligenceItem.id.in_(item_ids))) if item_ids else None
        self.db.execute(delete(IntelligenceAnalysis).where(IntelligenceAnalysis.id.in_(analysis_ids))) if analysis_ids else None
        self.db.execute(delete(AuditEvent).where(AuditEvent.investigation_id == investigation.id)); self.db.execute(delete(EntityRelationship).where(EntityRelationship.investigation_id == investigation.id)); self.db.execute(delete(EntityObservation).where(EntityObservation.investigation_id == investigation.id)); self.db.execute(delete(IndicatorOccurrence).where(IndicatorOccurrence.investigation_id == investigation.id)); self.db.execute(delete(Entity).where(Entity.investigation_id == investigation.id)); self.db.execute(delete(Event).where(Event.investigation_id == investigation.id)); self.db.execute(delete(RawRecord).where(RawRecord.id.in_(raw_ids))) if raw_ids else None; self.db.execute(delete(EvidenceParseRun).where(EvidenceParseRun.id.in_(run_ids))) if run_ids else None; self.db.execute(delete(EvidenceItem).where(EvidenceItem.id.in_(evidence_ids))) if evidence_ids else None
        self.db.delete(investigation); self.db.commit()
        storage=EvidenceStorage(get_settings())
        for storage_key in storage_keys: storage.delete(storage_key)
