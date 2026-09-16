"""Explainability structures describing *why* a resume looks the way it does."""

from pydantic import BaseModel, Field

from careerx.models.evidence import EvidenceKind


class EvidenceMatch(BaseModel):
    """A single retrieved chunk and how well it matched."""

    chunk_id: str
    kind: EvidenceKind
    label: str
    text: str
    score: float = Field(description="Cosine similarity in [-1, 1]; higher is more relevant.")


class RequirementMatch(BaseModel):
    """Top-k profile evidence for one job requirement."""

    requirement: str
    matches: list[EvidenceMatch] = Field(default_factory=list)

    @property
    def best_score(self) -> float:
        return max((match.score for match in self.matches), default=0.0)


class SectionScore(BaseModel):
    """Aggregate relevance of one profile entry to the whole posting."""

    section_id: str
    kind: EvidenceKind
    label: str
    score: float
    matched_requirements: list[str] = Field(default_factory=list)


class CoverageReport(BaseModel):
    """How much of the posting the candidate's profile actually supports."""

    covered: list[str] = Field(default_factory=list)
    partially_covered: list[str] = Field(default_factory=list)
    uncovered: list[str] = Field(default_factory=list)

    @property
    def coverage_ratio(self) -> float:
        total = len(self.covered) + len(self.partially_covered) + len(self.uncovered)
        if total == 0:
            return 0.0
        return (len(self.covered) + 0.5 * len(self.partially_covered)) / total


class GroundingIssue(BaseModel):
    """One piece of generated content that could not be traced to the profile."""

    kind: str
    detail: str
    removed: bool = False


class TailoringReport(BaseModel):
    """Everything the pipeline learned while tailoring, returned to the caller."""

    provider: str = ""
    model: str = ""
    embedding_backend: str = ""
    evidence_chunks: int = 0
    requirement_matches: list[RequirementMatch] = Field(default_factory=list)
    section_scores: list[SectionScore] = Field(default_factory=list)
    coverage: CoverageReport = Field(default_factory=CoverageReport)
    grounding_issues: list[GroundingIssue] = Field(default_factory=list)
