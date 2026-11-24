from pydantic import BaseModel


class TranscriptSegmentResponse(BaseModel):
    start: float
    end: float
    text: str


class ActionItemResponse(BaseModel):
    description: str
    owner: str | None = None
    due_date: str | None = None


class TimelineEventResponse(BaseModel):
    topic: str
    summary: str
    approx_time: str | None = None


class DecisionResponse(BaseModel):
    decision: str
    context: str | None = None


class SummaryResponse(BaseModel):
    overview: str
    key_points: list[str] = []


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
    summary: SummaryResponse | None = None
    action_items: list[ActionItemResponse] = []
    timeline: list[TimelineEventResponse] = []
    decisions: list[DecisionResponse] = []
    error: str | None = None
