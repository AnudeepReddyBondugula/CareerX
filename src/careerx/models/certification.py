from pydantic import BaseModel


class Certification(BaseModel):
    name: str = ""
    issuer: str = ""
