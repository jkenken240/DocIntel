from __future__ import annotations

import logging
import re
import uuid
from collections.abc import Awaitable, Callable, Mapping, Sequence
from typing import Any, cast

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.responses import Response

from docintel.schemas.problems import (
    FieldError,
    ProblemDetails,
    field_errors_from_validation,
)

logger = logging.getLogger(__name__)
TRACE_ID_PATTERN = re.compile(r"^[A-Za-z0-9._-]{1,100}$")
PROBLEM_BASE = "https://docintel.dev/problems"


class ProblemException(Exception):
    def __init__(
        self,
        *,
        status_code: int,
        code: str,
        title: str,
        detail: str,
        problem_type: str | None = None,
        field_errors: list[FieldError] | None = None,
        headers: dict[str, str] | None = None,
    ) -> None:
        super().__init__(detail)
        self.status_code = status_code
        self.code = code
        self.title = title
        self.detail = detail
        self.problem_type = problem_type or f"{PROBLEM_BASE}/{code.lower().replace('_', '-')}"
        self.field_errors = field_errors or []
        self.headers = headers or {}


def get_trace_id(request: Request) -> str:
    trace_id = getattr(request.state, "trace_id", None)
    return str(trace_id or uuid.uuid4().hex)


def problem_response(
    request: Request,
    *,
    status_code: int,
    code: str,
    title: str,
    detail: str,
    problem_type: str | None = None,
    field_errors: list[FieldError] | None = None,
    headers: Mapping[str, str] | None = None,
) -> JSONResponse:
    trace_id = get_trace_id(request)
    payload = ProblemDetails(
        type=problem_type or f"{PROBLEM_BASE}/{code.lower().replace('_', '-')}",
        title=title,
        status=status_code,
        detail=detail,
        code=code,
        trace_id=trace_id,
        field_errors=field_errors or [],
    )
    response_headers = {"X-Trace-ID": trace_id, **(headers or {})}
    return JSONResponse(
        status_code=status_code,
        content=payload.model_dump(mode="json"),
        media_type="application/problem+json",
        headers=response_headers,
    )


def register_error_handling(application: FastAPI) -> None:
    @application.middleware("http")
    async def trace_middleware(
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        supplied_trace = request.headers.get("X-Request-ID", "")
        request.state.trace_id = (
            supplied_trace if TRACE_ID_PATTERN.fullmatch(supplied_trace) else uuid.uuid4().hex
        )
        response = await call_next(request)
        response.headers.setdefault("X-Trace-ID", request.state.trace_id)
        return response

    @application.exception_handler(ProblemException)
    async def problem_exception_handler(
        request: Request,
        exception: ProblemException,
    ) -> JSONResponse:
        return problem_response(
            request,
            status_code=exception.status_code,
            code=exception.code,
            title=exception.title,
            detail=exception.detail,
            problem_type=exception.problem_type,
            field_errors=exception.field_errors,
            headers=exception.headers,
        )

    @application.exception_handler(RequestValidationError)
    async def validation_exception_handler(
        request: Request,
        exception: RequestValidationError,
    ) -> JSONResponse:
        return problem_response(
            request,
            status_code=422,
            code="REQUEST_VALIDATION_FAILED",
            title="Request validation failed",
            detail="One or more request values are invalid.",
            field_errors=field_errors_from_validation(
                cast(Sequence[Mapping[str, Any]], exception.errors())
            ),
        )

    @application.exception_handler(StarletteHTTPException)
    async def http_exception_handler(
        request: Request,
        exception: StarletteHTTPException,
    ) -> JSONResponse:
        return problem_response(
            request,
            status_code=exception.status_code,
            code="HTTP_ERROR",
            title="HTTP request failed",
            detail="The requested operation could not be completed.",
            headers=exception.headers,
        )

    @application.exception_handler(Exception)
    async def unhandled_exception_handler(
        request: Request,
        exception: Exception,
    ) -> JSONResponse:
        logger.exception(
            "Unhandled request error.",
            extra={"trace_id": get_trace_id(request)},
            exc_info=exception,
        )
        return problem_response(
            request,
            status_code=500,
            code="INTERNAL_ERROR",
            title="Internal server error",
            detail="The server could not complete the request.",
        )
