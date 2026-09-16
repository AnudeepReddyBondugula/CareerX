from pathlib import Path

import pytest

from careerx.latex.compiler import (
    LatexCompilationError,
    LatexCompiler,
    LatexEngineUnavailable,
    detect_engine,
)
from careerx.models import Resume
from careerx.renderers import ResumeRenderer

engine_required = pytest.mark.skipif(
    detect_engine() is None,
    reason="No LaTeX engine installed; PDF compilation cannot be exercised here.",
)


def test_a_missing_engine_raises_a_distinguishable_error(monkeypatch: pytest.MonkeyPatch) -> None:
    compiler = LatexCompiler(engine="definitely-not-a-real-engine")
    monkeypatch.setattr("careerx.latex.compiler.available_engines", lambda preferred=None: ())
    monkeypatch.setattr("careerx.latex.compiler.detect_engine", lambda preferred=None: None)

    assert not compiler.available

    with pytest.raises(LatexEngineUnavailable, match="tectonic"):
        compiler.compile(r"\documentclass{article}\begin{document}x\end{document}")


@engine_required
@pytest.mark.parametrize("template", ["classic", "treyHunner"])
def test_a_rendered_resume_compiles_to_a_pdf(profile: Resume, template: str) -> None:
    renderer = ResumeRenderer()
    compiler = LatexCompiler(assets_dir=renderer.assets_dir, timeout_seconds=300)

    result = compiler.compile(renderer.render(resume=profile, template=template), job_name="resume")

    assert result.pdf_bytes.startswith(b"%PDF-")
    assert len(result.pdf_bytes) > 1000


@engine_required
def test_special_characters_survive_the_full_render_and_compile_path() -> None:
    from careerx.models import CandidateProfile, Experience

    renderer = ResumeRenderer()
    compiler = LatexCompiler(assets_dir=renderer.assets_dir, timeout_seconds=300)

    resume = Resume(
        profile=CandidateProfile(full_name="R&D Lead #1 (100%)"),
        experience=[Experience(company="AT&T", title="Eng", achievements=[r"Cut cost_per_unit by 30% \o/"])],
    )

    result = compiler.compile(renderer.render(resume=resume, template="classic"))

    assert result.pdf_bytes.startswith(b"%PDF-")


@engine_required
def test_invalid_latex_reports_a_compilation_error_with_a_log() -> None:
    compiler = LatexCompiler(timeout_seconds=120)

    with pytest.raises(LatexCompilationError) as excinfo:
        compiler.compile(r"\documentclass{article}\begin{document}\undefinedmacro\end{document}")

    assert excinfo.value.log


@engine_required
def test_assets_are_staged_next_to_the_source(tmp_path: Path) -> None:
    assets = tmp_path / "assets"
    assets.mkdir()
    (assets / "careerxtest.sty").write_text(r"\ProvidesPackage{careerxtest}", encoding="utf-8")

    compiler = LatexCompiler(assets_dir=assets, timeout_seconds=120)

    result = compiler.compile(
        r"\documentclass{article}\usepackage{careerxtest}\begin{document}ok\end{document}",
    )

    assert result.pdf_bytes.startswith(b"%PDF-")
