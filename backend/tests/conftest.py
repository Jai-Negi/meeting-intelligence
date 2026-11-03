import os
import tempfile

# These must be set before anything from the app package is imported, because
# the database engine and settings are created at import time. Pointing them at
# a throwaway folder guarantees the tests can never touch your real dev database
# or your real uploads folder.
_TEST_DIR = tempfile.mkdtemp(prefix="meeting_intelligence_tests_")
os.environ["DATABASE_URL"] = f"sqlite:///{_TEST_DIR}/test.db"
os.environ["UPLOAD_DIR"] = f"{_TEST_DIR}/uploads"

import pytest
from fastapi.testclient import TestClient

from app.api import routes_meetings
from app.database.models import Base
from app.database.session import engine
from app.main import app


@pytest.fixture
def client(tmp_path, monkeypatch):
    """A test client backed by a fresh, empty database and a private uploads folder."""
    Base.metadata.drop_all(bind=engine)
    monkeypatch.setattr(routes_meetings.settings, "upload_dir", str(tmp_path / "uploads"))
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def no_background(monkeypatch):
    """Stops uploads from kicking off Whisper and the LLM agents during route tests."""

    async def _noop(*args, **kwargs):
        return None

    monkeypatch.setattr(routes_meetings, "_process_transcription", _noop)
