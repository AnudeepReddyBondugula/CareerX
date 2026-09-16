"""Resume generation and artifact download."""

from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, File, Form, Request, UploadFile
from fastapi.responses import FileResponse

from careerx.api.dependencies import (
    ArtifactStoreDep,
    RateLimited,
    ServiceDep,
    SettingsDep,
)
from careerx.api.errors import PayloadTooLarge
from careerx.api.schemas import ArtifactLinks, GenerateRequest, GenerateResponse
from careerx.services.artifact_store import ArtifactStore
from careerx.services.generation_service import GenerationResult
from careerx.services.profile_service import ProfileError, parse_profile

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["generation"])

LATEX_ARTIFACT = "resume.tex"
PDF_ARTIFACT = "resume.pdf"
JSON_ARTIFACT = "resume.json"
REPORT_ARTIFACT = "report.json"


@router.post(
    "/generate",
    response_model=GenerateResponse,
    dependencies=[RateLimited],
    summary="Generate a tailored resume from a profile and a job description",
)
def generate(
    request: Request,
    body: GenerateRequest,
    service: ServiceDep,
    artifacts: ArtifactStoreDep,
    settings: SettingsDep,
) -> GenerateResponse:
    """Run the full pipeline against a JSON profile."""
    _check_job_description_length(body.job_description, settings.max_job_description_chars)

    result = service.generate(
        profile=body.profile,
        job_description_text=body.job_description,
        template=body.template,
        compile_pdf=body.compile_pdf,
    )

    return _persist_and_respond(
        request=request,
        result=result,
        artifacts=artifacts,
        ttl_seconds=settings.artifact_ttl_seconds,
        include_latex=body.include_latex,
        include_report=body.include_report,
    )


@router.post(
    "/generate/upload",
    response_model=GenerateResponse,
    dependencies=[RateLimited],
    summary="Generate a tailored resume from an uploaded profile.json file",
)
async def generate_from_upload(
    request: Request,
    service: ServiceDep,
    artifacts: ArtifactStoreDep,
    settings: SettingsDep,
    profile: Annotated[UploadFile, File(description="The candidate's profile.json.")],
    job_description: Annotated[str, Form(description="The raw job posting text.")] = "",
    job_description_file: Annotated[UploadFile | None, File(description="The posting as a .txt file.")] = None,
    template: Annotated[str | None, Form()] = None,
    compile_pdf: Annotated[bool, Form()] = True,
    include_report: Annotated[bool, Form()] = True,
    include_latex: Annotated[bool, Form()] = True,
) -> GenerateResponse:
    """Multipart variant, so the browser UI and ``curl -F`` both work."""
    profile_bytes = await _read_limited(profile, settings.max_upload_bytes)

    posting = job_description.strip()
    if job_description_file is not None:
        file_bytes = await _read_limited(job_description_file, settings.max_upload_bytes)
        posting = file_bytes.decode("utf-8", errors="replace").strip() or posting

    if not posting:
        raise ProfileError("A job description must be supplied, either as text or as a file.")

    _check_job_description_length(posting, settings.max_job_description_chars)

    result = service.generate(
        profile=parse_profile(profile_bytes.decode("utf-8", errors="replace")),
        job_description_text=posting,
        template=template or None,
        compile_pdf=compile_pdf,
    )

    return _persist_and_respond(
        request=request,
        result=result,
        artifacts=artifacts,
        ttl_seconds=settings.artifact_ttl_seconds,
        include_latex=include_latex,
        include_report=include_report,
    )


@router.get(
    "/runs/{run_id}/{artifact}",
    summary="Download an artifact produced by a previous run",
    response_class=FileResponse,
)
def download(run_id: str, artifact: str, artifacts: ArtifactStoreDep) -> FileResponse:
    stored = artifacts.read(run_id, artifact)

    return FileResponse(
        stored.path,
        media_type=stored.media_type,
        filename=artifact,
        headers={"Cache-Control": "no-store"},
    )


# ----------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------


def _check_job_description_length(text: str, limit: int) -> None:
    if len(text) > limit:
        raise PayloadTooLarge(limit)


async def _read_limited(upload: UploadFile, limit_bytes: int) -> bytes:
    """Read an upload, refusing anything over the limit.

    Read in bounded chunks rather than calling ``.read()``, so an oversized
    upload is rejected without first buffering it all in memory.
    """
    chunks: list[bytes] = []
    total = 0

    while chunk := await upload.read(64 * 1024):
        total += len(chunk)
        if total > limit_bytes:
            raise PayloadTooLarge(limit_bytes)
        chunks.append(chunk)

    if total == 0:
        raise ProfileError(f"Uploaded file {upload.filename!r} is empty.")

    return b"".join(chunks)


def _persist_and_respond(
    *,
    request: Request,
    result: GenerationResult,
    artifacts: ArtifactStore,
    ttl_seconds: int,
    include_latex: bool,
    include_report: bool,
) -> GenerateResponse:
    run_id = artifacts.new_run_id()

    artifacts.write(run_id, LATEX_ARTIFACT, result.latex)
    artifacts.write(run_id, JSON_ARTIFACT, result.resume.model_dump_json(indent=2))
    artifacts.write(run_id, REPORT_ARTIFACT, result.report.model_dump_json(indent=2))

    if result.pdf_bytes is not None:
        artifacts.write(run_id, PDF_ARTIFACT, result.pdf_bytes)

    def link(artifact: str) -> str:
        return str(request.url_for("download", run_id=run_id, artifact=artifact))

    logger.info(
        "Run %s complete (template=%s, pdf=%s, issues=%s).",
        run_id,
        result.template,
        result.pdf_available,
        len(result.report.grounding_issues),
    )

    return GenerateResponse(
        run_id=run_id,
        template=result.template,
        expires_in_seconds=ttl_seconds,
        job_description=result.job_description,
        resume=result.resume,
        latex=result.latex if include_latex else None,
        pdf_available=result.pdf_available,
        pdf_unavailable_reason=result.pdf_unavailable_reason,
        report=result.report if include_report else None,
        artifacts=ArtifactLinks(
            latex=link(LATEX_ARTIFACT),
            resume_json=link(JSON_ARTIFACT),
            pdf=link(PDF_ARTIFACT) if result.pdf_available else None,
        ),
        timings_ms=result.timings_ms,
    )
