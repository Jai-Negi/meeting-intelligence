from pathlib import Path

ALLOWED_AUDIO_EXTENSIONS = {".mp3", ".m4a", ".wav", ".mp4", ".webm", ".ogg", ".flac", ".aac"}

# Groq's hosted Whisper does not accept aac, so it is refused up front rather
# than failing later in the background job.
GROQ_AUDIO_EXTENSIONS = ALLOWED_AUDIO_EXTENSIONS - {".aac"}


def allowed_extensions_for(transcription_provider: str) -> set[str]:
    """The file types the active transcriber can actually read."""
    if transcription_provider == "groq":
        return GROQ_AUDIO_EXTENSIONS
    return ALLOWED_AUDIO_EXTENSIONS


class UploadValidationError(Exception):
    """Raised when an uploaded file fails validation before processing starts."""


def validate_upload_name(
    filename: str | None, allowed_extensions: set[str] = ALLOWED_AUDIO_EXTENSIONS
) -> None:
    """Checks the filename and type, which can be done before any bytes are read."""
    if not filename:
        raise UploadValidationError("the uploaded file has no filename")

    extension = Path(filename).suffix.lower()
    if extension not in allowed_extensions:
        allowed = ", ".join(sorted(allowed_extensions))
        raise UploadValidationError(
            f"unsupported file type '{extension or 'unknown'}'. Allowed types: {allowed}"
        )


def validate_upload_size(size_bytes: int, max_size_mb: int) -> None:
    """Checks the size, so it can be called once the whole file has been received."""
    if size_bytes <= 0:
        raise UploadValidationError("the uploaded file is empty")

    if size_bytes > max_size_mb * 1024 * 1024:
        size_mb = size_bytes / (1024 * 1024)
        raise UploadValidationError(
            f"file is {size_mb:.1f}MB, which exceeds the {max_size_mb}MB limit"
        )


def validate_upload_file(
    filename: str | None,
    size_bytes: int,
    max_size_mb: int,
    allowed_extensions: set[str] = ALLOWED_AUDIO_EXTENSIONS,
) -> None:
    """
    Checks an uploaded file's name and size. Raises UploadValidationError
    with a clear, user facing message on the first problem found.
    """
    validate_upload_name(filename, allowed_extensions)
    validate_upload_size(size_bytes, max_size_mb)
