from pydantic import BaseModel, Field


class CandidateProfile(BaseModel):
    """Contact block shown in the resume header."""

    full_name: str = ""
    headline: str = Field(default="", description="Short professional title, e.g. 'Backend Engineer'.")
    email: str = ""
    phone: str = ""
    location: str = ""
    linkedin: str = ""
    github: str = ""
    portfolio: str = ""
