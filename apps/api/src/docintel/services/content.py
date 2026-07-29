from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import quote


class RangeNotSatisfiable(ValueError):
    pass


@dataclass(frozen=True)
class ByteRange:
    start: int
    end: int

    @property
    def length(self) -> int:
        return self.end - self.start + 1


def parse_byte_range(value: str | None, total_size: int) -> ByteRange | None:
    if value is None:
        return None
    if total_size <= 0 or not value.startswith("bytes="):
        raise RangeNotSatisfiable

    specification = value.removeprefix("bytes=").strip()
    if "," in specification or "-" not in specification:
        raise RangeNotSatisfiable

    start_text, end_text = specification.split("-", maxsplit=1)
    try:
        if not start_text:
            suffix_length = int(end_text)
            if suffix_length <= 0:
                raise RangeNotSatisfiable
            start = max(total_size - suffix_length, 0)
            end = total_size - 1
        else:
            start = int(start_text)
            end = int(end_text) if end_text else total_size - 1
            if start < 0 or start >= total_size or end < start:
                raise RangeNotSatisfiable
            end = min(end, total_size - 1)
    except ValueError as exception:
        raise RangeNotSatisfiable from exception

    return ByteRange(start=start, end=end)


def iter_file_range(
    path: Path,
    *,
    start: int,
    length: int,
    chunk_size: int = 64 * 1024,
) -> Iterator[bytes]:
    with path.open("rb") as handle:
        handle.seek(start)
        remaining = length
        while remaining:
            chunk = handle.read(min(chunk_size, remaining))
            if not chunk:
                break
            remaining -= len(chunk)
            yield chunk


def inline_content_disposition(filename: str) -> str:
    return f"inline; filename*=UTF-8''{quote(filename, safe='')}"
