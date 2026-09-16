"""Provider-agnostic LLM interface.

Everything downstream of this module depends on :class:`LLMProvider` rather
than on a vendor SDK, which is what makes the provider swappable at runtime
through a single environment variable.
"""

from __future__ import annotations

import abc
import logging
import random
import time
from collections.abc import Callable, Sequence
from enum import StrEnum
from typing import TypeVar

from pydantic import BaseModel

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)


class EmbeddingTask(StrEnum):
    """Some providers embed queries and documents into different spaces."""

    DOCUMENT = "document"
    QUERY = "query"


class ProviderError(RuntimeError):
    """Raised when a provider call fails after exhausting retries."""


class ProviderNotConfigured(ProviderError):
    """Raised when the selected provider has no usable credentials."""


class ProviderRequestError(ProviderError):
    """A provider rejected the request; retrying it unchanged will not help."""


def retry_with_backoff[R](
    operation: Callable[[], R],
    *,
    attempts: int,
    base_delay: float = 0.5,
    max_delay: float = 8.0,
    description: str = "provider call",
    sleep: Callable[[float], None] = time.sleep,
    retryable: Callable[[Exception], bool] = lambda _: True,
) -> R:
    """Run ``operation``, retrying transient failures with jittered backoff.

    ``retryable`` decides whether an exception is worth another attempt. The
    default retries everything; providers narrow it, so that a bad API key or a
    malformed request fails immediately instead of being retried three times
    against a wall.

    Kept dependency-free and injectable (``sleep``) so tests exercise the retry
    path without actually waiting.
    """
    last_error: Exception | None = None

    for attempt in range(1, attempts + 1):
        try:
            return operation()
        except ProviderNotConfigured:
            raise
        except Exception as exc:  # noqa: BLE001 - provider SDKs raise broadly
            last_error = exc

            if not retryable(exc):
                logger.error("%s failed with a non-retryable error: %s", description, exc)
                raise ProviderRequestError(f"{description} was rejected: {exc}") from exc

            logger.warning(
                "%s failed (attempt %s/%s): %s",
                description,
                attempt,
                attempts,
                exc,
            )

            if attempt == attempts:
                break

            delay = min(max_delay, base_delay * 2 ** (attempt - 1))
            sleep(delay * (0.5 + random.random() / 2))  # noqa: S311 - jitter, not crypto

    raise ProviderError(f"{description} failed after {attempts} attempt(s): {last_error}") from last_error


class LLMProvider(abc.ABC):
    """Structured generation and embeddings from a single vendor."""

    name: str = "base"

    @property
    @abc.abstractmethod
    def chat_model(self) -> str:
        """Identifier of the generation model in use."""

    @property
    @abc.abstractmethod
    def embedding_model(self) -> str:
        """Identifier of the embedding model in use."""

    @abc.abstractmethod
    def generate_structured(
        self,
        *,
        system_instruction: str,
        user_prompt: str,
        response_model: type[T],
    ) -> T:
        """Return a validated ``response_model`` instance from the model."""

    @abc.abstractmethod
    def embed(
        self,
        texts: Sequence[str],
        *,
        task: EmbeddingTask = EmbeddingTask.DOCUMENT,
    ) -> list[list[float]]:
        """Embed ``texts``, returning one vector per input in the same order."""
