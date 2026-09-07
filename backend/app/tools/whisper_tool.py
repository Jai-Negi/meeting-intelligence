import asyncio
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_model_cache: dict[str, Any] = {}


@dataclass
class TranscriptSegment:
    start: float
    end: float
    text: str


@dataclass
class TranscriptResult:
    text: str
    language: str
    segments: list[TranscriptSegment] = field(default_factory=list)


def _load_model(model_size: str):
    """
    Loads and caches the Whisper model in memory so repeated calls
    do not reload the model from disk every time.
    """
    if model_size not in _model_cache:
        import whisper

        logger.info("loading whisper model", extra={"model_size": model_size})
        _model_cache[model_size] = whisper.load_model(model_size)

    return _model_cache[model_size]


async def transcribe_audio(
    file_path: str | Path, model_size: str = "base"
) -> TranscriptResult:
    """
    Transcribes an audio file using Whisper.

    Whisper itself is synchronous and CPU or GPU bound, so the actual
    transcription runs in a background thread to avoid blocking the
    event loop while it works.
    """
    file_path = Path(file_path)

    if not file_path.exists():
        raise FileNotFoundError(f"audio file not found: {file_path}")

    def _run_transcription() -> dict:
        model = _load_model(model_size)
        return model.transcribe(str(file_path))

    logger.info("transcription started", extra={"file": str(file_path)})

    raw_result = await asyncio.to_thread(_run_transcription)

    segments = [
        TranscriptSegment(
            start=segment["start"], end=segment["end"], text=segment["text"].strip()
        )
        for segment in raw_result.get("segments", [])
    ]

    logger.info(
        "transcription completed",
        extra={"file": str(file_path), "segment_count": len(segments)},
    )

    return TranscriptResult(
        text=raw_result.get("text", "").strip(),
        language=raw_result.get("language", "unknown"),
        segments=segments,
    )
