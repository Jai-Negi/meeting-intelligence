from pathlib import Path
from typing import Any

from app.agents.base_agent import BaseAgent
from app.tools.whisper_tool import TranscriptResult, transcribe_audio


class TranscriptionAgent(BaseAgent):
    """
    Turns a raw meeting recording into a transcript with timestamped
    segments. This is the first step of the pipeline, everything else
    downstream (action items, timeline, decisions, insights) reads
    from the output of this agent.
    """

    name = "transcription_agent"
    max_retries = 2
    timeout_seconds = 600  # transcription can genuinely take a while on longer recordings
    retry_backoff_seconds = 5.0

    def __init__(self, model_size: str = "base") -> None:
        self.model_size = model_size

    async def run(self, file_path: str | Path, **kwargs: Any) -> TranscriptResult:
        return await transcribe_audio(file_path=file_path, model_size=self.model_size)
