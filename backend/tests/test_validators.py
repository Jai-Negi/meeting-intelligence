import pytest

from app.tools.validators import (
    GROQ_AUDIO_EXTENSIONS,
    UploadValidationError,
    allowed_extensions_for,
    validate_upload_file,
)


def test_valid_mp3_within_limit_passes():
    validate_upload_file(filename="recording.mp3", size_bytes=5 * 1024 * 1024, max_size_mb=500)


def test_valid_m4a_within_limit_passes():
    validate_upload_file(filename="audio.m4a", size_bytes=20 * 1024 * 1024, max_size_mb=500)


def test_extension_check_is_case_insensitive():
    validate_upload_file(filename="RECORDING.MP3", size_bytes=1024, max_size_mb=500)


def test_file_exactly_at_size_limit_passes():
    validate_upload_file(filename="recording.mp3", size_bytes=500 * 1024 * 1024, max_size_mb=500)


def test_missing_filename_raises():
    with pytest.raises(UploadValidationError, match="no filename"):
        validate_upload_file(filename=None, size_bytes=1024, max_size_mb=500)


def test_empty_filename_raises():
    with pytest.raises(UploadValidationError, match="no filename"):
        validate_upload_file(filename="", size_bytes=1024, max_size_mb=500)


def test_disallowed_extension_raises():
    with pytest.raises(UploadValidationError, match="unsupported file type"):
        validate_upload_file(filename="notes.txt", size_bytes=1024, max_size_mb=500)


def test_missing_extension_raises():
    with pytest.raises(UploadValidationError, match="unsupported file type"):
        validate_upload_file(filename="recording", size_bytes=1024, max_size_mb=500)


def test_empty_file_raises():
    with pytest.raises(UploadValidationError, match="empty"):
        validate_upload_file(filename="recording.mp3", size_bytes=0, max_size_mb=500)


def test_negative_size_raises():
    with pytest.raises(UploadValidationError, match="empty"):
        validate_upload_file(filename="recording.mp3", size_bytes=-5, max_size_mb=500)


def test_oversized_file_raises():
    with pytest.raises(UploadValidationError, match="exceeds"):
        validate_upload_file(filename="recording.mp3", size_bytes=600 * 1024 * 1024, max_size_mb=500)


def test_local_transcription_allows_aac():
    assert ".aac" in allowed_extensions_for("local")


def test_groq_transcription_refuses_aac_but_keeps_the_rest():
    allowed = allowed_extensions_for("groq")
    assert ".aac" not in allowed
    assert {".mp3", ".m4a", ".wav", ".mp4", ".webm", ".ogg", ".flac"} <= allowed


def test_a_narrower_allowed_set_is_enforced_and_listed():
    with pytest.raises(UploadValidationError, match="unsupported file type '.aac'") as exc:
        validate_upload_file(
            filename="call.aac",
            size_bytes=1024,
            max_size_mb=500,
            allowed_extensions=GROQ_AUDIO_EXTENSIONS,
        )
    assert ".aac" not in str(exc.value).split("Allowed types:")[1]
