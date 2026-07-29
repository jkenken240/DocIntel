from typing import Literal

from pydantic import BaseModel


class LivenessResponse(BaseModel):
    status: Literal["alive"] = "alive"
    service: str
    version: str


class ComponentCheck(BaseModel):
    status: Literal["ready", "not_ready"]
    detail: str


class ReadinessResponse(BaseModel):
    status: Literal["ready", "not_ready"]
    checks: dict[str, ComponentCheck]
