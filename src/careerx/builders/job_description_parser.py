from careerx.ai.gemini_client import GeminiClient
from careerx.ai.prompts.jd_parser_prompt import SYSTEM_INSTRUCTION
from careerx.models import JobDescription


class JobDescriptionParser:
    def __init__(self, client: GeminiClient | None = None) -> None:
        self.client = client or GeminiClient()

    def parse(self, job_description: str) -> JobDescription:
        return self.client.generate(
            system_instruction=SYSTEM_INSTRUCTION,
            user_prompt=job_description,
            response_model=JobDescription,
        )