from datetime import datetime

from pydantic import BaseModel


class MeetingSummaryResponse(BaseModel):
    job_id: str
    filename: str
    status: str
    created_at: datetime
