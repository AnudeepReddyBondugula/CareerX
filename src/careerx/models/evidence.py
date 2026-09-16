"""Atomic, retrievable units of a candidate's profile."""

from enum import StrEnum

from pydantic import BaseModel, Field


class EvidenceKind(StrEnum):
    """Which resume section a chunk originated from."""

    EXPERIENCE = "experience"
    PROJECT = "project"
    SKILL = "skill"
    EDUCATION = "education"
    CERTIFICATION = "certification"
    ACHIEVEMENT = "achievement"
    SUMMARY = "summary"


class EvidenceChunk(BaseModel):
    """One embeddable fact drawn from the profile.

    ``chunk_id`` is stable for a given profile so retrieval results can be
    cited back to the exact source line in the tailoring report.
    """

    chunk_id: str
    kind: EvidenceKind
    section_index: int = Field(description="Index of the owning entry within its section list.")
    item_index: int = Field(default=0, description="Index within the entry, e.g. which bullet.")
    label: str = Field(default="", description="Human-readable owner, e.g. 'Acme - Backend Engineer'.")
    text: str

    @property
    def section_id(self) -> str:
        """Identifier of the owning entry, shared by all of its chunks."""
        return f"{self.kind.value}:{self.section_index}"
