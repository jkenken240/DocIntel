from __future__ import annotations

import hashlib
import logging
import math
import unicodedata
import uuid
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from typing import Any, cast

from sqlalchemy import exists, select
from sqlalchemy.ext.asyncio import AsyncSession

from docintel.core.config import Settings
from docintel.core.errors import ProblemException
from docintel.db.session import SessionFactory
from docintel.intelligence.providers import (
    ClaimForVerification,
    ClaimSupportVerifier,
    ClaimVerificationOutput,
    EvidenceMaterial,
    GroundedAnswerOutput,
    GroundedAnswerProvider,
    ProviderIdentity,
)
from docintel.intelligence.retrieval import (
    RetrievalCandidate,
    RetrievalConfig,
    RetrievalError,
    normalize_question,
    select_diverse_evidence,
)
from docintel.models import (
    Answer,
    AnswerClaim,
    Chunk,
    ChunkEmbedding,
    Citation,
    ClaimVerification,
    ClaimVerificationEvidence,
    Document,
    DocumentJob,
    DocumentPage,
    DocumentStatus,
    EmbeddingSpace,
    EvidenceSnapshot,
    Question,
    QuestionStatus,
)
from docintel.processing.embeddings import (
    EmbeddingProvider,
    EmbeddingSpaceIdentity,
    validate_embedding_batch,
)
from docintel.schemas.questions import (
    CitationResponse,
    ClaimResponse,
    EmbeddingSpaceSnapshot,
    EvidenceResponse,
    ProviderSnapshot,
    QuestionResponse,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class QuestionContext:
    normalized_text: str
    selected_document_ids: tuple[uuid.UUID, ...]
    embedding_identity: EmbeddingSpaceIdentity
    answer_identity: ProviderIdentity
    verifier_identity: ProviderIdentity
    embedding_space_id: uuid.UUID | None


class QuestionService:
    def __init__(
        self,
        session_factory: SessionFactory,
        settings: Settings,
        embedding_provider: EmbeddingProvider,
        answer_provider: GroundedAnswerProvider,
        claim_verifier: ClaimSupportVerifier,
    ) -> None:
        self.session_factory = session_factory
        self.settings = settings
        self.embedding_provider = embedding_provider
        self.answer_provider = answer_provider
        self.claim_verifier = claim_verifier
        self.retrieval_config = RetrievalConfig(
            candidate_pool=settings.retrieval_candidate_pool,
            evidence_count=settings.retrieval_evidence_count,
            minimum_similarity=settings.retrieval_minimum_similarity,
            maximum_chunks_per_page=settings.retrieval_max_chunks_per_page,
            maximum_chunks_per_document=settings.retrieval_max_chunks_per_document,
            mmr_lambda=settings.retrieval_mmr_lambda,
            duplicate_overlap_ratio=settings.retrieval_duplicate_overlap_ratio,
        )

    async def ask(
        self,
        *,
        question_text: str,
        selected_document_ids: list[uuid.UUID],
    ) -> QuestionResponse:
        normalized = normalize_question(question_text)
        self._validate_question(normalized, question_text, selected_document_ids)
        selected = tuple(sorted(set(selected_document_ids), key=str))
        context = QuestionContext(
            normalized_text=normalized,
            selected_document_ids=selected,
            embedding_identity=self.embedding_provider.identity,
            answer_identity=self.answer_provider.identity,
            verifier_identity=self.claim_verifier.identity,
            embedding_space_id=None,
        )
        if not self._provider_identities_are_compatible(context):
            question_id = await self._create_insufficient(
                context,
                reason_code="PROVIDER_CONFIGURATION_MISMATCH",
            )
            return await self.get(question_id)

        space = await self._select_embedding_space(selected)
        context = replace(
            context,
            embedding_space_id=space.id if space is not None else None,
        )
        if space is None:
            question_id = await self._create_insufficient(
                context,
                reason_code="NO_COMPATIBLE_EMBEDDING_SPACE",
            )
            return await self.get(question_id)

        try:
            vectors = await self.embedding_provider.embed([normalized])
            validate_embedding_batch(
                texts=[normalized],
                vectors=vectors,
                expected_identity=context.embedding_identity,
                actual_identity=self.embedding_provider.identity,
            )
        except Exception as exception:
            logger.warning(
                "Question embedding failed safely.",
                extra={"exception_type": type(exception).__name__},
            )
            question_id = await self._create_insufficient(
                context,
                reason_code="QUESTION_EMBEDDING_FAILED",
            )
            return await self.get(question_id)

        try:
            candidates = await self._retrieve_candidates(
                embedding_space_id=space.id,
                vector=vectors[0],
                selected_document_ids=selected,
            )
            chosen = select_diverse_evidence(candidates, self.retrieval_config)
        except RetrievalError:
            question_id = await self._create_insufficient(
                context,
                reason_code="RETRIEVAL_INVALID",
            )
            return await self.get(question_id)

        if not chosen:
            question_id = await self._create_insufficient(
                context,
                reason_code="INSUFFICIENT_RETRIEVAL_SCORE",
            )
            return await self.get(question_id)

        question_id, evidence_material = await self._create_evidence_snapshots(
            context,
            chosen,
        )
        if not evidence_material:
            question_id = await self._mark_insufficient(
                question_id,
                context,
                reason_code="SOURCE_CHANGED",
            )
            return await self.get(question_id)

        try:
            raw_answer = await self.answer_provider.generate(normalized, evidence_material)
            generated = GroundedAnswerOutput.model_validate(raw_answer.model_dump(mode="python"))
        except Exception as exception:
            logger.warning(
                "Grounded answer generation failed safely.",
                extra={
                    "question_id": str(question_id),
                    "exception_type": type(exception).__name__,
                },
            )
            question_id = await self._mark_insufficient(
                question_id,
                context,
                reason_code="ANSWER_PROVIDER_INVALID",
            )
            return await self.get(question_id)

        if generated.status == "insufficient_evidence":
            question_id = await self._mark_insufficient(
                question_id,
                context,
                reason_code=generated.reason_code or "INSUFFICIENT_EVIDENCE",
            )
            return await self.get(question_id)

        try:
            claims = self._validate_generated_answer(generated, evidence_material)
        except ValueError:
            question_id = await self._mark_insufficient(
                question_id,
                context,
                reason_code="CITATION_VALIDATION_FAILED",
            )
            return await self.get(question_id)

        try:
            raw_verification = await self.claim_verifier.verify(claims, evidence_material)
            verification = ClaimVerificationOutput.model_validate(
                raw_verification.model_dump(mode="python")
            )
            verification_by_claim = self._validate_verification(
                claims,
                verification,
                evidence_material,
            )
        except Exception as exception:
            logger.warning(
                "Claim verification failed safely.",
                extra={
                    "question_id": str(question_id),
                    "exception_type": type(exception).__name__,
                },
            )
            question_id = await self._mark_insufficient(
                question_id,
                context,
                reason_code="CLAIM_VERIFICATION_FAILED",
            )
            return await self.get(question_id)

        unsupported = [result for result in verification_by_claim.values() if not result.supported]
        if unsupported:
            reason_code = (
                "CONTRADICTORY_EVIDENCE"
                if any(result.reason_code == "CONTRADICTORY_EVIDENCE" for result in unsupported)
                else "UNSUPPORTED_CLAIM"
            )
            question_id = await self._mark_insufficient(
                question_id,
                context,
                reason_code=reason_code,
            )
            return await self.get(question_id)

        persisted = await self._persist_answer(
            question_id,
            context,
            generated,
            verification_by_claim,
        )
        if not persisted:
            question_id = await self._mark_insufficient(
                question_id,
                context,
                reason_code="SOURCE_CHANGED",
            )
        return await self.get(question_id)

    async def get(self, question_id: uuid.UUID) -> QuestionResponse:
        async with self.session_factory() as session:
            question = await session.get(Question, question_id)
            if question is None:
                raise ProblemException(
                    status_code=404,
                    code="QUESTION_NOT_FOUND",
                    title="Question not found",
                    detail="The requested question does not exist.",
                )
            evidence = list(
                (
                    await session.scalars(
                        select(EvidenceSnapshot)
                        .where(EvidenceSnapshot.question_id == question_id)
                        .order_by(EvidenceSnapshot.retrieval_rank)
                    )
                ).all()
            )
            answer = await session.scalar(select(Answer).where(Answer.question_id == question_id))
            claims = (
                list(
                    (
                        await session.scalars(
                            select(AnswerClaim)
                            .where(AnswerClaim.answer_id == answer.id)
                            .order_by(AnswerClaim.ordinal)
                        )
                    ).all()
                )
                if answer is not None
                else []
            )
            claim_ids = [claim.id for claim in claims]
            citations = (
                list(
                    (
                        await session.scalars(
                            select(Citation)
                            .where(Citation.claim_id.in_(claim_ids))
                            .order_by(Citation.claim_id, Citation.ordinal)
                        )
                    ).all()
                )
                if claim_ids
                else []
            )
            verifications = (
                list(
                    (
                        await session.scalars(
                            select(ClaimVerification).where(
                                ClaimVerification.claim_id.in_(claim_ids)
                            )
                        )
                    ).all()
                )
                if claim_ids
                else []
            )

        evidence_by_id = {item.id: item for item in evidence}
        citations_by_claim: dict[uuid.UUID, list[Citation]] = {}
        for citation in citations:
            citations_by_claim.setdefault(citation.claim_id, []).append(citation)
        verification_by_claim = {item.claim_id: item for item in verifications}

        claim_responses: list[ClaimResponse] = []
        for claim in claims:
            verification = verification_by_claim[claim.id]
            citation_responses = [
                self._citation_response(citation, evidence_by_id[citation.evidence_snapshot_id])
                for citation in citations_by_claim.get(claim.id, [])
            ]
            claim_responses.append(
                ClaimResponse(
                    id=claim.id,
                    ordinal=claim.ordinal,
                    char_start=claim.char_start,
                    char_end=claim.char_end,
                    text=claim.text,
                    supported=verification.supported,
                    verification_reason_code=verification.reason_code,
                    citations=citation_responses,
                )
            )

        return QuestionResponse(
            id=question.id,
            question=question.normalized_text,
            selected_document_ids=[uuid.UUID(value) for value in question.selected_document_ids],
            status=question.status,
            insufficient_reason_code=question.insufficient_reason_code,
            answer_id=answer.id if answer is not None else None,
            answer_text=answer.text if answer is not None else None,
            claims=claim_responses,
            evidence=[self._evidence_response(item) for item in evidence],
            retrieval_configuration=cast(
                dict[str, int | float],
                question.retrieval_configuration,
            ),
            retrieval_configuration_hash=question.retrieval_configuration_hash,
            embedding_space=EmbeddingSpaceSnapshot(
                id=question.embedding_space_id,
                provider=question.embedding_provider,
                model=question.embedding_model,
                dimensions=question.embedding_dimensions,
                distance_metric=question.embedding_distance_metric,
                configuration_hash=question.embedding_configuration_hash,
            ),
            answer_provider=ProviderSnapshot(
                provider=question.answer_provider,
                model=question.answer_model,
                configuration_hash=question.answer_configuration_hash,
            ),
            verifier_provider=ProviderSnapshot(
                provider=question.verifier_provider,
                model=question.verifier_model,
                configuration_hash=question.verifier_configuration_hash,
            ),
            created_at=question.created_at,
        )

    def _validate_question(
        self,
        normalized: str,
        original: str,
        selected_document_ids: list[uuid.UUID],
    ) -> None:
        if not normalized:
            raise ProblemException(
                status_code=422,
                code="QUESTION_EMPTY",
                title="Question is empty",
                detail="Provide a non-empty question.",
            )
        if len(normalized) > self.settings.question_max_chars:
            raise ProblemException(
                status_code=413,
                code="QUESTION_TOO_LARGE",
                title="Question is too large",
                detail="The question exceeds the configured character limit.",
            )
        if any(
            unicodedata.category(character).startswith("C") and not character.isspace()
            for character in original
        ):
            raise ProblemException(
                status_code=422,
                code="QUESTION_INVALID_CHARACTERS",
                title="Question contains invalid characters",
                detail="The question contains unsupported control characters.",
            )
        if len(selected_document_ids) > self.settings.question_max_documents:
            raise ProblemException(
                status_code=413,
                code="TOO_MANY_DOCUMENT_FILTERS",
                title="Too many selected documents",
                detail="The document filter exceeds the configured limit.",
            )

    async def _select_embedding_space(
        self,
        selected_document_ids: tuple[uuid.UUID, ...],
    ) -> EmbeddingSpace | None:
        identity = self.embedding_provider.identity
        async with self.session_factory() as session:
            if selected_document_ids:
                documents = list(
                    (
                        await session.scalars(
                            select(Document)
                            .where(Document.id.in_(selected_document_ids))
                            .order_by(Document.id)
                        )
                    ).all()
                )
                if (
                    len(documents) != len(selected_document_ids)
                    or any(
                        document.status != DocumentStatus.READY
                        or document.active_embedding_space_id is None
                        for document in documents
                    )
                    or len({document.active_embedding_space_id for document in documents}) != 1
                ):
                    raise self._document_selection_conflict()
                space = await session.get(
                    EmbeddingSpace,
                    documents[0].active_embedding_space_id,
                )
                if space is None or not self._space_matches(space, identity):
                    raise self._document_selection_conflict()
                cancellation_exists = await session.scalar(
                    select(
                        exists().where(
                            DocumentJob.document_id.in_(selected_document_ids),
                            DocumentJob.cancellation_requested.is_(True),
                        )
                    )
                )
                if cancellation_exists:
                    raise self._document_selection_conflict()
                return space

            return cast(
                EmbeddingSpace | None,
                await session.scalar(
                    select(EmbeddingSpace)
                    .where(
                        EmbeddingSpace.provider == identity.provider,
                        EmbeddingSpace.model == identity.model,
                        EmbeddingSpace.dimensions == identity.dimensions,
                        EmbeddingSpace.distance_metric == identity.distance_metric,
                        EmbeddingSpace.configuration_hash == identity.configuration_hash,
                        exists().where(
                            Document.active_embedding_space_id == EmbeddingSpace.id,
                            Document.status == DocumentStatus.READY,
                        ),
                    )
                    .order_by(EmbeddingSpace.id)
                    .limit(1)
                ),
            )

    async def _retrieve_candidates(
        self,
        *,
        embedding_space_id: uuid.UUID,
        vector: list[float],
        selected_document_ids: tuple[uuid.UUID, ...],
    ) -> list[RetrievalCandidate]:
        distance = ChunkEmbedding.embedding.cosine_distance(vector)
        statement = (
            select(
                Document.id.label("document_id"),
                Document.original_filename,
                Document.processing_revision,
                DocumentPage.id.label("page_id"),
                DocumentPage.page_number,
                DocumentPage.text_sha256.label("page_text_sha256"),
                Chunk.id.label("chunk_id"),
                Chunk.ordinal.label("chunk_ordinal"),
                Chunk.char_start,
                Chunk.char_end,
                Chunk.text,
                Chunk.text_sha256,
                ChunkEmbedding.embedding,
                (1.0 - distance).label("score"),
            )
            .join(DocumentPage, DocumentPage.document_id == Document.id)
            .join(Chunk, Chunk.page_id == DocumentPage.id)
            .join(ChunkEmbedding, ChunkEmbedding.chunk_id == Chunk.id)
            .where(
                Document.status == DocumentStatus.READY,
                Document.active_embedding_space_id == embedding_space_id,
                Document.processing_revision == DocumentPage.processing_revision,
                Document.processing_revision == Chunk.processing_revision,
                ChunkEmbedding.embedding_space_id == embedding_space_id,
                distance <= 1.0 - self.retrieval_config.minimum_similarity,
                ~exists().where(
                    DocumentJob.document_id == Document.id,
                    DocumentJob.cancellation_requested.is_(True),
                ),
            )
            .order_by(
                distance,
                Document.id,
                DocumentPage.page_number,
                Chunk.ordinal,
                Chunk.id,
            )
            .limit(self.retrieval_config.candidate_pool)
        )
        if selected_document_ids:
            statement = statement.where(Document.id.in_(selected_document_ids))

        async with self.session_factory() as session:
            rows = (await session.execute(statement)).all()

        return [
            RetrievalCandidate(
                document_id=row.document_id,
                display_filename=row.original_filename,
                processing_revision=row.processing_revision,
                page_id=row.page_id,
                page_number=row.page_number,
                page_text_sha256=row.page_text_sha256,
                chunk_id=row.chunk_id,
                chunk_ordinal=row.chunk_ordinal,
                char_start=row.char_start,
                char_end=row.char_end,
                text=row.text,
                text_sha256=row.text_sha256,
                score=float(row.score),
                vector=tuple(float(value) for value in row.embedding),
            )
            for row in rows
        ]

    async def _create_evidence_snapshots(
        self,
        context: QuestionContext,
        candidates: list[RetrievalCandidate],
    ) -> tuple[uuid.UUID, list[EvidenceMaterial]]:
        question_id = uuid.uuid4()
        evidence_material: list[EvidenceMaterial] = []
        async with self.session_factory() as session:
            async with session.begin():
                if not await self._candidates_are_current(
                    session,
                    candidates,
                    context.embedding_space_id,
                ):
                    return question_id, evidence_material
                session.add(
                    self._new_question(
                        question_id,
                        context,
                        status=QuestionStatus.PROCESSING,
                    )
                )
                for rank, candidate in enumerate(candidates, start=1):
                    evidence_id = uuid.uuid4()
                    session.add(
                        EvidenceSnapshot(
                            id=evidence_id,
                            question_id=question_id,
                            document_id=candidate.document_id,
                            display_filename=candidate.display_filename,
                            processing_revision=candidate.processing_revision,
                            page_id=candidate.page_id,
                            page_number=candidate.page_number,
                            page_text_sha256=candidate.page_text_sha256,
                            chunk_id=candidate.chunk_id,
                            chunk_ordinal=candidate.chunk_ordinal,
                            char_start=candidate.char_start,
                            char_end=candidate.char_end,
                            text=candidate.text,
                            text_sha256=candidate.text_sha256,
                            retrieval_score=candidate.score,
                            retrieval_rank=rank,
                            embedding_space_id=cast(uuid.UUID, context.embedding_space_id),
                            embedding_provider=context.embedding_identity.provider,
                            embedding_model=context.embedding_identity.model,
                            embedding_dimensions=context.embedding_identity.dimensions,
                            embedding_distance_metric=(context.embedding_identity.distance_metric),
                            embedding_configuration_hash=(
                                context.embedding_identity.configuration_hash
                            ),
                        )
                    )
                    evidence_material.append(
                        EvidenceMaterial(
                            id=evidence_id,
                            document_id=candidate.document_id,
                            display_filename=candidate.display_filename,
                            page_number=candidate.page_number,
                            text=candidate.text,
                            retrieval_rank=rank,
                        )
                    )
        return question_id, evidence_material

    async def _candidates_are_current(
        self,
        session: AsyncSession,
        candidates: list[RetrievalCandidate],
        embedding_space_id: uuid.UUID | None,
    ) -> bool:
        if embedding_space_id is None:
            return False
        document_ids = sorted({candidate.document_id for candidate in candidates}, key=str)
        documents = list(
            (
                await session.scalars(
                    select(Document)
                    .where(Document.id.in_(document_ids))
                    .order_by(Document.id)
                    .with_for_update()
                )
            ).all()
        )
        if len(documents) != len(document_ids):
            return False
        documents_by_id = {document.id: document for document in documents}
        cancellation_exists = await session.scalar(
            select(
                exists().where(
                    DocumentJob.document_id.in_(document_ids),
                    DocumentJob.cancellation_requested.is_(True),
                )
            )
        )
        if cancellation_exists:
            return False

        for candidate in candidates:
            document = documents_by_id[candidate.document_id]
            if (
                document.status != DocumentStatus.READY
                or document.processing_revision != candidate.processing_revision
                or document.active_embedding_space_id != embedding_space_id
                or not math.isfinite(candidate.score)
            ):
                return False
            row = (
                await session.execute(
                    select(Chunk, DocumentPage, ChunkEmbedding)
                    .join(DocumentPage, DocumentPage.id == Chunk.page_id)
                    .join(ChunkEmbedding, ChunkEmbedding.chunk_id == Chunk.id)
                    .where(
                        Chunk.id == candidate.chunk_id,
                        Chunk.page_id == candidate.page_id,
                        Chunk.document_id == candidate.document_id,
                        ChunkEmbedding.embedding_space_id == embedding_space_id,
                    )
                )
            ).one_or_none()
            if row is None:
                return False
            chunk, page, _ = row
            if not self._candidate_matches_rows(candidate, chunk, page):
                return False
        return True

    async def _persist_answer(
        self,
        question_id: uuid.UUID,
        context: QuestionContext,
        generated: GroundedAnswerOutput,
        verification_by_claim: dict[int, Any],
    ) -> bool:
        answer_text = cast(str, generated.answer_text)
        async with self.session_factory() as session:
            async with session.begin():
                evidence = list(
                    (
                        await session.scalars(
                            select(EvidenceSnapshot)
                            .where(EvidenceSnapshot.question_id == question_id)
                            .order_by(EvidenceSnapshot.retrieval_rank)
                        )
                    ).all()
                )
                if not evidence or not await self._snapshots_are_current(
                    session,
                    evidence,
                    context.embedding_space_id,
                ):
                    return False
                question = await session.get(Question, question_id, with_for_update=True)
                if question is None or question.status != QuestionStatus.PROCESSING:
                    return False
                evidence_by_id = {item.id: item for item in evidence}

                answer = Answer(
                    question_id=question_id,
                    text=answer_text,
                    text_sha256=hashlib.sha256(answer_text.encode("utf-8")).hexdigest(),
                    provider=context.answer_identity.provider,
                    model=context.answer_identity.model,
                    configuration_hash=context.answer_identity.configuration_hash,
                )
                session.add(answer)
                await session.flush()
                for claim_output in generated.claims:
                    claim = AnswerClaim(
                        answer_id=answer.id,
                        ordinal=claim_output.ordinal,
                        char_start=claim_output.char_start,
                        char_end=claim_output.char_end,
                        text=claim_output.text,
                        text_sha256=hashlib.sha256(claim_output.text.encode("utf-8")).hexdigest(),
                    )
                    session.add(claim)
                    await session.flush()
                    for ordinal, evidence_id in enumerate(claim_output.evidence_ids):
                        if evidence_id not in evidence_by_id:
                            return False
                        session.add(
                            Citation(
                                claim_id=claim.id,
                                evidence_snapshot_id=evidence_id,
                                ordinal=ordinal,
                            )
                        )
                    verification_output = verification_by_claim[claim_output.ordinal]
                    verification = ClaimVerification(
                        claim_id=claim.id,
                        supported=verification_output.supported,
                        reason_code=verification_output.reason_code,
                        provider=context.verifier_identity.provider,
                        model=context.verifier_identity.model,
                        configuration_hash=context.verifier_identity.configuration_hash,
                    )
                    session.add(verification)
                    await session.flush()
                    for ordinal, evidence_id in enumerate(verification_output.evidence_ids):
                        session.add(
                            ClaimVerificationEvidence(
                                verification_id=verification.id,
                                evidence_snapshot_id=evidence_id,
                                ordinal=ordinal,
                            )
                        )
                question.status = QuestionStatus.ANSWERED
                question.insufficient_reason_code = None
                question.updated_at = datetime.now(UTC)
        return True

    async def _snapshots_are_current(
        self,
        session: AsyncSession,
        evidence: list[EvidenceSnapshot],
        embedding_space_id: uuid.UUID | None,
    ) -> bool:
        candidates = [
            RetrievalCandidate(
                document_id=item.document_id,
                display_filename=item.display_filename,
                processing_revision=item.processing_revision,
                page_id=item.page_id,
                page_number=item.page_number,
                page_text_sha256=item.page_text_sha256,
                chunk_id=item.chunk_id,
                chunk_ordinal=item.chunk_ordinal,
                char_start=item.char_start,
                char_end=item.char_end,
                text=item.text,
                text_sha256=item.text_sha256,
                score=item.retrieval_score,
                vector=(),
            )
            for item in evidence
        ]
        return await self._candidates_are_current(session, candidates, embedding_space_id)

    async def _create_insufficient(
        self,
        context: QuestionContext,
        *,
        reason_code: str,
    ) -> uuid.UUID:
        question_id = uuid.uuid4()
        async with self.session_factory() as session:
            async with session.begin():
                session.add(
                    self._new_question(
                        question_id,
                        context,
                        status=QuestionStatus.INSUFFICIENT_EVIDENCE,
                        reason_code=reason_code,
                    )
                )
        return question_id

    async def _mark_insufficient(
        self,
        question_id: uuid.UUID,
        context: QuestionContext,
        *,
        reason_code: str,
    ) -> uuid.UUID:
        async with self.session_factory() as session:
            async with session.begin():
                question = await session.get(Question, question_id, with_for_update=True)
                if question is None:
                    replacement_id = uuid.uuid4()
                    session.add(
                        self._new_question(
                            replacement_id,
                            context,
                            status=QuestionStatus.INSUFFICIENT_EVIDENCE,
                            reason_code=reason_code,
                        )
                    )
                    return replacement_id
                question.status = QuestionStatus.INSUFFICIENT_EVIDENCE
                question.insufficient_reason_code = reason_code
                question.updated_at = datetime.now(UTC)
                return question.id

    def _new_question(
        self,
        question_id: uuid.UUID,
        context: QuestionContext,
        *,
        status: QuestionStatus,
        reason_code: str | None = None,
    ) -> Question:
        return Question(
            id=question_id,
            normalized_text=context.normalized_text,
            selected_document_ids=[
                str(document_id) for document_id in context.selected_document_ids
            ],
            status=status,
            insufficient_reason_code=reason_code,
            retrieval_configuration=self.retrieval_config.snapshot(),
            retrieval_configuration_hash=self.retrieval_config.configuration_hash(),
            embedding_space_id=context.embedding_space_id,
            embedding_provider=context.embedding_identity.provider,
            embedding_model=context.embedding_identity.model,
            embedding_dimensions=context.embedding_identity.dimensions,
            embedding_distance_metric=context.embedding_identity.distance_metric,
            embedding_configuration_hash=context.embedding_identity.configuration_hash,
            answer_provider=context.answer_identity.provider,
            answer_model=context.answer_identity.model,
            answer_configuration_hash=context.answer_identity.configuration_hash,
            verifier_provider=context.verifier_identity.provider,
            verifier_model=context.verifier_identity.model,
            verifier_configuration_hash=context.verifier_identity.configuration_hash,
        )

    @staticmethod
    def _space_matches(
        space: EmbeddingSpace,
        identity: EmbeddingSpaceIdentity,
    ) -> bool:
        return (
            space.provider == identity.provider
            and space.model == identity.model
            and space.dimensions == identity.dimensions
            and space.distance_metric == identity.distance_metric
            and space.configuration_hash == identity.configuration_hash
        )

    def _provider_identities_are_compatible(self, context: QuestionContext) -> bool:
        identities = (context.answer_identity, context.verifier_identity)
        return (
            context.embedding_identity.provider == self.settings.ai_provider
            and context.embedding_identity.dimensions == self.settings.embedding_dimensions
            and bool(context.embedding_identity.model)
            and len(context.embedding_identity.configuration_hash) == 64
            and all(
                identity.provider == self.settings.ai_provider
                and bool(identity.model)
                and len(identity.configuration_hash) == 64
                for identity in identities
            )
        )

    @staticmethod
    def _candidate_matches_rows(
        candidate: RetrievalCandidate,
        chunk: Chunk,
        page: DocumentPage,
    ) -> bool:
        return (
            page.id == candidate.page_id
            and page.document_id == candidate.document_id
            and page.processing_revision == candidate.processing_revision
            and page.page_number == candidate.page_number
            and page.text_sha256 == candidate.page_text_sha256
            and hashlib.sha256(page.text.encode("utf-8")).hexdigest() == page.text_sha256
            and chunk.document_id == candidate.document_id
            and chunk.page_id == candidate.page_id
            and chunk.processing_revision == candidate.processing_revision
            and chunk.ordinal == candidate.chunk_ordinal
            and chunk.char_start == candidate.char_start
            and chunk.char_end == candidate.char_end
            and chunk.text == candidate.text
            and chunk.text_sha256 == candidate.text_sha256
            and page.text[candidate.char_start : candidate.char_end] == candidate.text
            and hashlib.sha256(candidate.text.encode("utf-8")).hexdigest() == candidate.text_sha256
        )

    @staticmethod
    def _validate_generated_answer(
        generated: GroundedAnswerOutput,
        evidence: list[EvidenceMaterial],
    ) -> list[ClaimForVerification]:
        answer_text = generated.answer_text
        if generated.status != "answered" or answer_text is None:
            raise ValueError("Answer output is not answered.")
        evidence_ids = {item.id for item in evidence}
        expected_ordinals = list(range(len(generated.claims)))
        if [claim.ordinal for claim in generated.claims] != expected_ordinals:
            raise ValueError("Claim ordering is invalid.")
        claims: list[ClaimForVerification] = []
        for claim in generated.claims:
            if (
                claim.char_end > len(answer_text)
                or claim.char_end <= claim.char_start
                or answer_text[claim.char_start : claim.char_end] != claim.text
                or not claim.evidence_ids
                or len(set(claim.evidence_ids)) != len(claim.evidence_ids)
                or any(evidence_id not in evidence_ids for evidence_id in claim.evidence_ids)
            ):
                raise ValueError("Claim or citation data is invalid.")
            claims.append(
                ClaimForVerification(
                    ordinal=claim.ordinal,
                    text=claim.text,
                    evidence_ids=tuple(claim.evidence_ids),
                )
            )
        return claims

    @staticmethod
    def _validate_verification(
        claims: list[ClaimForVerification],
        verification: ClaimVerificationOutput,
        evidence: list[EvidenceMaterial],
    ) -> dict[int, Any]:
        evidence_ids = {item.id for item in evidence}
        if len(verification.results) != len(claims):
            raise ValueError("Verifier result count is invalid.")
        by_claim: dict[int, Any] = {}
        claims_by_ordinal = {claim.ordinal: claim for claim in claims}
        for result in verification.results:
            claim = claims_by_ordinal.get(result.claim_ordinal)
            if (
                claim is None
                or result.claim_ordinal in by_claim
                or len(set(result.evidence_ids)) != len(result.evidence_ids)
                or any(item_id not in evidence_ids for item_id in result.evidence_ids)
                or any(item_id not in claim.evidence_ids for item_id in result.evidence_ids)
                or (result.supported and not result.evidence_ids)
            ):
                raise ValueError("Verifier references are invalid.")
            by_claim[result.claim_ordinal] = result
        return by_claim

    @staticmethod
    def _evidence_response(item: EvidenceSnapshot) -> EvidenceResponse:
        return EvidenceResponse(
            id=item.id,
            document_id=item.document_id,
            filename=item.display_filename,
            processing_revision=item.processing_revision,
            page_id=item.page_id,
            page_number=item.page_number,
            chunk_id=item.chunk_id,
            chunk_ordinal=item.chunk_ordinal,
            char_start=item.char_start,
            char_end=item.char_end,
            excerpt=item.text,
            text_sha256=item.text_sha256,
            retrieval_score=item.retrieval_score,
            retrieval_rank=item.retrieval_rank,
        )

    @staticmethod
    def _citation_response(
        citation: Citation,
        evidence: EvidenceSnapshot,
    ) -> CitationResponse:
        return CitationResponse(
            id=citation.id,
            evidence_id=evidence.id,
            document_id=evidence.document_id,
            filename=evidence.display_filename,
            page_number=evidence.page_number,
            chunk_id=evidence.chunk_id,
            char_start=evidence.char_start,
            char_end=evidence.char_end,
            excerpt=evidence.text,
            text_sha256=evidence.text_sha256,
            retrieval_score=evidence.retrieval_score,
            retrieval_rank=evidence.retrieval_rank,
        )

    @staticmethod
    def _document_selection_conflict() -> ProblemException:
        return ProblemException(
            status_code=409,
            code="DOCUMENT_SELECTION_NOT_SEARCHABLE",
            title="Selected documents cannot be searched together",
            detail=(
                "Every selected document must be READY and use one compatible active "
                "embedding space."
            ),
        )
