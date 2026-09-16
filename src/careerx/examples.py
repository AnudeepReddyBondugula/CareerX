"""A worked example profile, used by the docs, the UI and the tests."""

from __future__ import annotations

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


def example_profile() -> Resume:
    """A fictional but complete profile in the expected shape."""
    return Resume(
        profile=CandidateProfile(
            full_name="Ada Sharma",
            headline="Backend Engineer",
            email="ada.sharma@example.com",
            phone="+1 555 0100",
            location="Bengaluru, India",
            linkedin="https://linkedin.com/in/example",
            github="https://github.com/example",
        ),
        summary=(
            "Backend engineer with 4 years building Python services for high-throughput "
            "payment systems, focused on reliability and developer tooling."
        ),
        experience=[
            Experience(
                company="Northwind Payments",
                title="Senior Backend Engineer",
                location="Bengaluru, India",
                start_date="Mar 2023",
                end_date="Present",
                achievements=[
                    "Rebuilt the settlement pipeline on FastAPI and PostgreSQL, cutting median "
                    "reconciliation time from 40 minutes to 6 minutes.",
                    "Introduced contract tests across 12 internal services, reducing integration regressions by 70%.",
                    "Mentored 3 junior engineers through the team's on-call rotation.",
                ],
            ),
            Experience(
                company="Kitewheel Labs",
                title="Backend Engineer",
                location="Remote",
                start_date="Jul 2021",
                end_date="Feb 2023",
                achievements=[
                    "Designed a Celery-based ingestion service handling 2M events per day.",
                    "Migrated the reporting store from MySQL to PostgreSQL with zero downtime.",
                ],
            ),
        ],
        projects=[
            Project(
                name="CareerX",
                technologies=["Python", "FastAPI", "FAISS", "Pydantic", "LaTeX"],
                description=[
                    "Built an AI resume builder that grounds every generated bullet in retrieved profile evidence.",
                    "Implemented semantic retrieval over profile chunks with FAISS and pluggable embedding backends.",
                ],
                github="https://github.com/example/careerx",
            ),
            Project(
                name="Ledgerlint",
                technologies=["Go", "PostgreSQL"],
                description=["Wrote a static analyser for double-entry bookkeeping schemas."],
            ),
        ],
        skills=[
            Skill(name="Python", category="Languages"),
            Skill(name="Go", category="Languages"),
            Skill(name="SQL", category="Languages"),
            Skill(name="FastAPI", category="Frameworks"),
            Skill(name="Celery", category="Frameworks"),
            Skill(name="PostgreSQL", category="Databases"),
            Skill(name="Redis", category="Databases"),
            Skill(name="Docker", category="Cloud & DevOps"),
            Skill(name="AWS", category="Cloud & DevOps"),
            Skill(name="GitHub Actions", category="Cloud & DevOps"),
        ],
        education=[
            Education(
                institution="National Institute of Technology, Warangal",
                degree="B.Tech",
                field_of_study="Computer Science",
                start_date="2017",
                end_date="2021",
                grade="8.6 CGPA",
            )
        ],
        certifications=[
            Certification(name="AWS Certified Solutions Architect - Associate", issuer="Amazon Web Services"),
        ],
        achievements=[
            Achievement(
                title="Internal hackathon winner",
                description="Built a latency budget visualiser adopted by four platform teams.",
            )
        ],
    )


EXAMPLE_JOB_DESCRIPTION = """\
Senior Backend Engineer - Payments Platform

We are looking for a backend engineer to own the services behind our payments
platform. You will design and operate high-throughput Python services, work
closely with data engineering, and raise the reliability bar for the team.

Responsibilities
- Design, build and operate Python microservices handling millions of events daily.
- Own service reliability, including on-call, alerting and incident review.
- Improve our CI/CD pipelines and automated test coverage.
- Mentor engineers and review designs across the platform team.

Requirements
- 4+ years of backend engineering experience in Python.
- Strong experience with FastAPI or a comparable async web framework.
- Production experience with PostgreSQL and schema migrations.
- Experience with containerised deployments (Docker, Kubernetes).

Nice to have
- Experience with Kafka or another event streaming platform.
- Exposure to the payments or fintech domain.
- Familiarity with Terraform.
"""
