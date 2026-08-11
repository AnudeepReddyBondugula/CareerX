from __future__ import annotations

import logging
from typing import TypeVar

from google import genai
from google.genai import types
from pydantic import BaseModel

from careerx.config.settings import settings

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)


class GeminiClient:
    """
    Wrapper around the Google Gemini API.

    Responsibilities
    ----------------
    - Configure Gemini
    - Send prompts
    - Return structured Pydantic models
    - Retry transient failures
    """

    def __init__(self) -> None:
        self.client = genai.Client(api_key=settings.google_api_key)

        self.model = settings.gemini_model
        self.temperature = settings.temperature
        self.max_retries = settings.max_retries

    def generate(
        self,
        *,
        system_instruction: str,
        user_prompt: str,
        response_model: type[T],
    ) -> T:
        """
        Generate a structured response from Gemini.

        Parameters
        ----------
        system_instruction:
            System prompt.

        user_prompt:
            User input.

        response_model:
            Pydantic model describing the expected output.

        Returns
        -------
        T
            Validated Pydantic model.
        """

        last_exception: Exception | None = None

        for attempt in range(1, self.max_retries + 1):
            try:
                logger.info(
                    "Calling Gemini (%s). Attempt %s/%s",
                    self.model,
                    attempt,
                    self.max_retries,
                )

                response = self.client.models.generate_content(
                    model=self.model,
                    contents=user_prompt,
                    config=types.GenerateContentConfig(
                        system_instruction=system_instruction,
                        temperature=self.temperature,
                        response_mime_type="application/json",
                        response_schema=response_model,
                    ),
                )

                logger.info("Gemini request successful.")

                return response.parsed

            except Exception as exc:
                last_exception = exc

                logger.exception(
                    "Gemini request failed (Attempt %s/%s)",
                    attempt,
                    self.max_retries,
                )

        assert last_exception is not None

        raise last_exception