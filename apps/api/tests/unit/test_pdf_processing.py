from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from docintel.processing.errors import ProcessingError
from docintel.processing.pdf import (
    extract_page,
    normalize_page_text,
    sanitize_pdf_metadata,
    validate_pdf,
)
from tests.pdf_factory import make_encrypted_pdf, make_text_pdf


def test_page_text_normalization_is_explicit_and_deterministic() -> None:
    source = "ＡＢＣ\r\nCafé\rLine\x00\f"

    assert normalize_page_text(source) == "ABC\nCafé\nLine"


def test_pdf_metadata_is_sanitized_and_bounded() -> None:
    metadata = {
        "title": " Fictional\x00  Policy ",
        "author": "A\r\nB",
        "unsafe": "not retained",
        "subject": "x" * 2000,
    }

    sanitized = sanitize_pdf_metadata(metadata)

    assert sanitized["title"] == "Fictional Policy"
    assert sanitized["author"] == "A B"
    assert len(sanitized["subject"]) == 1024
    assert "unsafe" not in sanitized


def test_validate_and_extract_preserve_blank_page_numbering(tmp_path: Path) -> None:
    path = tmp_path / "fictional.pdf"
    path.write_bytes(
        make_text_pdf(
            [
                "First fictional page.",
                "",
                "Third fictional page.",
            ],
            metadata={"title": "Fictional lifecycle test"},
        )
    )

    validated = validate_pdf(path, max_pages=500)
    pages = [extract_page(path, page_number=number) for number in range(1, 4)]

    assert validated.page_count == 3
    assert validated.metadata["title"] == "Fictional lifecycle test"
    assert [page.page_number for page in pages] == [1, 2, 3]
    assert pages[1].text == ""
    assert pages[0].text_sha256 == hashlib.sha256(pages[0].text.encode("utf-8")).hexdigest()
    assert pages[0].char_count == len(pages[0].text)


def test_generated_pdf_normalizes_unicode_and_line_endings(tmp_path: Path) -> None:
    path = tmp_path / "unicode-lines.pdf"
    path.write_bytes(make_text_pdf(["Fictional Café policy.\r\nSecond line."]))

    page = extract_page(path, page_number=1)

    assert page.text == "Fictional Café policy.\nSecond line."


def test_encrypted_pdf_is_permanently_rejected(tmp_path: Path) -> None:
    path = tmp_path / "encrypted.pdf"
    path.write_bytes(make_encrypted_pdf())

    with pytest.raises(ProcessingError) as raised:
        validate_pdf(path, max_pages=500)

    assert raised.value.code == "PDF_ENCRYPTED"
    assert raised.value.retryable is False


def test_corrupt_pdf_is_permanently_rejected(tmp_path: Path) -> None:
    path = tmp_path / "corrupt.pdf"
    path.write_bytes(b"%PDF-this is deliberately corrupt")

    with pytest.raises(ProcessingError) as raised:
        validate_pdf(path, max_pages=500)

    assert raised.value.code == "PDF_CORRUPT"
    assert raised.value.retryable is False


def test_page_limit_is_permanently_rejected(tmp_path: Path) -> None:
    path = tmp_path / "too-many-pages.pdf"
    path.write_bytes(make_text_pdf(["One", "Two", "Three"]))

    with pytest.raises(ProcessingError) as raised:
        validate_pdf(path, max_pages=2)

    assert raised.value.code == "PDF_PAGE_LIMIT_EXCEEDED"
    assert raised.value.retryable is False
