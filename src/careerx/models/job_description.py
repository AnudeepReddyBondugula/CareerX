from pydantic import BaseModel, Field


class JobDescription(BaseModel):
    title: str = ""
    company: str = ""

    summary: str = ""

    responsibilities: list[str] = Field(default_factory=list)

    required_skills: list[str] = Field(default_factory=list)

    preferred_skills: list[str] = Field(default_factory=list)

    keywords: list[str] = Field(default_factory=list)
