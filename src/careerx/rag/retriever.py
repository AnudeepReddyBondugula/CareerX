"""Semantic retrieval of profile evidence for a job posting."""

from __future__ import annotations

import logging
from collections import defaultdict

from careerx.ai.providers.base import EmbeddingTask
from careerx.config.settings import Settings, get_settings
from careerx.models import (
    CoverageReport,
    EvidenceChunk,
    EvidenceMatch,
    JobDescription,
    RequirementMatch,
    Resume,
    SectionScore,
)
from careerx.rag.chunking import build_evidence_chunks
from careerx.rag.embeddings import EmbeddingBackend
from careerx.rag.index import VectorIndex

logger = logging.getLogger(__name__)

# Cosine thresholds for the coverage report. Tuned for normalised embeddings:
# below ~0.25 two texts generally share only incidental vocabulary.
COVERED_THRESHOLD = 0.55
PARTIAL_THRESHOLD = 0.30


class RetrievalResult:
    """Everything one retrieval pass produced."""

    def __init__(
        self,
        *,
        chunks: list[EvidenceChunk],
        requirement_matches: list[RequirementMatch],
        section_scores: list[SectionScore],
        coverage: CoverageReport,
        backend_name: str,
    ) -> None:
        self.chunks = chunks
        self.requirement_matches = requirement_matches
        self.section_scores = section_scores
        self.coverage = coverage
        self.backend_name = backend_name

    def top_evidence(self, limit: int = 60) -> list[EvidenceChunk]:
        """Highest-scoring distinct chunks across all requirements.

        This is what gets injected into the generation prompt, so it is capped:
        the point of retrieval is to send the model less, not everything.
        """
        best: dict[str, float] = {}
        for match in self.requirement_matches:
            for evidence in match.matches:
                best[evidence.chunk_id] = max(best.get(evidence.chunk_id, -1.0), evidence.score)

        by_id = {chunk.chunk_id: chunk for chunk in self.chunks}
        ranked = sorted(best.items(), key=lambda item: item[1], reverse=True)

        return [by_id[chunk_id] for chunk_id, _ in ranked[:limit] if chunk_id in by_id]


class EvidenceRetriever:
    """Builds a per-request FAISS index over a profile and queries it.

    The index is scoped to a single request because the service is stateless:
    a profile arrives, is indexed, is queried, and is discarded.
    """

    def __init__(
        self,
        backend: EmbeddingBackend,
        settings: Settings | None = None,
    ) -> None:
        self._backend = backend
        self._settings = settings or get_settings()

    def retrieve(self, resume: Resume, job_description: JobDescription) -> RetrievalResult:
        chunks = build_evidence_chunks(resume)
        requirements = job_description.requirement_statements()

        if not chunks or not requirements:
            logger.info(
                "Skipping retrieval: %s chunk(s), %s requirement(s).",
                len(chunks),
                len(requirements),
            )
            return RetrievalResult(
                chunks=chunks,
                requirement_matches=[],
                section_scores=[],
                coverage=CoverageReport(uncovered=list(requirements)),
                backend_name=self._backend.name,
            )

        document_vectors = self._backend.encode([chunk.text for chunk in chunks], task=EmbeddingTask.DOCUMENT)
        query_vectors = self._backend.encode(requirements, task=EmbeddingTask.QUERY)

        index = VectorIndex(document_vectors.shape[1])
        index.add(chunks, document_vectors)

        neighbours = index.search(query_vectors, self._settings.retrieval_top_k)

        requirement_matches = [
            RequirementMatch(
                requirement=requirement,
                matches=[
                    EvidenceMatch(
                        chunk_id=chunk.chunk_id,
                        kind=chunk.kind,
                        label=chunk.label,
                        text=chunk.text,
                        score=round(score, 4),
                    )
                    for chunk, score in row
                ],
            )
            for requirement, row in zip(requirements, neighbours, strict=True)
        ]

        return RetrievalResult(
            chunks=chunks,
            requirement_matches=requirement_matches,
            section_scores=self._score_sections(requirement_matches, chunks),
            coverage=self._build_coverage(requirement_matches),
            backend_name=self._backend.name,
        )

    @staticmethod
    def _score_sections(
        requirement_matches: list[RequirementMatch],
        chunks: list[EvidenceChunk],
    ) -> list[SectionScore]:
        """Roll per-chunk hits up into a relevance score per profile entry.

        A job or project is scored by how many distinct requirements it is the
        best evidence for, weighted by similarity - so one strongly matching
        bullet does not outrank an entry that speaks to five requirements.
        """
        by_section = {chunk.section_id: chunk for chunk in chunks}
        totals: dict[str, float] = defaultdict(float)
        matched: dict[str, list[str]] = defaultdict(list)

        for match in requirement_matches:
            seen_sections: set[str] = set()
            for evidence in match.matches:
                if evidence.score <= 0:
                    continue

                chunk_section = f"{evidence.kind.value}:{evidence.chunk_id.split(':')[1]}"
                if chunk_section in seen_sections:
                    continue

                seen_sections.add(chunk_section)
                totals[chunk_section] += evidence.score
                matched[chunk_section].append(match.requirement)

        scores = [
            SectionScore(
                section_id=section_id,
                kind=by_section[section_id].kind,
                label=by_section[section_id].label,
                score=round(total, 4),
                matched_requirements=matched[section_id],
            )
            for section_id, total in totals.items()
            if section_id in by_section
        ]

        scores.sort(key=lambda item: item.score, reverse=True)
        return scores

    @staticmethod
    def _build_coverage(requirement_matches: list[RequirementMatch]) -> CoverageReport:
        coverage = CoverageReport()

        for match in requirement_matches:
            best = match.best_score
            if best >= COVERED_THRESHOLD:
                coverage.covered.append(match.requirement)
            elif best >= PARTIAL_THRESHOLD:
                coverage.partially_covered.append(match.requirement)
            else:
                coverage.uncovered.append(match.requirement)

        return coverage
