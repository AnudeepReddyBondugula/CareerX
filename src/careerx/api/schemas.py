"""Request and response bodies for the HTTP API."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

from careerx.models import JobDescription, Resume, TailoringReport


class GenerateRequest(BaseModel):
    """JSON body for ``POST /api/v1/generate``."""

    profile: Resume = Field(description="The candidate's complete master profile.")
    job_description: str = Field(min_length=1, description="The raw job posting text.")
    template: str | None = Field(default=None, description="Template name; defaults to the server default.")
    compile_pdf: bool = Field(default=True, description="Compile the LaTeX to PDF as well as returning source.")
    include_report: bool = Field(default=True, description="Include the retrieval/grounding report in the response.")
    include_latex: bool = Field(default=True, description="Inline the LaTeX source in the response.")

    @field_validator("job_description")
    @classmethod
    def _non_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("job_description must not be blank.")
        return value


class ArtifactLinks(BaseModel):
    """Where to download this run's outputs."""

    latex: str
    resume_json: str
    pdf: str | None = None


class GenerateResponse(BaseModel):
    run_id: str
    template: str
    expires_in_seconds: int

    job_description: JobDescription
    resume: Resume

    latex: str | None = None
    pdf_available: bool = False
    pdf_unavailable_reason: str | None = None

    report: TailoringReport | None = None
    artifacts: ArtifactLinks
    timings_ms: dict[str, int] = Field(default_factory=dict)


class TemplateInfo(BaseModel):
    name: str
    is_default: bool


class MetaResponse(BaseModel):
    """Everything a client needs to know about this deployment's capabilities."""

    app: str
    version: str
    environment: str

    llm_provider: str
    llm_configured: bool
    chat_model: str | None = None
    embedding_backend: str | None = None

    latex_engine: str | None = None
    pdf_supported: bool

    templates: list[TemplateInfo]
    default_template: str

    limits: dict[str, int]


class HealthResponse(BaseModel):
    status: Literal["ok", "degraded"]
    checks: dict[str, Any] = Field(default_factory=dict)


class ErrorResponse(BaseModel):
    error: str
    detail: str
    request_id: str | None = None
