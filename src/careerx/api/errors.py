"""Exception types and handlers that keep error responses uniform."""

from __future__ import annotations

import logging

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from careerx.ai.providers.base import ProviderError, ProviderNotConfigured
from careerx.latex.compiler import LatexError
from careerx.renderers import TemplateNotFoundError
from careerx.services.artifact_store import ArtifactNotFoundError
from careerx.services.grounding import GroundingError
from careerx.services.profile_service import ProfileError

logger = logging.getLogger(__name__)


class RateLimitExceeded(Exception):
    """Raised when a client exceeds the configured request budget."""

    def __init__(self, retry_after_seconds: int) -> None:
        super().__init__("Rate limit exceeded.")
        self.retry_after_seconds = retry_after_seconds


class PayloadTooLarge(Exception):
    """Raised when an upload exceeds the configured size limit."""

    def __init__(self, limit_bytes: int) -> None:
        super().__init__(f"Payload exceeds the {limit_bytes} byte limit.")
        self.limit_bytes = limit_bytes


def _error(request: Request, code: int, error: str, detail: str, headers: dict[str, str] | None = None) -> JSONResponse:
    return JSONResponse(
        status_code=code,
        content={
            "error": error,
            "detail": detail,
            "request_id": getattr(request.state, "request_id", None),
        },
        headers=headers,
    )


def register_exception_handlers(app: FastAPI) -> None:
    """Map domain exceptions onto stable HTTP responses."""

    @app.exception_handler(ProfileError)
    async def _profile_error(request: Request, exc: ProfileError) -> JSONResponse:
        return _error(request, status.HTTP_422_UNPROCESSABLE_CONTENT, "invalid_profile", str(exc))

    @app.exception_handler(TemplateNotFoundError)
    async def _template_error(request: Request, exc: TemplateNotFoundError) -> JSONResponse:
        return _error(request, status.HTTP_400_BAD_REQUEST, "unknown_template", str(exc))

    @app.exception_handler(ArtifactNotFoundError)
    async def _artifact_error(request: Request, exc: ArtifactNotFoundError) -> JSONResponse:
        return _error(
            request,
            status.HTTP_404_NOT_FOUND,
            "artifact_not_found",
            "The requested artifact does not exist or has expired.",
        )

    @app.exception_handler(GroundingError)
    async def _grounding_error(request: Request, exc: GroundingError) -> JSONResponse:
        return _error(request, status.HTTP_422_UNPROCESSABLE_CONTENT, "ungrounded_content", str(exc))

    @app.exception_handler(ProviderNotConfigured)
    async def _provider_unconfigured(request: Request, exc: ProviderNotConfigured) -> JSONResponse:
        return _error(request, status.HTTP_503_SERVICE_UNAVAILABLE, "llm_not_configured", str(exc))

    @app.exception_handler(ProviderError)
    async def _provider_error(request: Request, exc: ProviderError) -> JSONResponse:
        logger.exception("Upstream LLM call failed.")
        return _error(
            request,
            status.HTTP_502_BAD_GATEWAY,
            "llm_upstream_error",
            "The language model provider could not complete the request. Please retry.",
        )

    @app.exception_handler(LatexError)
    async def _latex_error(request: Request, exc: LatexError) -> JSONResponse:
        return _error(request, status.HTTP_500_INTERNAL_SERVER_ERROR, "latex_error", str(exc))

    @app.exception_handler(RateLimitExceeded)
    async def _rate_limited(request: Request, exc: RateLimitExceeded) -> JSONResponse:
        return _error(
            request,
            status.HTTP_429_TOO_MANY_REQUESTS,
            "rate_limited",
            "Too many requests. Please slow down.",
            headers={"Retry-After": str(exc.retry_after_seconds)},
        )

    @app.exception_handler(PayloadTooLarge)
    async def _too_large(request: Request, exc: PayloadTooLarge) -> JSONResponse:
        return _error(request, status.HTTP_413_CONTENT_TOO_LARGE, "payload_too_large", str(exc))

    @app.exception_handler(RequestValidationError)
    async def _validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
        return _error(
            request,
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "validation_error",
            str(exc.errors()),
        )

    @app.exception_handler(Exception)
    async def _unhandled(request: Request, exc: Exception) -> JSONResponse:
        logger.exception("Unhandled error while serving %s %s", request.method, request.url.path)
        return _error(
            request,
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "internal_error",
            "An unexpected error occurred.",
        )
