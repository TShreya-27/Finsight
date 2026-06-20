"""Centralized configuration loaded from .env."""

from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import field_validator
from dotenv import load_dotenv


load_dotenv()

class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        extra="ignore"
    )

    PG_URL: str
    AUTH_PG_URL: str
    REDIS_URL: str

    TEMPORAL_ADDRESS: str = "localhost:7233"
    TEMPORAL_NAMESPACE: str = "default"
    TEMPORAL_TASK_QUEUE: str = "finsight-task-queue"
    TEMPORAL_ENABLED: bool = False
    JWT_SECRET_KEY: str
    AGNO_MODEL: str = "groq:llama-3.3-70b-versatile"
    MEMORY_MODEL: str = "groq:llama-3.1-8b-instant"

    GROQ_API_KEY: str


settings = Settings()
