# Correlation-v2 Implementation

`correlation-v2` is separate from v1. Alembic 0019 makes memberships unique per `(alert_id, correlation_version)`, preserving all prior v1 history. V2 ledger stores version, score, positive families, discriminator codes, and decision result in membership reasons.

V2 requires observed time within 180 seconds, net score at least 8, and two non-time positive families. Host=2, account=3, process=3, destination/domain=3, time=1. Host/IP/category/severity/title/metadata alone cannot merge. Different user, process, destination/domain, and independent rule family without process/destination continuity veto correlation.

Cluster admission requires compatibility with the earliest deterministic representative and a majority quorum of existing members. No root-to-root bridge merge occurs, preventing transitive fusion.
