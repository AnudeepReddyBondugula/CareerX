import pytest

from careerx.models import (
    Achievement,
    CandidateProfile,
    Certification,
    Education,
    Experience,
    Project,
    Resume,
    Skill,
)
from careerx.renderers import ResumeRenderer, TemplateNotFoundError

TEMPLATES = ("treyHunner", "classic")


@pytest.fixture
def renderer() -> ResumeRenderer:
    return ResumeRenderer()


def test_both_templates_are_discovered(renderer: ResumeRenderer) -> None:
    assert set(TEMPLATES).issubset(renderer.available_templates())


@pytest.mark.parametrize("template", TEMPLATES)
def test_a_full_profile_renders_a_complete_document(
    renderer: ResumeRenderer,
    profile: Resume,
    template: str,
) -> None:
    latex = renderer.render(resume=profile, template=template)

    assert latex.lstrip().startswith("\\documentclass")
    assert latex.rstrip().endswith("\\end{document}")
    assert "Ada Sharma" in latex
    assert "Northwind Payments" in latex


@pytest.mark.parametrize("template", TEMPLATES)
def test_an_empty_resume_still_renders(renderer: ResumeRenderer, template: str) -> None:
    latex = renderer.render(resume=Resume(), template=template)

    assert "\\begin{document}" in latex
    assert "\\end{document}" in latex


@pytest.mark.parametrize("template", TEMPLATES)
def test_empty_sections_are_omitted_rather_than_left_blank(renderer: ResumeRenderer, template: str) -> None:
    resume = Resume(skills=[Skill(name="Python", category="Languages")])

    latex = renderer.render(resume=resume, template=template)

    assert "PROJECTS" not in latex.upper()
    assert "EDUCATION" not in latex.upper()


@pytest.mark.parametrize("template", TEMPLATES)
def test_special_characters_in_user_data_are_escaped(renderer: ResumeRenderer, template: str) -> None:
    resume = Resume(
        profile=CandidateProfile(full_name="R&D Lead #1"),
        experience=[Experience(company="AT&T", achievements=["Raised margin 100% & cut cost_per_unit"])],
    )

    latex = renderer.render(resume=resume, template=template)

    assert r"R\&D Lead \#1" in latex
    assert r"AT\&T" in latex
    assert r"100\% \& cut cost\_per\_unit" in latex


@pytest.mark.parametrize("template", TEMPLATES)
def test_a_latex_injection_attempt_is_neutralised(renderer: ResumeRenderer, template: str) -> None:
    resume = Resume(
        profile=CandidateProfile(full_name=r"\input{/etc/passwd}"),
        experience=[Experience(company=r"\immediate\write18{rm -rf /}")],
    )

    latex = renderer.render(resume=resume, template=template)

    assert r"\input{/etc/passwd}" not in latex
    assert r"\write18" not in latex
    assert r"\textbackslash{}input" in latex


def test_skills_are_grouped_by_category_preserving_order(renderer: ResumeRenderer) -> None:
    resume = Resume(
        skills=[
            Skill(name="Python", category="Languages"),
            Skill(name="FastAPI", category="Frameworks"),
            Skill(name="Go", category="Languages"),
        ]
    )

    assert ResumeRenderer.group_skills(resume) == [
        ("Languages", ["Python", "Go"]),
        ("Frameworks", ["FastAPI"]),
    ]

    latex = renderer.render(resume=resume, template="classic")
    assert "Python, Go" in latex


def test_contact_links_skip_missing_fields() -> None:
    links = ResumeRenderer.build_contact_links(
        CandidateProfile(full_name="X", email="x@example.com", github="https://github.com/x")
    )

    assert [link["label"] for link in links] == ["x@example.com", "GitHub"]
    assert links[0]["target"] == "mailto:x@example.com"


def test_a_url_is_not_body_escaped(renderer: ResumeRenderer) -> None:
    resume = Resume(profile=CandidateProfile(full_name="X", github="https://github.com/a_b"))

    latex = renderer.render(resume=resume, template="classic")

    assert "https://github.com/a_b" in latex


def test_unknown_template_is_rejected(renderer: ResumeRenderer) -> None:
    with pytest.raises(TemplateNotFoundError, match="Unknown template"):
        renderer.render(resume=Resume(), template="nope")


@pytest.mark.parametrize("name", ["../../etc/passwd", "a/b", "..", "with space", ""])
def test_template_names_cannot_escape_the_template_directory(renderer: ResumeRenderer, name: str) -> None:
    with pytest.raises(TemplateNotFoundError, match="Invalid template name"):
        renderer.render(resume=Resume(), template=name)


def test_the_class_file_ships_with_the_package(renderer: ResumeRenderer) -> None:
    assert (renderer.assets_dir / "resume.cls").is_file()


@pytest.mark.parametrize("template", TEMPLATES)
def test_every_section_type_appears_when_present(renderer: ResumeRenderer, template: str) -> None:
    resume = Resume(
        profile=CandidateProfile(full_name="X"),
        summary="A summary line.",
        experience=[Experience(company="Acme", title="Eng", achievements=["Did work"])],
        projects=[Project(name="Proj", technologies=["Python"], description=["Built it"])],
        skills=[Skill(name="Python", category="Languages")],
        education=[Education(institution="Uni", degree="BSc", field_of_study="CS")],
        certifications=[Certification(name="Cert", issuer="Issuer")],
        achievements=[Achievement(title="Award", description="For work")],
    )

    latex = renderer.render(resume=resume, template=template)

    for expected in ("A summary line.", "Acme", "Proj", "Python", "Uni", "Cert", "Award"):
        assert expected in latex
