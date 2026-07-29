from __future__ import annotations

import asyncio
import uuid
from collections.abc import Iterator
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
from docintel.db.session import create_engine, create_session_factory
from docintel.main import create_app
from docintel.models import Document, DocumentJob, DocumentStatus, JobKind, JobStatus
from docintel.services.deletion import DeletionProcessor
from docintel.storage.local import LocalDocumentStorage
from docintel.storage.protocol import StorageError

PDF_BYTES = b"%PDF-1.4\n1 0 obj\n<< /Type /Catalog >>\nendobj\n%%EOF\n"


class FailingDeleteStorage(LocalDocumentStorage):
    async def delete(self, storage_key: str) -> None:
        raise StorageError("Injected deletion failure.")


@pytest.fixture
def lifecycle_settings(tmp_path: Path) -> Settings:
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
        upload_max_bytes=1024,
        upload_chunk_bytes=16,
        deletion_job_max_attempts=2,
        deletion_retry_base_seconds=0,
    )


@pytest.fixture
def sync_engine(lifecycle_settings: Settings) -> Iterator[Engine]:
    engine = create_sync_engine(lifecycle_settings.database_url)
    with engine.begin() as connection:
        connection.execute(delete(DocumentJob))
        connection.execute(delete(Document))
    yield engine
    with engine.begin() as connection:
        connection.execute(delete(DocumentJob))
        connection.execute(delete(Document))
    engine.dispose()


@pytest.fixture
def lifecycle_client(
    lifecycle_settings: Settings,
    sync_engine: Engine,
) -> Iterator[TestClient]:
    del sync_engine
    with TestClient(
        create_app(settings=lifecycle_settings),
        raise_server_exceptions=False,
    ) as client:
        yield client


def upload_pdf(
    client: TestClient,
    *,
    name: str = "Policy.pdf",
    content: bytes = PDF_BYTES,
    content_type: str = "application/pdf",
) -> Response:
    return cast(
        Response,
        client.post(
            "/api/v1/documents",
            files={"file": (name, content, content_type)},
        ),
    )


def run_deletion_once(
    settings: Settings,
    storage: LocalDocumentStorage,
) -> bool:
    async def execute() -> bool:
        engine = create_engine(settings.database_url)
        processor = DeletionProcessor(
            create_session_factory(engine),
            storage,
            settings,
            worker_id="integration-test-worker",
        )
        try:
            return await processor.run_once()
        finally:
            await engine.dispose()

    return asyncio.run(execute())


@pytest.mark.integration
def test_upload_creates_file_document_and_processing_job_atomically(
    lifecycle_client: TestClient,
    lifecycle_settings: Settings,
    sync_engine: Engine,
) -> None:
    response = upload_pdf(
        lifecycle_client,
        name="../../Quarterly Report.pdf",
    )

    assert response.status_code == 202
    payload = response.json()["document"]
    document_id = uuid.UUID(payload["id"])
    assert payload["name"] == "Quarterly Report.pdf"
    assert payload["status"] == "queued"
    assert payload["stage"] == "queued"
    assert payload["progress"] == {"completed": 0, "total": None, "unit": None}

    with Session(sync_engine) as session:
        document = session.get(Document, document_id)
        jobs = session.scalars(
            select(DocumentJob).where(DocumentJob.document_id == document_id)
        ).all()

    assert document is not None
    assert document.storage_key == f"{document_id}.pdf"
    assert "/" not in document.storage_key
    assert document.byte_size == len(PDF_BYTES)
    assert len(jobs) == 1
    assert jobs[0].kind == JobKind.PROCESSING
    assert jobs[0].status == JobStatus.QUEUED
    assert (lifecycle_settings.uploads_path / document.storage_key).read_bytes() == PDF_BYTES
    assert list(lifecycle_settings.uploads_path.glob("*.part")) == []


