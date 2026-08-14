# Production image inventory (R2)

| Service | Image | State |
| --- | --- | --- |
| PostgreSQL | `postgres:16.4-alpine` | Authoritative named data volume |
| Redis | `redis:7.4.2-alpine` | Non-authoritative broker/cache |
| Backend API, migrate, worker, beat, bootstrap | repository `backend/Dockerfile`, base `python:3.12.7-slim` | Built from the certified source tree |
| Frontend | repository `frontend/Dockerfile`, base `node:20.18.1-slim` | Built from the certified source tree |
| Optional Ollama | `ollama/ollama@sha256:4dea9fb511947e24a84237bb636b0203abcb2ff0d3fbc7b4ff865deb91362131` | Runtime only; model volume is preserved |

R2 does not update application dependencies or pull models. Image tag/digest
changes are a separately reviewed release operation.
