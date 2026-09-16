"""Parse a raw job posting into a structured :class:`JobDescription`."""

from __future__ import annotations

import logging

from careerx.ai.prompts import JD_PARSER_SYSTEM_INSTRUCTION
from careerx.ai.providers.base import LLMProvider
from careerx.models import JobDescription

logger = logging.getLogger(__name__)


class JobDescriptionParser:
    def __init__(self, provider: LLMProvider) -> None:
        self._provider = provider

    def parse(self, job_description: str) -> JobDescription:
        text = job_description.strip()
        if not text:
            raise ValueError("Job description is empty.")

        logger.info("Parsing job description (%s chars).", len(text))

        parsed = self._provider.generate_structured(
            system_instruction=JD_PARSER_SYSTEM_INSTRUCTION,
            user_prompt=text,
            response_model=JobDescription,
        )

        logger.info(
            "Parsed job description: %r at %r, %s requirement(s).",
            parsed.title,
            parsed.company,
            len(parsed.requirement_statements()),
        )

        return parsed
