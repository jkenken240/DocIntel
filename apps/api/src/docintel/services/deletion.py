from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import or_, select
from sqlalchemy.exc import SQLAlchemyError

from docintel.core.config import Settings
from docintel.db.session import SessionFactory
from docintel.models import Document, DocumentJob, DocumentStatus, JobKind, JobStatus
from docintel.storage.protocol import DocumentStorage, StorageError

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ClaimedDeletion:
    job_id: uuid.UUID
    document_id: uuid.UUID
    attempts: int
    max_attempts: int


class DeletionProcessor:
    """Claims and executes only durable document-deletion jobs."""

    def __init__(
        self,
        session_factory: SessionFactory,
        storage: DocumentStorage,
        settings: Settings,
        *,
        worker_id: str,
    ) -> None:
        self.session_factory = session_factory
        self.storage = storage
        self.settings = settings
        self.worker_id = worker_id

    async def run_once(self) -> bool:
        claim = await self._claim()
        if claim is None:
            return False

        document = await self._load_document(claim.document_id)
        if document is None:
            return True

        if await self._active_processing_must_finish(claim):
            return True

        try:
            await self.storage.delete(document.storage_key)
            if await self.storage.exists(document.storage_key):
                raise StorageError("Stored PDF remains after deletion.")
            await self._remove_database_aggregate(claim)
        except StorageError:
            logger.exception(
                "Document file deletion failed.",
                extra={
                    "document_id": str(claim.document_id),
                    "job_id": str(claim.job_id),
                },
            )
            await self._record_retryable_failure(claim)
        except SQLAlchemyError:
            logger.exception(
                "Document database cleanup failed; the lease will permit recovery.",
                extra={
                    "document_id": str(claim.document_id),
                    "job_id": str(claim.job_id),
                },
            )
        return True

    async def _claim(self) -> ClaimedDeletion | None:
        now = datetime.now(UTC)
        async with self.session_factory() as session:
            async with session.begin():
                job = await session.scalar(
                    select(DocumentJob)
                    .where(
                        DocumentJob.kind == JobKind.DELETION,
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
                job.updated_at = now
                await session.flush()
                return ClaimedDeletion(
                    job_id=job.id,
                    document_id=job.document_id,
                    attempts=job.attempts,
                    max_attempts=job.max_attempts,
                )

    async def _load_document(self, document_id: uuid.UUID) -> Document | None:
        async with self.session_factory() as session:
            return await session.get(Document, document_id)

    async def _active_processing_must_finish(self, claim: ClaimedDeletion) -> bool:
        now = datetime.now(UTC)
        async with self.session_factory() as session:
            async with session.begin():
                processing_job = await session.scalar(
                    select(DocumentJob)
                    .where(
                        DocumentJob.document_id == claim.document_id,
                        DocumentJob.kind == JobKind.PROCESSING,
                        DocumentJob.status == JobStatus.RUNNING,
                    )
                    .with_for_update()
                )
                if processing_job is None:
                    return False

                if (
                    processing_job.cancellation_requested
                    and processing_job.lease_expires_at is not None
                    and processing_job.lease_expires_at <= now
                ):
                    processing_job.status = JobStatus.CANCELLED
                    processing_job.completed_at = now
                    processing_job.updated_at = now
                    return False

                deletion_job = await session.get(DocumentJob, claim.job_id)
                if deletion_job is not None:
                    deletion_job.status = JobStatus.QUEUED
                    deletion_job.available_at = now + timedelta(
                        seconds=self.settings.worker_poll_seconds
                    )
                    deletion_job.claimed_by = None
                    deletion_job.lease_expires_at = None
                    deletion_job.attempts = max(0, deletion_job.attempts - 1)
                    deletion_job.updated_at = now
                return True

    async def _remove_database_aggregate(self, claim: ClaimedDeletion) -> None:
        async with self.session_factory() as session:
            async with session.begin():
                document = await session.scalar(
                    select(Document).where(Document.id == claim.document_id).with_for_update()
                )
                if document is None:
                    return
                if document.status != DocumentStatus.DELETING:
                    raise SQLAlchemyError("Document left the deleting state.")
                await session.delete(document)

    async def _record_retryable_failure(self, claim: ClaimedDeletion) -> None:
        now = datetime.now(UTC)
        async with self.session_factory() as session:
            async with session.begin():
                job = await session.get(DocumentJob, claim.job_id, with_for_update=True)
                document = await session.get(
                    Document,
                    claim.document_id,
                    with_for_update=True,
                )
                if job is None or document is None:
                    return

                job.claimed_by = None
                job.lease_expires_at = None
                job.error_code = "DELETE_FILE_FAILED"
                job.error_message = "The stored PDF could not be deleted."
                job.updated_at = now

                document.error_code = "DELETE_RETRYING"
                document.error_message = "Document deletion will be retried."
                document.updated_at = now

                if claim.attempts >= claim.max_attempts:
                    job.status = JobStatus.FAILED
                    document.error_code = "DELETE_FAILED"
                    document.error_message = (
                        "Document deletion failed and requires another delete request."
                    )
                else:
                    delay = self.settings.deletion_retry_base_seconds * (
                        2 ** max(0, claim.attempts - 1)
                    )
                    job.status = JobStatus.QUEUED
                    job.available_at = now + timedelta(seconds=delay)
