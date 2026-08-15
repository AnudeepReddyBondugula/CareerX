"""Resume renderer using Jinja2 and LaTeX."""

from __future__ import annotations

import logging
from collections import defaultdict
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, StrictUndefined

from careerx.models import Resume

logger = logging.getLogger(__name__)


class ResumeRenderer:
    """Renders a Resume into a LaTeX document."""

    def __init__(self, template_dir: Path) -> None:
        self._environment = Environment(
            loader=FileSystemLoader(template_dir),
            autoescape=False,
            trim_blocks=True,
            lstrip_blocks=True,
            undefined=StrictUndefined,
            # Variables
            variable_start_string="<<",
            variable_end_string=">>",
            # Control blocks
            block_start_string="<%",
            block_end_string="%>",
            # Comments
            comment_start_string="<#",
            comment_end_string="#>",
        )

    def render(
        self,
        *,
        resume: Resume,
        output_path: Path,
        template_name: str = "treyHunner.tex.j2",
    ) -> Path:
        """
        Render a Resume into a LaTeX (.tex) file.

        Args:
            resume: Resume model.
            output_path: Destination .tex file.
            template_name: Jinja template name.

        Returns:
            Path to generated .tex file.
        """
        logger.info("Rendering resume using template '%s'", template_name)

        template = self._environment.get_template(template_name)

        context = self._build_context(resume)

        latex = template.render(**context)

        output_path.parent.mkdir(parents=True, exist_ok=True)

        output_path.write_text(latex, encoding="utf-8")

        logger.info("Resume rendered successfully: %s", output_path)

        return output_path

    def _build_context(self, resume: Resume) -> dict[str, Any]:
        """
        Build template context.

        The renderer prepares presentation-specific data while keeping
        the template free of business logic.
        """
        return {
            "profile": resume.profile,
            "education": resume.education,
            "experiences": resume.experience,
            "projects": resume.projects,
            "certifications": resume.certifications,
            "achievements": resume.achievements,
            "skills": resume.skills,
        }

    @staticmethod
    def _group_skills(resume: Resume) -> dict[str, list[str]]:
        """
        Group skills by category.

        Example:
            {
                "Programming Languages": ["Python", "Java"],
                "Frameworks": ["FastAPI", "Django"],
            }
        """
        grouped: defaultdict[str, list[str]] = defaultdict(list)

        for skill in resume.skills:
            grouped[skill.category].append(skill.name)

        return dict(grouped)
