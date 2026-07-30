from __future__ import annotations

import asyncio
import hashlib
import math
import uuid
from collections.abc import Callable, Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import cast

import pytest
from fastapi.testclient import TestClient
from httpx import Response
from sqlalchemy import create_engine as create_sync_engine
from sqlalchemy import delete, func, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from docintel.core.config import Settings
from docintel.db.session import SessionFactory, create_engine, create_session_factory
from docintel.main import create_app
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
from docintel.processing.embeddings import (
    DeterministicMockEmbeddingProvider,
    EmbeddingProvider,
    EmbeddingSpaceIdentity,
)
from docintel.processing.processor import ClaimedProcessing, ProcessingProcessor
from docintel.services.deletion import DeletionProcessor
from docintel.storage.local import LocalDocumentStorage
from docintel.storage.protocol import DocumentStorage
from tests.pdf_factory import make_encrypted_pdf, make_scan_only_pdf, make_text_pdf


class BlockingEmbeddingProvider:
    def __init__(self) -> None:
        self.delegate = DeterministicMockEmbeddingProvider()
        self.started = asyncio.Event()
        self.release = asyncio.Event()

    @property
    def identity(self) -> EmbeddingSpaceIdentity:
        return self.delegate.identity

    async def embed(self, texts: list[str]) -> list[list[float]]:
        self.started.set()
        await self.release.wait()
        return await self.delegate.embed(texts)


class RecordingProcessingProcessor(ProcessingProcessor):
    def __init__(
        self,
        session_factory: SessionFactory,
        storage: DocumentStorage,
        settings: Settings,
        embedding_provider: EmbeddingProvider,
        *,
        worker_id: str,
        stage_log: list[DocumentStage],
    ) -> None:
        super().__init__(
            session_factory,
            storage,
            settings,
            embedding_provider,
            worker_id=worker_id,
        )
        self.stage_log = stage_log

    async def _set_stage(
        self,
        claim: ClaimedProcessing,
        stage: DocumentStage,
        *,
        completed: int,
        total: int | None,
        unit: ProgressUnit | None,
    ) -> None:
        self.stage_log.append(stage)
        await super()._set_stage(
            claim,
            stage,
            completed=completed,
            total=total,
            unit=unit,
        )


@pytest.fixture
def processing_settings(tmp_path: Path) -> Settings:
    paths = {name: tmp_path / name for name in ("uploads", "processed", "samples", "backups")}
    for path in paths.values():
        path.mkdir()
    return Settings(
        _env_file=None,
        environment="test",
        uploads_path=paths["uploads"],
        processed_path=paths["processed"],
        samples_path=paths["samples"],
        backups_path=paths["backups"],
        upload_max_bytes=1024 * 1024,
        upload_chunk_bytes=1024,
        processing_job_max_attempts=3,
        processing_retry_base_seconds=0,
        deletion_retry_base_seconds=0,
        worker_lease_seconds=5,
    )


@pytest.fixture
def processing_engine(processing_settings: Settings) -> Iterator[Engine]:
    engine = create_sync_engine(processing_settings.database_url)
    with engine.begin() as connection:
        connection.execute(delete(Document))
        connection.execute(delete(EmbeddingSpace))
    yield engine
    with engine.begin() as connection:
        connection.execute(delete(Document))
        connection.execute(delete(EmbeddingSpace))
    engine.dispose()


@pytest.fixture
def processing_client(
    processing_settings: Settings,
    processing_engine: Engine,
) -> Iterator[TestClient]:
    del processing_engine
    with TestClient(
        create_app(settings=processing_settings),
        raise_server_exceptions=False,
    ) as client:
        yield client


def upload_pdf(client: TestClient, content: bytes, *, name: str = "Fictional.pdf") -> Response:
    return cast(
        Response,
        client.post(
            "/api/v1/documents",
            files={"file": (name, content, "application/pdf")},
        ),
    )


