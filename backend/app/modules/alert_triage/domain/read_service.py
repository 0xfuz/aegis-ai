"""Persisted, bounded alert-triage projections; never recomputes Phase 7 state."""
from __future__ import annotations
from uuid import UUID
from sqlalchemy import desc, select
from sqlalchemy.orm import Session
from app.modules.alert_triage.domain.correlation_service import CORRELATION_VERSION
from app.modules.alert_triage.domain.correlation_v2_service import CORRELATION_V2_VERSION
from app.modules.alert_triage.infrastructure.models import AlertCluster, AlertClusterAssessment, AlertClusterMembership, AlertClusterPromotion
from app.shared.exceptions import NotFoundError

class AlertClusterTriageReadService:
    def __init__(self, db: Session): self.db = db
    def list(self, org_id: UUID, limit: int, offset: int) -> list[dict]:
        rows=self.db.scalars(select(AlertCluster).where(AlertCluster.org_id==org_id).order_by(desc(AlertCluster.updated_at),desc(AlertCluster.id)).limit(limit).offset(offset)).all()
        return [self._project(org_id,row,False) for row in rows]
    def get(self, org_id: UUID, cluster_id: UUID) -> dict:
        row=self.db.scalar(select(AlertCluster).where(AlertCluster.org_id==org_id,AlertCluster.id==cluster_id))
        if row is None: raise NotFoundError("Alert cluster not found.")
        return self._project(org_id,row,True)
    def _project(self,org_id:UUID,cluster:AlertCluster,include_members:bool)->dict:
        assessment=self.db.scalar(select(AlertClusterAssessment).where(AlertClusterAssessment.org_id==org_id,AlertClusterAssessment.cluster_id==cluster.id).order_by(desc(AlertClusterAssessment.evaluated_at),desc(AlertClusterAssessment.id)))
        promotion=self.db.scalar(select(AlertClusterPromotion).where(AlertClusterPromotion.org_id==org_id,AlertClusterPromotion.cluster_id==cluster.id))
        members=self.db.scalars(select(AlertClusterMembership).where(AlertClusterMembership.org_id==org_id,AlertClusterMembership.cluster_id==cluster.id,AlertClusterMembership.correlation_version==cluster.correlation_version).order_by(AlertClusterMembership.added_at,AlertClusterMembership.id).limit(50)).all() if include_members else []
        eligible,reason=self._eligibility(cluster,assessment,promotion)
        return {"id":str(cluster.id),"correlation_version":cluster.correlation_version,"status":cluster.status,"created_at":cluster.created_at.isoformat(),"updated_at":cluster.updated_at.isoformat(),"member_count":cluster.member_count,"members":[{"id":str(m.id),"score":m.score,"reasons":m.reasons,"added_at":m.added_at.isoformat()} for m in members],"triage":None if assessment is None else {"id":str(assessment.id),"priority":assessment.priority,"score":assessment.score,"version":assessment.scoring_version},"promotion":None if promotion is None else {"id":str(promotion.id),"status":promotion.status,"investigation_id":str(promotion.investigation_id)},"promotion_eligible":eligible,"promotion_reason":reason}
    @staticmethod
    def _eligibility(cluster,assessment,promotion):
        if promotion is not None:return False,"ALREADY_PROMOTED"
        # Promotion itself supports the two certified, persisted correlation
        # histories.  The surface must not silently strand existing v1
        # clusters, nor attempt a fallback for unknown versions.
        if cluster.correlation_version not in {CORRELATION_VERSION, CORRELATION_V2_VERSION}:
            return False,"CORRELATION_VERSION_UNSUPPORTED"
        if cluster.status!="OPEN":return False,"CLUSTER_NOT_OPEN"
        if assessment is None or assessment.cluster_id!=cluster.id:return False,"TRIAGE_REQUIRED"
        return True,"ELIGIBLE"
