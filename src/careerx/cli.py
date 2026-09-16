"""CareerX command-line interface."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.table import Table

from careerx import __version__
from careerx.config.logging import setup_logging
from careerx.config.settings import get_settings

app = typer.Typer(
    name="careerx",
    help="AI-powered, RAG-grounded ATS resume builder.",
    add_completion=False,
    no_args_is_help=True,
)
console = Console()


@app.command()
def generate(
    job_description: Annotated[
        Path,
        typer.Option("--job", "-j", exists=True, dir_okay=False, readable=True, help="Job description file."),
    ],
    profile: Annotated[
        Path,
        typer.Option("--profile", "-p", exists=True, dir_okay=False, readable=True, help="Profile JSON file."),
    ] = Path("profile.json"),
    output: Annotated[
        Path,
        typer.Option("--output", "-o", file_okay=False, help="Output directory."),
    ] = Path("output"),
    template: Annotated[str | None, typer.Option("--template", "-t", help="Template name.")] = None,
    no_pdf: Annotated[bool, typer.Option("--no-pdf", help="Render LaTeX only, skip PDF compilation.")] = False,
) -> None:
    """Generate a tailored resume from a profile and a job description."""
    settings = get_settings()
    setup_logging(settings.log_level, settings.log_format)

    from careerx.ai.providers.factory import build_provider
    from careerx.services.generation_service import ResumeGenerationService
    from careerx.services.profile_service import ProfileService

    candidate = ProfileService(profile).load_profile()
    posting = job_description.read_text(encoding="utf-8")

    with console.status("Retrieving evidence and generating resume..."):
        service = ResumeGenerationService(provider=build_provider(settings), settings=settings)
        result = service.generate(
            profile=candidate,
            job_description_text=posting,
            template=template,
            compile_pdf=not no_pdf,
        )

    output.mkdir(parents=True, exist_ok=True)

    (output / "resume.tex").write_text(result.latex, encoding="utf-8")
    (output / "resume.json").write_text(result.resume.model_dump_json(indent=2), encoding="utf-8")
    (output / "report.json").write_text(result.report.model_dump_json(indent=2), encoding="utf-8")

    written = ["resume.tex", "resume.json", "report.json"]

    if result.pdf_bytes is not None:
        (output / "resume.pdf").write_bytes(result.pdf_bytes)
        written.append("resume.pdf")

    _print_summary(result)

    console.print(f"\n[green]Wrote[/green] {', '.join(written)} to [bold]{output}[/bold]")

    if result.pdf_unavailable_reason:
        console.print(f"[yellow]No PDF:[/yellow] {result.pdf_unavailable_reason}")


@app.command()
def serve(
    host: Annotated[str | None, typer.Option("--host", help="Bind address.")] = None,
    port: Annotated[int | None, typer.Option("--port", help="Bind port.")] = None,
    reload: Annotated[bool, typer.Option("--reload", help="Reload on code changes (development only).")] = False,
) -> None:
    """Run the CareerX web application."""
    import uvicorn

    settings = get_settings()

    uvicorn.run(
        "careerx.api.app:app",
        host=host or settings.host,
        port=port or settings.port,
        reload=reload,
        log_config=None,
    )


@app.command()
def doctor() -> None:
    """Report whether this machine can run the full pipeline."""
    from careerx.ai.providers.base import ProviderNotConfigured
    from careerx.latex.compiler import detect_engine
    from careerx.renderers import ResumeRenderer

    settings = get_settings()
    table = Table(title=f"CareerX {__version__}")
    table.add_column("Check")
    table.add_column("Status")

    table.add_row("LLM provider", settings.llm_provider)

    try:
        from careerx.ai.providers.factory import build_provider

        provider = build_provider(settings)
        table.add_row("API key", f"[green]configured[/green] ({provider.chat_model})")
    except ProviderNotConfigured as exc:
        provider = None
        table.add_row("API key", f"[red]missing[/red] - {exc}")

    from careerx.rag.embeddings import build_embedding_backend

    table.add_row("Embeddings", build_embedding_backend(settings, provider).name)

    engine = detect_engine(settings.latex_engine)
    table.add_row(
        "LaTeX engine",
        f"[green]{engine}[/green]" if engine else "[yellow]not found - .tex only[/yellow]",
    )
    table.add_row("Templates", ", ".join(ResumeRenderer().available_templates()))

    console.print(table)


@app.command("example-profile")
def example_profile_command(
    output: Annotated[Path, typer.Option("--output", "-o", help="Where to write the example.")] = Path("profile.json"),
) -> None:
    """Write an example profile.json to start from."""
    from careerx.examples import example_profile

    if output.exists():
        typer.confirm(f"{output} exists. Overwrite?", abort=True)

    output.write_text(example_profile().model_dump_json(indent=2), encoding="utf-8")
    console.print(f"[green]Wrote[/green] example profile to [bold]{output}[/bold]")


@app.command("profile-schema")
def profile_schema_command() -> None:
    """Print the JSON Schema a profile must satisfy."""
    from careerx.models import Resume

    console.print_json(json.dumps(Resume.model_json_schema()))


@app.command()
def version() -> None:
    """Print the CareerX version."""
    console.print(__version__)


def _print_summary(result: object) -> None:
    from careerx.services.generation_service import GenerationResult

    assert isinstance(result, GenerationResult)

    coverage = result.report.coverage

    table = Table(title=f"Tailored for: {result.job_description.title or 'unspecified role'}")
    table.add_column("Metric")
    table.add_column("Value")

    table.add_row("Provider", f"{result.report.provider} / {result.report.model}")
    table.add_row("Embeddings", result.report.embedding_backend)
    table.add_row("Evidence chunks", str(result.report.evidence_chunks))
    table.add_row("Requirement coverage", f"{coverage.coverage_ratio:.0%}")
    table.add_row("Well supported", str(len(coverage.covered)))
    table.add_row("Partially supported", str(len(coverage.partially_covered)))
    table.add_row("Gaps (not claimed)", str(len(coverage.uncovered)))
    table.add_row(
        "Ungrounded items removed",
        f"[yellow]{len(result.report.grounding_issues)}[/yellow]" if result.report.grounding_issues else "0",
    )

    console.print(table)

    if result.report.section_scores:
        ranking = Table(title="Most relevant profile sections")
        ranking.add_column("Section")
        ranking.add_column("Kind")
        ranking.add_column("Score", justify="right")
        ranking.add_column("Matches", justify="right")

        for item in result.report.section_scores[:8]:
            ranking.add_row(
                item.label or item.section_id,
                item.kind.value,
                f"{item.score:.2f}",
                str(len(item.matched_requirements)),
            )

        console.print(ranking)


def main() -> None:
    app()


if __name__ == "__main__":
    main()