def run_processing_once(
    settings: Settings,
    provider: DeterministicMockEmbeddingProvider,
    *,
    worker_id: str = "processing-test-worker",
    stage_log: list[DocumentStage] | None = None,
) -> bool:
    async def execute() -> bool:
        engine = create_engine(settings.database_url)
        processor: ProcessingProcessor
        session_factory = create_session_factory(engine)
        storage = LocalDocumentStorage(settings.uploads_path)
        if stage_log is None:
            processor = ProcessingProcessor(
                session_factory,
                storage,
                settings,
                provider,
                worker_id=worker_id,
            )
        else:
            processor = RecordingProcessingProcessor(
                session_factory,
                storage,
                settings,
                provider,
                worker_id=worker_id,
                stage_log=stage_log,
            )
        try:
            return await processor.run_once()
        finally:
            await engine.dispose()

    return asyncio.run(execute())


def run_deletion_once(settings: Settings) -> bool:
    async def execute() -> bool:
        engine = create_engine(settings.database_url)
        processor = DeletionProcessor(
            create_session_factory(engine),
            LocalDocumentStorage(settings.uploads_path),
            settings,
            worker_id="deletion-test-worker",
        )
        try:
            return await processor.run_once()
        finally:
            await engine.dispose()

    return asyncio.run(execute())


@pytest.mark.integration
def test_valid_pdf_reaches_ready_with_page_correct_chunks_vectors_and_deletion(
    processing_client: TestClient,
    processing_settings: Settings,
    processing_engine: Engine,
) -> None:
    pdf = make_text_pdf(
        [
            (
                "Fictional Operations Policy\n\n"
                "The first paragraph defines a deterministic review process. "
                "Every record is fictional and contains no personal information."
            ),
            "",
            (
                "Fictional Continuity Plan\n\n"
                "The third page preserves its original PDF page number. "
                "Blank pages never shift the numbering."
            ),
        ],
        metadata={"title": " Fictional Operations Policy "},
    )
    upload = upload_pdf(processing_client, pdf)
    document_id = uuid.UUID(upload.json()["document"]["id"])
    stage_log: list[DocumentStage] = []

    assert upload.status_code == 202
    assert run_processing_once(
        processing_settings,
        DeterministicMockEmbeddingProvider(),
        stage_log=stage_log,
    )
    assert stage_log == [
        DocumentStage.VALIDATING,
        DocumentStage.EXTRACTING,
        DocumentStage.CHUNKING,
        DocumentStage.EMBEDDING,
    ]

    detail = processing_client.get(f"/api/v1/documents/{document_id}")
    status = processing_client.get(f"/api/v1/documents/{document_id}/status")
    assert detail.status_code == 200
    assert detail.json()["status"] == "ready"
    assert detail.json()["stage"] == "embedding"
    assert detail.json()["page_count"] == 3
    assert detail.json()["text_page_count"] == 2
    assert detail.json()["chunk_count"] >= 2
    assert detail.json()["pdf_metadata"]["title"] == "Fictional Operations Policy"
    assert detail.json()["processing_completed_at"]
    assert status.json()["progress"]["unit"] == "chunks"
    assert status.json()["progress"]["completed"] == status.json()["progress"]["total"]

    with Session(processing_engine) as session:
        document = session.get(Document, document_id)
        pages = session.scalars(
            select(DocumentPage)
            .where(DocumentPage.document_id == document_id)
            .order_by(DocumentPage.page_number)
        ).all()
        chunks = session.scalars(
            select(Chunk).where(Chunk.document_id == document_id).order_by(Chunk.ordinal)
        ).all()
        embeddings = session.scalars(
            select(ChunkEmbedding)
            .join(Chunk, Chunk.id == ChunkEmbedding.chunk_id)
            .where(Chunk.document_id == document_id)
        ).all()
        processing_job = session.scalar(
            select(DocumentJob).where(
                DocumentJob.document_id == document_id,
                DocumentJob.kind == JobKind.PROCESSING,
            )
        )
        assert document is not None
        storage_key = document.storage_key

    assert [page.page_number for page in pages] == [1, 2, 3]
    assert pages[1].text == ""
    assert all(page.char_count == len(page.text) for page in pages)
    assert all(
        page.text_sha256 == hashlib.sha256(page.text.encode("utf-8")).hexdigest() for page in pages
    )
    pages_by_id = {page.id: page for page in pages}
    assert [chunk.ordinal for chunk in chunks] == list(range(len(chunks)))
    for chunk in chunks:
        page = pages_by_id[chunk.page_id]
        assert chunk.text == page.text[chunk.char_start : chunk.char_end]
        assert 0 <= chunk.char_start < chunk.char_end <= len(page.text)
    assert len(embeddings) == len(chunks)
    for embedding in embeddings:
        vector = list(embedding.embedding)
        assert len(vector) == 1536
        assert all(math.isfinite(value) for value in vector)
        assert math.isclose(
            math.sqrt(sum(value * value for value in vector)),
            1.0,
            rel_tol=1e-5,
        )
    assert processing_job is not None
    assert processing_job.status == JobStatus.COMPLETED
    assert processing_job.stage == DocumentStage.EMBEDDING
    assert processing_job.progress_unit == ProgressUnit.CHUNKS
    assert processing_job.started_at is not None
    assert processing_job.stage_started_at is not None
    assert processing_job.last_heartbeat_at is not None

    deletion = processing_client.delete(f"/api/v1/documents/{document_id}")
    assert deletion.status_code == 202
    assert run_deletion_once(processing_settings)
    assert not (processing_settings.uploads_path / storage_key).exists()
    with Session(processing_engine) as session:
        assert session.get(Document, document_id) is None
        assert (
            session.scalar(
                select(func.count())
                .select_from(DocumentPage)
                .where(DocumentPage.document_id == document_id)
            )
            == 0
        )
        assert (
            session.scalar(
                select(func.count()).select_from(Chunk).where(Chunk.document_id == document_id)
            )
            == 0
        )
        assert (
            session.scalar(
                select(func.count())
                .select_from(ChunkEmbedding)
                .join(Chunk, Chunk.id == ChunkEmbedding.chunk_id)
                .where(Chunk.document_id == document_id)
            )
            == 0
        )


