import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.agents.email_agent import EmailAgent
from app.database.models import Meeting
from app.database.session import get_db
from app.schemas.email_draft import EmailDraftResponse

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/meetings", tags=["email"])


@router.post("/{job_id}/email", response_model=EmailDraftResponse)
async def draft_follow_up_email(job_id: str, db: Session = Depends(get_db)) -> EmailDraftResponse:
    """
    Drafts a follow up email for a finished meeting from its transcript,
    action items and decisions. The draft is generated fresh on every call
    and is not stored, so asking again simply gives a new draft.
    """
    meeting = db.query(Meeting).filter_by(id=job_id).first()

    if meeting is None:
        raise HTTPException(status_code=404, detail="job not found")

    if meeting.status != "completed" or meeting.transcript is None:
        raise HTTPException(
            status_code=409,
            detail="this meeting has not finished processing yet",
        )

    transcript_text = meeting.transcript.text
    action_items = [
        {"description": a.description, "owner": a.owner, "due_date": a.due_date}
        for a in meeting.action_items
    ]
    decisions = [{"decision": d.decision, "context": d.context} for d in meeting.decisions]

    result = await EmailAgent().execute(
        transcript_text=transcript_text,
        action_items=action_items,
        decisions=decisions,
    )

    if not result.success:
        logger.warning("email draft failed", extra={"job_id": job_id, "error": result.error})
        raise HTTPException(status_code=502, detail=f"could not draft the email: {result.error}")

    return EmailDraftResponse(subject=result.data.subject, body=result.data.body)
