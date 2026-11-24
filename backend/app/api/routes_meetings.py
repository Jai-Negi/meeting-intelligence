import asyncio
import logging
import uuid
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.tools.validators import (
    UploadValidationError,
    allowed_extensions_for,
    validate_upload_name,
    validate_upload_size,
)
from app.agents.action_item_agent import ActionItemAgent
from app.agents.decision_agent import DecisionAgent
from app.agents.summary_agent import SummaryAgent
from app.agents.timeline_agent import TimelineAgent
from app.agents.transcription_agent import TranscriptionAgent
from app.config import get_settings
from app.database.models import (
    ActionItem,
    Decision,
    Meeting,
    Summary,
    TimelineEvent,
    Transcript,
    TranscriptSegment,
)
from app.database.session import SessionLocal, get_db
from app.schemas.meeting import (
    ActionItemResponse,
    DecisionResponse,
    MeetingUploadResponse,
    SummaryResponse,
    TimelineEventResponse,
    TranscriptResponse,
    TranscriptSegmentResponse,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/meetings", tags=["meetings"])

settings = get_settings()


UNEXPECTED_ERROR_MESSAGE = "processing stopped because of an unexpected error, please retry"


async def _process_transcription(meeting_id: str, file_path: Path) -> None:
    """
    Background entry point for one meeting. Whatever goes wrong inside the
    pipeline, the meeting ends as completed or failed, never stuck on
    processing until the next restart.
    """
    try:
        await _run_pipeline(meeting_id, file_path)
    except Exception:
        logger.exception("pipeline crashed", extra={"meeting_id": meeting_id})
        _mark_failed_if_processing(meeting_id, UNEXPECTED_ERROR_MESSAGE)


def _mark_failed_if_processing(meeting_id: str, error: str) -> None:
    db = SessionLocal()
    try:
        meeting = db.query(Meeting).filter_by(id=meeting_id).first()
        if meeting is not None and meeting.status == "processing":
            meeting.status = "failed"
            meeting.error = error
            db.commit()
    finally:
        db.close()


async def _run_pipeline(meeting_id: str, file_path: Path) -> None:
    """
    Runs in the background after upload. Transcribes the recording,
    then if that succeeds, runs the summary, action item, timeline and
    decision agents on the resulting transcript, all at once since they
    are independent of one another. Opens its own database session
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

        # Transcription succeeded, now run all four analysis agents
        # concurrently since none of them depend on each other. A
        # failure in any one of them does not affect the others or
        # roll back the transcript. The meeting stays "processing" until
        # they have finished, so a "completed" meeting always has its
        # full results.
        await _process_extractions(meeting_id=meeting_id, transcript_text=result.data.text)

    finally:
        db.close()


async def _process_extractions(meeting_id: str, transcript_text: str) -> None:
    action_agent = ActionItemAgent()
    timeline_agent = TimelineAgent()
    decision_agent = DecisionAgent()
    summary_agent = SummaryAgent()

    action_result, timeline_result, decision_result, summary_result = await asyncio.gather(
        action_agent.execute(transcript_text=transcript_text),
        timeline_agent.execute(transcript_text=transcript_text),
        decision_agent.execute(transcript_text=transcript_text),
        summary_agent.execute(transcript_text=transcript_text),
    )

    steps = (
        ("action items", action_result),
        ("timeline", timeline_result),
        ("decisions", decision_result),
        ("summary", summary_result),
    )
    failures = [
        f"{step} could not be extracted: {result.error}"
        for step, result in steps
        if not result.success
    ]

    db = SessionLocal()
    try:
        if summary_result.success:
            db.add(
                Summary(
                    meeting_id=meeting_id,
                    overview=summary_result.data.overview,
                    key_points=summary_result.data.key_points,
                )
            )
        else:
            logger.warning(
                "summary failed",
                extra={"meeting_id": meeting_id, "error": summary_result.error},
            )

        if action_result.success:
            for item in action_result.data:
                db.add(
                    ActionItem(
                        meeting_id=meeting_id,
                        description=item.description,
                        owner=item.owner,
                        due_date=item.due_date,
                    )
                )
        else:
            logger.warning(
                "action item extraction failed",
                extra={"meeting_id": meeting_id, "error": action_result.error},
            )

        if timeline_result.success:
            for event in timeline_result.data:
                db.add(
                    TimelineEvent(
                        meeting_id=meeting_id,
                        topic=event.topic,
                        summary=event.summary,
                        approx_time=event.approx_time,
                    )
                )
        else:
            logger.warning(
                "timeline extraction failed",
                extra={"meeting_id": meeting_id, "error": timeline_result.error},
            )

        if decision_result.success:
            for decision in decision_result.data:
                db.add(
                    Decision(
                        meeting_id=meeting_id,
                        decision=decision.decision,
                        context=decision.context,
                    )
                )
        else:
            logger.warning(
                "decision extraction failed",
                extra={"meeting_id": meeting_id, "error": decision_result.error},
            )

        # Partial results are kept, but a failed step is recorded on the meeting
        # so "no action items" can be told apart from "action items failed".
        # If every step failed there is nothing useful, so the meeting fails
        # and can be retried.
        meeting = db.query(Meeting).filter_by(id=meeting_id).first()
        if meeting is not None:
            meeting.status = "failed" if len(failures) == len(steps) else "completed"
            meeting.error = "; ".join(failures) or None

        db.commit()
        logger.info("extractions saved", extra={"meeting_id": meeting_id})
    finally:
        db.close()


UPLOAD_CHUNK_BYTES = 1024 * 1024


@router.post("/upload", response_model=MeetingUploadResponse)
async def upload_meeting(
    background_tasks: BackgroundTasks,
    file: UploadFile,
    db: Session = Depends(get_db),
) -> MeetingUploadResponse:
    try:
        validate_upload_name(
            file.filename, allowed_extensions_for(settings.transcription_provider)
        )
    except UploadValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    upload_dir = Path(settings.upload_dir)
    upload_dir.mkdir(parents=True, exist_ok=True)

    job_id = str(uuid.uuid4())
    # Keep only the final name component so a filename such as "../../x.mp3"
    # or "C:\\temp\\x.mp3" can never place the file outside the uploads folder.
    safe_name = Path(file.filename.replace("\\", "/")).name
    destination = upload_dir / f"{job_id}_{safe_name}"

    # Copy the upload to disk in chunks rather than reading it all into memory,
    # and stop as soon as it passes the limit so a huge file is never fully stored.
    max_size_mb = settings.effective_max_upload_mb
    max_size_bytes = max_size_mb * 1024 * 1024
    size_bytes = 0
    try:
        with destination.open("wb") as out:
            while chunk := await file.read(UPLOAD_CHUNK_BYTES):
                size_bytes += len(chunk)
                if size_bytes > max_size_bytes:
                    raise UploadValidationError(f"file exceeds the {max_size_mb}MB limit")
                out.write(chunk)
        validate_upload_size(size_bytes, max_size_mb)
    except UploadValidationError as exc:
        destination.unlink(missing_ok=True)
        raise HTTPException(status_code=400, detail=str(exc))

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
    timeline = [
        TimelineEventResponse(topic=t.topic, summary=t.summary, approx_time=t.approx_time)
        for t in meeting.timeline_events
    ]
    decisions = [
        DecisionResponse(decision=d.decision, context=d.context) for d in meeting.decisions
    ]
    summary = (
        SummaryResponse(overview=meeting.summary.overview, key_points=meeting.summary.key_points)
        if meeting.summary is not None
        else None
    )

    if meeting.transcript is None:
        return TranscriptResponse(
            job_id=job_id,
            status=meeting.status,
            summary=summary,
            action_items=action_items,
            timeline=timeline,
            decisions=decisions,
            error=meeting.error,
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
        summary=summary,
        action_items=action_items,
        timeline=timeline,
        decisions=decisions,
        error=meeting.error,
    )