@pytest.mark.integration
@pytest.mark.parametrize(
    ("name", "content_factory", "expected_code", "max_pages"),
    [
        ("encrypted.pdf", make_encrypted_pdf, "PDF_ENCRYPTED", 500),
        (
            "corrupt.pdf",
            lambda: b"%PDF-this is deliberately corrupt",
            "PDF_CORRUPT",
            500,
        ),
        ("empty-text.pdf", lambda: make_text_pdf([""]), "NO_EXTRACTABLE_TEXT", 500),
        ("scan-only.pdf", make_scan_only_pdf, "NO_EXTRACTABLE_TEXT", 500),
        (
            "over-limit.pdf",
            lambda: make_text_pdf(["One", "Two", "Three"]),
            "PDF_PAGE_LIMIT_EXCEEDED",
            2,
        ),
    ],
)
def test_permanent_pdf_failures_are_safe_and_not_retryable(
    processing_client: TestClient,
    processing_settings: Settings,
    processing_engine: Engine,
    name: str,
    content_factory: object,
    expected_code: str,
    max_pages: int,
) -> None:
    factory = cast(Callable[[], bytes], content_factory)
    upload = upload_pdf(processing_client, factory(), name=name)
    document_id = uuid.UUID(upload.json()["document"]["id"])
    stage_settings = processing_settings.model_copy(update={"pdf_max_pages": max_pages})

    assert run_processing_once(
        stage_settings,
        DeterministicMockEmbeddingProvider(),
    )

    detail = processing_client.get(f"/api/v1/documents/{document_id}")
    retry = processing_client.post(f"/api/v1/documents/{document_id}/retry")
    assert detail.json()["status"] == "failed"
    assert detail.json()["error"] == {
        "code": expected_code,
        "message": detail.json()["error"]["message"],
        "retryable": False,
    }
    assert retry.status_code == 409
    assert retry.json()["code"] == "DOCUMENT_NOT_RETRYABLE"
    with Session(processing_engine) as session:
        job = session.scalar(
            select(DocumentJob).where(
                DocumentJob.document_id == document_id,
                DocumentJob.kind == JobKind.PROCESSING,
            )
        )
    assert job is not None
    assert job.status == JobStatus.FAILED
    assert job.failure_retryable is False


