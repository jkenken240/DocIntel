from __future__ import annotations

import hashlib
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pymupdf

from docintel.processing.errors import ProcessingError

METADATA_KEYS = (
    "title",
    "author",
    "subject",
    "keywords",
    "creator",
    "producer",
    "creationDate",
    "modDate",
    "trapped",
)
METADATA_CONTROL_PATTERN = re.compile(r"[\x00-\x1f\x7f]")


@dataclass(frozen=True)
class ValidatedPdf:
    page_count: int
    metadata: dict[str, str]


@dataclass(frozen=True)
class ExtractedPage:
    page_number: int
    width: float
    height: float
    text: str
    text_sha256: str

    @property
    def char_count(self) -> int:
        return len(self.text)

    @property
    def has_text(self) -> bool:
        return bool(self.text.strip())


def normalize_page_text(value: str) -> str:
    normalized = value.replace("\r\n", "\n").replace("\r", "\n")
    normalized = unicodedata.normalize("NFKC", normalized)
    return normalized.replace("\x00", "").replace("\f", "")


def sanitize_pdf_metadata(metadata: dict[str, Any] | None) -> dict[str, str]:
    sanitized: dict[str, str] = {}
    source = metadata or {}
    for key in METADATA_KEYS:
        raw_value = source.get(key)
        if not isinstance(raw_value, str):
            continue
        value = unicodedata.normalize("NFKC", raw_value)
        value = METADATA_CONTROL_PATTERN.sub(" ", value)
        value = " ".join(value.split())[:1024]
        if value:
            sanitized[key] = value
    return sanitized


def validate_pdf(path: Path, *, max_pages: int) -> ValidatedPdf:
    if not path.is_file():
        raise ProcessingError(
            "STORED_PDF_MISSING",
            "The stored PDF is unavailable.",
            retryable=True,
        )

    try:
        with pymupdf.open(path) as document:
            if document.needs_pass or document.is_encrypted:
                raise ProcessingError(
                    "PDF_ENCRYPTED",
                    "Password-protected PDFs are not supported.",
                    retryable=False,
                )

            page_count = document.page_count
            if page_count <= 0:
                raise ProcessingError(
                    "PDF_EMPTY",
                    "The PDF does not contain any pages.",
                    retryable=False,
                )
            if page_count > max_pages:
                raise ProcessingError(
                    "PDF_PAGE_LIMIT_EXCEEDED",
                    f"The PDF exceeds the configured {max_pages}-page limit.",
                    retryable=False,
                )

            for page_index in range(page_count):
                document.load_page(page_index)

            return ValidatedPdf(
                page_count=page_count,
                metadata=sanitize_pdf_metadata(document.metadata),
            )
    except ProcessingError:
        raise
    except (RuntimeError, ValueError, OSError) as exception:
        raise ProcessingError(
            "PDF_CORRUPT",
            "The PDF is corrupt or malformed.",
            retryable=False,
        ) from exception


def extract_page(path: Path, *, page_number: int) -> ExtractedPage:
    try:
        with pymupdf.open(path) as document:
            if document.needs_pass or document.is_encrypted:
                raise ProcessingError(
                    "PDF_ENCRYPTED",
                    "Password-protected PDFs are not supported.",
                    retryable=False,
                )
            page = document.load_page(page_number - 1)
            text = normalize_page_text(page.get_text("text", sort=True))
            return ExtractedPage(
                page_number=page_number,
                width=float(page.rect.width),
                height=float(page.rect.height),
                text=text,
                text_sha256=hashlib.sha256(text.encode("utf-8")).hexdigest(),
            )
    except ProcessingError:
        raise
    except (RuntimeError, ValueError, OSError, IndexError) as exception:
        raise ProcessingError(
            "PDF_EXTRACTION_FAILED",
            "A PDF page could not be extracted.",
            retryable=False,
        ) from exception
