from pydantic import BaseModel, Field


class Project(BaseModel):
    name: str = ""
    technologies: list[str] = Field(default_factory=list)
    description: list[str] = Field(default_factory=list)
    github: str = ""
    live_demo: str = ""
