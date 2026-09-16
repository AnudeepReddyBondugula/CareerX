"""The end-to-end resume tailoring pipeline.

    profile + posting
        -> parse posting into structure
        -> chunk profile into evidence, embed, index (FAISS)
        -> retrieve evidence per requirement, score sections, compute coverage
        -> generate a tailored resume grounded in that evidence
        -> verify nothing was invented
        -> render LaTeX
        -> compile PDF

Every stage is injectable so the pipeline can be tested without a network.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field

from careerx.ai.providers.base import LLMProvider
from careerx.builders import JobDescriptionParser, ResumeBuilder
from careerx.config.settings import Settings, get_settings
from careerx.latex.compiler import LatexCompilationError, LatexCompiler, LatexEngineUnavailable
from careerx.models import JobDescription, Resume, TailoringReport
from careerx.rag.embeddings import EmbeddingBackend, build_embedding_backend
from careerx.rag.retriever import EvidenceRetriever
from careerx.renderers import ResumeRenderer
from careerx.services.grounding import GroundingValidator

logger = logging.getLogger(__name__)


@dataclass
class GenerationResult:
    """Everything one tailoring run produced."""

    resume: Resume
    job_description: JobDescription
    report: TailoringReport
    latex: str
    template: str
    pdf_bytes: bytes | None = None
    pdf_unavailable_reason: str | None = None
    compile_log: str = ""
    timings_ms: dict[str, int] = field(default_factory=dict)

    @property
    def pdf_available(self) -> bool:
        return self.pdf_bytes is not None


class ResumeGenerationService:
    """Coordinates parsing, retrieval, generation, rendering and compilation."""

    def __init__(
        self,
        *,
        provider: LLMProvider,
        settings: Settings | None = None,
        embedding_backend: EmbeddingBackend | None = None,
        renderer: ResumeRenderer | None = None,
        compiler: LatexCompiler | None = None,
    ) -> None:
        self._settings = settings or get_settings()
        self._provider = provider
        self._parser = JobDescriptionParser(provider)
        self._builder = ResumeBuilder(provider)
        self._embeddings = embedding_backend or build_embedding_backend(self._settings, provider)
        self._retriever = EvidenceRetriever(self._embeddings, self._settings)
        self._renderer = renderer or ResumeRenderer()
        self._compiler = compiler or LatexCompiler(
            engine=self._settings.latex_engine,
            timeout_seconds=self._settings.latex_timeout_seconds,
            assets_dir=self._renderer.assets_dir,
        )

    @property
    def provider(self) -> LLMProvider:
        return self._provider

    @property
    def renderer(self) -> ResumeRenderer:
        return self._renderer

    @property
    def compiler(self) -> LatexCompiler:
        return self._compiler

    @property
    def embedding_backend_name(self) -> str:
        return self._embeddings.name

    def generate(
        self,
        *,
        profile: Resume,
        job_description_text: str,
        template: str | None = None,
        compile_pdf: bool = True,
    ) -> GenerationResult:
        template = template or self._settings.default_template
        timings: dict[str, int] = {}

        with _timed(timings, "parse_job_description"):
            job_description = self._parser.parse(job_description_text)

        with _timed(timings, "retrieve_evidence"):
            retrieval = self._retriever.retrieve(profile, job_description)

        with _timed(timings, "generate_resume"):
            generated = self._builder.build(
                resume=profile,
                job_description=job_description,
                retrieval=retrieval,
            )

        with _timed(timings, "verify_grounding"):
            tailored, issues = GroundingValidator(
                profile,
                strict=self._settings.strict_grounding,
            ).validate(generated)

        report = TailoringReport(
            provider=self._provider.name,
            model=self._provider.chat_model,
            embedding_backend=self._embeddings.name,
            evidence_chunks=len(retrieval.chunks),
            requirement_matches=retrieval.requirement_matches,
            section_scores=retrieval.section_scores,
            coverage=retrieval.coverage,
            grounding_issues=issues,
        )

        with _timed(timings, "render_latex"):
            latex = self._renderer.render(resume=tailored, template=template)

        result = GenerationResult(
            resume=tailored,
            job_description=job_description,
            report=report,
            latex=latex,
            template=template,
            timings_ms=timings,
        )

        if compile_pdf:
            with _timed(timings, "compile_pdf"):
                self._compile(result)

        logger.info("Tailoring run complete: %s", timings)

        return result

    def _compile(self, result: GenerationResult) -> None:
        """Attach a PDF, or a reason why there isn't one.

        A missing TeX engine is not an error: the caller still gets valid
        LaTeX source it can compile elsewhere, so the run degrades rather than
        fails.
        """
        try:
            compiled = self._compiler.compile(result.latex, job_name="resume")
        except LatexEngineUnavailable as exc:
            logger.warning("Skipping PDF compilation: %s", exc)
            result.pdf_unavailable_reason = str(exc)
        except LatexCompilationError as exc:
            logger.error("PDF compilation failed: %s", exc)
            result.pdf_unavailable_reason = str(exc)
            result.compile_log = exc.log
        else:
            result.pdf_bytes = compiled.pdf_bytes
            result.compile_log = compiled.log


class _timed:
    """Context manager recording elapsed milliseconds into ``store``."""

    __slots__ = ("_label", "_start", "_store")

    def __init__(self, store: dict[str, int], label: str) -> None:
        self._store = store
        self._label = label
        self._start = 0.0

    def __enter__(self) -> None:
        self._start = time.perf_counter()

    def __exit__(self, *exc_info: object) -> None:
        self._store[self._label] = int((time.perf_counter() - self._start) * 1000)
