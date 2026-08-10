# Wazuh Live Lab

Disposable Docker lab: Wazuh Manager 4.9.2, Ubuntu 22.04 with official Wazuh Agent 4.9.2-1, and the existing Aegis backend/PostgreSQL. Agent `001` (`lab-agent`) was Active. A safe `/etc/aegis-lab-safe-fim-marker` was created; scheduled FIM did not emit immediately. A real benign Agent SCA alert was used instead: ID `1786337922.1372612`, rule `19004`, level 7, decoder `sca`.

The unchanged alert flowed through the standalone forwarder to Aegis as CanonicalAlert `6696fcd9-6443-4c84-a09a-fb942bdd5b76`, RawEvent `e4913cc0-408d-42d4-a9f8-84def1149308`, and v2 cluster `ccdf21a1-a9ff-4133-96c7-6c03251fa16a`, with one triage assessment. Exact replay produced two occurrences and no additional canonical alert, membership, or assessment.

Outage validation disconnected only the disposable Agent from the backend network. The record persisted as `CONNECTION_OR_TIMEOUT`, attempt 1, with natural ~5.7-second retry delay; after reconnection it delivered as CanonicalAlert `fe82dc73-68c0-4889-9dcb-286d1e1d90e8` / RawEvent `101a97cc-3281-4cbd-9232-4b645af7af55`, v2 only. Invalid lab-only credentials produced HTTP 401 and quarantine without persistence; the intentional artifact was removed.

Observed values are lab observations only, not production performance. No Investigation, FACT, AIIE, Finding, confirmed MITRE mapping, promotion, or v1 membership was created. Secrets were absent from inspected spool/quarantine data. HTTPS/proxy/mTLS deployment controls remain outside this lab.
