"""HTTP-level tests, driven through FastAPI's TestClient.

The app is built with a fake provider injected into ``AppState``, so these
exercise real routing, validation, serialisation and error mapping without
touching an LLM.
"""

from __future__ import annotations

import io
import json
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from careerx.api.app import create_app
from careerx.config.settings import Settings
from careerx.examples import EXAMPLE_JOB_DESCRIPTION
from careerx.latex.compiler import LatexCompiler, LatexEngineUnavailable, detect_engine
from careerx.models import Resume
from careerx.rag.embeddings import HashingEmbeddings
from careerx.services.generation_service import ResumeGenerationService

from .conftest import FakeProvider


class _NoEngineCompiler(LatexCompiler):
    def compile(self, latex_source: str, *, job_name: str = "resume") -> object:
        raise LatexEngineUnavailable("No LaTeX engine found.")


@pytest.fixture
def client(settings: Settings, provider: FakeProvider) -> Iterator[TestClient]:
    app = create_app(settings)
    state = app.state.careerx

    state._provider = provider
    state._service = ResumeGenerationService(
        provider=provider,
        settings=settings,
        embedding_backend=HashingEmbeddings(1024),
        compiler=_NoEngineCompiler(),
    )

    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def payload(profile: Resume) -> dict:
    return {
        "profile": json.loads(profile.model_dump_json()),
        "job_description": EXAMPLE_JOB_DESCRIPTION,
        "template": "classic",
    }


# ----------------------------------------------------------------------
# System endpoints
# ----------------------------------------------------------------------


def test_healthz_is_always_ok(client: TestClient) -> None:
    response = client.get("/healthz")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_readyz_reports_a_degraded_service_without_a_latex_engine(client: TestClient) -> None:
    body = client.get("/readyz").json()

    assert body["checks"]["llm_configured"] is True
    assert body["checks"]["artifact_dir_writable"] is True


def test_meta_describes_the_deployment(client: TestClient) -> None:
    body = client.get("/api/v1/meta").json()

    assert body["llm_configured"] is True
    assert {"classic", "treyHunner"} <= {item["name"] for item in body["templates"]}
    assert body["default_template"] == "treyHunner"
    assert body["limits"]["max_upload_bytes"] > 0


def test_the_published_profile_example_validates_against_the_published_schema(client: TestClient) -> None:
    example = client.get("/api/v1/profile/example").json()

    assert client.get("/api/v1/profile/schema").status_code == 200
    assert Resume.model_validate(example).profile.full_name


def test_the_ui_and_docs_are_served(client: TestClient) -> None:
    assert client.get("/").status_code == 200
    assert client.get("/docs").status_code == 200
    assert client.get("/openapi.json").status_code == 200


def test_every_response_carries_a_request_id(client: TestClient) -> None:
    assert client.get("/healthz").headers["x-request-id"]


# ----------------------------------------------------------------------
# Generation - JSON
# ----------------------------------------------------------------------


def test_generate_returns_a_tailored_resume(client: TestClient, payload: dict) -> None:
    response = client.post("/api/v1/generate", json=payload)

    assert response.status_code == 200, response.text
    body = response.json()

    assert body["template"] == "classic"
    assert body["latex"].lstrip().startswith("\\documentclass")
    assert body["resume"]["profile"]["full_name"] == "Ada Sharma"
    assert body["job_description"]["title"] == "Senior Backend Engineer"
    assert len(body["run_id"]) == 32


def test_the_response_includes_the_retrieval_report(client: TestClient, payload: dict) -> None:
    report = client.post("/api/v1/generate", json=payload).json()["report"]

    assert report["evidence_chunks"] > 0
    assert report["requirement_matches"]
    assert report["section_scores"][0]["score"] > 0
    assert set(report["coverage"]) >= {"covered", "partially_covered", "uncovered"}


