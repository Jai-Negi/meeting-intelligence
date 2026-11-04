import logging

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.database.models import Meeting
from app.database.session import get_db
from app.schemas.meeting_summary import MeetingSummaryResponse

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/meetings", tags=["history"])


@router.get("", response_model=list[MeetingSummaryResponse])
async def list_meetings(
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
) -> list[MeetingSummaryResponse]:
    """Returns the most recent meetings first, without transcripts or extractions."""
    meetings = db.query(Meeting).order_by(Meeting.created_at.desc()).limit(limit).all()

    return [
        MeetingSummaryResponse(
            job_id=m.id,
            filename=m.filename,
            status=m.status,
            created_at=m.created_at,
        )
        for m in meetings
    ]
