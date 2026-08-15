import json
from pathlib import Path

from careerx.models import Resume


class ProfileService:
    def __init__(self, profile_path: Path | str = "profile.json"):
        self.profile_path = Path(profile_path)

    def load_profile(self) -> Resume:
        if not self.profile_path.exists():
            return Resume()

        with self.profile_path.open("r", encoding="utf-8") as file:
            data = json.load(file)

        return Resume.model_validate(data)

    def save_profile(self, resume: Resume) -> None:
        with self.profile_path.open("w", encoding="utf-8") as file:
            json.dump(
                resume.model_dump(),
                file,
                indent=4,
                ensure_ascii=False,
            )

    def update_profile(self, resume: Resume) -> Resume:
        self.save_profile(resume)
        return resume
