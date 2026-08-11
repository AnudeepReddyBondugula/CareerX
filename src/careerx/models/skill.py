from pydantic import BaseModel


class Skill(BaseModel):
    name: str = ""
    category: str = ""
