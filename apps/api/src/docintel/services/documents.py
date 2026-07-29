from __future__ import annotations

import base64
import json
import logging
import re
import unicodedata
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

from sqlalchemy import ColumnElement, and_, asc, desc, func, or_, select, update
from sqlalchemy.exc import SQLAlchemyError

from docintel.core.config import Settings
from docintel.core.errors import ProblemException
from docintel.db.session import SessionFactory
from docintel.models import (
    Document,
    DocumentJob,
    DocumentStage,
    DocumentStatus,
    JobKind,
    JobStatus,
)
from docintel.schemas.documents import (
    DocumentCursor,
    DocumentListResponse,
    DocumentSort,
    DocumentSummary,
    SortOrder,
)
from docintel.storage.protocol import (
    AsyncReadable,
    DocumentStorage,
    InvalidPdfSignatureError,
    StorageError,
    UploadTooLargeError,
)

logger = logging.getLogger(__name__)
CONTROL_CHARACTER_PATTERN = re.compile(r"[\x00-\x1f\x7f]")


@dataclass(frozen=True)
class DocumentContent:
    document: Document
    path: Path


def sanitize_display_filename(filename: str | None) -> str:
    normalized = unicodedata.normalize("NFKC", filename or "")
    basename = normalized.replace("\\", "/").rsplit("/", maxsplit=1)[-1]
    basename = CONTROL_CHARACTER_PATTERN.sub("", basename)
    basename = " ".join(basename.split()).strip(" .")
    if not basename:
        return "document.pdf"

    suffix = Path(basename).suffix
    stem = basename[: -len(suffix)] if suffix else basename
    allowed_stem_length = max(1, 255 - len(suffix))
    return f"{stem[:allowed_stem_length]}{suffix}"


def validate_pdf_metadata(filename: str, content_type: str | None) -> None:
    if Path(filename).suffix.lower() != ".pdf":
        raise ProblemException(
            status_code=415,
            code="INVALID_PDF_EXTENSION",
            title="Unsupported file extension",
            detail="The uploaded file must use a .pdf extension.",
        )

    normalized_type = (content_type or "").split(";", maxsplit=1)[0].strip().lower()
    if normalized_type != "application/pdf":
        raise ProblemException(
            status_code=415,
            code="INVALID_PDF_MEDIA_TYPE",
            title="Unsupported media type",
            detail="The uploaded file must have the application/pdf media type.",
        )


def encode_cursor(document: Document, sort: DocumentSort, order: SortOrder) -> str:
    values: dict[DocumentSort, str | int] = {
        "created_at": document.created_at.isoformat(),
        "name": document.original_filename.casefold(),
        "size": document.byte_size,
    }
    payload = DocumentCursor(
        sort=sort,
        order=order,
        value=values[sort],
        id=document.id,
    ).model_dump(mode="json")
    encoded = base64.urlsafe_b64encode(json.dumps(payload, separators=(",", ":")).encode()).decode()
    return encoded.rstrip("=")


def decode_cursor(value: str, sort: DocumentSort, order: SortOrder) -> DocumentCursor:
    try:
        padded = value + "=" * (-len(value) % 4)
        payload = json.loads(base64.urlsafe_b64decode(padded.encode()).decode())
        cursor = DocumentCursor.model_validate(payload)
    except (ValueError, UnicodeDecodeError, json.JSONDecodeError) as exception:
        raise ProblemException(
            status_code=400,
            code="INVALID_CURSOR",
            title="Invalid pagination cursor",
            detail="The pagination cursor is invalid or malformed.",
        ) from exception

    if cursor.sort != sort or cursor.order != order:
        raise ProblemException(
            status_code=400,
            code="CURSOR_QUERY_MISMATCH",
            title="Pagination cursor does not match",
            detail="The pagination cursor does not match the requested sort.",
        )

    try:
        if sort == "created_at":
            datetime.fromisoformat(cast(str, cursor.value))
        elif sort == "size":
            size = int(cursor.value)
            if size <= 0:
                raise ValueError
        elif not isinstance(cursor.value, str):
            raise ValueError
    except (TypeError, ValueError) as exception:
        raise ProblemException(
            status_code=400,
            code="INVALID_CURSOR",
            title="Invalid pagination cursor",
            detail="The pagination cursor is invalid or malformed.",
        ) from exception
    return cursor


