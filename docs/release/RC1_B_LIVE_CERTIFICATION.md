# RC1-B Live Operational Acceptance and Certification

## Certified source

- Branch: `release-readiness`
- Final pre-document source: `909ba2b5eaa67e1f50316df58c18d9d3a6e00fbc`
- Migration: one head at `0024`
- Phase 8 baseline: `phase8-certified` remains
  `35014ff47878b95d1b0a7a08bba45e66f1c885a9`.
- RC1-A offline certification remains the durable full-suite reference.

## Live acceptance

The preserved R4 deployment used named PostgreSQL, evidence, Redis and model
volumes with file-mounted secrets. No authoritative volume was recreated.

- TLS expiry was detected before forwarder delivery; a locally protected,
  CA/SAN-valid replacement was installed without weakening verification.
- Wazuh Vulnerability Detection was disabled only in the disposable acceptance
  Manager. `vd_updater` stayed absent and its temporary workspace remained
  bounded.
- Rule 502 telemetry was classified correctly: one persisted chain per actual
  Manager start. Recovery of an earlier pending startup delivery and a later
  Manager start are distinct source identities, not a replay loop.
- One benign documented Rule 100500 event produced one RawEvent, one
  CanonicalAlert, one `correlation-v2` membership, and one persisted triage
  assessment. No `correlation-v1` membership was created.
- One exact documented forwarder replay increased RawEvent receipt history and
  the original alert occurrence only; it created no CanonicalAlert, membership,
  triage, promotion, Investigation, claim, citation, Finding, MITRE mapping,
  action, or provider side effect.
- A controlled stateless/runtime restart preserved migration `0024`, all
  accepted records, empty execution queues, and frontend/API availability.

## Owner and authority acceptance

The owner completed authenticated presentation acceptance without creating or
reviewing authority records. The bounded MITRE read contract was subsequently
rechecked: the workspace uses only `GET /investigations/{id}/mitre`; the
separate certified `POST /mitre-mappings/{id}/review` action remains the sole
analyst-review write path.

No automatic Finding, MITRE confirmation, RecommendedAction, promotion,
correlation, triage, or provider action occurred during the live checks.

## Recovery rehearsal

The protected RC1-B backup passed checksums and restored into a new isolated
`aegis-restore-rc1b` namespace. The restored database reached `0024`, retained
zero v1 memberships, and preserved safe aggregate provenance counts. The
evidence archive retained two files with a matching aggregate digest. The
isolated containers, network, volumes, and empty restore spool were removed;
the protected backup remains retained for release recovery.

## Regression and security gates

| Gate | Result |
| --- | --- |
| RC1-A durable backend suite | 492 passed, 0 failed, 0 skipped, 235 warnings |
| RC1-B release-operations regression | 4 passed |
| RC1-B full frontend suite | 122 passed, 29 files |
| RC1-B focused MITRE/Findings/Intelligence UI | 24 passed, 4 files |
| Frontend typecheck/lint/build | PASS; lint had no warnings |
| Compose, disabled and enabled execution profiles | PASS |
| Live and restored migration revision | `0024` |
| Secret scan | no high-confidence tracked/history candidates |

The backend production implementation is unchanged since RC1-A. The only
post-RC1-A backend modification is the passing release-operations static test;
frontend changes were rerun through the complete frontend gate.

## Boundaries and limitations

This release remains private-by-default and requires an external TLS ingress
for public deployment. Ollama readiness was non-generative; no model download
or provider generation was performed in RC1-B. The Wazuh acceptance uses the
documented benign agentless/syslog path and does not claim production-scale
performance. Redis remains non-authoritative and rebuildable.

## Safe final state

After tagging, the R4 runtime is stopped using the documented dependency-safe
order. Named authoritative volumes, protected checkpoint, and RC1-B backup are
preserved. Only disposable restore/test resources are removed.
