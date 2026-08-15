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
            exists=True,
            file_okay=False,
            dir_okay=True,
            writable=True,
            help="Output Directory for generated files.",
        ),
    ],
    theme: Annotated[
        str,
        typer.Option(
            "--theme",
            help="Resume template.",
        ),
    ] = "treyHunner",
) -> None:
    """
    Generate an ATS-optimized resume.
    """

    output.mkdir(parents=True, exist_ok=True)

    typer.echo("Loading profile...")

    # ------------------------------------------------------------------
    # Module 3
    # ------------------------------------------------------------------

    from careerx.services.profile_service import ProfileService

    profile_service = ProfileService()
    resume = profile_service.load_profile()

    typer.echo("Profile loaded.")

    # ------------------------------------------------------------------
    # Module 5
    # ------------------------------------------------------------------

    typer.echo("Reading Job Description...")

    jd_text = job_description.read_text(encoding="utf-8")

    from careerx.builders.job_description_parser import JobDescriptionParser

    parser = JobDescriptionParser()

    job = parser.parse(jd_text)

    typer.echo("Job Description parsed.")

    # ------------------------------------------------------------------
    # Module 6
    # ------------------------------------------------------------------

    typer.echo("Generating tailored resume...")

    from careerx.builders.resume_builder import ResumeBuilder

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
        resume_json: Path = output / "tailored_resume.json"

        resume_json.parent.mkdir(parents=True, exist_ok=True)

        resume_json.write_text(
            tailored_resume.model_dump_json(indent=4),
            encoding="utf-8",
        )

        typer.echo(f"Tailored Resume JSON written to {resume_json}")
    except Exception as e:
        typer.secho(
            f"Failed to write Resume JSON: {e}",
            fg=typer.colors.RED,
        )
        typer.echo("Continuing with PDF generation...")

    # ------------------------------------------------------------------
    # Module 8
    # ------------------------------------------------------------------

    tex_path = output / "tailored_resume.tex"

    from careerx.renderers import ResumeRenderer

    renderer = ResumeRenderer(template_dir=Path("src/careerx/templates"))

    renderer.render(resume=tailored_resume, output_path=tex_path, template_name=f"{theme}.tex.j2")

    typer.echo(f"LaTeX written to {tex_path}")

    # ------------------------------------------------------------------
    # Module 9
    # ------------------------------------------------------------------

    typer.echo("Generating PDF...")

    from careerx.utils import PDFGenerator

    pdf = PDFGenerator()

    pdf.generate(
        tex_file=tex_path,
        output_dir=output,
    )

    typer.secho(
        f"PDF generated successfully: {output}",
        fg=typer.colors.GREEN,
    )


@app.command()
def version() -> None:
    """Display CareerX version."""

    typer.echo("CareerX 0.1.0")


def main() -> None:
    """CLI entrypoint."""

    app()


if __name__ == "__main__":
    main()
