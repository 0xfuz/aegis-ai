"""Server-side validation for immutable typed intelligence citations."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from app.modules.alert_triage.infrastructure.models import AlertCluster, AlertClusterAssessment, AlertClusterMembership, AlertClusterPromotion, CanonicalAlert
from app.modules.ai_reasoning.infrastructure.intelligence_models import IntelligenceAnalysis, IntelligenceClaimEvidenceLink, IntelligenceEvidenceReference, IntelligenceItem
from app.modules.evidence.infrastructure.models import EntityObservation, EntityRelationship, Event, EvidenceItem, EvidenceParseRun, IndicatorOccurrence, RawRecord
from app.modules.investigations.infrastructure.models import Finding, MitreMapping
from app.shared.exceptions import NotFoundError, ValidationError

_PREFIX_TYPES = {"E": "EVIDENCE_ITEM", "RR": "RAW_RECORD", "EV": "EVENT", "EO": "ENTITY_OBSERVATION", "IO": "INDICATOR_OCCURRENCE", "REL": "ENTITY_RELATIONSHIP", "AL": "CANONICAL_ALERT", "CM": "ALERT_CLUSTER_MEMBERSHIP", "TR": "ALERT_CLUSTER_ASSESSMENT", "PR": "ALERT_CLUSTER_PROMOTION", "FI": "FINDING", "MT": "MITRE_MAPPING"}
_COLUMNS = {"EVIDENCE_ITEM": "evidence_item_id", "RAW_RECORD": "raw_record_id", "EVENT": "event_id", "ENTITY_OBSERVATION": "entity_observation_id", "INDICATOR_OCCURRENCE": "indicator_occurrence_id", "ENTITY_RELATIONSHIP": "entity_relationship_id", "CANONICAL_ALERT": "canonical_alert_id", "ALERT_CLUSTER_MEMBERSHIP": "alert_cluster_membership_id", "ALERT_CLUSTER_ASSESSMENT": "alert_cluster_assessment_id", "ALERT_CLUSTER_PROMOTION": "alert_cluster_promotion_id", "FINDING": "finding_id", "MITRE_MAPPING": "mitre_mapping_id"}
_MODELS = {"EVIDENCE_ITEM": EvidenceItem, "RAW_RECORD": RawRecord, "EVENT": Event, "ENTITY_OBSERVATION": EntityObservation, "INDICATOR_OCCURRENCE": IndicatorOccurrence, "ENTITY_RELATIONSHIP": EntityRelationship, "CANONICAL_ALERT": CanonicalAlert, "ALERT_CLUSTER_MEMBERSHIP": AlertClusterMembership, "ALERT_CLUSTER_ASSESSMENT": AlertClusterAssessment, "ALERT_CLUSTER_PROMOTION": AlertClusterPromotion, "FINDING": Finding, "MITRE_MAPPING": MitreMapping}


def _digest(value: object) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()


class IntelligenceEvidenceReferenceService:
    """Creates only citations that can be reconstructed from a stored run snapshot."""

    def __init__(self, db: Session): self.db = db

    def create(self, org_id: UUID, investigation_id: UUID, analysis_id: UUID, snapshot_alias: str, expected_reference_type: str | None = None) -> IntelligenceEvidenceReference:
        return self.create_many(org_id, investigation_id, analysis_id, [(snapshot_alias, expected_reference_type)])[0]

    def create_many(self, org_id: UUID, investigation_id: UUID, analysis_id: UUID, requests: list[tuple[str, str | None]]) -> list[IntelligenceEvidenceReference]:
        try:
            run = self._run(org_id, investigation_id, analysis_id)
            rows = [self._one(run, alias, expected) for alias, expected in requests]
            self.db.commit()
            return rows
        except IntegrityError:
            self.db.rollback()
            if len(requests) == 1:
                recovered = self._existing_exact(org_id, investigation_id, analysis_id, *requests[0])
                if recovered: return [recovered]
            raise ValidationError("Unable to persist evidence reference.") from None
        except SQLAlchemyError:
            self.db.rollback(); raise ValidationError("Unable to persist evidence reference.") from None
        except Exception:
            self.db.rollback(); raise

    def link_claim(self, org_id: UUID, investigation_id: UUID, analysis_id: UUID, claim_id: UUID, reference_id: UUID, role: str) -> IntelligenceClaimEvidenceLink:
        if role not in {"SUPPORTS", "CONTRADICTS", "CONTEXT"}: raise ValidationError("Invalid evidence link role.")
        try:
            run = self._run(org_id, investigation_id, analysis_id)
            claim = self.db.get(IntelligenceItem, claim_id)
            ref = self.db.get(IntelligenceEvidenceReference, reference_id)
            if not claim or not ref or claim.org_id != org_id or ref.org_id != org_id or claim.investigation_id != investigation_id or ref.investigation_id != investigation_id or claim.analysis_id != run.id or ref.analysis_id != run.id: raise ValidationError("Claim and reference must belong to the same run scope.")
            if ref.reference_type in {"FINDING", "MITRE_MAPPING"} and role != "CONTEXT": raise ValidationError("Confirmed analyst conclusions may be linked only as context.")
            existing = self.db.scalar(select(IntelligenceClaimEvidenceLink).where(IntelligenceClaimEvidenceLink.item_id == claim_id, IntelligenceClaimEvidenceLink.evidence_reference_id == reference_id, IntelligenceClaimEvidenceLink.role == role))
            if existing: return existing
            row = IntelligenceClaimEvidenceLink(org_id=org_id, investigation_id=investigation_id, item_id=claim_id, evidence_reference_id=reference_id, role=role)
            self.db.add(row); self.db.commit(); return row
        except IntegrityError:
            self.db.rollback(); raise ValidationError("Unable to persist evidence link.") from None
        except SQLAlchemyError:
            self.db.rollback(); raise ValidationError("Unable to persist evidence link.") from None
        except Exception:
            self.db.rollback(); raise

    def _run(self, org_id, investigation_id, analysis_id):
        run = self.db.scalar(select(IntelligenceAnalysis).where(IntelligenceAnalysis.id == analysis_id, IntelligenceAnalysis.org_id == org_id, IntelligenceAnalysis.investigation_id == investigation_id))
        if not run or run.status in {"FAILED", "CANCELLED"}: raise NotFoundError("Active intelligence run not found.")
        if not isinstance(run.input_snapshot, dict) or not isinstance(run.input_snapshot.get("aliases"), dict): raise ValidationError("Intelligence run snapshot has no authoritative aliases.")
        return run

    def _one(self, run, alias, expected):
        entry = run.input_snapshot["aliases"].get(alias)
        if not isinstance(entry, dict) or not isinstance(entry.get("id"), str) or not isinstance(entry.get("type"), str): raise ValidationError("Unknown factual alias for this run.")
        ref_type = _PREFIX_TYPES.get(entry["type"], entry["type"])
        if ref_type not in _MODELS or (expected is not None and expected != ref_type): raise ValidationError("Snapshot alias type does not match the requested reference type.")
        try: target_id = UUID(entry["id"])
        except ValueError: raise ValidationError("Snapshot alias has invalid target identity.") from None
        target = self.db.get(_MODELS[ref_type], target_id)
        if not target: raise ValidationError("Snapshot target no longer exists.")
        self._validate_target(run, ref_type, target)
        existing = self.db.scalar(select(IntelligenceEvidenceReference).where(IntelligenceEvidenceReference.analysis_id == run.id, IntelligenceEvidenceReference.snapshot_alias == alias))
        if existing:
            if existing.reference_type == ref_type and getattr(existing, _COLUMNS[ref_type]) == target_id: return existing
            raise ValidationError("Snapshot alias conflicts with an existing evidence reference.")
        metadata, producer, version, evidence_hash = self._metadata(ref_type, target)
        row = IntelligenceEvidenceReference(org_id=run.org_id, investigation_id=run.investigation_id, analysis_id=run.id, snapshot_alias=alias, reference_type=ref_type, context_version=str(run.input_snapshot.get("context_version", "unknown"))[:64], builder_version=str(run.input_snapshot.get("builder_version", "unknown"))[:64], policy_version=_digest(run.input_snapshot.get("policy", {})), provenance_fingerprint=run.input_hash, locator_metadata=metadata, locator_hash=_digest(metadata), producer_name=producer, producer_version=version, evidence_sha256=evidence_hash, **{_COLUMNS[ref_type]: target_id})
        self.db.add(row); self.db.flush(); return row

    def _existing_exact(self, org, inv, analysis, alias, expected):
        row = self.db.scalar(select(IntelligenceEvidenceReference).where(IntelligenceEvidenceReference.org_id == org, IntelligenceEvidenceReference.investigation_id == inv, IntelligenceEvidenceReference.analysis_id == analysis, IntelligenceEvidenceReference.snapshot_alias == alias))
        if row and (expected is None or row.reference_type == expected): return row
        return None

    def _validate_target(self, run, kind, target):
        org, inv = run.org_id, run.investigation_id
        if getattr(target, "org_id", None) != org: raise ValidationError("Snapshot target is outside the run organization.")
        direct = {"EVIDENCE_ITEM", "EVENT", "ENTITY_OBSERVATION", "INDICATOR_OCCURRENCE", "ENTITY_RELATIONSHIP", "ALERT_CLUSTER_PROMOTION", "FINDING", "MITRE_MAPPING"}
        if kind in direct and getattr(target, "investigation_id", None) != inv: raise ValidationError("Snapshot target is outside the run investigation.")
        if kind == "RAW_RECORD":
            evidence = self.db.get(EvidenceItem, target.evidence_id)
            if not evidence or evidence.org_id != org or evidence.investigation_id != inv: raise ValidationError("Raw record provenance is outside the run scope.")
        if kind == "CANONICAL_ALERT": self._promotion_for_alert(run, target.id)
        if kind in {"ALERT_CLUSTER_MEMBERSHIP", "ALERT_CLUSTER_ASSESSMENT"}: self._promotion_cluster_target(run, kind, target)
        if kind == "ALERT_CLUSTER_PROMOTION": self._promotion_valid(target, org, inv)
        if kind == "FINDING" and target.status != "CONFIRMED": raise ValidationError("Only confirmed findings may be cited.")
        if kind == "MITRE_MAPPING" and target.status != "CONFIRMED": raise ValidationError("Only analyst-confirmed MITRE mappings may be cited.")

    def _promotion_valid(self, promotion, org, inv):
        if promotion.status != "COMPLETED" or promotion.org_id != org or promotion.investigation_id != inv: raise ValidationError("Promotion is outside the run scope.")
        cluster = self.db.get(AlertCluster, promotion.cluster_id); assessment = self.db.get(AlertClusterAssessment, promotion.triage_assessment_id)
        if not cluster or not assessment or cluster.org_id != org or assessment.org_id != org or assessment.cluster_id != cluster.id or cluster.correlation_version not in {"correlation-v1", "correlation-v2"}: raise ValidationError("Promotion lineage is invalid.")
        if promotion.manifest.get("correlation_version") != cluster.correlation_version: raise ValidationError("Promotion correlation version lineage is invalid.")
        return cluster

    def _promotion_for_alert(self, run, alert_id):
        promotion = self.db.scalar(select(AlertClusterPromotion).join(AlertCluster, AlertCluster.id == AlertClusterPromotion.cluster_id).join(AlertClusterMembership, AlertClusterMembership.cluster_id == AlertCluster.id).where(AlertClusterPromotion.org_id == run.org_id, AlertClusterPromotion.investigation_id == run.investigation_id, AlertClusterMembership.alert_id == alert_id, AlertClusterMembership.correlation_version == AlertCluster.correlation_version))
        if not promotion: raise ValidationError("Canonical alert is not reachable through the promoted cluster.")
        self._promotion_valid(promotion, run.org_id, run.investigation_id)

    def _promotion_cluster_target(self, run, kind, target):
        cluster_id = target.cluster_id
        promotion = self.db.scalar(select(AlertClusterPromotion).where(AlertClusterPromotion.org_id == run.org_id, AlertClusterPromotion.investigation_id == run.investigation_id, AlertClusterPromotion.cluster_id == cluster_id))
        if not promotion: raise ValidationError("Correlation target is not reachable through the promoted cluster.")
        cluster = self._promotion_valid(promotion, run.org_id, run.investigation_id)
        if kind == "ALERT_CLUSTER_MEMBERSHIP" and target.correlation_version != cluster.correlation_version: raise ValidationError("Membership correlation version does not match promotion.")
        if kind == "ALERT_CLUSTER_ASSESSMENT" and promotion.triage_assessment_id != target.id: raise ValidationError("Assessment does not match promotion.")

    def _metadata(self, kind, target):
        fields = {"reference_type": kind, "captured_at": datetime.now(timezone.utc).isoformat()}
        producer = version = evidence_hash = None
        if kind == "EVIDENCE_ITEM": fields.update({"evidence_id": str(target.id), "sha256": target.sha256}); evidence_hash = target.sha256
        elif kind == "RAW_RECORD":
            run = self.db.get(EvidenceParseRun, target.parse_run_id); fields.update({"evidence_id": str(target.evidence_id), "ordinal": target.ordinal, "content_type": target.content_type}); producer, version = run.parser_name, run.parser_version
        elif kind == "EVENT": fields.update({"raw_record_id": str(target.raw_record_id), "ordinal": target.ordinal}); producer, version = target.normalizer_name, target.normalizer_version
        elif kind in {"ENTITY_OBSERVATION", "INDICATOR_OCCURRENCE"}: fields.update({"raw_record_id": str(target.raw_record_id), "ordinal": target.occurrence_ordinal}); producer, version = target.extractor_name, target.extractor_version
        elif kind == "ENTITY_RELATIONSHIP": fields.update({"source_locator_hash": target.source_locator_hash}); producer, version = target.derivation_name, target.derivation_version
        elif kind == "CANONICAL_ALERT": fields.update({"source": target.source, "source_alert_id": target.source_alert_id}); producer = target.normalizer_version
        elif kind == "ALERT_CLUSTER_MEMBERSHIP": fields.update({"cluster_id": str(target.cluster_id), "correlation_version": target.correlation_version}); producer = target.correlation_version
        elif kind == "ALERT_CLUSTER_ASSESSMENT": fields.update({"cluster_id": str(target.cluster_id), "scoring_version": target.scoring_version}); producer = target.scoring_version
        elif kind == "ALERT_CLUSTER_PROMOTION": fields.update({"cluster_id": str(target.cluster_id), "export_version": target.export_version}); producer = target.export_version
        elif kind == "FINDING": fields.update({"status": target.status})
        elif kind == "MITRE_MAPPING": fields.update({"technique_id": target.technique_id, "status": target.status})
        return fields, producer, version, evidence_hash
