# Contributing to Aegis AI

Aegis AI is currently a private controlled-pilot project. Source access is
granted only by the owner to verified reviewers. Do not redistribute the
repository, screenshots, evidence, credentials, or evaluator materials.

## Before proposing a change

1. Start from the approved commit and use a clean worktree.
2. Read the relevant contract and keep changes within its authority boundary.
3. Use synthetic fixtures only. Never add raw telemetry, customer data,
   passwords, tokens, secret files, database dumps, prompt/provider output, or
   runtime artifacts.
4. Do not change migrations, correlation, triage, authentication, MITRE, AI
   authority, or release tags without explicit scoped approval.

## Validation and handoff

Run the focused tests and static checks appropriate to the change. Keep
generated files, `node_modules`, `.next`, coverage, logs, local environment
files, secret directories, and Docker runtime artifacts out of Git. Use
protected operator-owned files outside the checkout for any local secrets.

There is currently no public vulnerability-reporting channel. Send possible
security issues only through the owner-approved private contact path that
accompanied your evaluator access; do not open a public issue or include
sensitive material in a patch.
