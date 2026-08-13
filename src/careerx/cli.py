"""CareerX CLI."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

app = typer.Typer(
    name="careerx",
    help="AI-powered ATS Resume Builder.",
    add_completion=False,
)


@app.command()
def generate(
    job_description: Annotated[
        Path,
        typer.Option(
            "--job",
            "-j",
            exists=True,
            file_okay=True,
            dir_okay=False,
            readable=True,
            help="Path to the Job Description.",
        ),
    ],
    output: Annotated[
        Path,
        typer.Option(
            "--output",
            "-o",
            help="Output PDF path.",
        ),
    ],
    profile: Annotated[
        Path,
        typer.Option(
            "--profile",
            "-p",
            exists=True,
            file_okay=True,
            dir_okay=False,
            help="Candidate profile JSON.",
        ),
    ] = Path("profile.json"),
    resume_json: Annotated[
        Path | None,
        typer.Option(
            "--resume-json",
            "-r",
            help="Write AI-tailored Resume JSON.",
        ),
    ] = None,
    latex_output: Annotated[
        Path | None,
        typer.Option(
            "--latex",
            "-t",
            help="Directory to write generated .tex/.cls files.",
        ),
    ] = None,
    theme: Annotated[
        str,
        typer.Option(
            "--theme",
            help="Resume template.",
        ),
    ] = "modern",
) -> None:
    """
    Generate an ATS-optimized resume.
    """

    typer.echo("Loading profile...")

    # ------------------------------------------------------------------
    # Module 3
    # ------------------------------------------------------------------

    from careerx.services.profile_service import ProfileService

    profile_service = ProfileService(profile)
    resume = profile_service.load_profile()

    typer.echo("Profile loaded.")

    # ------------------------------------------------------------------
    # Module 5
    # ------------------------------------------------------------------

    typer.echo("Reading Job Description...")

    jd_text = job_description.read_text(encoding="utf-8")

    from careerx.builders import JobDescriptionParser

    parser = JobDescriptionParser()

    job = parser.parse(jd_text)

    typer.echo("Job Description parsed.")

    # ------------------------------------------------------------------
    # Module 6
    # ------------------------------------------------------------------

    typer.echo("Generating tailored resume...")

    from careerx.builders import ResumeBuilder

    builder = ResumeBuilder()

    tailored_resume = builder.build(
        resume=resume,
        job_description=job,
    )

    typer.echo("Resume generated.")

    # ------------------------------------------------------------------
    # Optional Resume JSON
    # ------------------------------------------------------------------
    try:    
        if resume_json is not None:
            resume_json.parent.mkdir(parents=True, exist_ok=True)

            resume_json.write_text(
                tailored_resume.model_dump_json(indent=4),
                encoding="utf-8",
            )

            typer.echo(f"Resume JSON written to {resume_json}")
    except Exception as e:
        typer.secho(
            f"Failed to write Resume JSON: {e}",
            fg=typer.colors.RED,
        )
        typer.echo("Continuing with PDF generation...")

    # ------------------------------------------------------------------
    # Module 8
    # ------------------------------------------------------------------

    tex_path: Path | None = None

    if latex_output is not None:
        latex_output.mkdir(parents=True, exist_ok=True)

        tex_path = latex_output / "resume.tex"

        from careerx.renderers import ResumeRenderer

        renderer = ResumeRenderer(template_dir=Path("src/careerx/templates"))

        renderer.render(resume=tailored_resume, output_path=tex_path, template_name=f"{theme}.tex.j2")

        typer.echo(f"LaTeX written to {tex_path}")

    # ------------------------------------------------------------------
    # Module 9
    # ------------------------------------------------------------------

    typer.echo("Generating PDF...")

    from careerx.renderers import PDFRenderer

    pdf = PDFRenderer(theme=theme)

    pdf.compile(
        resume=tailored_resume,
        output_path=output,
    )

    typer.secho(
        f"PDF generated successfully: {output}",
        fg=typer.colors.GREEN,
    )


@app.command()
def version() -> None:
    """Display CareerX version."""

    from careerx import __version__

    typer.echo(f"CareerX {__version__}")


def main() -> None:
    """CLI entrypoint."""

    app()


if __name__ == "__main__":
    main()