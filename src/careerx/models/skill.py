from pydantic import BaseModel, Field


class Skill(BaseModel):
    name: str = ""
    category: str = Field(
        default="Technical",
        description="Grouping label, e.g. 'Languages', 'Frameworks', 'Tools'.",
    )
