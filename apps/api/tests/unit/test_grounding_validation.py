from __future__ import annotations

import hashlib
import uuid

import pytest

from docintel.intelligence.providers import (
    ClaimVerificationOutput,
    ClaimVerificationResult,
    EvidenceMaterial,
    GeneratedClaim,
    GroundedAnswerOutput,
)
from docintel.intelligence.retrieval import RetrievalCandidate
from docintel.models import Chunk, DocumentPage
from docintel.services.questions import QuestionService


def source() -> EvidenceMaterial:
    return EvidenceMaterial(
        id=uuid.UUID("10000000-0000-0000-0000-000000000001"),
        document_id=uuid.UUID("20000000-0000-0000-0000-000000000001"),
        display_filename="Fictional.pdf",
        page_number=2,
        text="Records are retained for seven years.",
        retrieval_rank=1,
    )


def answer(evidence_id: uuid.UUID) -> GroundedAnswerOutput:
    text = "Records are retained for seven years."
    return GroundedAnswerOutput(
        status="answered",
        answer_text=text,
        claims=[
            GeneratedClaim(
                ordinal=0,
                text=text,
                char_start=0,
                char_end=len(text),
                evidence_ids=[evidence_id],
            )
        ],
    )


def test_claim_spans_and_known_unique_evidence_are_required() -> None:
    evidence = source()
    claims = QuestionService._validate_generated_answer(answer(evidence.id), [evidence])

    assert claims[0].text == evidence.text

    invalid_span = answer(evidence.id)
    invalid_span.claims[0].char_end -= 1
    with pytest.raises(ValueError):
        QuestionService._validate_generated_answer(invalid_span, [evidence])

    unknown = answer(uuid.uuid4())
    with pytest.raises(ValueError):
        QuestionService._validate_generated_answer(unknown, [evidence])

    duplicate = answer(evidence.id)
    duplicate.claims[0].evidence_ids.append(evidence.id)
    with pytest.raises(ValueError):
        QuestionService._validate_generated_answer(duplicate, [evidence])


def test_verification_requires_one_bounded_result_per_claim() -> None:
    evidence = source()
    claims = QuestionService._validate_generated_answer(answer(evidence.id), [evidence])
    valid = ClaimVerificationOutput(
        results=[
            ClaimVerificationResult(
                claim_ordinal=0,
                supported=True,
                evidence_ids=[evidence.id],
                reason_code="EXACT_EVIDENCE_MATCH",
            )
        ]
    )

    result = QuestionService._validate_verification(claims, valid, [evidence])

    assert result[0].supported is True

    with pytest.raises(ValueError):
        QuestionService._validate_verification(
            claims,
            ClaimVerificationOutput(results=[]),
            [evidence],
        )

    with pytest.raises(ValueError):
        QuestionService._validate_verification(
            claims,
            ClaimVerificationOutput(
                results=[
                    ClaimVerificationResult(
                        claim_ordinal=0,
                        supported=True,
                        evidence_ids=[uuid.uuid4()],
                        reason_code="EXACT_EVIDENCE_MATCH",
                    )
                ]
            ),
            [evidence],
        )


def test_candidate_document_page_chunk_offsets_and_hashes_must_match() -> None:
    text = "Records are retained for seven years."
    text_hash = hashlib.sha256(text.encode()).hexdigest()
    document_id = uuid.uuid4()
    page_id = uuid.uuid4()
    chunk_id = uuid.uuid4()
    candidate = RetrievalCandidate(
        document_id=document_id,
        display_filename="Fictional.pdf",
        processing_revision=2,
        page_id=page_id,
        page_number=3,
        page_text_sha256=text_hash,
        chunk_id=chunk_id,
        chunk_ordinal=4,
        char_start=0,
        char_end=len(text),
        text=text,
        text_sha256=text_hash,
        score=0.8,
        vector=(),
    )
    page = DocumentPage(
        id=page_id,
        document_id=document_id,
        processing_revision=2,
        page_number=3,
        width=612,
        height=792,
        text_sha256=text_hash,
        text=text,
        char_count=len(text),
    )
    chunk = Chunk(
        id=chunk_id,
        document_id=document_id,
        page_id=page_id,
        processing_revision=2,
        ordinal=4,
        char_start=0,
        char_end=len(text),
        text=text,
        text_sha256=text_hash,
        page_ordinal=0,
        chunker_version="test",
    )

    assert QuestionService._candidate_matches_rows(candidate, chunk, page)

    page.page_number = 2
    assert not QuestionService._candidate_matches_rows(candidate, chunk, page)
    page.page_number = 3
    chunk.char_end -= 1
    assert not QuestionService._candidate_matches_rows(candidate, chunk, page)
    chunk.char_end = len(text)
    page.text_sha256 = "0" * 64
    assert not QuestionService._candidate_matches_rows(candidate, chunk, page)
