"""Generate a tailored resume from a profile, a posting and retrieved evidence."""

from __future__ import annotations

import json
import logging

from careerx.ai.prompts import RESUME_BUILDER_SYSTEM_INSTRUCTION
from careerx.ai.providers.base import LLMProvider
from careerx.models import JobDescription, Resume
from careerx.rag.retriever import RetrievalResult

logger = logging.getLogger(__name__)

MAX_EVIDENCE_ITEMS = 60
MAX_RANKED_SECTIONS = 12


class ResumeBuilder:
    """Turns a master profile into a posting-specific resume."""

    def __init__(self, provider: LLMProvider) -> None:
        self._provider = provider

    def build(
        self,
        *,
        resume: Resume,
        job_description: JobDescription,
        retrieval: RetrievalResult | None = None,
    ) -> Resume:
        logger.info("Generating tailored resume for %r.", job_description.title or "unspecified role")

        tailored = self._provider.generate_structured(
            system_instruction=RESUME_BUILDER_SYSTEM_INSTRUCTION,
            user_prompt=self._build_prompt(
                resume=resume,
                job_description=job_description,
                retrieval=retrieval,
            ),
            response_model=Resume,
        )

        logger.info(
            "Tailored resume generated: %s role(s), %s project(s), %s skill(s).",
            len(tailored.experience),
            len(tailored.projects),
            len(tailored.skills),
        )

        return tailored

    @staticmethod
    def _build_prompt(
        *,
        resume: Resume,
        job_description: JobDescription,
        retrieval: RetrievalResult | None,
    ) -> str:
        sections = [
            "## CANDIDATE PROFILE",
            resume.model_dump_json(indent=2),
            "",
            "## JOB POSTING",
            job_description.model_dump_json(indent=2),
        ]

        if retrieval is not None:
            sections += [
                "",
                "## RETRIEVED EVIDENCE",
                "Profile facts ranked most relevant to this posting by semantic search.",
                _format_evidence(retrieval),
                "",
                "## SECTION RANKING",
                "Aggregate relevance of each profile entry to the whole posting.",
                _format_sections(retrieval),
                "",
                "## COVERAGE",
                _format_coverage(retrieval),
            ]

        sections += [
            "",
            "Produce the tailored resume as JSON matching the schema.",
        ]

        return "\n".join(sections)


def _format_evidence(retrieval: RetrievalResult) -> str:
    """Render the retrieved chunks compactly, best score first."""
    best: dict[str, tuple[float, str, str]] = {}

    for match in retrieval.requirement_matches:
        for evidence in match.matches:
            existing = best.get(evidence.chunk_id)
            if existing is None or evidence.score > existing[0]:
                best[evidence.chunk_id] = (evidence.score, evidence.label, evidence.text)

    ranked = sorted(best.items(), key=lambda item: item[1][0], reverse=True)[:MAX_EVIDENCE_ITEMS]

    if not ranked:
        return "(no evidence retrieved)"

    return "\n".join(f"- [{chunk_id}] (score {score:.2f}) {text}" for chunk_id, (score, _label, text) in ranked)


def _format_sections(retrieval: RetrievalResult) -> str:
    ranked = retrieval.section_scores[:MAX_RANKED_SECTIONS]

    if not ranked:
        return "(no sections ranked)"

    return "\n".join(
        f"- {item.label or item.section_id} ({item.kind.value}): score {item.score:.2f}, "
        f"matches {len(item.matched_requirements)} requirement(s)"
        for item in ranked
    )


def _format_coverage(retrieval: RetrievalResult) -> str:
    coverage = retrieval.coverage
    return json.dumps(
        {
            "well_supported": coverage.covered,
            "partially_supported": coverage.partially_covered,
            "not_supported_do_not_claim": coverage.uncovered,
        },
        indent=2,
    )
