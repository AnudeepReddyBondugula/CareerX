from pydantic import BaseModel, Field

from careerx.models.achievement import Achievement
from careerx.models.candidate_profile import CandidateProfile
from careerx.models.certification import Certification
from careerx.models.education import Education
from careerx.models.experience import Experience
from careerx.models.project import Project
from careerx.models.skill import Skill


class Resume(BaseModel):
    """The master profile and, after tailoring, the generated resume.

    The same shape is used for input and output so a generated resume can be
    fed back in as a profile without any translation layer.
    """

    profile: CandidateProfile = Field(default_factory=CandidateProfile)
    summary: str = ""

    education: list[Education] = Field(default_factory=list)
    experience: list[Experience] = Field(default_factory=list)
    projects: list[Project] = Field(default_factory=list)
    certifications: list[Certification] = Field(default_factory=list)
    skills: list[Skill] = Field(default_factory=list)
    achievements: list[Achievement] = Field(default_factory=list)

    def is_empty(self) -> bool:
        return not any(
            (
                self.education,
                self.experience,
                self.projects,
                self.certifications,
                self.skills,
                self.achievements,
            )
        )
