import pytest

from careerx.config.settings import Settings
from careerx.latex.compiler import LatexCompiler, LatexEngineUnavailable
from careerx.models import Experience, JobDescription, Resume, Skill
from careerx.rag.embeddings import HashingEmbeddings
from careerx.services.generation_service import ResumeGenerationService
from careerx.services.grounding import GroundingError

from .conftest import FakeProvider


def build_service(
    provider: FakeProvider,
    settings: Settings,
    *,
    compiler: LatexCompiler | None = None,
) -> ResumeGenerationService:
    return ResumeGenerationService(
        provider=provider,
        settings=settings,
        embedding_backend=HashingEmbeddings(1024),
        compiler=compiler or _NoEngineCompiler(),
    )


class _NoEngineCompiler(LatexCompiler):
    """Stands in for a machine with no TeX installation."""

    def compile(self, latex_source: str, *, job_name: str = "resume") -> object:
        raise LatexEngineUnavailable("No LaTeX engine found.")


def test_the_pipeline_produces_latex_and_a_report(
    provider: FakeProvider,
    settings: Settings,
    profile: Resume,
    job_description_text: str,
) -> None:
    result = build_service(provider, settings).generate(
        profile=profile,
        job_description_text=job_description_text,
        template="classic",
    )

    assert result.latex.lstrip().startswith("\\documentclass")
    assert result.template == "classic"
    assert result.report.provider == "fake"
    assert result.report.evidence_chunks > 0
    assert result.report.requirement_matches
    assert result.report.section_scores


def test_the_retrieved_evidence_reaches_the_generation_prompt(
    provider: FakeProvider,
    settings: Settings,
    profile: Resume,
    job_description_text: str,
) -> None:
    build_service(provider, settings).generate(
        profile=profile,
        job_description_text=job_description_text,
        template="classic",
    )

    # First prompt parses the posting; the second generates the resume.
    generation_prompt = provider.prompts[1]

    assert "## RETRIEVED EVIDENCE" in generation_prompt
    assert "## SECTION RANKING" in generation_prompt
    assert "not_supported_do_not_claim" in generation_prompt
    assert "Northwind Payments" in generation_prompt


def test_timings_are_recorded_for_each_stage(
    provider: FakeProvider,
    settings: Settings,
    profile: Resume,
    job_description_text: str,
) -> None:
    result = build_service(provider, settings).generate(
        profile=profile,
        job_description_text=job_description_text,
        template="classic",
    )

    assert {"parse_job_description", "retrieve_evidence", "generate_resume", "render_latex"} <= set(result.timings_ms)


def test_a_missing_latex_engine_degrades_instead_of_failing(
    provider: FakeProvider,
    settings: Settings,
    profile: Resume,
    job_description_text: str,
) -> None:
    result = build_service(provider, settings).generate(
        profile=profile,
        job_description_text=job_description_text,
        template="classic",
    )

    assert result.pdf_bytes is None
    assert not result.pdf_available
    assert "No LaTeX engine" in (result.pdf_unavailable_reason or "")
    assert result.latex  # the caller still gets usable source


def test_hallucinated_content_is_stripped_before_rendering(
    settings: Settings,
    profile: Resume,
    parsed_job_description: JobDescription,
    job_description_text: str,
) -> None:
    fabricated = profile.model_copy(deep=True)
    fabricated.experience.append(
        Experience(company="Globex", title="VP Engineering", achievements=["Ran a 500-person org"])
    )
    fabricated.skills.append(Skill(name="Kubernetes", category="Cloud"))

    provider = FakeProvider(job_description=parsed_job_description, resume=fabricated)

    result = build_service(provider, settings).generate(
        profile=profile,
        job_description_text=job_description_text,
        template="classic",
    )

    assert "Globex" not in result.latex
    assert "Kubernetes" not in result.latex
    assert {issue.kind for issue in result.report.grounding_issues} == {"unknown_company", "unknown_skill"}


def test_strict_mode_fails_the_run_instead_of_repairing(
    settings: Settings,
    profile: Resume,
    parsed_job_description: JobDescription,
    job_description_text: str,
) -> None:
    fabricated = profile.model_copy(deep=True)
    fabricated.skills.append(Skill(name="Kubernetes", category="Cloud"))

    strict = settings.model_copy(update={"strict_grounding": True})
    provider = FakeProvider(job_description=parsed_job_description, resume=fabricated)

    with pytest.raises(GroundingError):
        build_service(provider, strict).generate(
            profile=profile,
            job_description_text=job_description_text,
            template="classic",
        )


def test_compile_can_be_skipped(
    provider: FakeProvider,
    settings: Settings,
    profile: Resume,
    job_description_text: str,
) -> None:
    result = build_service(provider, settings).generate(
        profile=profile,
        job_description_text=job_description_text,
        template="classic",
        compile_pdf=False,
    )

    assert result.pdf_unavailable_reason is None
    assert "compile_pdf" not in result.timings_ms


def test_an_empty_job_description_is_rejected(
    provider: FakeProvider,
    settings: Settings,
    profile: Resume,
) -> None:
    with pytest.raises(ValueError, match="empty"):
        build_service(provider, settings).generate(profile=profile, job_description_text="   ")


def test_the_default_template_is_used_when_none_is_given(
    provider: FakeProvider,
    settings: Settings,
    profile: Resume,
    job_description_text: str,
) -> None:
    result = build_service(provider, settings).generate(
        profile=profile,
        job_description_text=job_description_text,
    )

    assert result.template == settings.default_template
