"""Compile LaTeX to PDF.

The engine of choice is Tectonic: a single self-contained binary that fetches
only the packages a document actually uses and caches them, instead of the
multi-gigabyte TeX Live install a resume with `fontawesome5` would otherwise
need. A `pdflatex`/`latexmk` path is kept for machines that already have a full
distribution.

When no engine is present at all, compilation raises
:class:`LatexEngineUnavailable` rather than a generic failure, so callers can
still return the generated ``.tex`` instead of failing the whole request.
"""

from __future__ import annotations

import logging
import shutil
import subprocess  # noqa: S404 - invoking a local TeX engine is the point
import tempfile
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

logger = logging.getLogger(__name__)

TECTONIC = "tectonic"
PDFLATEX = "pdflatex"

_SUPPORTED_ENGINES = (TECTONIC, PDFLATEX)

# LaTeX writes its real diagnostics to stdout; keep only the tail so a failure
# response stays readable and cannot leak an unbounded amount of log.
_MAX_LOG_CHARS = 4000


class LatexError(RuntimeError):
    """Base class for LaTeX compilation problems."""


class LatexEngineUnavailable(LatexError):
    """No LaTeX engine is installed on this machine."""


class LatexCompilationError(LatexError):
    """The engine ran but did not produce a PDF."""

    def __init__(self, message: str, *, log: str = "") -> None:
        super().__init__(message)
        self.log = log


@dataclass(frozen=True)
class CompilationResult:
    pdf_bytes: bytes
    engine: str
    log: str


@lru_cache(maxsize=1)
def available_engines(preferred: str | None = None) -> tuple[str, ...]:
    """Every installed engine, most preferred first.

    Cached because it shells out to ``which`` and the answer cannot change
    within a process.
    """
    ordered: list[str] = []

    for candidate in (preferred, *_SUPPORTED_ENGINES):
        if candidate and candidate not in ordered and shutil.which(candidate):
            ordered.append(candidate)

    return tuple(ordered)


def detect_engine(preferred: str | None = None) -> str | None:
    """Return the name of the engine that would be used, or ``None``."""
    engines = available_engines(preferred)
    return engines[0] if engines else None


class LatexCompiler:
    """Compiles LaTeX source to PDF bytes in an isolated temporary directory."""

    def __init__(
        self,
        *,
        engine: str | None = None,
        timeout_seconds: float = 120.0,
        assets_dir: Path | None = None,
    ) -> None:
        self._preferred_engine = engine
        self._timeout_seconds = timeout_seconds
        self._assets_dir = assets_dir

    @property
    def engine(self) -> str | None:
        return detect_engine(self._preferred_engine)

    @property
    def engines(self) -> tuple[str, ...]:
        return available_engines(self._preferred_engine)

    @property
    def available(self) -> bool:
        return self.engine is not None

    def compile(self, latex_source: str, *, job_name: str = "resume") -> CompilationResult:
        """Compile ``latex_source`` and return the resulting PDF bytes.

        Raises:
            LatexEngineUnavailable: if no engine is installed.
            LatexCompilationError: if the engine produced no PDF.
        """
        engines = self.engines
        if not engines:
            raise LatexEngineUnavailable(
                "No LaTeX engine found. Install `tectonic` (recommended) or a TeX distribution providing `pdflatex`."
            )

        failure: LatexCompilationError | None = None

        # An engine can be installed yet unusable - most commonly Tectonic on a
        # host that cannot reach its package bundle. Rather than fail the
        # request, try the next engine before giving up.
        for engine in engines:
            try:
                return self._compile_with(engine, latex_source, job_name=job_name)
            except LatexCompilationError as exc:
                logger.warning("Compilation with %s failed: %s", engine, exc)
                failure = failure or exc

        assert failure is not None
        raise failure

    def _compile_with(self, engine: str, latex_source: str, *, job_name: str) -> CompilationResult:
        with tempfile.TemporaryDirectory(prefix="careerx-latex-") as raw_workdir:
            workdir = Path(raw_workdir)
            self._stage_assets(workdir)

            tex_path = workdir / f"{job_name}.tex"
            tex_path.write_text(latex_source, encoding="utf-8")

            log = self._run(engine, tex_path, workdir)

            pdf_path = workdir / f"{job_name}.pdf"
            if not pdf_path.exists():
                raise LatexCompilationError(
                    f"{engine} exited without producing a PDF.",
                    log=log[-_MAX_LOG_CHARS:],
                )

            return CompilationResult(pdf_bytes=pdf_path.read_bytes(), engine=engine, log=log[-_MAX_LOG_CHARS:])

    def _stage_assets(self, workdir: Path) -> None:
        """Copy template assets (``.cls``, ``.sty``) next to the source file."""
        if self._assets_dir is None or not self._assets_dir.is_dir():
            return

        for asset in self._assets_dir.iterdir():
            if asset.is_file() and asset.suffix in {".cls", ".sty", ".tex"}:
                shutil.copy2(asset, workdir / asset.name)

    def _run(self, engine: str, tex_path: Path, workdir: Path) -> str:
        if engine == TECTONIC:
            commands = [
                [
                    engine,
                    "--outdir",
                    str(workdir),
                    "--chatter",
                    "minimal",
                    "--keep-logs",
                    str(tex_path),
                ]
            ]
        else:
            # pdflatex needs two passes to settle references and page layout.
            commands = [
                [
                    engine,
                    "-interaction=nonstopmode",
                    "-halt-on-error",
                    "-no-shell-escape",
                    f"-output-directory={workdir}",
                    str(tex_path),
                ]
            ] * 2

        output: list[str] = []

        for index, command in enumerate(commands, start=1):
            logger.info("Running %s (pass %s/%s).", engine, index, len(commands))

            try:
                completed = subprocess.run(  # noqa: S603 - fixed argv, no shell
                    command,
                    cwd=workdir,
                    capture_output=True,
                    text=True,
                    check=False,
                    timeout=self._timeout_seconds,
                )
            except subprocess.TimeoutExpired as exc:
                raise LatexCompilationError(
                    f"{engine} timed out after {self._timeout_seconds:g}s.",
                    log="".join(output)[-_MAX_LOG_CHARS:],
                ) from exc

            output.append(completed.stdout or "")
            output.append(completed.stderr or "")

            if completed.returncode != 0:
                logger.warning("%s exited with code %s.", engine, completed.returncode)
                break

        return "".join(output)
