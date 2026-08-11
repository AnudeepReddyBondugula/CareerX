from pydantic import BaseModel, Field

from careerx.models.achievement import Achievement
from careerx.models.candidate_profile import CandidateProfile
from careerx.models.certification import Certification
from careerx.models.education import Education
from careerx.models.experience import Experience
from careerx.models.project import Project
from careerx.models.skill import Skill


class Resume(BaseModel):
    profile: CandidateProfile = Field(default_factory=CandidateProfile)

    education: list[Education] = Field(default_factory=list)

    experience: list[Experience] = Field(default_factory=list)

    projects: list[Project] = Field(default_factory=list)

    certifications: list[Certification] = Field(default_factory=list)

    skills: list[Skill] = Field(default_factory=list)

    achievements: list[Achievement] = Field(default_factory=list)