class DocumentService:
    def __init__(
        self,
        session_factory: SessionFactory,
        storage: DocumentStorage,
        settings: Settings,
    ) -> None:
        self.session_factory = session_factory
        self.storage = storage
        self.settings = settings

    async def upload_pdf(
        self,
        *,
        source: AsyncReadable,
        filename: str | None,
        content_type: str | None,
    ) -> Document:
        display_name = sanitize_display_filename(filename)
        validate_pdf_metadata(display_name, content_type)
        document_id = uuid.uuid4()

        try:
            stored = await self.storage.store_pdf(
                document_id=str(document_id),
                source=source,
                max_bytes=self.settings.upload_max_bytes,
                chunk_bytes=self.settings.upload_chunk_bytes,
            )
        except UploadTooLargeError as exception:
            raise ProblemException(
                status_code=413,
                code="PDF_TOO_LARGE",
                title="PDF is too large",
                detail=f"The PDF exceeds the {self.settings.upload_max_bytes}-byte upload limit.",
            ) from exception
        except InvalidPdfSignatureError as exception:
            raise ProblemException(
                status_code=422,
                code="INVALID_PDF_SIGNATURE",
                title="Invalid PDF",
                detail="The uploaded file does not have a valid PDF signature.",
            ) from exception
        except StorageError as exception:
            logger.warning("PDF storage failed.", exc_info=True)
            raise ProblemException(
                status_code=503,
                code="STORAGE_UNAVAILABLE",
                title="Document storage unavailable",
                detail="The PDF could not be stored.",
            ) from exception

        document = Document(
            id=document_id,
            original_filename=display_name,
            storage_key=stored.storage_key,
            media_type="application/pdf",
            byte_size=stored.byte_size,
            sha256=stored.sha256,
            status=DocumentStatus.QUEUED,
            stage=DocumentStage.QUEUED,
        )
        job = DocumentJob(
            document_id=document_id,
            kind=JobKind.PROCESSING,
            status=JobStatus.QUEUED,
            max_attempts=3,
        )

        try:
            async with self.session_factory() as session:
                async with session.begin():
                    session.add_all([document, job])
                    await session.flush()
        except SQLAlchemyError as exception:
            try:
                await self.storage.delete(stored.storage_key)
            except StorageError:
                logger.error(
                    "Failed to clean a stored PDF after database rollback.",
                    extra={"storage_key": stored.storage_key},
                    exc_info=True,
                )
            logger.warning("Document transaction failed.", exc_info=True)
            raise ProblemException(
                status_code=503,
                code="DATABASE_UNAVAILABLE",
                title="Database unavailable",
                detail="The document record could not be created.",
            ) from exception

        return document

    async def get_document(self, document_id: uuid.UUID) -> Document:
        async with self.session_factory() as session:
            document = await session.get(Document, document_id)
        if document is None:
            raise self._not_found()
        return document

    async def get_content(self, document_id: uuid.UUID) -> DocumentContent:
        document = await self.get_document(document_id)
        if document.status == DocumentStatus.DELETING:
            raise ProblemException(
                status_code=409,
                code="DOCUMENT_DELETING",
                title="Document is being deleted",
                detail="The PDF is unavailable while deletion is in progress.",
            )

        try:
            path = self.storage.path_for(document.storage_key)
        except StorageError as exception:
            logger.error("Stored document key is invalid.", exc_info=True)
            raise ProblemException(
                status_code=500,
                code="STORAGE_REFERENCE_INVALID",
                title="Stored document unavailable",
                detail="The stored PDF reference is invalid.",
            ) from exception

        if not await self.storage.exists(document.storage_key):
            raise ProblemException(
                status_code=404,
                code="DOCUMENT_CONTENT_NOT_FOUND",
                title="Document content not found",
                detail="The stored PDF is not available.",
            )
        return DocumentContent(document=document, path=path)

    async def list_documents(
        self,
        *,
        limit: int,
        cursor_value: str | None,
        search: str | None,
        statuses: list[DocumentStatus] | None,
        sort: DocumentSort,
        order: SortOrder,
    ) -> DocumentListResponse:
        sort_column: ColumnElement[Any]
        if sort == "name":
            sort_column = func.lower(Document.original_filename)
        elif sort == "size":
            sort_column = cast(ColumnElement[Any], Document.byte_size)
        else:
            sort_column = cast(ColumnElement[Any], Document.created_at)

        statement = select(Document)
        if search:
            escaped_search = (
                search.strip().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
            )
            if escaped_search:
                statement = statement.where(
                    Document.original_filename.ilike(f"%{escaped_search}%", escape="\\")
                )
        if statuses:
            statement = statement.where(Document.status.in_(statuses))

        if cursor_value:
            cursor = decode_cursor(cursor_value, sort, order)
            cursor_sort_value: Any
            if sort == "created_at":
                cursor_sort_value = datetime.fromisoformat(cast(str, cursor.value))
            elif sort == "size":
                cursor_sort_value = int(cursor.value)
            else:
                cursor_sort_value = str(cursor.value)

            comparison = (
                or_(
                    sort_column > cursor_sort_value,
                    and_(sort_column == cursor_sort_value, Document.id > cursor.id),
                )
                if order == "asc"
                else or_(
                    sort_column < cursor_sort_value,
                    and_(sort_column == cursor_sort_value, Document.id < cursor.id),
                )
            )
            statement = statement.where(comparison)

        direction = asc if order == "asc" else desc
        statement = statement.order_by(direction(sort_column), direction(Document.id)).limit(
            limit + 1
        )

        async with self.session_factory() as session:
            documents = list((await session.scalars(statement)).all())

        has_more = len(documents) > limit
        visible_documents = documents[:limit]
        next_cursor = (
            encode_cursor(visible_documents[-1], sort, order)
            if has_more and visible_documents
            else None
        )
        return DocumentListResponse(
            items=[DocumentSummary.from_document(document) for document in visible_documents],
            next_cursor=next_cursor,
        )

    async def request_deletion(self, document_id: uuid.UUID) -> Document:
        now = datetime.now(UTC)
        async with self.session_factory() as session:
            async with session.begin():
                document = await session.scalar(
                    select(Document).where(Document.id == document_id).with_for_update()
                )
                if document is None:
                    raise self._not_found()

                await session.execute(
                    update(DocumentJob)
                    .where(
                        DocumentJob.document_id == document_id,
                        DocumentJob.kind == JobKind.PROCESSING,
                        DocumentJob.status == JobStatus.QUEUED,
                    )
                    .values(
                        status=JobStatus.CANCELLED,
                        cancellation_requested=True,
                        completed_at=now,
                        updated_at=now,
                    )
                )
                await session.execute(
                    update(DocumentJob)
                    .where(
                        DocumentJob.document_id == document_id,
                        DocumentJob.kind == JobKind.PROCESSING,
                        DocumentJob.status == JobStatus.RUNNING,
                    )
                    .values(cancellation_requested=True, updated_at=now)
                )

                active_deletion_job = await session.scalar(
                    select(DocumentJob)
                    .where(
                        DocumentJob.document_id == document_id,
                        DocumentJob.kind == JobKind.DELETION,
                        DocumentJob.status.in_([JobStatus.QUEUED, JobStatus.RUNNING]),
                    )
                    .with_for_update()
                )

                document.status = DocumentStatus.DELETING
                document.stage = DocumentStage.DELETING
                document.deletion_started_at = document.deletion_started_at or now
                document.updated_at = now

                if active_deletion_job is None:
                    document.error_code = None
                    document.error_message = None
                    session.add(
                        DocumentJob(
                            document_id=document_id,
                            kind=JobKind.DELETION,
                            status=JobStatus.QUEUED,
                            max_attempts=self.settings.deletion_job_max_attempts,
                            available_at=now,
                        )
                    )
                await session.flush()
                return document

    @staticmethod
    def _not_found() -> ProblemException:
        return ProblemException(
            status_code=404,
            code="DOCUMENT_NOT_FOUND",
            title="Document not found",
            detail="The requested document does not exist.",
        )
