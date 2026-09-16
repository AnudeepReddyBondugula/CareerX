"""Render a :class:`Resume` into LaTeX via Jinja2."""

from __future__ import annotations

import logging
import re
from collections import defaultdict
from collections.abc import Iterable
from importlib import resources
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, StrictUndefined, TemplateNotFound

from careerx.models import CandidateProfile, Resume
from careerx.renderers.latex_escape import LatexSafe, latex_escape, latex_url

logger = logging.getLogger(__name__)

TEMPLATE_SUFFIX = ".tex.j2"
_TEMPLATE_NAME_PATTERN = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


class TemplateNotFoundError(ValueError):
    """Raised when a requested template does not exist."""


def default_template_dir() -> Path:
    """Locate the bundled template directory, installed or in a source tree."""
    return Path(str(resources.files("careerx") / "templates"))


class ResumeRenderer:
    """Renders resumes to LaTeX source.

    Jinja's delimiters are remapped away from braces because ``{{`` and ``{%``
    collide with LaTeX's own syntax, and every interpolated value is escaped
    through ``finalize`` so no template can forget to do it.
    """

    def __init__(self, template_dir: Path | None = None) -> None:
        self._template_dir = Path(template_dir) if template_dir else default_template_dir()

        self._environment = Environment(
            loader=FileSystemLoader(self._template_dir),
            autoescape=False,
            trim_blocks=True,
            lstrip_blocks=True,
            undefined=StrictUndefined,
            finalize=latex_escape,
            variable_start_string="<<",
            variable_end_string=">>",
            block_start_string="<%",
            block_end_string="%>",
            comment_start_string="<#",
            comment_end_string="#>",
        )
        self._environment.filters["url"] = latex_url

    @property
    def template_dir(self) -> Path:
        return self._template_dir

    @property
    def assets_dir(self) -> Path:
        """Directory of files (``.cls``, ``.sty``) a template needs beside it."""
        return self._template_dir / "assets"

    def available_templates(self) -> list[str]:
        paths = self._template_dir.glob(f"*{TEMPLATE_SUFFIX}")
        return sorted(path.name.removesuffix(TEMPLATE_SUFFIX) for path in paths)

    def render(self, *, resume: Resume, template: str) -> str:
        """Render ``resume`` and return the LaTeX source."""
        if not _TEMPLATE_NAME_PATTERN.match(template):
            # Also blocks path traversal via the template name.
            raise TemplateNotFoundError(f"Invalid template name: {template!r}")

        try:
            jinja_template = self._environment.get_template(f"{template}{TEMPLATE_SUFFIX}")
        except TemplateNotFound as exc:
            raise TemplateNotFoundError(
                f"Unknown template {template!r}. Available: {', '.join(self.available_templates())}"
            ) from exc

        logger.info("Rendering resume with template %r.", template)

        return jinja_template.render(**self._build_context(resume))

    def render_to_file(self, *, resume: Resume, template: str, output_path: Path) -> Path:
        latex = self.render(resume=resume, template=template)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(latex, encoding="utf-8")
        return output_path

    def _build_context(self, resume: Resume) -> dict[str, Any]:
        """Prepare presentation data so templates stay free of logic."""
        return {
            "profile": resume.profile,
            "summary": resume.summary,
            "education": resume.education,
            "experiences": resume.experience,
            "projects": resume.projects,
            "certifications": resume.certifications,
            "achievements": resume.achievements,
            "skills": resume.skills,
            "skill_groups": self.group_skills(resume),
            "contact_links": self.build_contact_links(resume.profile),
        }

    @staticmethod
    def build_contact_links(profile: CandidateProfile) -> list[dict[str, object]]:
        """Contact entries for the header, in display order.

        Built here rather than in the template so the separator logic stays a
        simple ``loop.first`` check and no trailing separator is emitted.
        """
        entries: list[dict[str, object]] = []

        def add(icon: str, label: str, target: str | None = None) -> None:
            if label:
                entries.append(
                    {
                        "icon": LatexSafe(icon),
                        "label": label,
                        "target": latex_url(target) if target else None,
                    }
                )

        add(r"\faPhone*", profile.phone)
        add(r"\faEnvelope", profile.email, f"mailto:{profile.email}" if profile.email else None)
        add(r"\faMapMarker*", profile.location)
        add(r"\faLinkedin", "LinkedIn" if profile.linkedin else "", profile.linkedin)
        add(r"\faGithub", "GitHub" if profile.github else "", profile.github)
        add(r"\faGlobe", "Portfolio" if profile.portfolio else "", profile.portfolio)

        return entries

    @staticmethod
    def group_skills(resume: Resume) -> list[tuple[str, list[str]]]:
        """Group skill names by category, preserving first-seen order.

        Order matters: the model ranks skills by relevance to the posting, and
        a dict-order-preserving grouping keeps that ranking visible.
        """
        grouped: defaultdict[str, list[str]] = defaultdict(list)

        for skill in resume.skills:
            if skill.name:
                grouped[skill.category or "Technical"].append(skill.name)

        return list(grouped.items())


def join(values: Iterable[str], separator: str = ", ") -> str:
    return separator.join(values)
