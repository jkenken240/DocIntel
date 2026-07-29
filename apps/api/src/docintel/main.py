from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.ext.asyncio import AsyncEngine

from docintel.api.v1.documents import router as documents_router
from docintel.api.v1.health import router as health_router
from docintel.core.config import Settings, get_settings
from docintel.core.errors import register_error_handling
from docintel.core.logging import configure_logging
from docintel.db.session import create_engine, create_session_factory
from docintel.services.documents import DocumentService
from docintel.storage.local import LocalDocumentStorage
from docintel.storage.protocol import DocumentStorage


def create_app(
    settings: Settings | None = None,
    engine: AsyncEngine | None = None,
    storage: DocumentStorage | None = None,
) -> FastAPI:
    resolved_settings = settings or get_settings()
    configure_logging(resolved_settings.log_level)
    resolved_engine = engine or create_engine(resolved_settings.database_url)
    session_factory = create_session_factory(resolved_engine)
    resolved_storage = storage or LocalDocumentStorage(resolved_settings.uploads_path)

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        yield
        await resolved_engine.dispose()

    application = FastAPI(
        title=resolved_settings.app_name,
        version=resolved_settings.app_version,
        lifespan=lifespan,
    )
    application.state.settings = resolved_settings
    application.state.engine = resolved_engine
    application.state.session_factory = session_factory
    application.state.storage = resolved_storage
    application.state.document_service = DocumentService(
        session_factory,
        resolved_storage,
        resolved_settings,
    )
    register_error_handling(application)
    application.add_middleware(
        CORSMiddleware,
        allow_origins=resolved_settings.cors_origins,
        allow_credentials=False,
        allow_methods=["GET", "POST", "DELETE"],
        allow_headers=["Accept", "Content-Type", "Range", "If-None-Match", "X-Request-ID"],
        expose_headers=["ETag", "Content-Range", "Accept-Ranges", "X-Trace-ID"],
    )
    application.include_router(health_router, prefix=resolved_settings.api_v1_prefix)
    application.include_router(documents_router, prefix=resolved_settings.api_v1_prefix)
    return application


app = create_app()
