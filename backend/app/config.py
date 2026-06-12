from functools import lru_cache
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict

ENV_FILE = Path(__file__).resolve().parents[1] / ".env"


class Settings(BaseSettings):
    app_name: str = "AI Job Agent"
    app_env: str = "development"
    database_url: str = "sqlite:///./job_agent.db"
    frontend_origin: str = "http://localhost:3000"
    llm_provider: str = "offline"
    openai_api_key: str = ""
    openai_base_url: str = "https://api.openai.com/v1"
    openai_model: str = "gpt-4.1-mini"
    openai_embedding_model: str = "text-embedding-3-small"
    embedding_provider: str = "local"
    embedding_base_url: str = ""
    embedding_api_key: str = ""
    embedding_model: str = "backend/models/bge-small-zh-v1.5"
    embedding_device: str = "cpu"
    embedding_fallback: str = "offline-hashing"
    vector_backend: str = "sqlite"
    embedding_dimension: int = 512
    pgvector_test_database_url: str = ""

    model_config = SettingsConfigDict(env_file=ENV_FILE, env_file_encoding="utf-8-sig", extra="ignore")


@lru_cache
def get_settings() -> Settings:
    return Settings()
