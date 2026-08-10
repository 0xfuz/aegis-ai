"""Conservative deterministic correlation-v2; v1 remains untouched."""
from __future__ import annotations
from datetime import datetime, timedelta, timezone
from uuid import UUID
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.modules.alert_triage.infrastructure.models import AlertCluster, AlertClusterMembership, AlertDeduplicationDecision, CanonicalAlert
from app.shared.exceptions import NotFoundError

CORRELATION_V2_VERSION="correlation-v2"; WINDOW=timedelta(seconds=180)

class AlertCorrelationV2Service:
 def __init__(self,db:Session): self.db=db
 def process(self,org:UUID,alert_id:UUID):
  a=self._alert(org,alert_id)
  if self.db.scalar(select(AlertDeduplicationDecision.id).where(AlertDeduplicationDecision.org_id==org,AlertDeduplicationDecision.duplicate_alert_id==a.id,AlertDeduplicationDecision.decision_type=="SEMANTIC")): return None
  old=self.db.scalar(select(AlertClusterMembership).where(AlertClusterMembership.org_id==org,AlertClusterMembership.alert_id==a.id,AlertClusterMembership.correlation_version==CORRELATION_V2_VERSION))
  if old:return self.db.get(AlertCluster,old.cluster_id)
  roots=list(self.db.scalars(select(AlertCluster).where(AlertCluster.org_id==org,AlertCluster.correlation_version==CORRELATION_V2_VERSION,AlertCluster.status=="OPEN")))
  candidates=[]
  for c in roots:
   members=list(self.db.scalars(select(AlertClusterMembership).where(AlertClusterMembership.cluster_id==c.id,AlertClusterMembership.correlation_version==CORRELATION_V2_VERSION)))
   alerts=[self._alert(org,m.alert_id) for m in members]
   rep=min(alerts,key=lambda x:(x.observed_at,str(x.id)))
   ledger=self._decision(a,rep)
   compatible=[self._decision(a,x) for x in alerts]
   if ledger["merge"] and sum(x["merge"] for x in compatible)*2>=len(compatible): candidates.append((c,ledger))
  if not candidates:
   c=AlertCluster(org_id=org,identity_key=f"{CORRELATION_V2_VERSION}:alert:{a.id}",correlation_version=CORRELATION_V2_VERSION,status="OPEN",first_seen=a.observed_at,last_seen=a.observed_at,member_count=0,source_diversity=0);self.db.add(c);self.db.flush();ledger={"version":CORRELATION_V2_VERSION,"score":0,"positive":[],"discriminators":[],"merge":False,"code":"INITIAL_CLUSTER"}
  else: c,ledger=min(candidates,key=lambda x:x[0].identity_key)
  self.db.add(AlertClusterMembership(org_id=org,cluster_id=c.id,alert_id=a.id,candidate_alert_id=None,correlation_version=CORRELATION_V2_VERSION,score=ledger["score"],reasons=[ledger],added_at=datetime.now(timezone.utc)));self.db.flush()
  members=list(self.db.scalars(select(AlertClusterMembership).where(AlertClusterMembership.cluster_id==c.id,AlertClusterMembership.correlation_version==CORRELATION_V2_VERSION)))
  alerts=[self._alert(org,m.alert_id) for m in members];c.member_count=len(alerts);c.first_seen=min(x.observed_at for x in alerts);c.last_seen=max(x.observed_at for x in alerts);c.source_diversity=len({(x.connector_id,x.source) for x in alerts});self.db.commit();return c
 def _decision(self,a,b):
  o=a.normalized_observables; p=b.normalized_observables; pos=[]; disc=[]; score=0
  if abs((a.observed_at-b.observed_at).total_seconds())>WINDOW.total_seconds(): return {"version":CORRELATION_V2_VERSION,"score":0,"positive":[],"discriminators":["OUTSIDE_WINDOW"],"merge":False}
  for key,pts,fam in (("hostname",2,"host"),("username",3,"account"),("process",3,"process"),("destination_ip",3,"destination"),("domain",3,"destination")):
   if o.get(key) and o.get(key)==p.get(key):score+=pts;pos.append(fam)
  if o.get("username") and p.get("username") and o["username"]!=p["username"]:disc.append("DIFFERENT_USER")
  if o.get("process") and p.get("process") and o["process"]!=p["process"]:disc.append("INCOMPATIBLE_PROCESS")
  if (o.get("destination_ip") and p.get("destination_ip") and o["destination_ip"]!=p["destination_ip"]) or (o.get("domain") and p.get("domain") and o["domain"]!=p["domain"]):disc.append("DESTINATION_CONFLICT")
  if a.rule_id and b.rule_id and a.rule_id!=b.rule_id and not ({"process","destination"}&set(pos)):disc.append("INDEPENDENT_RULE_FAMILY")
  score+=1;pos.append("time")
  return {"version":CORRELATION_V2_VERSION,"score":score,"positive":sorted(set(pos)),"discriminators":disc,"merge":not disc and score>=8 and len(set(pos)-{"time"})>=2}
 def _alert(self,org,id):
  a=self.db.scalar(select(CanonicalAlert).where(CanonicalAlert.org_id==org,CanonicalAlert.id==id))
  if not a:raise NotFoundError("Canonical alert not found.")
  return a
