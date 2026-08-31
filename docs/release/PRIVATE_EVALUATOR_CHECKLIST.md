# Private evaluator checklist

Use this checklist before granting a verified technical evaluator access to the
private repository. It is not a public distribution checklist.

## Before access

- Confirm the evaluator has a supported Linux host, Git, Docker Engine with
  Compose v2, `openssl`, and `curl`.
- Share the exact approved commit and ask the evaluator to use a fresh clone.
- Confirm that the evaluator will create their own local state directory,
  bootstrap identity, and secrets. Do not share R4, benchmark, or another
  operator's runtime files.
- Explain that there is no fixed administrator account, demo account, or
  production synthetic-data path.

## Core evaluation

- Follow the [Core-mode quickstart](DEPLOYMENT_QUICKSTART.md) through
  protected secret materialization, Compose validation, migration `0024`,
  administrator bootstrap, login, and required password rotation.
- Verify API and frontend health endpoints on the evaluator's chosen loopback
  ports.
- Confirm a later self-service password change at **Settings → Security**
  clears the browser session and requires a fresh sign-in.
- Stop and restart the exact Compose project without deleting its volumes; the
  PostgreSQL state and rotated administrator login should persist.

## Optional paths and limits

- Core mode does not require Wazuh, Ollama, worker, beat, or AI execution.
- Wazuh is the only externally validated integration and needs separately
  configured forwarder/TLS/Manager materials.
- AI output is advisory and reviewable. AI-suggested MITRE techniques are not
  canonical until analyst review confirms them.
- The preserved V1-B3 campaign did not complete 300/300 events at five events
  per second. Do not infer a supported rate, enterprise readiness, high
  availability, or compliance status.

## Safe evaluator feedback

- Report only bounded reproduction steps and safe error categories.
- Do not include passwords, tokens, secret files, request bodies, raw Wazuh
  telemetry, evidence exports, prompts, provider output, or database dumps.
- This private repository has no public vulnerability-reporting channel.
  Report a potential security issue only through the owner-approved private
  contact path supplied with evaluator access.