@pytest.mark.integration
def test_transient_embedding_failure_retries_automatically(
    processing_client: TestClient,
    processing_settings: Settings,
    processing_engine: Engine,
) -> None:
    upload = upload_pdf(
        processing_client,
        make_text_pdf(["Fictional transient embedding test."]),
    )
    document_id = uuid.UUID(upload.json()["document"]["id"])
    provider = DeterministicMockEmbeddingProvider(fail_on_calls={1})

    assert run_processing_once(processing_settings, provider)
    retrying = processing_client.get(f"/api/v1/documents/{document_id}").json()
    assert retrying["status"] == "queued"
    assert retrying["error"]["code"] == "PROCESSING_RETRYING"
    assert retrying["error"]["retryable"] is True

    assert run_processing_once(processing_settings, provider)
    ready = processing_client.get(f"/api/v1/documents/{document_id}").json()
    assert ready["status"] == "ready"
    with Session(processing_engine) as session:
        job = session.scalar(
            select(DocumentJob).where(
                DocumentJob.document_id == document_id,
                DocumentJob.kind == JobKind.PROCESSING,
            )
        )
        page_count = session.scalar(
            select(func.count())
            .select_from(DocumentPage)
            .where(DocumentPage.document_id == document_id)
        )
    assert job is not None
    assert job.attempts == 2
    assert job.status == JobStatus.COMPLETED
    assert page_count == 1


@pytest.mark.integration
def test_manual_retry_replaces_stale_revision_and_prevents_duplicates(
    processing_settings: Settings,
    processing_engine: Engine,
) -> None:
    settings = processing_settings.model_copy(update={"processing_job_max_attempts": 1})
    with TestClient(create_app(settings=settings), raise_server_exceptions=False) as client:
        upload = upload_pdf(
            client,
            make_text_pdf(["Fictional manual retry test."]),
        )
        document_id = uuid.UUID(upload.json()["document"]["id"])
        failing_provider = DeterministicMockEmbeddingProvider(fail_on_calls={1})

        assert run_processing_once(settings, failing_provider)
        failed = client.get(f"/api/v1/documents/{document_id}").json()
        assert failed["status"] == "failed"
        assert failed["error"]["retryable"] is True

        retry = client.post(f"/api/v1/documents/{document_id}/retry")
        duplicate_retry = client.post(f"/api/v1/documents/{document_id}/retry")
        assert retry.status_code == 202
        assert retry.json()["document"]["processing_revision"] == 2
        assert duplicate_retry.status_code == 409
        assert duplicate_retry.json()["code"] == "DOCUMENT_RETRY_NOT_ALLOWED"

        assert run_processing_once(
            settings,
            DeterministicMockEmbeddingProvider(),
        )
        assert client.get(f"/api/v1/documents/{document_id}").json()["status"] == "ready"

    with Session(processing_engine) as session:
        document = session.get(Document, document_id)
        jobs = session.scalars(
            select(DocumentJob)
            .where(
                DocumentJob.document_id == document_id,
                DocumentJob.kind == JobKind.PROCESSING,
            )
            .order_by(DocumentJob.created_at)
        ).all()
        pages = session.scalars(
            select(DocumentPage).where(DocumentPage.document_id == document_id)
        ).all()
    assert document is not None
    assert document.processing_revision == 2
    assert [job.status for job in jobs] == [JobStatus.FAILED, JobStatus.COMPLETED]
    assert all(page.processing_revision == 2 for page in pages)


