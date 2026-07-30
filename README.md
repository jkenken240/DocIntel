# DocIntel

DocIntel is a planned AI-powered business document intelligence workspace. The
repository currently contains the Phase 4 deterministic processing pipeline: a
PostgreSQL/pgvector system of record, durable lifecycle jobs, protected local
PDF storage, deterministic PyMuPDF extraction and chunking, offline mock
embeddings, a FastAPI document API, and a lifecycle worker.

Vector retrieval, question answering, citations, OCR, PDF viewer UI, and the
finished visual interface are intentionally not implemented yet.

## Current architecture

```text
Browser
  |
  v
React + TypeScript + Vite ----> FastAPI /api/v1
                                  |        |
                                  v        v
                         PostgreSQL    protected PDF storage
                              ^
                              |
                  lifecycle worker
             (processing + deletion)

Host persistence:
E:\DocIntelData\postgres
E:\DocIntelData\uploads
E:\DocIntelData\processed
E:\DocIntelData\samples
E:\DocIntelData\backups
```

The application is a modular monolith. The API and lifecycle worker share one
Python codebase and PostgreSQL system of record. The worker claims processing
and deletion jobs durably with leases and PostgreSQL row locking.

See [docs/architecture.md](docs/architecture.md) for the Phase 4 boundaries,
lifecycle invariants, and API contract.

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

The migration service runs once, then the API, lifecycle worker, and web
services start.

- Web foundation: <http://localhost:5173>
- API documentation: <http://localhost:8000/docs>
- Liveness: <http://localhost:8000/api/v1/health/live>
- Readiness: <http://localhost:8000/api/v1/health/ready>

## Document API

All document routes are under `/api/v1/documents`:

- `POST /` uploads exactly one PDF as the multipart `file` field and returns
  HTTP 202.
- `GET /` lists documents with cursor pagination, search, status filters, and
  sorting.
- `GET /{document_id}` returns document metadata.
- `GET /{document_id}/status` returns compact lifecycle progress.
- `GET /{document_id}/content` streams protected inline PDF content and
  supports ETags and one byte range.
- `DELETE /{document_id}` durably requests deletion and returns HTTP 202.
- `POST /{document_id}/retry` retries only a failed, retryable processing
  revision and returns HTTP 202.

Uploads default to a 25 MiB limit. They are streamed through a bounded buffer,
validated for `.pdf`, `application/pdf`, and the `%PDF-` signature, hashed with
SHA-256, and atomically finalized under a server-generated UUID key. The
filename supplied by the client is retained only as sanitized display metadata.
The worker validates PDFs with PyMuPDF, preserves one-based pages, produces
page-contained deterministic character chunks, and writes normalized
1,536-dimensional mock vectors without network access.

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

Database-backed tests run against a migrated PostgreSQL/pgvector service:

```powershell
$env:DOCINTEL_RUN_INTEGRATION = "1"
python -m pytest apps/api/tests/integration
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

Phase 4 deliberately stops at `READY` documents with pages, chunks, and mock
vectors. It does not perform vector retrieval, semantic search, question
answering, evidence selection, citation generation, OCR, or live AI-provider
calls. Authentication, the PDF viewer, document-library UI, and production
deployment configuration are also deferred.
