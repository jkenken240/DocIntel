from __future__ import annotations

from docintel.core.config import Settings
from docintel.intelligence.openai_compatible import (
    OpenAICompatibleAnswerProvider,
    OpenAICompatibleClaimVerifier,
)
from docintel.intelligence.providers import (
    ClaimSupportVerifier,
    DeterministicMockAnswerProvider,
    DeterministicMockClaimVerifier,
    GroundedAnswerProvider,
)
from docintel.processing.embeddings import (
    DeterministicMockEmbeddingProvider,
    EmbeddingProvider,
    OpenAICompatibleEmbeddingProvider,
)


def _required(value: str | None, name: str) -> str:
    if value is None or not value.strip():
        raise RuntimeError(f"{name} is required for the OpenAI-compatible provider.")
    return value


def create_embedding_provider(settings: Settings) -> EmbeddingProvider:
    if settings.ai_provider == "mock":
        return DeterministicMockEmbeddingProvider(
            model=settings.mock_embedding_model,
            dimensions=settings.embedding_dimensions,
        )
    return OpenAICompatibleEmbeddingProvider(
        base_url=_required(settings.ai_base_url, "ai_base_url"),
        api_key=_required(settings.ai_api_key, "ai_api_key"),
        model=_required(settings.ai_embedding_model, "ai_embedding_model"),
        dimensions=settings.embedding_dimensions,
        timeout_seconds=settings.ai_timeout_seconds,
        maximum_response_bytes=settings.ai_max_response_bytes,
    )


def create_answer_provider(settings: Settings) -> GroundedAnswerProvider:
    if settings.ai_provider == "mock":
        return DeterministicMockAnswerProvider(model=settings.mock_answer_model)
    return OpenAICompatibleAnswerProvider(
        base_url=_required(settings.ai_base_url, "ai_base_url"),
        api_key=_required(settings.ai_api_key, "ai_api_key"),
        model=_required(settings.ai_chat_model, "ai_chat_model"),
        timeout_seconds=settings.ai_timeout_seconds,
        maximum_response_bytes=settings.ai_max_response_bytes,
    )


def create_claim_verifier(settings: Settings) -> ClaimSupportVerifier:
    if settings.ai_provider == "mock":
        return DeterministicMockClaimVerifier(model=settings.mock_verifier_model)
    return OpenAICompatibleClaimVerifier(
        base_url=_required(settings.ai_base_url, "ai_base_url"),
        api_key=_required(settings.ai_api_key, "ai_api_key"),
        model=_required(settings.ai_chat_model, "ai_chat_model"),
        timeout_seconds=settings.ai_timeout_seconds,
        maximum_response_bytes=settings.ai_max_response_bytes,
    )
