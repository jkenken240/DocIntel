from __future__ import annotations

import base64
from collections.abc import Sequence
from typing import cast

import pymupdf

ONE_PIXEL_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
)


def make_text_pdf(
    pages: Sequence[str],
    *,
    metadata: dict[str, str] | None = None,
) -> bytes:
    document = pymupdf.open()
    try:
        if metadata:
            document.set_metadata(metadata)
        for text in pages:
            page = document.new_page(width=612, height=792)
            if text:
                result = page.insert_textbox(
                    pymupdf.Rect(72, 72, 540, 720),
                    text,
                    fontsize=11,
                )
                if result < 0:
                    raise ValueError("Fictional fixture text did not fit on its page.")
        return cast(bytes, document.tobytes(garbage=4, deflate=True))
    finally:
        document.close()


def make_encrypted_pdf() -> bytes:
    document = pymupdf.open()
    try:
        page = document.new_page()
        page.insert_text((72, 72), "Fictional encrypted policy.")
        return cast(
            bytes,
            document.tobytes(
                encryption=pymupdf.PDF_ENCRYPT_AES_256,  # type: ignore[attr-defined]
                owner_pw="fictional-owner",
                user_pw="fictional-user",
            ),
        )
    finally:
        document.close()


def make_scan_only_pdf() -> bytes:
    document = pymupdf.open()
    try:
        page = document.new_page()
        page.insert_image(
            pymupdf.Rect(72, 72, 300, 300),
            stream=ONE_PIXEL_PNG,
        )
        return cast(bytes, document.tobytes(garbage=4, deflate=True))
    finally:
        document.close()
