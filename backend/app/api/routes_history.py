import logging
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Response, status
from sqlalchemy.orm import Session

from app.api import routes_meetings
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


@router.post(
    "/{job_id}/retry",
    response_model=MeetingSummaryResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def retry_meeting(
    job_id: str,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
) -> MeetingSummaryResponse:
    """
    Runs the whole pipeline again for a failed meeting, using the audio file
    that was saved at upload time. Anything left over from the earlier
    attempt is cleared first so results are never duplicated.
    """
    meeting = db.query(Meeting).filter_by(id=job_id).first()

    if meeting is None:
        raise HTTPException(status_code=404, detail="job not found")

    if meeting.status != "failed":
        raise HTTPException(status_code=409, detail="only failed meetings can be retried")

    file_path = Path(meeting.file_path)
    if not file_path.is_file():
        raise HTTPException(
            status_code=409,
            detail="the original audio file is no longer on the server, upload it again",
        )

    leftovers = [meeting.transcript, *meeting.action_items, *meeting.timeline_events, *meeting.decisions]
    for row in leftovers:
        if row is not None:
            db.delete(row)

    meeting.status = "processing"
    meeting.error = None
    db.commit()
    db.refresh(meeting)

    background_tasks.add_task(routes_meetings._process_transcription, job_id, file_path)
    logger.info("meeting retry started", extra={"job_id": job_id})

    return MeetingSummaryResponse(
        job_id=meeting.id,
        filename=meeting.filename,
        status=meeting.status,
        created_at=meeting.created_at,
    )
