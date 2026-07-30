from __future__ import annotations

import hashlib
import json
import math
import unicodedata
import uuid
from dataclasses import asdict, dataclass


class RetrievalError(Exception):
    pass


@dataclass(frozen=True)
class RetrievalConfig:
    candidate_pool: int
    evidence_count: int
    minimum_similarity: float
    maximum_chunks_per_page: int
    maximum_chunks_per_document: int
    mmr_lambda: float
    duplicate_overlap_ratio: float

    def __post_init__(self) -> None:
        if self.candidate_pool < 1:
            raise ValueError("candidate_pool must be positive")
        if not 1 <= self.evidence_count <= self.candidate_pool:
            raise ValueError("evidence_count must be between one and candidate_pool")
        if not -1.0 <= self.minimum_similarity <= 1.0:
            raise ValueError("minimum_similarity must be between -1 and 1")
        if self.maximum_chunks_per_page < 1:
            raise ValueError("maximum_chunks_per_page must be positive")
        if self.maximum_chunks_per_document < 1:
            raise ValueError("maximum_chunks_per_document must be positive")
        if not 0.0 <= self.mmr_lambda <= 1.0:
            raise ValueError("mmr_lambda must be between zero and one")
        if not 0.0 <= self.duplicate_overlap_ratio <= 1.0:
            raise ValueError("duplicate_overlap_ratio must be between zero and one")

    def snapshot(self) -> dict[str, int | float]:
        return asdict(self)

    def configuration_hash(self) -> str:
        payload = json.dumps(self.snapshot(), sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class RetrievalCandidate:
    document_id: uuid.UUID
    display_filename: str
    processing_revision: int
    page_id: uuid.UUID
    page_number: int
    page_text_sha256: str
    chunk_id: uuid.UUID
    chunk_ordinal: int
    char_start: int
    char_end: int
    text: str
    text_sha256: str
    score: float
    vector: tuple[float, ...]


def normalize_question(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value)
    normalized = " ".join(normalized.split())
    return normalized.strip()


def _cosine(left: tuple[float, ...], right: tuple[float, ...]) -> float:
    if len(left) != len(right) or not left:
        raise RetrievalError("Candidate vectors use incompatible dimensions.")
    if not all(math.isfinite(value) for value in (*left, *right)):
        raise RetrievalError("Candidate vectors contain non-finite values.")
    left_norm = math.sqrt(sum(value * value for value in left))
    right_norm = math.sqrt(sum(value * value for value in right))
    if left_norm == 0.0 or right_norm == 0.0:
        raise RetrievalError("Candidate vectors must be non-zero.")
    return sum(a * b for a, b in zip(left, right, strict=True)) / (left_norm * right_norm)


def _overlap_ratio(left: RetrievalCandidate, right: RetrievalCandidate) -> float:
    if left.page_id != right.page_id:
        return 0.0
    overlap = max(0, min(left.char_end, right.char_end) - max(left.char_start, right.char_start))
    if overlap == 0:
        return 0.0
    shortest = min(left.char_end - left.char_start, right.char_end - right.char_start)
    return overlap / shortest


def _stable_key(candidate: RetrievalCandidate) -> tuple[str, int, int, str]:
    return (
        str(candidate.document_id),
        candidate.page_number,
        candidate.chunk_ordinal,
        str(candidate.chunk_id),
    )


def select_diverse_evidence(
    candidates: list[RetrievalCandidate],
    config: RetrievalConfig,
) -> list[RetrievalCandidate]:
    unique: dict[uuid.UUID, RetrievalCandidate] = {}
    for candidate in candidates:
        if not math.isfinite(candidate.score):
            raise RetrievalError("Retrieval produced a non-finite score.")
        if candidate.score < config.minimum_similarity:
            continue
        existing = unique.get(candidate.chunk_id)
        if existing is None or (-candidate.score, _stable_key(candidate)) < (
            -existing.score,
            _stable_key(existing),
        ):
            unique[candidate.chunk_id] = candidate

    remaining = sorted(unique.values(), key=lambda item: (-item.score, _stable_key(item)))
    selected: list[RetrievalCandidate] = []
    page_counts: dict[uuid.UUID, int] = {}
    document_counts: dict[uuid.UUID, int] = {}

    while remaining and len(selected) < config.evidence_count:
        eligible = [
            candidate
            for candidate in remaining
            if page_counts.get(candidate.page_id, 0) < config.maximum_chunks_per_page
            and document_counts.get(candidate.document_id, 0) < config.maximum_chunks_per_document
            and not any(
                _overlap_ratio(candidate, chosen) >= config.duplicate_overlap_ratio
                for chosen in selected
            )
        ]
        if not eligible:
            break

        def mmr_key(
            candidate: RetrievalCandidate,
        ) -> tuple[float, float, tuple[str, int, int, str]]:
            diversity = (
                max(_cosine(candidate.vector, chosen.vector) for chosen in selected)
                if selected
                else 0.0
            )
            mmr_score = config.mmr_lambda * candidate.score - (1.0 - config.mmr_lambda) * diversity
            return (-mmr_score, -candidate.score, _stable_key(candidate))

        chosen = min(eligible, key=mmr_key)
        selected.append(chosen)
        remaining.remove(chosen)
        page_counts[chosen.page_id] = page_counts.get(chosen.page_id, 0) + 1
        document_counts[chosen.document_id] = document_counts.get(chosen.document_id, 0) + 1

    return selected
