from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from docintel.core.config import Settings
from docintel.main import create_app
from docintel.schemas.health import ComponentCheck, ReadinessResponse


def _settings(tmp_path: Path) -> Settings:
    return Settings(
        _env_file=None,
        environment="test",
        uploads_path=tmp_path / "uploads",
        processed_path=tmp_path / "processed",
        samples_path=tmp_path / "samples",
        backups_path=tmp_path / "backups",
    )


def test_liveness_has_no_dependency_checks(tmp_path: Path) -> None:
    with TestClient(create_app(settings=_settings(tmp_path))) as client:
        response = client.get("/api/v1/health/live")

    assert response.status_code == 200
    assert response.json() == {
        "status": "alive",
        "service": "DocIntel API",
        "version": "1.0.0",
    }


def test_readiness_returns_503_when_a_component_is_not_ready(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    report = ReadinessResponse(
        status="not_ready",
        checks={
            "database": ComponentCheck(status="not_ready", detail="Unavailable."),
        },
    )
    check_mock = AsyncMock(return_value=report)
    monkeypatch.setattr("docintel.api.v1.health.run_readiness_checks", check_mock)

    with TestClient(create_app(settings=_settings(tmp_path))) as client:
        response = client.get("/api/v1/health/ready")

    assert response.status_code == 503
    assert response.json() == report.model_dump(mode="json")
    check_mock.assert_awaited_once()
