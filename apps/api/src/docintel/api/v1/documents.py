from __future__ import annotations

import uuid
from typing import Annotated, cast

from fastapi import APIRouter, Query, Request, Response, status
from starlette.datastructures import UploadFile
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.responses import StreamingResponse

from docintel.core.errors import ProblemException
from docintel.models import DocumentStatus
from docintel.schemas.documents import (
    DocumentDetail,
    DocumentEnvelope,
    DocumentListResponse,
    DocumentSort,
    DocumentStatusResponse,
    SortOrder,
)
from docintel.services.content import (
    RangeNotSatisfiable,
    inline_content_disposition,
    iter_file_range,
    parse_byte_range,
)
from docintel.services.documents import DocumentService

router = APIRouter(prefix="/documents", tags=["documents"])


def get_document_service(request: Request) -> DocumentService:
    return cast(DocumentService, request.app.state.document_service)


@router.post(
    "",
    response_model=DocumentEnvelope,
    status_code=status.HTTP_202_ACCEPTED,
)
async def upload_document(request: Request) -> DocumentEnvelope:
    if not request.headers.get("content-type", "").lower().startswith("multipart/form-data"):
        raise ProblemException(
            status_code=415,
            code="MULTIPART_REQUIRED",
            title="Multipart upload required",
            detail="Upload exactly one PDF using the multipart file field.",
        )

    try:
        form = await request.form(max_files=2, max_fields=1)
    except StarletteHTTPException as exception:
        raise ProblemException(
            status_code=400,
            code="INVALID_MULTIPART_UPLOAD",
            title="Invalid multipart upload",
            detail="The multipart request could not be parsed.",
        ) from exception

    try:
        items = form.multi_items()
        file_items = [
            value for key, value in items if key == "file" and isinstance(value, UploadFile)
        ]
        unexpected_items = [
            key for key, value in items if key != "file" or not isinstance(value, UploadFile)
        ]
        if len(file_items) != 1 or unexpected_items:
            raise ProblemException(
                status_code=400,
                code="ONE_PDF_REQUIRED",
                title="Exactly one PDF is required",
                detail="Provide one PDF in the multipart file field and no additional fields.",
            )

        upload = file_items[0]
        document = await get_document_service(request).upload_pdf(
            source=upload,
            filename=upload.filename,
            content_type=upload.content_type,
        )
    finally:
        await form.close()

    return DocumentEnvelope(document=DocumentDetail.from_document(document))


@router.get("", response_model=DocumentListResponse)
async def list_documents(
    request: Request,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    cursor: Annotated[str | None, Query(min_length=1, max_length=1000)] = None,
    search: Annotated[str | None, Query(max_length=200)] = None,
    document_status: Annotated[
        list[DocumentStatus] | None,
        Query(alias="status"),
    ] = None,
    sort: Annotated[DocumentSort, Query()] = "created_at",
    order: Annotated[SortOrder, Query()] = "desc",
) -> DocumentListResponse:
    return await get_document_service(request).list_documents(
        limit=limit,
        cursor_value=cursor,
        search=search,
        statuses=document_status,
        sort=sort,
        order=order,
    )


@router.get("/{document_id}", response_model=DocumentDetail)
async def get_document(document_id: uuid.UUID, request: Request) -> DocumentDetail:
    document = await get_document_service(request).get_document(document_id)
    return DocumentDetail.from_document(document)


@router.get("/{document_id}/status", response_model=DocumentStatusResponse)
async def get_document_status(
    document_id: uuid.UUID,
    request: Request,
) -> DocumentStatusResponse:
    document = await get_document_service(request).get_document(document_id)
    return DocumentStatusResponse.from_document(document)


@router.get("/{document_id}/content")
async def get_document_content(
    document_id: uuid.UUID,
    request: Request,
) -> Response:
    content = await get_document_service(request).get_content(document_id)
    document = content.document
    etag = f'"{document.sha256}"'
    common_headers = {
        "Accept-Ranges": "bytes",
        "ETag": etag,
        "Content-Disposition": inline_content_disposition(document.original_filename),
        "X-Content-Type-Options": "nosniff",
    }

    if request.headers.get("if-none-match") == etag:
        return Response(status_code=status.HTTP_304_NOT_MODIFIED, headers=common_headers)

    try:
        requested_range = parse_byte_range(
            request.headers.get("range"),
            document.byte_size,
        )
    except RangeNotSatisfiable as exception:
        raise ProblemException(
            status_code=416,
            code="RANGE_NOT_SATISFIABLE",
            title="Requested range is not satisfiable",
            detail="The requested byte range is invalid for this PDF.",
            headers={"Content-Range": f"bytes */{document.byte_size}", **common_headers},
        ) from exception

    if requested_range is None:
        start = 0
        length = document.byte_size
        response_status = status.HTTP_200_OK
        headers = {**common_headers, "Content-Length": str(length)}
    else:
        start = requested_range.start
        length = requested_range.length
        response_status = status.HTTP_206_PARTIAL_CONTENT
        headers = {
            **common_headers,
            "Content-Length": str(length),
            "Content-Range": (
                f"bytes {requested_range.start}-{requested_range.end}/{document.byte_size}"
            ),
        }

    return StreamingResponse(
        iter_file_range(content.path, start=start, length=length),
        status_code=response_status,
        media_type="application/pdf",
        headers=headers,
    )


@router.delete(
    "/{document_id}",
    response_model=DocumentEnvelope,
    status_code=status.HTTP_202_ACCEPTED,
)
async def delete_document(
    document_id: uuid.UUID,
    request: Request,
) -> DocumentEnvelope:
    document = await get_document_service(request).request_deletion(document_id)
    return DocumentEnvelope(document=DocumentDetail.from_document(document))
