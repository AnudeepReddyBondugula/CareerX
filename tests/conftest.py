"""Shared fixtures.

Every test runs against a fake LLM provider, so the suite is hermetic: no API
key, no network, and deterministic output.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import TypeVar

import pytest
from pydantic import BaseModel

from careerx.ai.providers.base import EmbeddingTask, LLMProvider
from careerx.config.settings import Settings
from careerx.examples import EXAMPLE_JOB_DESCRIPTION, example_profile
from careerx.models import JobDescription, Resume

T = TypeVar("T", bound=BaseModel)


class FakeProvider(LLMProvider):
    """Returns canned structured responses and records what it was asked.

    ``embed`` deliberately raises so tests exercise the local fallback in the
    embedding chain rather than silently depending on a network call.
    """

    name = "fake"

    def __init__(
        self,
        *,
        job_description: JobDescription | None = None,
        resume: Resume | None = None,
    ) -> None:
        self.job_description = job_description or JobDescription()
        self.resume = resume or Resume()
        self.prompts: list[str] = []
        self.calls = 0

    @property
    def chat_model(self) -> str:
        return "fake-chat"

    @property
    def embedding_model(self) -> str:
        return "fake-embedding"

    def generate_structured(
        self,
        *,
        system_instruction: str,
        user_prompt: str,
        response_model: type[T],
    ) -> T:
        self.calls += 1
        self.prompts.append(user_prompt)

        if response_model is JobDescription:
            return self.job_description  # type: ignore[return-value]
        if response_model is Resume:
            return self.resume  # type: ignore[return-value]

        raise AssertionError(f"Unexpected response model: {response_model}")

    def embed(
        self,
        texts: Sequence[str],
        *,
        task: EmbeddingTask = EmbeddingTask.DOCUMENT,
    ) -> list[list[float]]:
        raise RuntimeError("FakeProvider does not provide embeddings.")


@pytest.fixture
def profile() -> Resume:
    return example_profile()


@pytest.fixture
def job_description_text() -> str:
    return EXAMPLE_JOB_DESCRIPTION


@pytest.fixture
def parsed_job_description() -> JobDescription:
    return JobDescription(
        title="Senior Backend Engineer",
        company="Northwind",
        seniority="Senior",
        summary="Own the services behind the payments platform.",
        responsibilities=[
            "Design, build and operate Python microservices handling millions of events daily.",
            "Own service reliability, including on-call and incident review.",
            "Improve CI/CD pipelines and automated test coverage.",
        ],
        required_skills=["Python", "FastAPI", "PostgreSQL", "Docker"],
        preferred_skills=["Kafka", "Terraform"],
        keywords=["microservices", "reliability", "payments"],
    )


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    """Settings isolated from the developer's own ``.env`` and filesystem."""
    return Settings(
        _env_file=None,
        llm_provider="gemini",
        google_api_key="test-key",
        embedding_backend="hashing",
        artifact_dir=tmp_path / "artifacts",
        artifact_ttl_seconds=60,
        rate_limit_requests=1000,
    )


@pytest.fixture
def provider(parsed_job_description: JobDescription, profile: Resume) -> FakeProvider:
    return FakeProvider(job_description=parsed_job_description, resume=profile)
