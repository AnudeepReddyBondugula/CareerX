"""OpenAI implementation of :class:`LLMProvider`."""

from __future__ import annotations

import json
import logging
from collections.abc import Sequence
from typing import TypeVar

from pydantic import BaseModel, ValidationError

from careerx.ai.providers.base import (
    EmbeddingTask,
    LLMProvider,
    ProviderError,
    ProviderNotConfigured,
    retry_with_backoff,
)
from careerx.ai.providers.schema import to_strict_json_schema
from careerx.config.settings import Settings

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)

_RETRYABLE_STATUS_CODES = frozenset({408, 409, 429})


def _is_retryable(exc: Exception) -> bool:
    """Retry rate limits, timeouts and server errors; nothing else."""
    from openai import APIStatusError

    if isinstance(exc, APIStatusError):
        return exc.status_code in _RETRYABLE_STATUS_CODES or exc.status_code >= 500

    return True


class OpenAIProvider(LLMProvider):
    """Structured generation and embeddings backed by the OpenAI API.

    Uses the ``json_schema`` response format so the model is constrained by the
    Pydantic schema itself rather than by prompt instructions alone. Falls back
    to plain JSON mode for models or gateways that do not support strict
    schemas.
    """

    name = "openai"

    def __init__(self, settings: Settings) -> None:
        if not settings.openai_api_key:
            raise ProviderNotConfigured("OPENAI_API_KEY is not set; cannot use the OpenAI provider.")

        from openai import OpenAI

        self._settings = settings
        self._client = OpenAI(
            api_key=settings.openai_api_key,
            base_url=settings.openai_base_url,
            timeout=settings.request_timeout_seconds,
            max_retries=0,  # retries are handled by retry_with_backoff
        )
        self._supports_strict_schema = True

    @property
    def chat_model(self) -> str:
        return self._settings.openai_model

    @property
    def embedding_model(self) -> str:
        return self._settings.openai_embedding_model

    def generate_structured(
        self,
        *,
        system_instruction: str,
        user_prompt: str,
        response_model: type[T],
    ) -> T:
        messages = [
            {"role": "system", "content": system_instruction},
            {"role": "user", "content": user_prompt},
        ]

        def _call() -> T:
            response = self._client.chat.completions.create(
                model=self.chat_model,
                messages=messages,
                temperature=self._settings.temperature,
                response_format=self._response_format(response_model),
            )

            choice = response.choices[0]
            if choice.finish_reason == "length":
                raise ProviderError("OpenAI response was truncated before valid JSON was produced.")

            content = choice.message.content
            if not content:
                raise ProviderError(f"OpenAI returned an empty response for {response_model.__name__}.")

            try:
                return response_model.model_validate_json(content)
            except ValidationError as exc:
                raise ProviderError(f"OpenAI response did not match {response_model.__name__}: {exc}") from exc

        try:
            return retry_with_backoff(
                _call,
                attempts=self._settings.max_retries,
                description=f"openai.generate_structured[{response_model.__name__}]",
                retryable=_is_retryable,
            )
        except ProviderError:
            if not self._supports_strict_schema:
                raise

            logger.warning("Strict JSON schema rejected by the endpoint; retrying in plain JSON mode.")
            self._supports_strict_schema = False

            messages[0]["content"] = (
                f"{system_instruction}\n\n"
                "Respond with a single JSON object matching this JSON Schema exactly:\n"
                f"{json.dumps(to_strict_json_schema(response_model))}"
            )

            return retry_with_backoff(
                _call,
                attempts=self._settings.max_retries,
                description=f"openai.generate_structured[{response_model.__name__}][json-mode]",
                retryable=_is_retryable,
            )

    def _response_format(self, response_model: type[BaseModel]) -> dict[str, object]:
        if not self._supports_strict_schema:
            return {"type": "json_object"}

        return {
            "type": "json_schema",
            "json_schema": {
                "name": response_model.__name__,
                "strict": True,
                "schema": to_strict_json_schema(response_model),
            },
        }

    def embed(
        self,
        texts: Sequence[str],
        *,
        task: EmbeddingTask = EmbeddingTask.DOCUMENT,
    ) -> list[list[float]]:
        # OpenAI embeds queries and documents into the same space, so `task`
        # carries no meaning here and is accepted only for interface parity.
        del task

        if not texts:
            return []

        batch_size = self._settings.embedding_batch_size
        vectors: list[list[float]] = []

        for start in range(0, len(texts), batch_size):
            batch = list(texts[start : start + batch_size])

            def _call(batch: list[str] = batch) -> list[list[float]]:
                response = self._client.embeddings.create(model=self.embedding_model, input=batch)
                if len(response.data) != len(batch):
                    raise ProviderError(f"OpenAI returned {len(response.data)} embeddings for {len(batch)} inputs.")
                # The API does not guarantee ordering, but does return an index.
                ordered = sorted(response.data, key=lambda item: item.index)
                return [list(item.embedding) for item in ordered]

            vectors.extend(
                retry_with_backoff(
                    _call,
                    attempts=self._settings.max_retries,
                    description="openai.embed",
                    retryable=_is_retryable,
                )
            )

        return vectors
