from pathlib import Path

from docintel.core.config import Settings


def test_mock_provider_is_the_foundation_default() -> None:
    settings = Settings(_env_file=None)

    assert settings.ai_provider == "mock"
    assert settings.embedding_dimensions == 1536
    assert settings.mock_embedding_model == "mock-hash-v1"
    assert settings.pdf_max_pages == 500
    assert (
        settings.chunk_target_chars,
        settings.chunk_max_chars,
        settings.chunk_overlap_chars,
    ) == (1400, 1800, 200)


def test_storage_paths_are_fully_configurable(tmp_path: Path) -> None:
    settings = Settings(
        _env_file=None,
        uploads_path=tmp_path / "uploads",
        processed_path=tmp_path / "processed",
        samples_path=tmp_path / "samples",
        backups_path=tmp_path / "backups",
    )

    assert settings.storage_paths["uploads"] == (tmp_path / "uploads", True)
    assert settings.storage_paths["samples"] == (tmp_path / "samples", False)
