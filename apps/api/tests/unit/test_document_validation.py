import base64

import pytest

from docintel.core.errors import ProblemException
from docintel.services.documents import (
    decode_cursor,
    sanitize_display_filename,
    validate_pdf_metadata,
)


@pytest.mark.parametrize(
    ("supplied", "expected"),
    [
        ("../../Quarterly Report.pdf", "Quarterly Report.pdf"),
        (r"..\\..\\policy.pdf", "policy.pdf"),
        ("\x00\x1freport.pdf", "report.pdf"),
        ("   report   final.pdf  ", "report final.pdf"),
        (None, "document.pdf"),
    ],
)
def test_filename_is_sanitized_for_display_only(
    supplied: str | None,
    expected: str,
) -> None:
    assert sanitize_display_filename(supplied) == expected


def test_pdf_metadata_accepts_expected_hints() -> None:
    validate_pdf_metadata("Policy.PDF", "application/pdf")


@pytest.mark.parametrize(
    ("filename", "content_type", "code"),
    [
        ("policy.txt", "application/pdf", "INVALID_PDF_EXTENSION"),
        ("policy.pdf", "text/plain", "INVALID_PDF_MEDIA_TYPE"),
        ("policy.pdf", None, "INVALID_PDF_MEDIA_TYPE"),
    ],
)
def test_pdf_metadata_rejects_invalid_hints(
    filename: str,
    content_type: str | None,
    code: str,
) -> None:
    with pytest.raises(ProblemException) as raised:
        validate_pdf_metadata(filename, content_type)

    assert raised.value.code == code


def test_decode_cursor_rejects_invalid_sort_value() -> None:
    payload = (
        b'{"version":1,"sort":"created_at","order":"asc",'
        b'"value":"not-a-date","id":"00000000-0000-0000-0000-000000000001"}'
    )
    cursor = base64.urlsafe_b64encode(payload).decode().rstrip("=")

    with pytest.raises(ProblemException) as raised:
        decode_cursor(cursor, "created_at", "asc")

    assert raised.value.code == "INVALID_CURSOR"
