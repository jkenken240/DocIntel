from collections.abc import Mapping, Sequence
from typing import Any

from pydantic import BaseModel, Field


class FieldError(BaseModel):
    field: str
    message: str


class ProblemDetails(BaseModel):
    type: str
    title: str
    status: int
    detail: str
    code: str
    trace_id: str
    field_errors: list[FieldError] = Field(default_factory=list)

    model_config = {"extra": "allow"}


def field_errors_from_validation(
    errors: Sequence[Mapping[str, Any]],
) -> list[FieldError]:
    field_errors: list[FieldError] = []
    for error in errors:
        location = ".".join(str(part) for part in error.get("loc", ()) if part != "body")
        field_errors.append(
            FieldError(
                field=location or "request",
                message=str(error.get("msg", "Invalid value.")),
            )
        )
    return field_errors
