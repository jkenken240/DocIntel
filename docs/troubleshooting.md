# Troubleshooting

## Bootstrap says Docker is unavailable

Start Docker Desktop, select the Linux container engine, then verify:

```powershell
docker info --format '{{.OSType}}'
docker compose version
```

The first command must return `linux`. The bootstrap does not change Docker
Desktop, WSL, Node, Python, npm, or global storage settings.

## Compose reports missing variables

Run the idempotent bootstrap from the repository root:

```powershell
.\scripts\bootstrap.ps1
```

If Windows reports that script execution is disabled, run the reviewed script
with a process-only bypass. It does not modify the machine or user policy:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\bootstrap.ps1
```

It creates `.env` only when absent. If `.env` already exists, it is preserved;
compare it manually with `.env.example` and retain local credentials outside
Git.

## Readiness returns HTTP 503

Inspect the bounded component report:

```powershell
Invoke-RestMethod http://localhost:8000/api/v1/health/ready | ConvertTo-Json -Depth 6
docker compose ps
```

- `database`: PostgreSQL query failed; inspect `docker compose logs --tail 100 db`.
- `pgvector`: the extension is absent or inaccessible; confirm the migration
  service completed.
- `migration`: run `docker compose run --rm migrate` and confirm revision
  `20260730_0004` without resetting the database.
- `storage`: confirm the configured root and its `uploads`, `processed`,
  `samples`, and `backups` access. Do not loosen normal-data permissions
  broadly.
- `provider`: configuration is incomplete or incompatible. The default mock
  provider needs no key.

Routine API responses intentionally sanitize internal exceptions. Use the
returned trace ID to correlate bounded local logs.

## A PDF fails processing

The upload endpoint performs inexpensive extension, MIME-hint, signature, and
size checks. The worker then rejects encrypted, malformed, over-500-page, and
no-extractable-text PDFs. OCR is not available, so an image-only scan fails
with `NO_EXTRACTABLE_TEXT`. A permanent validation failure is not retryable.

Blank pages are allowed when another page has extractable text, and original
one-based page numbering is preserved.

## A question returns insufficient evidence

This is a deliberate grounded result, not an application crash. Confirm:

- at least one selected document is `READY`;
- explicitly selected documents share one compatible active embedding space;
- the question asks for information actually present in the documents;
- no selected source is deleting or stale.

DocIntel does not add below-threshold chunks just to fill the evidence set and
does not expose rejected provider output.

## A citation opens the page but has no visual highlight

This is expected. The backend proves citations with normalized page text,
page-relative offsets, exact excerpts, hashes, and processing revision. PDF
geometry is not stored, so the viewer opens the correct original page while the
exact selectable excerpt remains in the evidence panel. It never guesses a
highlight rectangle.

## The PDF viewer fails to load

Confirm the source was not deleted, the API content endpoint responds, and the
web container is serving its production assets:

```powershell
docker compose ps
docker compose logs --tail 100 web api
```

The viewer exposes only bounded safe failure codes to the UI. It does not show
exception messages, storage paths, request headers, or PDF bytes.

## A successful upload row remains visible

An accepted minor v1.0 limitation can leave a successful upload row visible
until the page is refreshed. The authoritative checks are that the server
returned HTTP 202, the document appears in the library, and lifecycle state
progresses. Refreshing clears the stale row. This does not indicate that the
PDF is uploading again.

## Data preservation and cleanup

Normal persistent data is under the configured E-drive root. `docker compose
down` removes containers and the project network but not bind-mounted files.
Never use `git clean`, Docker pruning, or a broad recursive delete as an
application reset.

For an isolated validation project, record the exact Compose project name and
absolute data root before startup. Bring down only that project, verify no
matching labeled containers or network remain, then remove only the exact
validated root. Reject symlinks, relative paths, repository paths, drive roots,
and mismatches before elevated deletion.