@pytest.mark.integration
def test_upload_validation_rejects_bad_inputs_without_residue(
    lifecycle_client: TestClient,
    lifecycle_settings: Settings,
    sync_engine: Engine,
) -> None:
    cases = [
        ("bad.txt", PDF_BYTES, "application/pdf", 415, "INVALID_PDF_EXTENSION"),
        ("bad.pdf", PDF_BYTES, "text/plain", 415, "INVALID_PDF_MEDIA_TYPE"),
        ("bad.pdf", b"not-pdf", "application/pdf", 422, "INVALID_PDF_SIGNATURE"),
        (
            "large.pdf",
            b"%PDF-" + b"x" * 1024,
            "application/pdf",
            413,
            "PDF_TOO_LARGE",
        ),
    ]

    for name, content, media_type, expected_status, expected_code in cases:
        response = upload_pdf(
            lifecycle_client,
            name=name,
            content=content,
            content_type=media_type,
        )
        assert response.status_code == expected_status
        assert response.headers["content-type"].startswith("application/problem+json")
        assert response.json()["code"] == expected_code
        assert response.json()["trace_id"] == response.headers["x-trace-id"]

    multiple = lifecycle_client.post(
        "/api/v1/documents",
        files=[
            ("file", ("one.pdf", PDF_BYTES, "application/pdf")),
            ("file", ("two.pdf", PDF_BYTES, "application/pdf")),
        ],
    )
    assert multiple.status_code == 400
    assert multiple.json()["code"] == "ONE_PDF_REQUIRED"

    with Session(sync_engine) as session:
        assert session.scalar(select(func.count()).select_from(Document)) == 0
        assert session.scalar(select(func.count()).select_from(DocumentJob)) == 0
    assert list(lifecycle_settings.uploads_path.iterdir()) == []


@pytest.mark.integration
def test_list_detail_status_content_etag_and_ranges(
    lifecycle_client: TestClient,
) -> None:
    alpha = upload_pdf(lifecycle_client, name="Alpha Policy.pdf").json()["document"]
    beta = upload_pdf(lifecycle_client, name="Beta Policy.pdf").json()["document"]

    searched = lifecycle_client.get(
        "/api/v1/documents",
        params={"search": "Alpha", "status": "queued", "sort": "name", "order": "asc"},
    )
    assert searched.status_code == 200
    assert [item["name"] for item in searched.json()["items"]] == ["Alpha Policy.pdf"]

    first_page = lifecycle_client.get(
        "/api/v1/documents",
        params={"limit": 1, "sort": "name", "order": "asc"},
    )
    assert first_page.status_code == 200
    assert first_page.json()["items"][0]["id"] == alpha["id"]
    cursor = first_page.json()["next_cursor"]
    assert cursor

    second_page = lifecycle_client.get(
        "/api/v1/documents",
        params={"limit": 1, "sort": "name", "order": "asc", "cursor": cursor},
    )
    assert second_page.status_code == 200
    assert second_page.json()["items"][0]["id"] == beta["id"]

    detail = lifecycle_client.get(f"/api/v1/documents/{alpha['id']}")
    compact_status = lifecycle_client.get(f"/api/v1/documents/{alpha['id']}/status")
    assert detail.status_code == 200
    assert detail.json()["sha256"]
    assert compact_status.status_code == 200
    assert compact_status.json()["status"] == "queued"

    content = lifecycle_client.get(f"/api/v1/documents/{alpha['id']}/content")
    assert content.status_code == 200
    assert content.content == PDF_BYTES
    assert content.headers["content-type"] == "application/pdf"
    assert content.headers["accept-ranges"] == "bytes"
    assert content.headers["content-disposition"].startswith("inline;")
    etag = content.headers["etag"]

    not_modified = lifecycle_client.get(
        f"/api/v1/documents/{alpha['id']}/content",
        headers={"If-None-Match": etag},
    )
    assert not_modified.status_code == 304

    partial = lifecycle_client.get(
        f"/api/v1/documents/{alpha['id']}/content",
        headers={"Range": "bytes=0-4"},
    )
    assert partial.status_code == 206
    assert partial.content == b"%PDF-"
    assert partial.headers["content-range"] == f"bytes 0-4/{len(PDF_BYTES)}"

    invalid_range = lifecycle_client.get(
        f"/api/v1/documents/{alpha['id']}/content",
        headers={"Range": "bytes=9999-10000"},
    )
    assert invalid_range.status_code == 416
    assert invalid_range.json()["code"] == "RANGE_NOT_SATISFIABLE"


