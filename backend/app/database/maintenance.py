import logging

from app.database.models import Meeting
from app.database.session import SessionLocal

logger = logging.getLogger(__name__)

INTERRUPTED_MESSAGE = "processing was interrupted because the server restarted"


def fail_interrupted_jobs() -> int:
    """
    Marks every meeting still sitting on 'processing' as failed and returns
    how many were changed.

    Background jobs only live inside the running server process. Anything
    still marked as processing when the server starts up lost its job when
    the previous process stopped, so it will never finish by itself.
    """
    db = SessionLocal()
    try:
        stuck = db.query(Meeting).filter_by(status="processing").all()
        for meeting in stuck:
            meeting.status = "failed"
            meeting.error = INTERRUPTED_MESSAGE
        db.commit()

        if stuck:
            logger.warning("marked interrupted jobs as failed", extra={"count": len(stuck)})
        return len(stuck)
    finally:
        db.close()
