from __future__ import annotations

import logging
import os
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncEngine

from docintel.core.config import Settings
from docintel.schemas.health import ComponentCheck, ReadinessResponse

MIGRATION_HEAD = "20260730_0003"
logger = logging.getLogger(__name__)


def _ready(detail: str) -> ComponentCheck:
    return ComponentCheck(status="ready", detail=detail)


def _not_ready(detail: str) -> ComponentCheck:
    return ComponentCheck(status="not_ready", detail=detail)


async def check_database(engine: AsyncEngine) -> dict[str, ComponentCheck]:
    checks: dict[str, ComponentCheck] = {}

    try:
        async with engine.connect() as connection:
            await connection.execute(text("SELECT 1"))
            checks["database"] = _ready("PostgreSQL query succeeded.")

            vector_installed = bool(
                (
                    await connection.execute(
                        text("SELECT EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'vector')")
                    )
                ).scalar_one()
            )
            checks["pgvector"] = (
                _ready("pgvector extension is installed.")
                if vector_installed
                else _not_ready("pgvector extension is not installed.")
            )

            migration_revision = (
                await connection.execute(text("SELECT version_num FROM alembic_version"))
            ).scalar_one_or_none()
            checks["migration"] = (
                _ready(f"Database is at Alembic revision {MIGRATION_HEAD}.")
                if migration_revision == MIGRATION_HEAD
                else _not_ready("Database revision does not match the application migration head.")
            )
    except SQLAlchemyError:
        logger.warning("Database readiness check failed.", exc_info=True)
        checks.setdefault("database", _not_ready("PostgreSQL is unavailable."))
        checks.setdefault("pgvector", _not_ready("Blocked by database availability."))
        checks.setdefault("migration", _not_ready("Blocked by database availability."))

    return checks


def _has_required_access(path: Path, writable: bool) -> bool:
    if not path.is_dir():
        return False
    required_mode = os.R_OK | (os.W_OK if writable else 0)
    return os.access(path, required_mode)


def check_storage(settings: Settings) -> ComponentCheck:
    failures: list[str] = []

    for name, (path, writable) in settings.storage_paths.items():
        if not _has_required_access(path, writable):
            access = "read/write" if writable else "read"
            failures.append(f"{name} ({path}, requires {access})")

    if failures:
        return _not_ready("Unavailable storage paths: " + "; ".join(failures))

    return _ready("All configured storage paths have the required access.")


def check_provider_configuration(settings: Settings) -> ComponentCheck:
    if settings.ai_provider == "mock":
        if settings.embedding_dimensions != 1536:
            return _not_ready("The deterministic mock provider requires 1536 embedding dimensions.")
        return _ready("Deterministic mock provider configuration is valid; no request made.")

    required_values = {
        "base URL": settings.ai_base_url,
        "API key": settings.ai_api_key,
        "chat model": settings.ai_chat_model,
        "embedding model": settings.ai_embedding_model,
    }
    missing = [name for name, value in required_values.items() if not value]
    if missing:
        return _not_ready(
            "OpenAI-compatible provider configuration is missing: " + ", ".join(missing)
        )
    if not settings.ai_structured_output:
        return _not_ready("The configured provider must support structured output.")

    return _ready("OpenAI-compatible provider configuration is valid; no request made.")


async def run_readiness_checks(
    settings: Settings,
    engine: AsyncEngine,
) -> ReadinessResponse:
    checks = await check_database(engine)
    checks["storage"] = check_storage(settings)
    checks["provider"] = check_provider_configuration(settings)

    overall_status = (
        "ready" if all(check.status == "ready" for check in checks.values()) else "not_ready"
    )
    return ReadinessResponse(status=overall_status, checks=checks)