@pytest.mark.integration
def test_deletion_is_idempotent_while_active_and_removes_aggregate(
    lifecycle_client: TestClient,
    lifecycle_settings: Settings,
    sync_engine: Engine,
) -> None:
    document = upload_pdf(lifecycle_client).json()["document"]
    document_id = uuid.UUID(document["id"])

    first_delete = lifecycle_client.delete(f"/api/v1/documents/{document_id}")
    second_delete = lifecycle_client.delete(f"/api/v1/documents/{document_id}")
    assert first_delete.status_code == 202
    assert second_delete.status_code == 202
    assert first_delete.json()["document"]["status"] == "deleting"

    with Session(sync_engine) as session:
        processing_job = session.scalar(
            select(DocumentJob).where(
                DocumentJob.document_id == document_id,
                DocumentJob.kind == JobKind.PROCESSING,
            )
        )
        deletion_jobs = session.scalars(
            select(DocumentJob).where(
                DocumentJob.document_id == document_id,
                DocumentJob.kind == JobKind.DELETION,
            )
        ).all()
        stored_document = session.get(Document, document_id)
        assert stored_document is not None
        stored_key = stored_document.storage_key

    assert processing_job is not None
    assert processing_job.status == JobStatus.CANCELLED
    assert len(deletion_jobs) == 1
    assert run_deletion_once(
        lifecycle_settings,
        LocalDocumentStorage(lifecycle_settings.uploads_path),
    )
    assert not (lifecycle_settings.uploads_path / stored_key).exists()

    with Session(sync_engine) as session:
        assert session.get(Document, document_id) is None
        assert (
            session.scalar(
                select(func.count())
                .select_from(DocumentJob)
                .where(DocumentJob.document_id == document_id)
            )
            == 0
        )
    assert lifecycle_client.get(f"/api/v1/documents/{document_id}").status_code == 404


@pytest.mark.integration
def test_deletion_failure_keeps_aggregate_and_can_recover(
    lifecycle_client: TestClient,
    lifecycle_settings: Settings,
    sync_engine: Engine,
) -> None:
    document = upload_pdf(lifecycle_client).json()["document"]
    document_id = uuid.UUID(document["id"])
    lifecycle_client.delete(f"/api/v1/documents/{document_id}")

    assert run_deletion_once(
        lifecycle_settings,
        FailingDeleteStorage(lifecycle_settings.uploads_path),
    )

    with Session(sync_engine) as session:
        retained = session.get(Document, document_id)
        deletion_job = session.scalar(
            select(DocumentJob).where(
                DocumentJob.document_id == document_id,
                DocumentJob.kind == JobKind.DELETION,
            )
        )

    assert retained is not None
    assert retained.status == DocumentStatus.DELETING
    assert retained.error_code == "DELETE_RETRYING"
    assert deletion_job is not None
    assert deletion_job.status == JobStatus.QUEUED
    assert deletion_job.attempts == 1
    assert (lifecycle_settings.uploads_path / retained.storage_key).exists()

    assert run_deletion_once(
        lifecycle_settings,
        LocalDocumentStorage(lifecycle_settings.uploads_path),
    )
    with Session(sync_engine) as session:
        assert session.get(Document, document_id) is None


@pytest.mark.integration
def test_missing_document_operations_return_sanitized_problems(
    lifecycle_client: TestClient,
) -> None:
    missing_id = uuid.uuid4()

    for method, path in [
        ("GET", f"/api/v1/documents/{missing_id}"),
        ("GET", f"/api/v1/documents/{missing_id}/status"),
        ("GET", f"/api/v1/documents/{missing_id}/content"),
        ("DELETE", f"/api/v1/documents/{missing_id}"),
    ]:
        response = lifecycle_client.request(method, path)
        assert response.status_code == 404
        assert response.json()["code"] == "DOCUMENT_NOT_FOUND"
        assert response.json()["trace_id"] == response.headers["x-trace-id"]
