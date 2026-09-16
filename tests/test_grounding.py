import pytest

from careerx.models import (
    CandidateProfile,
    Certification,
    Education,
    Experience,
    Project,
    Resume,
    Skill,
)
from careerx.services.grounding import GroundingError, GroundingValidator


@pytest.fixture
def source() -> Resume:
    return Resume(
        profile=CandidateProfile(full_name="Ada Sharma", email="ada@example.com"),
        experience=[
            Experience(
                company="Acme",
                title="Engineer",
                achievements=["Reduced latency by 30% across the checkout path"],
            )
        ],
        projects=[Project(name="Ledgerlint", description=["Wrote a static analyser"])],
        education=[Education(institution="NIT Warangal", degree="B.Tech")],
        certifications=[Certification(name="AWS SAA", issuer="Amazon")],
        skills=[Skill(name="Python"), Skill(name="Go")],
    )


def test_a_faithful_resume_passes_unchanged(source: Resume) -> None:
    result, issues = GroundingValidator(source).validate(source)

    assert issues == []
    assert result.experience[0].company == "Acme"


def test_an_invented_employer_is_removed(source: Resume) -> None:
    tailored = source.model_copy(deep=True)
    tailored.experience.append(Experience(company="Globex", title="Director", achievements=["Led the org"]))

    result, issues = GroundingValidator(source).validate(tailored)

    assert [item.company for item in result.experience] == ["Acme"]
    assert [issue.kind for issue in issues] == ["unknown_company"]
    assert "Globex" in issues[0].detail


def test_an_invented_project_is_removed(source: Resume) -> None:
    tailored = source.model_copy(deep=True)
    tailored.projects.append(Project(name="Kubernetes Operator Framework"))

    result, issues = GroundingValidator(source).validate(tailored)

    assert [item.name for item in result.projects] == ["Ledgerlint"]
    assert issues[0].kind == "unknown_project"


def test_an_unclaimed_skill_is_removed(source: Resume) -> None:
    tailored = source.model_copy(deep=True)
    tailored.skills.append(Skill(name="Rust"))

    result, issues = GroundingValidator(source).validate(tailored)

    assert [item.name for item in result.skills] == ["Python", "Go"]
    assert issues[0].kind == "unknown_skill"


def test_an_invented_metric_is_removed(source: Resume) -> None:
    tailored = source.model_copy(deep=True)
    tailored.experience[0].achievements = [
        "Reduced latency by 30% across the checkout path",
        "Improved throughput by 85%",
    ]

    result, issues = GroundingValidator(source).validate(tailored)

    assert result.experience[0].achievements == ["Reduced latency by 30% across the checkout path"]
    assert issues[0].kind == "invented_metric"
    assert "85%" in issues[0].detail


def test_a_metric_present_in_the_profile_survives_rewording(source: Resume) -> None:
    tailored = source.model_copy(deep=True)
    tailored.experience[0].achievements = ["Cut checkout latency 30%, improving conversion"]

    result, issues = GroundingValidator(source).validate(tailored)

    assert issues == []
    assert result.experience[0].achievements == ["Cut checkout latency 30%, improving conversion"]


def test_small_counts_are_not_treated_as_invented_metrics(source: Resume) -> None:
    tailored = source.model_copy(deep=True)
    tailored.experience[0].achievements = ["Mentored 3 engineers"]

    _, issues = GroundingValidator(source).validate(tailored)

    assert issues == []


def test_contact_details_always_come_from_the_profile(source: Resume) -> None:
    tailored = source.model_copy(deep=True)
    tailored.profile = CandidateProfile(full_name="Someone Else", email="attacker@example.com")

    result, _ = GroundingValidator(source).validate(tailored)

    assert result.profile.full_name == "Ada Sharma"
    assert result.profile.email == "ada@example.com"


def test_entity_matching_ignores_case_and_spacing(source: Resume) -> None:
    tailored = source.model_copy(deep=True)
    tailored.experience[0].company = "  acme  "

    result, issues = GroundingValidator(source).validate(tailored)

    assert issues == []
    assert len(result.experience) == 1


def test_strict_mode_raises_instead_of_repairing(source: Resume) -> None:
    tailored = source.model_copy(deep=True)
    tailored.skills.append(Skill(name="Rust"))

    with pytest.raises(GroundingError, match="ungrounded"):
        GroundingValidator(source, strict=True).validate(tailored)


def test_the_source_resume_is_never_mutated(source: Resume) -> None:
    tailored = source.model_copy(deep=True)
    tailored.experience.append(Experience(company="Globex"))

    GroundingValidator(source).validate(tailored)

    assert len(tailored.experience) == 2
    assert len(source.experience) == 1
