from pathlib import Path

from docintel.core.config import Settings
from docintel.services.readiness import check_provider_configuration, check_storage


def _storage_settings(tmp_path: Path) -> Settings:
    paths = {name: tmp_path / name for name in ("uploads", "processed", "samples", "backups")}
    for path in paths.values():
        path.mkdir()
    return Settings(
        _env_file=None,
        uploads_path=paths["uploads"],
        processed_path=paths["processed"],
        samples_path=paths["samples"],
        backups_path=paths["backups"],
    )


def test_storage_is_ready_when_all_configured_directories_exist(tmp_path: Path) -> None:
    result = check_storage(_storage_settings(tmp_path))

    assert result.status == "ready"


def test_storage_reports_missing_directory(tmp_path: Path) -> None:
    settings = _storage_settings(tmp_path)
    settings.backups_path.rmdir()

    result = check_storage(settings)

    assert result.status == "not_ready"
    assert "backups" in result.detail


def test_mock_provider_check_is_configuration_only(tmp_path: Path) -> None:
    result = check_provider_configuration(_storage_settings(tmp_path))

    assert result.status == "ready"
    assert "no request made" in result.detail


def test_openai_compatible_provider_requires_configuration(tmp_path: Path) -> None:
    settings = _storage_settings(tmp_path).model_copy(update={"ai_provider": "openai_compatible"})

    result = check_provider_configuration(settings)

    assert result.status == "not_ready"
    assert "API key" in result.detail
