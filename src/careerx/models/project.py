from pydantic import BaseModel, Field


class Project(BaseModel):
    name: str = ""
    description: str = ""
    technologies: list[str] = Field(default_factory=list)
    highlights: list[str] = Field(default_factory=list)
    github: str = ""
    live_demo: str = ""
