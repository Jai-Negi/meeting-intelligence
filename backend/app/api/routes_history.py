import logging
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
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


@router.delete("/{job_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_meeting(job_id: str, db: Session = Depends(get_db)) -> Response:
    """
    Removes a meeting, its transcript, every extraction row, and the uploaded
    audio file. Refuses while the meeting is still processing, because the
    background job would otherwise write results for a meeting that no
    longer exists.
    """
    meeting = db.query(Meeting).filter_by(id=job_id).first()

    if meeting is None:
        raise HTTPException(status_code=404, detail="job not found")

    if meeting.status == "processing":
        raise HTTPException(
            status_code=409,
            detail="this meeting is still processing, try again once it has finished",
        )

    file_path = Path(meeting.file_path)

    db.delete(meeting)
    db.commit()

    file_path.unlink(missing_ok=True)
    logger.info("meeting deleted", extra={"job_id": job_id})

    return Response(status_code=status.HTTP_204_NO_CONTENT)
