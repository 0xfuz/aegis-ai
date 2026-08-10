# Aegis-AI S1 Threat Model

## Trust boundaries

`External alert producer → generic webhook → connector authentication → RawEvent → CanonicalAlert → dedupe/correlation/triage → analyst-controlled promotion → Investigation → Evidence → FACT → AIIE → frontend`.

Additional boundaries are browser→API (JWT/RBAC), backend→PostgreSQL, backend→Redis, backend→Ollama, and backend→controlled evidence storage. Raw alerts/evidence are untrusted at every downstream stage; only analyst review may create Findings or confirm MITRE mappings.

## Threat actors

- Unauthenticated attacker: probes public health/auth/connector-ingest surfaces and attempts resource exhaustion.
- Compromised connector or malicious alert producer: can submit authenticated but adversarial detection text and replay volume.
- Authenticated analyst: may attempt cross-organization UUID access or misuse permitted mutation routes.
- Malicious tenant user: attempts BOLA/IDOR across case, evidence, intelligence, and audit resources.
- Compromised evidence source: supplies malformed, oversized, path-like, or prompt-injection evidence.

## Security objectives

Tenant scope must originate from the JWT or authenticated connector, canonical FACTs must arise only from evidence ingestion, AIIE remains append-only/reviewable, and untrusted text cannot create analyst verdicts, MITRE confirmation, or promotion authority.
