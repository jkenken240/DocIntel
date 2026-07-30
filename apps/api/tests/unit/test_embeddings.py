from __future__ import annotations

import math

import httpx
import pytest

from docintel.processing.embeddings import (
    DeterministicMockEmbeddingProvider,
    EmbeddingSpaceIdentity,
    OpenAICompatibleEmbeddingProvider,
    validate_embedding_batch,
)
from docintel.processing.errors import ProcessingError


@pytest.mark.asyncio
async def test_mock_embeddings_are_deterministic_normalized_and_batch_stable() -> None:
    provider = DeterministicMockEmbeddingProvider()
    text = "Fictional policy text with Café."

    first = await provider.embed([text, "Second text"])
    second = await provider.embed([text])

    assert first[0] == second[0]
    assert len(first[0]) == 1536
    assert math.isclose(
        math.sqrt(sum(value * value for value in first[0])),
        1.0,
        rel_tol=1e-12,
    )
    assert provider.identity.provider == "mock"
    assert provider.identity.model == "mock-hash-v1"
    assert provider.identity.distance_metric == "cosine"
    assert len(provider.identity.configuration_hash) == 64


@pytest.mark.asyncio
async def test_mock_provider_supports_controlled_transient_failure() -> None:
    provider = DeterministicMockEmbeddingProvider(fail_on_calls={1})

    with pytest.raises(ProcessingError) as raised:
        await provider.embed(["fictional"])

    assert raised.value.code == "EMBEDDING_PROVIDER_TEMPORARY"
    assert raised.value.retryable is True
    assert len((await provider.embed(["fictional"]))[0]) == 1536


@pytest.mark.parametrize(
    ("vectors", "actual_identity", "expected_code"),
    [
        ([], None, "EMBEDDING_COUNT_MISMATCH"),
        ([[0.0] * 8], None, "EMBEDDING_DIMENSION_MISMATCH"),
        ([[float("nan")] + [0.0] * 1535], None, "EMBEDDING_NON_FINITE"),
    ],
)
def test_embedding_batch_validation_rejects_invalid_results(
    vectors: list[list[float]],
    actual_identity: EmbeddingSpaceIdentity | None,
    expected_code: str,
) -> None:
    provider = DeterministicMockEmbeddingProvider()

    with pytest.raises(ProcessingError) as raised:
        validate_embedding_batch(
            texts=["fictional"],
            vectors=vectors,
            expected_identity=provider.identity,
            actual_identity=actual_identity or provider.identity,
        )

    assert raised.value.code == expected_code


def test_embedding_batch_validation_rejects_space_mismatch() -> None:
    provider = DeterministicMockEmbeddingProvider()
    wrong_identity = EmbeddingSpaceIdentity(
        provider="mock",
        model="different",
        dimensions=1536,
        distance_metric="cosine",
        configuration_hash="0" * 64,
    )

    with pytest.raises(ProcessingError) as raised:
        validate_embedding_batch(
            texts=["fictional"],
            vectors=[[0.0] * 1536],
            expected_identity=provider.identity,
            actual_identity=wrong_identity,
        )

    assert raised.value.code == "EMBEDDING_SPACE_MISMATCH"


@pytest.mark.asyncio
async def test_openai_compatible_embeddings_use_mocked_http_only() -> None:
    vector = [0.0] * 1536
    vector[7] = 1.0

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/embeddings"
        assert request.headers["authorization"] == "Bearer test-only-key"
        return httpx.Response(
            200,
            json={"data": [{"index": 0, "embedding": vector}]},
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        provider = OpenAICompatibleEmbeddingProvider(
            base_url="https://provider.invalid/v1",
            api_key="test-only-key",
            model="fictional-embedding",
            dimensions=1536,
            timeout_seconds=1,
            maximum_response_bytes=64 * 1024,
            client=client,
        )
        result = await provider.embed(["fictional input"])

    assert result == [vector]
    assert provider.identity.provider == "openai_compatible"
    assert provider.identity.model == "fictional-embedding"
