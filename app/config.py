import os
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_env: Literal["dev", "staging", "prod"] = "dev"

    # Groq (LLM inference)
    groq_api_key: str
    groq_sonnet_model_id: str
    groq_haiku_model_id: str
    groq_fallback_model_id: str

    # Chroma (local vector store) + embeddings
    chroma_persist_directory: str = "./data/chroma"
    embedding_model_name: str = "sentence-transformers/all-mpnet-base-v2"

    # PostgreSQL
    postgres_dsn: str
    postgres_readonly_dsn: str
    # Local-dev password for the app_readonly role scripts/apply_schema.py
    # creates -- not a real external secret, just the local Postgres role's
    # own password (must match what's baked into postgres_readonly_dsn).
    postgres_readonly_password: str

    # Local filesystem (folded in from S3 -- see blueprint's "Storage
    # follow-up" amendment)
    raw_documents_dir: str = "./data/raw_documents"
    raw_customer_data_dir: str = "./data/raw_customer_data"

    # LangSmith
    langsmith_tracing: bool = True
    langsmith_api_key: str
    langsmith_project: str = "audience-match-dev"
    langsmith_workspace_id: str | None = None

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")


settings = Settings()

# LangChain's tracer reads these directly from the process environment, not from
# the Settings object above -- export them so tracing activates regardless of
# whether the value came from a real env var, .env, or a Settings default.
os.environ.setdefault("LANGSMITH_TRACING", str(settings.langsmith_tracing).lower())
os.environ.setdefault("LANGSMITH_API_KEY", settings.langsmith_api_key)
os.environ.setdefault("LANGSMITH_PROJECT", settings.langsmith_project)
if settings.langsmith_workspace_id:
    os.environ.setdefault("LANGSMITH_WORKSPACE_ID", settings.langsmith_workspace_id)
