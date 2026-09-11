from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


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

    # File storage
    upload_dir: str = "./uploads"
    max_upload_size_mb: int = 500


@lru_cache
def get_settings() -> Settings:
    return Settings()
