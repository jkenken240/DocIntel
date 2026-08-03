# Deterministic v1.0 demo workflow

This workflow demonstrates DocIntel without API keys, paid requests, real
documents, or copied business content. Every name, place, person, project, and
amount in the generated PDFs is fictional.

## Generate the PDFs

Run from `E:\DocIntel` with Python 3.13:

```powershell
py -3.13 .\scripts\generate_demo_pdfs.py `
  --output-dir E:\DocIntelV1Demo\samples
```

The output directory must be absolute, outside the repository, and sufficiently
narrow. The generator refuses symlinks, repository paths, broad roots,
unrelated existing entries, and an existing known file whose bytes differ.
Running it again against the same exact output is idempotent.

Expected files and SHA-256 values:

| File | Pages | SHA-256 |
| --- | ---: | --- |
| `Aster Ridge Governance Brief.pdf` | 3 | `19c59138c2c717fa71bd8d69116de57bc017461b793141e55a09c193d38ad74e` |
| `Blue Dune Operations Profile.pdf` | 3 | `f14bd5fe4028863bb787a1e9bdbffdaaa1df78f1e02684e19a0be00fa5051d62` |

The generator uses a fixed PDF object order, fixed metadata, built-in fonts,
ASCII source text, and no timestamps or random identifiers. Equivalent runs
produce byte-identical files.

## Run the offline product demonstration

1. Confirm `.env` contains `DOCINTEL_AI_PROVIDER=mock` and no provider key.
2. Start the production stack with `docker compose up --build -d`.
3. Open <http://localhost:5173/documents>.
4. Select both generated PDFs through the file picker.
5. Observe upload acceptance and real lifecycle progress until both documents
   show `READY` / **Evidence ready**.
6. Search for `Aster`, clear the search, filter to `READY`, then select both
   documents.
7. Choose **Ask with selection**.
8. Ask: **What compliance audit records retention period applies to Aster Ridge and Blue Dune?**
9. Confirm the answer has structured claims supported by both documents.
10. Open the Aster Ridge citation and verify page 2 contains the exact excerpt
   `Aster Ridge has a compliance audit records retention period of seven years.`
11. Open the Blue Dune citation and verify page 3 contains the exact excerpt
   `Blue Dune has a compliance audit records retention period of nine years.`
12. Confirm each PDF canvas is visible and shows the cited one-based page.

Retrieval score and evidence order are implementation details. Filename, page,
excerpt, offsets, hashes, processing revision, and source eligibility are the
auditable citation facts.

## Demonstrate refusal

Ask:

> What is the orbital launch authorization code?

DocIntel should show **The evidence was not strong enough**, preserve the
question and selected sources, and display no answer or citations. Repeating an
unsupported question is not presented as a guarantee of success.

## Demonstrate deletion integrity

Delete `Aster Ridge Governance Brief.pdf` through its confirmation dialog.
Wait until it disappears from the library, then revisit the earlier grounded
result. The dependent result must be unavailable rather than retain a
valid-looking broken citation.

## Demo data cleanup

`docker compose down` stops containers without removing normal bind-mounted
data. To remove a dedicated demo only, first verify its exact configured root
and that it is outside `E:\DocIntelData` and the repository. Never use broad
recursive deletion, wildcards, or Docker system pruning.
