import logging
import uuid
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, HTTPException, UploadFile

from app.agents.transcription_agent import TranscriptionAgent
from app.config import get_settings
from app.schemas.meeting import (
    MeetingUploadResponse,
    TranscriptResponse,
    TranscriptSegmentResponse,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/meetings", tags=["meetings"])

settings = get_settings()

# In memory job store. This is fine for local development and demos,
# it will be replaced by the database backed job manager once that
# piece of the orchestrator is built.
_jobs: dict[str, dict] = {}


async def _process_transcription(job_id: str, file_path: Path) -> None:
    agent = TranscriptionAgent(model_size=settings.whisper_model_size)
    result = await agent.execute(file_path=file_path)

    if result.success:
        _jobs[job_id] = {
            "status": "completed",
            "text": result.data.text,
            "language": result.data.language,
            "segments": [
                {"start": s.start, "end": s.end, "text": s.text}
                for s in result.data.segments
            ],
            "error": None,
        }
    else:
        _jobs[job_id] = {
            "status": "failed",
            "text": None,
            "language": None,
            "segments": [],
            "error": result.error,
        }


@router.post("/upload", response_model=MeetingUploadResponse)
async def upload_meeting(
    background_tasks: BackgroundTasks, file: UploadFile
) -> MeetingUploadResponse:
    upload_dir = Path(settings.upload_dir)
    upload_dir.mkdir(parents=True, exist_ok=True)

    job_id = str(uuid.uuid4())
    destination = upload_dir / f"{job_id}_{file.filename}"

    contents = await file.read()
    destination.write_bytes(contents)

    _jobs[job_id] = {
        "status": "processing",
        "text": None,
        "language": None,
        "segments": [],
        "error": None,
    }

    logger.info(
        "meeting uploaded", extra={"job_id": job_id, "filename": file.filename}
    )

    background_tasks.add_task(_process_transcription, job_id, destination)

    return MeetingUploadResponse(
        job_id=job_id, filename=file.filename, status="processing"
    )


@router.get("/{job_id}", response_model=TranscriptResponse)
async def get_transcript(job_id: str) -> TranscriptResponse:
    job = _jobs.get(job_id)

    if job is None:
        raise HTTPException(status_code=404, detail="job not found")

    return TranscriptResponse(
        job_id=job_id,
        status=job["status"],
        text=job["text"],
        language=job["language"],
        segments=[TranscriptSegmentResponse(**s) for s in job["segments"]],
        error=job["error"],
    )
