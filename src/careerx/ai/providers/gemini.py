"""Google Gemini implementation of :class:`LLMProvider`."""

from __future__ import annotations

import logging
from collections.abc import Sequence
from typing import TypeVar

from pydantic import BaseModel

from careerx.ai.providers.base import (
    EmbeddingTask,
    LLMProvider,
    ProviderError,
    ProviderNotConfigured,
    retry_with_backoff,
)
from careerx.config.settings import Settings

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)

_TASK_TYPES = {
    EmbeddingTask.DOCUMENT: "RETRIEVAL_DOCUMENT",
    EmbeddingTask.QUERY: "RETRIEVAL_QUERY",
}

# The only 4xx codes a later identical attempt can succeed on.
_RETRYABLE_CLIENT_CODES = frozenset({408, 429})


def _is_retryable(exc: Exception) -> bool:
    """Decide whether a Gemini failure is transient.

    A 4xx means the key or the request is wrong, not that the service is
    briefly unavailable, so retrying only delays the inevitable error.
    """
    from google.genai import errors

    if isinstance(exc, errors.ClientError):
        return getattr(exc, "code", None) in _RETRYABLE_CLIENT_CODES

    return True


class GeminiProvider(LLMProvider):
    """Structured generation and embeddings backed by the Gemini API."""

    name = "gemini"

    def __init__(self, settings: Settings) -> None:
        if not settings.google_api_key:
            raise ProviderNotConfigured("GOOGLE_API_KEY is not set; cannot use the Gemini provider.")

        from google import genai  # imported lazily so the SDK is optional at import time

        self._settings = settings
        self._client = genai.Client(api_key=settings.google_api_key)

    @property
    def chat_model(self) -> str:
        return self._settings.gemini_model

    @property
    def embedding_model(self) -> str:
        return self._settings.gemini_embedding_model

    def generate_structured(
        self,
        *,
        system_instruction: str,
        user_prompt: str,
        response_model: type[T],
    ) -> T:
        from google.genai import types

        config = types.GenerateContentConfig(
            system_instruction=system_instruction,
            temperature=self._settings.temperature,
            response_mime_type="application/json",
            response_schema=response_model,
        )

        def _call() -> T:
            response = self._client.models.generate_content(
                model=self.chat_model,
                contents=user_prompt,
                config=config,
            )

            parsed = response.parsed
            if parsed is None:
                # The SDK returns None when the model emitted unparsable JSON
                # or stopped early (e.g. a safety block or token limit).
                raise ProviderError(f"Gemini returned no parsable JSON for {response_model.__name__}.")

            if isinstance(parsed, response_model):
                return parsed

            return response_model.model_validate(parsed)

        return retry_with_backoff(
            _call,
            attempts=self._settings.max_retries,
            description=f"gemini.generate_structured[{response_model.__name__}]",
            retryable=_is_retryable,
        )

    def embed(
        self,
        texts: Sequence[str],
        *,
        task: EmbeddingTask = EmbeddingTask.DOCUMENT,
    ) -> list[list[float]]:
        if not texts:
            return []

        from google.genai import types

        config = types.EmbedContentConfig(task_type=_TASK_TYPES[task])
        batch_size = self._settings.embedding_batch_size
        vectors: list[list[float]] = []

        for start in range(0, len(texts), batch_size):
            batch = list(texts[start : start + batch_size])

            def _call(batch: list[str] = batch) -> list[list[float]]:
                response = self._client.models.embed_content(
                    model=self.embedding_model,
                    contents=batch,
                    config=config,
                )
                embeddings = response.embeddings or []
                if len(embeddings) != len(batch):
                    raise ProviderError(f"Gemini returned {len(embeddings)} embeddings for {len(batch)} inputs.")
                return [list(item.values or []) for item in embeddings]

            vectors.extend(
                retry_with_backoff(
                    _call,
                    attempts=self._settings.max_retries,
                    description="gemini.embed",
                    retryable=_is_retryable,
                )
            )

        return vectors
