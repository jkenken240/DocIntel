import os

import pytest

from docintel.core.config import get_settings
from docintel.db.session import create_engine
from docintel.services.readiness import run_readiness_checks


@pytest.mark.integration
@pytest.mark.skipif(
    os.getenv("DOCINTEL_RUN_INTEGRATION") != "1",
    reason="Set DOCINTEL_RUN_INTEGRATION=1 for database integration checks.",
)
async def test_migrated_platform_is_ready() -> None:
    settings = get_settings()
    engine = create_engine(settings.database_url)

    try:
        report = await run_readiness_checks(settings, engine)
    finally:
        await engine.dispose()

    assert report.status == "ready", report.model_dump()
    assert report.checks["pgvector"].status == "ready"
    assert report.checks["migration"].status == "ready"
