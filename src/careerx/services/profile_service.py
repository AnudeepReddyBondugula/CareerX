"""Loading and persisting candidate profiles."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from careerx.models import Resume

logger = logging.getLogger(__name__)


class ProfileError(ValueError):
    """Raised when a profile cannot be read or does not match the schema."""


def parse_profile(data: Any) -> Resume:
    """Validate ``data`` (a mapping or JSON string) into a :class:`Resume`."""
    if isinstance(data, str | bytes | bytearray):
        try:
            data = json.loads(data)
        except json.JSONDecodeError as exc:
            raise ProfileError(f"Profile is not valid JSON: {exc}") from exc

    if not isinstance(data, dict):
        raise ProfileError("Profile must be a JSON object.")

    try:
        resume = Resume.model_validate(data)
    except ValidationError as exc:
        raise ProfileError(f"Profile does not match the expected schema: {exc}") from exc

    if resume.is_empty():
        raise ProfileError("Profile contains no experience, projects, education, skills or certifications.")

    return resume


class ProfileService:
    """File-backed profile storage, used by the CLI."""

    def __init__(self, profile_path: Path | str = "profile.json") -> None:
        self.profile_path = Path(profile_path)

    def load_profile(self) -> Resume:
        if not self.profile_path.exists():
            raise ProfileError(f"Profile not found at {self.profile_path}.")

        return parse_profile(self.profile_path.read_text(encoding="utf-8"))

    def save_profile(self, resume: Resume) -> Path:
        self.profile_path.parent.mkdir(parents=True, exist_ok=True)
        self.profile_path.write_text(resume.model_dump_json(indent=2), encoding="utf-8")
        return self.profile_path
