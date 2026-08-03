# Changelog

All notable changes to DocIntel are recorded here. The project uses semantic
versioning for application release identity; database, processing, chunker,
provider, and API-contract identifiers are versioned independently.

## [1.0.0] - 2026-08-03

### Added

- Secure bounded PDF upload, protected local storage, lifecycle records,
  inline content delivery, byte ranges, ETags, and durable deletion.
- PyMuPDF validation and page-correct extraction, deterministic chunking,
  offline 1,536-dimensional mock embeddings, durable worker leases, retries,
  cancellation, and reconciliation.
- Compatible pgvector retrieval, deterministic diversity controls, immutable
  evidence snapshots, structured grounded answers, claim-level citations, and
  support verification.
- Responsive professional workspace for overview, uploads, document lifecycle,
  source selection, grounded questions, evidence navigation, and PDF.js source
  pages.
- Production backend and nginx frontend images, loopback-hardened Compose,
  frozen Python locks, idempotent PowerShell bootstrap, and isolated storage
  overrides.
- Desktop/mobile Playwright verification, eleven important-state axe scans,
  production PDF.js checks, audits, clean migration checks, and guarded CI
  teardown.
- Deterministic fictional demo-document generator, release documentation,
  security guidance, troubleshooting, validation checklist, and portfolio
  screenshots.

### Security

- Client filenames are display-only; storage uses generated UUID keys.
- Retrieved PDF text is handled as untrusted data, not provider instructions.
- Citations are independently revalidated against exact page slices and hashes.
- Default publishing is loopback-only and mock providers require no secrets or
  external requests.

### Known limitations

- Local unauthenticated portfolio application; not approved for public
  exposure or production SaaS use.
- PDF only; no OCR for image-only documents.
- No persisted PDF geometry or guessed on-page text highlights.
- A successful upload row can occasionally remain visible until refresh even
  though authoritative upload and lifecycle state are correct.
- Live OpenAI-compatible interoperability is optional and was not exercised by
  release validation.
