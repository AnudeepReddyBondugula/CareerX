"""Embedding backends, ordered by quality and by how much they cost to run.

The service must work on a free host with no API key and 512 MB of RAM, so the
backend is resolved at runtime through a fallback chain rather than pinned at
import time:

1. ``provider``              - Gemini/OpenAI embedding APIs (best quality).
2. ``sentence-transformers`` - local MiniLM, free and offline, needs torch.
3. ``hashing``               - deterministic, dependency-free, always available.
"""

from __future__ import annotations

import abc
import hashlib
import logging
import math
import re
from collections.abc import Sequence

import numpy as np

from careerx.ai.providers.base import EmbeddingTask, LLMProvider
from careerx.config.settings import Settings, get_settings

logger = logging.getLogger(__name__)

_TOKEN_PATTERN = re.compile(r"[a-z0-9+#.]+")


class EmbeddingBackend(abc.ABC):
    """Turns text into unit-norm vectors suitable for cosine similarity."""

    name: str = "base"

    @property
    @abc.abstractmethod
    def dimension(self) -> int: ...

    @abc.abstractmethod
    def encode(self, texts: Sequence[str], *, task: EmbeddingTask) -> np.ndarray:
        """Return an ``(len(texts), dimension)`` float32 array of unit vectors."""

    @staticmethod
    def _normalise(matrix: np.ndarray) -> np.ndarray:
        """L2-normalise rows so an inner product equals cosine similarity."""
        matrix = np.asarray(matrix, dtype=np.float32)
        if matrix.ndim == 1:
            matrix = matrix.reshape(1, -1)
        norms = np.linalg.norm(matrix, axis=1, keepdims=True)
        # Guard against all-zero rows, which a hashing backend can produce for
        # text made entirely of stop characters.
        np.maximum(norms, 1e-12, out=norms)
        return (matrix / norms).astype(np.float32)


class ProviderEmbeddings(EmbeddingBackend):
    """Delegates to the configured LLM provider's embedding endpoint."""

    def __init__(self, provider: LLMProvider) -> None:
        self._provider = provider
        self.name = f"provider:{provider.name}:{provider.embedding_model}"
        self._dimension: int | None = None

    @property
    def dimension(self) -> int:
        if self._dimension is None:
            # Dimensions differ per model; discover once with a probe.
            self._dimension = len(self._provider.embed(["dimension probe"])[0])
        return self._dimension

    def encode(self, texts: Sequence[str], *, task: EmbeddingTask) -> np.ndarray:
        if not texts:
            return np.zeros((0, self.dimension), dtype=np.float32)

        vectors = self._provider.embed(list(texts), task=task)
        matrix = self._normalise(np.asarray(vectors, dtype=np.float32))
        self._dimension = matrix.shape[1]
        return matrix


class SentenceTransformerEmbeddings(EmbeddingBackend):
    """Local MiniLM-style embeddings; free and offline, but needs torch."""

    def __init__(self, model_name: str) -> None:
        from sentence_transformers import SentenceTransformer

        self._model = SentenceTransformer(model_name)
        self.name = f"sentence-transformers:{model_name}"

    @property
    def dimension(self) -> int:
        return int(self._model.get_sentence_embedding_dimension())

    def encode(self, texts: Sequence[str], *, task: EmbeddingTask) -> np.ndarray:
        del task  # symmetric model: queries and documents share one space

        if not texts:
            return np.zeros((0, self.dimension), dtype=np.float32)

        vectors = self._model.encode(list(texts), convert_to_numpy=True, show_progress_bar=False)
        return self._normalise(vectors)


class HashingEmbeddings(EmbeddingBackend):
    """Deterministic hashed bag-of-terms embeddings.

    This is the always-available floor of the fallback chain. It has no notion
    of synonymy, so it is genuinely weaker than a neural encoder, but it is
    exact on shared vocabulary, needs no network and no model download, and it
    keeps tests hermetic and fast.
    """

    def __init__(self, dimension: int = 512) -> None:
        self._dimension = dimension
        self.name = f"hashing:{dimension}"

    @property
    def dimension(self) -> int:
        return self._dimension

    def encode(self, texts: Sequence[str], *, task: EmbeddingTask) -> np.ndarray:
        del task

        matrix = np.zeros((len(texts), self._dimension), dtype=np.float32)

        for row, text in enumerate(texts):
            for term, count in self._terms(text).items():
                bucket, sign = self._bucket(term)
                # Sublinear term frequency damps the effect of repetition.
                matrix[row, bucket] += sign * (1.0 + math.log(count))

        return self._normalise(matrix)

    @staticmethod
    def _terms(text: str) -> dict[str, int]:
        """Word unigrams plus adjacent bigrams, to retain a little word order."""
        tokens = _TOKEN_PATTERN.findall(text.casefold())
        counts: dict[str, int] = {}

        for token in tokens:
            counts[token] = counts.get(token, 0) + 1

        for left, right in zip(tokens, tokens[1:], strict=False):
            bigram = f"{left}_{right}"
            counts[bigram] = counts.get(bigram, 0) + 1

        return counts

    def _bucket(self, term: str) -> tuple[int, float]:
        """Map a term to a bucket and a sign (signed hashing reduces collisions)."""
        digest = hashlib.blake2b(term.encode("utf-8"), digest_size=8).digest()
        value = int.from_bytes(digest, "big")
        return value % self._dimension, 1.0 if (value >> 63) & 1 else -1.0


def build_embedding_backend(
    settings: Settings | None = None,
    provider: LLMProvider | None = None,
) -> EmbeddingBackend:
    """Resolve an embedding backend, falling back when one is unavailable."""
    settings = settings or get_settings()
    choice = settings.embedding_backend

    if choice in {"auto", "provider"} and provider is not None:
        try:
            backend = ProviderEmbeddings(provider)
            backend.dimension  # noqa: B018 - probe now so failures surface here
            return backend
        except Exception as exc:  # noqa: BLE001 - any failure means fall through
            if choice == "provider":
                raise
            logger.warning("Provider embeddings unavailable (%s); falling back.", exc)

    if choice in {"auto", "sentence-transformers"}:
        try:
            return SentenceTransformerEmbeddings(settings.sentence_transformers_model)
        except Exception as exc:  # noqa: BLE001
            if choice == "sentence-transformers":
                raise
            logger.info("sentence-transformers unavailable (%s); using hashing embeddings.", exc)

    return HashingEmbeddings(settings.hashing_embedding_dimension)
