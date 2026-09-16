"""Shared application state and FastAPI dependencies."""

from __future__ import annotations

import logging
from typing import Annotated

from fastapi import Depends, Request

from careerx.ai.providers.base import LLMProvider, ProviderNotConfigured
from careerx.api.errors import RateLimitExceeded
from careerx.api.rate_limit import SlidingWindowRateLimiter
from careerx.config.settings import Settings
from careerx.services.artifact_store import ArtifactStore
from careerx.services.generation_service import ResumeGenerationService

logger = logging.getLogger(__name__)


class AppState:
    """Process-wide objects built once at startup.

    The LLM provider and the embedding backend are expensive to construct (a
    network probe, possibly a model load), so they are created lazily on first
    use and then reused, rather than per request.
    """

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.artifacts = ArtifactStore(settings.artifact_dir, ttl_seconds=settings.artifact_ttl_seconds)
        self.rate_limiter = SlidingWindowRateLimiter(
            settings.rate_limit_requests,
            settings.rate_limit_window_seconds,
        )

        self._provider: LLMProvider | None = None
        self._service: ResumeGenerationService | None = None
        self._provider_error: str | None = None

    @property
    def provider_error(self) -> str | None:
        return self._provider_error

    def try_build_service(self) -> ResumeGenerationService | None:
        """Build the pipeline, returning ``None`` when it cannot be configured.

        Used by readiness checks, which must report on the provider without
        turning a missing API key into a 500.
        """
        try:
            return self.service
        except ProviderNotConfigured as exc:
            self._provider_error = str(exc)
            return None

    @property
    def provider(self) -> LLMProvider:
        if self._provider is None:
            from careerx.ai.providers.factory import build_provider

            self._provider = build_provider(self.settings)
            self._provider_error = None

        return self._provider

    @property
    def service(self) -> ResumeGenerationService:
        if self._service is None:
            self._service = ResumeGenerationService(provider=self.provider, settings=self.settings)

        return self._service


def get_state(request: Request) -> AppState:
    return request.app.state.careerx


def get_settings_dep(state: Annotated[AppState, Depends(get_state)]) -> Settings:
    return state.settings


def get_artifact_store(state: Annotated[AppState, Depends(get_state)]) -> ArtifactStore:
    return state.artifacts


def get_service(state: Annotated[AppState, Depends(get_state)]) -> ResumeGenerationService:
    return state.service


def enforce_rate_limit(request: Request, state: Annotated[AppState, Depends(get_state)]) -> None:
    """Rate limit by client address, honouring a proxy's forwarded header."""
    forwarded = request.headers.get("x-forwarded-for", "")
    client_host = forwarded.split(",")[0].strip() if forwarded else (request.client.host if request.client else "-")

    allowed, retry_after = state.rate_limiter.check(client_host)

    if not allowed:
        logger.info("Rate limited %s on %s", client_host, request.url.path)
        raise RateLimitExceeded(retry_after)


StateDep = Annotated[AppState, Depends(get_state)]
SettingsDep = Annotated[Settings, Depends(get_settings_dep)]
ArtifactStoreDep = Annotated[ArtifactStore, Depends(get_artifact_store)]
ServiceDep = Annotated[ResumeGenerationService, Depends(get_service)]
RateLimited = Depends(enforce_rate_limit)
