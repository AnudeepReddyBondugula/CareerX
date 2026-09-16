"""FAISS-backed vector index over profile evidence."""

from __future__ import annotations

import logging
from collections.abc import Sequence

import faiss
import numpy as np

from careerx.models import EvidenceChunk

logger = logging.getLogger(__name__)


class VectorIndex:
    """An exact inner-product index over unit-norm vectors.

    A profile has hundreds of chunks, not millions, so ``IndexFlatIP`` is the
    right choice: it is exact, needs no training, and an approximate index
    would trade away recall for a speedup that is irrelevant at this size.
    Because all vectors are L2-normalised, inner product *is* cosine
    similarity.
    """

    def __init__(self, dimension: int) -> None:
        self._dimension = dimension
        self._index = faiss.IndexFlatIP(dimension)
        self._chunks: list[EvidenceChunk] = []

    def __len__(self) -> int:
        return len(self._chunks)

    @property
    def dimension(self) -> int:
        return self._dimension

    @property
    def chunks(self) -> Sequence[EvidenceChunk]:
        return tuple(self._chunks)

    def add(self, chunks: Sequence[EvidenceChunk], vectors: np.ndarray) -> None:
        """Add ``chunks`` with their corresponding row vectors."""
        if len(chunks) != len(vectors):
            raise ValueError(f"Got {len(chunks)} chunks but {len(vectors)} vectors.")

        if not chunks:
            return

        if vectors.shape[1] != self._dimension:
            raise ValueError(f"Expected {self._dimension}-dimensional vectors, got {vectors.shape[1]}.")

        self._index.add(np.ascontiguousarray(vectors, dtype=np.float32))
        self._chunks.extend(chunks)

    def search(self, queries: np.ndarray, top_k: int) -> list[list[tuple[EvidenceChunk, float]]]:
        """Return the ``top_k`` nearest chunks for each query row.

        Queries are batched into a single FAISS call, which matters because a
        posting can carry dozens of requirements.
        """
        if len(self._chunks) == 0 or len(queries) == 0:
            return [[] for _ in range(len(queries))]

        queries = np.ascontiguousarray(queries, dtype=np.float32)
        effective_k = min(top_k, len(self._chunks))

        scores, indices = self._index.search(queries, effective_k)

        results: list[list[tuple[EvidenceChunk, float]]] = []
        for row_scores, row_indices in zip(scores, indices, strict=True):
            row: list[tuple[EvidenceChunk, float]] = []
            for score, position in zip(row_scores, row_indices, strict=True):
                # FAISS pads with -1 when fewer than k neighbours exist.
                if position < 0:
                    continue
                row.append((self._chunks[int(position)], float(score)))
            results.append(row)

        return results
