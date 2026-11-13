from pathlib import Path
from typing import Any

from app.agents.base_agent import BaseAgent
from app.config import get_settings
from app.tools.groq_whisper_tool import transcribe_audio_groq
from app.tools.whisper_tool import TranscriptResult, transcribe_audio


class TranscriptionAgent(BaseAgent):
    """
    Turns a raw meeting recording into a transcript with timestamped
    segments. This is the first step of the pipeline, everything else
    downstream (action items, timeline, decisions, insights) reads
    from the output of this agent.

    The transcription itself is done either by Whisper running on this
    machine ("local") or by Groq's hosted Whisper ("groq"). Both give back
    the same kind of result. When no provider is passed in, the
    TRANSCRIPTION_PROVIDER setting decides.
    """

    name = "transcription_agent"
    max_retries = 2
    timeout_seconds = 600  # transcription can genuinely take a while on longer recordings
    retry_backoff_seconds = 5.0

    def __init__(self, model_size: str = "base", provider: str | None = None) -> None:
        self.model_size = model_size
        self.provider = provider or get_settings().transcription_provider

    async def run(self, file_path: str | Path, **kwargs: Any) -> TranscriptResult:
        if self.provider == "groq":
            return await transcribe_audio_groq(file_path=file_path)
        return await transcribe_audio(file_path=file_path, model_size=self.model_size)
