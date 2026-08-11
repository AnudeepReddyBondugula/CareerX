from pydantic import BaseModel


class Certification(BaseModel):
    name: str = ""
    issuer: str = ""
    issue_date: str = ""
    credential_id: str = ""
