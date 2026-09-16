"""Health, readiness and capability endpoints."""

from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Response, status

from careerx import __version__
from careerx.api.dependencies import ArtifactStoreDep, SettingsDep, StateDep
from careerx.api.schemas import HealthResponse, MetaResponse, TemplateInfo
from careerx.latex.compiler import detect_engine
from careerx.models import Resume
from careerx.renderers import ResumeRenderer

router = APIRouter(tags=["system"])


@router.get("/healthz", response_model=HealthResponse, summary="Liveness probe")
def healthz() -> HealthResponse:
    """Always succeeds while the process can serve requests."""
    return HealthResponse(status="ok", checks={"version": __version__})


@router.get("/readyz", response_model=HealthResponse, summary="Readiness probe")
def readyz(state: StateDep, artifacts: ArtifactStoreDep, response: Response) -> HealthResponse:
    """Reports whether the service can actually complete a generation.

    A missing LaTeX engine is reported as degraded rather than unready: the
    service still returns usable LaTeX source without one.
    """
    service = state.try_build_service()
    engine = detect_engine(state.settings.latex_engine)

    checks: dict[str, Any] = {
        "llm_provider": state.settings.llm_provider,
        "llm_configured": service is not None,
        "latex_engine": engine,
        "artifact_dir_writable": _is_writable(artifacts),
    }

    if service is None:
        checks["llm_error"] = state.provider_error

    ready = checks["llm_configured"] and checks["artifact_dir_writable"]

    if not ready:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return HealthResponse(status="degraded", checks=checks)

    if engine is None:
        return HealthResponse(status="degraded", checks=checks)

    return HealthResponse(status="ok", checks=checks)


@router.get("/api/v1/meta", response_model=MetaResponse, summary="Deployment capabilities")
def meta(state: StateDep, settings: SettingsDep) -> MetaResponse:
    renderer = ResumeRenderer()
    templates = renderer.available_templates()
    engine = detect_engine(settings.latex_engine)
    service = state.try_build_service()

    return MetaResponse(
        app=settings.app_name,
        version=__version__,
        environment=settings.environment,
        llm_provider=settings.llm_provider,
        llm_configured=service is not None,
        chat_model=service.provider.chat_model if service else None,
        embedding_backend=service.embedding_backend_name if service else None,
        latex_engine=engine,
        pdf_supported=engine is not None,
        templates=[TemplateInfo(name=name, is_default=name == settings.default_template) for name in templates],
        default_template=settings.default_template,
        limits={
            "max_upload_bytes": settings.max_upload_bytes,
            "max_job_description_chars": settings.max_job_description_chars,
            "artifact_ttl_seconds": settings.artifact_ttl_seconds,
            "rate_limit_requests": settings.rate_limit_requests,
            "rate_limit_window_seconds": settings.rate_limit_window_seconds,
        },
    )


@router.get("/api/v1/profile/schema", summary="JSON Schema for the profile upload")
def profile_schema() -> dict[str, Any]:
    """The exact schema a uploaded ``profile.json`` must satisfy."""
    return Resume.model_json_schema()


@router.get("/api/v1/profile/example", summary="A minimal valid profile")
def profile_example() -> dict[str, Any]:
    """A filled-in example, useful as a starting point for a real profile."""
    from careerx.examples import example_profile

    return json.loads(example_profile().model_dump_json())


def _is_writable(artifacts: ArtifactStoreDep) -> bool:
    try:
        artifacts.root.mkdir(parents=True, exist_ok=True)
        probe = artifacts.root / ".write-probe"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
    except OSError:
        return False

    return True
