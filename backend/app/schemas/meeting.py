from pydantic import BaseModel


class TranscriptSegmentResponse(BaseModel):
    start: float
    end: float
    text: str


class ActionItemResponse(BaseModel):
    description: str
    owner: str | None = None
    due_date: str | None = None


class MeetingUploadResponse(BaseModel):
    job_id: str
    filename: str
    status: str


class TranscriptResponse(BaseModel):
    job_id: str
    status: str
    text: str | None = None
    language: str | None = None
    segments: list[TranscriptSegmentResponse] = []
    action_items: list[ActionItemResponse] = []
    error: str | None = None
