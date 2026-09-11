import logging
import uuid
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.agents.action_item_agent import ActionItemAgent
from app.agents.transcription_agent import TranscriptionAgent
from app.config import get_settings
from app.database.models import ActionItem, Meeting, Transcript, TranscriptSegment
from app.database.session import SessionLocal, get_db
from app.schemas.meeting import (
    ActionItemResponse,
    MeetingUploadResponse,
    TranscriptResponse,
    TranscriptSegmentResponse,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/meetings", tags=["meetings"])

settings = get_settings()


async def _process_transcription(meeting_id: str, file_path: Path) -> None:
    """
    Runs in the background after upload. Transcribes the recording,
    then if that succeeds, immediately runs action item extraction
    on the resulting transcript. Opens its own database session
    since the request's session is already closed by the time this
    actually runs.
    """
    agent = TranscriptionAgent(model_size=settings.whisper_model_size)
    result = await agent.execute(file_path=file_path)

    db = SessionLocal()
    try:
        meeting = db.query(Meeting).filter_by(id=meeting_id).first()
        if meeting is None:
            logger.error("meeting not found for background job", extra={"meeting_id": meeting_id})
            return

        if not result.success:
            meeting.status = "failed"
            meeting.error = result.error
            db.commit()
            return

        meeting.status = "completed"
        transcript = Transcript(
            meeting_id=meeting.id,
            text=result.data.text,
            language=result.data.language,
        )
        db.add(transcript)
        db.flush()

        for segment in result.data.segments:
            db.add(
                TranscriptSegment(
                    transcript_id=transcript.id,
                    start=segment.start,
                    end=segment.end,
                    text=segment.text,
                )
            )

        db.commit()

        # Transcription succeeded, now extract action items from the
        # resulting text. A failure here does not roll back the
        # transcript, the meeting simply ends up with no action items.
        await _process_action_items(meeting_id=meeting_id, transcript_text=result.data.text)

    finally:
        db.close()


async def _process_action_items(meeting_id: str, transcript_text: str) -> None:
    agent = ActionItemAgent()
    result = await agent.execute(transcript_text=transcript_text)

    if not result.success:
        logger.warning(
            "action item extraction failed, meeting keeps its transcript",
            extra={"meeting_id": meeting_id, "error": result.error},
        )
        return

    db = SessionLocal()
    try:
        for item in result.data:
            db.add(
                ActionItem(
                    meeting_id=meeting_id,
                    description=item.description,
                    owner=item.owner,
                    due_date=item.due_date,
                )
            )
        db.commit()
        logger.info(
            "action items saved", extra={"meeting_id": meeting_id, "count": len(result.data)}
        )
    finally:
        db.close()


@router.post("/upload", response_model=MeetingUploadResponse)
async def upload_meeting(
    background_tasks: BackgroundTasks,
    file: UploadFile,
    db: Session = Depends(get_db),
) -> MeetingUploadResponse:
    upload_dir = Path(settings.upload_dir)
    upload_dir.mkdir(parents=True, exist_ok=True)

    job_id = str(uuid.uuid4())
    destination = upload_dir / f"{job_id}_{file.filename}"

    contents = await file.read()
    destination.write_bytes(contents)

    meeting = Meeting(
        id=job_id,
        filename=file.filename,
        file_path=str(destination),
        status="processing",
    )
    db.add(meeting)
    db.commit()

    logger.info(
        "meeting uploaded", extra={"job_id": job_id, "uploaded_filename": file.filename}
    )

    background_tasks.add_task(_process_transcription, job_id, destination)

    return MeetingUploadResponse(job_id=job_id, filename=file.filename, status="processing")


@router.get("/{job_id}", response_model=TranscriptResponse)
async def get_transcript(job_id: str, db: Session = Depends(get_db)) -> TranscriptResponse:
    meeting = db.query(Meeting).filter_by(id=job_id).first()

    if meeting is None:
        raise HTTPException(status_code=404, detail="job not found")

    action_items = [
        ActionItemResponse(description=a.description, owner=a.owner, due_date=a.due_date)
        for a in meeting.action_items
    ]

    if meeting.transcript is None:
        return TranscriptResponse(
            job_id=job_id, status=meeting.status, action_items=action_items, error=meeting.error
        )

    return TranscriptResponse(
        job_id=job_id,
        status=meeting.status,
        text=meeting.transcript.text,
        language=meeting.transcript.language,
        segments=[
            TranscriptSegmentResponse(start=s.start, end=s.end, text=s.text)
            for s in meeting.transcript.segments
        ],
        action_items=action_items,
        error=meeting.error,
    )
