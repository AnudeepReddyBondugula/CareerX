"""Verify that generated resume content traces back to the source profile.

An LLM asked to "optimise" a resume will, given the chance, invent a plausible
employer or sharpen "improved performance" into "improved performance by 40%".
Prompting alone does not reliably prevent this, so every generated resume is
checked against the profile before it is rendered:

* entities (companies, projects, schools, certifications) must already exist;
* skills must already be claimed;
* every number in a bullet must appear somewhere in the source profile.

Violations are either removed (default) or raised (``strict_grounding``).
"""

from __future__ import annotations

import logging
import re

from careerx.models import GroundingIssue, Resume

logger = logging.getLogger(__name__)

# Matches 40, 40%, 1.5x, 3,000, $2M, 10k - the shapes resume metrics take.
_NUMBER_PATTERN = re.compile(r"\d[\d,.]*\s*(?:%|x|k|m|b|bn)?", re.IGNORECASE)

# Numbers that are almost always calendar years or trivia rather than claims.
_NUMERIC_ALLOWLIST = frozenset({"1", "2", "3", "4", "5", "6", "7", "8", "9", "10", "0"})


class GroundingError(RuntimeError):
    """Raised in strict mode when generated content is not supported."""


def _normalise(text: str) -> str:
    return " ".join(text.casefold().split())


def _normalise_number(token: str) -> str:
    return token.replace(",", "").replace(" ", "").casefold().rstrip(".")


class GroundingValidator:
    """Checks a tailored resume against the profile it was derived from."""

    def __init__(self, source: Resume, *, strict: bool = False) -> None:
        self._source = source
        self._strict = strict
        self._corpus = _normalise(self._flatten(source))
        self._source_numbers = {_normalise_number(match.group()) for match in _NUMBER_PATTERN.finditer(self._corpus)}

        self._companies = {_normalise(item.company) for item in source.experience if item.company}
        self._projects = {_normalise(item.name) for item in source.projects if item.name}
        self._institutions = {_normalise(item.institution) for item in source.education if item.institution}
        self._certifications = {_normalise(item.name) for item in source.certifications if item.name}
        self._skills = {_normalise(item.name) for item in source.skills if item.name}

    @staticmethod
    def _flatten(resume: Resume) -> str:
        """All profile text as one blob, for substring and number checks."""
        parts: list[str] = [resume.summary]

        for experience in resume.experience:
            parts += [
                experience.company,
                experience.title,
                experience.location,
                experience.start_date,
                experience.end_date,
                *experience.achievements,
            ]

        for project in resume.projects:
            parts += [project.name, *project.technologies, *project.description]

        for education in resume.education:
            parts += [
                education.institution,
                education.degree,
                education.field_of_study,
                education.start_date,
                education.end_date,
                education.grade,
            ]

        for certification in resume.certifications:
            parts += [certification.name, certification.issuer]

        for achievement in resume.achievements:
            parts += [achievement.title, achievement.description]

        parts += [skill.name for skill in resume.skills]

        return " ".join(part for part in parts if part)

    def validate(self, tailored: Resume) -> tuple[Resume, list[GroundingIssue]]:
        """Return a grounded copy of ``tailored`` plus the issues found.

        Raises:
            GroundingError: in strict mode, if any issue was found.
        """
        issues: list[GroundingIssue] = []
        result = tailored.model_copy(deep=True)

        # Contact details are facts, never model output.
        result.profile = self._source.profile.model_copy(deep=True)

        result.experience = [
            item
            for item in result.experience
            if self._keep(
                _normalise(item.company) in self._companies,
                issues,
                kind="unknown_company",
                detail=f"Experience at {item.company!r} is not present in the profile.",
            )
        ]

        result.projects = [
            item
            for item in result.projects
            if self._keep(
                _normalise(item.name) in self._projects,
                issues,
                kind="unknown_project",
                detail=f"Project {item.name!r} is not present in the profile.",
            )
        ]

        result.education = [
            item
            for item in result.education
            if self._keep(
                _normalise(item.institution) in self._institutions,
                issues,
                kind="unknown_institution",
                detail=f"Education at {item.institution!r} is not present in the profile.",
            )
        ]

        result.certifications = [
            item
            for item in result.certifications
            if self._keep(
                _normalise(item.name) in self._certifications,
                issues,
                kind="unknown_certification",
                detail=f"Certification {item.name!r} is not present in the profile.",
            )
        ]

        result.skills = [
            item
            for item in result.skills
            if self._keep(
                _normalise(item.name) in self._skills,
                issues,
                kind="unknown_skill",
                detail=f"Skill {item.name!r} is not claimed in the profile.",
            )
        ]

        for experience in result.experience:
            experience.achievements = self._check_bullets(experience.achievements, issues, context=experience.company)

        for project in result.projects:
            project.description = self._check_bullets(project.description, issues, context=project.name)

        if issues and self._strict:
            raise GroundingError(f"Generated resume contains {len(issues)} ungrounded item(s): {issues[0].detail}")

        if issues:
            logger.warning("Removed %s ungrounded item(s) from the generated resume.", len(issues))

        return result, issues

    def _check_bullets(self, bullets: list[str], issues: list[GroundingIssue], *, context: str) -> list[str]:
        """Drop bullets that introduce a metric absent from the profile."""
        kept: list[str] = []

        for bullet in bullets:
            invented = self._invented_numbers(bullet)
            if invented:
                issues.append(
                    GroundingIssue(
                        kind="invented_metric",
                        detail=(
                            f"Bullet under {context!r} introduces {', '.join(sorted(invented))}, "
                            "which does not appear in the profile."
                        ),
                        removed=True,
                    )
                )
                continue

            kept.append(bullet)

        return kept

    def _invented_numbers(self, text: str) -> set[str]:
        found: set[str] = set()

        for match in _NUMBER_PATTERN.finditer(_normalise(text)):
            token = _normalise_number(match.group())
            if not token or token in _NUMERIC_ALLOWLIST:
                continue
            if token not in self._source_numbers:
                found.add(token)

        return found

    @staticmethod
    def _keep(ok: bool, issues: list[GroundingIssue], *, kind: str, detail: str) -> bool:
        if not ok:
            issues.append(GroundingIssue(kind=kind, detail=detail, removed=True))
        return ok
