# DocIntel v1.0 release validation

This checklist separates reproducible automated evidence from the final
owner-performed native Windows browser gate.

## Automated quality gates

### Backend

From `apps/api`, install the frozen sets separately and build the package:

```powershell
python -m pip install --require-hashes -r requirements.lock
python -m pip install --require-hashes -r requirements-dev.lock
python -m build
python -m ruff format --check .
python -m ruff check .
python -m mypy src tests
python -m pytest tests/unit
python -m pip_audit -r requirements.lock --disable-pip
```

Import the built wheel in a clean virtual environment with the frozen runtime
set. Against a migrated PostgreSQL/pgvector database, run:

```powershell
$env:DOCINTEL_RUN_INTEGRATION = "1"
python -m pytest tests/integration
alembic upgrade head
alembic current
alembic check
```

The required head is `20260730_0004`.

### Frontend

From `apps/web`:

```powershell
npm.cmd ci
npm.cmd audit --audit-level=high
npm.cmd run lint
npm.cmd run typecheck
npm.cmd run test
npm.cmd run build
```

### Production Compose and browsers

Use a unique Compose project, loopback-only ports, mock providers, and a fresh
absolute data root outside normal storage. Validate and build:

```powershell
docker compose config --quiet
docker compose build
```

Start `db`, `migrate`, `api`, `worker`, and `web`; confirm PostgreSQL,
pgvector, migration, storage, provider, API, worker, and web health; then run
the committed desktop and mobile Playwright projects against nginx:

```powershell
npm.cmd --prefix apps/web run test:e2e
```

The browser suite must cover upload, `READY`, search/filter, explicit source
selection, grounded claims/citations, exact evidence and PDF page navigation,
insufficient evidence, confirmation-dialog keyboard behavior, source deletion,
dependent-result invalidation, mobile routes, reduced motion, and axe scans.

Failure artifacts are diagnostic only. Successful validation must leave no
reports, traces, screenshots, videos, generated PDFs, databases, credentials,
or other build outputs in Git.

## Demo-generator verification

Generate into two fresh absolute directories and compare the files by name and
SHA-256. Each file must be a valid unencrypted three-page PDF, render without
layout defects, contain the documented page-correct facts, and match the hashes
in [demo-workflow.md](demo-workflow.md).

Also test these safe failures:

- relative output path;
- repository path;
- broad drive/root path;
- symlinked path component;
- unrelated existing entry;
- different existing known filename.

## Repository hygiene

Before checkpointing:

```powershell
git status --short
git diff --check
git diff --name-only
```

Confirm there are no real `.env` files, credentials, API keys, uploaded PDFs,
databases, `.part` files, dependency directories, build output, browser
artifacts, temporary screenshots, or persistent E-drive data in the commit.
Exactly three reviewed final PNG screenshots belong under
`docs/assets/screenshots/`.

## Owner-only native Windows acceptance

The owner performs this gate in the ordinary Windows browser against a freshly
bootstrapped isolated E-drive root. Playwright `setInputFiles` or another
programmatic transfer does not satisfy the native file-picker step.

If the host blocks direct script execution, bootstrap with the process-scoped
form below; it does not modify the global or user execution policy:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\bootstrap.ps1 -DataRoot E:\DocIntelV1Validation\data
```

1. Open `http://localhost:5173/documents` in the normal browser.
2. Activate **Choose PDF files** and use the native Windows file picker to
   select both generated demo PDFs.
3. Confirm each selected file enters a truthful queued/uploading state.
4. Confirm each accepted HTTP 202 upload appears in the library without a page
   refresh and reaches `READY`.
5. Confirm no file remains falsely active. The accepted limitation is that a
   successful row may remain visible until refresh; it must not imply another
   server upload.
6. Search, filter, select both sources, and ask the documented cross-document
   question.
7. Validate every material claim, citation filename, original page, exact
   excerpt, and visibly rendered PDF page.
8. Ask the documented unsupported question and confirm the deliberate refusal.
9. Delete one cited source and confirm dependent-result invalidation.
10. Check keyboard navigation, modal focus trap/restoration, live
    announcements, reduced motion, and desktop/mobile responsive layouts.
11. Restart Compose and confirm intended persistence.
12. Confirm mock-provider operation with no key and no paid request.
13. Bring down and remove only the isolated project and exact verified data
    root.

The release candidate must stop before commit until the owner confirms this
native file-picker gate.
