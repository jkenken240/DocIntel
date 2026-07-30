from __future__ import annotations

import hashlib
import json
import math
import re
import unicodedata
from dataclasses import dataclass
from typing import Protocol

from docintel.processing.errors import ProcessingError

TOKEN_PATTERN = re.compile(r"\w+|[^\w\s]", re.UNICODE)


@dataclass(frozen=True)
class EmbeddingSpaceIdentity:
    provider: str
    model: str
    dimensions: int
    distance_metric: str
    configuration_hash: str


class EmbeddingProvider(Protocol):
    @property
    def identity(self) -> EmbeddingSpaceIdentity: ...

    async def embed(self, texts: list[str]) -> list[list[float]]: ...


def mock_configuration_hash(*, model: str, dimensions: int) -> str:
    payload = {
        "algorithm": "signed-token-sha256-v1",
        "dimensions": dimensions,
        "distance_metric": "cosine",
        "model": model,
        "normalization": "NFKC-casefold",
        "provider": "mock",
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


class DeterministicMockEmbeddingProvider:
    def __init__(
        self,
        *,
        model: str = "mock-hash-v1",
        dimensions: int = 1536,
        fail_on_calls: set[int] | None = None,
    ) -> None:
        self._identity = EmbeddingSpaceIdentity(
            provider="mock",
            model=model,
            dimensions=dimensions,
            distance_metric="cosine",
            configuration_hash=mock_configuration_hash(
                model=model,
                dimensions=dimensions,
            ),
        )
        self.fail_on_calls = fail_on_calls or set()
        self.call_count = 0

    @property
    def identity(self) -> EmbeddingSpaceIdentity:
        return self._identity

    async def embed(self, texts: list[str]) -> list[list[float]]:
        self.call_count += 1
        if self.call_count in self.fail_on_calls:
            raise ProcessingError(
                "EMBEDDING_PROVIDER_TEMPORARY",
                "The local embedding provider temporarily failed.",
                retryable=True,
            )
        return [self._embed_one(text) for text in texts]

    def _embed_one(self, text: str) -> list[float]:
        normalized = unicodedata.normalize("NFKC", text).casefold()
        tokens = TOKEN_PATTERN.findall(normalized)
        if not tokens:
            tokens = [normalized or "<empty>"]

        vector = [0.0] * self.identity.dimensions
        for token in tokens:
            digest = hashlib.sha256(token.encode("utf-8")).digest()
            index = int.from_bytes(digest[:4], "big") % self.identity.dimensions
            sign = 1.0 if digest[4] & 1 else -1.0
            weight = 1.0 + (digest[5] / 255.0)
            vector[index] += sign * weight

        norm = math.sqrt(sum(value * value for value in vector))
        if norm == 0:
            raise ProcessingError(
                "EMBEDDING_ZERO_VECTOR",
                "The local embedding provider produced an invalid vector.",
                retryable=False,
            )
        return [value / norm for value in vector]


def validate_embedding_batch(
    *,
    texts: list[str],
    vectors: list[list[float]],
    expected_identity: EmbeddingSpaceIdentity,
    actual_identity: EmbeddingSpaceIdentity,
) -> None:
    if actual_identity != expected_identity:
        raise ProcessingError(
            "EMBEDDING_SPACE_MISMATCH",
            "The embedding provider configuration does not match the active space.",
            retryable=False,
        )
    if len(vectors) != len(texts):
        raise ProcessingError(
            "EMBEDDING_COUNT_MISMATCH",
            "The embedding provider returned an unexpected vector count.",
            retryable=True,
        )
    for vector in vectors:
        if len(vector) != expected_identity.dimensions:
            raise ProcessingError(
                "EMBEDDING_DIMENSION_MISMATCH",
                "The embedding provider returned an invalid vector dimension.",
                retryable=False,
            )
        if not all(math.isfinite(value) for value in vector):
            raise ProcessingError(
                "EMBEDDING_NON_FINITE",
                "The embedding provider returned a non-finite vector.",
                retryable=False,
            )
