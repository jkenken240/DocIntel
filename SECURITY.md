# Security policy

## Supported use

DocIntel v1.0 is supported as a local, single-operator, unauthenticated
portfolio application on the documented Docker Compose topology. Database,
API, and web ports bind to `127.0.0.1` by default.

Do not expose DocIntel to a LAN, public address, reverse proxy, or shared host
without adding authentication, authorization, TLS, rate limiting, monitoring,
tenant isolation where applicable, and an additional security review. The
current release is not a production SaaS security boundary.

## Sensitive data

Uploaded PDFs, normalized page text, chunks, embeddings, evidence snapshots,
questions, answers, and backups can all contain sensitive information. Protect
the configured data root as a single sensitive asset:

```text
E:\DocIntelData\postgres
E:\DocIntelData\uploads
E:\DocIntelData\processed
E:\DocIntelData\samples
E:\DocIntelData\backups
```

Use only fictional documents for public demonstrations. DocIntel does not
encrypt storage at rest or manage OS-level permissions, disk encryption,
retention policy, or backup access for the operator.

## Secrets and providers

- Real `.env` files are ignored and must never be committed.
- Provider keys belong only in the local backend environment, never frontend
  source, URLs, screenshots, logs, or documents.
- The default mock provider requires no credentials and makes no provider
  request.
- OpenAI-compatible adapters are disabled unless explicitly configured. They
  enforce bounded timeouts and response sizes and require structured JSON, but
  live-provider interoperability is outside release validation.
- Provider readiness checks configuration only; it does not send a paid or
  live AI request.

Rotate any credential immediately if it is exposed. Remove it from current
files and Git history using an appropriately reviewed incident process; simply
deleting it in a later commit is insufficient.

## Application security properties

- The upload API bounds total bytes and streaming chunk size, checks extension,
  MIME hint, PDF signature, and SHA-256, and uses `.part` files plus atomic
  finalization.
- User filenames are sanitized display metadata and never filesystem targets.
- Stored paths are contained under configured roots and use generated UUID
  storage keys.
- PyMuPDF performs deep validation before derived data can become `READY`.
- Retrieved PDF content is untrusted data and is explicitly separated from
  provider instructions.
- Provider output is schema validated, citation identifiers are never guessed,
  and exact answer spans, page slices, offsets, hashes, revisions, and source
  eligibility are rechecked transactionally.
- Unsupported answers are not exposed. Bounded reason codes replace raw
  provider payloads and internal exceptions.
- Routine logs and problem responses exclude document contents, storage paths,
  secrets, unrestricted exception messages, and chain-of-thought.
- Source deletion physically removes the file before database cleanup and
  removes dependent answer aggregates that would otherwise retain broken
  citations.

## Browser boundary

The frontend renders untrusted filenames, questions, answers, claims, and
evidence as React text; it does not use `dangerouslySetInnerHTML`. The protected
PDF endpoint remains unauthenticated because the whole v1.0 application is
local and unauthenticated. Browser object URLs and PDF.js tasks are cleaned up
on lifecycle changes.

## Operational guidance

- Keep the default loopback bind address.
- Keep Docker Desktop, Windows, browsers, Python, Node, and dependencies
  patched.
- Review readiness before use and stop on storage, migration, database,
  pgvector, or provider failures.
- Preserve normal data with `docker compose down`; avoid broad Docker pruning
  and unsafe recursive deletion.
- Validate exact paths, reject symlinks, and use a dedicated Compose project
  before removing isolated test data.
- Do not treat generated embeddings or mock-provider output as confidential
  encryption or a security control.

## Reporting a vulnerability

Do not open a public issue containing credentials, private PDFs, extracted
content, filesystem paths, or exploit details. Contact the repository owner
privately through the contact method listed on the GitHub profile for
`jkenken240`, include the affected commit and a minimal fictional reproduction,
and allow time for triage before public disclosure.

This repository does not promise a fixed security-support lifetime or response
SLA. Reports are evaluated for the current `main` branch and documented local
deployment boundary.
