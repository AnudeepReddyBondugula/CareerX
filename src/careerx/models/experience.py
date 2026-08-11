from pydantic import BaseModel, Field


class Experience(BaseModel):
    company: str = ""
    title: str = ""
    location: str = ""
    start_date: str = ""
    end_date: str = ""
    currently_working: bool = False
    achievements: list[str] = Field(default_factory=list)