@pytest.mark.integration
def test_concurrent_claim_lease_renewal_and_expired_lease_reconciliation(
    processing_client: TestClient,
    processing_settings: Settings,
    processing_engine: Engine,
) -> None:
    upload = upload_pdf(
        processing_client,
        make_text_pdf(["Fictional worker recovery test."]),
    )
    document_id = uuid.UUID(upload.json()["document"]["id"])

    async def claim_concurrently() -> tuple[
        ClaimedProcessing | None,
        ClaimedProcessing | None,
    ]:
        engine = create_engine(processing_settings.database_url)
        factory = create_session_factory(engine)
        first = ProcessingProcessor(
            factory,
            LocalDocumentStorage(processing_settings.uploads_path),
            processing_settings,
            DeterministicMockEmbeddingProvider(),
            worker_id="worker-one",
        )
        second = ProcessingProcessor(
            factory,
            LocalDocumentStorage(processing_settings.uploads_path),
            processing_settings,
            DeterministicMockEmbeddingProvider(),
            worker_id="worker-two",
        )
        try:
            claims = await asyncio.gather(first._claim(), second._claim())
            owner = first if claims[0] is not None else second
            claim = claims[0] or claims[1]
            assert claim is not None
            await owner._heartbeat(claim)
            return claims
        finally:
            await engine.dispose()

    claims = asyncio.run(claim_concurrently())
    assert sum(claim is not None for claim in claims) == 1

    stale_text = "stale interrupted data"
    with Session(processing_engine) as session:
        job = session.scalar(
            select(DocumentJob).where(
                DocumentJob.document_id == document_id,
                DocumentJob.kind == JobKind.PROCESSING,
            )
        )
        assert job is not None
        heartbeat = job.last_heartbeat_at
        session.add(
            DocumentPage(
                document_id=document_id,
                processing_revision=1,
                page_number=1,
                width=612,
                height=792,
                text=stale_text,
                text_sha256=hashlib.sha256(stale_text.encode()).hexdigest(),
                char_count=len(stale_text),
            )
        )
        job.lease_expires_at = datetime.now(UTC) - timedelta(seconds=1)
        session.commit()

    assert heartbeat is not None
    assert run_processing_once(
        processing_settings,
        DeterministicMockEmbeddingProvider(),
        worker_id="recovery-worker",
    )
    with Session(processing_engine) as session:
        document = session.get(Document, document_id)
        job = session.scalar(
            select(DocumentJob).where(
                DocumentJob.document_id == document_id,
                DocumentJob.kind == JobKind.PROCESSING,
            )
        )
        pages = session.scalars(
            select(DocumentPage).where(DocumentPage.document_id == document_id)
        ).all()
    assert document is not None
    assert document.status == DocumentStatus.READY
    assert job is not None
    assert job.attempts == 2
    assert job.status == JobStatus.COMPLETED
    assert all(page.text != stale_text for page in pages)


@pytest.mark.integration
def test_processing_cancels_cooperatively_when_deletion_is_requested(
    processing_client: TestClient,
    processing_settings: Settings,
    processing_engine: Engine,
) -> None:
    upload = upload_pdf(
        processing_client,
        make_text_pdf(["Fictional cancellation test with deterministic content."]),
    )
    document_id = uuid.UUID(upload.json()["document"]["id"])
    provider = BlockingEmbeddingProvider()

    async def process_and_delete() -> tuple[bool, int]:
        engine = create_engine(processing_settings.database_url)
        processor = ProcessingProcessor(
            create_session_factory(engine),
            LocalDocumentStorage(processing_settings.uploads_path),
            processing_settings,
            provider,
            worker_id="cancellation-worker",
        )
        try:
            task = asyncio.create_task(processor.run_once())
            await asyncio.wait_for(provider.started.wait(), timeout=10)
            response = await asyncio.to_thread(
                processing_client.delete,
                f"/api/v1/documents/{document_id}",
            )
            provider.release.set()
            processed = await asyncio.wait_for(task, timeout=10)
            return processed, response.status_code
        finally:
            await engine.dispose()

    processed, delete_status = asyncio.run(process_and_delete())
    assert processed
    assert delete_status == 202
    with Session(processing_engine) as session:
        document = session.get(Document, document_id)
        processing_job = session.scalar(
            select(DocumentJob).where(
                DocumentJob.document_id == document_id,
                DocumentJob.kind == JobKind.PROCESSING,
            )
        )
        embedding_count = session.scalar(
            select(func.count())
            .select_from(ChunkEmbedding)
            .join(Chunk, Chunk.id == ChunkEmbedding.chunk_id)
            .where(Chunk.document_id == document_id)
        )
    assert document is not None
    assert document.status == DocumentStatus.DELETING
    assert processing_job is not None
    assert processing_job.status == JobStatus.CANCELLED
    assert embedding_count == 0

    assert run_deletion_once(processing_settings)
    with Session(processing_engine) as session:
        assert session.get(Document, document_id) is None
