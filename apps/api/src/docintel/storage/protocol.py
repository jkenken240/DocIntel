from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


class AsyncReadable(Protocol):
    async def read(self, size: int = -1) -> bytes: ...


@dataclass(frozen=True)
class StoredPdf:
    storage_key: str
    path: Path
    byte_size: int
    sha256: str


class StorageError(Exception):
    """Base exception for sanitized storage failures."""


class UploadTooLargeError(StorageError):
    pass


class InvalidPdfSignatureError(StorageError):
    pass


class DocumentStorage(Protocol):
    async def store_pdf(
        self,
        *,
        document_id: str,
        source: AsyncReadable,
        max_bytes: int,
        chunk_bytes: int,
    ) -> StoredPdf: ...

    def path_for(self, storage_key: str) -> Path: ...

    async def exists(self, storage_key: str) -> bool: ...

    async def delete(self, storage_key: str) -> None: ...
