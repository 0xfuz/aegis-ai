# Phase 7 Known Limitations

- Correlation metrics use a synthetic labeled adversarial corpus; they are not production-world detection accuracy.
- Correlation-v2 has not been validated against broad real-world telemetry.
- Sparse telemetry can remain LOW/MEDIUM and conservatively separate.
- The Wazuh live lab covered one Manager/Agent and limited benign SCA telemetry; it is not a production rollout.
- Forwarder monitoring, alerting, production secret rotation, and operator quarantine workflow remain future work.
- Production ingress/reverse-proxy body and connection controls, network allowlisting/mTLS, distributed rate limiting/backpressure, access-token invalidation, connector source allowlists, and CI SCA/SBOM policy remain deployment/deferred hardening responsibilities.
