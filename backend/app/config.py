from functools import lru_cache
from typing import Literal
from pydantic_settings import BaseSettings, SettingsConfigDict


GROQ_MAX_UPLOAD_MB = 25  # the largest audio file Groq's free tier accepts


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # App
    app_name: str = "Meeting Intelligence Engine"
    environment: str = "development"
    debug: bool = True

    # Database
    database_url: str = "sqlite:///./meeting_intelligence.db"

    # LLM
    groq_api_key: str = ""
    anthropic_api_key: str = ""
    ollama_base_url: str = "http://localhost:11434"
    llm_provider: str = "groq"

    # Whisper
    whisper_model_size: str = "base"

    # Transcription: local runs Whisper on this machine, groq uses Groq's hosted Whisper
    transcription_provider: Literal["local", "groq"] = "local"
    groq_whisper_model: str = "whisper-large-v3-turbo"

    # File storage
    upload_dir: str = "./uploads"
    max_upload_size_mb: int = 500

    # CORS - comma separated list of allowed frontend origins
    cors_origins: str = "http://localhost:3000"

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def effective_max_upload_mb(self) -> int:
        """The upload limit that actually applies, given which transcriber is in use."""
        if self.transcription_provider == "groq":
            return min(self.max_upload_size_mb, GROQ_MAX_UPLOAD_MB)
        return self.max_upload_size_mb


@lru_cache
def get_settings() -> Settings:
    return Settings()