def test_a_missing_pdf_is_reported_rather_than_failing_the_request(client: TestClient, payload: dict) -> None:
    body = client.post("/api/v1/generate", json=payload).json()

    assert body["pdf_available"] is False
    assert "No LaTeX engine" in body["pdf_unavailable_reason"]
    assert body["artifacts"]["pdf"] is None
    assert body["artifacts"]["latex"]


def test_the_report_and_latex_can_be_omitted(client: TestClient, payload: dict) -> None:
    body = client.post(
        "/api/v1/generate",
        json={**payload, "include_report": False, "include_latex": False},
    ).json()

    assert body["report"] is None
    assert body["latex"] is None


def test_an_unknown_template_is_a_400(client: TestClient, payload: dict) -> None:
    response = client.post("/api/v1/generate", json={**payload, "template": "nonexistent"})

    assert response.status_code == 400
    assert response.json()["error"] == "unknown_template"


def test_a_blank_job_description_is_rejected(client: TestClient, payload: dict) -> None:
    response = client.post("/api/v1/generate", json={**payload, "job_description": "   "})

    assert response.status_code == 422
    assert response.json()["error"] == "validation_error"


def test_an_oversized_job_description_is_rejected(client: TestClient, payload: dict) -> None:
    response = client.post("/api/v1/generate", json={**payload, "job_description": "x" * 40_000})

    assert response.status_code == 413
    assert response.json()["error"] == "payload_too_large"


def test_a_malformed_profile_is_rejected(client: TestClient) -> None:
    response = client.post(
        "/api/v1/generate",
        json={"profile": {"experience": "not-a-list"}, "job_description": "Backend engineer"},
    )

    assert response.status_code == 422


# ----------------------------------------------------------------------
# Generation - multipart
# ----------------------------------------------------------------------


def _profile_upload(profile: Resume) -> dict:
    return {"profile": ("profile.json", io.BytesIO(profile.model_dump_json().encode()), "application/json")}


def test_generate_from_an_uploaded_file(client: TestClient, profile: Resume) -> None:
    response = client.post(
        "/api/v1/generate/upload",
        files=_profile_upload(profile),
        data={"job_description": EXAMPLE_JOB_DESCRIPTION, "template": "classic"},
    )

    assert response.status_code == 200, response.text
    assert response.json()["resume"]["profile"]["full_name"] == "Ada Sharma"


def test_the_job_description_can_be_uploaded_as_a_file(client: TestClient, profile: Resume) -> None:
    files = _profile_upload(profile)
    files["job_description_file"] = ("jd.txt", io.BytesIO(EXAMPLE_JOB_DESCRIPTION.encode()), "text/plain")

    response = client.post("/api/v1/generate/upload", files=files, data={"template": "classic"})

    assert response.status_code == 200, response.text


def test_an_upload_without_any_job_description_is_rejected(client: TestClient, profile: Resume) -> None:
    response = client.post("/api/v1/generate/upload", files=_profile_upload(profile), data={"template": "classic"})

    assert response.status_code == 422
    assert response.json()["error"] == "invalid_profile"


def test_a_profile_that_is_not_json_is_rejected(client: TestClient) -> None:
    response = client.post(
        "/api/v1/generate/upload",
        files={"profile": ("profile.json", io.BytesIO(b"not json at all"), "application/json")},
        data={"job_description": EXAMPLE_JOB_DESCRIPTION},
    )

    assert response.status_code == 422
    assert "not valid JSON" in response.json()["detail"]


def test_an_empty_profile_upload_is_rejected(client: TestClient) -> None:
    response = client.post(
        "/api/v1/generate/upload",
        files={"profile": ("profile.json", io.BytesIO(b""), "application/json")},
        data={"job_description": EXAMPLE_JOB_DESCRIPTION},
    )

    assert response.status_code == 422


def test_an_oversized_upload_is_rejected(client: TestClient, settings: Settings) -> None:
    oversized = b"x" * (settings.max_upload_bytes + 1024)

    response = client.post(
        "/api/v1/generate/upload",
        files={"profile": ("profile.json", io.BytesIO(oversized), "application/json")},
        data={"job_description": EXAMPLE_JOB_DESCRIPTION},
    )

    assert response.status_code == 413


