# DocIntel v1.0 release notes

DocIntel v1.0 is a portfolio-ready local release candidate demonstrating how a
document question-answering product can make grounding inspectable rather than
decorative.

## The demonstration

Upload fictional PDFs through the production browser workspace and watch a
durable worker validate, extract, normalize, chunk, and embed them. Select
`READY` sources, ask a cross-document question, and inspect each factual claim
through structured citations. Every citation resolves to an immutable evidence
snapshot, sanitized filename, original one-based PDF page, exact page-relative
offsets, text hash, and a visibly rendered source page.

When evidence is absent, stale, incompatible, conflicting beyond a qualified
answer, or unable to support a material claim, DocIntel deliberately returns
insufficient evidence. It does not show the rejected provider answer or invent
citations.

## Why it is credible

- Uploads are streamed with bounded memory, validated, hashed, and atomically
  stored under server-generated keys.
- Processing jobs use PostgreSQL row locking, leases, retries, cancellation,
  and restart reconciliation.
- Chunks never cross pages and exactly match stored normalized page slices.
- Mock embeddings and grounded providers are deterministic, offline, and free
  of API keys or paid requests.
- Retrieval never mixes embedding spaces and never pads evidence with chunks
  below its configured threshold.
- Claims, citations, evidence, and verification results are separate structured
  records.
- Deleting a source removes its file and derived aggregate and prevents
  dependent answers from remaining apparently valid.
- The responsive workspace is covered by component, desktop, mobile,
  accessibility, production Compose, and PDF.js browser tests.

## Reproducible local runtime

The release ships frozen Python runtime/development locks, a packaged non-root
backend image, a multi-stage nginx frontend image, an idempotent Windows
bootstrap, loopback-only default ports, and a clean Alembic path through
`20260730_0004`. CI uses the same production topology with an empty temporary
database and guarded project-specific teardown.

## Safe portfolio data

The standard-library demo generator creates two polished, complementary,
byte-identical fictional PDFs. They support the documented question:

> What compliance audit records retention period applies to Aster Ridge and Blue Dune?

No real company, person, address, project, customer, credential, or business
document is included.

## Release boundary

DocIntel v1.0 is a local, unauthenticated portfolio application. It is not a
cloud service and must not be exposed publicly without authentication,
authorization, TLS, rate limiting, monitoring, and another security review.
OCR, additional document types, multi-turn chat, streaming answers, web search,
agents, collaboration, sharing, annotations, billing, and deployment
automation remain future work.

See the [README](README.md), [security policy](SECURITY.md), and
[release-validation checklist](docs/release-validation.md) before operating the
release candidate.
