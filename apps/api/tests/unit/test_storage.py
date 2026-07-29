from __future__ import annotations

import hashlib
import uuid
from pathlib import Path

import pytest

from docintel.storage.local import LocalDocumentStorage
from docintel.storage.protocol import (
    InvalidPdfSignatureError,
    StorageError,
    UploadTooLargeError,
)


class AsyncBytes:
    def __init__(self, value: bytes) -> None:
        self.value = value
        self.offset = 0

    async def read(self, size: int = -1) -> bytes:
        if self.offset >= len(self.value):
            return b""
        end = len(self.value) if size < 0 else self.offset + size
        chunk = self.value[self.offset : end]
        self.offset += len(chunk)
        return chunk


class FailingStream:
    def __init__(self) -> None:
        self.reads = 0

    async def read(self, size: int = -1) -> bytes:
        del size
        self.reads += 1
        if self.reads == 1:
            return b"%PDF-"
        raise RuntimeError("Injected stream failure.")


def directory_entries(path: Path) -> list[Path]:
    return list(path.iterdir())


@pytest.mark.asyncio
async def test_store_pdf_streams_hashes_and_atomically_finalizes(tmp_path: Path) -> None:
    content = b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\n%%EOF\n"
    storage = LocalDocumentStorage(tmp_path)
    document_id = str(uuid.uuid4())

    stored = await storage.store_pdf(
        document_id=document_id,
        source=AsyncBytes(content),
        max_bytes=1024,
        chunk_bytes=7,
    )

    assert stored.storage_key == f"{document_id}.pdf"
    assert stored.path.read_bytes() == content
    assert stored.byte_size == len(content)
    assert stored.sha256 == hashlib.sha256(content).hexdigest()
    assert not any(path.suffix == ".part" for path in directory_entries(tmp_path))


@pytest.mark.asyncio
async def test_oversized_upload_removes_part_file(tmp_path: Path) -> None:
    storage = LocalDocumentStorage(tmp_path)

    with pytest.raises(UploadTooLargeError):
        await storage.store_pdf(
            document_id=str(uuid.uuid4()),
            source=AsyncBytes(b"%PDF-" + b"x" * 32),
            max_bytes=16,
            chunk_bytes=8,
        )

    assert directory_entries(tmp_path) == []


@pytest.mark.asyncio
async def test_invalid_signature_removes_part_file(tmp_path: Path) -> None:
    storage = LocalDocumentStorage(tmp_path)

    with pytest.raises(InvalidPdfSignatureError):
        await storage.store_pdf(
            document_id=str(uuid.uuid4()),
            source=AsyncBytes(b"not-a-pdf"),
            max_bytes=1024,
            chunk_bytes=5,
        )

    assert directory_entries(tmp_path) == []


@pytest.mark.asyncio
async def test_unexpected_stream_failure_removes_part_file(tmp_path: Path) -> None:
    storage = LocalDocumentStorage(tmp_path)

    with pytest.raises(RuntimeError, match="Injected stream failure"):
        await storage.store_pdf(
            document_id=str(uuid.uuid4()),
            source=FailingStream(),
            max_bytes=1024,
            chunk_bytes=5,
        )

    assert directory_entries(tmp_path) == []


def test_storage_key_cannot_escape_root(tmp_path: Path) -> None:
    storage = LocalDocumentStorage(tmp_path)

    with pytest.raises(StorageError):
        storage.path_for("../outside.pdf")
