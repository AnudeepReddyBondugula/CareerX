from __future__ import annotations

import logging

from careerx.ai.gemini_client import GeminiClient
from careerx.ai.prompts.resume_builder_prompt import SYSTEM_INSTRUCTION
from careerx.models import JobDescription, Resume

logger = logging.getLogger(__name__)


class ResumeBuilder:
    """
    Builds an ATS-optimized Resume from an existing Resume
    and a parsed Job Description.
    """

    def __init__(
        self,
        client: GeminiClient | None = None,
    ) -> None:
        self.client = client or GeminiClient()

    def build(
        self,
        resume: Resume,
        job_description: JobDescription,
    ) -> Resume:
        """
        Generate a tailored resume.

        Parameters
        ----------
        resume:
            Candidate's master resume.

        job_description:
            Parsed Job Description.

        Returns
        -------
        Resume
            ATS-optimized resume.
        """

        logger.info("Generating tailored resume.")

        prompt = self._build_prompt(
            resume=resume,
            job_description=job_description,
        )

        tailored_resume = self.client.generate(
            system_instruction=SYSTEM_INSTRUCTION,
            user_prompt=prompt,
            response_model=Resume,
        )

        logger.info("Resume generated successfully.")

        return tailored_resume

    @staticmethod
    def _build_prompt(
        *,
        resume: Resume,
        job_description: JobDescription,
    ) -> str:
        """
        Construct the prompt sent to Gemini.
        """

        return f"""
Candidate Resume
================

{resume.model_dump_json(indent=2)}

==================================================

Job Description
===============

{job_description.model_dump_json(indent=2)}

==================================================

Generate an ATS-optimized Resume.
Return only valid JSON.
"""
