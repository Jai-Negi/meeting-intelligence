import pytest

from app.tools.validators import UploadValidationError, validate_upload_file


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
