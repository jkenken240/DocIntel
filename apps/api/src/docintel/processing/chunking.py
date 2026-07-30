from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass

PARAGRAPH_BOUNDARY = re.compile(r"\n[ \t]*\n+")
SENTENCE_BOUNDARY = re.compile(r"""[.!?](?:["')\]]*)[ \t\n]+""")
WHITESPACE_BOUNDARY = re.compile(r"\s+")


@dataclass(frozen=True)
class ChunkingConfig:
    target_chars: int
    max_chars: int
    overlap_chars: int
    version: str

    def __post_init__(self) -> None:
        if self.target_chars <= 0:
            raise ValueError("target_chars must be positive")
        if self.max_chars < self.target_chars:
            raise ValueError("max_chars must be at least target_chars")
        if self.overlap_chars < 0 or self.overlap_chars >= self.target_chars:
            raise ValueError("overlap_chars must be non-negative and below target_chars")
        if not self.version:
            raise ValueError("version is required")


@dataclass(frozen=True)
class ChunkSlice:
    ordinal: int
    char_start: int
    char_end: int
    text: str
    text_sha256: str
    chunker_version: str


def _preferred_boundary(
    text: str,
    *,
    start: int,
    target_end: int,
    hard_end: int,
) -> int:
    minimum_end = min(start + max(1, (target_end - start) // 2), target_end)
    window = text[start:hard_end]
    target_relative = target_end - start
    minimum_relative = minimum_end - start

    for pattern in (PARAGRAPH_BOUNDARY, SENTENCE_BOUNDARY, WHITESPACE_BOUNDARY):
        candidates = [
            match.end()
            for match in pattern.finditer(window)
            if minimum_relative <= match.end() <= hard_end - start
        ]
        if candidates:
            relative_end = min(
                candidates,
                key=lambda candidate: (abs(candidate - target_relative), candidate),
            )
            return start + relative_end
    return hard_end


def chunk_page(text: str, config: ChunkingConfig) -> list[ChunkSlice]:
    if not text or not text.strip():
        return []

    chunks: list[ChunkSlice] = []
    start = 0
    while start < len(text):
        target_end = min(start + config.target_chars, len(text))
        hard_end = min(start + config.max_chars, len(text))
        end = (
            len(text)
            if hard_end == len(text)
            else _preferred_boundary(
                text,
                start=start,
                target_end=target_end,
                hard_end=hard_end,
            )
        )
        if end <= start:
            end = hard_end

        chunk_text = text[start:end]
        chunks.append(
            ChunkSlice(
                ordinal=len(chunks),
                char_start=start,
                char_end=end,
                text=chunk_text,
                text_sha256=hashlib.sha256(chunk_text.encode("utf-8")).hexdigest(),
                chunker_version=config.version,
            )
        )
        if end == len(text):
            break
        start = max(start + 1, end - config.overlap_chars)

    return chunks
