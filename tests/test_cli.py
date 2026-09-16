"""CLI tests, driven through Typer's runner with the provider patched out."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from careerx.cli import app
from careerx.config.settings import Settings
from careerx.models import Resume

from .conftest import FakeProvider

runner = CliRunner()


@pytest.fixture
def cli_env(
    monkeypatch: pytest.MonkeyPatch,
    settings: Settings,
    provider: FakeProvider,
    tmp_path: Path,
) -> Path:
    """Point the CLI at a fake provider and an isolated working directory."""
    monkeypatch.setattr("careerx.config.settings.get_settings", lambda: settings)
    monkeypatch.setattr("careerx.cli.get_settings", lambda: settings)
    monkeypatch.setattr("careerx.ai.providers.factory.build_provider", lambda settings=None: provider)

    return tmp_path


def test_version_prints_the_package_version() -> None:
    result = runner.invoke(app, ["version"])

    assert result.exit_code == 0
    assert result.stdout.strip()


def test_doctor_reports_the_environment(cli_env: Path) -> None:
    result = runner.invoke(app, ["doctor"])

    assert result.exit_code == 0
    assert "LaTeX engine" in result.stdout
    assert "Templates" in result.stdout


def test_example_profile_writes_a_valid_profile(cli_env: Path) -> None:
    target = cli_env / "profile.json"

    result = runner.invoke(app, ["example-profile", "-o", str(target)])

    assert result.exit_code == 0
    assert Resume.model_validate_json(target.read_text(encoding="utf-8")).profile.full_name


def test_example_profile_asks_before_overwriting(cli_env: Path) -> None:
    target = cli_env / "profile.json"
    target.write_text("{}", encoding="utf-8")

    result = runner.invoke(app, ["example-profile", "-o", str(target)], input="n\n")

    assert result.exit_code != 0
    assert target.read_text(encoding="utf-8") == "{}"


def test_profile_schema_prints_json(cli_env: Path) -> None:
    result = runner.invoke(app, ["profile-schema"])

    assert result.exit_code == 0
    assert "properties" in result.stdout


def test_generate_writes_every_artifact(cli_env: Path, profile: Resume, job_description_text: str) -> None:
    profile_path = cli_env / "profile.json"
    profile_path.write_text(profile.model_dump_json(), encoding="utf-8")

    jd_path = cli_env / "jd.txt"
    jd_path.write_text(job_description_text, encoding="utf-8")

    output = cli_env / "out"

    result = runner.invoke(
        app,
        [
            "generate",
            "--job",
            str(jd_path),
            "--profile",
            str(profile_path),
            "--output",
            str(output),
            "--template",
            "classic",
            "--no-pdf",
        ],
    )

    assert result.exit_code == 0, result.stdout
    assert (output / "resume.tex").read_text(encoding="utf-8").lstrip().startswith("\\documentclass")
    assert Resume.model_validate_json((output / "resume.json").read_text(encoding="utf-8"))
    assert json.loads((output / "report.json").read_text(encoding="utf-8"))["evidence_chunks"] > 0


def test_generate_prints_a_coverage_summary(cli_env: Path, profile: Resume, job_description_text: str) -> None:
    profile_path = cli_env / "profile.json"
    profile_path.write_text(profile.model_dump_json(), encoding="utf-8")
    jd_path = cli_env / "jd.txt"
    jd_path.write_text(job_description_text, encoding="utf-8")

    result = runner.invoke(
        app,
        ["generate", "-j", str(jd_path), "-p", str(profile_path), "-o", str(cli_env / "out"), "--no-pdf"],
    )

    assert result.exit_code == 0
    assert "Requirement coverage" in result.stdout
    assert "Most relevant profile sections" in result.stdout


def test_generate_fails_clearly_when_the_profile_is_missing(cli_env: Path, job_description_text: str) -> None:
    jd_path = cli_env / "jd.txt"
    jd_path.write_text(job_description_text, encoding="utf-8")

    result = runner.invoke(
        app,
        ["generate", "-j", str(jd_path), "-p", str(cli_env / "nope.json"), "-o", str(cli_env / "out")],
    )

    assert result.exit_code != 0
