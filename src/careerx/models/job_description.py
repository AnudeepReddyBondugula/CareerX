from pydantic import BaseModel, Field


class JobDescription(BaseModel):
    """Structured view of a raw job posting."""

    title: str = ""
    company: str = ""
    location: str = ""
    seniority: str = ""
    summary: str = ""

    responsibilities: list[str] = Field(default_factory=list)
    required_skills: list[str] = Field(default_factory=list)
    preferred_skills: list[str] = Field(default_factory=list)
    keywords: list[str] = Field(default_factory=list)

    def requirement_statements(self) -> list[str]:
        """Flatten the posting into de-duplicated retrieval queries.

        These are the units the retriever searches profile evidence for, so
        ordering is preserved (most structural first) and blanks are dropped.
        """
        seen: set[str] = set()
        statements: list[str] = []

        groups = (
            self.responsibilities,
            self.required_skills,
            self.preferred_skills,
            self.keywords,
        )

        for group in groups:
            for item in group:
                text = item.strip()
                key = text.casefold()
                if text and key not in seen:
                    seen.add(key)
                    statements.append(text)

        return statements
