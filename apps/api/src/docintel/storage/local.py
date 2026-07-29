from __future__ import annotations

import hashlib
import os
import re
from pathlib import Path
from typing import BinaryIO

from anyio import CancelScope, to_thread

from docintel.storage.protocol import (
    AsyncReadable,
    DocumentStorage,
    InvalidPdfSignatureError,
    StorageError,
    StoredPdf,
    UploadTooLargeError,
)

STORAGE_KEY_PATTERN = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}\.pdf$"
)


class LocalDocumentStorage(DocumentStorage):
    """Protected local storage rooted at one configured directory."""

    def __init__(self, root: Path) -> None:
        self.root = root.resolve(strict=False)

    def path_for(self, storage_key: str) -> Path:
        if not STORAGE_KEY_PATTERN.fullmatch(storage_key):
            raise StorageError("Invalid storage key.")

        candidate = (self.root / storage_key).resolve(strict=False)
        if candidate.parent != self.root:
            raise StorageError("Storage key resolves outside the storage root.")
        return candidate

    async def store_pdf(
        self,
        *,
        document_id: str,
        source: AsyncReadable,
        max_bytes: int,
        chunk_bytes: int,
    ) -> StoredPdf:
        storage_key = f"{document_id}.pdf"
        final_path = self.path_for(storage_key)
        part_path = self.root / f".{document_id}.part"
        digest = hashlib.sha256()
        signature = bytearray()
        total = 0
        handle: BinaryIO | None = None
        finalized = False

        try:
            if not self.root.is_dir():
                raise StorageError("Configured storage root is unavailable.")
            if final_path.exists() or part_path.exists():
                raise StorageError("Generated storage path already exists.")

            handle = await to_thread.run_sync(lambda: part_path.open("xb"))
            while chunk := await source.read(chunk_bytes):
                total += len(chunk)
                if total > max_bytes:
                    raise UploadTooLargeError("PDF exceeds the configured upload limit.")

                if len(signature) < 5:
                    signature.extend(chunk[: 5 - len(signature)])
                    if len(signature) == 5 and bytes(signature) != b"%PDF-":
                        raise InvalidPdfSignatureError("File does not have a PDF signature.")

                digest.update(chunk)
                await to_thread.run_sync(handle.write, chunk)

            if bytes(signature) != b"%PDF-":
                raise InvalidPdfSignatureError("File does not have a PDF signature.")

            await to_thread.run_sync(handle.flush)
            await to_thread.run_sync(os.fsync, handle.fileno())
            await to_thread.run_sync(handle.close)
            handle = None
            await to_thread.run_sync(os.replace, part_path, final_path)
            finalized = True
        except OSError as exception:
            raise StorageError("Unable to persist the uploaded PDF.") from exception
        finally:
            if not finalized:
                cleanup_error: OSError | None = None
                with CancelScope(shield=True):
                    if handle is not None:
                        try:
                            await to_thread.run_sync(handle.close)
                        except OSError as exception:
                            cleanup_error = exception
                    try:
                        await to_thread.run_sync(lambda: part_path.unlink(missing_ok=True))
                    except OSError as exception:
                        cleanup_error = exception
                if cleanup_error is not None:
                    raise StorageError("Unable to clean an incomplete upload.") from cleanup_error

        return StoredPdf(
            storage_key=storage_key,
            path=final_path,
            byte_size=total,
            sha256=digest.hexdigest(),
        )

    async def exists(self, storage_key: str) -> bool:
        path = self.path_for(storage_key)
        return await to_thread.run_sync(path.is_file)

    async def delete(self, storage_key: str) -> None:
        path = self.path_for(storage_key)
        try:
            await to_thread.run_sync(lambda: path.unlink(missing_ok=True))
            if await to_thread.run_sync(path.exists):
                raise StorageError("Stored PDF is still present after deletion.")
        except OSError as exception:
            raise StorageError("Unable to delete the stored PDF.") from exception
