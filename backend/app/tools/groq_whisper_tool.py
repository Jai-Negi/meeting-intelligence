import asyncio
import logging
from pathlib import Path

import httpx

from app.config import GROQ_MAX_UPLOAD_MB, get_settings
from app.tools.whisper_tool import TranscriptResult, TranscriptSegment

logger = logging.getLogger(__name__)

GROQ_TRANSCRIPTION_URL = "https://api.groq.com/openai/v1/audio/transcriptions"


class GroqTranscriptionError(Exception):
    """Raised when Groq's hosted Whisper cannot transcribe a file."""


def _describe_error(response: httpx.Response) -> str:
    try:
        message = response.json()["error"]["message"]
    except (ValueError, KeyError, TypeError):
        message = response.text[:200] or "no details given"
    return f"Groq transcription failed with status {response.status_code}: {message}"


async def transcribe_audio_groq(
    file_path: str | Path, model: str | None = None
) -> TranscriptResult:
    """
    Transcribes an audio file with Groq's hosted Whisper instead of running
    Whisper on this machine. Returns the same TranscriptResult as the local
    version, so nothing downstream needs to know which one was used.
    """
    settings = get_settings()
    file_path = Path(file_path)

    if not file_path.exists():
        raise FileNotFoundError(f"audio file not found: {file_path}")

    if not settings.groq_api_key:
        raise GroqTranscriptionError(
            "GROQ_API_KEY is not set, it is needed to transcribe with Groq"
        )

    size_mb = file_path.stat().st_size / (1024 * 1024)
    if size_mb > GROQ_MAX_UPLOAD_MB:
        raise GroqTranscriptionError(
            f"audio file is {size_mb:.1f}MB, Groq accepts at most {GROQ_MAX_UPLOAD_MB}MB per file"
        )

    audio = await asyncio.to_thread(file_path.read_bytes)
    model_name = model or settings.groq_whisper_model

    logger.info("groq transcription started", extra={"file": str(file_path), "model": model_name})

    async with httpx.AsyncClient(timeout=httpx.Timeout(300.0)) as client:
        response = await client.post(
            GROQ_TRANSCRIPTION_URL,
            headers={"Authorization": f"Bearer {settings.groq_api_key}"},
            data={"model": model_name, "response_format": "verbose_json"},
            files={"file": (file_path.name, audio)},
        )

    if response.status_code != 200:
        raise GroqTranscriptionError(_describe_error(response))

    payload = response.json()

    segments = [
        TranscriptSegment(
            start=float(segment["start"]),
            end=float(segment["end"]),
            text=segment["text"].strip(),
        )
        for segment in payload.get("segments", [])
    ]

    logger.info(
        "groq transcription completed",
        extra={"file": str(file_path), "segment_count": len(segments)},
    )

    return TranscriptResult(
        text=(payload.get("text") or "").strip(),
        language=payload.get("language") or "unknown",
        segments=segments,
    )
