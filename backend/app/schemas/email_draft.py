from pydantic import BaseModel


class EmailDraftResponse(BaseModel):
    subject: str
    body: str
