# DocIntel

DocIntel is a planned AI-powered business document intelligence workspace. The
repository currently contains the Phase 2 platform foundation only: a
PostgreSQL/pgvector database, an Alembic migration, a FastAPI health surface,
and a minimal React/Vite operational shell.

Document upload, extraction, chunking, embeddings, retrieval, question
answering, citations, PDF viewing, and the finished visual interface are
intentionally not implemented yet.

## Foundation architecture

```text
Browser
  |
  v
React + TypeScript + Vite ----> FastAPI /api/v1/health/*
                                      |
                                      v
                              PostgreSQL + pgvector

Host persistence:
E:\DocIntelData\postgres
E:\DocIntelData\uploads
E:\DocIntelData\processed
E:\DocIntelData\samples
E:\DocIntelData\backups
```

The application is a modular monolith. The API and future durable worker share
one Python codebase and PostgreSQL system of record. The worker is deliberately
deferred until the secure document lifecycle phase creates real work for it.

See [docs/architecture.md](docs/architecture.md) for the Phase 2 boundaries and
readiness contract.

## Prerequisites

- Docker Desktop with Docker Compose
- Node.js 24 or newer for running frontend checks outside Docker
- Python 3.13 for running backend checks outside Docker

Docker is the supported local path on Windows. Project-owned persistent data is
kept outside the repository under `E:\DocIntelData` through configurable bind
mounts.

## Configure

The repository does not track a real `.env`.

PowerShell:

```powershell
Copy-Item .env.example .env
```

Bash:

```bash
cp .env.example .env
```

Review the values before starting services. The checked-in example is already
configured for:

```text
E:/DocIntelData/postgres
E:/DocIntelData/uploads
E:/DocIntelData/processed
E:/DocIntelData/samples
E:/DocIntelData/backups
```

When using WSL without Docker Desktop path conversion, use `/mnt/e/...`
equivalents instead.

## Run with Docker

```powershell
docker compose up --build
```

The migration service runs once, then the API and web services start.

- Web foundation: <http://localhost:5173>
- API documentation: <http://localhost:8000/docs>
- Liveness: <http://localhost:8000/api/v1/health/live>
- Readiness: <http://localhost:8000/api/v1/health/ready>

Stop the services without deleting persistent data:

```powershell
docker compose down
```

Do not add `--volumes`: storage uses E: drive bind mounts, and PostgreSQL data
is intentionally persistent.

## Run checks

Backend, with Python available:

```powershell
python -m pip install -e "apps/api[dev]"
python -m ruff format --check apps/api
python -m ruff check apps/api
python -m mypy apps/api/src apps/api/tests
python -m pytest apps/api/tests/unit
```

Frontend:

```powershell
npm.cmd --prefix apps/web ci
npm.cmd --prefix apps/web run lint
npm.cmd --prefix apps/web run typecheck
npm.cmd --prefix apps/web run test
npm.cmd --prefix apps/web run build
```

The GitHub Actions workflow runs the same static checks and tests, upgrades a
clean pgvector database, and exercises the integration readiness check.

## Readiness behavior

`GET /api/v1/health/live` checks only that the API process is responsive.

`GET /api/v1/health/ready` returns HTTP 200 only when:

- PostgreSQL accepts a query.
- The `vector` extension is installed.
- The database is at the expected Alembic revision.
- upload, processed, sample, and backup paths have the required access.
- the selected AI provider configuration is valid.

Provider readiness is configuration-only. The default `mock` selection is
deterministic and makes no network or paid provider request.

## Current limitations

This is intentionally a foundation release. It has no document or AI workflow,
no worker, no authentication, and no production deployment configuration. The
basic web page exists only to expose platform health while later phases are
built.