# ----------------------------------------------------------------------
# Artifacts
# ----------------------------------------------------------------------


def test_artifacts_are_downloadable_after_a_run(client: TestClient, payload: dict) -> None:
    body = client.post("/api/v1/generate", json=payload).json()

    latex = client.get(body["artifacts"]["latex"])
    resume_json = client.get(body["artifacts"]["resume_json"])

    assert latex.status_code == 200
    assert latex.text.lstrip().startswith("\\documentclass")
    assert resume_json.json()["profile"]["full_name"] == "Ada Sharma"


def test_artifacts_are_not_cached_by_intermediaries(client: TestClient, payload: dict) -> None:
    body = client.post("/api/v1/generate", json=payload).json()

    assert client.get(body["artifacts"]["latex"]).headers["cache-control"] == "no-store"


def test_an_unknown_run_is_a_404(client: TestClient) -> None:
    response = client.get(f"/api/v1/runs/{'0' * 32}/resume.tex")

    assert response.status_code == 404
    assert response.json()["error"] == "artifact_not_found"


@pytest.mark.parametrize("artifact", ["..%2F..%2Fetc%2Fpasswd", "....//etc/passwd"])
def test_path_traversal_on_download_is_refused(client: TestClient, artifact: str) -> None:
    response = client.get(f"/api/v1/runs/{'0' * 32}/{artifact}")

    assert response.status_code == 404


# ----------------------------------------------------------------------
# Rate limiting
# ----------------------------------------------------------------------


def test_requests_beyond_the_limit_are_rejected_with_retry_after(
    settings: Settings,
    provider: FakeProvider,
    payload: dict,
) -> None:
    limited = settings.model_copy(update={"rate_limit_requests": 2, "rate_limit_window_seconds": 60})
    app = create_app(limited)
    app.state.careerx._service = ResumeGenerationService(
        provider=provider,
        settings=limited,
        embedding_backend=HashingEmbeddings(512),
        compiler=_NoEngineCompiler(),
    )

    with TestClient(app) as test_client:
        assert test_client.post("/api/v1/generate", json=payload).status_code == 200
        assert test_client.post("/api/v1/generate", json=payload).status_code == 200

        blocked = test_client.post("/api/v1/generate", json=payload)

    assert blocked.status_code == 429
    assert blocked.json()["error"] == "rate_limited"
    assert int(blocked.headers["retry-after"]) > 0


def test_system_endpoints_are_not_rate_limited(client: TestClient) -> None:
    for _ in range(30):
        assert client.get("/healthz").status_code == 200


# ----------------------------------------------------------------------
# End to end, with a real LaTeX engine when one is installed
# ----------------------------------------------------------------------


@pytest.mark.skipif(detect_engine() is None, reason="No LaTeX engine installed.")
@pytest.mark.parametrize("template", ["classic", "treyHunner"])
def test_a_full_run_returns_a_downloadable_pdf(
    settings: Settings,
    provider: FakeProvider,
    profile: Resume,
    template: str,
) -> None:
    app = create_app(settings)
    app.state.careerx._service = ResumeGenerationService(
        provider=provider,
        settings=settings,
        embedding_backend=HashingEmbeddings(1024),
    )

    with TestClient(app) as test_client:
        body = test_client.post(
            "/api/v1/generate",
            json={
                "profile": json.loads(profile.model_dump_json()),
                "job_description": EXAMPLE_JOB_DESCRIPTION,
                "template": template,
            },
        ).json()

        assert body["pdf_available"] is True, body.get("pdf_unavailable_reason")

        pdf = test_client.get(body["artifacts"]["pdf"])

    assert pdf.status_code == 200
    assert pdf.headers["content-type"] == "application/pdf"
    assert pdf.content.startswith(b"%PDF-")
