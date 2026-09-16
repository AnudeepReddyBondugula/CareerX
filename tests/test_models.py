from careerx.examples import example_profile
from careerx.models import JobDescription, Resume


def test_requirement_statements_deduplicates_case_insensitively() -> None:
    job = JobDescription(
        responsibilities=["Build APIs", "build apis"],
        required_skills=["Python", " Python "],
        keywords=["Python"],
    )

    assert job.requirement_statements() == ["Build APIs", "Python"]


def test_requirement_statements_preserves_section_order() -> None:
    job = JobDescription(
        responsibilities=["Operate services"],
        required_skills=["Python"],
        preferred_skills=["Kafka"],
        keywords=["payments"],
    )

    assert job.requirement_statements() == ["Operate services", "Python", "Kafka", "payments"]


def test_requirement_statements_drops_blanks() -> None:
    assert JobDescription(required_skills=["", "   ", "Go"]).requirement_statements() == ["Go"]


def test_empty_resume_is_detected() -> None:
    assert Resume().is_empty()
    assert not example_profile().is_empty()


def test_example_profile_round_trips_through_json() -> None:
    original = example_profile()
    assert Resume.model_validate_json(original.model_dump_json()) == original
