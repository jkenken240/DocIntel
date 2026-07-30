from __future__ import annotations

import math
import uuid

import pytest

from docintel.intelligence.retrieval import (
    RetrievalCandidate,
    RetrievalConfig,
    RetrievalError,
    normalize_question,
    select_diverse_evidence,
)


def candidate(
    *,
    name: str,
    score: float,
    vector: tuple[float, ...],
    document: int = 1,
    page: int = 1,
    start: int = 0,
    end: int = 100,
    ordinal: int = 0,
) -> RetrievalCandidate:
    return RetrievalCandidate(
        document_id=uuid.UUID(int=document),
        display_filename=f"Document-{document}.pdf",
        processing_revision=1,
        page_id=uuid.UUID(int=100 + page + document * 10),
        page_number=page,
        page_text_sha256="a" * 64,
        chunk_id=uuid.uuid5(uuid.NAMESPACE_URL, name),
        chunk_ordinal=ordinal,
        char_start=start,
        char_end=end,
        text=name.ljust(end - start, "."),
        text_sha256="b" * 64,
        score=score,
        vector=vector,
    )


def config(**overrides: int | float) -> RetrievalConfig:
    values: dict[str, int | float] = {
        "candidate_pool": 10,
        "evidence_count": 4,
        "minimum_similarity": 0.2,
        "maximum_chunks_per_page": 2,
        "maximum_chunks_per_document": 2,
        "mmr_lambda": 0.7,
        "duplicate_overlap_ratio": 0.7,
    }
    values.update(overrides)
    return RetrievalConfig(**values)  # type: ignore[arg-type]


def test_question_normalization_is_deterministic() -> None:
    assert normalize_question("  What\r\n  is  CAFE\u0301? ") == "What is CAFÉ?"


def test_threshold_stable_ties_caps_and_overlap_suppression() -> None:
    first = candidate(name="first", score=0.9, vector=(1.0, 0.0), ordinal=0)
    overlapping = candidate(
        name="overlap",
        score=0.89,
        vector=(1.0, 0.0),
        start=10,
        end=100,
        ordinal=1,
    )
    same_page = candidate(
        name="same-page",
        score=0.8,
        vector=(0.8, 0.2),
        start=120,
        end=220,
        ordinal=2,
    )
    capped_page = candidate(
        name="capped-page",
        score=0.79,
        vector=(0.7, 0.3),
        start=240,
        end=340,
        ordinal=3,
    )
    diverse = candidate(
        name="diverse",
        score=0.8,
        vector=(0.0, 1.0),
        document=2,
        page=1,
    )
    below = candidate(name="below", score=0.19, vector=(0.0, 1.0), document=3)

    selected = select_diverse_evidence(
        [below, capped_page, diverse, overlapping, same_page, first],
        config(),
    )

    assert [item.chunk_id for item in selected] == [
        first.chunk_id,
        diverse.chunk_id,
        capped_page.chunk_id,
    ]
    assert overlapping not in selected
    assert same_page not in selected
    assert below not in selected


def test_identifier_tie_breaking_is_stable() -> None:
    later = candidate(name="later", score=0.7, vector=(1.0, 0.0), document=2)
    earlier = candidate(name="earlier", score=0.7, vector=(1.0, 0.0), document=1)

    selected = select_diverse_evidence(
        [later, earlier],
        config(evidence_count=2),
    )

    assert [item.document_id.int for item in selected] == [1, 2]


@pytest.mark.parametrize("score", [math.nan, math.inf, -math.inf])
def test_non_finite_retrieval_scores_are_rejected(score: float) -> None:
    with pytest.raises(RetrievalError):
        select_diverse_evidence(
            [candidate(name="invalid", score=score, vector=(1.0, 0.0))],
            config(),
        )
