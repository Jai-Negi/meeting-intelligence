import asyncio
import logging
import uuid
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.agents.action_item_agent import ActionItemAgent
from app.agents.decision_agent import DecisionAgent
from app.agents.timeline_agent import TimelineAgent
from app.agents.transcription_agent import TranscriptionAgent
from app.config import get_settings
from app.database.models import (
    ActionItem,
    Decision,
    Meeting,
    TimelineEvent,
    Transcript,
    TranscriptSegment,
)
from app.database.session import SessionLocal, get_db
from app.schemas.meeting import (
    ActionItemResponse,
    DecisionResponse,
    MeetingUploadResponse,
    TimelineEventResponse,
    TranscriptResponse,
    TranscriptSegmentResponse,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/meetings", tags=["meetings"])

settings = get_settings()


async def _process_transcription(meeting_id: str, file_path: Path) -> None:
    """
    Runs in the background after upload. Transcribes the recording,
    then if that succeeds, runs action item, timeline, and decision
    extraction on the resulting transcript, all at once since they
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

        # Transcription succeeded, now run all three extraction agents
        # concurrently since none of them depend on each other. A
        # failure in any one of them does not affect the others or
        # roll back the transcript.
        await _process_extractions(meeting_id=meeting_id, transcript_text=result.data.text)

    finally:
        db.close()


async def _process_extractions(meeting_id: str, transcript_text: str) -> None:
    action_agent = ActionItemAgent()
    timeline_agent = TimelineAgent()
    decision_agent = DecisionAgent()

    action_result, timeline_result, decision_result = await asyncio.gather(
        action_agent.execute(transcript_text=transcript_text),
        timeline_agent.execute(transcript_text=transcript_text),
        decision_agent.execute(transcript_text=transcript_text),
    )

    db = SessionLocal()
    try:
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

        db.commit()
        logger.info("extractions saved", extra={"meeting_id": meeting_id})
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
    timeline = [
        TimelineEventResponse(topic=t.topic, summary=t.summary, approx_time=t.approx_time)
        for t in meeting.timeline_events
    ]
    decisions = [
        DecisionResponse(decision=d.decision, context=d.context) for d in meeting.decisions
    ]

    if meeting.transcript is None:
        return TranscriptResponse(
            job_id=job_id,
            status=meeting.status,
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
        action_items=action_items,
        timeline=timeline,
        decisions=decisions,
        error=meeting.error,
    )
EOFcat > app/api/routes_meetings.py << 'EOF'
import asyncio
import logging
import uuid
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.agents.action_item_agent import ActionItemAgent
from app.agents.decision_agent import DecisionAgent
from app.agents.timeline_agent import TimelineAgent
from app.agents.transcription_agent import TranscriptionAgent
from app.config import get_settings
from app.database.models import (
    ActionItem,
    Decision,
    Meeting,
    TimelineEvent,
    Transcript,
    TranscriptSegment,
)
from app.database.session import SessionLocal, get_db
from app.schemas.meeting import (
    ActionItemResponse,
    DecisionResponse,
    MeetingUploadResponse,
    TimelineEventResponse,
    TranscriptResponse,
    TranscriptSegmentResponse,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/meetings", tags=["meetings"])

settings = get_settings()


async def _process_transcription(meeting_id: str, file_path: Path) -> None:
    """
    Runs in the background after upload. Transcribes the recording,
    then if that succeeds, runs action item, timeline, and decision
    extraction on the resulting transcript, all at once since they
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

        # Transcription succeeded, now run all three extraction agents
        # concurrently since none of them depend on each other. A
        # failure in any one of them does not affect the others or
        # roll back the transcript.
        await _process_extractions(meeting_id=meeting_id, transcript_text=result.data.text)

    finally:
        db.close()


async def _process_extractions(meeting_id: str, transcript_text: str) -> None:
    action_agent = ActionItemAgent()
    timeline_agent = TimelineAgent()
    decision_agent = DecisionAgent()

    action_result, timeline_result, decision_result = await asyncio.gather(
        action_agent.execute(transcript_text=transcript_text),
        timeline_agent.execute(transcript_text=transcript_text),
        decision_agent.execute(transcript_text=transcript_text),
    )

    db = SessionLocal()
    try:
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

        db.commit()
        logger.info("extractions saved", extra={"meeting_id": meeting_id})
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
    timeline = [
        TimelineEventResponse(topic=t.topic, summary=t.summary, approx_time=t.approx_time)
        for t in meeting.timeline_events
    ]
    decisions = [
        DecisionResponse(decision=d.decision, context=d.context) for d in meeting.decisions
    ]

    if meeting.transcript is None:
        return TranscriptResponse(
            job_id=job_id,
            status=meeting.status,
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
        action_items=action_items,
        timeline=timeline,
        decisions=decisions,
        error=meeting.error,
    )
