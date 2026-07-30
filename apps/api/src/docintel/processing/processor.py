from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from functools import partial

from anyio import to_thread
from sqlalchemy import delete, func, or_, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from docintel.core.config import Settings
from docintel.db.session import SessionFactory
from docintel.models import (
    Chunk,
    ChunkEmbedding,
    Document,
    DocumentJob,
    DocumentPage,
    DocumentStage,
    DocumentStatus,
    EmbeddingSpace,
    JobKind,
    JobStatus,
    ProgressUnit,
)
from docintel.processing.chunking import ChunkingConfig, ChunkSlice, chunk_page
from docintel.processing.embeddings import (
    EmbeddingProvider,
    EmbeddingSpaceIdentity,
    validate_embedding_batch,
)
from docintel.processing.errors import ProcessingCancelled, ProcessingError
from docintel.processing.pdf import ExtractedPage, ValidatedPdf, extract_page, validate_pdf
from docintel.storage.protocol import DocumentStorage, StorageError

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ClaimedProcessing:
    job_id: uuid.UUID
    document_id: uuid.UUID
    processing_revision: int
    attempts: int
    max_attempts: int


class ProcessingProcessor:
    """Durably executes deterministic Phase 4 processing jobs."""

    def __init__(
        self,
        session_factory: SessionFactory,
        storage: DocumentStorage,
        settings: Settings,
        embedding_provider: EmbeddingProvider,
        *,
        worker_id: str,
    ) -> None:
        self.session_factory = session_factory
        self.storage = storage
        self.settings = settings
        self.embedding_provider = embedding_provider
        self.worker_id = worker_id
        self.chunking_config = ChunkingConfig(
            target_chars=settings.chunk_target_chars,
            max_chars=settings.chunk_max_chars,
            overlap_chars=settings.chunk_overlap_chars,
            version=settings.chunker_version,
        )

    async def run_once(self) -> bool:
        claim = await self._claim()
        if claim is None:
            return False

        try:
            await self._process(claim)
        except ProcessingCancelled:
            await self._record_cancellation(claim)
        except ProcessingError as exception:
            logger.warning(
                "Document processing stopped with a safe failure.",
                extra={
                    "document_id": str(claim.document_id),
                    "job_id": str(claim.job_id),
                    "error_code": exception.code,
                    "retryable": exception.retryable,
                },
            )
            await self._record_failure(claim, exception)
        except Exception as exception:
            logger.error(
                "Document processing stopped unexpectedly.",
                extra={
                    "document_id": str(claim.document_id),
                    "job_id": str(claim.job_id),
                    "exception_type": type(exception).__name__,
                },
            )
            await self._record_failure(
                claim,
                ProcessingError(
                    "PROCESSING_TEMPORARY_FAILURE",
                    "Document processing temporarily failed.",
                    retryable=True,
                ),
            )
        return True

    async def _claim(self) -> ClaimedProcessing | None:
        now = datetime.now(UTC)
        async with self.session_factory() as session:
            async with session.begin():
                job = await session.scalar(
                    select(DocumentJob)
                    .join(Document, Document.id == DocumentJob.document_id)
                    .where(
                        DocumentJob.kind == JobKind.PROCESSING,
                        Document.status != DocumentStatus.DELETING,
                        or_(
                            (
                                (DocumentJob.status == JobStatus.QUEUED)
                                & (DocumentJob.available_at <= now)
                            ),
                            (
                                (DocumentJob.status == JobStatus.RUNNING)
                                & (DocumentJob.lease_expires_at <= now)
                            ),
                        ),
                    )
                    .order_by(DocumentJob.available_at, DocumentJob.created_at)
                    .with_for_update(skip_locked=True)
                    .limit(1)
                )
                if job is None:
                    return None

                job.status = JobStatus.RUNNING
                job.attempts += 1
                job.claimed_by = self.worker_id
                job.lease_expires_at = now + timedelta(seconds=self.settings.worker_lease_seconds)
                job.started_at = job.started_at or now
                job.last_heartbeat_at = now
                job.updated_at = now
                job.error_code = None
                job.error_message = None
                job.failure_retryable = None
                await session.flush()
                return ClaimedProcessing(
                    job_id=job.id,
                    document_id=job.document_id,
                    processing_revision=job.processing_revision,
                    attempts=job.attempts,
                    max_attempts=job.max_attempts,
                )

    async def _process(self, claim: ClaimedProcessing) -> None:
        storage_key = await self._prepare_attempt(claim)
        try:
            path = self.storage.path_for(storage_key)
        except StorageError as exception:
            raise ProcessingError(
                "STORAGE_REFERENCE_INVALID",
                "The stored PDF reference is invalid.",
                retryable=False,
            ) from exception

        await self._set_stage(
            claim,
            DocumentStage.VALIDATING,
            completed=0,
            total=None,
            unit=None,
        )
        validated = await to_thread.run_sync(
            lambda: validate_pdf(path, max_pages=self.settings.pdf_max_pages)
        )
        await self._persist_validation(claim, validated)

        await self._set_stage(
            claim,
            DocumentStage.EXTRACTING,
            completed=0,
            total=validated.page_count,
            unit=ProgressUnit.PAGES,
        )
        text_page_count = 0
        for page_number in range(1, validated.page_count + 1):
            await self._heartbeat(claim)
            extracted_page = await to_thread.run_sync(
                partial(
                    extract_page,
                    path,
                    page_number=page_number,
                )
            )
            if extracted_page.has_text:
                text_page_count += 1
            await self._persist_page(
                claim,
                extracted_page,
                completed=page_number,
                text_page_count=text_page_count,
            )

        if text_page_count == 0:
            raise ProcessingError(
                "NO_EXTRACTABLE_TEXT",
                "The PDF does not contain extractable text. OCR is not available.",
                retryable=False,
            )

        pages = await self._load_pages(claim)
        await self._set_stage(
            claim,
            DocumentStage.CHUNKING,
            completed=0,
            total=len(pages),
            unit=ProgressUnit.PAGES,
        )
        global_ordinal = 0
        for completed, stored_page in enumerate(pages, start=1):
            await self._heartbeat(claim)
            page_chunks = chunk_page(stored_page.text, self.chunking_config)
            await self._persist_page_chunks(
                claim,
                stored_page,
                page_chunks=page_chunks,
                starting_ordinal=global_ordinal,
                completed=completed,
            )
            global_ordinal += len(page_chunks)

        chunks = await self._load_chunks(claim)
        if not chunks:
            raise ProcessingError(
                "CHUNKING_EMPTY",
                "The PDF text could not be divided into chunks.",
                retryable=False,
            )

        embedding_identity = self.embedding_provider.identity
        embedding_space_id = await self._get_or_create_embedding_space(embedding_identity)
        await self._set_stage(
            claim,
            DocumentStage.EMBEDDING,
            completed=0,
            total=len(chunks),
            unit=ProgressUnit.CHUNKS,
        )
        for offset in range(0, len(chunks), self.settings.embedding_batch_size):
            await self._heartbeat(claim)
            batch = chunks[offset : offset + self.settings.embedding_batch_size]
            texts = [chunk.text for chunk in batch]
            vectors = await self.embedding_provider.embed(texts)
            validate_embedding_batch(
                texts=texts,
                vectors=vectors,
                expected_identity=embedding_identity,
                actual_identity=self.embedding_provider.identity,
            )
            await self._persist_embedding_batch(
                claim,
                chunks=batch,
                vectors=vectors,
                embedding_space_id=embedding_space_id,
                completed=offset + len(batch),
            )

        if not await self.storage.exists(storage_key):
            raise ProcessingError(
                "STORED_PDF_MISSING",
                "The stored PDF is unavailable.",
                retryable=True,
            )
        final_validation = await to_thread.run_sync(
            lambda: validate_pdf(path, max_pages=self.settings.pdf_max_pages)
        )
        await self._mark_ready(
            claim,
            expected_page_count=final_validation.page_count,
            embedding_space_id=embedding_space_id,
        )

    async def _prepare_attempt(self, claim: ClaimedProcessing) -> str:
        now = datetime.now(UTC)
        async with self.session_factory() as session:
            async with session.begin():
                document, job = await self._lock_active(session, claim)
                await session.execute(
                    delete(DocumentPage).where(DocumentPage.document_id == claim.document_id)
                )
                document.status = DocumentStatus.PROCESSING
                document.stage = DocumentStage.VALIDATING
                document.stage_started_at = now
                document.processing_started_at = document.processing_started_at or now
                document.processing_completed_at = None
                document.page_count = 0
                document.text_page_count = 0
                document.chunk_count = 0
                document.pdf_metadata = {}
                document.active_embedding_space_id = None
                document.progress_completed = 0
                document.progress_total = None
                document.progress_unit = None
                document.error_code = None
                document.error_message = None
                document.error_retryable = None
                document.updated_at = now
                self._renew_job(job, now)
                return document.storage_key

    async def _set_stage(
        self,
        claim: ClaimedProcessing,
        stage: DocumentStage,
        *,
        completed: int,
        total: int | None,
        unit: ProgressUnit | None,
    ) -> None:
        now = datetime.now(UTC)
        async with self.session_factory() as session:
            async with session.begin():
                document, job = await self._lock_active(session, claim)
                document.status = DocumentStatus.PROCESSING
                document.stage = stage
                document.stage_started_at = now
                document.progress_completed = completed
                document.progress_total = total
                document.progress_unit = unit
                document.updated_at = now
                job.stage = stage
                job.stage_started_at = now
                job.progress_completed = completed
                job.progress_total = total
                job.progress_unit = unit
                self._renew_job(job, now)

    async def _persist_validation(
        self,
        claim: ClaimedProcessing,
        validated: ValidatedPdf,
    ) -> None:
        now = datetime.now(UTC)
        async with self.session_factory() as session:
            async with session.begin():
                document, job = await self._lock_active(session, claim)
                document.page_count = validated.page_count
                document.pdf_metadata = validated.metadata
                document.updated_at = now
                self._renew_job(job, now)

    async def _persist_page(
        self,
        claim: ClaimedProcessing,
        page: ExtractedPage,
        *,
        completed: int,
        text_page_count: int,
    ) -> None:
        now = datetime.now(UTC)
        async with self.session_factory() as session:
            async with session.begin():
                document, job = await self._lock_active(session, claim)
                session.add(
                    DocumentPage(
                        document_id=claim.document_id,
                        processing_revision=claim.processing_revision,
                        page_number=page.page_number,
                        width=page.width,
                        height=page.height,
                        text=page.text,
                        text_sha256=page.text_sha256,
                        char_count=page.char_count,
                    )
                )
                document.text_page_count = text_page_count
                document.progress_completed = completed
                document.updated_at = now
                job.progress_completed = completed
                self._renew_job(job, now)

    async def _load_pages(self, claim: ClaimedProcessing) -> list[DocumentPage]:
        await self._heartbeat(claim)
        async with self.session_factory() as session:
            return list(
                (
                    await session.scalars(
                        select(DocumentPage)
                        .where(
                            DocumentPage.document_id == claim.document_id,
                            DocumentPage.processing_revision == claim.processing_revision,
                        )
                        .order_by(DocumentPage.page_number)
                    )
                ).all()
            )

    async def _persist_page_chunks(
        self,
        claim: ClaimedProcessing,
        page: DocumentPage,
        *,
        page_chunks: list[ChunkSlice],
        starting_ordinal: int,
        completed: int,
    ) -> None:
        now = datetime.now(UTC)
        async with self.session_factory() as session:
            async with session.begin():
                document, job = await self._lock_active(session, claim)
                for page_ordinal, chunk in enumerate(page_chunks):
                    if page.text[chunk.char_start : chunk.char_end] != chunk.text:
                        raise ProcessingError(
                            "CHUNK_SLICE_MISMATCH",
                            "A deterministic chunk did not match its page text.",
                            retryable=False,
                        )
                    session.add(
                        Chunk(
                            document_id=claim.document_id,
                            page_id=page.id,
                            processing_revision=claim.processing_revision,
                            ordinal=starting_ordinal + page_ordinal,
                            page_ordinal=page_ordinal,
                            char_start=chunk.char_start,
                            char_end=chunk.char_end,
                            text=chunk.text,
                            text_sha256=chunk.text_sha256,
                            chunker_version=chunk.chunker_version,
                        )
                    )
                document.chunk_count = starting_ordinal + len(page_chunks)
                document.progress_completed = completed
                document.updated_at = now
                job.progress_completed = completed
                self._renew_job(job, now)

    async def _load_chunks(self, claim: ClaimedProcessing) -> list[Chunk]:
        await self._heartbeat(claim)
        async with self.session_factory() as session:
            return list(
                (
                    await session.scalars(
                        select(Chunk)
                        .where(
                            Chunk.document_id == claim.document_id,
                            Chunk.processing_revision == claim.processing_revision,
                        )
                        .order_by(Chunk.ordinal)
                    )
                ).all()
            )

    async def _get_or_create_embedding_space(
        self,
        identity: EmbeddingSpaceIdentity,
    ) -> uuid.UUID:
        values = {
            "id": uuid.uuid4(),
            "provider": identity.provider,
            "model": identity.model,
            "dimensions": identity.dimensions,
            "distance_metric": identity.distance_metric,
            "configuration_hash": identity.configuration_hash,
        }
        async with self.session_factory() as session:
            async with session.begin():
                created_id = await session.scalar(
                    insert(EmbeddingSpace)
                    .values(**values)
                    .on_conflict_do_nothing(
                        constraint="uq_embedding_spaces_identity",
                    )
                    .returning(EmbeddingSpace.id)
                )
                if created_id is not None:
                    return created_id
                existing_id = await session.scalar(
                    select(EmbeddingSpace.id).where(
                        EmbeddingSpace.provider == identity.provider,
                        EmbeddingSpace.model == identity.model,
                        EmbeddingSpace.dimensions == identity.dimensions,
                        EmbeddingSpace.distance_metric == identity.distance_metric,
                        EmbeddingSpace.configuration_hash == identity.configuration_hash,
                    )
                )
                if existing_id is None:
                    raise ProcessingError(
                        "EMBEDDING_SPACE_UNAVAILABLE",
                        "The embedding space could not be initialized.",
                        retryable=True,
                    )
                return existing_id

    async def _persist_embedding_batch(
        self,
        claim: ClaimedProcessing,
        *,
        chunks: list[Chunk],
        vectors: list[list[float]],
        embedding_space_id: uuid.UUID,
        completed: int,
    ) -> None:
        now = datetime.now(UTC)
        async with self.session_factory() as session:
            async with session.begin():
                document, job = await self._lock_active(session, claim)
                session.add_all(
                    [
                        ChunkEmbedding(
                            chunk_id=chunk.id,
                            embedding_space_id=embedding_space_id,
                            embedding=vector,
                        )
                        for chunk, vector in zip(chunks, vectors, strict=True)
                    ]
                )
                document.progress_completed = completed
                document.updated_at = now
                job.progress_completed = completed
                self._renew_job(job, now)

    async def _mark_ready(
        self,
        claim: ClaimedProcessing,
        *,
        expected_page_count: int,
        embedding_space_id: uuid.UUID,
    ) -> None:
        now = datetime.now(UTC)
        async with self.session_factory() as session:
            async with session.begin():
                document, job = await self._lock_active(session, claim)
                pages = list(
                    (
                        await session.scalars(
                            select(DocumentPage)
                            .where(
                                DocumentPage.document_id == claim.document_id,
                                DocumentPage.processing_revision == claim.processing_revision,
                            )
                            .order_by(DocumentPage.page_number)
                        )
                    ).all()
                )
                chunks = list(
                    (
                        await session.scalars(
                            select(Chunk)
                            .where(
                                Chunk.document_id == claim.document_id,
                                Chunk.processing_revision == claim.processing_revision,
                            )
                            .order_by(Chunk.ordinal)
                        )
                    ).all()
                )
                embedding_count = await session.scalar(
                    select(func.count())
                    .select_from(ChunkEmbedding)
                    .join(Chunk, Chunk.id == ChunkEmbedding.chunk_id)
                    .where(
                        Chunk.document_id == claim.document_id,
                        Chunk.processing_revision == claim.processing_revision,
                        ChunkEmbedding.embedding_space_id == embedding_space_id,
                    )
                )
                other_active_jobs = await session.scalar(
                    select(func.count())
                    .select_from(DocumentJob)
                    .where(
                        DocumentJob.document_id == claim.document_id,
                        DocumentJob.kind == JobKind.PROCESSING,
                        DocumentJob.id != claim.job_id,
                        DocumentJob.status.in_([JobStatus.QUEUED, JobStatus.RUNNING]),
                    )
                )

                if document.page_count != expected_page_count or len(pages) != expected_page_count:
                    raise self._ready_invariant_failure()
                if [page.page_number for page in pages] != list(range(1, expected_page_count + 1)):
                    raise self._ready_invariant_failure()
                if not chunks or document.chunk_count != len(chunks):
                    raise self._ready_invariant_failure()
                chunks_by_page: dict[uuid.UUID, int] = {}
                pages_by_id = {page.id: page for page in pages}
                for expected_ordinal, chunk in enumerate(chunks):
                    page = pages_by_id.get(chunk.page_id)
                    if (
                        page is None
                        or chunk.ordinal != expected_ordinal
                        or chunk.processing_revision != claim.processing_revision
                        or page.text[chunk.char_start : chunk.char_end] != chunk.text
                    ):
                        raise self._ready_invariant_failure()
                    chunks_by_page[page.id] = chunks_by_page.get(page.id, 0) + 1
                if any(page.text.strip() and chunks_by_page.get(page.id, 0) == 0 for page in pages):
                    raise self._ready_invariant_failure()
                if embedding_count != len(chunks) or other_active_jobs:
                    raise self._ready_invariant_failure()
                if job.cancellation_requested or document.status == DocumentStatus.DELETING:
                    raise ProcessingCancelled

                job.status = JobStatus.COMPLETED
                job.progress_completed = len(chunks)
                job.progress_total = len(chunks)
                job.progress_unit = ProgressUnit.CHUNKS
                job.completed_at = now
                job.claimed_by = None
                job.lease_expires_at = None
                job.last_heartbeat_at = now
                job.updated_at = now

                document.status = DocumentStatus.READY
                document.stage = DocumentStage.EMBEDDING
                document.progress_completed = len(chunks)
                document.progress_total = len(chunks)
                document.progress_unit = ProgressUnit.CHUNKS
                document.active_embedding_space_id = embedding_space_id
                document.processing_completed_at = now
                document.error_code = None
                document.error_message = None
                document.error_retryable = None
                document.updated_at = now

    async def _heartbeat(self, claim: ClaimedProcessing) -> None:
        now = datetime.now(UTC)
        async with self.session_factory() as session:
            async with session.begin():
                _, job = await self._lock_active(session, claim)
                self._renew_job(job, now)

    async def _record_cancellation(self, claim: ClaimedProcessing) -> None:
        now = datetime.now(UTC)
        async with self.session_factory() as session:
            async with session.begin():
                job = await session.get(DocumentJob, claim.job_id, with_for_update=True)
                if (
                    job is None
                    or job.status != JobStatus.RUNNING
                    or job.claimed_by != self.worker_id
                ):
                    return
                job.status = JobStatus.CANCELLED
                job.cancellation_requested = True
                job.completed_at = now
                job.claimed_by = None
                job.lease_expires_at = None
                job.last_heartbeat_at = now
                job.updated_at = now

    async def _record_failure(
        self,
        claim: ClaimedProcessing,
        error: ProcessingError,
    ) -> None:
        now = datetime.now(UTC)
        async with self.session_factory() as session:
            async with session.begin():
                document = await session.get(
                    Document,
                    claim.document_id,
                    with_for_update=True,
                )
                job = await session.get(DocumentJob, claim.job_id, with_for_update=True)
                if document is None or job is None:
                    return
                if job.status != JobStatus.RUNNING or job.claimed_by != self.worker_id:
                    return
                if document.status == DocumentStatus.DELETING or job.cancellation_requested:
                    job.status = JobStatus.CANCELLED
                    job.completed_at = now
                    job.claimed_by = None
                    job.lease_expires_at = None
                    job.updated_at = now
                    return

                job.error_code = error.code
                job.error_message = error.safe_message
                job.failure_retryable = error.retryable
                job.claimed_by = None
                job.lease_expires_at = None
                job.last_heartbeat_at = now
                job.updated_at = now

                if error.retryable and claim.attempts < claim.max_attempts:
                    delay = self.settings.processing_retry_base_seconds * (
                        2 ** max(0, claim.attempts - 1)
                    )
                    job.status = JobStatus.QUEUED
                    job.available_at = now + timedelta(seconds=delay)
                    document.status = DocumentStatus.QUEUED
                    document.stage = DocumentStage.QUEUED
                    document.stage_started_at = now
                    document.progress_completed = 0
                    document.progress_total = None
                    document.progress_unit = None
                    document.error_code = "PROCESSING_RETRYING"
                    document.error_message = "Document processing will be retried."
                    document.error_retryable = True
                else:
                    job.status = JobStatus.FAILED
                    job.completed_at = now
                    document.status = DocumentStatus.FAILED
                    document.error_code = error.code
                    document.error_message = error.safe_message
                    document.error_retryable = error.retryable
                document.updated_at = now

    async def _lock_active(
        self,
        session: AsyncSession,
        claim: ClaimedProcessing,
    ) -> tuple[Document, DocumentJob]:
        document = await session.get(
            Document,
            claim.document_id,
            with_for_update=True,
        )
        job = await session.get(DocumentJob, claim.job_id, with_for_update=True)
        if (
            document is None
            or job is None
            or document.processing_revision != claim.processing_revision
            or job.processing_revision != claim.processing_revision
            or document.status == DocumentStatus.DELETING
            or job.status != JobStatus.RUNNING
            or job.claimed_by != self.worker_id
            or job.cancellation_requested
        ):
            raise ProcessingCancelled
        return document, job

    def _renew_job(self, job: DocumentJob, now: datetime) -> None:
        job.lease_expires_at = now + timedelta(seconds=self.settings.worker_lease_seconds)
        job.last_heartbeat_at = now
        job.updated_at = now

    @staticmethod
    def _ready_invariant_failure() -> ProcessingError:
        return ProcessingError(
            "READY_INVARIANT_FAILED",
            "Document processing did not satisfy readiness requirements.",
            retryable=True,
        )
